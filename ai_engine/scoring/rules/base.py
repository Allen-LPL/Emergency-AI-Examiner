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
