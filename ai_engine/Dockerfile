FROM python:3.11-slim

WORKDIR /app

ENV PYTHONPATH=/app
ENV CUDA_VISIBLE_DEVICES=0

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libsndfile1 libpq-dev gcc libgl1 libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

COPY ai_engine/requirements.txt /app/ai_engine_requirements.txt
COPY backend/requirements.txt /app/backend_requirements.txt

RUN pip install --no-cache-dir \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    -r /app/backend_requirements.txt

RUN pip install --no-cache-dir \
    torch torchaudio \
    --index-url https://download.pytorch.org/whl/cu121

RUN pip install --no-cache-dir \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    -r /app/ai_engine_requirements.txt

COPY . .

CMD ["celery", "-A", "backend.app.tasks.celery_app", "worker", "--loglevel=info", "--concurrency=1"]
