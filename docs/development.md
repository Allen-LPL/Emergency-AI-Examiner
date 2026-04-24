# 开发规范

## 1. 项目结构

```
Emergency-AI-Examiner/
├── backend/         # FastAPI 后端
├── ai_engine/       # AI 处理引擎
├── frontend/        # React 前端
├── docs/            # 文档
├── docker-compose.yml
└── README.md
```

## 2. 命名规范

### Python (后端 + AI引擎)
- 文件名: snake_case (`exam_service.py`)
- 类名: PascalCase (`ScoringEngine`)
- 函数/变量: snake_case (`process_examination`)
- 常量: UPPER_SNAKE_CASE (`VOICE_SCORING_RULES`)
- 模块: snake_case

### TypeScript (前端)
- 文件名: PascalCase for components (`ScoreCard.tsx`), camelCase for utils
- 组件名: PascalCase (`VideoPlayer`)
- 函数/变量: camelCase (`getExamStatus`)
- 接口: PascalCase with prefix-free (`ScoreResult`)

### 数据库
- 表名: snake_case 复数 (`exam_scores`)
- 字段名: snake_case (`time_seconds`)

## 3. Git 规范

### 分支策略
- `main`: 稳定发布分支
- `develop`: 开发分支
- `feature/*`: 功能分支
- `fix/*`: 修复分支

### 提交信息格式
```
<type>(<scope>): <description>

类型:
- feat: 新功能
- fix: 修复
- refactor: 重构
- docs: 文档
- test: 测试
- chore: 构建/工具

示例:
feat(scoring): add phase4 defibrillation rules
fix(audio): handle empty ASR result gracefully
docs(api): update upload endpoint documentation
```

## 4. 模块规范

### 新增评分规则
1. 在 `ai_engine/scoring/rules/` 下对应阶段文件中添加新的 `ScoringRule` 子类
2. 实现 `evaluate(timeline, context)` 方法
3. 将实例加入对应阶段的 `PHASE*_RULES` 列表
4. 规则会自动被 `ScoringEngine` 加载

### 新增检测模型
1. 将模型权重放入 `ai_engine/models/`
2. 在对应模块中用 try/except 导入
3. 提供 fallback 到 CPU 或规则方法
4. 更新 `ai_engine/config.py` 配置项

### 新增API接口
1. 在 `backend/app/api/v1/` 下添加路由文件
2. 在 `backend/app/api/v1/router.py` 中注册路由
3. 添加对应的 Schema (pydantic model)
4. 添加对应的 Service 层函数

## 5. 依赖管理

- 后端: `backend/requirements.txt`
- AI引擎: `ai_engine/requirements.txt`
- 前端: `frontend/package.json`
- 新增依赖需同步更新对应的 requirements 文件和 Dockerfile

## 6. 日志规范

使用 loguru，统一格式:
```python
from loguru import logger

logger.info("Processing exam {exam_id}", exam_id=1)
logger.error("ASR failed: {error}", error=str(e))
```
