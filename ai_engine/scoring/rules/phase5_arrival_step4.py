from ai_engine.fusion.timeline import Timeline
from ai_engine.scoring.rules.base import ScoringRule


class ContinueCompression(ScoringRule):
    rule_code = "continue_compression"
    rule_name = "持续胸外按压5个循环"
    phase = "phase5_arrival_step4"
    max_score = 2.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        sensor = context.get("sensor_data", {})
        cycles = sensor.get("phase5_compression_cycles", 0)
        if cycles >= 5:
            return self._result(2.0)
        return self._result(
            0.0,
            f"传感器显示{cycles}个循环(需5个)" if cycles else "传感器数据缺失",
        )


class ReEvaluate(ScoringRule):
    rule_code = "re_evaluate"
    rule_name = "再次规范评估"
    phase = "phase5_arrival_step4"
    max_score = 1.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        score, match = self._compute_voice_score(context)
        if not match:
            return self._result(0.0, "未听到再次评估口令(离开/让开)")

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


class CompressionHandover(ScoringRule):
    rule_code = "compression_handover"
    rule_name = "按压人员更换有效规范"
    phase = "phase5_arrival_step4"
    max_score = 2.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        score, match = self._compute_voice_score(context)
        if not match:
            return self._result(0.0, "未听到按压更换口令(替/换/按压)")

        video_confirmed, video_event = self._check_video_confirm(
            timeline,
            "standing_nearby",
            match.get("time", 0.0),
            window=5.0,
        )
        evidence = {
            "similarity": match.get("similarity", 0.0),
            "matched_text": match.get("matched_text"),
            "speaker_role": match.get("speaker_role"),
            "video_confirmed": video_confirmed,
            "video_event": video_event,
        }
        if score >= self.max_score * 0.6:
            return self._result(score, evidence=evidence)
        return self._result(
            score,
            f"话术匹配度偏低({match.get('similarity', 0.0):.0%})",
            evidence,
        )


PHASE5_RULES = [
    ContinueCompression(),
    ReEvaluate(),
    CompressionHandover(),
]
