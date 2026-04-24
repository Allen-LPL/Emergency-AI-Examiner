from jinja2 import Template

REPORT_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>急救考核评分报告 #{{ exam_id }}</title>
<style>
  body { font-family: "Microsoft YaHei", "PingFang SC", sans-serif; margin: 40px; color: #333; }
  h1 { color: #1a56db; border-bottom: 2px solid #1a56db; padding-bottom: 10px; }
  .score-header { display: flex; justify-content: space-between; align-items: center; margin: 20px 0; }
  .total-score { font-size: 48px; font-weight: bold; color: {{ score_color }}; }
  .max-score { font-size: 20px; color: #666; }
  table { width: 100%; border-collapse: collapse; margin: 20px 0; }
  th, td { border: 1px solid #ddd; padding: 10px 12px; text-align: left; }
  th { background: #f0f5ff; font-weight: 600; }
  .phase-header { background: #e6f4ff; font-weight: bold; }
  .full-score { color: #52c41a; }
  .partial-score { color: #faad14; }
  .zero-score { color: #ff4d4f; }
  .deduction { background: #fff2f0; }
  .section { margin: 30px 0; }
  .phase-summary { display: flex; gap: 15px; flex-wrap: wrap; margin: 20px 0; }
  .phase-card { border: 1px solid #d9d9d9; border-radius: 8px; padding: 15px; min-width: 150px; }
  .phase-card h4 { margin: 0 0 8px 0; font-size: 14px; color: #666; }
  .phase-card .value { font-size: 24px; font-weight: bold; }
</style>
</head>
<body>
<h1>院外心脏骤停急救考核评分报告</h1>
<div class="score-header">
  <div>
    <div>考核编号: #{{ exam_id }}</div>
    <div>考核时间: {{ created_at }}</div>
  </div>
  <div>
    <span class="total-score">{{ total_score }}</span>
    <span class="max-score"> / {{ max_total }}</span>
  </div>
</div>

<div class="section">
<h2>各阶段得分</h2>
<div class="phase-summary">
{% for phase_name, phase_data in phase_scores.items() %}
<div class="phase-card">
  <h4>{{ phase_display_names.get(phase_name, phase_name) }}</h4>
  <div class="value {% if phase_data.score == phase_data.max_score %}full-score{% elif phase_data.score > 0 %}partial-score{% else %}zero-score{% endif %}">
    {{ phase_data.score }} / {{ phase_data.max_score }}
  </div>
</div>
{% endfor %}
</div>
</div>

<div class="section">
<h2>评分明细</h2>
<table>
<tr><th>阶段</th><th>考核项目</th><th>满分</th><th>得分</th><th>扣分原因</th></tr>
{% for item in items %}
<tr class="{% if item.actual_score == 0 and item.max_score > 0 %}deduction{% endif %}">
  <td>{{ phase_display_names.get(item.phase, item.phase) }}</td>
  <td>{{ item.rule_name }}</td>
  <td>{{ item.max_score }}</td>
  <td class="{% if item.actual_score == item.max_score %}full-score{% elif item.actual_score > 0 %}partial-score{% else %}zero-score{% endif %}">
    {{ item.actual_score }}
  </td>
  <td>{{ item.deduction_reason or "-" }}</td>
</tr>
{% endfor %}
</table>
</div>

<div class="section">
<h2>改进建议</h2>
<ul>
{% for suggestion in suggestions %}
<li>{{ suggestion }}</li>
{% endfor %}
</ul>
</div>
</body>
</html>
"""

PHASE_DISPLAY_NAMES = {
    "phase1_before_arrival": "到达现场前",
    "phase2_arrival_step1": "到达现场(第一步)",
    "phase3_arrival_step2": "到达现场(第二步)",
    "phase4_arrival_step3": "到达现场(第三步)",
    "phase5_arrival_step4": "到达现场(第四步)",
    "phase6_arrival_step5": "到达现场(第五步)",
    "objective_compression": "按压质量(客观)",
    "objective_ventilation": "有效通气(客观)",
    "objective_ccf": "CCF按压分数(客观)",
}


def generate_suggestions(items: list[dict]) -> list[str]:
    suggestions = []
    for item in items:
        if item.get("actual_score", 0) < item.get("max_score", 0):
            rule_name = item.get("rule_name", "")
            reason = item.get("deduction_reason", "")
            if reason:
                suggestions.append(f"【{rule_name}】{reason}")
            else:
                suggestions.append(f"【{rule_name}】该项未得满分，请加强练习")
    if not suggestions:
        suggestions.append("表现优秀，请继续保持！")
    return suggestions


def generate_html_report(
    exam_id: int,
    score_result: dict,
    created_at: str = "",
) -> str:
    total = score_result.get("total_score", 0)
    if total >= 80:
        score_color = "#52c41a"
    elif total >= 60:
        score_color = "#faad14"
    else:
        score_color = "#ff4d4f"

    items_raw = score_result.get("items", [])
    items = []
    for item in items_raw:
        if hasattr(item, "__dict__"):
            items.append(
                {
                    "phase": item.phase,
                    "rule_code": item.rule_code,
                    "rule_name": item.rule_name,
                    "max_score": item.max_score,
                    "actual_score": item.actual_score,
                    "deduction_reason": item.deduction_reason,
                }
            )
        else:
            items.append(item)

    phase_scores = score_result.get("phase_scores", {})
    ps_dict = {}
    for k, v in phase_scores.items():
        if hasattr(v, "model_dump"):
            ps_dict[k] = v.model_dump()
        elif isinstance(v, dict):
            ps_dict[k] = v
        else:
            ps_dict[k] = {"score": 0, "max_score": 0}

    template = Template(REPORT_TEMPLATE)
    return template.render(
        exam_id=exam_id,
        total_score=total,
        max_total=score_result.get("max_total", 100),
        score_color=score_color,
        created_at=created_at,
        phase_scores=ps_dict,
        phase_display_names=PHASE_DISPLAY_NAMES,
        items=items,
        suggestions=generate_suggestions(items),
    )
