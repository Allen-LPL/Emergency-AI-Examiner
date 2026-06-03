FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

# Avoid interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Install Python 3.11 + system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3.11-venv python3.11-dev python3-pip \
    ffmpeg libsndfile1 libpq-dev gcc libgl1 libglib2.0-0 curl \
    # weasyprint 生成 PDF 报告所需中文字体: 缺这两个包, 模板里所有中文 (标题/表头/规则名)
    # 会因 fontconfig 找不到 CJK 字形而渲染为空, 只剩阿拉伯数字, 见 backend/Dockerfile.
    fonts-noto-cjk fonts-noto-color-emoji && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 && \
    update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 && \
    ln -sf /usr/bin/python3.11 /usr/bin/python && \
    rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel

WORKDIR /app

ENV PYTHONPATH=/app
ENV CUDA_VISIBLE_DEVICES=0

# Install backend requirements (celery, redis, etc.)
COPY backend/requirements.txt /app/backend_requirements.txt
RUN pip install \
    --no-cache-dir \
    --default-timeout=1000 \
    --retries=20 \
    --timeout=1000 \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn \
    -r /app/backend_requirements.txt

# Install AI common requirements
COPY ai_engine/requirements.txt /app/ai_engine_requirements.txt
RUN pip install \
    --no-cache-dir \
    --default-timeout=1000 \
    --retries=20 \
    --timeout=1000 \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn \
    -r /app/ai_engine_requirements.txt

# Install fixed PyTorch CUDA 12.1
RUN pip install --no-cache-dir \
    torch==2.5.1+cu121 \
    torchvision==0.20.1+cu121 \
    torchaudio==2.5.1+cu121 \
    --index-url https://download.pytorch.org/whl/cu121

# Install AI libraries.
# Let ultralytics/FunASR/pyannote resolve their runtime deps normally;
# only keep silero-vad on --no-deps because torch/torchaudio are already pinned above.
RUN pip install --no-cache-dir \
    ultralytics==8.3.0 \
    modelscope==1.18.0 \
    funasr==1.1.6 \
    pyannote.audio==3.1.1

RUN pip install --no-cache-dir --no-deps silero-vad==5.1.2


# Pre-download YOLO pose model
RUN python -c "from ultralytics import YOLO; YOLO('yolov8n-pose.pt')" && \
    mkdir -p /app/models && \
    cp yolov8n-pose.pt /app/models/ 2>/dev/null || true

# 预下载 ASR 模型 (Paraformer-large 主 ASR + 标点) - 来自 ModelScope
# 不再预下载 SenseVoiceSmall, 项目已切到 Paraformer-large
RUN python -c "from funasr import AutoModel; AutoModel(\
    model='iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch', \
    punc_model='iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch', \
    device='cpu', hub='ms', disable_update=True)"

# 预下载 pyannote 说话人分离模型 (3.1)
# 需要 HF_TOKEN, 通过 build arg 传入. 失败不阻断 build (运行时再试一次).
ARG HF_TOKEN=""
RUN if [ -n "$HF_TOKEN" ]; then \
    python -c "import os; from pyannote.audio import Pipeline; \
    Pipeline.from_pretrained('pyannote/speaker-diarization-3.1', token=os.environ.get('HF_TOKEN'))" \
    || echo "[warn] pyannote 预下载失败, 运行时会重试"; \
    else \
    echo "[warn] 未提供 HF_TOKEN build arg, 跳过 pyannote 预下载"; \
    fi

COPY . .

CMD ["celery", "-A", "backend.app.tasks.celery_app", "worker", "--loglevel=info", "--concurrency=1"]
