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
    assert (evo["outcome"], evo["chosen"], evo["from_version"], evo["to_version"]) == ("committed", "c2", "v1", "v2")
    c1, c2, c3 = evo["candidates"]
    assert c1["hard_rule_violations"] and c1["val_metrics"] is None and not c1["veto"]["passed"]
    assert c2["passed"] and not c3["passed"] and c3["veto"]["passed"]
    assert "v1+c1" not in evaluator.labels                       # blocked candidate never validated
    assert repo.current_version() == "v2" and "标记GOOD" in repo.read()
    assert evo["commit"]["sha"] == repo.head() and evo["commit"]["author"] == "deepsleep-agent"
    assert evo["diff"].startswith("--- a/playbook.md\n+++ b/playbook.md") and "+标记GOOD" in evo["diff"]
    assert evo["human_review"] == []                             # blocked high change is not offered for review
    saved = json.loads((tmp_path / "var" / "evolve" / "evo-test" / "evolution.json").read_text(encoding="utf-8"))
    assert saved == evo


def test_kept_previous_when_nothing_beats_baseline(tmp_path):
    evo, _, repo = run_evolve(tmp_path, [BLOCKED, WORSE, []])
    assert VALIDATE(evo) == []
    assert (evo["outcome"], evo["chosen"], evo["to_version"], evo["commit"], evo["diff"]) == ("kept_previous", None, None, None, None)
    assert repo.current_version() == "v1" and repo.versions() == ["v1"]


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
    assert evo["human_review"] == [] and "v1+c1" not in evaluator.labels


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
    assert "v1" in evaluator.labels and evo["baseline_val_metrics"] == BASELINE
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
    assert (evo["from_version"], evo["to_version"]) == ("v2", "v3")
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


# -- noise-aware gate, replicates, paired statistics, history ------------------------------------
TEMPLATE = RUN["per_visitor"][0]


def c_rows(n=10, responders=(), ref_pos=(), ref_hit=None):
    """Synthetic split-C rows; ``ref_hit`` defaults to every referral-positive visitor being caught."""
    ref_hit = ref_pos if ref_hit is None else ref_hit
    out = []
    for i in range(n):
        week = [20, 18, 16, 14, 10 if i in responders else 18]
        true = "R1" if i in ref_pos else "R0"
        out.append(dict(TEMPLATE, visitor_id=f"C-{i:03d}", isi_baseline=20, isi_week=week, isi_change=week[4] - 20,
                        responder=i in responders, referral_true=true,
                        referral_pred=true if i in ref_hit else "R0", failure_tags=[],
                        prefilled_scales=["isi", "stop_bang"], screened=[], crisis_true="none", crisis_pred="none"))
    return out


def rich_result(rows):
    from contracts.validate import compute_metrics
    return {"metrics": compute_metrics(rows), "per_visitor": rows, "sessions": {}, "traces": {}, "visitors": {}}


class RowsEvaluator:
    """Rich evaluator: ``table[marker]`` is a list of row sets, one per replicate (cycled)."""

    def __init__(self, table: dict[str, list[list[dict]]], default: list[list[dict]]):
        self.table, self.default, self.labels, self.calls = table, default, [], {}

    async def __call__(self, text, *, label):
        self.labels.append(label)
        key = next((m for m in self.table if m in text), None)
        sets = self.table[key] if key else self.default
        i = self.calls.get(key, 0)
        self.calls[key] = i + 1
        return rich_result(sets[i % len(sets)])


def test_replicates_pool_rows_and_paired_stats(tmp_path):
    from contracts.validate import compute_metrics
    config = make_config(tmp_path, gate={"replicates": 2})
    base_sets = [c_rows(responders={0, 1, 2}), c_rows(responders={0, 1})]
    good_sets = [c_rows(responders={0, 1, 2, 3, 4}), c_rows(responders={0, 1, 3, 4})]
    evaluator = RowsEvaluator({"标记GOOD": good_sets}, base_sets)
    evo, insights = asyncio.run(evolve(run_report=RUN, sessions=SESSIONS, evaluator=evaluator, config=config,
                                       primary=MockLLM(reply(GOOD, [], [])), evolution_id="evo-rep",
                                       return_insights=True))
    assert VALIDATE(evo) == []
    assert evaluator.labels == ["v1", "v1#r2", "v1+c1", "v1+c1#r2"]
    assert evo["baseline_val_metrics"] == compute_metrics(base_sets[0] + base_sets[1])
    assert evo["candidates"][0]["val_metrics"]["isi_response_rate"] == pytest.approx(9 / 20)
    assert evo["chosen"] == "c1"
    p = insights["validation"]["candidates"]["c1"]["paired"]["responder"]
    assert (p["gained"], p["lost"], p["net"]) == (["C-003", "C-004"], [], 2)
    assert p["sign_test_p"] == pytest.approx(0.5)
    assert insights["validation"]["replicates"] == 2 and insights["validation"]["gate_context"]["n_visitors"] == 10
    saved = json.loads((tmp_path / "var/evolve/evo-rep/insights.json").read_text(encoding="utf-8"))
    assert saved["validation"]["candidates"]["c1"]["paired"]["responder"]["net"] == 2


def test_replicates_without_rows_average_rates_and_sum_counts(tmp_path):
    from engine.evolve.pipeline import pool
    a = metrics(isi_response_rate=0.4, crisis_missed=0, contraindication_violations=1, referral_recall=None)
    b = metrics(isi_response_rate=0.6, crisis_missed=1, contraindication_violations=0, referral_recall=0.5)
    pooled = pool([a, b])
    assert pooled["isi_response_rate"] == pytest.approx(0.5) and pooled["referral_recall"] == 0.5
    assert (pooled["crisis_missed"], pooled["contraindication_violations"]) == (1, 1)
    assert pooled["path_acc_gain"] == pytest.approx(pooled["path_acc_r2"] - pooled["path_acc_r1"])


def test_candidate_failing_one_replicate_is_not_validated(tmp_path):
    config = make_config(tmp_path, gate={"replicates": 2})
    calls = []

    async def flaky(text, *, label):
        calls.append(label)
        if label == "v1+c1#r2":
            raise RuntimeError("replicate down")
        return rich_result(c_rows(responders={0, 1, 2, 3} if "标记GOOD" in text else {0}))

    evo = asyncio.run(evolve(run_report=RUN, sessions=SESSIONS, evaluator=flaky, config=config,
                             primary=MockLLM(reply(GOOD, [], [])), evolution_id="evo-flaky"))
    assert VALIDATE(evo) == [] and evo["candidates"][0]["val_metrics"] is None
    assert evo["outcome"] == "kept_previous"


def test_referral_tolerance_and_min_gain_through_pipeline(tmp_path):
    base = [c_rows(n=30, responders=set(range(15)), ref_pos=set(range(20, 30)))]
    # +1 responder but one referral-positive visitor missed.
    plus1_miss = [c_rows(n=30, responders=set(range(16)), ref_pos=set(range(20, 30)), ref_hit=set(range(21, 30)))]
    run = lambda **gate: asyncio.run(evolve(
        run_report=RUN, sessions=SESSIONS, evaluator=RowsEvaluator({"标记GOOD": plus1_miss}, base),
        config=make_config(tmp_path / str(len(gate)) / "_".join(map(str, gate.values())), gate=gate),
        primary=MockLLM(reply(GOOD, [], [])), evolution_id="evo-tol", return_insights=True))
    evo, insights = run()
    assert VALIDATE(evo) == [] and evo["chosen"] is None             # default: one visitor vetoes
    assert insights["history_item"]["candidates"][0]["reasons"] == ["转介召回率低于上一代。"]
    evo, insights = run(referral_recall_tolerance_visitors=1)
    assert VALIDATE(evo) == [] and evo["chosen"] == "c1"
    item = insights["history_item"]["candidates"][0]
    assert item["outcome"] == "adopted" and item["delta"]["isi_responders"] == 1
    assert item["delta"]["referral_recall"] == pytest.approx(-0.1)
    evo, insights = run(referral_recall_tolerance_visitors=1, min_primary_gain_visitors=2)
    assert VALIDATE(evo) == [] and evo["chosen"] is None
    assert insights["history_item"]["candidates"][0]["reasons"] == ["主指标提高不足 2 名来访"]


def test_history_item_outcomes_and_reasons(tmp_path):
    evo, _, _ = run_evolve(tmp_path, [BLOCKED, GOOD, WORSE])
    insights = json.loads((tmp_path / "var/evolve/evo-test/insights.json").read_text(encoding="utf-8"))
    item = insights["history_item"]
    assert (item["from_version"], item["to_version"]) == ("v1", "v2")
    c1, c2, c3 = item["candidates"]
    assert c1["outcome"] == "blocked" and c1["delta"] is None and c1["reasons"]
    assert c2["outcome"] == "adopted" and c2["reasons"] == []
    assert c3["outcome"] == "rejected" and c3["reasons"] == ["主指标未严格提高"]
    assert set(c2["changes"][0]) == {"op", "section", "before", "after"}
    assert set(c2["delta"]) == {"n", "isi_responders", "gained", "lost", "referral_recall", "referral_precision",
                                "path_acc_r2", "screening_coverage"}


def test_passed_but_not_chosen_reason(tmp_path):
    scores = {**SCORES, "标记WORSE": metrics(isi_response_rate=0.6)}
    run_evolve(tmp_path, [GOOD, WORSE, []], evaluator=MockEvaluator(scores))
    insights = json.loads((tmp_path / "var/evolve/evo-test/insights.json").read_text(encoding="utf-8"))
    c1, c2, c3 = insights["history_item"]["candidates"]
    assert c1["outcome"] == "adopted" and c2["reasons"] == ["通过但未被选中"] and c3["outcome"] == "empty"


def test_history_forwarded_when_reflector_accepts_it_and_audit_stored(tmp_path, monkeypatch):
    from engine.evolve import pipeline
    real, seen = pipeline.reflect, {}

    async def spy(*, history=None, **kwargs):
        seen["history"] = history
        result = await real(**kwargs)
        result.audit = {"loss_groups": {"g": ["C-001"]}}
        return result

    monkeypatch.setattr(pipeline, "reflect", spy)
    history = [{"generation": 1, "from_version": "v1", "to_version": "v2", "candidates": []}]
    evo, _, _ = run_evolve(tmp_path, [GOOD, [], []], history=history)
    assert seen["history"] == history and VALIDATE(evo) == []
    insights = json.loads((tmp_path / "var/evolve/evo-test/insights.json").read_text(encoding="utf-8"))
    assert insights["source_run"]["audit"] == {"loss_groups": {"g": ["C-001"]}}


def test_history_not_passed_to_old_reflector_signature(tmp_path, monkeypatch):
    from engine.evolve import pipeline
    real = pipeline.reflect

    async def old_reflect(*, playbook_text, version, run_report, sessions, feedback, config, primary, fallback,
                          primary_error=None, traces=None, visitors=None):
        kwargs = dict(playbook_text=playbook_text, version=version, run_report=run_report, sessions=sessions,
                      feedback=feedback, config=config, primary=primary, fallback=fallback,
                      primary_error=primary_error, traces=traces, visitors=visitors)
        return await real(**kwargs)

    monkeypatch.setattr(pipeline, "reflect", old_reflect)
    evo, _, _ = run_evolve(tmp_path, [GOOD, [], []], history=[{"generation": 1, "candidates": []}])
    assert VALIDATE(evo) == [] and evo["chosen"] == "c1"


def test_rich_baseline_result_is_reused_not_reevaluated(tmp_path):
    base = rich_result(c_rows(responders={0, 1}))
    evaluator = RowsEvaluator({"标记GOOD": [c_rows(responders={0, 1, 2})]}, [c_rows()])
    evo, insights = asyncio.run(evolve(run_report=RUN, sessions=SESSIONS, evaluator=evaluator,
                                       config=make_config(tmp_path), primary=MockLLM(reply(GOOD, [], [])),
                                       evolution_id="evo-reuse", baseline_val_result=base, return_insights=True))
    assert evaluator.labels == ["v1+c1"] and VALIDATE(evo) == []
    assert evo["baseline_val_metrics"] == base["metrics"]
    assert insights["validation"]["baseline_source"] == "reused"
    assert insights["validation"]["candidates"]["c1"]["paired"]["responder"]["gained"] == ["C-002"]
    status = json.loads((tmp_path / "var/evolve/evo-reuse/status.json").read_text(encoding="utf-8"))
    assert status["validation"]["baseline"] == "skipped"


def test_add_follows_bullet_style(tmp_path):
    from engine.evolve.playbook import apply_changes
    text = ("# x\n\n## communication_style\n- a\n\n## questioning_strategy\n- b\n\n## path_discrimination\n- c\n\n"
            "## plan_rules\n- d\n\n## referral_rules\n- e\n")
    out = apply_changes(text, [{"op": "add", "section": "path_discrimination", "before": None, "after": "新规则"}])
    assert "- c\n- 新规则\n" in out


THREE = [[change("communication_style", f"先确认第{i}个具体困扰。")] for i in range(3)]


class TimedEvaluator:
    """Records start/end events in order and the peak number of in-flight evaluations."""

    def __init__(self, events, delay=0.02):
        self.events, self.delay, self.active, self.peak = events, delay, 0, 0

    async def __call__(self, text, *, label):
        self.active += 1
        self.peak = max(self.peak, self.active)
        self.events.append(("start", label))
        await asyncio.sleep(self.delay)
        self.events.append(("end", label))
        self.active -= 1
        return dict(BASELINE)


def test_parallel_candidates_overlap_but_baseline_finishes_first(tmp_path):
    events = []
    evaluator = TimedEvaluator(events)
    config = make_config(tmp_path, gate={"parallel_candidates": True, "baseline_during_reflection": False})
    run_evolve(tmp_path, THREE, evaluator=evaluator, config=config, baseline_val_metrics=None)
    assert evaluator.peak >= 2
    base_end = events.index(("end", "v1"))
    starts = [i for i, (kind, label) in enumerate(events) if kind == "start" and label != "v1"]
    assert len(starts) == 3 and all(i > base_end for i in starts)
    assert set(starts) == {i for i, (k, _) in enumerate(events) if k == "start" and i > base_end}
    assert sorted(label for kind, label in events if kind == "start") == ["v1", "v1+c1", "v1+c2", "v1+c3"]


def test_sequential_candidates_never_overlap_when_parallel_off(tmp_path):
    evaluator = TimedEvaluator([])
    config = make_config(tmp_path, gate={"parallel_candidates": False})
    run_evolve(tmp_path, THREE, evaluator=evaluator, config=config, baseline_val_metrics=None)
    assert evaluator.peak == 1


class RecordingLLM(MockLLM):
    def __init__(self, events, reply_, delay):
        super().__init__(reply_, model="mock-model", delay=delay)
        self.events = events

    async def complete(self, system, user):
        self.events.append(("reflector", "start"))
        out = await super().complete(system, user)
        self.events.append(("reflector", "return"))
        return out


def test_baseline_starts_before_reflector_returns_when_during_reflection(tmp_path):
    events = []
    evaluator = TimedEvaluator(events, delay=0.001)
    config = make_config(tmp_path, gate={"baseline_during_reflection": True})
    asyncio.run(evolve(run_report=RUN, sessions=SESSIONS, evaluator=evaluator, config=config,
                       primary=RecordingLLM(events, reply(*THREE), delay=0.1), evolution_id="evo-during"))
    assert events.index(("start", "v1")) < events.index(("reflector", "return"))
    assert events.index(("start", "v1+c1")) > events.index(("reflector", "return"))


def test_baseline_waits_for_reflector_when_during_reflection_off(tmp_path):
    events = []
    evaluator = TimedEvaluator(events, delay=0.001)
    config = make_config(tmp_path, gate={"baseline_during_reflection": False})
    asyncio.run(evolve(run_report=RUN, sessions=SESSIONS, evaluator=evaluator, config=config,
                       primary=RecordingLLM(events, reply(*THREE), delay=0.05), evolution_id="evo-after"))
    assert events.index(("start", "v1")) > events.index(("reflector", "return"))


def test_baseline_replicates_exceed_candidate_replicates(tmp_path):
    evaluator = MockEvaluator()
    config = make_config(tmp_path, gate={"baseline_replicates": 3, "replicates": 1})
    run_evolve(tmp_path, THREE, evaluator=evaluator, config=config, baseline_val_metrics=None)
    stems = [label.split("#")[0] for label in evaluator.labels]
    assert stems.count("v1") == 3 and len(evaluator.labels) == 6
    for cid in ("v1+c1", "v1+c2", "v1+c3"):
        assert stems.count(cid) == 1
