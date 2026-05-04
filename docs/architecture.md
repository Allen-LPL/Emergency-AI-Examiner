# 系统架构文档

## 1. 系统概述

Emergency-AI-Examiner 是一套院前急救（CPR / AED / 三人协同急救）自动考核评分系统。通过上传考试视频（含音频），自动解析人员动作、语音口令，根据评分规则自动打分，输出评分报告。

## 2. 架构图

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Frontend   │────>│   Backend    │────>│   Database   │
│  React+TS    │     │   FastAPI    │     │  PostgreSQL  │
│  TailwindCSS │<────│              │     └─────────────┘
│  Ant Design  │     │              │            │
└─────────────┘     │   /api/v1    │     ┌─────────────┐
                     │              │────>│    Redis     │
                     └──────┬───────┘     └─────────────┘
                            │                    │
                     ┌──────▼───────┐     ┌──────▼───────┐
                     │ Celery Task  │     │   Flower     │
                     │   Worker     │     │  Monitoring  │
                     └──────┬───────┘     └──────────────┘
                            │
                     ┌──────▼───────┐
                     │  AI Engine   │
                     ├──────────────┤
                     │ Video Module │
                     │ Audio Module │
                     │ Fusion       │
                     │ Scoring      │
                     └──────────────┘
```

## 3. 数据流

```
上传视频 -> FastAPI接收 -> 存储到磁盘 -> 创建Exam记录
         -> Celery任务入队 -> Worker提取任务
         -> AI Pipeline处理:
            1. 视频抽帧 (FrameExtractor)
            2. 人体检测+跟踪 (ObjectDetector + PersonTracker)
            3. 姿态估计 (PoseEstimator)
            4. 动作识别 (ActionRecognizer)
            5. 音频提取 (AudioExtractor)
            6. 语音活动检测 (VoiceActivityDetector)
            7. 语音识别 (SpeechRecognizer / FunASR)
            8. 说话人分离 (SpeakerDiarizer)
             9. 角色推断 (SpeakerRoleInferrer) - 医生/护士/驾驶员
             10. 话术模板匹配 (TemplateMatcher) - 替代旧KeywordMatcher
             11. 多模态事件融合 (EventMerger)
             12. 跨模态评分引擎 (ScoringEngine) - 音频触发+视频辅证+传感器验证
             13. 报告生成 (ReportGenerator)
         -> 结果写入数据库 -> 状态更新为completed
         -> 前端轮询获取结果 -> 展示评分报告
```

## 4. 模块说明

### 4.1 后端 (backend/)
- **FastAPI**: RESTful API, 异步处理
- **SQLAlchemy 2.0**: ORM, 支持async/sync双模式
- **Celery**: 异步任务队列，处理耗时的AI分析
- **Redis**: 消息队列 + 任务进度缓存

### 4.2 AI引擎 (ai_engine/)
- **视频模块**: YOLOv8检测 + ByteTrack跟踪 + YOLO-Pose姿态 + 规则动作识别
- **音频模块**: FunASR中文语音识别 + Silero-VAD + pyannote说话人分离 + 角色推断 + 话术模板匹配
- **融合模块**: 多模态事件合并 + 统一时间轴 + 时间窗口查询
- **评分模块**: 跨模态评分引擎(音频主轴+视频辅证+传感器验证)，38条规则覆盖6阶段+客观评分

### 4.3 前端 (frontend/)
- **React 18 + TypeScript**: 类型安全的前端
- **TailwindCSS + Ant Design**: UI框架
- **3个核心页面**: 首页(上传+列表)、详情页(视频+时间轴)、报告页(评分+雷达图)

## 5. 技术选型理由

| 组件 | 选型 | 理由 |
|------|------|------|
| 后端框架 | FastAPI | 高性能异步, 自动API文档, Python生态 |
| 数据库 | PostgreSQL | JSON字段支持, 企业级稳定性 |
| 任务队列 | Celery+Redis | Python生态标准方案, GPU任务隔离 |
| 目标检测 | YOLOv8 | 速度快, 易部署, 支持追踪 |
| 姿态估计 | YOLO-Pose | 与检测模型统一, 无需额外依赖 |
| 语音识别 | FunASR | 中文识别最优, 支持时间戳 |
| 前端 | React+TS | 组件化, 类型安全, 生态丰富 |
