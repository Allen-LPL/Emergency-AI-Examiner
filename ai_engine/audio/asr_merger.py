# pyright: reportMissingImports=false
"""三路 ASR 结果合并: Paraformer (主) + FunASR WS + Whisper HTTP.

合并策略:
    1. 以本地 Paraformer 分段转写为主轴 (段级时间戳、speaker、role 均来自 Paraformer)
    2. FunASR WS 和 Whisper HTTP 对整段音频做全文转写, 用于逐段校验与纠错
    3. 过滤 ASR 幻觉: 连续重复字符 (如 "取取取取取"), 单字段高频重复
    4. 多路一致性校验: 若主路文本在辅路中也出现, 置信度提升; 若仅主路有, 降低置信度
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from loguru import logger

from ai_engine.audio.hotwords import get_hotword_set


_REPEAT_CHAR_RE = re.compile(r"(.)\1{2,}")
_REPEAT_WORD_RE = re.compile(r"([\u4e00-\u9fff]{1,2}?)\1{2,}")

_MIN_SEGMENT_TEXT_LEN = 2
_HALLUCINATION_RATIO_THRESHOLD = 0.5


class ASRMerger:
    def __init__(self, hotword_set: frozenset[str] | None = None):
        self.hotword_set = hotword_set or get_hotword_set()

    def merge(
        self,
        paraformer_segments: list[dict[str, Any]],
        funasr_result: dict[str, Any],
        whisper_result: dict[str, Any],
        tencent_result: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        funasr_text = funasr_result.get("text", "") or ""
        funasr_segments = funasr_result.get("segments", []) or []
        whisper_text = whisper_result.get("text", "") or ""
        tencent_text = (tencent_result or {}).get("text", "") or ""
        tencent_segments = (tencent_result or {}).get("segments", []) or []

        funasr_text_clean = self._clean_hallucinations(funasr_text)
        whisper_text_clean = self._clean_hallucinations(whisper_text)
        tencent_text_clean = self._clean_hallucinations(tencent_text)

        logger.info(
            f"[ASRMerger] 输入: paraformer={len(paraformer_segments)}段, "
            f"funasr={len(funasr_text)}字, whisper={len(whisper_text)}字, "
            f"tencent={len(tencent_text)}字"
        )

        merged: list[dict[str, Any]] = []
        corrections = 0

        for seg in paraformer_segments:
            raw = seg.get("raw_text") or seg.get("text") or ""
            cleaned = self._clean_hallucinations(raw)

            if not cleaned or len(cleaned) < _MIN_SEGMENT_TEXT_LEN:
                seg["text"] = cleaned
                seg["asr_source"] = "paraformer"
                seg["asr_confidence_boost"] = 0.0
                merged.append(seg)
                continue

            funasr_match = self._find_best_match_in_fulltext(
                cleaned, funasr_text_clean
            )
            whisper_match = self._find_best_match_in_fulltext(
                cleaned, whisper_text_clean
            )
            tencent_match = self._find_best_match_in_fulltext(
                cleaned, tencent_text_clean
            ) if tencent_text_clean else 0.0

            # 优先看 FunASR 的时间对齐分段, 没有再退回 Tencent 的时间对齐分段
            funasr_seg_match = self._find_time_aligned_segment(
                seg.get("start", 0), seg.get("end", 0), funasr_segments
            )
            if not funasr_seg_match and tencent_segments:
                funasr_seg_match = self._find_time_aligned_segment(
                    seg.get("start", 0), seg.get("end", 0), tencent_segments
                )

            best_text = cleaned
            source = "paraformer"
            boost = 0.0

            # 三路投票: 命中数 >= 2 高置信; 命中 1 路低置信; 全 miss 走纠错
            high_hits = sum(
                1 for m in (funasr_match, whisper_match, tencent_match) if m > 0.8
            )
            mid_hits = sum(
                1 for m in (funasr_match, whisper_match, tencent_match) if m > 0.6
            )
            all_miss = (
                funasr_match < 0.3 and whisper_match < 0.3 and tencent_match < 0.3
            )

            if high_hits >= 2:
                boost = 0.3
            elif mid_hits >= 1:
                boost = 0.1
            elif all_miss and len(cleaned) > 4:
                candidate = self._pick_best_alternative(
                    cleaned, funasr_seg_match, whisper_text_clean,
                    seg.get("start", 0), seg.get("end", 0),
                )
                if candidate and candidate != cleaned:
                    best_text = candidate
                    source = "corrected"
                    corrections += 1
                    boost = -0.1

            seg["text"] = best_text
            seg["asr_source"] = source
            seg["asr_confidence_boost"] = boost
            merged.append(seg)

        logger.info(
            f"[ASRMerger] 合并完成: {len(merged)}段, 纠正={corrections}段"
        )
        return merged

    def _clean_hallucinations(self, text: str) -> str:
        if not text:
            return ""
        result = _REPEAT_WORD_RE.sub(r"\1", text)
        result = _REPEAT_CHAR_RE.sub(r"\1", result)
        result = self._remove_noise_chars(result)
        return result.strip()

    def _remove_noise_chars(self, text: str) -> str:
        if not text or len(text) < 3:
            return text

        char_counts: dict[str, int] = {}
        total = 0
        for ch in text:
            if "\u4e00" <= ch <= "\u9fff":
                char_counts[ch] = char_counts.get(ch, 0) + 1
                total += 1

        if total == 0:
            return text

        noise_chars: set[str] = set()
        for ch, count in char_counts.items():
            ratio = count / total
            if ratio > _HALLUCINATION_RATIO_THRESHOLD and ch not in self.hotword_set:
                if not any(ch in hw for hw in self.hotword_set):
                    noise_chars.add(ch)

        if not noise_chars:
            return text

        cleaned = "".join(ch for ch in text if ch not in noise_chars)
        if len(cleaned.strip()) < _MIN_SEGMENT_TEXT_LEN:
            return text
        return cleaned

    def _find_best_match_in_fulltext(self, segment_text: str, fulltext: str) -> float:
        if not segment_text or not fulltext:
            return 0.0
        seg_clean = segment_text.replace(" ", "").replace("，", "").replace("。", "")
        full_clean = fulltext.replace(" ", "").replace("，", "").replace("。", "")
        if not seg_clean or not full_clean:
            return 0.0
        if seg_clean in full_clean:
            return 1.0
        matcher = SequenceMatcher(None, seg_clean, full_clean, autojunk=False)
        best = 0.0
        for block in matcher.get_matching_blocks():
            if block.size >= len(seg_clean) * 0.5:
                best = max(best, block.size / len(seg_clean))
        if best > 0:
            return best
        return matcher.ratio() * (len(seg_clean) / max(len(full_clean), 1))

    def _find_time_aligned_segment(
        self, start: float, end: float, funasr_segments: list[dict],
    ) -> str:
        if not funasr_segments:
            return ""
        best_text = ""
        best_overlap = 0.0
        for seg in funasr_segments:
            seg_start = seg.get("start", 0)
            seg_end = seg.get("end", 0)
            if isinstance(seg_start, (int, float)) and isinstance(seg_end, (int, float)):
                overlap = max(0, min(end, seg_end) - max(start, seg_start))
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_text = seg.get("text", "")
        return self._clean_hallucinations(best_text)

    def _pick_best_alternative(
        self,
        primary: str,
        funasr_seg_text: str,
        whisper_fulltext: str,
        start: float,
        end: float,
    ) -> str | None:
        candidates: list[tuple[str, float]] = []

        if funasr_seg_text and len(funasr_seg_text) >= _MIN_SEGMENT_TEXT_LEN:
            sim = SequenceMatcher(
                None, primary, funasr_seg_text, autojunk=False
            ).ratio()
            hotword_bonus = self._hotword_coverage(funasr_seg_text)
            candidates.append((funasr_seg_text, sim * 0.5 + hotword_bonus * 0.5))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[1], reverse=True)
        best_text, best_score = candidates[0]

        if best_score > 0.3:
            return best_text
        return None

    def _hotword_coverage(self, text: str) -> float:
        if not text:
            return 0.0
        hits = sum(1 for hw in self.hotword_set if hw in text)
        return min(hits / 3.0, 1.0)


__all__ = ["ASRMerger"]
