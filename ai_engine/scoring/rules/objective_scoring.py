from ai_engine.fusion.timeline import Timeline
from ai_engine.scoring.rules.base import ScoringRule


class CompressionQuality(ScoringRule):
    rule_code = "compression_quality"
    rule_name = "按压质量(达标率)"
    phase = "objective_compression"
    max_score = 10.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        sensor = context.get("sensor_data", {})
        rate = sensor.get("compression_compliance_rate")
        if rate is None:
            return self._result(0.0, "传感器数据缺失，无法评估按压质量")
        if rate >= 90:
            return self._result(10.0)
        score = round(10 * (rate / 90), 1)
        return self._result(score, f"按压达标率{rate}%(<90%)")


class VentilationQuality(ScoringRule):
    rule_code = "ventilation_quality"
    rule_name = "有效通气(达标率)"
    phase = "objective_ventilation"
    max_score = 10.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        sensor = context.get("sensor_data", {})
        rate = sensor.get("ventilation_compliance_rate")
        if rate is None:
            return self._result(0.0, "传感器数据缺失，无法评估通气质量")
        if rate >= 90:
            return self._result(10.0)
        score = round(10 * (rate / 90), 1)
        return self._result(score, f"通气达标率{rate}%(<90%)")


class CCFScore(ScoringRule):
    rule_code = "ccf_score"
    rule_name = "CCF按压分数"
    phase = "objective_ccf"
    max_score = 20.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        sensor = context.get("sensor_data", {})
        ccf_value = sensor.get("ccf_percentage")

        if ccf_value is not None:
            score = round(20 * (ccf_value / 80), 1)
            return self._result(min(score, 20.0), evidence={"ccf": ccf_value})

        duration = timeline.get_duration()
        compressions = timeline.find_events_by_type("chest_compression")
        if compressions and duration > 0:
            first_comp = compressions[0]["time"]
            last_comp = compressions[-1]["time"]
            compression_duration = last_comp - first_comp
            estimated_ccf = (
                (compression_duration / duration) * 100 if duration > 0 else 0
            )
            score = round(20 * (estimated_ccf / 80), 1)
            return self._result(
                min(score, 20.0),
                evidence={
                    "estimated_ccf": round(estimated_ccf, 1),
                    "note": "基于视频估算",
                },
            )

        return self._result(0.0, "无法计算CCF(数据不足)")


OBJECTIVE_RULES = [
    CompressionQuality(),
    VentilationQuality(),
    CCFScore(),
]
