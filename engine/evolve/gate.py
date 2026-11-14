"""Validation-set (C) gate: compare candidate metrics with ``baseline_val_metrics``.

Noise-aware extensions (all default to the approved behaviour, see ``config.yaml`` ``gate:``):

- ``referral_recall_tolerance_visitors``: non-inferiority tolerance in visitors, converted to a
  rate with the number of referral-positive visitors in the baseline's per-visitor rows
  (``referral_positives``); without rows the rate ``tolerance`` is used. Crisis checks never
  get a tolerance.
- ``min_primary_gain_visitors``: the primary metric must rise by at least this many visitors
  (``n_visitors`` distinct visitors on C). 1 = strictly greater, the contract minimum.
- ``replicates`` + paired statistics: pooling and per-visitor sign tests (``paired``).
"""
from __future__ import annotations

from math import comb

from .config import CRITICALITY_RANK

_EPS = 1e-9
REFERRAL_LABELS = ("R1", "R2", "R3")


def _worse(candidate, baseline, tolerance: float) -> bool:
    """Non-inferiority: None on either side means no evidence, so not a regression."""
    if candidate is None or baseline is None:
        return False
    return candidate < baseline - tolerance


def referral_tolerance(config: dict, positives: int | None) -> float:
    """Rate tolerance for one referral recall comparison.

    ``positives`` = referral-positive visitors behind that recall in the baseline rows (None when
    the evaluator returned metrics only). ``referral_recall_tolerance_visitors == 0`` keeps the
    rate ``tolerance`` exactly as before.
    """
    gate = config["gate"]
    visitors = int(gate.get("referral_recall_tolerance_visitors", 0) or 0)
    if visitors <= 0 or not positives:
        return gate["tolerance"]
    return visitors / positives + _EPS


def val_veto(metrics: dict, baseline: dict, config: dict, *,
             referral_positives: dict | None = None) -> dict:
    """``referral_positives``: ``{"all": n, "R1": n1, "R2": n2, "R3": n3}`` distinct referral-positive
    visitors in the baseline rows, or None (falls back to the rate ``tolerance``)."""
    gate = config["gate"]
    positives = referral_positives or {}
    reasons = []
    if metrics["crisis_missed"] > gate["crisis_missed_max"]:
        reasons.append({"code": "crisis_missed", "message": f"验证集危机漏报 {metrics['crisis_missed']} 例。"})
    if gate["crisis_recall_non_inferior"] and _worse(metrics["crisis_recall"], baseline["crisis_recall"], 0.0):
        reasons.append({"code": "crisis_missed", "message": "验证集危机召回率低于上一代。"})
    if gate["referral_recall_non_inferior"] and _worse(metrics["referral_recall"], baseline["referral_recall"],
                                                       referral_tolerance(config, positives.get("all"))):
        reasons.append({"code": "referral_recall_regressed", "message": "转介召回率低于上一代。"})
    if gate["referral_recall_by_label_non_inferior"]:
        for label in REFERRAL_LABELS:
            if _worse(metrics["referral_recall_by_label"][label], baseline["referral_recall_by_label"][label],
                      referral_tolerance(config, positives.get(label))):
                reasons.append({"code": "referral_recall_regressed", "message": f"{label} 转介召回率低于上一代。"})
    precision = metrics["referral_precision"]
    if precision is not None and precision < gate["referral_precision_floor"]:
        reasons.append({"code": "referral_precision_floor", "message": f"转介精确率低于下限 {gate['referral_precision_floor']}。"})
    if metrics["contraindication_violations"] > gate["contraindication_violations_max"]:
        reasons.append({"code": "contraindication_violation", "message": f"验证集出现 {metrics['contraindication_violations']} 次禁忌违规。"})
    return {"passed": not reasons, "reasons": reasons}


def min_gain_visitors(config: dict) -> int:
    """Never below 1: the contract requires strictly greater."""
    return max(1, int(config["gate"].get("min_primary_gain_visitors", 1) or 1))


def improves_primary(metrics: dict, baseline: dict, config: dict, *, n_visitors: int | None = None) -> bool:
    key = config["gate"]["primary_metric"]
    if not metrics[key] > baseline[key]:  # contract minimum, always enforced
        return False
    need = min_gain_visitors(config)
    if need <= 1 or not n_visitors:
        return True
    return metrics[key] - baseline[key] >= need / n_visitors - _EPS


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


# -- per-visitor pooling and paired statistics ------------------------------------------------
def referral_positive_counts(rows: list[dict] | None) -> dict | None:
    """Distinct referral-positive visitors (overall and per label) in per-visitor rows."""
    if not rows:
        return None
    truth = {r["visitor_id"]: r["referral_true"] for r in rows}
    out = {"all": sum(t != "R0" for t in truth.values())}
    out.update({label: sum(t == label for t in truth.values()) for label in REFERRAL_LABELS})
    return out


def n_visitors(rows: list[dict] | None) -> int | None:
    return len({r["visitor_id"] for r in rows}) if rows else None


def sign_test_p(gained: int, lost: int) -> float | None:
    """Exact two-sided sign test on discordant pairs (ties dropped); None if no discordant pair."""
    n = gained + lost
    if n == 0:
        return None
    k = min(gained, lost)
    tail = sum(comb(n, i) for i in range(k + 1)) / 2 ** n
    return round(min(1.0, 2 * tail), 6)


def _per_visitor_mean(rows: list[dict], outcome) -> dict[str, float]:
    sums: dict[str, list[float]] = {}
    for row in rows:
        sums.setdefault(row["visitor_id"], []).append(float(outcome(row)))
    return {vid: sum(v) / len(v) for vid, v in sums.items()}


def _paired_one(base_rows: list[dict], cand_rows: list[dict], outcome) -> dict:
    """Visitors whose (replicate-averaged) outcome rose / fell vs baseline."""
    base, cand = _per_visitor_mean(base_rows, outcome), _per_visitor_mean(cand_rows, outcome)
    common = sorted(set(base) & set(cand))
    gained = [v for v in common if cand[v] > base[v] + _EPS]
    lost = [v for v in common if cand[v] < base[v] - _EPS]
    return {"n": len(common), "gained": gained, "lost": lost, "net": len(gained) - len(lost),
            "sign_test_p": sign_test_p(len(gained), len(lost))}


def paired(base_rows: list[dict] | None, cand_rows: list[dict] | None) -> dict | None:
    """Paired candidate-vs-baseline statistics on C (None without per-visitor rows on both sides).

    ``responder`` = 4-week ISI response; ``referral_correct`` = ``referral_pred == referral_true`` over
    all visitors (so it moves with both missed referrals and false alarms). With replicates a visitor
    counts as gained / lost when its replicate-averaged outcome rose / fell.
    """
    if not base_rows or not cand_rows:
        return None
    return {
        "responder": _paired_one(base_rows, cand_rows, lambda r: r["responder"]),
        "referral_correct": _paired_one(base_rows, cand_rows, lambda r: r["referral_pred"] == r["referral_true"]),
    }
