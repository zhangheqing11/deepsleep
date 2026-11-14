import copy
import math

import pytest

from engine.evolve import dimensions as dims
from engine.evolve import evidence as ev
from evolve_support import example, make_config

SESSION = example("session.A-001.json")
VISITOR = example("visitor.A-001.json")
MAIN = VISITOR["main_path"]


def probs(p_true, main=MAIN):
    rest = (1 - p_true) / 4
    return {p: (p_true if p == main else rest) for p in ev.PATHS}


def trace_for(session, values):
    """One classifier output per agent turn, in order."""
    agent_turns = [(r["round"], t["turn"]) for r in session["rounds"] for t in r["transcript"] if t["speaker"] == "agent"]
    return {"path_probs": [{"round": r, "turn": t, "probs": probs(v)} for (r, t), v in zip(agent_turns, values)]}


def test_curve_entropy_key_clue_and_first_correct():
    trace = trace_for(SESSION, [0.2, 0.15, 0.5, 0.7, 0.8, 0.9, 0.9, 0.9])
    item = ev.visitor_evidence("A-001", MAIN, SESSION, trace, VISITOR)
    assert item["curve"][0]["p_true"] == pytest.approx(0.2)
    assert item["curve"][0]["entropy"] == pytest.approx(math.log2(5), abs=1e-3)   # uniform
    assert item["curve"][2]["entropy"] < item["curve"][0]["entropy"]
    assert item["first_correct"]["agent_turn"] == 3
    assert item["key_clue_known"]
    assert item["key_clue"] is None or item["key_clue"]["agent_turn"] >= 0
    line = ev.describe(item)
    assert "正确路径权重 0.20→0.15→0.50" in line and "第 3 个 agent 回合起判对" in line


def test_key_clue_turn_from_revealed_ids():
    visitor = copy.deepcopy(VISITOR)
    first_reveal = next((r["round"], t["turn"], t["revealed_clue_ids"][0]) for r in SESSION["rounds"]
                        for t in r["transcript"] if t["revealed_clue_ids"])
    for clue in visitor["clues"]:
        clue["supports"] = MAIN if clue["id"] == first_reveal[2] else "R0"
    item = ev.visitor_evidence("A-001", MAIN, SESSION, None, visitor)
    assert (item["key_clue"]["round"], item["key_clue"]["turn"]) == first_reveal[:2]
    assert item["curve"] == [] and "无分类器权重记录" in ev.describe(item)


def test_alternative_trace_shapes_and_bad_entries():
    alt = {"classifier": [{"round": 1, "turn": 2, "weights": {"P1": 2, "P2": 2, "P3": 0, "P4": 0, "P5": 0}},
                          {"round": 1, "turn": 4, "P1": 1},           # flat dict shape
                          {"round": 1, "turn": 6, "probs": {"P1": -1}},  # invalid → skipped
                          "junk"]}
    series = ev.classifier_series(SESSION, alt)
    assert [s["turn"] for s in series] == [2, 4] and series[0]["probs"]["P1"] == pytest.approx(0.5)
    session = copy.deepcopy(SESSION)
    session["rounds"][0]["transcript"][1]["path_probs"] = probs(0.6)
    assert len(ev.classifier_series(session, None)) == 1


def test_aggregate_curves_and_differences():
    a = ev.visitor_evidence("A-001", MAIN, SESSION, trace_for(SESSION, [0.2, 0.4, 0.7, 0.8, 0.9]), VISITOR)
    b = ev.visitor_evidence("A-001", MAIN, SESSION, trace_for(SESSION, [0.2, 0.2, 0.3, 0.6, 0.9]), VISITOR)
    summary = ev.aggregate([a, b])
    assert summary["n_with_path_probs"] == 2
    first = summary["by_step"][0]
    assert (first["round"], first["step"], first["n"], first["mean_p_true"]) == (1, 1, 2, 0.2)
    assert summary["d1_p_true"][0] == pytest.approx(0.1)
    assert len(summary["d2_p_true"]) == len(summary["d1_p_true"]) - 1
    assert summary["mean_first_correct_agent_turn"] is not None


def test_empty_evidence_is_safe():
    summary = ev.aggregate([ev.visitor_evidence("X", "P1", None, None, None)])
    assert summary["n_with_path_probs"] == 0 and summary["key_clue_rate"] is None and summary["d1_p_true"] == []


def test_classify_dimensions_and_resistance(tmp_path):
    config = make_config(tmp_path)
    row = {"visitor_id": "A-001", "failure_tags": ["path_wrong_r2", "screen_missed", "crisis_missed"], "alliance": 0.9}
    assert dims.classify(row, None, config) == ["path", "screening", "safety"]
    assert "resistance" in dims.classify({**row, "alliance": 0.2}, None, config)
    defensive = {"persona": {"defensiveness": "high"}}
    assert "resistance" in dims.classify(row, defensive, config)
    assert dims.classify({**row, "failure_tags": []}, defensive, config) == []


def test_scorecard_covers_all_dimensions(tmp_path):
    card = dims.scorecard(example("run_report.run1.json"), None, make_config(tmp_path))
    assert set(dims.DIMENSIONS) <= set(card)
    assert card["safety"]["crisis_missed"] == example("run_report.run1.json")["metrics"]["crisis_missed"]
    assert sum(card["failures_by_dimension"].values()) > 0


def test_subagent_map_covers_sections():
    from engine.evolve.config import SECTIONS
    assert set(dims.SUBAGENT_BY_SECTION) == set(SECTIONS)
    assert dims.SUBAGENT_BY_SECTION["plan_rules"] == dims.SUBAGENT_BY_SECTION["referral_rules"] == "plan_adjustment"


def s3_record(rnd, turn, p_true, *, final=False, status="ok", attitude="cooperative"):
    """Shape written by engine-session 5597333 (engine/session.py)."""
    weights = probs(p_true) if status == "ok" else dict.fromkeys(ev.PATHS, 0.2)
    rec = {"round": rnd, "final": final, "weights": weights, "attitude": attitude,
           "uncertainty": 0.5, "margin": 0.1, "status": status, "provider": "mock", "latency_ms": 3.0}
    if not final:
        rec["turn"] = turn
    return rec


def test_s3_trace_shape():
    visitor_turns = [(r["round"], t["turn"]) for r in SESSION["rounds"] for t in r["transcript"] if t["speaker"] == "visitor"]
    (r1a, t1a), (r1b, t1b), (r1c, t1c) = visitor_turns[:3]
    trace = {"path_probs": [
        s3_record(r1a, t1a, 0.2),
        s3_record(r1b, t1b, 0.0, status="timeout"),              # uniform fallback → excluded
        s3_record(r1c, t1c, 0.6, attitude="resistant"),
        s3_record(1, None, 0.65, final=True),                     # round-end record, no turn
    ]}
    item = ev.visitor_evidence("A-001", MAIN, SESSION, trace, VISITOR)
    assert [p["p_true"] for p in item["curve"]] == [0.2, 0.6]
    assert item["finals"][1]["p_true"] == pytest.approx(0.65) and item["finals"][1]["correct"]
    assert item["classifier_failures"] == 1 and item["resistant_steps"] == 1
    summary = ev.aggregate([item])
    assert summary["r1_end_p_true"] == pytest.approx(0.65)        # final record preferred
    assert summary["classifier_failures"] == 1 and summary["resistant_step_rate"] == pytest.approx(0.5)
    line = ev.describe(item)
    assert "第 1 轮 0.65" in line and "来访抗拒 1 次" in line and "已剔除" in line


def test_failed_final_record_is_ignored():
    trace = {"path_probs": [s3_record(1, None, 0.9, final=True, status="error")]}
    item = ev.visitor_evidence("A-001", MAIN, SESSION, trace, VISITOR)
    assert item["finals"] == {} and item["curve"] == [] and item["classifier_failures"] == 1
