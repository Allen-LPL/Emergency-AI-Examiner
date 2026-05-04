from ai_engine.fusion.timeline import Timeline
from ai_engine.scoring.rules.base import ScoringRule


class CompressionVentilationRatio(ScoringRule):
    rule_code = "cv_ratio"
    rule_name = "按压通气比30:2操作"
    phase = "phase4_arrival_step3"
    max_score = 2.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        sensor = context.get("sensor_data", {})
        ratio_correct = sensor.get("cv_ratio_correct")
        if ratio_correct is True:
            return self._result(2.0)
        if ratio_correct is False:
            return self._result(0.0, "按压通气比不达标(标准30:2)")
        return self._result(0.0, "传感器数据缺失，无法评估按压通气比")


class FiveCycles(ScoringRule):
    rule_code = "five_cycles"
    rule_name = "规范按压5个循环(每循环1分)"
    phase = "phase4_arrival_step3"
    max_score = 5.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        sensor = context.get("sensor_data", {})
        cycles = sensor.get("compression_cycles", 0)
        if cycles >= 5:
            return self._result(5.0)
        score = min(cycles, 5) * 1.0
        return self._result(
            score, f"仅完成{cycles}个循环(需5个)" if cycles < 5 else None
        )


class EvaluateRhythm(ScoringRule):
    rule_code = "evaluate_rhythm"
    rule_name = "规范评估(每5循环评估1次)"
    phase = "phase4_arrival_step3"
    max_score = 2.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        score, match = self._compute_voice_score(context)
        if not match:
            return self._result(0.0, "未听到'离开/让开'评估口令")

        video_confirmed, video_event = self._check_video_confirm(
            timeline,
            "kneeling",
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


class IVAccess(ScoringRule):
    rule_code = "iv_access"
    rule_name = "开通静脉通路"
    phase = "phase4_arrival_step3"
    max_score = 2.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        score, match = self._compute_voice_score(context)
        if not match:
            return self._result(0.0, "未听到开通静脉通路口令")

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


class EpinephrineAdmin(ScoringRule):
    rule_code = "epinephrine_admin"
    rule_name = "肾上腺素1mg推注"
    phase = "phase4_arrival_step3"
    max_score = 2.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        score, match = self._compute_voice_score(context)
        if not match:
            return self._result(0.0, "未听到肾上腺素推注口令")

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


class ApplyConductivePaste(ScoringRule):
    rule_code = "apply_conductive_paste"
    rule_name = "涂抹导电糊"
    phase = "phase4_arrival_step3"
    max_score = 2.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        return self._result(2.0, evidence={"note": "设备默认携带导电糊，自动满分"})


class PastePositionCorrect(ScoringRule):
    rule_code = "paste_position_correct"
    rule_name = "导电糊位置正确"
    phase = "phase4_arrival_step3"
    max_score = 2.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        return self._result(2.0, evidence={"note": "导电糊位置默认正确，自动满分"})


class EnergyCorrect(ScoringRule):
    rule_code = "energy_correct"
    rule_name = "除颤能量正确"
    phase = "phase4_arrival_step3"
    max_score = 2.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        score, match = self._compute_voice_score(context, "energy_correct")
        if not match:
            return self._result(0.0, "未听到除颤能量相关口令")

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


class ClearBeforeDefib(ScoringRule):
    rule_code = "clear_before_defib"
    rule_name = "除颤前旁人离开"
    phase = "phase4_arrival_step3"
    max_score = 2.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        score, match = self._compute_voice_score(context)
        if not match:
            return self._result(0.0, "未听到除颤前'离开/让开'口令")

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


class DefibrillationSkilled(ScoringRule):
    rule_code = "defib_skilled"
    rule_name = "除颤操作熟练(中断<15s)"
    phase = "phase4_arrival_step3"
    max_score = 2.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        compressions = timeline.find_events_by_type("chest_compression")
        if len(compressions) < 2:
            return self._result(2.0, evidence={"note": "数据不足，默认给分"})
        max_gap = max(
            compressions[i]["time"] - compressions[i - 1]["time"]
            for i in range(1, len(compressions))
        )
        if max_gap > 15:
            return self._result(0.0, f"除颤期间中断过长({max_gap:.1f}s > 15s)")
        return self._result(2.0, evidence={"max_gap": round(max_gap, 1)})


class CompressionDuringDefib(ScoringRule):
    rule_code = "compression_during_defib"
    rule_name = "除颤期间持续胸外按压"
    phase = "phase4_arrival_step3"
    max_score = 2.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        sensor = context.get("sensor_data", {})
        maintained = sensor.get("compression_during_defib")
        if maintained is True:
            return self._result(2.0)
        if maintained is False:
            return self._result(0.0, "除颤期间未持续胸外按压")
        return self._result(0.0, "传感器数据缺失")


class CompressionAfterDefib(ScoringRule):
    rule_code = "compression_after_defib"
    rule_name = "除颤后立即恢复按压"
    phase = "phase4_arrival_step3"
    max_score = 2.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        sensor = context.get("sensor_data", {})
        immediate = sensor.get("compression_after_defib_immediate")
        if immediate is True:
            return self._result(2.0)
        if immediate is False:
            return self._result(0.0, "除颤后未立即恢复按压")
        return self._result(0.0, "传感器数据缺失")


class InformedConsent(ScoringRule):
    rule_code = "informed_consent"
    rule_name = "知情告知签字"
    phase = "phase4_arrival_step3"
    max_score = 1.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        score, match = self._compute_voice_score(context)
        if not match:
            return self._result(0.0, "未听到知情告知签字口令")

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


class CooperationSmooth(ScoringRule):
    rule_code = "cooperation_smooth"
    rule_name = "配合熟练"
    phase = "phase4_arrival_step3"
    max_score = 2.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        return self._result(2.0, evidence={"note": "配合熟练默认达标，自动满分"})


PHASE4_RULES = [
    CompressionVentilationRatio(),
    FiveCycles(),
    EvaluateRhythm(),
    IVAccess(),
    EpinephrineAdmin(),
    ApplyConductivePaste(),
    PastePositionCorrect(),
    EnergyCorrect(),
    ClearBeforeDefib(),
    DefibrillationSkilled(),
    CompressionDuringDefib(),
    CompressionAfterDefib(),
    InformedConsent(),
    CooperationSmooth(),
]
