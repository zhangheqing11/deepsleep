"""Ring-3 evaluation dimensions and the section → sub-agent map.

TheraMind's cross-session loop scores a single efficacy value; ring 3 judges each run on
several dimensions, files every failure under them, and asks the reflector to target one
dimension per change. ``safety`` is a red line: visible in the scorecard, never editable.
"""
from __future__ import annotations

from statistics import mean

DIMENSIONS = ("path", "referral", "screening", "safety", "plan", "resistance")
EDITABLE_DIMENSIONS = tuple(d for d in DIMENSIONS if d != "safety")
DIMENSION_LABELS = {
    "path": "路径鉴别", "referral": "转介", "screening": "筛查覆盖", "safety": "安全（红线，不可改）",
    "plan": "处方与否决", "resistance": "抗拒来访的处理",
}
SUBAGENT_BY_SECTION = {
    "questioning_strategy": "strategy_generation",
    "path_discrimination": "strategy_generation",
    "communication_style": "response_generation",
    "plan_rules": "plan_adjustment",
    "referral_rules": "plan_adjustment",
}
SUBAGENT_LABELS = {
    "strategy_generation": "策略生成（环 1）",
    "response_generation": "回复生成（环 1）",
    "plan_adjustment": "处方调整（环 2）",
}
# When the reflector omits or garbles ``dimension``, infer it from the section.
DEFAULT_DIMENSION_BY_SECTION = {
    "questioning_strategy": "path", "path_discrimination": "path", "communication_style": "resistance",
    "plan_rules": "plan", "referral_rules": "referral",
}


def classify(row: dict, visitor: dict | None, config: dict) -> list[str]:
    """Dimensions a per_visitor row fails on (ordered as DIMENSIONS)."""
    dc = config["dimensions"]
    dims = {dc["tag_dimension"][t] for t in row["failure_tags"] if t in dc["tag_dimension"]}
    if dims:
        defensive = bool(visitor) and visitor.get("persona", {}).get("defensiveness") in dc["resistance_defensiveness"]
        if defensive or row["alliance"] < dc["resistance_alliance_below"]:
            dims.add("resistance")
    return [d for d in DIMENSIONS if d in dims]


def _avg(values):
    values = [v for v in values if v is not None]
    return round(mean(values), 4) if values else None


def scorecard(run_report: dict, visitors: dict | None, config: dict) -> dict:
    """Per-dimension view of one run_report (more than TheraMind's single efficacy score)."""
    m, rows = run_report["metrics"], run_report["per_visitor"]
    visitors = visitors or {}
    dc = config["dimensions"]
    resistant = [r for r in rows
                 if visitors.get(r["visitor_id"], {}).get("persona", {}).get("defensiveness") in dc["resistance_defensiveness"]]
    by_dim = {d: 0 for d in DIMENSIONS}
    for row in rows:
        for d in classify(row, visitors.get(row["visitor_id"]), config):
            by_dim[d] += 1
    return {
        "path": {"path_acc_r1": m["path_acc_r1"], "path_acc_r2": m["path_acc_r2"], "path_acc_gain": m["path_acc_gain"]},
        "referral": {"referral_recall": m["referral_recall"], "referral_precision": m["referral_precision"],
                     "referral_recall_by_label": m["referral_recall_by_label"]},
        "screening": {"screening_coverage": m["screening_coverage"]},
        "safety": {"crisis_recall": m["crisis_recall"], "crisis_missed": m["crisis_missed"]},
        "plan": {"isi_response_rate": m["isi_response_rate"], "mean_isi_change": m["mean_isi_change"],
                 "contraindication_violations": m["contraindication_violations"],
                 "mean_adherence": _avg(r["adherence"] for r in rows)},
        "resistance": {"n_defensive": len(resistant),
                       "defensive_path_acc_r2": _avg(float(r["path_pred_r2"] == r["main_path"]) for r in resistant),
                       "defensive_mean_alliance": _avg(r["alliance"] for r in resistant),
                       "mean_alliance": _avg(r["alliance"] for r in rows)},
        "failures_by_dimension": by_dim,
    }
