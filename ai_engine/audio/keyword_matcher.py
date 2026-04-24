from loguru import logger

VOICE_SCORING_RULES = {
    "phase1_safety": {
        "keywords": ["安全"],
        "match_mode": "any",
        "phase": "phase1_before_arrival",
        "rule_code": "environment_safety",
        "rule_name": "评估现场环境安全",
        "max_score": 1,
    },
    "phase2_inform_family": {
        "keywords": ["停", "救"],
        "match_mode": "all",
        "phase": "phase2_arrival_step1",
        "rule_code": "inform_family",
        "rule_name": "口头告知病情",
        "max_score": 1,
    },
    "phase3_sign_ecg": {
        "keywords": ["签", "字"],
        "match_mode": "all",
        "phase": "phase3_arrival_step2",
        "rule_code": "ecg_sign",
        "rule_name": "心电图纸告知家属签字",
        "max_score": 1,
    },
    "phase4_evaluate": {
        "keywords": ["离开", "让开"],
        "match_mode": "any",
        "phase": "phase4_arrival_step3",
        "rule_code": "evaluate_rhythm",
        "rule_name": "规范评估心率",
        "max_score": 2,
    },
    "phase4_iv_access": {
        "keywords": ["开通", "静脉"],
        "match_mode": "all",
        "phase": "phase4_arrival_step3",
        "rule_code": "iv_access",
        "rule_name": "开通静脉通路",
        "max_score": 2,
    },
    "phase4_epinephrine": {
        "keywords": ["肾上腺素", "1mg"],
        "match_mode": "all",
        "phase": "phase4_arrival_step3",
        "rule_code": "epinephrine_admin",
        "rule_name": "肾上腺素1mg推注",
        "max_score": 2,
    },
    "phase4_clear_defib": {
        "keywords": ["离开", "让开"],
        "match_mode": "any",
        "phase": "phase4_arrival_step3",
        "rule_code": "clear_before_defib",
        "rule_name": "除颤前旁人离开",
        "max_score": 2,
    },
    "phase4_sign_consent": {
        "keywords": ["签", "字"],
        "match_mode": "all",
        "phase": "phase4_arrival_step3",
        "rule_code": "informed_consent",
        "rule_name": "知情告知签字",
        "max_score": 1,
    },
    "phase5_evaluate": {
        "keywords": ["离开", "让开"],
        "match_mode": "any",
        "phase": "phase5_arrival_step4",
        "rule_code": "re_evaluate",
        "rule_name": "再次规范评估",
        "max_score": 1,
    },
    "phase5_handover": {
        "keywords": ["替", "换", "按压"],
        "match_mode": "any_two",
        "phase": "phase5_arrival_step4",
        "rule_code": "compression_handover",
        "rule_name": "按压人员更换",
        "max_score": 2,
    },
    "phase6_transfer_consent": {
        "keywords": ["同意", "签", "字"],
        "match_mode": "any_two",
        "phase": "phase6_arrival_step5",
        "rule_code": "transfer_consent",
        "rule_name": "转运知情告知",
        "max_score": 1,
    },
    "phase6_monitoring": {
        "keywords": ["血压", "氧饱和度", "呼末", "心律", "生命体征"],
        "match_mode": "any",
        "phase": "phase6_arrival_step5",
        "rule_code": "transfer_monitoring",
        "rule_name": "转运途中持续监护",
        "max_score": 1,
    },
    "phase6_humanistic_care": {
        "keywords": ["抢救", "尽力"],
        "match_mode": "any",
        "phase": "phase6_arrival_step5",
        "rule_code": "humanistic_care",
        "rule_name": "人文关怀",
        "max_score": 1,
    },
}


class KeywordMatcher:
    def __init__(self, rules: dict | None = None):
        self.rules = rules or VOICE_SCORING_RULES

    def match_transcript(self, transcription: list[dict]) -> list[dict]:
        full_text = " ".join(seg.get("text", "") for seg in transcription)
        matched_events = []

        for rule_key, rule in self.rules.items():
            keywords = rule["keywords"]
            match_mode = rule["match_mode"]
            is_match, matched_kw = self._check_match(full_text, keywords, match_mode)

            if not is_match:
                continue

            match_time = self._find_keyword_time(transcription, matched_kw)
            matched_events.append(
                {
                    "time": match_time,
                    "text": " ".join(matched_kw),
                    "rule_key": rule_key,
                    "rule_code": rule["rule_code"],
                    "rule_name": rule["rule_name"],
                    "phase": rule["phase"],
                    "matched_keywords": matched_kw,
                    "score": rule["max_score"],
                }
            )

        logger.info(
            f"Keyword matching: {len(matched_events)} rules matched from {len(self.rules)} total"
        )
        return matched_events

    def _check_match(
        self, text: str, keywords: list[str], match_mode: str
    ) -> tuple[bool, list[str]]:
        found = [kw for kw in keywords if kw in text]

        if match_mode == "any":
            return len(found) > 0, found
        elif match_mode == "all":
            return len(found) == len(keywords), found
        elif match_mode == "any_two":
            return len(found) >= 2, found
        return False, []

    def _find_keyword_time(
        self, transcription: list[dict], keywords: list[str]
    ) -> float:
        for seg in transcription:
            text = seg.get("text", "")
            if any(kw in text for kw in keywords):
                return seg.get("start", 0.0)
        return 0.0
