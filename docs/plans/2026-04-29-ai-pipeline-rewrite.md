# AI Pipeline Rewrite Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rewrite the AI engine pipeline to actually work with GPU (Quadro P2200, 5GB VRAM, CUDA 12.2), sequential model loading, adaptive frame sampling, full audio chain (VAD+ASR+diarization+keywords), and fine-grained progress reporting to the frontend.

**Architecture:** 5-stage Celery pipeline (preprocess → video → audio → fusion → scoring) with per-substep progress callbacks via `update_state`. Models loaded sequentially to fit 5GB VRAM. Frontend PipelineProgress component reads real stage/substep data from status API.

**Tech Stack:** Python 3.11, PyTorch (CUDA 12.1), ultralytics (YOLOv8n-pose), FunASR (SenseVoice), pyannote.audio 3.1, Silero-VAD, Celery, FastAPI, React 18 + TypeScript + Ant Design

---

## Task 1: Fix Dockerfile Dependencies (GPU + Proper Install)

**Files:**
- Modify: `ai_engine/Dockerfile`
- Modify: `ai_engine/requirements.txt`
- Modify: `docker-compose.yml` (add GPU runtime to worker)
- Create: `docker-compose.gpu.yml` (if not exists, or modify existing)

**What to do:**

1. Rewrite `ai_engine/Dockerfile`:
   - Base image: `python:3.11-slim`
   - Install system deps: ffmpeg, libsndfile1, libpq-dev, gcc, libgl1, libglib2.0-0
   - Install torch FIRST with explicit CUDA 12.1 index URL: `pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121`
   - Then install remaining requirements WITHOUT `|| true` — failures must be visible
   - Set `ENV PYTHONPATH=/app`
   - Set `ENV CUDA_VISIBLE_DEVICES=0`

2. Clean up `ai_engine/requirements.txt`:
   - Remove `torch>=2.0.0` and `torchaudio>=2.0.0` (installed separately with CUDA index)
   - Keep: numpy, opencv-python, Pillow, ultralytics, funasr, modelscope, silero-vad, ffmpeg-python, soundfile, librosa, tqdm, loguru, pydantic, pydantic-settings
   - Add: `pyannote.audio>=3.1.0`

3. Modify `docker-compose.yml` celery_worker service:
   - Add `deploy.resources.reservations.devices` for GPU access
   - Or use docker-compose.gpu.yml override

4. Commit: `fix: Dockerfile GPU torch install, remove || true`

---

## Task 2: Rewrite Pipeline Core with Progress Callbacks

**Files:**
- Rewrite: `ai_engine/pipeline.py`
- Modify: `ai_engine/config.py`

**What to do:**

1. Rewrite `ai_engine/config.py`:
   - Add `protected_namespaces = ("settings_",)` to model_config (fix pydantic warning about `model_dir`)
   - Add `max_total_frames: int = 600` (adaptive sampling cap)
   - Add `gpu_memory_cleanup: bool = True`

2. Rewrite `ai_engine/pipeline.py` with this structure:

```python
class ExaminationPipeline:
    def __init__(self, config, progress_callback=None):
        self.config = config
        self._report_progress = progress_callback or (lambda **kw: None)

    def process(self, video_path: str) -> dict:
        # Stage 1: Preprocess
        self._report_progress(progress=2, stage="preprocessing", substep="video_info", detail="提取视频信息...")
        video_info = self._get_video_info(video_path)

        self._report_progress(progress=4, stage="preprocessing", substep="audio_extract", detail="分离音频轨道...")
        audio_path = self._extract_audio(video_path)

        # Stage 2: Video Analysis (5-45%)
        video_events = self._process_video(video_path, video_info)

        # Free GPU for audio
        self._cleanup_gpu()

        # Stage 3: Audio Analysis (45-70%)
        audio_events, voice_matches, transcription = self._process_audio(audio_path)

        self._cleanup_gpu()

        # Stage 4: Fusion (70-85%)
        all_events = self._fuse_events(video_events, audio_events)

        # Stage 5: Scoring (85-100%)
        scores = self._score(all_events, voice_matches, transcription)

        return {"events": all_events, "scores": scores, ...}

    def _process_video(self, video_path, video_info):
        # Calculate adaptive fps
        duration = video_info["duration"]
        target_fps = min(2.0, self.config.max_total_frames / duration)
        
        self._report_progress(progress=6, stage="video_analysis", substep="frame_sampling",
            detail=f"自适应采样: {target_fps:.1f}fps, 预计{int(duration * target_fps)}帧")
        frames = self._extract_frames(video_path, target_fps)
        total_frames = len(frames)
        
        self._report_progress(progress=10, stage="video_analysis", substep="pose_detection",
            detail=f"YOLOv8n-pose 人体检测+骨架 (0/{total_frames}帧)")
        # Load yolov8n-pose, run detection+pose in single pass
        # Report progress every 50 frames
        
        self._report_progress(progress=35, stage="video_analysis", substep="tracking",
            detail="ByteTrack 多人跟踪...")
        # ByteTrack tracking
        
        self._report_progress(progress=40, stage="video_analysis", substep="action_recognition",
            detail="动作识别: 按压/通气/跑步...")
        # Action recognition from pose sequences
        
        return events

    def _process_audio(self, audio_path):
        self._report_progress(progress=46, stage="audio_analysis", substep="vad",
            detail="Silero-VAD 语音活动检测...")
        # VAD
        
        self._report_progress(progress=50, stage="audio_analysis", substep="asr",
            detail="FunASR SenseVoice 语音识别...")
        # ASR
        
        self._report_progress(progress=58, stage="audio_analysis", substep="diarization",
            detail="pyannote.audio 说话人分离...")
        # Speaker diarization
        
        self._report_progress(progress=65, stage="audio_analysis", substep="keyword_matching",
            detail="关键词模板匹配 (13条规则)...")
        # Keyword matching
        
        return audio_events, voice_matches, transcription

    def _cleanup_gpu(self):
        import gc
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
```

Key points:
- `progress_callback` is a callable that receives `progress`, `stage`, `substep`, `detail`
- Models loaded lazily within each stage, freed after stage completes
- Adaptive frame sampling: `target_fps = min(2.0, 600 / duration)`
- Single YOLOv8n-pose model for both detection and pose (not two separate models)

3. Commit: `refactor: rewrite pipeline with progress callbacks and GPU memory management`

---

## Task 3: Rewrite Video Analysis Module

**Files:**
- Create: `ai_engine/video/pose_detector.py` (merged detection+pose)
- Modify: `ai_engine/video/extractor.py` (adaptive sampling)
- Modify: `ai_engine/video/tracker.py` (use pose_detector output)
- Keep: `ai_engine/video/action_recognizer.py` (mostly unchanged)

**What to do:**

1. `ai_engine/video/extractor.py` — Add adaptive sampling method:
```python
def extract_frames_adaptive(self, video_path: str, max_frames: int = 600) -> list[dict]:
    info = self.get_video_info(video_path)
    duration = info["duration"]
    target_fps = min(2.0, max_frames / max(duration, 1))
    return self.extract_frames(video_path, target_fps)  # modify extract_frames to accept fps param
```

2. Create `ai_engine/video/pose_detector.py`:
```python
class PoseDetector:
    """Merged person detection + pose estimation using YOLOv8n-pose.
    Single inference pass → bbox + 17 keypoints."""
    
    def __init__(self, device="cuda:0"):
        from ultralytics import YOLO
        self.model = YOLO("yolov8n-pose.pt")
        self.model.to(device)
    
    def detect_batch(self, frames: list[dict], progress_fn=None) -> list[dict]:
        """Process frames, return per-frame detections with poses."""
        results = []
        for i, frame_data in enumerate(frames):
            result = self.model(frame_data["frame"], verbose=False)
            # Extract bboxes + keypoints from single result
            detections = self._parse_result(result, frame_data["timestamp"])
            results.append(detections)
            if progress_fn and i % 50 == 0:
                progress_fn(i, len(frames))
        return results
    
    def release(self):
        del self.model
        # torch.cuda.empty_cache() called by pipeline
```

3. Modify `ai_engine/video/tracker.py` — Adapt to use pose_detector bboxes for tracking instead of running a separate YOLO model.

4. Commit: `refactor: merged pose detection, adaptive sampling`

---

## Task 4: Ensure Audio Analysis Chain Works

**Files:**
- Modify: `ai_engine/audio/extractor.py` (verify ffmpeg extraction)
- Modify: `ai_engine/audio/vad.py` (verify Silero-VAD)
- Modify: `ai_engine/audio/asr.py` (verify FunASR + GPU fallback)
- Modify: `ai_engine/audio/diarizer.py` (verify pyannote + HF token from config)
- Keep: `ai_engine/audio/keyword_matcher.py` (works as-is)

**What to do:**

The audio modules are already coded correctly. Main changes:
1. `asr.py`: Ensure SenseVoice model loads on GPU first, falls back to CPU (already has this logic, verify it works)
2. `diarizer.py`: Read HF token from `AIEngineConfig.hf_token` (already done)
3. `extractor.py`: Verify ffmpeg subprocess works in Docker container
4. All modules: Add `release()` method to free GPU memory after use

5. Commit: `refactor: audio modules GPU memory management`

---

## Task 5: Rewrite Celery Task with Progress Callback

**Files:**
- Modify: `backend/app/tasks/exam_task.py`
- Modify: `backend/app/schemas/exam.py`
- Modify: `backend/app/api/v1/exam.py`

**What to do:**

1. Rewrite `exam_task.py`:
```python
@celery_app.task(bind=True, max_retries=2, default_retry_delay=30)
def process_exam_task(self, exam_id: int, video_path: str):
    db = ...  # get sync db
    exam.status = "processing"
    db.flush()

    def progress_callback(progress, stage, substep, detail):
        self.update_state(state="PROGRESS", meta={
            "progress": progress,
            "stage": stage,
            "substep": substep,
            "detail": detail,
        })

    pipeline = ExaminationPipeline(progress_callback=progress_callback)
    result = pipeline.process(video_path)
    # save events, scores, update exam status
```

2. Modify `backend/app/schemas/exam.py` — Add fields to ExamStatusResponse:
```python
class ExamStatusResponse(BaseModel):
    id: int
    status: str
    progress: int = 0
    stage: str | None = None       # NEW
    substep: str | None = None     # NEW
    detail: str | None = None      # NEW
```

3. Modify `backend/app/api/v1/exam.py` — Return enriched status:
```python
# In get_exam_status endpoint:
if result.state == "PROGRESS" and isinstance(result.info, dict):
    progress = result.info.get("progress", 0)
    stage = result.info.get("stage")
    substep = result.info.get("substep")
    detail = result.info.get("detail")
return ExamStatusResponse(
    id=exam.id, status=exam.status, progress=progress,
    stage=stage, substep=substep, detail=detail
)
```

4. Commit: `feat: enriched progress reporting via Celery meta`

---

## Task 6: Update Frontend Pipeline Component

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/components/PipelineProgress.tsx`

**What to do:**

1. Update `types/index.ts` ExamStatus:
```typescript
export interface ExamStatus {
  id: number
  status: string
  progress: number
  stage?: string      // NEW
  substep?: string    // NEW
  detail?: string     // NEW
}
```

2. Update `PipelineProgress.tsx`:
- Accept `stage`, `substep`, `detail` props alongside `progress` and `status`
- When `stage` is provided, use it to determine active stage (instead of only progress ranges)
- When `detail` is provided, show it as the substep text (instead of cycling hardcoded strings)
- Keep the cycling animation as fallback when `detail` is not provided

3. Update `ExamDetail.tsx` to pass the new fields from status API to PipelineProgress.

4. Commit: `feat: frontend reads real pipeline progress from API`

---

## Task 7: Docker Compose GPU Configuration

**Files:**
- Modify: `docker-compose.yml` (remove `version` field)
- Modify or create: `docker-compose.gpu.yml`

**What to do:**

1. Remove `version: "3.8"` from `docker-compose.yml` (deprecated, causes warning)

2. In `docker-compose.gpu.yml`, add GPU runtime for celery_worker:
```yaml
services:
  celery_worker:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    environment:
      - NVIDIA_VISIBLE_DEVICES=all
      - CUDA_VISIBLE_DEVICES=0
```

3. Add HF_TOKEN to worker env (from .env file)

4. Commit: `feat: GPU docker compose configuration`

---

## Execution Order

Tasks 1-5 are backend, Task 6 is frontend, Task 7 is infra.

**Critical path:** Task 1 (deps) → Task 2 (pipeline core) → Task 3 (video) + Task 4 (audio) parallel → Task 5 (celery integration) → Task 6 (frontend) → Task 7 (docker)

**Verification after each task:**
- Tasks 1-5: `python -c "from ai_engine.pipeline import ExaminationPipeline"` should not error
- Task 6: `cd frontend && npm run build` should succeed
- Task 7: `docker compose -f docker-compose.yml -f docker-compose.gpu.yml build celery_worker` should succeed
</content>
</invoke>