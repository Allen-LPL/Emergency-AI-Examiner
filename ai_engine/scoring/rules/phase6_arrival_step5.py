from ai_engine.fusion.timeline import Timeline
from ai_engine.scoring.rules.base import ScoringRule


class ScoopStretcherTransfer(ScoringRule):
    rule_code = "scoop_stretcher"
    rule_name = "铲式担架转运"
    phase = "phase6_arrival_step5"
    max_score = 1.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        return self._result(1.0, evidence={"note": "担架默认携带，自动满分"})


class TransferConsent(ScoringRule):
    rule_code = "transfer_consent"
    rule_name = "转运知情告知"
    phase = "phase6_arrival_step5"
    max_score = 1.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        score, match = self._compute_voice_score(context)
        if not match:
            return self._result(0.0, "未听到转运知情告知口令")

        evidence = {
            "similarity": match.get("similarity", 0.0),
            "matched_text": match.get("matched_text"),
            "speaker_role": match.get("speaker_role"),
        }
        if score >= self.max_score * 0.6:
            return self._result(score, evidence=evidence)
        return self._result(
            score,
            f"话术匹配度偏低({match.get('similarity', 0.0):.0%})",
            evidence,
        )


class BodyCameraWarning(ScoringRule):
    rule_code = "body_camera"
    rule_name = "执法记录仪预警"
    phase = "phase6_arrival_step5"
    max_score = 1.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        return self._result(1.0, evidence={"note": "执法记录仪默认开启，自动满分"})


class TransferMonitoring(ScoringRule):
    rule_code = "transfer_monitoring"
    rule_name = "转运途中持续监护"
    phase = "phase6_arrival_step5"
    max_score = 1.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        score, match = self._compute_voice_score(context)
        if not match:
            return self._result(0.0, "未听到监护相关口令")

        evidence = {
            "similarity": match.get("similarity", 0.0),
            "matched_text": match.get("matched_text"),
            "speaker_role": match.get("speaker_role"),
        }
        if score >= self.max_score * 0.6:
            return self._result(score, evidence=evidence)
        return self._result(
            score,
            f"话术匹配度偏低({match.get('similarity', 0.0):.0%})",
            evidence,
        )


class HumanisticCare(ScoringRule):
    rule_code = "humanistic_care"
    rule_name = "人文关怀"
    phase = "phase6_arrival_step5"
    max_score = 1.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        score, match = self._compute_voice_score(context)
        if not match:
            return self._result(0.0, "未听到人文关怀口令")

        evidence = {
            "similarity": match.get("similarity", 0.0),
            "matched_text": match.get("matched_text"),
            "speaker_role": match.get("speaker_role"),
        }
        if score >= self.max_score * 0.6:
            return self._result(score, evidence=evidence)
        return self._result(
            score,
            f"话术匹配度偏低({match.get('similarity', 0.0):.0%})",
            evidence,
        )


PHASE6_RULES = [
    ScoopStretcherTransfer(),
    TransferConsent(),
    BodyCameraWarning(),
    TransferMonitoring(),
    HumanisticCare(),
]
