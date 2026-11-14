"""Validation-set (C) gate: compare candidate metrics with ``baseline_val_metrics``."""
from __future__ import annotations

from .config import CRITICALITY_RANK


def _worse(candidate, baseline, tolerance: float) -> bool:
    """Non-inferiority: None on either side means no evidence, so not a regression."""
    if candidate is None or baseline is None:
        return False
    return candidate < baseline - tolerance


def val_veto(metrics: dict, baseline: dict, config: dict) -> dict:
    gate = config["gate"]
    tol = gate["tolerance"]
    reasons = []
    if metrics["crisis_missed"] > gate["crisis_missed_max"]:
        reasons.append({"code": "crisis_missed", "message": f"验证集危机漏报 {metrics['crisis_missed']} 例。"})
    if gate["crisis_recall_non_inferior"] and _worse(metrics["crisis_recall"], baseline["crisis_recall"], 0.0):
        reasons.append({"code": "crisis_missed", "message": "验证集危机召回率低于上一代。"})
    if gate["referral_recall_non_inferior"] and _worse(metrics["referral_recall"], baseline["referral_recall"], tol):
        reasons.append({"code": "referral_recall_regressed", "message": "转介召回率低于上一代。"})
    if gate["referral_recall_by_label_non_inferior"]:
        for label in ("R1", "R2", "R3"):
            if _worse(metrics["referral_recall_by_label"][label], baseline["referral_recall_by_label"][label], tol):
                reasons.append({"code": "referral_recall_regressed", "message": f"{label} 转介召回率低于上一代。"})
    precision = metrics["referral_precision"]
    if precision is not None and precision < gate["referral_precision_floor"]:
        reasons.append({"code": "referral_precision_floor", "message": f"转介精确率低于下限 {gate['referral_precision_floor']}。"})
    if metrics["contraindication_violations"] > gate["contraindication_violations_max"]:
        reasons.append({"code": "contraindication_violation", "message": f"验证集出现 {metrics['contraindication_violations']} 次禁忌违规。"})
    return {"passed": not reasons, "reasons": reasons}


def improves_primary(metrics: dict, baseline: dict, config: dict) -> bool:
    key = config["gate"]["primary_metric"]
    return metrics[key] > baseline[key]


def choose(candidates: list[dict]) -> str | None:
    """Pick among passed candidates: primary metric, then larger ISI drop, then fewer high changes, then id."""
    passed = [c for c in candidates if c["passed"]]
    if not passed:
        return None

    def key(c):
        high = sum(CRITICALITY_RANK[ch["criticality"]] == 2 for ch in c["changes"])
        m = c["val_metrics"]
        return (-m["isi_response_rate"], m["mean_isi_change"], high, c["id"])

    return min(passed, key=key)["id"]
