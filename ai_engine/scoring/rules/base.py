from abc import ABC, abstractmethod

from ai_engine.fusion.timeline import Timeline


class ScoringRule(ABC):
    rule_code: str = ""
    rule_name: str = ""
    phase: str = ""
    max_score: float = 0.0

    @abstractmethod
    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        pass

    def _result(
        self,
        actual_score: float,
        deduction_reason: str | None = None,
        evidence: dict | None = None,
    ) -> dict:
        return {
            "rule_code": self.rule_code,
            "rule_name": self.rule_name,
            "phase": self.phase,
            "max_score": self.max_score,
            "actual_score": min(actual_score, self.max_score),
            "deduction_reason": deduction_reason,
            "evidence": evidence,
        }

    def _find_voice_match(
        self, context: dict, rule_code: str | None = None
    ) -> dict | None:
        code = rule_code or self.rule_code
        voice_matches = context.get("voice_matches", [])
        return next((m for m in voice_matches if m.get("rule_code") == code), None)

    def _compute_voice_score(
        self, context: dict, rule_code: str | None = None
    ) -> tuple[float, dict | None]:
        match = self._find_voice_match(context, rule_code)
        if not match:
            return 0.0, None

        similarity = match.get("similarity", 0.0)
        role_correct = match.get("role_correct", True)
        base_score = self.max_score * similarity

        # 说话角色不正确时，保留部分分值但施加固定折减。
        if not role_correct:
            base_score *= 0.8

        return round(min(base_score, self.max_score), 1), match

    def _check_video_confirm(
        self,
        timeline: Timeline,
        event_type: str,
        audio_time: float,
        window: float = 5.0,
    ) -> tuple[bool, dict | None]:
        event = timeline.find_event_near(event_type, audio_time, window)
        return event is not None, event
