# Emergency-AI-Examiner

院前急救（CPR / AED / 三人协同急救）自动考核评分系统

通过上传考试视频（含音频），自动解析人员动作是否标准、语音口令是否准确，根据评分规则自动打分，输出评分报告、时间轴回放、扣分原因和改进建议。

## 功能特性

- **视频分析**: YOLOv8 人体检测 + ByteTrack 多人跟踪 + 姿态估计 + 动作识别
- **音频分析**: FunASR 中文语音识别 + 语音活动检测 + 说话人分离 + 关键词匹配
- **多模态融合**: 视频+音频+传感器事件统一时间轴
- **自动评分**: 基于规则引擎的100分制自动评分（6阶段+客观评分）
- **评分报告**: HTML/PDF 报告，含分项得分、雷达图、扣分原因、改进建议

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | FastAPI, SQLAlchemy 2.0, PostgreSQL, Redis, Celery |
| AI引擎 | YOLOv8, FunASR, Silero-VAD, pyannote.audio |
| 前端 | React 18, TypeScript, TailwindCSS, Ant Design |
| 部署 | Docker, Docker Compose, NVIDIA GPU |

## 快速开始

### Docker 部署（推荐）

```bash
git clone <repo-url>
cd Emergency-AI-Examiner

cp .env.example .env
# 编辑 .env 配置数据库密码、密钥等

# CPU 部署
docker compose up -d

# GPU 部署
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

访问:
- 前端: http://localhost
- API: http://localhost:8000/docs
- Celery监控: http://localhost:5555

### 本地开发

```bash
# 启动依赖服务
docker compose up -d db redis

# 后端
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload --port 8000

# Celery Worker
pip install -r ai_engine/requirements.txt
celery -A backend.app.tasks.celery_app worker --loglevel=info

# 前端
cd frontend && npm install && npm run dev
```

## 项目结构

```
Emergency-AI-Examiner/
├── backend/                 # FastAPI 后端
│   ├── app/
│   │   ├── api/v1/          # API 路由
│   │   ├── models/          # 数据库模型
│   │   ├── schemas/         # Pydantic 模型
│   │   ├── services/        # 业务逻辑
│   │   ├── tasks/           # Celery 任务
│   │   ├── core/            # 安全、认证
│   │   ├── config.py        # 配置
│   │   ├── database.py      # 数据库连接
│   │   └── main.py          # 入口
│   └── requirements.txt
├── ai_engine/               # AI 处理引擎
│   ├── video/               # 视频分析模块
│   ├── audio/               # 音频分析模块
│   ├── fusion/              # 多模态融合
│   ├── scoring/             # 评分引擎
│   │   └── rules/           # 各阶段评分规则
│   ├── pipeline.py          # 处理流水线
│   └── config.py            # AI配置
├── frontend/                # React 前端
│   └── src/
│       ├── pages/           # 页面组件
│       ├── components/      # 通用组件
│       └── api/             # API 客户端
├── docs/                    # 技术文档
├── docker-compose.yml       # Docker 部署
└── docker-compose.gpu.yml   # GPU 部署覆盖
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/v1/auth/register | 用户注册 |
| POST | /api/v1/auth/login | 用户登录 |
| POST | /api/v1/exam/upload | 上传考试视频 |
| GET | /api/v1/exam/{id}/status | 查询处理状态 |
| GET | /api/v1/exam/{id}/result | 获取评分结果 |
| GET | /api/v1/exam/{id}/timeline | 获取事件时间轴 |
| GET | /api/v1/exam/{id}/report | 获取HTML报告 |
| GET | /api/v1/exams | 考试列表 |

完整API文档启动后访问: http://localhost:8000/docs

## 评分规则

总分100分，分为6个考核阶段 + 客观评分:

| 阶段 | 分值 | 主要内容 |
|------|------|----------|
| 到达现场前 | 5 | 设备携带、跑步、环境安全 |
| 到达现场(一) | 5 | 设备放置、告知病情、开始按压 |
| 到达现场(二) | 10 | 球囊通气、心电监护、签字 |
| 到达现场(三) | 30 | 按压通气比、除颤、静脉通路、肾上腺素 |
| 到达现场(四) | 5 | 持续按压、评估、更换人员 |
| 到达现场(五) | 5 | 担架转运、知情告知、人文关怀 |
| 客观评分 | 40 | 按压质量、通气质量、CCF |

详见 [docs/scoring_rules.md](docs/scoring_rules.md)

## 文档

- [系统架构](docs/architecture.md)
- [API文档](docs/api.md)
- [部署指南](docs/deploy.md)
- [评分规则](docs/scoring_rules.md)
- [开发规范](docs/development.md)

## MVP 阶段划分

### 第一阶段 (当前)
- [x] 视频上传
- [x] 视频帧提取 + 人体检测 + 姿态估计
- [x] 音频提取 + 中文语音识别 + 关键词匹配
- [x] 基于规则的自动评分
- [x] HTML 评分报告

### 第二阶段 (规划)
- [ ] 多摄像头支持
- [ ] 实时评分 (流式视频)
- [ ] 边缘端部署 (TensorRT)
- [ ] 模型训练平台 (自定义设备检测)
- [ ] 传感器数据接入 (CPR模拟人)

## License

MIT
