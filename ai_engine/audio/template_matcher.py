# pyright: reportMissingImports=false
"""话术模板匹配 (重写版).

变化点:
    - 输入从旧的 dict 列表改为 SpeechSegment 列表 (强类型)
    - 输出 AudioEvent (统一接口)
    - 相似度算法保持: SequenceMatcher * 0.4 + bigram 覆盖 * 0.6
    - 保留所有现有 rule_code, scoring engine 不需改动
    - 新增急救话术规则 (defib_prepare / defib_done / airway_open /
      ventilation / transport_prepare / history_inquiry)
"""

from __future__ import annotations

import difflib
from typing import Any, Optional

from loguru import logger

from ai_engine.audio.types import AudioEvent, SpeechSegment


VOICE_TEMPLATES: dict[str, dict[str, Any]] = {
    # ---------- phase1 院前准备 ----------
    "environment_safety": {
        "templates": ["现场环境安全", "环境安全可以施救", "确认现场安全"],
        "expected_role": "doctor",
        "phase": "phase1_before_arrival",
        "rule_code": "environment_safety",
        "rule_name": "评估现场环境安全",
    },
    # ---------- phase2 到场告知 ----------
    "inform_family": {
        "templates": [
            "患者意识丧失呼吸心跳停止需要立即抢救",
            "病人没有反应没有呼吸需要紧急心肺复苏",
            "患者心跳骤停我们需要立即进行抢救",
        ],
        "expected_role": "doctor",
        "phase": "phase2_arrival_step1",
        "rule_code": "inform_family",
        "rule_name": "口头告知病情",
    },
    "start_compression": {
        "templates": [
            "开始胸外按压", "立即胸外按压",
            "开始心肺复苏", "继续按压", "开始按压",
        ],
        "expected_role": "doctor",
        "phase": "phase2_arrival_step1",
        "rule_code": "compression_start_fast",
        "rule_name": "及时开始胸外按压",
    },
    # ---------- phase3 评估 / 心电监护 ----------
    "ecg_sign": {
        "templates": [
            "请家属在心电图上签字",
            "这是心电图结果请您签字确认",
            "心电图打印好了请签字",
        ],
        "expected_role": "doctor",
        "phase": "phase3_arrival_step2",
        "rule_code": "ecg_sign",
        "rule_name": "心电图纸告知家属签字",
    },
    "airway_open": {
        "templates": [
            "开放气道", "保持气道通畅", "清理口腔异物",
        ],
        "expected_role": "doctor",
        "phase": "phase3_arrival_step2",
        "rule_code": "airway_open",
        "rule_name": "开放气道",
    },
    "ventilation": {
        "templates": [
            "球囊通气", "观察胸廓起伏", "简易呼吸器通气",
        ],
        "expected_role": None,
        "phase": "phase3_arrival_step2",
        "rule_code": "ventilation",
        "rule_name": "球囊通气",
    },
    # ---------- phase4 除颤 / 用药 ----------
    "evaluate_rhythm": {
        "templates": [
            "所有人离开评估心律", "大家让开我要评估心律",
            "停止按压评估心律", "让开不要接触患者",
        ],
        "expected_role": "doctor",
        "phase": "phase4_arrival_step3",
        "rule_code": "evaluate_rhythm",
        "rule_name": "规范评估心律",
    },
    "iv_access": {
        "templates": [
            "开通静脉通路", "建立静脉通路",
            "静脉通路已开通", "请开通静脉通路",
        ],
        "expected_role": None,
        "phase": "phase4_arrival_step3",
        "rule_code": "iv_access",
        "rule_name": "开通静脉通路",
    },
    "epinephrine_admin": {
        "templates": [
            "肾上腺素一毫克静脉推注",
            "给予肾上腺素一毫克",
            "推注肾上腺素一毫克",
            "肾上腺素一毫克",
        ],
        "expected_role": "doctor",
        "phase": "phase4_arrival_step3",
        "rule_code": "epinephrine_admin",
        "rule_name": "肾上腺素1mg推注",
    },
    "defib_prepare": {
        "templates": [
            "准备除颤", "准备充电", "充电",
            "除颤能量二百焦耳", "双相波二百焦",
        ],
        "expected_role": "doctor",
        "phase": "phase4_arrival_step3",
        "rule_code": "energy_correct",
        "rule_name": "除颤能量正确",
    },
    "clear_before_defib": {
        "templates": [
            "所有人离开准备除颤",
            "大家不要接触患者准备放电",
            "让开准备除颤",
            "所有人离开患者", "清场准备放电",
        ],
        "expected_role": "doctor",
        "phase": "phase4_arrival_step3",
        "rule_code": "clear_before_defib",
        "rule_name": "除颤前旁人离开",
    },
    "defib_done": {
        "templates": [
            "放电", "除颤完成", "电击完成", "电击结束",
        ],
        "expected_role": "doctor",
        "phase": "phase4_arrival_step3",
        "rule_code": "defib_skilled",
        "rule_name": "除颤操作熟练",
    },
    "informed_consent": {
        "templates": [
            "请家属签署知情同意书",
            "需要您签字确认",
            "请在知情同意书上签字",
        ],
        "expected_role": "doctor",
        "phase": "phase4_arrival_step3",
        "rule_code": "informed_consent",
        "rule_name": "知情告知签字",
    },
    # ---------- phase5 持续 CPR ----------
    "re_evaluate": {
        "templates": [
            "再次评估心律", "停止按压再次评估",
            "所有人离开再次评估",
        ],
        "expected_role": "doctor",
        "phase": "phase5_arrival_step4",
        "rule_code": "re_evaluate",
        "rule_name": "再次规范评估",
    },
    "compression_handover": {
        "templates": [
            "更换按压人员", "替换按压",
            "换人按压", "你来接替按压",
        ],
        "expected_role": "doctor",
        "phase": "phase5_arrival_step4",
        "rule_code": "compression_handover",
        "rule_name": "按压人员更换",
    },
    # ---------- phase6 转运 ----------
    "transport_prepare": {
        "templates": [
            "准备转运", "铲式担架", "固定患者准备转运",
        ],
        "expected_role": None,
        "phase": "phase6_arrival_step5",
        "rule_code": "scoop_stretcher",
        "rule_name": "铲式担架转运",
    },
    "transfer_consent": {
        "templates": [
            "需要转运到医院请签字同意",
            "转运知情同意请签字",
            "现在需要转运到医院进一步治疗",
        ],
        "expected_role": "doctor",
        "phase": "phase6_arrival_step5",
        "rule_code": "transfer_consent",
        "rule_name": "转运知情告知",
    },
    "transfer_monitoring": {
        "templates": [
            "转运途中持续监测血压氧饱和度",
            "监测生命体征",
            "持续监护血压心律氧饱和度",
        ],
        "expected_role": None,
        "phase": "phase6_arrival_step5",
        "rule_code": "transfer_monitoring",
        "rule_name": "转运途中持续监护",
    },
    "humanistic_care": {
        "templates": [
            "我们会尽全力抢救",
            "请放心我们正在全力抢救",
            "我们一直在尽力",
        ],
        "expected_role": "doctor",
        "phase": "phase6_arrival_step5",
        "rule_code": "humanistic_care",
        "rule_name": "人文关怀",
    },
    # ---------- 病史询问 (新增) ----------
    "history_inquiry": {
        "templates": [
            "询问病史",
            "有什么过敏史",
            "平时用什么药",
            "发病时间是什么时候",
            "之前有什么病",
        ],
        "expected_role": "driver",  # 由家属沟通方 (默认 driver) 询问
        "phase": "phase2_arrival_step1",
        "rule_code": "history_inquiry",
        "rule_name": "询问病史",
    },
}


class TemplateMatcher:
    """话术模板匹配引擎 (输入 SpeechSegment, 输出 AudioEvent)."""

    def __init__(
        self,
        templates: Optional[dict[str, dict[str, Any]]] = None,
        min_similarity: float = 0.35,
    ) -> None:
        self.templates = templates or VOICE_TEMPLATES
        self.min_similarity = min_similarity

    def match(self, segments: list[SpeechSegment]) -> list[AudioEvent]:
        events: list[AudioEvent] = []
        for rule_key, rule in self.templates.items():
            best = self._find_best_match(segments, rule_key, rule)
            if best is not None:
                events.append(best)
        logger.info(
            f"[TemplateMatcher] 命中 {len(events)}/{len(self.templates)} 条规则"
        )
        return events

    def _find_best_match(
        self,
        segments: list[SpeechSegment],
        rule_key: str,
        rule: dict[str, Any],
    ) -> Optional[AudioEvent]:
        best_event: Optional[AudioEvent] = None
        best_sim = 0.0

        expected_role = rule.get("expected_role")

        for seg in segments:
            text = (seg.text or "").strip()
            if not text:
                continue
            for template in rule["templates"]:
                similarity = self._compute_similarity(text, template)
                if similarity > best_sim and similarity >= self.min_similarity:
                    best_sim = similarity
                    role_correct = (
                        expected_role is None or seg.role == expected_role
                    )
                    best_event = AudioEvent(
                        start=seg.start,
                        end=seg.end,
                        speaker=seg.speaker,
                        role=seg.role,
                        event_type=rule["rule_code"],
                        text=text,
                        rule_code=rule["rule_code"],
                        rule_name=rule.get("rule_name"),
                        phase=rule.get("phase"),
                        similarity=round(best_sim, 3),
                        matched_template=template,
                        role_correct=role_correct,
                        extras={"rule_key": rule_key},
                    )
        return best_event

    @staticmethod
    def _compute_similarity(text: str, template: str) -> float:
        seq_sim = difflib.SequenceMatcher(None, text, template).ratio()
        if len(template) >= 2:
            bigrams = [template[i : i + 2] for i in range(len(template) - 1)]
            hits = sum(1 for bg in bigrams if bg in text)
            coverage = hits / len(bigrams)
        else:
            coverage = 1.0 if template in text else 0.0
        return seq_sim * 0.4 + coverage * 0.6


__all__ = ["TemplateMatcher", "VOICE_TEMPLATES"]
