from ai_engine.fusion.timeline import Timeline
from ai_engine.scoring.rules.base import ScoringRule


class ScoopStretcherTransfer(ScoringRule):
    rule_code = "scoop_stretcher"
    rule_name = "铲式担架转运"
    phase = "phase6_arrival_step5"
    max_score = 1.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        ev = timeline.find_first_event("stretcher_transfer")
        if ev:
            return self._result(1.0)
        equipment = context.get("detected_equipment", [])
        found = any(e.get("class_name") == "scoop_stretcher" for e in equipment)
        if found:
            return self._result(1.0)
        return self._result(0.0, "未检测到铲式担架转运")


class TransferConsent(ScoringRule):
    rule_code = "transfer_consent"
    rule_name = "转运知情告知"
    phase = "phase6_arrival_step5"
    max_score = 1.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        voice_matches = context.get("voice_matches", [])
        found = any(m.get("rule_code") == "transfer_consent" for m in voice_matches)
        if found:
            return self._result(1.0)
        return self._result(0.0, "未听到转运知情告知口令(同意/签/字)")


class BodyCameraWarning(ScoringRule):
    rule_code = "body_camera"
    rule_name = "执法记录仪预警"
    phase = "phase6_arrival_step5"
    max_score = 1.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        manual = context.get("manual_scores", {})
        if "body_camera" in manual:
            return self._result(float(manual["body_camera"]))
        return self._result(0.0, "需人工评估(执法记录仪)")


class TransferMonitoring(ScoringRule):
    rule_code = "transfer_monitoring"
    rule_name = "转运途中持续监护"
    phase = "phase6_arrival_step5"
    max_score = 1.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        voice_matches = context.get("voice_matches", [])
        found = any(m.get("rule_code") == "transfer_monitoring" for m in voice_matches)
        if found:
            return self._result(1.0)
        return self._result(0.0, "未听到监护相关口令(血压/氧饱和度/心律/生命体征)")


class HumanisticCare(ScoringRule):
    rule_code = "humanistic_care"
    rule_name = "人文关怀"
    phase = "phase6_arrival_step5"
    max_score = 1.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        voice_matches = context.get("voice_matches", [])
        found = any(m.get("rule_code") == "humanistic_care" for m in voice_matches)
        if found:
            return self._result(1.0)
        return self._result(0.0, "未听到人文关怀口令(抢救/尽力)")


PHASE6_RULES = [
    ScoopStretcherTransfer(),
    TransferConsent(),
    BodyCameraWarning(),
    TransferMonitoring(),
    HumanisticCare(),
]
