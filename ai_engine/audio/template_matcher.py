"""
话术模板匹配引擎
将每条评分规则与完整的标准话术模板进行匹配，
计算匹配度(0-100%)，支持按说话人角色过滤。
替代原有的简单关键词匹配 (keyword_matcher.py)。
"""

import difflib

from loguru import logger

VOICE_TEMPLATES = {
    "environment_safety": {
        "templates": ["现场环境安全", "环境安全，可以施救", "确认现场安全"],
        "expected_role": "doctor",
        "phase": "phase1_before_arrival",
        "rule_code": "environment_safety",
        "rule_name": "评估现场环境安全",
        "max_score": 1,
    },
    "inform_family": {
        "templates": [
            "患者意识丧失，呼吸心跳停止，需要立即抢救",
            "病人没有反应，没有呼吸，需要紧急心肺复苏",
            "患者心跳骤停，我们需要立即进行抢救",
        ],
        "expected_role": "doctor",
        "phase": "phase2_arrival_step1",
        "rule_code": "inform_family",
        "rule_name": "口头告知病情",
        "max_score": 1,
    },
    "start_compression": {
        "templates": ["开始胸外按压", "开始心肺复苏", "开始按压"],
        "expected_role": "doctor",
        "phase": "phase2_arrival_step1",
        "rule_code": "compression_start_fast",
        "rule_name": "及时开始胸外按压",
        "max_score": 3,
    },
    "ecg_sign": {
        "templates": [
            "请家属在心电图上签字",
            "这是心电图结果，请您签字确认",
            "心电图打印好了，请签字",
        ],
        "expected_role": "doctor",
        "phase": "phase3_arrival_step2",
        "rule_code": "ecg_sign",
        "rule_name": "心电图纸告知家属签字",
        "max_score": 1,
    },
    "evaluate_rhythm": {
        "templates": [
            "所有人离开，评估心律",
            "大家让开，我要评估心律",
            "停止按压，评估心律",
            "让开，不要接触患者",
        ],
        "expected_role": "doctor",
        "phase": "phase4_arrival_step3",
        "rule_code": "evaluate_rhythm",
        "rule_name": "规范评估心律",
        "max_score": 2,
    },
    "iv_access": {
        "templates": [
            "开通静脉通路",
            "建立静脉通路",
            "静脉通路已开通",
            "请开通静脉通路",
        ],
        "expected_role": None,
        "phase": "phase4_arrival_step3",
        "rule_code": "iv_access",
        "rule_name": "开通静脉通路",
        "max_score": 2,
    },
    "epinephrine_admin": {
        "templates": [
            "肾上腺素1毫克静脉推注",
            "给予肾上腺素1mg",
            "推注肾上腺素1毫克",
            "肾上腺素一毫克",
        ],
        "expected_role": "doctor",
        "phase": "phase4_arrival_step3",
        "rule_code": "epinephrine_admin",
        "rule_name": "肾上腺素1mg推注",
        "max_score": 2,
    },
    "energy_announce": {
        "templates": [
            "除颤能量200焦",
            "双相波200焦耳",
            "设置200焦",
            "能量200焦准备除颤",
        ],
        "expected_role": "doctor",
        "phase": "phase4_arrival_step3",
        "rule_code": "energy_correct",
        "rule_name": "除颤能量正确",
        "max_score": 2,
    },
    "clear_before_defib": {
        "templates": [
            "所有人离开，准备除颤",
            "大家不要接触患者，准备放电",
            "让开，准备除颤",
            "所有人离开患者",
        ],
        "expected_role": "doctor",
        "phase": "phase4_arrival_step3",
        "rule_code": "clear_before_defib",
        "rule_name": "除颤前旁人离开",
        "max_score": 2,
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
        "max_score": 1,
    },
    "re_evaluate": {
        "templates": ["再次评估心律", "停止按压，再次评估", "所有人离开，再次评估"],
        "expected_role": "doctor",
        "phase": "phase5_arrival_step4",
        "rule_code": "re_evaluate",
        "rule_name": "再次规范评估",
        "max_score": 1,
    },
    "compression_handover": {
        "templates": ["更换按压人员", "替换按压", "换人按压", "你来接替按压"],
        "expected_role": "doctor",
        "phase": "phase5_arrival_step4",
        "rule_code": "compression_handover",
        "rule_name": "按压人员更换",
        "max_score": 2,
    },
    "transfer_consent": {
        "templates": [
            "需要转运到医院，请签字同意",
            "转运知情同意，请签字",
            "现在需要转运到医院进一步治疗",
        ],
        "expected_role": "doctor",
        "phase": "phase6_arrival_step5",
        "rule_code": "transfer_consent",
        "rule_name": "转运知情告知",
        "max_score": 1,
    },
    "transfer_monitoring": {
        "templates": [
            "转运途中持续监测血压、氧饱和度",
            "监测生命体征",
            "持续监护血压心律氧饱和度",
        ],
        "expected_role": None,
        "phase": "phase6_arrival_step5",
        "rule_code": "transfer_monitoring",
        "rule_name": "转运途中持续监护",
        "max_score": 1,
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
        "max_score": 1,
    },
}


class TemplateMatcher:
    """话术模板匹配引擎"""

    def __init__(self, templates: dict | None = None, min_similarity: float = 0.35):
        """
        初始化模板匹配器

        Args:
            templates: 话术模板定义字典，默认使用 VOICE_TEMPLATES
            min_similarity: 最低匹配度阈值，低于该值不记为命中
        """
        self.templates = templates or VOICE_TEMPLATES
        self.min_similarity = min_similarity

    def match_transcript(self, transcription: list[dict]) -> list[dict]:
        """
        对转写结果进行话术模板匹配

        Args:
            transcription: 带有 text、start、end、speaker、speaker_role 字段的转写段列表

        Returns:
            匹配结果列表，每个元素包含匹配时间、规则信息、相似度、说话人及角色信息
        """
        matched_events = []

        for rule_key, rule in self.templates.items():
            best_match = self._find_best_match(transcription, rule_key, rule)
            if best_match:
                matched_events.append(best_match)

        logger.info(
            f"话术模板匹配: {len(matched_events)}/{len(self.templates)} 条规则匹配成功"
        )
        return matched_events

    def _find_best_match(
        self, transcription: list[dict], rule_key: str, rule: dict
    ) -> dict | None:
        """在所有转写段中找到与当前规则最佳匹配的一条记录"""
        best_result = None
        best_similarity = 0.0

        expected_role = rule.get("expected_role")

        for seg in transcription:
            text = seg.get("text", "").strip()
            if not text:
                continue

            for template in rule["templates"]:
                similarity = self._compute_similarity(text, template)

                if similarity > best_similarity and similarity >= self.min_similarity:
                    best_similarity = similarity
                    speaker_role = seg.get("speaker_role", "unknown")
                    role_correct = (
                        expected_role is None or speaker_role == expected_role
                    )
                    best_result = {
                        "time": seg.get("start", 0.0),
                        "end": seg.get("end", 0.0),
                        "rule_key": rule_key,
                        "rule_code": rule["rule_code"],
                        "rule_name": rule["rule_name"],
                        "phase": rule["phase"],
                        "score": rule["max_score"],
                        "similarity": round(best_similarity, 3),
                        "matched_text": text,
                        "matched_template": template,
                        "speaker": seg.get("speaker"),
                        "speaker_role": speaker_role,
                        "role_correct": role_correct,
                        "matched_keywords": [],
                    }

        return best_result

    def _compute_similarity(self, text: str, template: str) -> float:
        """
        计算文本与模板的综合匹配度

        组合两类信号:
        1. 序列相似度
        2. 模板双字片段覆盖率
        """
        seq_sim = difflib.SequenceMatcher(None, text, template).ratio()

        template_chars = [template[i : i + 2] for i in range(0, len(template) - 1)]
        if template_chars:
            hits = sum(1 for token in template_chars if token in text)
            keyword_coverage = hits / len(template_chars)
        else:
            keyword_coverage = 0.0

        combined = seq_sim * 0.4 + keyword_coverage * 0.6
        return combined
