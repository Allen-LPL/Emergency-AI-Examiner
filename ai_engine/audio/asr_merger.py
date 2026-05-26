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
# \u4e2d\u6587\u5b57\u7b26\u4e4b\u95f4\u7684\u7a7a\u767d (FunASR runtime SDK ONNX \u8f93\u51fa text_seg \u5b57\u4e0e\u5b57\u95f4\u7528\u7a7a\u683c\u5206\u9694).
# \u4e0d\u5f52\u4e00\u5316\u7684\u8bdd "\u53d6 \u53d6 \u53d6 \u53d6" \u4e0d\u4f1a\u88ab _REPEAT_CHAR_RE \u5339\u914d, \u566a\u97f3\u5b57\u7b26\u6d41\u4e0d\u5230\u6e05\u6d17\u903b\u8f91.
_CJK_INTERNAL_SPACE_RE = re.compile(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])")
# \u8fde\u7eed 3+ \u4e2a\u7531\u7a7a\u683c/\u9017\u53f7\u5206\u9694\u7684 2-5 \u4f4d\u6570\u5b57 token, \u5178\u578b Whisper \u4e2d\u6587\u5e7b\u542c "1001 1002 1003 1004 1005"
_REPEAT_NUMBER_RE = re.compile(r"(?:\b\d{2,5}[\s,\uff0c\u3001]+){2,}\d{2,5}")
# "5 4 3 2 1" \u6216 "1 2 3 4 5" \u5012\u8ba1\u65f6 / \u987a\u6570, \u81f3\u5c11 4 \u4e2a\u8fde\u7eed 1-2 \u4f4d\u6574\u6570
_COUNTDOWN_RE = re.compile(r"(?:\b\d{1,2}[\s,\uff0c\u3001]+){3,}\d{1,2}\b")
# \u4efb\u610f 6-80 \u5b57\u77ed\u8bed\u8fde\u7eed\u91cd\u590d 3+ \u6b21, \u538b\u6210\u5355\u6b21 (\u8986\u76d6 Whisper "\u5224\u65ad\u8109\u640f\u7b49\u64cd\u4f5c..." \u00d7 17 \u8fd9\u79cd\u590d\u8bfb)
_REPEAT_PHRASE_RE = re.compile(r"(.{6,80}?)(?:\1){2,}")
# \u53e5\u5b50\u8fb9\u754c (\u4e2d\u82f1\u6807\u70b9 + \u6362\u884c); \u7528\u4e8e\u53e5\u7ea7\u6e05\u7406\u65f6\u5207\u53e5
_SENTENCE_SPLIT_RE = re.compile(r"([\u3002!?\uff01\uff1f\n]+)")

_MIN_SEGMENT_TEXT_LEN = 2
_HALLUCINATION_RATIO_THRESHOLD = 0.5
# \u53e5\u5185\u6570\u5b57\u5360\u6bd4\u9608\u503c: \u5355\u53e5\u4e2d\u6570\u5b57\u5b57\u7b26 >=3 \u4e14\u5360\u6bd4 >50% \u2192 \u5220\u6574\u53e5.
# \u65e7\u7248\u672c\u7528\u5168\u6bb5\u9608\u503c 60%, Whisper 1571 \u5b57\u6df7\u5408\u771f\u5b9e\u4e2d\u6587+\u5e7b\u542c\u6570\u5b57\u6bb5, \u6574\u6bb5\u6bd4\u4f8b ~30% \u89e6\u4e0d\u5230,
# \u6539\u6210\u53e5\u7ea7\u7c92\u5ea6\u540e\u771f\u6b63\u7684\u5e7b\u542c\u53e5 "1001\u30011002\u30011003\u30011004\u30011005" \u5355\u53e5 100% \u6570\u5b57, \u5fc5\u5220.
# \u771f\u5b9e\u6309\u538b\u8ba1\u6570\u7531 Paraformer \u4e3b\u8def\u51fa, \u8d70\u975e aggressive \u901a\u9053\u4e0d\u4f1a\u88ab\u8bef\u5220.
_NUMBER_PER_SENTENCE_RATIO = 0.5
_NUMBER_PER_SENTENCE_MIN = 3


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

        # 外部 ASR 整段文本走 aggressive 通道: 压重复短语 + 句级数字幻听清理.
        # Whisper 这一路最常见的两种污染都在这里被剥干净: prompt 复读 + 1001/1002... 数字串.
        funasr_text_clean = self._clean_hallucinations(funasr_text, aggressive=True)
        whisper_text_clean = self._clean_hallucinations(whisper_text, aggressive=True)
        tencent_text_clean = self._clean_hallucinations(tencent_text, aggressive=True)

        logger.info(
            f"[ASRMerger] 输入: paraformer={len(paraformer_segments)}段, "
            f"funasr={len(funasr_text)}字 (清洗后 {len(funasr_text_clean)}), "
            f"whisper={len(whisper_text)}字 (清洗后 {len(whisper_text_clean)}), "
            f"tencent={len(tencent_text)}字 (清洗后 {len(tencent_text_clean)})"
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

    def _clean_hallucinations(self, text: str, aggressive: bool = False) -> str:
        """清洗 ASR 文本中的幻听.

        Args:
            text: 原始 ASR 文本.
            aggressive: 是否启用激进模式 (外部 ASR 全文用 True, Paraformer 主路段用 False).
                       激进模式额外做: (a) 6-80 字短语重复 3+ 次压成单次,
                                       (b) 句级数字幻听清理 (单句数字 >=3 字且占比 >50% 删整句).
                       Paraformer 段已经是 VAD 切好的短段, 真实按压计数段不应被误删, 所以默认 False.
        """
        if not text:
            return ""
        # 先归一化中文字之间的空白, 否则 FunASR 的 "取 取 取 取" 不会被字符重复正则匹配,
        # 大段"取"幻听污染合并结果. 见 2026-05-26 funasr_server.log 实例.
        result = _CJK_INTERNAL_SPACE_RE.sub("", text)
        result = _REPEAT_WORD_RE.sub(r"\1", result)
        result = _REPEAT_CHAR_RE.sub(r"\1", result)
        if aggressive:
            # 先压重复短语 (Whisper 复读 prompt × 17 次的兜底)
            result = _REPEAT_PHRASE_RE.sub(r"\1", result)
            # 再按句子清数字幻听
            result = self._strip_number_hallucination_per_sentence(result)
        result = self._remove_noise_chars(result)
        return result.strip()

    @staticmethod
    def _strip_number_hallucination_per_sentence(text: str) -> str:
        """逐句判定数字幻听并删除整句, 比整段阈值更精准.

        规则: 用句末标点切句, 单句中阿拉伯数字字符数 >=3 且占该句长度 >50% → 当成幻听删整句.
        正常句子如 "按压频率每分钟110次" 只有 3 个数字, 总长 11 字, 占比 27% < 50%, 保留.
        幻听句如 "1001、1002、1003、1004、1005" 18 个数字字符, 占比 ~75%, 删除.
        """
        if not text:
            return text
        # _SENTENCE_SPLIT_RE 用括号捕获保留分隔符, 这样 join 后标点不丢
        parts = _SENTENCE_SPLIT_RE.split(text)
        cleaned: list[str] = []
        for part in parts:
            stripped = part.strip()
            if len(stripped) <= 1:
                cleaned.append(part)
                continue
            digit_chars = sum(1 for c in stripped if c.isdigit())
            if (
                digit_chars >= _NUMBER_PER_SENTENCE_MIN
                and digit_chars / len(stripped) > _NUMBER_PER_SENTENCE_RATIO
            ):
                # 整句幻听, 整段删 (不保留前面的标点)
                continue
            cleaned.append(part)
        return "".join(cleaned)

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
