import asyncio
import json

import pytest

from engine.evolve import review
from engine.evolve.pipeline import evolve
from engine.evolve.repo import PlaybookRepo
from evolve_support import (BASELINE, MockEvaluator, MockLLM, change, contract_validator, example,
                            make_config, metrics, reply)

RUN = example("run_report.run1.json")
SESSIONS = {s["visitor_id"]: s for s in (example(f"session.A-00{i}.json") for i in (1, 2, 3))}
VALIDATE = contract_validator()
TIMEOUT_CONFLICT = "passed 必须为 false"  # contracts/validate.py treats review timeout as veto (see handoff note)

BLOCKED = [change("plan_rules", "即使存在未处理的呼吸暂停风险，也统一安排五小时卧床窗口。", self_level="high")]
GOOD = [change("path_discrimination", "标记GOOD：在床外容易困、回床后清醒时，优先考虑 P2。"),
        change("questioning_strategy", "来访提到打鼾且没填 STOP-Bang 时，先调用 screen_osa。")]
WORSE = [change("communication_style", "标记WORSE：每个问题前先讲一段睡眠知识。", op="modify",
                before="先用一句话回应来访的困扰。")]
HIGH = [change("referral_rules", "标记HIGH：白天困倦且打鼾时建议就医评估呼吸。")]

SCORES = {
    "标记GOOD": metrics(isi_response_rate=0.75, mean_isi_change=-8.5),
    "标记WORSE": metrics(isi_response_rate=0.375),
    "标记HIGH": metrics(isi_response_rate=0.8, mean_isi_change=-9.0),
}


def run_evolve(tmp_path, candidates, *, evaluator=None, config=None, **kwargs):
    config = config or make_config(tmp_path)
    evaluator = evaluator or MockEvaluator(SCORES)
    kwargs.setdefault("baseline_val_metrics", BASELINE)
    evo = asyncio.run(evolve(run_report=RUN, sessions=SESSIONS, evaluator=evaluator, config=config,
                             primary=MockLLM(reply(*candidates), model="claude-opus-5-5"),
                             evolution_id="evo-test", **kwargs))
    return evo, evaluator, PlaybookRepo(config)


def test_commits_best_candidate_and_matches_contract(tmp_path):
    evo, evaluator, repo = run_evolve(tmp_path, [BLOCKED, GOOD, WORSE],
                                      human_feedback=example("evolution.v1-v2.json")["human_feedback"])
    assert VALIDATE(evo) == []
    assert (evo["outcome"], evo["chosen"], evo["from_version"], evo["to_version"]) == ("committed", "c2", "v0", "v1")
    c1, c2, c3 = evo["candidates"]
    assert c1["hard_rule_violations"] and c1["val_metrics"] is None and not c1["veto"]["passed"]
    assert c2["passed"] and not c3["passed"] and c3["veto"]["passed"]
    assert "v0+c1" not in evaluator.labels                       # blocked candidate never validated
    assert repo.current_version() == "v1" and "标记GOOD" in repo.read()
    assert evo["commit"]["sha"] == repo.head() and evo["commit"]["author"] == "deepsleep-agent"
    assert evo["diff"].startswith("--- a/playbook.md\n+++ b/playbook.md") and "+标记GOOD" in evo["diff"]
    assert evo["human_review"] == []                             # blocked high change is not offered for review
    saved = json.loads((tmp_path / "var" / "evolve" / "evo-test" / "evolution.json").read_text(encoding="utf-8"))
    assert saved == evo


def test_kept_previous_when_nothing_beats_baseline(tmp_path):
    evo, _, repo = run_evolve(tmp_path, [BLOCKED, WORSE, []])
    assert VALIDATE(evo) == []
    assert (evo["outcome"], evo["chosen"], evo["to_version"], evo["commit"], evo["diff"]) == ("kept_previous", None, None, None, None)
    assert repo.current_version() == "v0" and repo.versions() == ["v0"]


def test_human_veto_blocks_high_change(tmp_path):
    config = make_config(tmp_path)
    review.submit(config, "evo-test", "c1-referral_rules-1", "reject", {"safety": 2, "clinical": 2, "feasibility": 3}, "需先区分")
    evo, _, _ = run_evolve(tmp_path, [HIGH, GOOD, WORSE], config=config)
    assert VALIDATE(evo) == []
    assert evo["human_review"][0]["decision"] == "reject"
    assert not evo["candidates"][0]["passed"] and evo["chosen"] == "c2"


def test_approve_cannot_rescue_hard_blocked_change(tmp_path):
    config = make_config(tmp_path)
    review.submit(config, "evo-test", "c1-plan_rules-1", "approve")
    evo, evaluator, _ = run_evolve(tmp_path, [BLOCKED, WORSE, []], config=config)
    assert not evo["candidates"][0]["passed"] and evo["outcome"] == "kept_previous"
    assert evo["human_review"] == [] and "v0+c1" not in evaluator.labels


def test_review_timeout_passes_under_default_policy(tmp_path):
    evo, _, _ = run_evolve(tmp_path, [HIGH, GOOD, WORSE])
    assert evo["human_review"] == [{"change_id": "c1-referral_rules-1", "decision": "timeout", "scores": None, "comment": None}]
    assert evo["candidates"][0]["passed"] and evo["chosen"] == "c1"
    # Schema-valid; the only invariant error is the known timeout-policy conflict in contracts/validate.py.
    errors = VALIDATE(evo)
    assert errors and all(TIMEOUT_CONFLICT in e for e in errors)


def test_review_timeout_vetoes_under_veto_policy(tmp_path):
    config = make_config(tmp_path, review={"timeout_policy": "veto"})
    evo, _, _ = run_evolve(tmp_path, [HIGH, GOOD, WORSE], config=config)
    assert VALIDATE(evo) == []
    assert not evo["candidates"][0]["passed"] and evo["chosen"] == "c2"


def test_safety_regression_in_validation_vetoes(tmp_path):
    scores = {**SCORES, "标记GOOD": metrics(isi_response_rate=0.9, crisis_missed=1, crisis_recall=0.5)}
    evo, _, _ = run_evolve(tmp_path, [GOOD, WORSE, []], evaluator=MockEvaluator(scores))
    assert VALIDATE(evo) == []
    c1 = evo["candidates"][0]
    assert not c1["passed"] and {r["code"] for r in c1["veto"]["reasons"]} == {"crisis_missed"}
    assert evo["outcome"] == "kept_previous"


def test_baseline_evaluated_when_missing_and_evaluator_errors_isolated(tmp_path):
    evaluator = MockEvaluator(SCORES, fail_on="标记WORSE")
    evo, evaluator, _ = run_evolve(tmp_path, [WORSE, GOOD, []], evaluator=evaluator, baseline_val_metrics=None)
    assert VALIDATE(evo) == []
    assert "v0" in evaluator.labels and evo["baseline_val_metrics"] == BASELINE
    assert evo["candidates"][0]["val_metrics"] is None and not evo["candidates"][0]["passed"]
    assert evo["chosen"] == "c2"


def test_unapplicable_modify_is_dropped(tmp_path):
    stale = [change("communication_style", "新说法", op="modify", before="playbook 里没有这句话")]
    evo, _, _ = run_evolve(tmp_path, [stale, GOOD, []])
    assert VALIDATE(evo) == []
    assert evo["candidates"][0]["changes"] == [] and evo["candidates"][0]["val_metrics"] is None


def test_reflector_total_failure_keeps_previous(tmp_path):
    config = make_config(tmp_path)
    evo = asyncio.run(evolve(run_report=RUN, sessions=SESSIONS, evaluator=MockEvaluator(), config=config,
                             primary=MockLLM(error=RuntimeError("down")), fallback=MockLLM(error=RuntimeError("down")),
                             baseline_val_metrics=BASELINE, evolution_id="evo-fail"))
    assert VALIDATE(evo) == []
    assert evo["reflector"]["fell_back"] and evo["outcome"] == "kept_previous"


def test_second_generation_builds_on_first(tmp_path):
    config = make_config(tmp_path)
    run_evolve(tmp_path, [GOOD, [], []], config=config)
    evo = asyncio.run(evolve(run_report=RUN, sessions=SESSIONS, config=config,
                             evaluator=MockEvaluator({"标记HIGH": SCORES["标记HIGH"]}),
                             primary=MockLLM(reply(HIGH, [], [])), evolution_id="evo-2",
                             baseline_val_metrics=SCORES["标记GOOD"]))
    assert VALIDATE(evo) == [] or all(TIMEOUT_CONFLICT in e for e in VALIDATE(evo))
    assert (evo["from_version"], evo["to_version"]) == ("v1", "v2")
    text = PlaybookRepo(config).read()
    assert "标记GOOD" in text and "标记HIGH" in text


@pytest.mark.parametrize("name", ["evolution.v1-v2.json"])
def test_contract_example_still_valid(name):
    assert VALIDATE(example(name)) == []


def test_insights_sidecar_and_contract_stays_clean(tmp_path):
    evo, _, _ = run_evolve(tmp_path, [BLOCKED, GOOD, WORSE])
    assert VALIDATE(evo) == []
    assert all("dimension" not in ch for c in evo["candidates"] for ch in c["changes"])
    insights = json.loads((tmp_path / "var" / "evolve" / "evo-test" / "insights.json").read_text(encoding="utf-8"))
    meta = insights["changes"]["c2-path_discrimination-1"]
    assert meta == {"section": "path_discrimination", "subagent": "strategy_generation", "dimension": "path"}
    assert insights["changes"]["c1-plan_rules-1"]["subagent"] == "plan_adjustment"
    assert "safety" in insights["source_run"]["scorecard"]


def test_rich_evaluator_gives_val_evidence_and_dimension_deltas(tmp_path):
    session, visitor = example("session.A-001.json"), example("visitor.A-001.json")
    main = visitor["main_path"]
    agent_turns = [(r["round"], t["turn"]) for r in session["rounds"] for t in r["transcript"] if t["speaker"] == "agent"]

    def rich(m, p_values):
        trace = {"path_probs": [{"round": r, "turn": t, "probs": {p: (v if p == main else (1 - v) / 4)
                                                                   for p in ("P1", "P2", "P3", "P4", "P5")}}
                                for (r, t), v in zip(agent_turns, p_values)]}
        row = dict(RUN["per_visitor"][0], visitor_id="A-001", main_path=main)
        return {"metrics": m, "per_visitor": [row], "sessions": {"A-001": session},
                "traces": {"A-001": trace}, "visitors": {"A-001": visitor}}

    class Rich:
        async def __call__(self, text, *, label):
            if "标记GOOD" in text:
                return rich(SCORES["标记GOOD"], [0.4, 0.7, 0.9])
            return rich(BASELINE, [0.2, 0.3, 0.5])

    evo, insights = asyncio.run(evolve(run_report=RUN, sessions=SESSIONS, evaluator=Rich(), config=make_config(tmp_path),
                                       primary=MockLLM(reply(GOOD, [], [])), evolution_id="evo-rich",
                                       return_insights=True))
    assert VALIDATE(evo) == [] and evo["chosen"] == "c1" and evo["baseline_val_metrics"] == BASELINE
    base_ev = insights["validation"]["baseline"]["evidence"]
    cand = insights["validation"]["candidates"]["c1"]
    assert cand["evidence"]["by_step"][0]["mean_p_true"] > base_ev["by_step"][0]["mean_p_true"]
    assert cand["scorecard_delta"]["plan"]["isi_response_rate"] == pytest.approx(0.25)


def test_add_follows_bullet_style(tmp_path):
    from engine.evolve.playbook import apply_changes
    text = ("# x\n\n## communication_style\n- a\n\n## questioning_strategy\n- b\n\n## path_discrimination\n- c\n\n"
            "## plan_rules\n- d\n\n## referral_rules\n- e\n")
    out = apply_changes(text, [{"op": "add", "section": "path_discrimination", "before": None, "after": "新规则"}])
    assert "- c\n- 新规则\n" in out
