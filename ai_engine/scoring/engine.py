from collections import defaultdict

from loguru import logger

from ai_engine.fusion.timeline import Timeline
from ai_engine.scoring.rules import ALL_RULES


class ScoringEngine:
    def __init__(self, rules=None):
        self.rules = rules or ALL_RULES

    def score(self, timeline: Timeline, context: dict | None = None) -> dict:
        context = context or {}
        items = []

        for rule in self.rules:
            try:
                result = rule.evaluate(timeline, context)
                items.append(result)
            except Exception as e:
                logger.error(f"Rule {rule.rule_code} failed: {e}")
                items.append(
                    {
                        "rule_code": rule.rule_code,
                        "rule_name": rule.rule_name,
                        "phase": rule.phase,
                        "max_score": rule.max_score,
                        "actual_score": 0.0,
                        "deduction_reason": f"评分规则执行异常: {str(e)[:100]}",
                        "evidence": None,
                    }
                )

        total_score = sum(item["actual_score"] for item in items)
        phase_scores = self._get_phase_summary(items)

        logger.info(
            f"Scoring complete: {total_score}/{sum(item['max_score'] for item in items)}"
        )
        return {
            "total_score": round(total_score, 1),
            "max_total": 100.0,
            "items": items,
            "phase_scores": phase_scores,
        }

    def _get_phase_summary(self, items: list[dict]) -> dict:
        phases: dict[str, dict[str, float]] = defaultdict(
            lambda: {"score": 0.0, "max_score": 0.0}
        )
        for item in items:
            phase = item["phase"]
            phases[phase]["score"] += item["actual_score"]
            phases[phase]["max_score"] += item["max_score"]
        return dict(phases)
