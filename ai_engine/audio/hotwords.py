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
import re
from pathlib import Path
from typing import Any

from loguru import logger

# 外部热词文件: 由 CPR 标准 SRT 字幕整理而来, 308 条, 比硬编码的 HOTWORDS_* 更全面.
# 文件格式: 词\t权重 (tab 分隔), 权重档次 30/25/20/15
#   30 = 数字口令类 (一千零一/1001/五四三二一/还有十五秒...) → 数字场景必备但 Whisper 慎用
#   25 = 医学术语 / 急救动作 (心肺复苏/胸外按压/肾上腺素...)
#   20 = 生命体征 / 转运
#   15 = 团队协作口令
_EXTERNAL_HOTWORD_FILE = (
    Path(__file__).resolve().parent.parent / "hotwords" / "cpr_funasr_hotwords_weighted.txt"
)
# 数字识别: 全数字 / 阿拉伯数字混合中文计数单位 / 纯中文计数串
_DIGIT_PATTERN = re.compile(
    r"^("
    r"\d+|"                         # 纯阿拉伯数字 (1001, 30, 110)
    r"\d+[%℃\-/到至比].*|"           # 含数字的混合 (92%到98%, 100-120, 30比2)
    r".*\d+.*|"                     # 任意含阿拉伯数字
    r"[零一二三四五六七八九十百千万]{2,}|"  # 纯中文数字串 (一千零一/三十/五四三二一)
    r".*[零一二三四五六七八九十百千万]{3,}.*"  # 含 3+ 连续中文数字字符
    r")$"
)


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


def _load_external_hotwords() -> list[tuple[str, int]]:
    """从 cpr_funasr_hotwords_weighted.txt 加载 308 条 CPR 标准热词.

    文件格式: 每行 `词\\t权重`, 权重为整数.
    解析失败/文件缺失时返回空列表并 warn, 不阻塞主链路.
    """
    if not _EXTERNAL_HOTWORD_FILE.exists():
        logger.warning(
            f"[hotwords] 外部热词文件不存在, 跳过: {_EXTERNAL_HOTWORD_FILE}"
        )
        return []
    entries: list[tuple[str, int]] = []
    try:
        with _EXTERNAL_HOTWORD_FILE.open("r", encoding="utf-8") as f:
            for line_no, raw in enumerate(f, 1):
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                # 容错: tab 或多空格分隔均可
                parts = re.split(r"[\t ]+", line, maxsplit=1)
                if len(parts) != 2:
                    continue
                word, weight_str = parts
                try:
                    entries.append((word.strip(), int(weight_str)))
                except ValueError:
                    logger.warning(
                        f"[hotwords] {_EXTERNAL_HOTWORD_FILE.name}:{line_no} "
                        f"权重无法解析, 跳过: {line!r}"
                    )
        logger.info(
            f"[hotwords] 从 {_EXTERNAL_HOTWORD_FILE.name} 加载 {len(entries)} 条热词"
        )
    except OSError as exc:
        logger.error(f"[hotwords] 读取外部热词文件失败: {exc}")
        return []
    return entries


def _build_hotword_dict() -> dict[str, int]:
    """合并所有分组 (硬编码 HOTWORDS_* + 外部 cpr 热词文件), 去重取最大权重.

    外部文件权重档次是 15/20/25/30, 硬编码档次是 7/8/10/11/100,
    数值不同但都是相对权重, 同名词取 max 即可让最强者生效.
    """
    result: dict[str, int] = {}
    for group in _ALL_GROUPS:
        for word, weight in group:
            if word in result:
                result[word] = max(result[word], weight)
            else:
                result[word] = weight
    # 追加外部 CPR 标准热词 (308 条), 与硬编码合并
    for word, weight in _load_external_hotwords():
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


def export_tencent_hotwords(output_path: str | None = None) -> str:
    """导出腾讯云 ASR 热词表格式 (一行一词 `词 权重`, 空格分隔, 权重 1-100).

    腾讯云控制台-语音识别-自学习模型-热词管理 接受的上传格式即「词 权重」,
    与 FunASR 格式基本一致, 直接复用合并后的热词字典即可.

    Args:
        output_path: 可选, 写入文件路径; None 时仅返回字符串内容.

    Returns:
        热词表内容字符串. 可直接复制到腾讯云控制台粘贴, 或保存为 .txt 上传.

    使用方式:
        python -c "from ai_engine.audio.hotwords import export_tencent_hotwords; \\
                   print(export_tencent_hotwords('/tmp/tencent_hotwords.txt'))"
    """
    hotword_dict = get_hotword_dict()
    # 腾讯权重上限 100, 我们的最高 100, 不需要 rescale
    lines = [f"{word} {weight}" for word, weight in hotword_dict.items()]
    content = "\n".join(lines) + "\n"
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(content, encoding="utf-8")
        logger.info(
            f"[hotwords] 已导出 {len(lines)} 条腾讯热词到 {output_path}"
        )
    return content


def _is_digit_hotword(word: str) -> bool:
    """判断热词是否属于"数字口令"类 (1001/一千零一/五四三二一/30比2/还有15秒...).

    背景: Whisper 在中文医疗场景最严重的幻听就是数字串 ('1001 1002 1003...'),
    如果把这类词塞进 initial_prompt, 反而会暗示模型"该区域应该输出数字",
    与我们消除数字幻听的目标背道而驰. 所以 Whisper initial_prompt 必须过滤掉.
    """
    return bool(_DIGIT_PATTERN.match(word))


def get_whisper_initial_prompt() -> str:
    """生成 Whisper initial_prompt: 自然散文风格领域描述, 防 prompt leaking.

    历史踩坑 (2026-05-25):
        - 早期 prompt 用"顿号列表" ("常用术语: 心肺复苏、CPR、环境安全...")
          → medium 模型遇到静音段把整段 prompt 复读了 17 次, 1571 字里 700 字都是 prompt 残影.
        - 根因: Whisper 内部 condition_on_previous_text 会把 prompt 当成"已转写文本",
          列表式 prompt 是低熵高重复结构, 模型在没信号区域倾向于复读这种"安全"模式.

    防 leak 设计原则:
        1. 用完整句子 + 自然连接词 ("配合"、"过程中"、"等等"), 让 prompt 看起来像
           一段已经讲完的话, Whisper 不会觉得"还要继续讲完";
        2. 不出现长串顿号枚举 (列表枚举是复读高发模式);
        3. 句末用句号收尾, 提示模型"上一段已结束";
        4. 短一些, 总长 < 90 字 (~135 token), 远低于 224 token 上限;
        5. 不含数字, 避免诱导数字幻听 (与 _is_digit_hotword 过滤一致).

    返回示例:
        "这是一段急救现场的中文录音, 急救医生和护士配合完成心肺复苏抢救,
         过程中涉及胸外按压、人工通气、除颤、肾上腺素给药与气道管理等操作."
    """
    # 不再动态拼热词列表 (那是诱因), 用固定散文描述, 让 Whisper 知道领域即可.
    # 真正的术语命中由 FunASR/Paraformer/Tencent 三路热词去覆盖, Whisper 在这套
    # 多路架构里只承担"对照检查"角色, 不需要识别冷门术语.
    return (
        "这是一段急救现场的中文录音, 急救医生和护士配合完成心肺复苏抢救, "
        "过程中涉及胸外按压、人工通气、除颤、肾上腺素给药与气道管理等操作."
    )


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
    "export_tencent_hotwords",
    "get_hotwords",
    "get_hotword_prompt",
]
