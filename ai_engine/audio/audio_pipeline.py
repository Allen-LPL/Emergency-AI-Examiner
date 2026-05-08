# pyright: reportMissingImports=false
"""音频处理总编排 AudioPipeline.

把 ai_engine/audio/* 各模块串联起来:

    audio_path
        ↓ AudioPreprocessor          16kHz mono + 降噪 + loudnorm
        ↓ SpeakerDiarizer            pyannote 3.1 → DiarizationSegment
        ↓ SpeakerSegmentMerger       合并/切分 → SpeechSegment
        ↓ ParaformerASR              FunASR Paraformer-large 转写 raw_text
        ↓ TextCleaner.clean          去标签 + 规范化
        ↓ DomainCorrector.correct    领域同音替换
        ↓ classify_segment_type      counting/medical_command/...
        ↓ SpeakerRoleBinder.bind     speaker → doctor/nurse/driver
        ↓ TemplateMatcher.match      话术规则命中
        → 返回 segments + events + speaker_role_map + hotwords

每一步都有详细中文日志, 单一阶段失败不影响后续阶段。

返回结构 (用于 ai_engine.pipeline 与 transcript 持久化):

{
    "audio_path": str,                # 预处理后的音频路径
    "segments": [SpeechSegment.to_dict()],
    "events":   [AudioEvent.to_dict()],
    "speaker_role_map": {speaker: role},
    "hotwords": [str],
    "stats": {
        "diarization_segments": int,
        "merged_segments": int,
        "asr_success": int,
        "asr_failed": int,
        "matched_rules": int,
    },
}
"""

from __future__ import annotations

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
from ai_engine.audio.speaker_segment import SpeakerSegmentMerger
from ai_engine.audio.template_matcher import TemplateMatcher
from ai_engine.audio.text_cleaner import clean_asr_text, is_valid_text
from ai_engine.audio.types import SpeechSegment


class AudioPipeline:
    """音频处理总编排.

    模型只在第一次实例化时加载, 多次调用 process() 复用.
    """

    def __init__(
        self,
        hf_token: Optional[str] = None,
        device: str = "cuda:0",
        num_speakers: int = 3,
        sample_rate: int = 16000,
        min_template_similarity: float = 0.35,
        manual_speaker_role_map: Optional[dict[str, str]] = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.manual_speaker_role_map = manual_speaker_role_map

        # 1) 预处理: 不依赖模型, 轻量
        self.preprocessor = AudioPreprocessor(sample_rate=sample_rate)

        # 2) 说话人分离 (pyannote 3.1)
        self.diarizer = SpeakerDiarizer(
            hf_token=hf_token,
            device=device,
            num_speakers=num_speakers,
        )

        # 3) 段合并器 (无模型)
        self.segment_merger = SpeakerSegmentMerger()

        # 4) ASR (Paraformer-large via ModelScope)
        self.asr = ParaformerASR(device=device)

        # 5) 角色绑定器 + 模板匹配 (无模型)
        self.role_binder = SpeakerRoleBinder()
        self.template_matcher = TemplateMatcher(
            min_similarity=min_template_similarity
        )

    # ------------------------------------------------------------------ #
    def process(
        self,
        audio_path: str,
        exam_id: Optional[int] = None,
        manual_speaker_role_map: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        """执行完整音频管线."""
        logger.info(f"[AudioPipeline] 开始: audio={audio_path}, exam_id={exam_id}")

        # ------ 阶段 1: 预处理 ------
        try:
            preprocessed = self.preprocessor.process(audio_path)
        except Exception as exc:
            logger.exception(f"[AudioPipeline] 预处理失败: {exc}")
            preprocessed = audio_path  # 兜底: 用原始音频继续

        # ------ 阶段 2: 说话人分离 ------
        diar_segments = self.diarizer.diarize(preprocessed)
        logger.info(
            f"[AudioPipeline] diarization: {len(diar_segments)}段, "
            f"speakers={sorted({s.speaker for s in diar_segments})}"
        )

        # ------ 阶段 3: 段合并 ------
        if not diar_segments:
            # pyannote 不可用时, 走单 speaker 兜底:
            # 把整个音频当作一个 SPEAKER_DEFAULT 段, 给 ASR 全文转写
            duration = self._probe_duration(preprocessed)
            speech_segments = [
                SpeechSegment(
                    start=0.0,
                    end=duration,
                    speaker=UNKNOWN_SPEAKER,
                )
            ] if duration > 0 else []
            logger.warning(
                f"[AudioPipeline] diarization 空, 退化为单 speaker 模式 "
                f"({UNKNOWN_SPEAKER}, duration={duration:.1f}s)"
            )
        else:
            speech_segments = self.segment_merger.merge(diar_segments)

        # ------ 阶段 4: ASR ------
        speech_segments = self.asr.transcribe_segments(
            audio_path=preprocessed,
            segments=speech_segments,
            hotword=get_hotword_prompt(),
            sample_rate=self.sample_rate,
        )

        # ------ 阶段 5: 文本清洗 + 纠错 + 分类 ------
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
                cleaned_segments.append(seg)
            else:
                # 文本无效但段本身保留 (供前端时间轴展示), 标记 unknown
                seg.text = corrected or None
                seg.segment_type = "unknown"
                asr_failed += 1
                cleaned_segments.append(seg)

        logger.info(
            f"[AudioPipeline] 文本清洗完成: 有效={asr_success}, 无效={asr_failed}"
        )

        # ------ 阶段 6: 角色绑定 ------
        manual_map = manual_speaker_role_map or self.manual_speaker_role_map
        speaker_role_map = self.role_binder.bind(
            cleaned_segments, manual_map=manual_map
        )
        cleaned_segments = self.role_binder.apply_roles(
            cleaned_segments, speaker_role_map
        )

        # ------ 阶段 7: 模板匹配 ------
        events = self.template_matcher.match(cleaned_segments)

        # ------ 输出 ------
        result = {
            "audio_path": preprocessed,
            "segments": [s.to_dict() for s in cleaned_segments],
            "events": [e.to_dict() for e in events],
            "speaker_role_map": speaker_role_map,
            "hotwords": get_hotwords(),
            "stats": {
                "diarization_segments": len(diar_segments),
                "merged_segments": len(speech_segments),
                "asr_success": asr_success,
                "asr_failed": asr_failed,
                "matched_rules": len(events),
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
    def _probe_duration(audio_path: str) -> float:
        """读取音频时长 (秒). 失败返回 0."""
        try:
            import soundfile as sf

            with sf.SoundFile(audio_path) as f:
                return f.frames / float(f.samplerate)
        except Exception as exc:
            logger.warning(f"[AudioPipeline] 读取音频时长失败: {exc}")
            return 0.0


__all__ = ["AudioPipeline"]
