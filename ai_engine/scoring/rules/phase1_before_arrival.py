from ai_engine.fusion.timeline import Timeline
from ai_engine.scoring.rules.base import ScoringRule


class CarryDefibrillator(ScoringRule):
    rule_code = "carry_defibrillator"
    rule_name = "携带除颤监护一体机"
    phase = "phase1_before_arrival"
    max_score = 1.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        equipment = context.get("detected_equipment", [])
        found = any(e.get("class_name") == "defibrillator" for e in equipment)
        if found:
            return self._result(1.0)
        return self._result(0.0, "未检测到除颤监护一体机")


class CarryMedicineBox(ScoringRule):
    rule_code = "carry_medicine_box"
    rule_name = "携带急救药箱"
    phase = "phase1_before_arrival"
    max_score = 1.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        equipment = context.get("detected_equipment", [])
        found = any(e.get("class_name") == "medicine_box" for e in equipment)
        if found:
            return self._result(1.0)
        return self._result(0.0, "未检测到急救药箱")


class CarryBreathingBag(ScoringRule):
    rule_code = "carry_breathing_bag"
    rule_name = "携带呼吸球囊"
    phase = "phase1_before_arrival"
    max_score = 1.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        equipment = context.get("detected_equipment", [])
        found = any(e.get("class_name") == "breathing_bag" for e in equipment)
        if found:
            return self._result(1.0)
        return self._result(0.0, "未检测到呼吸球囊")


class RunningToScene(ScoringRule):
    rule_code = "running_to_scene"
    rule_name = "跑步前往现场"
    phase = "phase1_before_arrival"
    max_score = 1.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        running = timeline.find_events_by_type("running")
        if running:
            return self._result(1.0)
        return self._result(0.0, "未检测到跑步动作")


class EnvironmentSafety(ScoringRule):
    rule_code = "environment_safety"
    rule_name = "评估现场环境安全"
    phase = "phase1_before_arrival"
    max_score = 1.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        voice_matches = context.get("voice_matches", [])
        found = any(m.get("rule_code") == "environment_safety" for m in voice_matches)
        if found:
            return self._result(1.0)
        return self._result(0.0, "未听到'安全'口令")


PHASE1_RULES = [
    CarryDefibrillator(),
    CarryMedicineBox(),
    CarryBreathingBag(),
    RunningToScene(),
    EnvironmentSafety(),
]
