# pyright: reportMissingImports=false
"""ASR 文本清洗: 去除 SenseVoice / FunASR 特殊标签、压缩空白、过滤无效短文本。"""

from __future__ import annotations

import re
import unicodedata


# SenseVoice / FunASR 常见的语种与情绪标签, 用正则统一删除
_TAG_PATTERN = re.compile(
    r"<\|"
    r"(?:zh|ja|en|yue|ko|EMO_UNKNOWN|HAPPY|SAD|ANGRY|NEUTRAL|"
    r"Speech|nospeech|BGM|Event|Laughter|Cry|Applause|Cough|Sneeze|Breath|"
    r"WithItn|WoItn)"
    r"\|>",
    re.IGNORECASE,
)

# 多余空白与中文之间空格
_MULTI_WS = re.compile(r"\s+")
_ZH_GAP = re.compile(r"([一-鿿])\s+([一-鿿])")


def clean_asr_text(text: str | None) -> str:
    """规范化 ASR 文本.

    步骤:
        1. None / 空 → 空字符串
        2. 删除 <|...|> 类标签
        3. unicodedata NFKC 归一化全角半角
        4. 压缩多空白
        5. 中文字之间多余空格去掉
    """
    if not text:
        return ""

    cleaned = _TAG_PATTERN.sub("", text)
    cleaned = unicodedata.normalize("NFKC", cleaned)
    cleaned = _MULTI_WS.sub(" ", cleaned)
    # 去除中文字符之间的空格 (Paraformer 偶尔会出现 "胸 外 按 压")
    # 用循环以处理 "胸 外 按 压" 这种连续多空格情况
    prev = None
    while prev != cleaned:
        prev = cleaned
        cleaned = _ZH_GAP.sub(r"\1\2", cleaned)
    return cleaned.strip()


def is_valid_text(text: str | None, min_chars: int = 2) -> bool:
    """简单判断 ASR 文本是否有效.

    无效场景:
        - None / 空字符串
        - 长度小于 min_chars
        - 全是标点/数字 (这种很可能是噪音误识别)
    """
    if not text:
        return False
    text = text.strip()
    if len(text) < min_chars:
        return False
    if not re.search(r"[一-鿿\w]", text):
        return False
    return True


__all__ = ["clean_asr_text", "is_valid_text"]
