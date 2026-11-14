"""Engine session loop: safety branches, loop-1 sub-agents, loop 2, caps, vetoes, concurrency (offline)."""
import asyncio
import copy
import json
import time

import pytest

from contracts.validate import load_validators, validate_document
from engine.classifier import uniform_state
from engine.config import load_config
from engine.interfaces import VisitorReply
from engine.mock_agent import MockAgentLLM
from engine.playbook import SECTIONS, load_playbook, parse_sections
from engine.run import build_deps, load_visitors, run_batch
from engine.session import SessionRunner
from engine.stubs import IndexScreening, MockVisitorSim, StubOutcomeModel, phq9_items
from safety.judges import JudgeResult
from safety.layer import SafetyLayer

from conftest import ROOT

VALIDATORS = load_validators()
EXAMPLES = ROOT / "contracts/examples"
CAPS = load_config()["round_turn_cap"]
VERIFY = "我想确认一下，现在你还有这种念头吗？"
HISTORY_TEXT = "大学时有过希望睡去不再醒来的念头，但已经很多年没有了。"
PASSIVE_TEXT = "有时候真想一觉睡过去别醒了。"
ACTIVE_TEXT = "我已经想好用什么方法了。"
SAY = {"action": "say", "text": "能多说说你的睡眠吗？"}


def visitor(vid="A-001"):
    return copy.deepcopy(json.loads((EXAMPLES / f"visitor.{vid}.json").read_text(encoding="utf-8")))


def assert_valid(session, v):
    errors = validate_document(session, "session", VALIDATORS, {v["id"]: v})
    assert errors == [], errors


class StubJudge:
    provider = "stub"

    def __init__(self, labels=None, fail=False):
        self.labels = labels or {}
        self.fail = fail
        self.calls = []

    async def classify(self, text):
        self.calls.append(text)
        if self.fail:
            raise RuntimeError("judge down")
        label = next((lab for key, lab in self.labels.items() if key in text), "none")
        return JudgeResult({k: float(k == label) for k in ("none", "history", "passive", "active")}, "ok", "stub", 1.0)


DEFAULT_LABELS = {"很多年没有了": "history", "别醒了": "passive", "想好用什么方法": "active"}


class ScriptedSim:
    model_name = "scripted-visitor"

    def __init__(self, replies):
        self.replies = list(replies)
        self.memories = []

    async def reply(self, visitor, round, transcript, memory):
        self.memories.append(dict(memory))
        return VisitorReply(self.replies.pop(0) if self.replies else "嗯，还好。", [], None)


class ScriptedLLM:
    """policy(state, messages) -> {"action": say|tool|end_round, "text"?, "tool"?} drives strategy + response
    (and the merged turn); memory / plan / select default to the mock policy unless overridden."""
    model_name = "scripted-agent"

    def __init__(self, policy=None, *, response=None, plan=None, delay=0.0):
        self.policy = policy or (lambda state, messages: SAY)
        self.response = response
        self.plan = plan
        self.delay = delay
        self.calls = []
        self.inflight = self.max_inflight = 0
        self.mock = MockAgentLLM()

    async def complete_json(self, messages, *, task, state):
        self.inflight += 1
        self.max_inflight = max(self.max_inflight, self.inflight)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            self.calls.append((task, messages, state))
            if task in ("strategy", "turn"):
                decision = dict(self.policy(state, messages))
                kind = "verify_safety" if state["history_check_required"] else "explore"
                out = {"action": decision["action"], "strategy": {"type": kind, "intent": decision.get("text", "")}}
                if decision["action"] == "tool":
                    out["tool"] = decision["tool"]
                if task == "turn" and decision["action"] == "say":
                    out.update(text=decision["text"], acts=[])
                return out
            if task == "response":
                if self.response:
                    return self.response(state, messages)
                return {"text": state["strategy"]["intent"], "acts": ["reflection"]}
            if task == "plan" and self.plan:
                return self.plan(state, messages)
            return await self.mock.complete_json(messages, task=task, state=state)
        finally:
            self.inflight -= 1

    def tasks(self):
        return [task for task, _, _ in self.calls]


def deps_for(*, llm=None, sim=None, judge=None, classifier=None, outcome=None, merged=False):
    config = {"agent_llm": {"provider": "mock"}, "path_classifier": {"provider": "mock"},
              "pipeline": {"merge_strategy_response": merged}}
    return build_deps(config=config, llm=llm or ScriptedLLM(), sim=sim or ScriptedSim([]),
                      classifier=classifier, screening=IndexScreening(), outcome=outcome,
                      safety=SafetyLayer({"judge_provider": "mock"}, judge=judge or StubJudge(DEFAULT_LABELS)))


def run(deps, v, run_id="test-run"):
    return asyncio.run(SessionRunner(deps, v, run_id).run())


def turns(session, rnd=1):
    return [(t["speaker"], t["text"]) for t in session["rounds"][rnd - 1]["transcript"]]


def agent_count(session, rnd):
    return sum(1 for s, _ in turns(session, rnd) if s == "agent")


# ------------------------------------------------------------------ none / structure

@pytest.mark.parametrize("merged", [False, True])
def test_none_completes_two_rounds_and_is_contract_valid(merged):
    v = visitor()
    llm = ScriptedLLM()
    session, trace = run(deps_for(llm=llm, merged=merged), v)
    assert session["status"] == "completed" and len(session["rounds"]) == 2
    assert session["safety_events"] == [] and session["plan"] is not None
    assert agent_count(session, 1) == CAPS[1] + 1 and agent_count(session, 2) == CAPS[2] + 1  # + closing messages
    tasks = set(llm.tasks())
    assert tasks == ({"turn", "memory", "plan", "select"} if merged
                     else {"strategy", "response", "memory", "plan", "select"})
    assert trace["pipeline"] == ("merged" if merged else "split")
    assert set(trace["latency_ms"]) >= {"classifier", "memory", "plan", "select"}
    assert_valid(session, v)


def test_path_pred_is_argmax_of_final_classifier_weights_and_probs_are_traced():
    v = visitor()
    sim = ScriptedSim(["最近睡不好。", "一躺下脑子就反复想，担心明天。"])
    session, trace = run(deps_for(sim=sim), v)
    finals = [row for row in trace["path_probs"] if row["final"]]
    assert [row["round"] for row in finals] == [1, 2]
    for rnd, row in zip(session["rounds"], finals):
        top = max(row["weights"], key=row["weights"].get)
        assert rnd["path_pred"] == top == "P3"
        assert rnd["path_confidence"] == pytest.approx(row["weights"][top], abs=1e-4)
        assert set(row) >= {"weights", "attitude", "uncertainty", "margin", "status", "provider", "latency_ms"}
    per_turn = [row for row in trace["path_probs"] if not row["final"]]
    assert len(per_turn) == CAPS[1] + CAPS[2]  # one classification per committed agent action
    assert per_turn[0]["turn"] == 1 and per_turn[0]["uncertainty"] == 1.0


def test_subagents_read_only_their_playbook_sections():
    llm = ScriptedLLM()
    run(deps_for(llm=llm), visitor())
    system = {task: messages[0]["content"] for task, messages, _ in llm.calls}
    assert "## questioning_strategy" in system["strategy"] and "## path_discrimination" in system["strategy"]
    assert "## plan_rules" not in system["strategy"]
    assert "## communication_style" in system["response"] and "## path_discrimination" not in system["response"]
    assert "## referral_rules" in system["memory"] and "## plan_rules" not in system["memory"]
    assert "## plan_rules" in system["plan"] and "## plan_rules" in system["select"]
    strategy_user = next(m[-1]["content"] for t, m, _ in llm.calls if t == "strategy")
    assert "路径分类器：" in strategy_user and "uncertainty" in strategy_user


def test_resistant_visitor_gets_supportive_step_then_revisit():
    v = visitor()  # A-001: sleep_elsewhere clue is deny_first, defensiveness mid
    deps = build_deps(config={"agent_llm": {"provider": "mock"}, "path_classifier": {"provider": "mock"}},
                      safety=SafetyLayer({"judge_provider": "mock"}))
    session, trace = run(deps, v)
    kinds = [(s["type"], s.get("target_topic")) for s in trace["strategies"]]
    first = kinds.index(("explore", "sleep_elsewhere"))
    assert kinds[first + 1][0] == "supportive" and kinds[first + 2] == ("revisit", "sleep_elsewhere")
    revealed = [cid for r in session["rounds"] for t in r["transcript"] for cid in t["revealed_clue_ids"]]
    assert "A-001-c3" in revealed
    assert_valid(session, v)


def test_classifier_failure_falls_back_to_uniform_and_continues():
    class Down:
        provider = "down"

        async def classify(self, dialogue):
            return uniform_state("error", "down", 1.0)

    session, trace = run(deps_for(classifier=Down()), visitor())
    assert session["status"] == "completed"
    assert all(row["status"] == "error" and row["uncertainty"] == 1.0 for row in trace["path_probs"])
    assert session["rounds"][0]["path_pred"] == "P1"  # deterministic tie-break on uniform weights


# ------------------------------------------------------------------ loop 2

def test_round2_evaluates_round1_plan_and_selects():
    v = visitor()

    class Outcome:
        def __init__(self):
            self.seen = []

        def simulate(self, visitor, plan, context):
            self.seen.append((plan, context))
            return {"isi_week": [19, 17, 15, 13, 11], "isi_change": -8, "adherence": 0.9, "responder": True}

    outcome = Outcome()
    llm = ScriptedLLM()
    sim = ScriptedSim([])
    session, trace = run(deps_for(llm=llm, sim=sim, outcome=outcome), v)
    plan1 = trace["plans"]["1"]["plan"]
    assert outcome.seen[0][0] == plan1
    assert len(outcome.seen[0][1]["session"]["rounds"]) >= 1
    assert trace["round1_outcome"]["isi_change"] == -8 and trace["selection"]["decision"] == "maintain"
    strategy_r2 = next(m[-1]["content"] for t, m, s in llm.calls if t == "strategy" and s["round"] == 2)
    assert "第 1 轮处方 4 周模拟结果" in strategy_r2 and "第 2 轮方案决定" in strategy_r2 and "第 1 轮记忆" in strategy_r2
    plan_r2 = [m[-1]["content"] for t, m, s in llm.calls if t == "plan"][-1]
    assert "第 2 轮方案决定" in plan_r2
    assert any("round1_outcome" in m for m in sim.memories)
    assert session["plan"] == trace["plans"]["2"]["plan"]
    assert_valid(session, v)


def test_invalid_outcome_model_output_yields_error_session():
    class Broken:
        def simulate(self, visitor, plan, context):
            return {"isi_week": [1, 2]}

    session, _ = run(deps_for(outcome=Broken()), visitor())
    assert session["status"] == "error" and "isi_week" in session["error"]
    assert_valid(session, visitor())


def test_stub_outcome_rewards_on_target_plans():
    v = visitor()  # main path P2
    on = StubOutcomeModel().simulate(v, {"components": ["stimulus_control"]}, {})
    off = StubOutcomeModel().simulate(v, {"components": ["digital_curfew"]}, {})
    assert on["isi_change"] < off["isi_change"] and len(on["isi_week"]) == 5


# ------------------------------------------------------------------ history_check

def history_llm(verify: bool):
    def policy(state, messages):
        instructed = "【安全层指令】" in messages[-1]["content"]
        assert instructed == state["history_check_required"]
        if instructed:
            return {"action": "say", "text": VERIFY if verify else "那你平时几点起床？"}
        return SAY
    return ScriptedLLM(policy)


def test_history_verified_by_agent_needs_no_script():
    v = visitor()
    sim = ScriptedSim(["最近睡不好。", HISTORY_TEXT, "现在没有了。"])
    llm = history_llm(True)
    session, trace = run(deps_for(llm=llm, sim=sim), v)
    assert [(e["action"], e["level"], e["turn"]) for e in session["safety_events"]] == [("history_check", "none", 3)]
    t = turns(session, 1)
    assert t[3] == ("agent", VERIFY) and t[4][0] == "visitor"
    assert all(s != "safety" for s, _ in t)
    assert trace["history_checks"] == [{"round": 1, "turn": 4, "verified_by_agent": True}]
    response_msgs = [m[-1]["content"] for task, m, s in llm.calls if task == "response" and s["history_check_required"]]
    assert response_msgs and "【安全层指令】" in response_msgs[0]  # injected into both sub-agents
    assert_valid(session, v)


def test_history_not_verified_inserts_fixed_script_once():
    v = visitor()
    script = SafetyLayer({"judge_provider": "mock"}).script_for("history_check")
    sim = ScriptedSim(["最近睡不好。", HISTORY_TEXT, "现在没有了。", HISTORY_TEXT])
    session, trace = run(deps_for(llm=history_llm(False), sim=sim), v)
    t = turns(session, 1)
    assert t[3] == ("agent", "那你平时几点起床？") and t[4] == ("safety", script) and t[5][0] == "visitor"
    assert [s for s, _ in t].count("safety") == 1
    assert trace["history_checks"][0]["verified_by_agent"] is False
    assert_valid(session, v)


def test_history_on_last_visitor_turn_is_flushed_before_round_ends():
    v = visitor()
    sim = ScriptedSim(["最近睡不好。"] + ["嗯。"] * (CAPS[1] - 1) + [HISTORY_TEXT, "现在没有了。"])
    session, trace = run(deps_for(sim=sim), v)
    t = turns(session, 1)
    i = t.index(("visitor", HISTORY_TEXT))
    assert t[i + 1][0] == "safety" and t[i + 2] == ("visitor", "现在没有了。") and t[i + 3][0] == "agent"
    assert trace["history_checks"][-1]["at_round_end"] is True
    assert_valid(session, v)


def test_history_pending_survives_tool_call_until_next_message():
    v = visitor()
    seq = iter([{"action": "tool", "tool": "screen_osa"}])

    def policy(state, messages):
        if state["history_check_required"]:
            return next(seq, None) or {"action": "say", "text": VERIFY}
        return SAY

    session, trace = run(deps_for(llm=ScriptedLLM(policy), sim=ScriptedSim(["最近睡不好。", HISTORY_TEXT])), v)
    assert session["tool_calls"][0]["turn"] == 4
    assert turns(session, 1)[3] == ("agent", VERIFY)
    assert trace["history_checks"][0]["verified_by_agent"] is True
    assert_valid(session, v)


# ------------------------------------------------------------------ passive / active

def test_passive_inserts_safety_check_and_discards_speculation():
    v = visitor("A-003")
    script = SafetyLayer({"judge_provider": "mock"}).script_for("safety_check")
    llm = ScriptedLLM()
    session, trace = run(deps_for(llm=llm, sim=ScriptedSim(["最近很累。", PASSIVE_TEXT, "没有具体计划。", PASSIVE_TEXT])), v)
    t = turns(session, 1)
    assert t[2] == ("visitor", PASSIVE_TEXT) and t[3] == ("safety", script) and t[4] == ("visitor", "没有具体计划。")
    assert [s for s, _ in t].count("safety") == 1
    assert [e["action"] for e in session["safety_events"]] == ["safety_check"]
    assert session["rounds"][0]["crisis_level"] == "passive" and len(trace["ignored_events"]) == 1
    assert trace["speculation"]["discarded"] >= 1
    committed = [row["turn"] for row in trace["path_probs"] if not row["final"] and row["round"] == 1]
    assert 3 not in committed and 5 in committed  # step after the passive line used the post-script transcript
    assert_valid(session, v)


def test_active_runs_crisis_protocol_and_exits():
    v = visitor("A-003")
    script = SafetyLayer({"judge_provider": "mock"}).script_for("crisis_protocol")
    session, trace = run(deps_for(sim=ScriptedSim(["最近很累。", ACTIVE_TEXT])), v)
    assert session["status"] == "crisis_exit" and session["plan"] is None and len(session["rounds"]) == 1
    assert turns(session, 1)[-1] == ("safety", script)
    assert session["rounds"][0]["crisis_level"] == "active"
    assert trace["plans"] == {}  # no plan, no closing message after a crisis
    assert_valid(session, v)


def test_active_after_safety_check_answer():
    v = visitor("A-003")
    session, _ = run(deps_for(sim=ScriptedSim(["最近很累。", PASSIVE_TEXT, ACTIVE_TEXT])), v)
    assert [e["action"] for e in session["safety_events"]] == ["safety_check", "crisis_protocol"]
    assert session["status"] == "crisis_exit"
    assert_valid(session, v)


def test_active_in_reply_to_round1_closing_message():
    v = visitor()
    sim = ScriptedSim(["最近睡不好。"] + ["嗯。"] * CAPS[1] + [ACTIVE_TEXT])
    session, _ = run(deps_for(sim=sim), v)
    assert session["status"] == "crisis_exit" and len(session["rounds"]) == 1
    assert [s for s, _ in turns(session, 1)][-3:] == ["agent", "visitor", "safety"]
    assert_valid(session, v)


def test_active_in_opening_statement():
    v = visitor()
    session, _ = run(deps_for(sim=ScriptedSim([ACTIVE_TEXT])), v)
    assert session["status"] == "crisis_exit"
    assert [s for s, _ in turns(session, 1)] == ["visitor", "safety"]
    assert_valid(session, v)


# ------------------------------------------------------------------ judge failure

def test_judge_failure_without_rule_hit_continues_and_counts():
    judge = StubJudge(fail=True)
    session, trace = run(deps_for(judge=judge), visitor())
    assert session["status"] == "completed" and session["safety_events"] == []
    assert trace["judge_failures"] == len(judge.calls) > 0
    assert_valid(session, visitor())


def test_judge_failure_with_ambiguous_rule_falls_back_to_passive():
    ambiguous = "我不想活了"
    assert SafetyLayer({"judge_provider": "mock"}).rules.match(ambiguous).tier == "ambiguous"
    session, _ = run(deps_for(judge=StubJudge(fail=True), sim=ScriptedSim(["最近睡不好。", ambiguous])), visitor())
    event = session["safety_events"][0]
    assert (event["level"], event["source"], event["action"], event["judge_status"]) == \
        ("passive", "rule_ambiguous", "safety_check", "error")
    assert_valid(session, visitor())


# ------------------------------------------------------------------ scales, tools, caps

def test_prefilled_item9_triggers_safety_check_at_turn_zero():
    v = visitor("A-003")
    v["prefilled"] = [{"scale": "phq9", "reported_score": 7, "items": [1, 1, 1, 1, 1, 1, 0, 0, 1]}]
    session, _ = run(deps_for(), v)
    event = session["safety_events"][0]
    assert (event["round"], event["turn"], event["source"], event["action"]) == (1, 0, "scale_item9", "safety_check")
    assert [s for s, _ in turns(session, 1)][:3] == ["visitor", "safety", "visitor"]
    assert_valid(session, v)


def test_screen_mood_counts_as_turn_and_item9_is_assessed():
    v = visitor("A-003")  # true PHQ-9 item 9 = 1
    calls = iter([{"action": "tool", "tool": "screen_mood"}])
    session, _ = run(deps_for(llm=ScriptedLLM(lambda s, m: next(calls, SAY))), v)
    call = session["tool_calls"][0]
    assert (call["round"], call["turn"], call["tool"]) == (1, 2, "screen_mood")
    assert call["result"]["phq9_items"][8] == 1 and sum(call["result"]["phq9_items"]) == v["indices"]["phq9"]
    event = session["safety_events"][0]
    assert (event["turn"], event["source"]) == (2, "scale_item9")
    assert turns(session, 1)[1][0] == "safety"
    assert (agent_count(session, 1) - 1) + 1 == CAPS[1]  # agent lines minus closing, plus the tool call
    assert_valid(session, v)


def test_turn_cap_holds_when_agent_only_calls_tools():
    v = visitor("A-002")
    session, _ = run(deps_for(llm=ScriptedLLM(lambda s, m: {"action": "tool", "tool": "screen_osa"})), v)
    assert [sum(1 for c in session["tool_calls"] if c["round"] == r) for r in (1, 2)] == [CAPS[1], CAPS[2]]
    assert_valid(session, v)


def test_end_round_stops_early():
    v = visitor()
    session, _ = run(deps_for(llm=ScriptedLLM(lambda s, m: {"action": "end_round"})), v)
    assert [s for s, _ in turns(session, 1)] == ["visitor", "agent", "visitor"]
    assert [s for s, _ in turns(session, 2)] == ["agent", "visitor"]
    assert_valid(session, v)


def test_phq9_items_split():
    assert phq9_items(14, 1) == [2, 2, 2, 2, 2, 1, 1, 1, 1]
    assert sum(phq9_items(27, 3)) == 27 and phq9_items(0, 0) == [0] * 9
    with pytest.raises(ValueError):
        phq9_items(2, 3)


# ------------------------------------------------------------------ vetoes and failures

def test_plan_veto_rewrite_then_remediation():
    v = visitor()

    def bad_plan(state, messages):
        plan = MockAgentLLM()._plan(state)
        plan["plan"].update(components=["sleep_restriction"], tib_minutes=300, bedtime="02:00")
        return plan

    llm = ScriptedLLM(plan=bad_plan)
    session, trace = run(deps_for(llm=llm), v)
    plan = session["plan"]
    assert "sleep_restriction" not in plan["components"] and plan["components"]
    assert plan["tib_minutes"] == 330 and plan["bedtime"] == "01:30"
    plan_msgs = [m[-1]["content"] for t, m, _ in llm.calls if t == "plan"]
    assert len(plan_msgs) == 4 and "未通过固定规则检查" in plan_msgs[1]  # two rounds x (draft + rewrite)
    assert [e["violations"] for e in trace["vetoes"] if e["stage"] == "plan_remediated"] == [[], []]
    assert_valid(session, v)


@pytest.mark.parametrize("merged", [False, True])
def test_forbidden_wording_in_agent_message_is_rewritten(merged):
    v = visitor()

    def policy(state, messages):
        if "未通过固定规则检查" in messages[-1]["content"]:
            return {"action": "say", "text": "听起来睡眠困扰你挺久了。"}
        return {"action": "say", "text": "你这是失眠症。"}

    def response(state, messages):
        return {"text": policy(state, messages)["text"], "acts": []}

    session, trace = run(deps_for(llm=ScriptedLLM(policy, response=response), merged=merged), v)
    assert "你这是失眠症。" not in [t for s, t in turns(session, 1) if s == "agent"]
    assert any(entry["stage"] == "turn" for entry in trace["vetoes"])
    assert_valid(session, v)


def test_invalid_agent_output_is_retried():
    state = {"n": 0}

    def policy(s, m):
        state["n"] += 1
        return {"action": "dance"} if state["n"] == 1 else SAY

    session, trace = run(deps_for(llm=ScriptedLLM(policy)), visitor())
    assert session["status"] == "completed" and any(not c["ok"] for c in trace["llm_calls"])


def test_persistent_llm_failure_yields_valid_error_session():
    session, _ = run(deps_for(llm=ScriptedLLM(lambda s, m: {"action": "dance"})), visitor())
    assert session["status"] == "error" and "strategy failed" in session["error"] and session["plan"] is None
    assert_valid(session, visitor())


# ------------------------------------------------------------------ concurrency and mock end to end

def test_batch_runs_concurrently_within_limit():
    base = visitor()
    visitors = []
    for i in range(50):
        v = copy.deepcopy(base)
        v["id"] = f"A-{i + 1:03d}"
        v["clues"] = [dict(c, id=f"{v['id']}-c{j}") for j, c in enumerate(base["clues"])]
        visitors.append(v)
    llm = ScriptedLLM(delay=0.01)
    deps = deps_for(llm=llm, sim=MockVisitorSim())
    started = time.perf_counter()
    results = asyncio.run(run_batch(visitors, deps, "conc-run", max_sessions=20))
    elapsed = time.perf_counter() - started
    sequential = len(llm.calls) * 0.01
    assert elapsed < sequential / 4
    assert llm.max_inflight <= 20  # at most one agent request per session at a time
    assert [s["visitor_id"] for s, _ in results] == [v["id"] for v in visitors]
    for (session, _), v in zip(results, visitors):
        assert session["status"] == "completed"
        assert_valid(session, v)


@pytest.mark.parametrize("merged", [False, True])
def test_mock_end_to_end_on_contract_examples(merged):
    visitors = load_visitors([EXAMPLES])
    assert {v["id"] for v in visitors} == {"A-001", "A-002", "A-003"}
    deps = build_deps(config={"agent_llm": {"provider": "mock"}, "path_classifier": {"provider": "mock"},
                              "pipeline": {"merge_strategy_response": merged}},
                      safety=SafetyLayer({"judge_provider": "mock"}))
    results = asyncio.run(run_batch(visitors, deps, "mock-run"))
    by_id = {s["visitor_id"]: s for s, _ in results}
    for v in visitors:
        assert_valid(by_id[v["id"]], v)
    assert any(c["tool"] == "screen_osa" for c in by_id["A-002"]["tool_calls"])
    assert by_id["A-002"]["rounds"][-1]["referral_pred"] == "R1"
    assert by_id["A-002"]["rounds"][-1]["path_pred"] == "P4"
    assert by_id["A-003"]["safety_events"][0]["source"] == "scale_item9"


# ------------------------------------------------------------------ playbook and config

def test_playbook_v0_sections_match_contract():
    playbook = load_playbook(load_config()["playbook_path"])
    assert list(playbook.sections) == list(SECTIONS)
    assert "screen_mood" in playbook.sections["questioning_strategy"]
    with pytest.raises(ValueError):
        parse_sections("## communication_style\nx\n## plan_rules\ny\n")


def test_config_validation():
    with pytest.raises(ValueError):
        load_config({"round_turn_cap": {1: 0, 2: 3}})
    with pytest.raises(ValueError):
        load_config({"path_classifier": {"provider": "gpt"}})
    assert load_config()["concurrency"]["max_sessions"] <= 50


def test_missing_keys_fall_back_to_mock():
    deps = build_deps(safety=SafetyLayer({"judge_provider": "mock"}))
    assert deps.llm.model_name == "mock(fallback)" and deps.classifier.provider == "mock(fallback)"


@pytest.mark.xfail(strict=True, reason="contract conflict (reported): repeated passive via screen_mood item 9 has "
                   "action none, which session.safety_events forbids, yet validate.py requires a scale_item9 event")
def test_repeated_passive_then_item9_contract_conflict():
    v = visitor("A-003")
    calls = iter([SAY, {"action": "tool", "tool": "screen_mood"}])
    llm = ScriptedLLM(lambda s, m: next(calls, SAY))
    session, trace = run(deps_for(llm=llm, sim=ScriptedSim(["最近很累。", PASSIVE_TEXT, "没有计划。"])), v)
    assert trace["ignored_events"][0]["source"] == "scale_item9"
    assert_valid(session, v)


def test_locked_lines_marked_and_hidden_from_agents():
    from engine.playbook import locked_lines
    text = load_playbook(load_config()["playbook_path"]).text
    locked = locked_lines(text)
    assert any("330" in line for line in locked) and any("禁忌" in line for line in locked)
    llm = ScriptedLLM()
    run(deps_for(llm=llm), visitor())
    assert all("locked" not in m[0]["content"] for _, m, _ in llm.calls)


def test_trace_fixtures_match_documented_path_probs_shape():
    keys = {"round", "final", "weights", "attitude", "uncertainty", "margin", "status", "provider", "latency_ms"}
    files = sorted((ROOT / "engine/fixtures/trace").glob("*.json"))
    assert len(files) >= 2
    for file in files:
        trace = json.loads(file.read_text(encoding="utf-8"))
        assert trace["path_probs"] and all(keys <= set(row) for row in trace["path_probs"])
        assert all(("turn" in row) != row["final"] for row in trace["path_probs"])
        assert set(trace["path_probs"][0]["weights"]) == {"P1", "P2", "P3", "P4", "P5"}
        session = json.loads((ROOT / "engine/fixtures/sessions" / file.name).read_text(encoding="utf-8"))
        assert [r for r in trace["path_probs"] if r["final"]][-1]["weights"]
        assert session["visitor_id"] == trace["visitor_id"]
