from ai_engine.fusion.timeline import Timeline
from ai_engine.scoring.rules.base import ScoringRule


class CarryDefibrillator(ScoringRule):
    rule_code = "carry_defibrillator"
    rule_name = "携带除颤监护一体机"
    phase = "phase1_before_arrival"
    max_score = 1.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        return self._result(1.0, evidence={"note": "设备默认携带，自动满分"})


class CarryMedicineBox(ScoringRule):
    rule_code = "carry_medicine_box"
    rule_name = "携带急救药箱"
    phase = "phase1_before_arrival"
    max_score = 1.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        return self._result(1.0, evidence={"note": "设备默认携带，自动满分"})


class CarryBreathingBag(ScoringRule):
    rule_code = "carry_breathing_bag"
    rule_name = "携带呼吸球囊"
    phase = "phase1_before_arrival"
    max_score = 1.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        return self._result(1.0, evidence={"note": "设备默认携带，自动满分"})


class RunningToScene(ScoringRule):
    rule_code = "running_to_scene"
    rule_name = "跑步前往现场"
    phase = "phase1_before_arrival"
    max_score = 1.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        running = timeline.find_events_by_type("running")
        if running:
            return self._result(1.0, evidence={"count": len(running)})
        return self._result(0.0, "未检测到跑步动作")


class EnvironmentSafety(ScoringRule):
    rule_code = "environment_safety"
    rule_name = "评估现场环境安全"
    phase = "phase1_before_arrival"
    max_score = 1.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        score, match = self._compute_voice_score(context)
        if not match:
            return self._result(0.0, "未听到'安全'相关口令")

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


PHASE1_RULES = [
    CarryDefibrillator(),
    CarryMedicineBox(),
    CarryBreathingBag(),
    RunningToScene(),
    EnvironmentSafety(),
]
