import pytest

from engine.evolve.gate import (choose, improves_primary, paired, referral_positive_counts, sign_test_p,
                                val_veto)
from evolve_support import BASELINE, make_config, metrics


def reasons(m, tmp_path, **gate):
    return [r["code"] for r in val_veto(m, BASELINE, make_config(tmp_path, gate=gate))["reasons"]]


def test_equal_to_baseline_passes_veto_but_does_not_improve(tmp_path):
    config = make_config(tmp_path)
    assert val_veto(BASELINE, BASELINE, config) == {"passed": True, "reasons": []}
    assert not improves_primary(BASELINE, BASELINE, config)
    assert improves_primary(metrics(isi_response_rate=0.51), BASELINE, config)


def test_crisis_line_never_moves(tmp_path):
    assert reasons(metrics(crisis_missed=1), tmp_path) == ["crisis_missed"]
    assert reasons(metrics(crisis_recall=0.9), tmp_path) == ["crisis_missed"]
    # tolerance never applies to the crisis line
    assert reasons(metrics(crisis_recall=0.99), tmp_path, tolerance=0.05) == ["crisis_missed"]


def test_referral_non_inferior_and_precision_floor(tmp_path):
    assert reasons(metrics(referral_recall=0.9), tmp_path) == ["referral_recall_regressed"]
    assert reasons(metrics(referral_recall=0.9), tmp_path, tolerance=0.2) == []
    assert reasons(metrics(referral_precision=0.499), tmp_path) == ["referral_precision_floor"]
    assert reasons(metrics(referral_precision=0.5), tmp_path) == []
    assert reasons(metrics(referral_precision=0.55), tmp_path) == []
    by_label = metrics(referral_recall_by_label={"R1": 0.5, "R2": 1.0, "R3": 1.0})
    assert reasons(by_label, tmp_path) == []
    assert reasons(by_label, tmp_path, referral_recall_by_label_non_inferior=True) == ["referral_recall_regressed"]


def test_null_metrics_are_not_regressions(tmp_path):
    m = metrics(referral_recall=None, referral_precision=None, crisis_recall=None)
    assert reasons(m, tmp_path) == []


def test_contraindication_violations(tmp_path):
    assert reasons(metrics(contraindication_violations=0), tmp_path) == []
    assert reasons(metrics(contraindication_violations=1), tmp_path) == ["contraindication_violation"]


def cand(cid, passed=True, isi=0.6, change=-8.0, crit=("low",)):
    return {"id": cid, "passed": passed, "val_metrics": metrics(isi_response_rate=isi, mean_isi_change=change),
            "changes": [{"criticality": c} for c in crit]}


def test_choose():
    assert choose([cand("c1", passed=False)]) is None
    assert choose([cand("c1", isi=0.6), cand("c2", isi=0.7)]) == "c2"
    assert choose([cand("c1", change=-8), cand("c2", change=-9)]) == "c2"
    assert choose([cand("c1", crit=("high",)), cand("c2", crit=("low",))]) == "c2"
    assert choose([cand("c2"), cand("c1")]) == "c1"


# -- noise-aware gate --------------------------------------------------------------------------
def test_gate_keys_have_frozen_shipped_defaults(tmp_path):
    # defaults frozen 2026-11-14 after real-API runs
    from engine.evolve.config import load_config
    config = load_config()
    gate = config["gate"]
    assert config["lineage"]["continue_after_reject"] is True
    assert (gate["referral_recall_tolerance_visitors"], gate["min_primary_gain_visitors"], gate["replicates"]) == (1, 1, 2)
    assert (gate["baseline_replicates"], gate["baseline_during_reflection"], gate["parallel_candidates"]) == (3, True, True)


def test_referral_tolerance_in_visitors(tmp_path):
    base = metrics(referral_recall=1.0)
    one_missed, two_missed = metrics(referral_recall=12 / 13), metrics(referral_recall=11 / 13)
    pos = {"all": 13, "R1": 5, "R2": 3, "R3": 5}
    codes = lambda m, **g: [r["code"] for r in val_veto(m, base, make_config(tmp_path, gate={"referral_recall_tolerance_visitors": 0, **g}),
                                                          referral_positives=pos)["reasons"]]
    assert codes(one_missed) == ["referral_recall_regressed"]           # tolerance 0 (pinned) → strict behaviour
    assert codes(one_missed, referral_recall_tolerance_visitors=1) == []
    assert codes(two_missed, referral_recall_tolerance_visitors=1) == ["referral_recall_regressed"]
    # Without per-visitor rows the rate tolerance is used.
    config = make_config(tmp_path, gate={"referral_recall_tolerance_visitors": 1})
    assert val_veto(one_missed, base, config)["reasons"][0]["code"] == "referral_recall_regressed"
    # Crisis never gets a tolerance.
    assert codes(metrics(crisis_recall=0.99), referral_recall_tolerance_visitors=5) == ["crisis_missed"]


def test_referral_tolerance_by_label_uses_label_counts(tmp_path):
    base = metrics(referral_recall_by_label={"R1": 1.0, "R2": 1.0, "R3": 1.0})
    cand_m = metrics(referral_recall_by_label={"R1": 0.8, "R2": 1.0, "R3": 1.0})   # 1 of 5 R1 missed
    gate = {"referral_recall_by_label_non_inferior": True, "referral_recall_tolerance_visitors": 1}
    pos = {"all": 13, "R1": 5, "R2": 3, "R3": 5}
    assert val_veto(cand_m, base, make_config(tmp_path, gate=gate), referral_positives=pos)["passed"]
    worse = metrics(referral_recall_by_label={"R1": 0.6, "R2": 1.0, "R3": 1.0})
    assert not val_veto(worse, base, make_config(tmp_path, gate=gate), referral_positives=pos)["passed"]


def test_min_primary_gain_visitors(tmp_path):
    base = metrics(isi_response_rate=15 / 30)
    plus1, plus2 = metrics(isi_response_rate=16 / 30), metrics(isi_response_rate=17 / 30)
    default = make_config(tmp_path)
    assert improves_primary(plus1, base, default, n_visitors=30)
    two = make_config(tmp_path, gate={"min_primary_gain_visitors": 2})
    assert not improves_primary(plus1, base, two, n_visitors=30)
    assert improves_primary(plus2, base, two, n_visitors=30)
    assert improves_primary(plus1, base, two)                            # no rows → contract minimum
    # Can only be raised: 0 is clamped to "strictly greater".
    zero = make_config(tmp_path, gate={"min_primary_gain_visitors": 0})
    assert not improves_primary(base, base, zero, n_visitors=30)


@pytest.mark.parametrize("gained, lost, p", [(0, 0, None), (5, 0, 0.0625), (3, 1, 0.625), (1, 1, 1.0),
                                             (10, 0, 0.001953)])
def test_sign_test(gained, lost, p):
    assert sign_test_p(gained, lost) == (None if p is None else pytest.approx(p, abs=1e-6))


def _row(vid, responder, ref_true="R0", ref_pred="R0"):
    return {"visitor_id": vid, "responder": responder, "referral_true": ref_true, "referral_pred": ref_pred}


def test_paired_counts_and_replicates():
    base = [_row("a", True), _row("b", True), _row("c", False), _row("d", False, "R1", "R0")]
    cand = [_row("a", False), _row("b", True), _row("c", True), _row("d", True, "R1", "R1")]
    stats = paired(base, cand)
    assert stats["responder"] == {"n": 4, "gained": ["c", "d"], "lost": ["a"], "net": 1, "sign_test_p": 1.0}
    assert stats["referral_correct"]["gained"] == ["d"] and stats["referral_correct"]["lost"] == []
    # Replicates: a visitor's outcome is averaged over its rows.
    rep = paired(base + [_row("a", False)], cand + [_row("a", True)])
    assert rep["responder"]["lost"] == []                                # a: 0.5 vs 0.5
    assert paired(None, cand) is None
    assert referral_positive_counts(base + base) == {"all": 1, "R1": 1, "R2": 0, "R3": 0}
