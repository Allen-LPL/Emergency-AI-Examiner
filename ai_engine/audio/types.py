# pyright: reportMissingImports=false
"""音频管线统一数据结构。

所有音频子模块 (Diarizer / Merger / ASR / Cleaner / Binder / Matcher)
都基于这里定义的 dataclass 进行交互, 保证字段一致、可序列化。

设计原则:
    1. 顶层接口返回 dict (便于 JSON 序列化与跨进程传递),
       内部模块内部可使用 dataclass 的 to_dict() 转换。
    2. 时间字段统一用 float 秒, 保留 3 位小数。
    3. 所有可选字段都有合理默认值, 避免 Pydantic 空值陷阱。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


# 音频段类型枚举 (字符串, 便于 JSON 序列化与跨语言对接)
SEGMENT_TYPE_COUNTING = "counting"  # 计数类: 主要为数字
SEGMENT_TYPE_MEDICAL_COMMAND = "medical_command"  # 医疗口令: 医生下达
SEGMENT_TYPE_ASSISTANT_RESPONSE = "assistant_response"  # 护士应答
SEGMENT_TYPE_FAMILY_INQUIRY = "family_inquiry"  # 家属沟通/病史询问
SEGMENT_TYPE_NOISE = "noise"  # 噪音, 无效内容
SEGMENT_TYPE_UNKNOWN = "unknown"  # 兜底


SEGMENT_TYPES = {
    SEGMENT_TYPE_COUNTING,
    SEGMENT_TYPE_MEDICAL_COMMAND,
    SEGMENT_TYPE_ASSISTANT_RESPONSE,
    SEGMENT_TYPE_FAMILY_INQUIRY,
    SEGMENT_TYPE_NOISE,
    SEGMENT_TYPE_UNKNOWN,
}


@dataclass
class DiarizationSegment:
    """pyannote 输出的原始 speaker 分段 (未做 ASR)."""

    start: float
    end: float
    speaker: str
    confidence: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SpeechSegment:
    """完整音频段: 包含 speaker、role、文本、分类。

    生命周期:
        Diarizer 产出 → SegmentMerger 合并 → ParaformerASR 填 text →
        TextCleaner/DomainCorrector 清洗 → classify_segment_type 分类 →
        RoleBinder 填 role → TemplateMatcher 用作输入。
    """

    start: float
    end: float
    speaker: str
    role: Optional[str] = None
    text: Optional[str] = None
    raw_text: Optional[str] = None  # ASR 原始输出 (未清洗)
    confidence: Optional[float] = None
    segment_type: Optional[str] = None

    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "speaker": self.speaker,
            "role": self.role,
            "text": self.text,
            "raw_text": self.raw_text,
            "confidence": self.confidence,
            "segment_type": self.segment_type,
        }


@dataclass
class AudioEvent:
    """话术模板匹配命中的事件, 直接喂给 scoring 引擎。"""

    start: float
    end: float
    speaker: str
    role: Optional[str]
    event_type: str  # 同 rule_code, 便于 EventMerger 兼容
    text: str
    rule_code: Optional[str] = None
    rule_name: Optional[str] = None
    phase: Optional[str] = None
    similarity: Optional[float] = None
    matched_template: Optional[str] = None
    role_correct: bool = True
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "speaker": self.speaker,
            "role": self.role,
            "event_type": self.event_type,
            "text": self.text,
            "rule_code": self.rule_code,
            "rule_name": self.rule_name,
            "phase": self.phase,
            "similarity": self.similarity,
            "matched_template": self.matched_template,
            "role_correct": self.role_correct,
            "extras": self.extras,
        }


__all__ = [
    "DiarizationSegment",
    "SpeechSegment",
    "AudioEvent",
    "SEGMENT_TYPE_COUNTING",
    "SEGMENT_TYPE_MEDICAL_COMMAND",
    "SEGMENT_TYPE_ASSISTANT_RESPONSE",
    "SEGMENT_TYPE_FAMILY_INQUIRY",
    "SEGMENT_TYPE_NOISE",
    "SEGMENT_TYPE_UNKNOWN",
    "SEGMENT_TYPES",
]
