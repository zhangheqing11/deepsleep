from engine.evolve.gate import choose, improves_primary, val_veto
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
