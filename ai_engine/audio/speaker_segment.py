# pyright: reportMissingImports=false
"""把 pyannote 输出的细碎 diarization 合并成适合 ASR 的 SpeechSegment.

合并规则:
    1. 同一 speaker 相邻段间隔 ≤ MERGE_GAP (默认 0.8s) 可合并
    2. 单段最长 MAX_DURATION (默认 20s), 超过会切分
    3. 单段最短 MIN_DURATION (默认 0.8s), 过短直接丢弃
       (太短的段 ASR 效果差且容易把咳嗽/笑声误判为语音)
    4. 多 speaker 重叠时, 按 speaker 归属分别保留, 不混合 (避免 ASR 串音)
    5. 输出按 start 排序

为什么要做这一步:
    pyannote 输出常见 0.2~0.5s 碎片, 直接交给 Paraformer 会:
      - 字符上下文不足导致 ASR 准确率骤降
      - 反复进出模型造成显著的吞吐损失
"""

from __future__ import annotations

from dataclasses import replace

from loguru import logger

from ai_engine.audio.types import DiarizationSegment, SpeechSegment


MERGE_GAP = 0.8
MAX_DURATION = 20.0
MIN_DURATION = 0.8


class SpeakerSegmentMerger:
    """把短 diarization 合并/切分为 SpeechSegment 列表.

    Args:
        merge_gap: 相邻同 speaker 段允许合并的最大间隔 (秒)
        max_duration: 单段最长长度 (秒), 超过会切分
        min_duration: 单段最短长度 (秒), 不足直接丢弃
    """

    def __init__(
        self,
        merge_gap: float = MERGE_GAP,
        max_duration: float = MAX_DURATION,
        min_duration: float = MIN_DURATION,
    ) -> None:
        self.merge_gap = merge_gap
        self.max_duration = max_duration
        self.min_duration = min_duration

    def merge(
        self, diarization: list[DiarizationSegment]
    ) -> list[SpeechSegment]:
        if not diarization:
            return []

        # 步骤 1: 按 speaker 分组, 同 speaker 内按 start 合并相邻段
        sorted_segs = sorted(diarization, key=lambda s: (s.speaker, s.start))
        merged_per_speaker: dict[str, list[DiarizationSegment]] = {}

        for seg in sorted_segs:
            bucket = merged_per_speaker.setdefault(seg.speaker, [])
            if bucket and (seg.start - bucket[-1].end) <= self.merge_gap:
                # 合并到上一个段, 取并集
                last = bucket[-1]
                bucket[-1] = replace(
                    last,
                    end=max(last.end, seg.end),
                )
            else:
                bucket.append(seg)

        # 步骤 2: 把所有 speaker 的合并结果汇总, 按 start 排序
        all_merged: list[DiarizationSegment] = []
        for bucket in merged_per_speaker.values():
            all_merged.extend(bucket)
        all_merged.sort(key=lambda s: s.start)

        # 步骤 3: 长段切分 + 短段丢弃 + 转 SpeechSegment
        result: list[SpeechSegment] = []
        for seg in all_merged:
            chunks = self._split_long(seg)
            for c in chunks:
                if (c.end - c.start) < self.min_duration:
                    # 过短的段会被 ASR 当作噪音, 直接丢
                    continue
                result.append(
                    SpeechSegment(
                        start=round(c.start, 3),
                        end=round(c.end, 3),
                        speaker=c.speaker,
                    )
                )

        result.sort(key=lambda s: s.start)
        logger.info(
            f"[SegmentMerger] {len(diarization)}段 → 合并为 {len(result)}段 "
            f"(merge_gap={self.merge_gap}s, "
            f"max={self.max_duration}s, min={self.min_duration}s)"
        )
        return result

    def _split_long(
        self, seg: DiarizationSegment
    ) -> list[DiarizationSegment]:
        """把超过 max_duration 的段切成不超过 max_duration 的小块."""
        duration = seg.end - seg.start
        if duration <= self.max_duration:
            return [seg]

        chunks: list[DiarizationSegment] = []
        cur = seg.start
        while cur < seg.end:
            nxt = min(cur + self.max_duration, seg.end)
            chunks.append(
                DiarizationSegment(start=cur, end=nxt, speaker=seg.speaker)
            )
            cur = nxt
        return chunks


__all__ = [
    "SpeakerSegmentMerger",
    "MERGE_GAP",
    "MAX_DURATION",
    "MIN_DURATION",
]
