import json
from pathlib import Path

from loguru import logger


class ReportGenerator:
    def generate_json_report(
        self, exam_id: int, score_result: dict, timeline_events: list[dict]
    ) -> dict:
        return {
            "exam_id": exam_id,
            "total_score": score_result.get("total_score", 0),
            "max_total": score_result.get("max_total", 100),
            "phase_scores": score_result.get("phase_scores", {}),
            "scoring_details": score_result.get("items", []),
            "timeline": timeline_events,
        }

    def save_json_report(
        self,
        exam_id: int,
        score_result: dict,
        timeline_events: list[dict],
        output_dir: str,
    ) -> str:
        report = self.generate_json_report(exam_id, score_result, timeline_events)
        output_path = Path(output_dir) / f"exam_{exam_id}_report.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        logger.info(f"JSON report saved to {output_path}")
        return str(output_path)
