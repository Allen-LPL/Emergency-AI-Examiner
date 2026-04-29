# AI Pipeline Rewrite Design

## Context

Current AI pipeline has correct architecture but dependencies fail to install (Dockerfile `|| true` swallows errors). All AI modules are skipped at runtime. Need full rewrite with working dependencies, GPU acceleration, and real-time progress reporting.

## Hardware

- Quadro P2200: 5GB VRAM, CUDA 12.2, Turing arch
- YOLO inference ~500MB VRAM, FunASR ~1GB, pyannote ~500MB
- Can run models sequentially (not simultaneously) to fit in 5GB
- HuggingFace token available for pyannote speaker diarization

## Architecture: 5-Stage Pipeline

```
Video File → Celery Task
  │
  ├─ Stage 1: Preprocessing (0-5%)
  │   ├─ Video info extraction (duration/resolution/frame count)
  │   └─ Audio track separation (ffmpeg → WAV 16kHz)
  │
  ├─ Stage 2: Video Analysis (5-45%)
  │   ├─ Adaptive frame sampling (target <600 frames total)
  │   │   - 5min video → 2fps → 600 frames
  │   │   - 30min video → 0.33fps → 600 frames
  │   ├─ YOLOv8n-pose: person detection + 17-keypoint skeleton (single inference)
  │   ├─ ByteTrack: multi-person tracking (persistent IDs)
  │   ├─ Action recognition: compression/ventilation/running/kneeling (rule engine)
  │   └─ Free GPU memory after video stage
  │
  ├─ Stage 3: Audio Analysis (45-70%)
  │   ├─ Silero-VAD: speech segment detection
  │   ├─ FunASR SenseVoice: Chinese ASR with word-level timestamps
  │   ├─ pyannote.audio 3.1: speaker diarization (who said what when)
  │   ├─ Keyword template matching (13 rules across 6 phases)
  │   └─ Free GPU memory after audio stage
  │
  ├─ Stage 4: Multimodal Fusion (70-85%)
  │   ├─ Merge video + audio events onto unified timeline
  │   └─ Temporal correlation (e.g., "said X then did action Y within Z seconds")
  │
  └─ Stage 5: Scoring + Report (85-100%)
      ├─ 6-phase rule engine scoring (100 points)
      ├─ Generate deduction reasons + improvement suggestions
      └─ Write events + scores to database
```

## Key Design Decisions

### 1. Merged Detection + Pose (Single Model)

Use `yolov8n-pose.pt` instead of separate detector + pose estimator. One inference pass gives both bounding boxes and 17 keypoints. Halves the video processing time.

### 2. Adaptive Frame Sampling

Cap total frames at 600 regardless of video duration:
- `target_fps = min(2.0, 600 / duration_seconds)`
- 5min → 2fps (600 frames), 10min → 1fps (600 frames), 30min → 0.33fps (594 frames)

GPU inference at ~15ms/frame → 600 frames ≈ 9 seconds for detection.

### 3. Sequential GPU Usage

5GB VRAM is tight. Load models one at a time:
1. Load YOLOv8n-pose → run video → `del model; torch.cuda.empty_cache()`
2. Load FunASR → run ASR → free
3. Load pyannote → run diarization → free

### 4. Fine-Grained Progress Reporting

Current: 5 coarse progress points (10/40/60/80/90%).
New: Per-substep progress via Celery `update_state`:

```python
self.update_state(state="PROGRESS", meta={
    "progress": 23,
    "stage": "video_analysis",
    "substep": "pose_detection",
    "detail": "已处理 150/600 帧",
})
```

Backend status API returns these fields. Frontend PipelineProgress component reads real substep data instead of hardcoded text.

### 5. Equipment Detection Strategy

No custom training data. COCO generic model cannot detect defibrillators/medicine boxes. Strategy:
- Equipment-related scoring primarily via audio keywords (already implemented)
- COCO object classes used only as auxiliary signals (person count, scene context)
- Phase 2 future: fine-tune YOLOv8 with labeled medical equipment data

## Files to Create/Modify

### Backend
- `ai_engine/pipeline.py` — Full rewrite with 5-stage architecture, progress callbacks
- `ai_engine/config.py` — Add adaptive sampling config, GPU memory management
- `ai_engine/video/extractor.py` — Add adaptive frame sampling
- `ai_engine/video/pose_detector.py` — NEW: merged detection+pose using yolov8n-pose
- `ai_engine/video/tracker.py` — Minor: use pose_detector output
- `ai_engine/video/action_recognizer.py` — Keep existing logic, improve interface
- `ai_engine/Dockerfile` — Fix dependencies: GPU torch, proper install without || true
- `backend/app/tasks/exam_task.py` — Pass progress callback to pipeline
- `backend/app/schemas/exam.py` — Add stage/substep/detail to ExamStatusResponse
- `backend/app/api/v1/exam.py` — Return enriched status data
- `docker-compose.gpu.yml` — GPU runtime for worker

### Frontend
- `frontend/src/components/PipelineProgress.tsx` — Read real stage/substep from API
- `frontend/src/types/index.ts` — Update ExamStatus type with stage/substep fields

## Estimated Processing Time (Quadro P2200)

| Stage | 5min video | 30min video |
|-------|-----------|-------------|
| Preprocessing | 5s | 15s |
| Video (YOLOv8n-pose GPU) | 15s | 15s (same frame count) |
| Audio (FunASR GPU) | 60s | 5min |
| Speaker diarization (pyannote GPU) | 30s | 3min |
| Fusion + Scoring | <1s | <1s |
| **Total** | **~2min** | **~9min** |
</content>
</invoke>