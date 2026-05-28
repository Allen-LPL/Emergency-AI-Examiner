# 设备直连对接文档

> 面向 CPR 模拟人设备工程师, 描述如何将考试视频与传感器指标上报到院前急救自动考核系统。
> Last update: 2026-05-28

---

## 1. 基本信息

- **BaseURL (远端测试)**: `http://192.168.31.82:8001`
- **BaseURL (生产)**: 待运维提供
- **协议**: HTTP/1.1
- **无鉴权**: 不需要 token, 设备直连即可调用
- **字符集**: UTF-8

### 错误响应格式

所有错误以 FastAPI 标准格式返回:

```json
{ "detail": "<中文错误说明>" }
```

| HTTP Code | 含义 |
|---|---|
| 400 | 参数错误(扩展名/JSON/字段范围) |
| 404 | 资源不存在(exam_id 无效) |
| 413 | 文件过大(默认上限 2GB) |
| 500 | 服务器错误(落盘/数据库异常) |

---

## 2. 上报接口

### POST `/api/v1/exam/upload`

合并上传 - 一次性提交考试视频 + 设备码 + CPR 模拟人指标(可选)。

**请求**

- Content-Type: `multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file` | File | 是 | 考试视频, 支持 .mp4/.mov/.avi/.mkv/.webm, ≤ 2GB |
| `device_code` | string | 是 | 设备唯一码, 1-64 字符 |
| `metrics` | string (JSON) | 否 | CPR 指标 JSON 字符串, 无模拟人时可省略 |

**响应 200**

```json
{
  "exam_id": 42,
  "task_id": "8c4f9a-...",
  "device_code": "DEV-001",
  "metrics_received": true,
  "status": "pending"
}
```

**curl 示例**

```bash
curl -X POST http://192.168.31.82:8001/api/v1/exam/upload \
  -F "file=@/path/to/exam.mp4" \
  -F "device_code=DEV-001" \
  -F 'metrics={"session_duration_sec":180,"compression_duration_sec":145,"press_total":200,"press_correct":185,"press_wrong":15,"press_frequency":112,"press_avg_depth":53,"blow_total":20,"blow_correct":18,"blow_wrong":2}'
```

**Java OkHttp 示例**

```java
OkHttpClient client = new OkHttpClient();

String metricsJson = new Gson().toJson(metricsMap);

RequestBody body = new MultipartBody.Builder()
    .setType(MultipartBody.FORM)
    .addFormDataPart("file", "exam.mp4",
        RequestBody.create(MediaType.parse("video/mp4"), videoFile))
    .addFormDataPart("device_code", "DEV-001")
    .addFormDataPart("metrics", metricsJson)
    .build();

Request request = new Request.Builder()
    .url("http://192.168.31.82:8001/api/v1/exam/upload")
    .post(body)
    .build();

Response response = client.newCall(request).execute();
```

---

## 3. `metrics` JSON 字段定义

> 字段命名规范: 蛇形小写 (snake_case)。设备端 CPRData.java 字段为驼峰 (camelCase), 上报前需做命名转换。
> 所有计数字段非负; 浮点字段单位见下表。

### 3.1 会话时长 (用于派生 CCF)

| 字段 | 类型 | 必填 | 单位 | 说明 |
|---|---|---|---|---|
| `session_duration_sec` | float | 是 | 秒 | 考试总时长 |
| `compression_duration_sec` | float | 是 | 秒 | 有按压动作的累计时长 |

### 3.2 按压核心计数

| 字段 | 类型 | 必填 | 单位 | 对应 CPRData.java | 说明 |
|---|---|---|---|---|---|
| `press_total` | int | 是 | 次 | `pressNubmer` | 按压总次数 |
| `press_correct` | int | 是 | 次 | `pressRightNumber` | 按压正确次数 |
| `press_wrong` | int | 是 | 次 | `pressWrongNumber` | 按压错误次数 |
| `press_frequency` | float | 是 | 次/分 | `pressFrequency` | 平均按压频率 |
| `press_avg_depth` | float | 是 | mm | 聚合自 `pressValue` 序列 | 平均按压深度 |

### 3.3 按压错误分布(可选, 默认 0)

| 字段 | 类型 | 单位 | 对应 CPRData.java | 说明 |
|---|---|---|---|---|
| `press_too_deep` | int | 次 | `pressOversize` | 按压过深次数 |
| `press_too_shallow` | int | 次 | `pressSmall` | 按压过浅次数 |
| `press_too_fast` | int | 次 | `pressMore` | 按压过快次数 |
| `press_too_slow` | int | 次 | `pressLow` | 按压过慢次数 |
| `press_no_recoil` | int | 次 | `pressNoSet` | 未回弹次数 |
| `press_wrong_position` | int | 次 | `pressPositionWrong` | 位置错误次数 |

### 3.4 通气核心计数

| 字段 | 类型 | 必填 | 单位 | 对应 CPRData.java | 说明 |
|---|---|---|---|---|---|
| `blow_total` | int | 是 | 次 | `blowNumber` | 通气总次数 |
| `blow_correct` | int | 是 | 次 | `blowRightNumber` | 通气正确次数 |
| `blow_wrong` | int | 是 | 次 | `blowWrongNumber` | 通气错误次数 |
| `blow_avg_volume` | float | 否 | ml | 聚合自 `blowValue` | 平均通气量 |

### 3.5 通气错误分布(可选, 默认 0)

| 字段 | 类型 | 单位 | 对应 CPRData.java | 说明 |
|---|---|---|---|---|
| `blow_too_much` | int | 次 | `blowOversize` | 通气过多次数 |
| `blow_too_little` | int | 次 | `blowSmall` | 通气过少次数 |
| `blow_too_many` | int | 次 | `blowMore` | 多吹次数 |
| `blow_too_few` | int | 次 | `blowLow` | 少吹次数 |
| `blow_into_stomach` | int | 次 | 累计 `isBlowStomach=true` | 进胃次数 |
| `blow_airway_blocked` | int | 次 | 累计 `isBlowWayIn=false` | 气道未开放次数 |

### 3.6 流程

| 字段 | 类型 | 必填 | 对应 CPRData.java | 说明 |
|---|---|---|---|---|
| `shoulder_tapped` | bool | 否 | `clap_your_shoulders` | 是否完成拍肩(默认 false) |

### 3.7 字段填写边界

- 没有进行按压的会话: `press_total = 0`、`press_correct = 0`、其余按压字段都填 0
- 没有进行通气的会话: `blow_total = 0`、`blow_correct = 0`、其余通气字段都填 0
- `session_duration_sec` 必须 > 0,否则 CCF 派生为 0
- 完全没有 CPR 模拟人时,**整个 `metrics` 字段可省略**,服务器会按视频估算 CCF

---

## 4. 服务器派生指标公式

服务器接收到 `metrics` 后,会自动派生以下三个评分用指标并入库:

| 派生字段 | 公式 | 说明 |
|---|---|---|
| `compression_compliance_rate` | `press_correct / press_total * 100` | 按压达标率(%),分母 0 时记 0 |
| `ventilation_compliance_rate` | `blow_correct / blow_total * 100` | 通气达标率(%),分母 0 时记 0 |
| `ccf_percentage` | `compression_duration_sec / session_duration_sec * 100` | 胸外按压比 CCF(%),分母 0 时记 0 |

**评分规则(客观分 40/40)**

| 项目 | 计算 | 满分 |
|---|---|---|
| 按压质量 | `compression_compliance_rate ≥ 90 → 10`, 否则 `10 × rate/90` | 10 |
| 通气质量 | `ventilation_compliance_rate ≥ 90 → 10`, 否则 `10 × rate/90` | 10 |
| CCF 评分 | `min(20 × ccf/80, 20)` | 20 |

---

## 5. 查询接口

### 5.1 GET `/api/v1/exam/{exam_id}/status`

轮询考试处理进度。

**响应 200**

```json
{
  "id": 42,
  "status": "processing",
  "progress": 65,
  "stage": "scoring",
  "substep": "fusion",
  "detail": null
}
```

`status` 可能值: `pending` / `processing` / `completed` / `failed`。建议每 2-5 秒轮询一次直到 `completed` 或 `failed`。

### 5.2 GET `/api/v1/exam/{exam_id}/result`

获取最终评分(仅 `status=completed` 可用)。

**响应 200**

```json
{
  "exam_id": 42,
  "total_score": 87.5,
  "max_total": 100.0,
  "items": [...],
  "phase_scores": {...}
}
```

### 5.3 GET `/api/v1/exam/{exam_id}/metrics`

回显该考试的 CPR 指标 + 派生指标(供设备端确认上报无误)。

### 5.4 GET `/api/v1/exam/{exam_id}/report`

返回 HTML 评分报告,可直接浏览器打开。

### 5.5 GET `/api/v1/exam/{exam_id}/video`

下载 AI 标注后的视频文件(含姿态骨架与字幕)。

### 5.6 GET `/api/v1/exams?device_code=DEV-001&page=1&page_size=20`

按设备码分页查询考试列表。

---

## 6. 调试接口

### POST `/api/v1/exam/mock-upload?perfect=true`

不上传视频, 直接生成 mock 满分(或随机)考试记录, 用于设备端联调。

**Form 字段**: `device_code` (必填)

**Query 参数**: `perfect=true|false`(默认 true)

**响应 200**

```json
{
  "exam_id": 99,
  "device_code": "DEV-001",
  "mock": true,
  "perfect": true,
  "derived_metrics": {
    "compression_compliance_rate": 95.0,
    "ventilation_compliance_rate": 95.0,
    "ccf_percentage": 83.33
  }
}
```

---

## 7. 联系方式

线上 Swagger UI: `http://192.168.31.82:8001/docs`
如字段或接口与文档不一致,以 Swagger 为准并联系后端工程师。
