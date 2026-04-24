from ai_engine.fusion.timeline import Timeline
from ai_engine.scoring.rules.base import ScoringRule


class EquipmentPlacement(ScoringRule):
    rule_code = "equipment_placement"
    rule_name = "设备放置在合适位置"
    phase = "phase2_arrival_step1"
    max_score = 1.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        ev = timeline.find_first_event("equipment_placement")
        if ev:
            return self._result(1.0)
        return self._result(0.0, "未检测到设备放置动作")


class InformFamily(ScoringRule):
    rule_code = "inform_family"
    rule_name = "评估患者并口头告知病情(20s内)"
    phase = "phase2_arrival_step1"
    max_score = 1.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        voice_matches = context.get("voice_matches", [])
        match = next(
            (m for m in voice_matches if m.get("rule_code") == "inform_family"), None
        )
        if not match:
            return self._result(0.0, "未听到告知病情口令(关键词:停/救)")

        phases = timeline.detect_phases()
        phase_start = phases.get("phase2_arrival_step1", {}).get("start_time", 0)
        time_diff = match.get("time", 0) - phase_start
        if time_diff > 20:
            return self._result(0.0, f"告知病情超时({time_diff:.1f}s > 20s)")
        return self._result(1.0)


class CompressionStartFast(ScoringRule):
    rule_code = "compression_start_fast"
    rule_name = "及时开始胸外按压(设备放下15s内)"
    phase = "phase2_arrival_step1"
    max_score = 3.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        equip_event = timeline.find_first_event("equipment_placement")
        comp_event = timeline.find_first_event("chest_compression")

        if not comp_event:
            return self._result(0.0, "未检测到胸外按压动作")

        if not equip_event:
            return self._result(3.0, evidence={"note": "未检测到设备放置，默认给分"})

        time_diff = comp_event["time"] - equip_event["time"]
        if time_diff > 15:
            return self._result(0.0, f"开始按压超时({time_diff:.1f}s > 15s)")
        return self._result(3.0, evidence={"time_diff": round(time_diff, 1)})


PHASE2_RULES = [
    EquipmentPlacement(),
    InformFamily(),
    CompressionStartFast(),
]
