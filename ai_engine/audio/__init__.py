# pyright: reportMissingImports=false
"""ai_engine.audio 包入口.

新音频管线 (2026-05 重构, 替代旧 asr.py / vad.py / role_inferrer.py / keyword_matcher.py):

    AudioPipeline (audio_pipeline.py)
        ├─ AudioPreprocessor (preprocessor.py)
        ├─ SpeakerDiarizer    (diarizer.py)              pyannote.audio 3.1
        ├─ SpeakerSegmentMerger (speaker_segment.py)
        ├─ ParaformerASR      (paraformer_asr.py)        FunASR Paraformer-large
        ├─ TextCleaner        (text_cleaner.py)
        ├─ DomainCorrector    (domain_corrector.py)      急救热词与同音替换
        ├─ SpeakerRoleBinder  (role_binder.py)           speaker → doctor/nurse/driver
        └─ TemplateMatcher    (template_matcher.py)      话术模板匹配

外部仍保留 AudioExtractor (extractor.py) 用于从 mp4 提取原始 wav.
"""

from ai_engine.audio.audio_pipeline import AudioPipeline
from ai_engine.audio.diarizer import SpeakerDiarizer, UNKNOWN_SPEAKER
from ai_engine.audio.domain_corrector import (
    classify_segment_type,
    correct,
    get_hotword_prompt,
    get_hotwords,
)
from ai_engine.audio.extractor import AudioExtractor
from ai_engine.audio.paraformer_asr import ParaformerASR
from ai_engine.audio.preprocessor import AudioPreprocessor
from ai_engine.audio.role_binder import (
    ROLE_DOCTOR,
    ROLE_DRIVER,
    ROLE_NURSE,
    ROLE_UNKNOWN,
    SpeakerRoleBinder,
)
from ai_engine.audio.speaker_segment import SpeakerSegmentMerger
from ai_engine.audio.template_matcher import TemplateMatcher, VOICE_TEMPLATES
from ai_engine.audio.text_cleaner import clean_asr_text, is_valid_text
from ai_engine.audio.types import (
    AudioEvent,
    DiarizationSegment,
    SpeechSegment,
)

__all__ = [
    # 数据结构
    "AudioEvent",
    "DiarizationSegment",
    "SpeechSegment",
    # 编排器
    "AudioPipeline",
    # 子模块
    "AudioPreprocessor",
    "SpeakerDiarizer",
    "SpeakerSegmentMerger",
    "ParaformerASR",
    "SpeakerRoleBinder",
    "TemplateMatcher",
    # 外部工具
    "AudioExtractor",
    # 文本处理
    "clean_asr_text",
    "is_valid_text",
    "correct",
    "classify_segment_type",
    "get_hotwords",
    "get_hotword_prompt",
    # 常量
    "UNKNOWN_SPEAKER",
    "ROLE_DOCTOR",
    "ROLE_NURSE",
    "ROLE_DRIVER",
    "ROLE_UNKNOWN",
    "VOICE_TEMPLATES",
]
