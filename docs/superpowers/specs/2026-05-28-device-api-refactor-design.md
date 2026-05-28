# 设备直连改造:移除鉴权 + 合并上报 + CPR 指标重构

- **日期**: 2026-05-28
- **目标分支**: main
- **作者**: Allen
- **状态**: 设计待评审

---

## 1. 背景

当前后端假设交互模式为"用户登录 → 上传视频 → 单独上报传感器"。实际部署场景中,设备(CPR 模拟人 + 摄像头)是数据来源,登录鉴权和"当前用户"概念形同虚设。同时传感器上报接口字段(`compression_compliance_rate / ventilation_compliance_rate / ccf_percentage`)是聚合指标,设备端 `CPRData.java` 暴露的却是按压/通气原始计数器,两者口径不对齐,迫使设备端做服务器评分逻辑的镜像实现。

## 2. 目标

1. 去除登录/鉴权,所有接口面向**设备直连**
2. 视频上传 + 传感器数据上报**合并为单次** `multipart/form-data` 请求,以 `device_code` 标识数据来源
3. 传感器表与上报接口按 `CPRData.java` 重新设计:**设备只透传原始计数器**,服务器派生评分指标
4. 产出可分发给设备工程师的对接文档 `docs/device_api.md`

## 3. 非目标

- 不实现设备白名单/鉴权
- 不重写 AI 评分规则(`ai_engine/scoring/rules/objective_scoring.py` 继续消费 `*_compliance_rate / ccf_percentage`)
- 不动 `users` 表(模型保留,仅停用相关路由与依赖)

## 4. 系统改造概览

```
[Android 设备]
    │  POST /api/v1/exam/upload
    │  multipart: file=video.mp4
    │            device_code=DEV-001
    │            metrics={JSON 原始计数器}
    ▼
[FastAPI exam.py]
    ├─ 落盘视频
    ├─ 创建 exams 行(user_id=NULL, device_code=DEV-001)
    ├─ 解析 metrics → 派生 compliance_rate/ccf → 写入 cpr_metrics 行
    └─ 派发 Celery 任务
         │
         ▼
   [exam_task.py]
       从 cpr_metrics 读取派生指标
       → AI 流水线 → 评分入库 → 状态置 completed
```

## 5. 鉴权与路由清理

### 5.1 删除项

| 文件 | 处理 |
|---|---|
| `backend/app/api/v1/user.py` | 整个文件删除 |
| `backend/app/api/deps.py` 中的 `get_current_user / oauth2_scheme` | 删除 |
| `backend/app/core/security.py` | 删除整个文件 |
| `backend/app/schemas/user.py` 整个文件(Token/UserCreate/UserResponse) | 删除(数据库模型 User 仍保留) |

### 5.2 路由注册改动

`backend/app/api/v1/router.py`:

```python
api_v1_router.include_router(exam_router)
# 不再 include user_router 和 sensor_router
```

### 5.3 Exam 模型改动

`backend/app/models/exam.py`:

```python
user_id: Mapped[int | None] = mapped_column(
    Integer, ForeignKey("users.id"), nullable=True, index=True
)
device_code: Mapped[str] = mapped_column(String(64), index=True)
```

新增 `device_code` 必填字段(NOT NULL,长度 ≤ 64);`user_id` 改 nullable,上传时一律写 `None`。

### 5.4 GET 接口改造

所有 `/exam/*` GET 接口删除 `current_user: User = Depends(get_current_user)`,不再做归属校验;`GET /exams` 把签名改为 `device_code: str = Query(...)` 必填,按 `device_code` 过滤分页。

| 接口 | 改动 |
|---|---|
| `GET /exam/{exam_id}/status` | 删除 current_user |
| `GET /exam/{exam_id}/result` | 删除 current_user |
| `GET /exam/{exam_id}/timeline` | 删除 current_user |
| `GET /exam/{exam_id}/video` | 删除 current_user |
| `GET /exam/{exam_id}/report` | 删除 current_user |
| `GET /exam/{exam_id}/debug` | 无改动(已无鉴权) |
| `GET /exams` | 改为 `?device_code=xxx&page=&page_size=` |
| **新增** `GET /exam/{exam_id}/metrics` | 返回 `cpr_metrics` 行 |

`backend/app/services/exam_service.py::list_user_exams` 重命名为 `list_exams_by_device(db, device_code, skip, limit)`,过滤条件由 `Exam.user_id` 改为 `Exam.device_code`。

## 6. 合并上报接口

### 6.1 接口规格

**`POST /api/v1/exam/upload`**

- Content-Type: `multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file` | File | 是 | 视频文件,支持 `.mp4/.mov/.avi/.mkv/.webm`,大小受 `settings.max_upload_size_mb` 限制 |
| `device_code` | string (form) | 是 | 设备唯一码,1-64 字符 |
| `metrics` | string (form, JSON) | 否 | CPR 模拟人指标 JSON(无模拟人时省略) |

### 6.2 处理流程

1. 校验扩展名与大小(沿用现逻辑)
2. 落盘视频到 `settings.upload_dir`(绝对路径)
3. 创建 `Exam` 记录:`user_id=None`、`device_code=<param>`、`video_url=<abs>`、`status="pending"`
4. 若 `metrics` 非空:
   - JSON 解析失败 → 返回 400
   - 字段越界(负值/超范围)→ 返回 400
   - 通过校验 → 写 `cpr_metrics` 行,同时派生 `compression_compliance_rate / ventilation_compliance_rate / ccf_percentage` 三个字段
5. 派发 Celery 任务

### 6.3 响应

```json
{
  "exam_id": 42,
  "task_id": "celery-uuid",
  "device_code": "DEV-001",
  "metrics_received": true
}
```

错误响应继续遵循 FastAPI `HTTPException` 标准:`{ "detail": "<中文说明>" }`,常用状态码:400(参数错误)、413(视频过大)、500(落盘失败)。

### 6.4 调试接口

**`POST /api/v1/exam/mock-upload?perfect=true|false`**

不接收视频文件,生成假 exam_id + 假 metrics(替代旧 `/sensor/mock/*`)。

- `perfect=true`:生成满分 metrics(`compression_compliance_rate=95 / ventilation_compliance_rate=92 / ccf_percentage=82`,客观分 40/40)
- `perfect=false`:在合理区间内随机
- 仍生成 exam 行(状态直接置 `completed`),不派发 Celery

## 7. `cpr_metrics` 数据模型

### 7.1 新表结构(替换 `sensor_data` 表;由 `Base.metadata.create_all` 自动建表)

**主键与关联**
- `id` int PK
- `exam_id` int FK→exams.id, unique, index
- `device_code` varchar(64) index — 冗余存,便于按设备聚合查询

**会话时长**
- `session_duration_sec` float — 会话总秒数
- `compression_duration_sec` float — 有按压动作的累计秒数

**按压核心计数**

| 字段 | 类型 | 对应 CPRData.java |
|---|---|---|
| `press_total` | int | `pressNubmer` |
| `press_correct` | int | `pressRightNumber` |
| `press_wrong` | int | `pressWrongNumber` |
| `press_frequency` | float | `pressFrequency`(次/分) |
| `press_avg_depth` | float | 设备端聚合自 `pressValue` 序列(mm) |

**按压错误分布**

| 字段 | 类型 | 对应 |
|---|---|---|
| `press_too_deep` | int | `pressOversize` |
| `press_too_shallow` | int | `pressSmall` |
| `press_too_fast` | int | `pressMore` |
| `press_too_slow` | int | `pressLow` |
| `press_no_recoil` | int | `pressNoSet` |
| `press_wrong_position` | int | `pressPositionWrong` |

**通气核心**

| 字段 | 类型 | 对应 |
|---|---|---|
| `blow_total` | int | `blowNumber` |
| `blow_correct` | int | `blowRightNumber` |
| `blow_wrong` | int | `blowWrongNumber` |
| `blow_avg_volume` | float \| null | 设备端聚合自 `blowValue` |

**通气错误分布**

| 字段 | 类型 | 对应 |
|---|---|---|
| `blow_too_much` | int | `blowOversize` |
| `blow_too_little` | int | `blowSmall` |
| `blow_too_many` | int | `blowMore` |
| `blow_too_few` | int | `blowLow` |
| `blow_into_stomach` | int | 累计 `isBlowStomach=true` 的次数 |
| `blow_airway_blocked` | int | 累计 `isBlowWayIn=false` 的次数 |

**流程**
- `shoulder_tapped` bool — 对应 `clap_your_shoulders`

**服务器派生字段(入库存表)**
- `compression_compliance_rate` float — `press_correct / press_total * 100`(分母为 0 时记 0)
- `ventilation_compliance_rate` float — `blow_correct / blow_total * 100`
- `ccf_percentage` float — `compression_duration_sec / session_duration_sec * 100`(分母为 0 时记 0)

### 7.2 与 AI 流水线衔接

`backend/app/tasks/exam_task.py` 改为从 `cpr_metrics` 读取并构造 `sensor_dict`:

```python
sensor_dict = {
    "compression_compliance_rate": row.compression_compliance_rate,
    "ventilation_compliance_rate": row.ventilation_compliance_rate,
    "ccf_percentage": row.ccf_percentage,
    # 透传原始计数,后续若新增更细粒度评分规则可直接使用
    "press_total": row.press_total,
    "press_correct": row.press_correct,
    "blow_total": row.blow_total,
    "blow_correct": row.blow_correct,
}
```

`ai_engine/scoring/rules/objective_scoring.py` 不需要修改 —— 三个派生字段名与现有评分规则消费一致。

### 7.3 旧表/旧接口处理

- `sensor_data` 表失去代码引用后保留为孤儿表,不做迁移
- `backend/app/models/sensor.py`、`backend/app/schemas/sensor.py`、`backend/app/api/v1/sensor.py` 全部删除并新建对应文件(`models/cpr_metrics.py`、`schemas/cpr_metrics.py`,无 `api/v1/cpr_metrics.py`,合并到 `exam.py`)
- `backend/app/models/__init__.py` 中 `SensorData` 导出改为 `CprMetrics`

## 8. 设备工程师对接文档

**`docs/device_api.md`** —— 离线分发用的中文对接说明:

1. 基本信息(BaseURL、Content-Type、错误码约定)
2. `POST /api/v1/exam/upload` 完整字段表 + 错误响应表 + curl 示例 + Java OkHttp 示例
3. `POST /api/v1/exam/mock-upload` 调试接口说明
4. `metrics` JSON 全部字段:类型、范围、单位、对应 `CPRData.java` 字段、是否必填、边界场景填写说明
5. 服务器派生指标公式(让设备工程师理解打分逻辑)
6. 查询接口清单(`status` 轮询、`result` 获取最终分数、`metrics` 回显)

## 9. 影响面与风险

### 9.1 必改

- `backend/app/api/v1/exam.py` — 合并接口、所有 GET 去鉴权
- `backend/app/api/v1/router.py` — 移除 user/sensor 路由
- `backend/app/api/deps.py` — 删除 `get_current_user`
- `backend/app/models/exam.py` — 加 `device_code`、`user_id` 改 nullable
- `backend/app/models/__init__.py` — 替换 `SensorData` 导出
- `backend/app/main.py` — 移除 `User` 导入(若 ruff 报未使用)
- `backend/app/services/exam_service.py` — `create_exam` 签名加 `device_code`,`list_user_exams` 改 `list_exams_by_device`
- `backend/app/tasks/exam_task.py` — 读 `cpr_metrics`

### 9.2 删除

- `backend/app/api/v1/user.py`
- `backend/app/api/v1/sensor.py`
- `backend/app/core/security.py`
- `backend/app/schemas/user.py`(整个文件)
- `backend/app/schemas/sensor.py`
- `backend/app/models/sensor.py`

### 9.3 新建

- `backend/app/models/cpr_metrics.py`
- `backend/app/schemas/cpr_metrics.py`
- `docs/device_api.md`

### 9.4 测试

`tests/` 下涉及 `current_user` mock 或 `sensor_data` 表结构的用例会失败,同步更新或删除。`tests/ai_engine/test_pipeline.py` 不受影响。

### 9.5 数据风险

数据库为 PostgreSQL(`postgresql+asyncpg`,见 `backend/app/config.py`)。`Base.metadata.create_all` **不会** ALTER 已存在表 —— 老 `exams` 行缺 `device_code` 列、老 `sensor_data` 表结构与新 `cpr_metrics` 不兼容。

部署 192.168.31.82 时按以下顺序:
1. `scripts/deploy.sh` 中或运维手动连库执行:`DROP TABLE IF EXISTS sensor_data; DROP TABLE IF EXISTS exam_scores; DROP TABLE IF EXISTS exam_events; DROP TABLE IF EXISTS transcripts; DROP TABLE IF EXISTS speaker_role_maps; DROP TABLE IF EXISTS exams;`(级联依赖,顺序需先删子表)
2. 重启后端 → `lifespan` 中的 `create_all` 自动建新表
3. **部署前需明示运维**:此次升级会丢失所有历史考试记录与传感器数据

## 10. 验收标准

1. 启动后端 → Swagger 显示 `/api/v1/exam/upload` 接受 multipart 三字段,无 `/auth/*` 与 `/sensor/*` 路由
2. 用 curl 不带 Authorization 头直接调用 `/api/v1/exam/upload`,带视频 + device_code + metrics → 返回 200 + exam_id + task_id
3. 上报 `metrics` 后 `cpr_metrics` 表写入完整行,三个派生字段公式正确
4. Celery 任务消费 → 评分结果含按压/通气/CCF 三项客观分
5. `GET /api/v1/exams?device_code=DEV-001` 仅返回该设备的考试记录
6. `docs/device_api.md` 可独立分发,设备工程师按文档可独立完成对接
