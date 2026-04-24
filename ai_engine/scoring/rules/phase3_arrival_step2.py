from ai_engine.fusion.timeline import Timeline
from ai_engine.scoring.rules.base import ScoringRule


class BreathingBagPrep(ScoringRule):
    rule_code = "breathing_bag_prep"
    rule_name = "准备呼吸球囊通气(手法正确)"
    phase = "phase3_arrival_step2"
    max_score = 3.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        sensor = context.get("sensor_data", {})
        ventilation_volume = sensor.get("ventilation_volume_ml")
        if ventilation_volume is not None:
            if 500 <= ventilation_volume <= 600:
                return self._result(3.0)
            return self._result(
                0.0, f"通气量不达标({ventilation_volume}ml，标准500-600ml)"
            )
        return self._result(0.0, "传感器数据缺失，无法评估通气量")


class ECGConnection(ScoringRule):
    rule_code = "ecg_connection"
    rule_name = "连接心电监护(位置正确)"
    phase = "phase3_arrival_step2"
    max_score = 3.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        ev = timeline.find_first_event("ecg_connection")
        if ev:
            return self._result(3.0)
        video_events = timeline.get_events(source="video")
        has_monitor = any("monitor" in e.get("event_type", "") for e in video_events)
        if has_monitor:
            return self._result(3.0)
        return self._result(0.0, "未检测到心电监护连接")


class ECGPrint(ScoringRule):
    rule_code = "ecg_print"
    rule_name = "完成心电监护打印"
    phase = "phase3_arrival_step2"
    max_score = 1.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        ev = timeline.find_first_event("ecg_print")
        if ev:
            return self._result(1.0)
        return self._result(0.0, "未检测到心电图打印")


class ECGSign(ScoringRule):
    rule_code = "ecg_sign"
    rule_name = "心电图纸告知家属签字"
    phase = "phase3_arrival_step2"
    max_score = 1.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        voice_matches = context.get("voice_matches", [])
        found = any(m.get("rule_code") == "ecg_sign" for m in voice_matches)
        if found:
            return self._result(1.0)
        return self._result(0.0, "未听到签字口令")


class SmoothCooperation2(ScoringRule):
    rule_code = "smooth_cooperation_step2"
    rule_name = "配合熟练(中断<15s)"
    phase = "phase3_arrival_step2"
    max_score = 2.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        compressions = timeline.find_events_by_type("chest_compression")
        if len(compressions) < 2:
            return self._result(2.0, evidence={"note": "按压事件不足，默认给分"})

        max_gap = 0.0
        for i in range(1, len(compressions)):
            gap = compressions[i]["time"] - compressions[i - 1]["time"]
            max_gap = max(max_gap, gap)

        if max_gap > 15:
            return self._result(0.0, f"按压中断过长({max_gap:.1f}s > 15s)")
        return self._result(2.0)


PHASE3_RULES = [
    BreathingBagPrep(),
    ECGConnection(),
    ECGPrint(),
    ECGSign(),
    SmoothCooperation2(),
]
