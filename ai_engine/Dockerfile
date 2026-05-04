FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

# Avoid interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Install Python 3.11 + system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3.11-venv python3.11-dev python3-pip \
    ffmpeg libsndfile1 libpq-dev gcc libgl1 libglib2.0-0 curl && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 && \
    update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 && \
    ln -sf /usr/bin/python3.11 /usr/bin/python && \
    rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel

WORKDIR /app

ENV PYTHONPATH=/app
ENV CUDA_VISIBLE_DEVICES=0

# Install backend requirements first (changes less often)
COPY backend/requirements.txt /app/backend_requirements.txt
RUN pip install --no-cache-dir \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    -r /app/backend_requirements.txt


# Install AI engine requirements
COPY ai_engine/requirements.txt /app/ai_engine_requirements.txt
RUN pip install \
    --no-cache-dir \
    --default-timeout=1000 \
    --retries=20 \
    --timeout=1000 \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn \
    -r /app/ai_engine_requirements.txt

RUN pip uninstall -y torch torchvision torchaudio || true

RUN pip install --no-cache-dir \
    torch==2.5.1+cu121 \
    torchvision==0.20.1+cu121 \
    torchaudio==2.5.1+cu121 \
    --index-url https://download.pytorch.org/whl/cu121


# Pre-download YOLO pose model
RUN python -c "from ultralytics import YOLO; YOLO('yolov8n-pose.pt')" && \
    mkdir -p /app/models && \
    cp yolov8n-pose.pt /app/models/ 2>/dev/null || true

# Pre-download SenseVoiceSmall + VAD + Punctuation models
RUN python -c "from funasr import AutoModel; AutoModel(model='iic/SenseVoiceSmall', vad_model='iic/speech_fsmn_vad_zh-cn-16k-common-pytorch', punc_model='iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch', device='cpu', hub='ms', disable_update=True)"

COPY . .

CMD ["celery", "-A", "backend.app.tasks.celery_app", "worker", "--loglevel=info", "--concurrency=1"]
