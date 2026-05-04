# 音频处理管线技术文档

## 处理流程

```
视频文件 (.mp4)
    │
    ▼
AudioExtractor (ffmpeg)
    │ 输出: exam_audio.wav (16kHz, mono)
    ▼
Silero-VAD 语音活动检测
    │ 输出: [{start: 0.5, end: 2.3}, {start: 3.1, end: 5.8}, ...]
    │       (118段语音片段)
    ▼
FunASR SenseVoiceSmall 逐段转写
    │ 对每个 VAD 段: 切割音频 → 独立推理 → 带时间戳的文本
    │ 输出: [{start, end, text, confidence}, ...]
    ▼
pyannote.audio 3.1 说话人分离
    │ 全音频 diarization → 按时间重叠分配 speaker ID
    │ 输出: 每段转写标注 speaker (SPEAKER_00/01/02)
    ▼
SpeakerRoleInferrer 角色推断
    │ 按 speaker 分组 → 计算术语密度 → 贪心角色分配
    │ 输出: 每段转写标注 speaker_role (doctor/nurse/driver)
    ▼
TemplateMatcher 话术模板匹配
    │ 15条标准话术模板 × 所有转写段 → 最佳匹配
    │ 输出: [{rule_code, similarity, speaker_role, matched_text}, ...]
    ▼
音频事件列表 + 话术匹配结果
```

## 模块详解

### 1. 语音活动检测 (VAD)

**文件**: `ai_engine/audio/vad.py`
**模型**: Silero-VAD v5
**作用**: 将连续音频切分为有声片段，过滤静音区域

### 2. 语音识别 (ASR)

**文件**: `ai_engine/audio/asr.py`
**模型**: FunASR SenseVoiceSmall (iic/SenseVoiceSmall)

关键修复: `transcribe_segments()` 方法现在逐段切割音频并独立推理，
不再将整个音频作为一个整体处理（之前的 bug 导致 118 段 VAD 只输出 1 段转写）。

```python
# 逐段处理流程:
for vad_seg in vad_segments:
    chunk = audio[start_sample:end_sample]  # 按 VAD 时间戳切割
    result = model.generate(chunk)           # 独立推理 (无内置 VAD)
    segments.append({
        start: vad_start + seg_start,        # 时间戳对齐到原始音频
        end: vad_start + seg_end,
        text: result.text,
    })
```

### 3. 说话人分离 (Diarization)

**文件**: `ai_engine/audio/diarizer.py`
**模型**: pyannote/speaker-diarization-3.1

`assign_speakers()` 通过时间重叠将 diarization 结果映射到 ASR 转写段:
- 每个转写段取 diarization 中重叠时间最长的 speaker
- 支持最多 4 个说话人 (可配置)

### 4. 角色推断 (Role Inference)

**文件**: `ai_engine/audio/role_inferrer.py`

无预训练 voice embedding，纯基于转写内容的角色推断:

| 角色 | 推断依据 |
|------|----------|
| 医生 | 医疗指令词频最高 (肾上腺素/除颤/评估/静脉/通气...) |
| 驾驶员 | 转运词频最高 或 发言段数最少 |
| 护士 | 剩余的说话人 |

算法: 贪心分配，每个角色只分配一次。先分配医生，再分配驾驶员，最后护士。

### 5. 话术模板匹配 (Template Matching)

**文件**: `ai_engine/audio/template_matcher.py`

替代原有 `keyword_matcher.py` 的简单关键词搜索。

**匹配度计算**:
```
similarity = SequenceMatcher(text, template).ratio() × 0.4
           + bigram_coverage(text, template) × 0.6
```

**模板定义示例**:
```python
{
    "templates": ["肾上腺素1毫克静脉推注", "给予肾上腺素1mg"],
    "expected_role": "doctor",       # 期望医生说
    "phase": "phase4_arrival_step3",
    "rule_code": "epinephrine_admin",
    "max_score": 2,
}
```

**匹配流程**:
1. 遍历每条规则的所有模板
2. 对每个转写段计算匹配度
3. 取全局最高匹配度的段作为最终匹配
4. 匹配度 ≥ 35% 才算匹配成功
5. 记录说话人角色是否与期望一致

## 配置项

| 配置 | 默认值 | 说明 |
|------|--------|------|
| `asr_model` | `iic/SenseVoiceSmall` | ASR 模型 |
| `sample_rate` | `16000` | 音频采样率 |
| `max_speakers` | `4` | 最大说话人数 |
| `hf_token` | 环境变量 | HuggingFace token (pyannote) |
| `min_similarity` | `0.35` | 话术模板最低匹配度阈值 |
