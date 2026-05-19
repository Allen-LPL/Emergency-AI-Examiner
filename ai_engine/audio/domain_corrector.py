# pyright: reportMissingImports=false
"""急救领域热词与同音替换纠错.

用途:
    1. get_hotword_prompt() 给 ParaformerASR 提供 hotword 字符串, 让模型在解码时
       对术语词更敏感, 显著降低"除颤→出战""插管→餐馆"这类同音错识。
    2. correct(text) 对 ASR 输出再做一次硬替换兜底, 处理热词没拦住的明显误识。
    3. classify_segment_type(text) 把每段文本分到 medical_command /
       assistant_response / family_inquiry / counting / unknown, 供
       SpeakerRoleBinder 做角色推断与 TemplateMatcher 过滤无效段。
"""

from __future__ import annotations

import re

from ai_engine.audio.types import (
    SEGMENT_TYPE_ASSISTANT_RESPONSE,
    SEGMENT_TYPE_COUNTING,
    SEGMENT_TYPE_FAMILY_INQUIRY,
    SEGMENT_TYPE_MEDICAL_COMMAND,
    SEGMENT_TYPE_UNKNOWN,
)


from ai_engine.audio.hotwords import get_hotword_list as _get_hotword_list
from ai_engine.audio.hotwords import get_paraformer_hotword_prompt as _get_hotword_prompt

ALL_HOTWORDS: list[str] = _get_hotword_list()


# ------------------------------------------------------------------ #
# 同音/谐音替换表 (按出现频率排序常见的纠错)
# ------------------------------------------------------------------ #
CORRECTION_MAP: dict[str, str] = {
    # 除颤 / 室颤 类
    "死战": "除颤",
    "出战": "除颤",
    "实战": "室颤",
    # 插管 类
    "餐馆": "插管",
    "菜馆": "插管",
    # 按压
    "安装": "按压",
    "按装": "按压",
    # 充电/放电
    "充点": "充电",
    "冲电": "充电",
    "放点": "放电",
    # 患者
    "航客": "患者",
    # 复苏
    "公诉": "复苏",
    # 静脉通路
    "开放资料": "开放静脉通路",
    # 肾上腺素
    "审上腺素": "肾上腺素",
    "肾上腺速": "肾上腺素",
    # 球囊
    "球能": "球囊",
}


# ------------------------------------------------------------------ #
# 文本分类用关键词 (用于 classify_segment_type)
# ------------------------------------------------------------------ #
MEDICAL_COMMAND_KEYWORDS = [
    "按压", "除颤", "充电", "放电", "插管", "通气", "球囊",
    "肾上腺素", "推注", "静脉", "评估", "心律", "室颤",
    "开始", "停止", "继续", "暂停", "准备", "恢复",
    "心肺复苏", "电击", "能量", "焦耳", "导电糊",
    "气管", "气道", "心电图",
]

ASSISTANT_RESPONSE_KEYWORDS = [
    "好的", "收到", "明白", "已完成", "完成", "准备好",
    "已连接", "已开通", "已备好", "知道了", "可以",
    "我来", "我做", "我接", "记录", "签字",
]

FAMILY_INQUIRY_KEYWORDS = [
    "家属", "病史", "过敏", "用药", "发病时间",
    "既往", "什么时候", "多长时间", "怎么发病",
    "之前", "以前", "平时", "最近", "签字",
    "知情", "同意书", "送医院",
]

# 数字与计数词模式: 用于识别 counting 类段
_DIGIT_RE = re.compile(r"[0-9]+")
_CN_NUMS = "零一二三四五六七八九十百千万两壹贰叁肆伍陆柒捌玖拾佰仟"
_CN_NUM_RE = re.compile(f"[{_CN_NUMS}]+")


# ------------------------------------------------------------------ #
# 公共 API
# ------------------------------------------------------------------ #
def get_hotwords() -> list[str]:
    """返回完整热词列表 (去重保序)."""
    return _get_hotword_list()


def get_hotword_prompt() -> str:
    """返回 ParaformerASR.hotword 接受的字符串 (空格分隔)."""
    return _get_hotword_prompt()


def correct(text: str | None) -> str:
    """对 ASR 输出做硬替换纠错. 输入 None 视为空字符串."""
    if not text:
        return ""
    out = text
    for wrong, right in CORRECTION_MAP.items():
        if wrong in out:
            out = out.replace(wrong, right)
    return out


def classify_segment_type(text: str | None) -> str:
    """对清洗 + 纠错后的文本做粗分类.

    判定顺序 (按优先级, 命中即返回):
        1. counting:           大部分字符是数字/中文数字 (按压计数)
        2. medical_command:    含医疗动作/术语关键词
        3. assistant_response: 短应答类
        4. family_inquiry:     家属沟通/病史询问
        5. unknown:            兜底
    """
    if not text:
        return SEGMENT_TYPE_UNKNOWN
    s = text.strip()
    if not s:
        return SEGMENT_TYPE_UNKNOWN

    # 1) counting: 数字字符占比 ≥ 50%
    digit_chars = sum(len(m.group()) for m in _DIGIT_RE.finditer(s))
    cn_num_chars = sum(len(m.group()) for m in _CN_NUM_RE.finditer(s))
    num_chars = digit_chars + cn_num_chars
    # 注意: 中文数字字符也可能出现在医疗口令里 ("一毫克"), 所以需要更严格 — 整体很短或纯数字才算 counting
    if num_chars >= max(2, int(0.5 * len(s))) and len(s) <= 15:
        return SEGMENT_TYPE_COUNTING

    # 2) medical_command (医疗动作优先级最高, 因为可能与 assistant_response 重合)
    if any(kw in s for kw in MEDICAL_COMMAND_KEYWORDS):
        return SEGMENT_TYPE_MEDICAL_COMMAND

    # 3) assistant_response (短应答)
    if len(s) <= 12 and any(kw in s for kw in ASSISTANT_RESPONSE_KEYWORDS):
        return SEGMENT_TYPE_ASSISTANT_RESPONSE

    # 4) family_inquiry
    if any(kw in s for kw in FAMILY_INQUIRY_KEYWORDS):
        return SEGMENT_TYPE_FAMILY_INQUIRY

    # 5) 兜底: 较长 assistant_response 也归类
    if any(kw in s for kw in ASSISTANT_RESPONSE_KEYWORDS):
        return SEGMENT_TYPE_ASSISTANT_RESPONSE

    return SEGMENT_TYPE_UNKNOWN


__all__ = [
    "ALL_HOTWORDS",
    "CORRECTION_MAP",
    "MEDICAL_COMMAND_KEYWORDS",
    "ASSISTANT_RESPONSE_KEYWORDS",
    "FAMILY_INQUIRY_KEYWORDS",
    "get_hotwords",
    "get_hotword_prompt",
    "correct",
    "classify_segment_type",
]
