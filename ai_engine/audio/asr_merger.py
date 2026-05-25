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
# \u8fde\u7eed 3+ \u4e2a\u7531\u7a7a\u683c/\u9017\u53f7\u5206\u9694\u7684 2-5 \u4f4d\u6570\u5b57 token, \u5178\u578b Whisper \u4e2d\u6587\u5e7b\u542c "1001 1002 1003 1004 1005"
_REPEAT_NUMBER_RE = re.compile(r"(?:\b\d{2,5}[\s,\uff0c\u3001]+){2,}\d{2,5}")
# "5 4 3 2 1" \u6216 "1 2 3 4 5" \u5012\u8ba1\u65f6 / \u987a\u6570, \u81f3\u5c11 4 \u4e2a\u8fde\u7eed 1-2 \u4f4d\u6574\u6570
_COUNTDOWN_RE = re.compile(r"(?:\b\d{1,2}[\s,\uff0c\u3001]+){3,}\d{1,2}\b")

_MIN_SEGMENT_TEXT_LEN = 2
_HALLUCINATION_RATIO_THRESHOLD = 0.5
# \u6570\u5b57\u5b57\u7b26\u5360\u6bb5\u843d\u603b\u957f\u5ea6\u7684\u9608\u503c: \u8d85\u8fc7\u8be5\u6bd4\u4f8b\u8ba4\u4e3a\u6574\u6bb5\u662f\u6570\u5b57\u5e7b\u542c, \u5220\u6389\u6570\u5b57\u6bb5
# (\u8003\u6838\u573a\u666f\u7684\u771f\u5b9e\u6309\u538b\u8ba1\u6570, \u6bb5\u5185\u901a\u5e38\u4f1a\u5939\u6742"\u7ee7\u7eed\u6309\u538b"\u3001"\u653e\u624b"\u7b49\u6c49\u5b57, \u5360\u6bd4\u4e0d\u4f1a\u5230 60%)
_NUMBER_HALLUCINATION_RATIO = 0.6


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
        result = self._strip_number_hallucination(result)
        result = self._remove_noise_chars(result)
        return result.strip()

    @staticmethod
    def _strip_number_hallucination(text: str) -> str:
        """删除 Whisper 中文模型典型的"连续数字串"和"倒计时"幻听.

        策略: 先找数字段, 若它们的总字符数占全文 >= 60% (说明这段几乎全是数字,
        是 Whisper 把静音/噪声转成了数字串), 把这些数字段整段抠掉; 否则保留
        (考核场景按压计数 "1001 1002 1003" 夹在 "继续按压...现在停" 之间, 占比不到 60% 不会误删).
        """
        if not text:
            return text
        matches = _REPEAT_NUMBER_RE.findall(text) + _COUNTDOWN_RE.findall(text)
        if not matches:
            return text
        digit_chars = sum(len(m) for m in matches)
        if digit_chars / max(len(text), 1) < _NUMBER_HALLUCINATION_RATIO:
            return text
        # 数字占比过高, 整段抠掉所有数字段
        for m in matches:
            text = text.replace(m, "")
        return text

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
