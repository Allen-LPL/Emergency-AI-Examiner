# Emergency-AI-Examiner Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an automated scoring system for pre-hospital emergency (CPR/AED/3-person team) examinations that analyzes video + audio to score performance against a 100-point rubric.

**Architecture:** FastAPI backend with Celery async tasks, PostgreSQL for persistence, Redis for task queue. AI engine as a separate Python package with video (YOLOv8 + MMPose), audio (FunASR), fusion, and scoring modules. React + Tailwind + Ant Design frontend. Docker Compose for deployment with NVIDIA GPU support.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, PostgreSQL, Redis, Celery, YOLOv8, MMPose, FunASR, React 18, TailwindCSS, Ant Design, Docker

---

## Scoring Rules Summary (from Excel)

### Assessment Modalities
- **Video (D)**: Visual detection of actions, equipment, positioning
- **Voice (E)**: Keyword detection in spoken Chinese commands
- **Time (F)**: Timing constraints between events
- **Sensor (G)**: CPR manikin data (compression quality, ventilation) - Phase 2

### Phase Breakdown (100 points total)

#### Phase 1: Before Arrival (5 pts)
| # | Rule | Points | Modality | Detection |
|---|------|--------|----------|-----------|
| 1 | Carry defibrillator monitor | 1 | Video | Object detection |
| 2 | Carry emergency medicine box | 1 | Video | Object detection |
| 3 | Carry breathing bag | 1 | Video | Object detection |
| 4 | Running to scene (urgency) | 1 | Video | Action recognition |
| 5 | Assess environment safety | 1 | Voice | Keywords: "安全" |

#### Phase 2: Arrival Step 1 (5 pts)
| # | Rule | Points | Modality | Detection |
|---|------|--------|----------|-----------|
| 1 | Equipment placed properly | 1 | Video | Object placement detection |
| 2 | Assess patient, inform family (within 20s) | 1 | Voice+Time | Keywords: "停","救"; Time < 20s |
| 3 | Start chest compression (within 15s of equipment placement) | 3 | Video+Time | Action: chest_compression; Time < 15s from equipment_placed |

#### Phase 3: Arrival Step 2 (10 pts) - Subjective
| # | Rule | Points | Modality | Detection |
|---|------|--------|----------|-----------|
| 1 | Prepare breathing bag, correct technique | 3 | Sensor | Ventilation 500-600ml |
| 2 | Connect ECG monitor, correct position | 3 | Video | Object detection: ECG leads |
| 3 | ECG printing completed | 1 | Video | Paper output detection |
| 4 | Inform family to sign ECG | 1 | Voice | Keywords: "签","字" |
| 5 | Smooth cooperation (interruption < 15s) | 2 | Time | Gap analysis |

#### Phase 4: Arrival Step 3 (30 pts) - Main Operations
| # | Rule | Points | Modality | Detection |
|---|------|--------|----------|-----------|
| 1a | Compression-ventilation ratio 30:2 | 2 | Sensor | Ratio detection |
| 1b | Standard 5 cycles (1pt each) | 5 | Sensor | Cycle counting |
| 2 | Evaluate every 5 cycles | 2 | Voice | Keywords: "离开","让开" |
| 3a | IV access at appropriate time | 2 | Voice | Keywords: "开通","静脉" |
| 3b | Epinephrine 1mg every 3-5min | 2 | Voice | Keywords: "肾上腺素","推注","1mg" |
| 4a | Apply conductive paste | 2 | Video | Action detection |
| 4b | Paste position correct | 2 | Video | Position analysis |
| 4c | Energy correct | 2 | Video | Auto-scored if 4a+4b correct |
| 4d | Others clear before defib | 2 | Voice | Keywords: "离开","让开" |
| 4e | Skilled operation (interruption < 15s) | 2 | Time | Gap analysis |
| 4f | Continue compression during defib | 2 | Sensor | Compression detection |
| 4g | Immediate compression after defib | 2 | Sensor | Time < 3s |
| 5 | Informed consent | 1 | Voice | Keywords: "签","字" |
| 6 | Smooth cooperation | 2 | Video | Overall assessment |

#### Phase 5: Arrival Step 4 (5 pts)
| # | Rule | Points | Modality | Detection |
|---|------|--------|----------|-----------|
| 1 | Continue 5 compression cycles | 2 | Sensor | Cycle counting |
| 2 | Re-evaluate | 1 | Voice | Keywords: "离开","让开" |
| 3 | Effective compression handover | 2 | Voice | Keywords: "替","换","按压" |

#### Phase 6: Arrival Step 5 (5 pts)
| # | Rule | Points | Modality | Detection |
|---|------|--------|----------|-----------|
| 1 | Scoop stretcher transfer | 1 | Video | Object: scoop stretcher |
| 2 | Transfer informed consent | 1 | Voice | Keywords: "同意","签","字" |
| 3 | Body camera warning | 1 | - | Manual/reserved |
| 4 | Continuous monitoring during transfer | 1 | Voice | Keywords: "血压","氧饱和度","呼末CO2","心律","生命体征" |
| 5 | Humanistic care | 1 | Voice | Keywords: "抢救","尽力" |

#### Objective Scoring (40 pts)
| # | Rule | Points | Modality | Formula |
|---|------|--------|----------|---------|
| 1 | Compression quality | 10 | Sensor | >90%: 10pts; <90%: 10*(value/90%) |
| 2 | Effective ventilation | 10 | Sensor | >90%: 10pts; <90%: 10*(value/90%) |
| 3 | CCF (Chest Compression Fraction) | 20 | Sensor+Time | 20*(value/80%) |

---

## Task 1: Project Scaffolding

**Files:**
- Create: Full directory structure
- Create: `backend/requirements.txt`
- Create: `frontend/package.json`
- Create: `ai_engine/requirements.txt`
- Create: `.gitignore`
- Create: `.env.example`

**Directory Structure:**
```
Emergency-AI-Examiner/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── deps.py
│   │   │   └── v1/
│   │   │       ├── __init__.py
│   │   │       ├── router.py
│   │   │       ├── exam.py
│   │   │       └── user.py
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── exam.py
│   │   │   ├── event.py
│   │   │   └── score.py
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── exam.py
│   │   │   ├── event.py
│   │   │   └── score.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── exam_service.py
│   │   │   └── report_service.py
│   │   └── tasks/
│   │       ├── __init__.py
│   │       ├── celery_app.py
│   │       └── exam_task.py
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   ├── alembic.ini
│   ├── requirements.txt
│   └── Dockerfile
├── ai_engine/
│   ├── __init__.py
│   ├── config.py
│   ├── pipeline.py
│   ├── video/
│   │   ├── __init__.py
│   │   ├── extractor.py
│   │   ├── detector.py
│   │   ├── tracker.py
│   │   ├── pose_estimator.py
│   │   └── action_recognizer.py
│   ├── audio/
│   │   ├── __init__.py
│   │   ├── extractor.py
│   │   ├── vad.py
│   │   ├── asr.py
│   │   ├── diarizer.py
│   │   └── keyword_matcher.py
│   ├── fusion/
│   │   ├── __init__.py
│   │   ├── event_merger.py
│   │   └── timeline.py
│   ├── scoring/
│   │   ├── __init__.py
│   │   ├── engine.py
│   │   ├── rules/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── phase1_before_arrival.py
│   │   │   ├── phase2_arrival_step1.py
│   │   │   ├── phase3_arrival_step2.py
│   │   │   ├── phase4_arrival_step3.py
│   │   │   ├── phase5_arrival_step4.py
│   │   │   ├── phase6_arrival_step5.py
│   │   │   └── objective_scoring.py
│   │   └── report_generator.py
│   ├── models/
│   │   └── .gitkeep
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── api/
│   │   │   └── index.ts
│   │   ├── components/
│   │   │   ├── Layout.tsx
│   │   │   ├── VideoPlayer.tsx
│   │   │   ├── Timeline.tsx
│   │   │   ├── ScoreCard.tsx
│   │   │   └── RadarChart.tsx
│   │   ├── pages/
│   │   │   ├── Home.tsx
│   │   │   ├── ExamDetail.tsx
│   │   │   └── Report.tsx
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   └── index.css
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   ├── vite.config.ts
│   └── Dockerfile
├── docs/
│   ├── architecture.md
│   ├── api.md
│   ├── deploy.md
│   ├── scoring_rules.md
│   └── development.md
├── docker-compose.yml
├── docker-compose.gpu.yml
├── .env.example
├── .gitignore
└── README.md
```

---

## Task 2: Backend Core (FastAPI + DB + Celery)

**Files:**
- Create: `backend/app/main.py` - FastAPI application entry
- Create: `backend/app/config.py` - Settings via pydantic-settings
- Create: `backend/app/database.py` - SQLAlchemy async engine + session
- Create: `backend/app/models/*.py` - All DB models
- Create: `backend/app/schemas/*.py` - Pydantic schemas
- Create: `backend/app/api/v1/*.py` - API routes
- Create: `backend/app/services/*.py` - Business logic
- Create: `backend/app/tasks/*.py` - Celery tasks
- Create: `backend/requirements.txt`
- Create: `backend/alembic.ini` + `backend/alembic/env.py`

### Database Models:
- `users`: id, username, password_hash, created_at
- `exams`: id, user_id(FK), video_url, audio_url, status(enum: pending/processing/completed/failed), total_score, created_at, updated_at
- `exam_events`: id, exam_id(FK), time_seconds(float), actor(str), event_type(str), event_data(JSON), source(enum: video/audio/sensor/fusion), confidence(float)
- `exam_scores`: id, exam_id(FK), phase(str), rule_code(str), rule_name(str), max_score(float), actual_score(float), deduction_reason(str), evidence(JSON)

### API Routes:
- POST `/api/v1/exam/upload` - Upload video, create exam, queue processing
- GET `/api/v1/exam/{id}/status` - Get processing status
- GET `/api/v1/exam/{id}/result` - Get scoring result
- GET `/api/v1/exam/{id}/timeline` - Get event timeline
- GET `/api/v1/exam/{id}/report` - Get full report (PDF/HTML)
- GET `/api/v1/exams` - List all exams
- POST `/api/v1/auth/register` - User registration
- POST `/api/v1/auth/login` - User login

---

## Task 3: AI Engine - Video Processing Module

**Files:**
- Create: `ai_engine/video/extractor.py` - Frame extraction from video
- Create: `ai_engine/video/detector.py` - YOLOv8 person + equipment detection
- Create: `ai_engine/video/tracker.py` - ByteTrack multi-person tracking
- Create: `ai_engine/video/pose_estimator.py` - MMPose/RTMPose pose estimation
- Create: `ai_engine/video/action_recognizer.py` - Action recognition for CPR actions

### Key Detectable Items:
**Objects**: defibrillator, medicine_box, breathing_bag, ecg_monitor, scoop_stretcher, ecg_paper
**Actions**: running, chest_compression, ventilation, defibrillation, ecg_connection, equipment_placement, stretcher_transfer
**Poses**: compression_pose, ventilation_pose, standing, kneeling

---

## Task 4: AI Engine - Audio Processing Module

**Files:**
- Create: `ai_engine/audio/extractor.py` - Extract audio from video (ffmpeg)
- Create: `ai_engine/audio/vad.py` - Voice Activity Detection
- Create: `ai_engine/audio/asr.py` - Chinese ASR with timestamps (FunASR)
- Create: `ai_engine/audio/diarizer.py` - Speaker diarization
- Create: `ai_engine/audio/keyword_matcher.py` - Medical keyword matching

### Voice Keywords by Phase:
```python
VOICE_RULES = {
    "phase1_safety": {"keywords": ["安全"], "score": 1},
    "phase2_inform": {"keywords": ["停", "救"], "score": 1},
    "phase3_sign_ecg": {"keywords": ["签", "字"], "score": 1},
    "phase4_evaluate": {"keywords": ["离开", "让开"], "score": 2},
    "phase4_iv_access": {"keywords": ["开通", "静脉"], "score": 2},
    "phase4_epinephrine": {"keywords": ["肾上腺素", "推注", "1mg"], "score": 2},
    "phase4_clear_defib": {"keywords": ["离开", "让开"], "score": 2},
    "phase4_sign_consent": {"keywords": ["签", "字"], "score": 1},
    "phase5_evaluate": {"keywords": ["离开", "让开"], "score": 1},
    "phase5_handover": {"keywords": ["替", "换", "按压"], "score": 2},
    "phase6_transfer_consent": {"keywords": ["同意", "签", "字"], "score": 1},
    "phase6_monitoring": {"keywords": ["血压", "氧饱和度", "呼末CO2", "心律", "生命体征"], "score": 1},
    "phase6_care": {"keywords": ["抢救", "尽力"], "score": 1},
}
```

---

## Task 5: AI Engine - Fusion + Scoring

**Files:**
- Create: `ai_engine/fusion/event_merger.py` - Merge video + audio events
- Create: `ai_engine/fusion/timeline.py` - Unified timeline construction
- Create: `ai_engine/scoring/engine.py` - Main scoring engine
- Create: `ai_engine/scoring/rules/base.py` - Base rule class
- Create: `ai_engine/scoring/rules/phase*.py` - Per-phase rules
- Create: `ai_engine/scoring/report_generator.py` - PDF/HTML report

---

## Task 6: AI Engine - Pipeline Orchestrator

**Files:**
- Create: `ai_engine/pipeline.py` - Main pipeline: video -> audio -> fusion -> scoring
- Create: `ai_engine/config.py` - AI engine configuration

---

## Task 7: Frontend Application

**Files:**
- Create: React app with Vite + TypeScript
- Create: 3 main pages (Home, ExamDetail, Report)
- Create: Shared components (VideoPlayer, Timeline, ScoreCard, RadarChart)
- Create: API client layer

---

## Task 8: Docker + Deployment

**Files:**
- Create: `docker-compose.yml` - All services
- Create: `docker-compose.gpu.yml` - GPU override
- Create: `backend/Dockerfile`
- Create: `ai_engine/Dockerfile`
- Create: `frontend/Dockerfile`
- Create: `nginx/nginx.conf`

---

## Task 9: Documentation

**Files:**
- Create: `docs/architecture.md`
- Create: `docs/api.md`
- Create: `docs/deploy.md`
- Create: `docs/scoring_rules.md`
- Create: `docs/development.md`
- Create: `README.md`
