# 音频主轴跨模态评分系统 实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将评分系统从单模态孤岛升级为"音频主轴(说话人+话术模板) → 视频辅证 → 传感器验证"的跨模态对齐评分架构

**Architecture:** 音频管线输出带角色标注(医生/驾驶员/护士)的逐段转写 → 话术模板匹配引擎计算匹配度分数 → 评分规则在时间窗口内交叉验证三路数据源 → 设备检测类规则默认满分

**Tech Stack:** pyannote.audio 3.1 (diarization) + FunASR SenseVoiceSmall (ASR) + difflib/sklearn (模板匹配) + React/Ant Design (前端)

---

## Stream A: AI Engine 音频管线升级

### Task A1: 说话人角色推断器

**Files:**
- Create: `ai_engine/audio/role_inferrer.py`
- Modify: `ai_engine/audio/diarizer.py`

**核心逻辑:**
1. pyannote diarization 输出 speaker segments (SPEAKER_00/01/02)
2. 将每个 speaker 的所有转写文本合并
3. 用医疗术语密度判断角色:
   - 医生: 包含最多医疗指令词 (肾上腺素/除颤/静脉/评估/通气)
   - 护士: 包含辅助执行词 (准备好/已完成/记录/签字)
   - 驾驶员: 剩余的 speaker (最少发言或包含转运相关词)
4. 将角色标注写入 transcription 段

### Task A2: 话术模板匹配引擎

**Files:**
- Create: `ai_engine/audio/template_matcher.py`
- Remove logic from: `ai_engine/audio/keyword_matcher.py` (保留文件但标记废弃)

**核心逻辑:**
1. 每条规则定义完整话术模板 + 期望角色
2. 使用 difflib.SequenceMatcher 计算模板匹配度 (0-100%)
3. 匹配度 >= 60% 视为匹配成功,分数按匹配度线性计算
4. 按 speaker_role 分组匹配 (只有对应角色说了才算分)
5. 输出: 匹配时间点 + 匹配度 + 匹配文本 + 说话人角色

### Task A3: Pipeline 音频流程重组

**Files:**
- Modify: `ai_engine/pipeline.py`

**核心逻辑:**
1. VAD → ASR(逐段) → Diarization → Speaker Assignment → Role Inference → Template Matching
2. 将 role_inferrer 结果写入 context
3. 将 template_matcher 替代 keyword_matcher

---

## Stream B: 评分引擎跨模态升级

### Task B1: Timeline 增加时间窗口查询

**Files:**
- Modify: `ai_engine/fusion/timeline.py`

**新增方法:** `find_event_near(event_type, center_time, window)` — 在 center_time ± window 内搜索指定类型事件

### Task B2: 评分规则全面改造

**Files:**
- Modify: `ai_engine/scoring/rules/base.py` (新增 cross-modal helper)
- Modify: `ai_engine/scoring/rules/phase1_before_arrival.py` (设备规则默认满分)
- Modify: All phase rule files (跨模态验证)
- Modify: `ai_engine/scoring/rules/__init__.py`

**核心改动:**
1. 设备检测类5条规则 → 默认满分
2. 音频类规则 → 检查 template_matches (含匹配度)
3. 有 video_confirm 的规则 → 在音频时间点 ±5s 内查视频事件
4. 评分公式: 基础分(音频) × 匹配度 × 视频确认系数 × 传感器系数

### Task B3: 视频事件扩展 (~10种)

**Files:**
- Modify: `ai_engine/video/action_recognizer.py`
- Modify: `ai_engine/video/pose_estimator.py`

**新增事件:** ventilation_pose, equipment_handling, person_swap, ecg_connection_pose, standing_nearby

---

## Stream C: 前端企业级 UI 重建

### Task C1: 前端页面重构

**Files:**
- Rewrite: `frontend/src/pages/ExamDetail.tsx`
- Rewrite: `frontend/src/pages/Report.tsx`
- Create: `frontend/src/components/ScoringPhaseCard.tsx`
- Create: `frontend/src/components/SpeakerTimeline.tsx`
- Create: `frontend/src/components/TemplateMatchView.tsx`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/index.ts`

**UI 布局:** 简约大气企业级设计
- 顶部: 总分卡片 + 雷达图
- 中间: 6阶段评分卡片 (每个阶段展开显示规则+证据)
- 下方: 说话人时间轴 (颜色区分医生/护士/驾驶员)
- 底部: 话术模板匹配明细 + 视频确认状态

---

## Stream D: 文档

### Task D1: 代码逻辑文档

**Files:**
- Create: `docs/architecture.md` (整体架构说明)
- Create: `docs/scoring-rules.md` (评分规则逻辑文档)
- Create: `docs/audio-pipeline.md` (音频管线说明)
