# 部署文档

## 1. 环境要求

- Docker 24+
- Docker Compose v2
- 最低 8GB RAM (CPU模式)
- 推荐 16GB RAM + NVIDIA GPU (GPU模式)

## 2. 快速部署 (Docker Compose)

### 2.1 CPU 部署
```bash
cp .env.example .env
# 编辑 .env 修改密码等配置

docker compose up -d
```

### 2.2 GPU 部署
```bash
# 确保已安装 NVIDIA Container Toolkit
# https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html

cp .env.example .env
# 编辑 .env, 设置 AI_DEVICE=cuda:0

docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d

# 或使用仓库自带脚本远端部署（默认自动加载 docker-compose.gpu.yml）
./scripts/deploy.sh rebuild
```

说明:
- `docker-compose.gpu.yml` 现在使用 `gpus: all`，这是面向本地/非 Swarm `docker compose` 的显式 GPU 请求方式。
- 若宿主机未安装 NVIDIA Container Toolkit，请先执行官方安装与 `nvidia-ctk runtime configure --runtime=docker` 配置，否则 CUDA 镜像仍会以普通容器方式启动。
- 如需强制关闭 GPU 覆盖，可在执行脚本时设置 `DEPLOY_GPU=0 ./scripts/deploy.sh rebuild`。

### 2.3 验证部署
```bash
# 检查服务状态
docker compose ps

# 检查API健康
curl http://localhost:8000/health

# 访问前端
open http://localhost

# 访问Flower监控
open http://localhost:5555
```

## 3. 本地开发部署

### 3.1 后端
```bash
# 安装 PostgreSQL 和 Redis (或使用Docker)
docker compose up -d db redis

# 安装Python依赖
cd backend
pip install -r requirements.txt

# 数据库迁移
cd ..
alembic -c backend/alembic.ini upgrade head

# 启动API
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000

# 启动Celery Worker (新终端)
celery -A backend.app.tasks.celery_app worker --loglevel=info
```

### 3.2 AI引擎
```bash
pip install -r ai_engine/requirements.txt

# 首次运行会自动下载模型
# YOLOv8: ~6MB (nano)
# FunASR SenseVoice: ~200MB
# Silero-VAD: ~2MB
```

### 3.3 前端
```bash
cd frontend
npm install
npm run dev
# 访问 http://localhost:5173
```

## 4. 服务端口说明

| 服务 | 端口 | 说明 |
|------|------|------|
| Frontend | 80 | Nginx静态文件服务 |
| Backend API | 8000 | FastAPI |
| PostgreSQL | 5432 | 数据库 |
| Redis | 6379 | 缓存/消息队列 |
| Flower | 5555 | Celery监控面板 |

## 5. 环境变量说明

参考 `.env.example` 文件，关键配置:

| 变量 | 默认值 | 说明 |
|------|--------|------|
| POSTGRES_PASSWORD | changeme | 数据库密码 |
| SECRET_KEY | changeme | JWT签名密钥 |
| AI_DEVICE | cuda:0 | AI计算设备 |
| HF_TOKEN | - | HuggingFace Token (说话人分离) |
| MAX_UPLOAD_SIZE_MB | 2048 | 最大上传文件 |

## 6. 数据库初始化

```bash
# 使用Alembic创建表
alembic -c backend/alembic.ini upgrade head

# 或手动创建 (仅开发)
python -c "from backend.app.database import sync_engine, Base; from backend.app.models import *; Base.metadata.create_all(sync_engine)"
```
