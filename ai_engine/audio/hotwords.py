# pyright: reportMissingImports=false
"""急救领域热词库管理.

统一管理急救场景热词, 支持多种输出格式:
    - FunASR WebSocket: JSON dict {"词": 权重, ...}
    - FunASR Paraformer (本地): 空格分隔的热词字符串
    - 通用列表: list[str]

热词权重说明:
    100 = 最高优先级 (核心操作步骤: 心肺复苏/CPR/AED/除颤等)
     11 = 高优先级 (重要术语/指令)
     10 = 中优先级
      8 = 标准优先级
      7 = 基础优先级
"""

from __future__ import annotations

import json
from typing import Any


# ------------------------------------------------------------------ #
# 热词表: (词, 权重)
# 按急救操作流程分组, 便于维护
# ------------------------------------------------------------------ #

# --- 基础场景 & 角色 ---
HOTWORDS_SCENE: list[tuple[str, int]] = [
    ("急救", 11),
    ("抢救", 11),
    ("心肺复苏", 100),
    ("CPR", 100),
    ("院前急救", 11),
    ("应急救护", 10),
    ("现场急救", 11),
    ("有人晕倒", 11),
    ("晕倒", 10),
    ("患者", 10),
    ("伤者", 8),
    ("病人", 8),
]

# --- 环境安全评估 ---
HOTWORDS_SAFETY: list[tuple[str, int]] = [
    ("环境安全", 100),
    ("现场安全", 11),
    ("安全评估", 10),
    ("做好个人防护", 100),
    ("个人防护", 11),
    ("戴手套", 8),
    ("口罩", 6),
]

# --- 意识判断 ---
HOTWORDS_CONSCIOUSNESS: list[tuple[str, int]] = [
    ("判断意识", 100),
    ("意识", 11),
    ("有无意识", 11),
    ("轻拍双肩", 11),
    ("拍打双肩", 11),
    ("呼叫患者", 10),
    ("你怎么了", 9),
    ("能听见吗", 9),
    ("无反应", 11),
    ("意识丧失", 11),
]

# --- 呼救 & 120 ---
HOTWORDS_CALL: list[tuple[str, int]] = [
    ("呼救", 11),
    ("大声呼救", 11),
    ("拨打120", 100),
    ("打120", 11),
    ("120", 100),
    ("呼叫120", 11),
    ("叫救护车", 10),
    ("救护车", 10),
]

# --- AED / 除颤 ---
HOTWORDS_AED: list[tuple[str, int]] = [
    ("取AED", 100),
    ("AED", 100),
    ("自动体外除颤仪", 100),
    ("除颤仪", 100),
    ("除颤监护仪", 11),
    ("除颤监护一体机", 11),
    ("监护仪", 11),
    ("心电监护", 11),
    ("上监护仪", 11),
    ("准备上监护仪", 11),
    ("贴电极片", 100),
    ("电极片", 11),
    ("分析心律", 100),
    ("心律分析", 11),
    ("不要接触患者", 11),
    ("请离开患者", 11),
    ("所有人离开", 11),
    ("开始除颤", 100),
    ("除颤", 100),
    ("电击", 10),
    ("恢复按压", 11),
]

# --- 呼吸检查 ---
HOTWORDS_BREATHING: list[tuple[str, int]] = [
    ("检查呼吸", 100),
    ("判断呼吸", 11),
    ("呼吸", 11),
    ("没有呼吸", 11),
    ("无正常呼吸", 11),
    ("濒死叹息样呼吸", 11),
]

# --- 脉搏检查 ---
HOTWORDS_PULSE: list[tuple[str, int]] = [
    ("检查脉搏", 100),
    ("判断脉搏", 11),
    ("脉搏", 11),
    ("颈动脉", 100),
    ("触摸颈动脉", 11),
    ("无脉搏", 11),
]

# --- 胸外按压 ---
HOTWORDS_COMPRESSION: list[tuple[str, int]] = [
    ("开始按压", 100),
    ("胸外按压", 100),
    ("按压", 11),
    ("按压部位", 11),
    ("胸骨下半段", 11),
    ("两乳头连线中点", 11),
    ("按压深度", 11),
    ("按压频率", 11),
    ("每分钟一百到一百二十次", 11),
    ("五到六厘米", 11),
    ("充分回弹", 11),
    ("减少中断", 10),
    ("三十比二", 100),
    ("30比2", 100),
    ("三十次按压", 11),
    ("两次通气", 11),
]

# --- 气道 & 通气 ---
HOTWORDS_AIRWAY: list[tuple[str, int]] = [
    ("开放气道", 100),
    ("打开气道", 11),
    ("仰头举颏", 100),
    ("仰头抬颏", 11),
    ("清理口腔异物", 11),
    ("清除异物", 10),
    ("人工呼吸", 100),
    ("呼吸球囊", 100),
    ("球囊", 11),
    ("球囊面罩", 11),
    ("简易呼吸器", 11),
    ("通气", 11),
    ("有效通气", 11),
    ("胸廓起伏", 11),
    ("给氧", 10),
    ("吸氧", 10),
    ("氧气", 10),
    ("氧气瓶", 8),
    ("面罩", 8),
]

# --- 药物 & 静脉通路 ---
HOTWORDS_MEDICATION: list[tuple[str, int]] = [
    ("药物已到", 11),
    ("药物", 10),
    ("急救药箱", 11),
    ("肾上腺素", 100),
    ("阿托品", 11),
    ("胺碘酮", 11),
    ("利多卡因", 10),
    ("生理盐水", 10),
    ("建立静脉通路", 100),
    ("静脉通路", 100),
    ("准备静脉", 11),
    ("静脉", 11),
    ("静脉注射", 11),
    ("静脉推注", 11),
    ("留置针", 10),
    ("输液", 10),
    ("医嘱", 8),
    ("无医嘱", 8),
]

# --- 复苏结果 ---
HOTWORDS_OUTCOME: list[tuple[str, int]] = [
    ("复苏成功", 11),
    ("自主呼吸", 11),
    ("恢复自主循环", 100),
    ("ROSC", 100),
    ("继续复苏", 11),
    ("停止复苏", 11),
]

# --- 转运 ---
HOTWORDS_TRANSPORT: list[tuple[str, int]] = [
    ("转运", 10),
    ("准备转运", 11),
    ("担架", 8),
    ("转运车", 8),
]

# --- 人员角色 & 协调 ---
HOTWORDS_COORDINATION: list[tuple[str, int]] = [
    ("医生", 8),
    ("护士", 8),
    ("助手", 8),
    ("家属", 8),
    ("指挥员", 8),
    ("操作者", 8),
    ("按压员", 10),
    ("通气员", 10),
    ("记录员", 8),
    ("各就各位", 11),
    ("收到", 7),
    ("准备开始", 11),
    ("开始", 8),
    ("停止", 8),
    ("交换", 8),
    ("换人", 8),
    ("轮换", 8),
    ("计时", 8),
    ("两分钟", 11),
    ("五秒到十秒", 11),
    ("十秒内", 11),
]

# --- 生命体征 ---
HOTWORDS_VITALS: list[tuple[str, int]] = [
    ("生命体征", 11),
    ("血压", 8),
    ("血氧", 8),
    ("血氧饱和度", 10),
    ("心率", 8),
    ("心跳", 8),
    ("呼吸频率", 8),
    ("瞳孔", 8),
    ("面色", 7),
    ("发绀", 10),
]

# --- 心律 & 骤停 ---
HOTWORDS_RHYTHM: list[tuple[str, int]] = [
    ("室颤", 100),
    ("室速", 100),
    ("无脉性室速", 100),
    ("心搏骤停", 100),
    ("心跳骤停", 100),
    ("呼吸心跳骤停", 100),
    ("可除颤心律", 11),
    ("不可除颤心律", 11),
]

# --- 操作指令 ---
HOTWORDS_COMMANDS: list[tuple[str, int]] = [
    ("继续按压", 11),
    ("暂停按压", 11),
    ("暴露胸部", 11),
    ("保持气道通畅", 11),
    ("保持呼吸道通畅", 11),
    ("评估", 8),
    ("重新评估", 10),
    ("观察", 7),
    ("记录时间", 8),
    ("报告医生", 8),
    ("准备药物", 11),
    ("准备除颤", 11),
    ("准备按压", 11),
    ("准备通气", 11),
    ("准备球囊", 11),
    ("球囊通气", 100),
    ("面罩通气", 11),
    ("连接氧气", 11),
    ("连接监护仪", 11),
    ("连接除颤仪", 11),
    ("开机", 8),
    ("插电极", 8),
    ("充电", 8),
    ("放电", 8),
    ("确认安全", 11),
    ("清场", 11),
    ("大家离开", 11),
    ("无人接触", 11),
    ("我离开", 8),
    ("你离开", 8),
    ("他离开", 8),
]


# ------------------------------------------------------------------ #
# 全部热词合并 (去重保序)
# ------------------------------------------------------------------ #
_ALL_GROUPS: list[list[tuple[str, int]]] = [
    HOTWORDS_SCENE,
    HOTWORDS_SAFETY,
    HOTWORDS_CONSCIOUSNESS,
    HOTWORDS_CALL,
    HOTWORDS_AED,
    HOTWORDS_BREATHING,
    HOTWORDS_PULSE,
    HOTWORDS_COMPRESSION,
    HOTWORDS_AIRWAY,
    HOTWORDS_MEDICATION,
    HOTWORDS_OUTCOME,
    HOTWORDS_TRANSPORT,
    HOTWORDS_COORDINATION,
    HOTWORDS_VITALS,
    HOTWORDS_RHYTHM,
    HOTWORDS_COMMANDS,
]


def _build_hotword_dict() -> dict[str, int]:
    """合并所有分组, 去重取最大权重."""
    result: dict[str, int] = {}
    for group in _ALL_GROUPS:
        for word, weight in group:
            if word in result:
                result[word] = max(result[word], weight)
            else:
                result[word] = weight
    return result


# 单例缓存
_HOTWORD_DICT: dict[str, int] | None = None


def get_hotword_dict() -> dict[str, int]:
    """返回 {热词: 权重} 字典 (缓存)."""
    global _HOTWORD_DICT
    if _HOTWORD_DICT is None:
        _HOTWORD_DICT = _build_hotword_dict()
    return _HOTWORD_DICT


def get_hotword_list() -> list[str]:
    """返回去重的热词列表 (不含权重)."""
    return list(get_hotword_dict().keys())


def get_funasr_ws_hotwords() -> str:
    """返回 FunASR WebSocket 热词格式: JSON dict 字符串.

    格式: '{"心肺复苏": 100, "CPR": 100, ...}'
    直接用于 WebSocket 配置消息的 hotwords 字段.
    """
    return json.dumps(get_hotword_dict(), ensure_ascii=False)


def get_paraformer_hotword_prompt() -> str:
    """返回本地 Paraformer 热词格式: 空格分隔的热词字符串.

    格式: '心肺复苏 CPR 除颤 肾上腺素 ...'
    """
    return " ".join(get_hotword_dict().keys())


def get_hotword_set() -> frozenset[str]:
    """返回热词集合, 用于快速查找."""
    return frozenset(get_hotword_dict().keys())


def get_high_priority_words(min_weight: int = 100) -> list[str]:
    """返回高优先级热词 (权重 >= min_weight)."""
    return [w for w, v in get_hotword_dict().items() if v >= min_weight]


def get_whisper_initial_prompt() -> str:
    """生成 Whisper initial_prompt: 领域描述 + 高权重热词样本.

    背景: Whisper 在中文医疗领域裸跑会大量幻听 (纯数字串/倒计时/重复短语).
    initial_prompt 给模型注入领域上下文, 可显著压低幻听并提高术语命中.

    限制: Whisper 把 initial_prompt 转成 token, 上限 224 token,
    超出会截断且损失末尾内容. 中文 1 字约 ~1.5 token, 所以总长控制在 130 字内,
    只挑权重 >= 10 的高优先级热词, 再做截断兜底.
    """
    hotword_dict = get_hotword_dict()
    # 权重 >=10 的热词按权重降序拍平, 优先保住核心动作/术语
    high_words = sorted(
        [(w, v) for w, v in hotword_dict.items() if v >= 10],
        key=lambda x: -x[1],
    )
    candidate = [w for w, _ in high_words]

    description = (
        "以下是中国心肺复苏与急救考核现场的对话录音, "
        "涉及胸外按压、人工通气、除颤、肾上腺素给药、气道开放、"
        "判断意识、判断呼吸、判断脉搏等操作. 常用术语: "
    )
    # 130 字上限, 减去描述和句末标点
    budget = 130 - len(description) - 1
    selected: list[str] = []
    used = 0
    for word in candidate:
        # +1 是分隔符 "、" 的开销
        cost = len(word) + 1
        if used + cost > budget:
            break
        selected.append(word)
        used += cost
    return description + "、".join(selected) + "."


# ------------------------------------------------------------------ #
# 供 domain_corrector 兼容使用
# ------------------------------------------------------------------ #
def get_hotwords() -> list[str]:
    """兼容旧接口 domain_corrector.get_hotwords()."""
    return get_hotword_list()


def get_hotword_prompt() -> str:
    """兼容旧接口 domain_corrector.get_hotword_prompt()."""
    return get_paraformer_hotword_prompt()


__all__ = [
    "get_hotword_dict",
    "get_hotword_list",
    "get_funasr_ws_hotwords",
    "get_paraformer_hotword_prompt",
    "get_hotword_set",
    "get_high_priority_words",
    "get_whisper_initial_prompt",
    "get_hotwords",
    "get_hotword_prompt",
]
