# pyright: reportMissingImports=false
"""音频处理总编排 AudioPipeline.

新流程 (2026-05 重构):

    audio_path
        ↓ AudioPreprocessor          16kHz mono + 降噪 + loudnorm
        ↓ VoiceActivityDetector      fsmn-vad → 有效人声片段
        ↓ SpeakerDiarizer            pyannote 3.1 → speaker 标签 (可失败)
        ↓ _build_speech_segments     VAD 片段 + diarization 时间重叠匹配 speaker
        ↓ ParaformerASR              FunASR Paraformer-large 转写 raw_text
        ↓ TextCleaner.clean          去标签 + 规范化
        ↓ DomainCorrector.correct    领域同音替换
        ↓ classify_segment_type      counting/medical_command/...
        ↓ SpeakerRoleBinder.bind     speaker → doctor/nurse/driver
        ↓ TemplateMatcher.match      话术规则命中
        → 返回 segments + events + speaker_role_map + hotwords

关键设计:
    - ASR 分段来自 VAD，不来自 diarization
    - diarization 失败不影响 ASR，只会导致 speaker=UNKNOWN_SPEAKER
    - 禁止整段音频进 ASR（杜绝 472s 整段幻听）
"""

from __future__ import annotations

import os
from typing import Any, Optional

from loguru import logger

from ai_engine.audio.diarizer import SpeakerDiarizer, UNKNOWN_SPEAKER
from ai_engine.audio.domain_corrector import (
    classify_segment_type,
    correct,
    get_hotword_prompt,
    get_hotwords,
)
from ai_engine.audio.paraformer_asr import ParaformerASR
from ai_engine.audio.preprocessor import AudioPreprocessor
from ai_engine.audio.role_binder import SpeakerRoleBinder
from ai_engine.audio.template_matcher import TemplateMatcher
from ai_engine.audio.text_cleaner import clean_asr_text, is_valid_text
from ai_engine.audio.types import DiarizationSegment, SpeechSegment
from ai_engine.audio.vad import VoiceActivityDetector, VadSegment

MAX_ASR_SEGMENT_DURATION = 20.0
MIN_ASR_SEGMENT_DURATION = 0.5


class AudioPipeline:
    """音频处理总编排. 模型只在第一次实例化时加载, 多次调用 process() 复用."""

    def __init__(
        self,
        hf_token: Optional[str] = None,
        device: str = "cuda:0",
        num_speakers: int = 3,
        sample_rate: int = 16000,
        min_template_similarity: float = 0.35,
        manual_speaker_role_map: Optional[dict[str, str]] = None,
        vad_model: str = "fsmn-vad",
    ) -> None:
        self.sample_rate = sample_rate
        self.manual_speaker_role_map = manual_speaker_role_map

        self.preprocessor = AudioPreprocessor(sample_rate=sample_rate)

        self.vad = VoiceActivityDetector(model_name=vad_model)

        self.diarizer = SpeakerDiarizer(
            hf_token=hf_token,
            device=device,
            num_speakers=num_speakers,
        )

        self.asr = ParaformerASR(device=device)

        self.role_binder = SpeakerRoleBinder()
        self.template_matcher = TemplateMatcher(
            min_similarity=min_template_similarity
        )

        self._log_diagnostics()

    def _log_diagnostics(self) -> None:
        try:
            import torch
            torch_ver = torch.__version__
            cuda_ver = getattr(torch.version, "cuda", "N/A")
            cuda_ok = torch.cuda.is_available()
            cuda_cnt = torch.cuda.device_count() if cuda_ok else 0
        except ImportError:
            torch_ver, cuda_ver, cuda_ok, cuda_cnt = "N/A", "N/A", False, 0

        logger.info(
            "[AudioPipeline] 环境自检:\n"
            f"  torch={torch_ver}, cuda={cuda_ver}\n"
            f"  cuda_available={cuda_ok}, cuda_devices={cuda_cnt}\n"
            f"  ASR model={self.asr.model_name}, device={self.asr.device}\n"
            f"  VAD enabled={self.vad.enabled}\n"
            f"  Diarizer model={self.diarizer.model_name}, "
            f"enabled={self.diarizer.pipeline is not None}\n"
            f"  HF_TOKEN={bool(os.environ.get('HF_TOKEN'))}, "
            f"HUGGINGFACE_HUB_TOKEN="
            f"{bool(os.environ.get('HUGGINGFACE_HUB_TOKEN'))}, "
            f"AI_HF_TOKEN={bool(os.environ.get('AI_HF_TOKEN'))}"
        )

    # ------------------------------------------------------------------ #
    def process(
        self,
        audio_path: str,
        exam_id: Optional[int] = None,
        manual_speaker_role_map: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        logger.info(f"[AudioPipeline] 开始: audio={audio_path}, exam_id={exam_id}")

        # ------ 阶段 1: 预处理 ------
        try:
            preprocessed = self.preprocessor.process(audio_path)
        except Exception as exc:
            logger.exception(f"[AudioPipeline] 预处理失败: {exc}")
            preprocessed = audio_path

        duration = self._probe_duration(preprocessed)
        logger.info(f"[AudioPipeline] audio duration={duration:.1f}s")

        # ------ 阶段 2: VAD (主分段来源) ------
        vad_segments = self.vad.detect(preprocessed)
        vad_speech_dur = sum(s.end - s.start for s in vad_segments)
        logger.info(
            f"[AudioPipeline] VAD: {len(vad_segments)}段, "
            f"speech_duration={vad_speech_dur:.1f}s"
        )

        if not vad_segments:
            logger.warning(
                "[AudioPipeline] VAD 未检测到有效人声, 跳过 ASR"
            )
            return self._empty_result(preprocessed)

        # ------ 阶段 3: 说话人分离 (可失败) ------
        diar_segments = self.diarizer.diarize(preprocessed)
        diar_ok = len(diar_segments) > 0
        logger.info(
            f"[AudioPipeline] diarization: {len(diar_segments)}段, "
            f"speakers={sorted({s.speaker for s in diar_segments}) if diar_ok else '[]'}, "
            f"fallback_speaker={'no' if diar_ok else 'yes'}"
        )

        # ------ 阶段 4: VAD → SpeechSegment + speaker 匹配 ------
        speech_segments = self._build_speech_segments(vad_segments, diar_segments)
        logger.info(
            f"[AudioPipeline] speech_segments: {len(speech_segments)}段 "
            f"(来自 {len(vad_segments)} VAD segments)"
        )

        # ------ 阶段 5: ASR ------
        speech_segments = self.asr.transcribe_segments(
            audio_path=preprocessed,
            segments=speech_segments,
            hotword=get_hotword_prompt(),
            sample_rate=self.sample_rate,
        )

        # ------ 阶段 6: 文本清洗 + 纠错 + 分类 ------
        asr_success = 0
        asr_failed = 0
        cleaned_segments: list[SpeechSegment] = []
        for seg in speech_segments:
            cleaned = clean_asr_text(seg.raw_text)
            corrected = correct(cleaned)
            if is_valid_text(corrected):
                seg.text = corrected
                seg.segment_type = classify_segment_type(corrected)
                asr_success += 1
            else:
                seg.text = corrected or None
                seg.segment_type = "unknown"
                asr_failed += 1
            cleaned_segments.append(seg)

        logger.info(
            f"[AudioPipeline] ASR segments: {len(cleaned_segments)}, "
            f"有效={asr_success}, 无效={asr_failed}"
        )

        # ------ 阶段 7: 角色绑定 ------
        manual_map = manual_speaker_role_map or self.manual_speaker_role_map
        speaker_role_map = self.role_binder.bind(
            cleaned_segments, manual_map=manual_map
        )
        cleaned_segments = self.role_binder.apply_roles(
            cleaned_segments, speaker_role_map
        )

        # ------ 阶段 8: 模板匹配 ------
        events = self.template_matcher.match(cleaned_segments)

        result = {
            "audio_path": preprocessed,
            "segments": [s.to_dict() for s in cleaned_segments],
            "events": [e.to_dict() for e in events],
            "speaker_role_map": speaker_role_map,
            "hotwords": get_hotwords(),
            "stats": {
                "audio_duration": round(duration, 1),
                "vad_segments": len(vad_segments),
                "vad_speech_duration": round(vad_speech_dur, 1),
                "diarization_segments": len(diar_segments),
                "asr_segments": len(speech_segments),
                "asr_success": asr_success,
                "asr_failed": asr_failed,
                "matched_rules": len(events),
                "fallback_speaker": not diar_ok,
            },
        }
        logger.info(
            f"[AudioPipeline] 完成: exam_id={exam_id}, "
            f"segments={len(cleaned_segments)}, events={len(events)}, "
            f"speakers={list(speaker_role_map.keys())}"
        )
        return result

    # ------------------------------------------------------------------ #
    @staticmethod
    def _build_speech_segments(
        vad_segments: list[VadSegment],
        diar_segments: list[DiarizationSegment],
    ) -> list[SpeechSegment]:
        """从 VAD 片段构建 SpeechSegment，用 diarization 时间重叠匹配 speaker。

        长片段按 MAX_ASR_SEGMENT_DURATION 切分，短片段丢弃。
        """
        result: list[SpeechSegment] = []
        for vad in vad_segments:
            speaker = _match_speaker_by_overlap(vad, diar_segments)
            seg_dur = vad.end - vad.start

            if seg_dur > MAX_ASR_SEGMENT_DURATION:
                cur = vad.start
                while cur < vad.end:
                    end = min(cur + MAX_ASR_SEGMENT_DURATION, vad.end)
                    if (end - cur) >= MIN_ASR_SEGMENT_DURATION:
                        result.append(SpeechSegment(
                            start=round(cur, 3),
                            end=round(end, 3),
                            speaker=speaker,
                        ))
                    cur = end
            else:
                result.append(SpeechSegment(
                    start=round(vad.start, 3),
                    end=round(vad.end, 3),
                    speaker=speaker,
                ))

        result.sort(key=lambda s: s.start)
        return result

    @staticmethod
    def _probe_duration(audio_path: str) -> float:
        try:
            import soundfile as _sf
            with _sf.SoundFile(audio_path) as f:
                return f.frames / float(f.samplerate)
        except Exception as exc:
            logger.warning(f"[AudioPipeline] 读取音频时长失败: {exc}")
            return 0.0

    @staticmethod
    def _empty_result(audio_path: str) -> dict[str, Any]:
        return {
            "audio_path": audio_path,
            "segments": [],
            "events": [],
            "speaker_role_map": {},
            "hotwords": get_hotwords(),
            "stats": {
                "audio_duration": 0.0,
                "vad_segments": 0,
                "vad_speech_duration": 0.0,
                "diarization_segments": 0,
                "asr_segments": 0,
                "asr_success": 0,
                "asr_failed": 0,
                "matched_rules": 0,
                "fallback_speaker": True,
            },
        }


def _match_speaker_by_overlap(
    vad: VadSegment,
    diar_segments: list[DiarizationSegment],
) -> str:
    """在 diarization 结果中找与 vad 时间重叠最大的 speaker。"""
    if not diar_segments:
        return UNKNOWN_SPEAKER

    best_speaker = UNKNOWN_SPEAKER
    best_overlap = 0.0

    for diar in diar_segments:
        overlap = max(0.0, min(vad.end, diar.end) - max(vad.start, diar.start))
        if overlap > best_overlap:
            best_overlap = overlap
            best_speaker = diar.speaker

    return best_speaker


__all__ = ["AudioPipeline"]
