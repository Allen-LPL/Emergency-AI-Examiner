"""考核报告生成 - HTML 与 PDF (基于院外心脏骤停急救考核评分表模板)."""

from io import BytesIO

from jinja2 import Template
from loguru import logger

# ============================================================
# 阶段编码 → 中文显示
# ============================================================
PHASE_DISPLAY_NAMES = {
    "phase1_before_arrival": "到达现场前",
    "phase2_arrival_step1": "到达现场（第一步）",
    "phase3_arrival_step2": "到达现场（第二步）",
    "phase4_arrival_step3": "到达现场（第三步）",
    "phase5_arrival_step4": "到达现场（第四步）",
    "phase6_arrival_step5": "到达现场（第五步）",
    "objective_compression": "按压质量",
    "objective_ventilation": "有效通气",
    "objective_ccf": "CCF（按压分数）",
}

# 主观评分 / 客观评分 分组
SUBJECTIVE_PHASES = {
    "phase1_before_arrival",
    "phase2_arrival_step1",
    "phase3_arrival_step2",
    "phase4_arrival_step3",
    "phase5_arrival_step4",
    "phase6_arrival_step5",
}
OBJECTIVE_PHASES = {
    "objective_compression",
    "objective_ventilation",
    "objective_ccf",
}

# ============================================================
# rule_code → 判断模态分类 (视频 / 语音 / 时间 / 传感器)
# 对齐 Excel 表中各行所标注的"判断"列含义
# ============================================================
RULE_JUDGMENT_TYPE: dict[str, str] = {
    # phase1 - 到达现场前
    "carry_defibrillator": "video",
    "carry_medicine_box": "video",
    "carry_breathing_bag": "video",
    "running_to_scene": "video",
    "environment_safety": "voice",
    # phase2 - 到达现场(第一步)
    "equipment_placement": "video",
    "inform_family": "voice",
    "compression_start_fast": "time",
    # phase3 - 到达现场(第二步)
    "breathing_bag_prep": "sensor",
    "ecg_connection": "video",
    "ecg_print": "video",
    "ecg_sign": "voice",
    "smooth_cooperation_step2": "time",
    # phase4 - 到达现场(第三步)
    "cv_ratio": "sensor",
    "five_cycles": "sensor",
    "evaluate_rhythm": "voice",
    "iv_access": "voice",
    "epinephrine_admin": "voice",
    "apply_conductive_paste": "video",
    "paste_position_correct": "video",
    "energy_correct": "video",
    "clear_before_defib": "voice",
    "defib_skilled": "time",
    "compression_during_defib": "sensor",
    "compression_after_defib": "sensor",
    "informed_consent": "voice",
    "cooperation_smooth": "video",
    # phase5 - 到达现场(第四步)
    "continue_compression": "sensor",
    "re_evaluate": "voice",
    "compression_handover": "voice",
    # phase6 - 到达现场(第五步)
    "scoop_stretcher": "video",
    "transfer_consent": "voice",
    "body_camera": "video",
    "transfer_monitoring": "voice",
    "humanistic_care": "voice",
    # 客观评分
    "compression_quality": "sensor",
    "ventilation_quality": "sensor",
    "ccf_score": "sensor",
}

def _judgment_type(rule_code: str) -> str:
    """根据规则编码推断判断模态，未知归为视频。"""
    return RULE_JUDGMENT_TYPE.get(rule_code, "video")


# ============================================================
# HTML 模板 - 对齐院外心脏骤停急救考核评分表(三人)结构
# ============================================================
REPORT_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>院外心脏骤停急救考核评分表 #{{ exam_id }}</title>
<style>
  @page { size: A4 landscape; margin: 14mm 10mm; }
  body {
    font-family: "Noto Sans CJK SC", "Microsoft YaHei", "PingFang SC", "WenQuanYi Zen Hei", sans-serif;
    color: #222;
    font-size: 11px;
    line-height: 1.5;
  }
  h1 {
    text-align: center;
    font-size: 18px;
    margin: 0 0 6px 0;
    letter-spacing: 2px;
  }
  .meta {
    display: flex;
    justify-content: space-between;
    margin-bottom: 8px;
    font-size: 11px;
    color: #444;
  }
  .meta .total {
    font-weight: bold;
    color: {{ score_color }};
    font-size: 14px;
  }
  table.score-table {
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
  }
  table.score-table th,
  table.score-table td {
    border: 1px solid #555;
    padding: 4px 6px;
    vertical-align: middle;
    word-break: break-word;
    text-align: center;
  }
  table.score-table thead th {
    background: #e6efff;
    font-weight: bold;
    font-size: 11px;
  }
  td.criteria-cell {
    text-align: left;
    white-space: pre-line;
  }
  td.judgment-cell {
    font-size: 10px;
    text-align: left;
    white-space: pre-line;
    color: #333;
  }
  td.category-cell {
    writing-mode: vertical-rl;
    font-weight: bold;
    background: #fafafa;
    letter-spacing: 4px;
  }
  td.phase-cell {
    font-weight: bold;
    background: #f4f7ff;
  }
  td.score-cell {
    font-weight: bold;
    font-size: 12px;
  }
  td.score-cell.full { color: #1a7f37; }
  td.score-cell.partial { color: #d97706; }
  td.score-cell.zero { color: #c92a2a; }
  tr.total-row td {
    background: #fff5e0;
    font-weight: bold;
    font-size: 13px;
  }
  .summary-section {
    margin-top: 16px;
    page-break-inside: avoid;
  }
  .summary-section h2 {
    font-size: 14px;
    margin: 0 0 6px 0;
    border-left: 4px solid #1a56db;
    padding-left: 8px;
  }
  .deduction-list {
    border: 1px solid #f1c4c4;
    background: #fff7f7;
    padding: 8px 12px;
    border-radius: 4px;
  }
  .deduction-list ul {
    margin: 0;
    padding-left: 20px;
  }
  .deduction-list li { margin: 3px 0; }
  .check { color: #1a7f37; font-weight: bold; }
  .blank-cell { color: #bbb; }
</style>
</head>
<body>

<h1>院外心脏骤停急救临床路径考核评分表（三人）</h1>

<div class="meta">
  <div>
    <div>考核编号：#{{ exam_id }}</div>
    <div>考核时间：{{ created_at }}</div>
  </div>
  <div>
    最终得分：<span class="total">{{ total_score }}</span> / {{ max_total }}
  </div>
</div>

<table class="score-table">
  <colgroup>
    <col style="width: 4.5%">  <!-- 考核项目 -->
    <col style="width: 10%">   <!-- 实施阶段 -->
    <col style="width: 21%">   <!-- 关键技能 -->
    <col style="width: 11%">   <!-- 视频判断 -->
    <col style="width: 11%">   <!-- 语音判断 -->
    <col style="width: 11%">   <!-- 时间判断 -->
    <col style="width: 11%">   <!-- 传感器判断 -->
    <col style="width: 5%">    <!-- 分值 -->
    <col style="width: 5%">    <!-- 得分 -->
    <col style="width: 10.5%"> <!-- 备注说明 -->
  </colgroup>
  <thead>
    <tr>
      <th>考核项目</th>
      <th>实施阶段/内容</th>
      <th>关键技能操作技能标准及评分</th>
      <th>视频判断</th>
      <th>语音判断</th>
      <th>时间判断</th>
      <th>传感器判断</th>
      <th>分值</th>
      <th>得分</th>
      <th>备注说明</th>
    </tr>
  </thead>
  <tbody>
    {% for category in categories %}
      {% for phase in category.phases %}
        {% set phase_idx = loop.index0 %}
        {% set phase_row_count = phase['items']|length %}
        {% for item in phase['items'] %}
        <tr>
          {% if phase_idx == 0 and loop.first %}
          <td class="category-cell" rowspan="{{ category.row_count }}">{{ category.name }}</td>
          {% endif %}
          {% if loop.first %}
          <td class="phase-cell" rowspan="{{ phase_row_count }}">
            {{ phase['display_name'] }}<br>
            <span style="font-size:10px;font-weight:normal;color:#666;">
              {{ phase['score'] }} / {{ phase['max_score'] }}
            </span>
          </td>
          {% endif %}
          <td class="criteria-cell">{{ item['rule_name'] }}</td>
          <td class="judgment-cell">{% if item['judgment'] == 'video' %}<span class="check">✓</span>{% else %}<span class="blank-cell">-</span>{% endif %}</td>
          <td class="judgment-cell">{% if item['judgment'] == 'voice' %}<span class="check">✓</span>{% else %}<span class="blank-cell">-</span>{% endif %}</td>
          <td class="judgment-cell">{% if item['judgment'] == 'time' %}<span class="check">✓</span>{% else %}<span class="blank-cell">-</span>{% endif %}</td>
          <td class="judgment-cell">{% if item['judgment'] == 'sensor' %}<span class="check">✓</span>{% else %}<span class="blank-cell">-</span>{% endif %}</td>
          <td>{{ item['max_score'] }}</td>
          <td class="score-cell {{ item['score_class'] }}">{{ item['actual_score'] }}</td>
          <td class="judgment-cell">{{ item['deduction_reason'] or '' }}</td>
        </tr>
        {% endfor %}
      {% endfor %}
    {% endfor %}
    <tr class="total-row">
      <td colspan="7" style="text-align:right;">总分</td>
      <td>{{ max_total }}</td>
      <td class="score-cell" style="color:{{ score_color }};">{{ total_score }}</td>
      <td></td>
    </tr>
  </tbody>
</table>

{% if deductions %}
<div class="summary-section">
  <h2>扣分项汇总</h2>
  <div class="deduction-list">
    <ul>
      {% for d in deductions %}
      <li>
        【{{ d['phase_name'] }}】{{ d['rule_name'] }}
        <span style="color:#c92a2a;">-{{ d['lost'] }}分</span>
        {% if d['deduction_reason'] %} - {{ d['deduction_reason'] }}{% endif %}
      </li>
      {% endfor %}
    </ul>
  </div>
</div>
{% endif %}

</body>
</html>
"""


def _score_class(actual: float, max_score: float) -> str:
    if actual >= max_score and max_score > 0:
        return "full"
    if actual <= 0:
        return "zero"
    return "partial"


def _format_score(value: float) -> str:
    """评分显示保留至多 1 位小数，整数则不带小数点。"""
    if abs(value - round(value)) < 0.05:
        return str(int(round(value)))
    return f"{value:.1f}"


def _build_categories(
    items: list[dict],
    phase_scores: dict[str, dict[str, float]],
) -> list[dict]:
    """按 主观/客观 二级分组组织行数据，保持评分表原有顺序。"""
    # 按 phase 分组保留原 items 顺序
    by_phase: dict[str, list[dict]] = {}
    phase_order: list[str] = []
    for item in items:
        phase = item["phase"]
        if phase not in by_phase:
            by_phase[phase] = []
            phase_order.append(phase)
        by_phase[phase].append(item)

    # 让顺序对齐 Excel 表 (phase1 → phase6 → objective_*)
    desired_order = list(PHASE_DISPLAY_NAMES.keys())
    phase_order.sort(
        key=lambda p: desired_order.index(p) if p in desired_order else 999
    )

    def make_phase_block(phase: str) -> dict:
        rows = []
        for item in by_phase[phase]:
            rows.append(
                {
                    "rule_code": item["rule_code"],
                    "rule_name": item["rule_name"],
                    "max_score": _format_score(item["max_score"]),
                    "actual_score": _format_score(item["actual_score"]),
                    "score_class": _score_class(
                        item["actual_score"], item["max_score"]
                    ),
                    "deduction_reason": item.get("deduction_reason") or "",
                    "judgment": _judgment_type(item["rule_code"]),
                }
            )
        ps = phase_scores.get(phase, {"score": 0.0, "max_score": 0.0})
        return {
            "phase": phase,
            "display_name": PHASE_DISPLAY_NAMES.get(phase, phase),
            "score": _format_score(ps.get("score", 0.0)),
            "max_score": _format_score(ps.get("max_score", 0.0)),
            "items": rows,
        }

    subj_phases = [
        make_phase_block(p) for p in phase_order if p in SUBJECTIVE_PHASES
    ]
    obj_phases = [
        make_phase_block(p) for p in phase_order if p in OBJECTIVE_PHASES
    ]

    categories = []
    if subj_phases:
        categories.append(
            {
                "name": "主观评分",
                "phases": subj_phases,
                "row_count": sum(len(ph["items"]) for ph in subj_phases),
            }
        )
    if obj_phases:
        categories.append(
            {
                "name": "客观评分",
                "phases": obj_phases,
                "row_count": sum(len(ph["items"]) for ph in obj_phases),
            }
        )
    return categories


def _normalize_score_result(score_result) -> tuple[list[dict], dict]:
    """统一 items / phase_scores 为 dict 结构，兼容 ORM / Pydantic / dict。"""
    items_raw = score_result.get("items", []) if isinstance(score_result, dict) else getattr(score_result, "items", [])
    items: list[dict] = []
    for it in items_raw:
        if isinstance(it, dict):
            items.append(it)
        elif hasattr(it, "model_dump"):
            items.append(it.model_dump())
        else:
            items.append(
                {
                    "phase": getattr(it, "phase", ""),
                    "rule_code": getattr(it, "rule_code", ""),
                    "rule_name": getattr(it, "rule_name", ""),
                    "max_score": float(getattr(it, "max_score", 0.0)),
                    "actual_score": float(getattr(it, "actual_score", 0.0)),
                    "deduction_reason": getattr(it, "deduction_reason", None),
                }
            )

    phase_scores_raw = (
        score_result.get("phase_scores", {})
        if isinstance(score_result, dict)
        else getattr(score_result, "phase_scores", {})
    )
    phase_scores: dict[str, dict] = {}
    for k, v in phase_scores_raw.items():
        if hasattr(v, "model_dump"):
            phase_scores[k] = v.model_dump()
        elif isinstance(v, dict):
            phase_scores[k] = v
        else:
            phase_scores[k] = {
                "score": float(getattr(v, "score", 0.0)),
                "max_score": float(getattr(v, "max_score", 0.0)),
            }
    return items, phase_scores


def _render_report_html(
    exam_id: int,
    score_result,
    created_at: str,
) -> str:
    """渲染对齐 Excel 评分表结构的 HTML 报告。"""
    items, phase_scores = _normalize_score_result(score_result)

    total = score_result.get("total_score", 0) if isinstance(score_result, dict) else getattr(score_result, "total_score", 0)
    max_total = score_result.get("max_total", 100) if isinstance(score_result, dict) else getattr(score_result, "max_total", 100)

    if total >= 80:
        score_color = "#1a7f37"
    elif total >= 60:
        score_color = "#d97706"
    else:
        score_color = "#c92a2a"

    categories = _build_categories(items, phase_scores)

    deductions = []
    for it in items:
        lost = float(it["max_score"]) - float(it["actual_score"])
        if lost > 0:
            deductions.append(
                {
                    "phase_name": PHASE_DISPLAY_NAMES.get(it["phase"], it["phase"]),
                    "rule_name": it["rule_name"],
                    "lost": _format_score(lost),
                    "deduction_reason": it.get("deduction_reason") or "",
                }
            )

    template = Template(REPORT_TEMPLATE)
    return template.render(
        exam_id=exam_id,
        total_score=_format_score(float(total)),
        max_total=_format_score(float(max_total)),
        score_color=score_color,
        created_at=created_at,
        categories=categories,
        deductions=deductions,
    )


def generate_html_report(
    exam_id: int,
    score_result,
    created_at: str = "",
) -> str:
    """对外暴露的 HTML 报告生成入口。"""
    return _render_report_html(exam_id, score_result, created_at)


def generate_pdf_report(
    exam_id: int,
    score_result,
    created_at: str = "",
) -> bytes:
    """对外暴露的 PDF 报告生成入口 - 使用 weasyprint 将 HTML 渲染为 PDF。"""
    html = _render_report_html(exam_id, score_result, created_at)
    try:
        from weasyprint import HTML
    except ImportError as exc:
        logger.error(f"[报告] 缺少 weasyprint 依赖: {exc}")
        raise RuntimeError("PDF 生成依赖 weasyprint 未安装") from exc

    buffer = BytesIO()
    HTML(string=html).write_pdf(buffer)
    pdf_bytes = buffer.getvalue()
    logger.info(
        f"[报告] PDF 已生成: exam_id={exam_id}, size={len(pdf_bytes) / 1024:.1f}KB"
    )
    return pdf_bytes
