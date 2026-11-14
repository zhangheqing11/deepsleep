"""Engine session loop: safety integration branches, caps, vetoes, concurrency (offline)."""
import asyncio
import copy
import json
import time

import pytest

from contracts.validate import load_validators, validate_document
from engine.config import load_config
from engine.interfaces import VisitorReply
from engine.llm import MockAgentLLM
from engine.playbook import SECTIONS, load_playbook, parse_sections
from engine.run import build_deps, load_visitors, run_batch
from engine.session import SessionRunner
from engine.stubs import IndexScreening, MockVisitorSim, phq9_items
from safety.judges import JudgeResult
from safety.layer import SafetyLayer

from conftest import ROOT

VALIDATORS = load_validators()
EXAMPLES = ROOT / "contracts/examples"
VERIFY = "我想确认一下，现在你还有这种念头吗？"
HISTORY_TEXT = "大学时有过希望睡去不再醒来的念头，但已经很多年没有了。"
PASSIVE_TEXT = "有时候真想一觉睡过去别醒了。"
ACTIVE_TEXT = "我已经想好用什么方法了。"


def visitor(vid="A-001", **changes):
    data = json.loads((EXAMPLES / f"visitor.{vid}.json").read_text(encoding="utf-8"))
    data = copy.deepcopy(data)
    data.update(changes)
    return data


def assert_valid(session, v):
    errors = validate_document(session, "session", VALIDATORS, {v["id"]: v})
    assert errors == [], errors


class StubJudge:
    """Label by substring; 'raise' simulates a provider failure."""
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
    """Visitor replies from a list; falls back to a neutral answer."""
    model_name = "scripted-visitor"

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    async def reply(self, visitor, round, transcript, memory):
        self.prompts.append(transcript[-1]["text"] if transcript else None)
        text = self.replies.pop(0) if self.replies else "嗯，还好。"
        return VisitorReply(text, [], None)


class ScriptedLLM:
    """turn policy: callable(state, messages) -> dict; assess/plan have defaults."""
    model_name = "scripted-agent"

    def __init__(self, turn=None, plan=None, delay=0.0):
        self.turn = turn or (lambda state, messages: {"action": "say", "text": "能多说说你的睡眠吗？", "acts": []})
        self.plan = plan
        self.delay = delay
        self.calls = []
        self.inflight = 0
        self.max_inflight = 0

    async def complete_json(self, messages, *, task, state):
        self.inflight += 1
        self.max_inflight = max(self.max_inflight, self.inflight)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            self.calls.append((task, messages[-1]["content"], state))
            if task == "turn":
                return self.turn(state, messages)
            if task == "assess":
                return {"path": "P2", "confidence": 0.6, "referral": "R0"}
            if self.plan:
                return self.plan(state, messages)
            return MockAgentLLM()._plan(state)
        finally:
            self.inflight -= 1


def deps_for(*, llm=None, sim=None, judge=None, config=None):
    return build_deps(config=config or {"agent_llm": {"provider": "mock"}}, llm=llm or ScriptedLLM(),
                      sim=sim or ScriptedSim([]), screening=IndexScreening(),
                      safety=SafetyLayer({"judge_provider": "mock"}, judge=judge or StubJudge(DEFAULT_LABELS)))


def run(deps, v, run_id="test-run"):
    return asyncio.run(SessionRunner(deps, v, run_id).run())


def turns(session, rnd=1):
    return [(t["speaker"], t["text"]) for t in session["rounds"][rnd - 1]["transcript"]]


# ------------------------------------------------------------------ none

def test_none_completes_two_rounds_and_is_contract_valid():
    v = visitor()
    session, trace = run(deps_for(), v)
    assert session["status"] == "completed" and len(session["rounds"]) == 2
    assert session["safety_events"] == [] and session["plan"] is not None
    cap = load_config()["round_turn_cap"]
    assert sum(1 for s, _ in turns(session, 1) if s == "agent") == cap[1]
    assert sum(1 for s, _ in turns(session, 2) if s == "agent") == cap[2] + 1  # + closing message
    assert session["context_scales"] == v["prefilled"]
    assert_valid(session, v)


# ------------------------------------------------------------------ history_check

def history_llm(verify: bool):
    def turn(state, messages):
        if state["history_check_required"]:
            assert "【安全层指令】" in messages[-1]["content"]
            text = VERIFY if verify else "那你平时几点起床？"
            return {"action": "say", "text": text, "acts": []}
        assert "【安全层指令】" not in messages[-1]["content"]
        return {"action": "say", "text": "能多说说吗？", "acts": []}
    return ScriptedLLM(turn)


def test_history_verified_by_agent_needs_no_script():
    v = visitor()
    sim = ScriptedSim(["最近睡不好。", HISTORY_TEXT, "现在没有了。"])
    session, trace = run(deps_for(llm=history_llm(True), sim=sim), v)
    events = session["safety_events"]
    assert [(e["action"], e["level"], e["turn"]) for e in events] == [("history_check", "none", 3)]
    t = turns(session, 1)
    assert t[3] == ("agent", VERIFY) and t[4][0] == "visitor"
    assert all(s != "safety" for s, _ in t)
    assert trace["history_checks"] == [{"round": 1, "turn": 4, "verified_by_agent": True}]
    assert session["rounds"][0]["crisis_level"] == "none"
    assert_valid(session, v)


def test_history_not_verified_inserts_fixed_script_once():
    v = visitor()
    layer_script = SafetyLayer({"judge_provider": "mock"}).script_for("history_check")
    sim = ScriptedSim(["最近睡不好。", HISTORY_TEXT, "现在没有了。", HISTORY_TEXT])
    session, trace = run(deps_for(llm=history_llm(False), sim=sim), v)
    t = turns(session, 1)
    assert t[3] == ("agent", "那你平时几点起床？")
    assert t[4] == ("safety", layer_script)
    assert t[5][0] == "visitor"
    assert [s for s, _ in t].count("safety") == 1  # history_check issued once per session
    assert trace["history_checks"][0]["verified_by_agent"] is False
    assert len([e for e in session["safety_events"] if e["action"] == "history_check"]) == 1
    assert_valid(session, v)


def test_history_on_last_visitor_turn_is_flushed_before_round_ends():
    v = visitor()
    cap = load_config()["round_turn_cap"][1]
    sim = ScriptedSim(["最近睡不好。"] + ["嗯。"] * (cap - 1) + [HISTORY_TEXT, "现在没有了。"])
    session, trace = run(deps_for(sim=sim), v)
    t = turns(session, 1)
    assert t[-3] == ("visitor", HISTORY_TEXT)
    assert t[-2][0] == "safety" and t[-1] == ("visitor", "现在没有了。")
    assert trace["history_checks"][-1]["at_round_end"] is True
    assert_valid(session, v)


def test_history_pending_survives_tool_call_until_next_message():
    v = visitor()
    seq = iter([{"action": "tool", "tool": "screen_osa"}])

    def turn(state, messages):
        if state["history_check_required"]:
            nxt = next(seq, None)
            if nxt:
                return nxt
            return {"action": "say", "text": VERIFY, "acts": []}
        return {"action": "say", "text": "能多说说吗？", "acts": []}

    sim = ScriptedSim(["最近睡不好。", HISTORY_TEXT])
    session, trace = run(deps_for(llm=ScriptedLLM(turn), sim=sim), v)
    assert session["tool_calls"][0]["turn"] == 4
    assert turns(session, 1)[3] == ("agent", VERIFY)
    assert trace["history_checks"][0]["verified_by_agent"] is True
    assert_valid(session, v)


# ------------------------------------------------------------------ passive / active

def test_passive_inserts_safety_check_and_continues():
    v = visitor("A-003")
    script = SafetyLayer({"judge_provider": "mock"}).script_for("safety_check")
    sim = ScriptedSim(["最近很累。", PASSIVE_TEXT, "没有具体计划。", PASSIVE_TEXT])
    llm = ScriptedLLM()
    session, trace = run(deps_for(llm=llm, sim=sim), v)
    t = turns(session, 1)
    assert t[2] == ("visitor", PASSIVE_TEXT) and t[3] == ("safety", script) and t[4] == ("visitor", "没有具体计划。")
    assert [s for s, _ in t].count("safety") == 1  # second passive does not repeat the script
    assert session["status"] == "completed"
    assert [e["action"] for e in session["safety_events"]] == ["safety_check"]
    assert session["rounds"][0]["crisis_level"] == "passive"
    assert len(trace["ignored_events"]) == 1
    # The agent's next turn saw the inserted script (speculation was discarded).
    after = [c for c in llm.calls if c[0] == "turn" and "【安全层】" in c[1]]
    assert after and script in after[0][1]
    assert trace["speculation"]["discarded"] >= 1
    assert_valid(session, v)


def test_active_runs_crisis_protocol_and_exits():
    v = visitor("A-003")
    script = SafetyLayer({"judge_provider": "mock"}).script_for("crisis_protocol")
    sim = ScriptedSim(["最近很累。", ACTIVE_TEXT])
    session, _ = run(deps_for(sim=sim), v)
    assert session["status"] == "crisis_exit" and session["plan"] is None
    assert len(session["rounds"]) == 1
    assert turns(session, 1)[-1] == ("safety", script)
    assert session["safety_events"][-1]["action"] == "crisis_protocol"
    assert session["rounds"][0]["crisis_level"] == "active"
    assert_valid(session, v)


def test_active_after_safety_check_answer():
    v = visitor("A-003")
    sim = ScriptedSim(["最近很累。", PASSIVE_TEXT, ACTIVE_TEXT])
    session, _ = run(deps_for(sim=sim), v)
    assert [e["action"] for e in session["safety_events"]] == ["safety_check", "crisis_protocol"]
    assert session["status"] == "crisis_exit"
    assert_valid(session, v)


def test_active_in_opening_statement():
    v = visitor()
    session, _ = run(deps_for(sim=ScriptedSim([ACTIVE_TEXT])), v)
    assert session["status"] == "crisis_exit"
    assert [s for s, _ in turns(session, 1)] == ["visitor", "safety"]
    assert_valid(session, v)


# ------------------------------------------------------------------ judge failure

def test_judge_failure_without_rule_hit_continues_and_counts():
    v = visitor()
    judge = StubJudge(fail=True)
    session, trace = run(deps_for(judge=judge), v)
    assert session["status"] == "completed" and session["safety_events"] == []
    assert trace["judge_failures"] == len(judge.calls) > 0
    assert_valid(session, v)


def test_judge_failure_with_ambiguous_rule_falls_back_to_passive():
    v = visitor()
    layer = SafetyLayer({"judge_provider": "mock"})
    ambiguous = "我不想活了"
    assert layer.rules.match(ambiguous).tier == "ambiguous"
    session, _ = run(deps_for(judge=StubJudge(fail=True), sim=ScriptedSim(["最近睡不好。", ambiguous])), v)
    event = session["safety_events"][0]
    assert (event["level"], event["source"], event["action"], event["judge_status"]) == \
        ("passive", "rule_ambiguous", "safety_check", "error")
    assert_valid(session, v)


# ------------------------------------------------------------------ scales and tools

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
    llm = ScriptedLLM(lambda state, m: next(calls, {"action": "say", "text": "能多说说吗？", "acts": []}))
    session, _ = run(deps_for(llm=llm), v)
    call = session["tool_calls"][0]
    assert (call["round"], call["turn"], call["tool"]) == (1, 2, "screen_mood")
    assert call["result"]["phq9_items"][8] == 1 and sum(call["result"]["phq9_items"]) == v["indices"]["phq9"]
    event = session["safety_events"][0]
    assert (event["turn"], event["source"]) == (2, "scale_item9")
    assert turns(session, 1)[1][0] == "safety"  # script right after the tool turn
    agent_actions = sum(1 for s, _ in turns(session, 1) if s == "agent") + 1
    assert agent_actions == load_config()["round_turn_cap"][1]
    assert_valid(session, v)


def test_turn_cap_holds_when_agent_only_calls_tools():
    v = visitor("A-002")
    llm = ScriptedLLM(lambda state, m: {"action": "tool", "tool": "screen_osa"})
    session, _ = run(deps_for(llm=llm), v)
    caps = load_config()["round_turn_cap"]
    assert [sum(1 for c in session["tool_calls"] if c["round"] == r) for r in (1, 2)] == [caps[1], caps[2]]
    assert_valid(session, v)


def test_end_round_stops_early():
    v = visitor()
    llm = ScriptedLLM(lambda state, m: {"action": "end_round"})
    session, _ = run(deps_for(llm=llm), v)
    assert [s for s, _ in turns(session, 1)] == ["visitor"]
    assert [s for s, _ in turns(session, 2)] == ["agent", "visitor"]  # closing message + reply
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
    plan_calls = [c for c in llm.calls if c[0] == "plan"]
    assert len(plan_calls) == 2 and "未通过固定规则检查" in plan_calls[1][1]
    assert trace["vetoes"][-1] == {"stage": "plan_remediated", "violations": []}
    assert_valid(session, v)


def test_forbidden_wording_in_agent_message_is_rewritten():
    v = visitor()
    seen = []

    def turn(state, messages):
        seen.append(messages[-1]["content"])
        if "未通过固定规则检查" in messages[-1]["content"]:
            return {"action": "say", "text": "听起来睡眠困扰你挺久了。", "acts": []}
        return {"action": "say", "text": "你这是失眠症。", "acts": []}

    session, trace = run(deps_for(llm=ScriptedLLM(turn)), v)
    agent_texts = [t for s, t in turns(session, 1) if s == "agent"]
    assert "你这是失眠症。" not in agent_texts
    assert any(entry["stage"] == "turn" for entry in trace["vetoes"])
    assert_valid(session, v)


def test_invalid_agent_output_is_retried():
    v = visitor()
    state = {"n": 0}

    def turn(s, m):
        state["n"] += 1
        return {"action": "dance"} if state["n"] == 1 else {"action": "say", "text": "嗯。", "acts": []}

    session, trace = run(deps_for(llm=ScriptedLLM(turn)), v)
    assert session["status"] == "completed"
    assert any(not c["ok"] for c in trace["llm_calls"])


def test_persistent_llm_failure_yields_valid_error_session():
    v = visitor()
    llm = ScriptedLLM(lambda s, m: {"action": "dance"})
    session, _ = run(deps_for(llm=llm), v)
    assert session["status"] == "error" and "turn failed" in session["error"]
    assert session["plan"] is None
    assert_valid(session, v)


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
    per_session_calls = len(llm.calls) / 50
    assert elapsed < per_session_calls * 0.01 * 50 / 4  # far below sequential time
    assert llm.max_inflight <= 20 * 2  # one turn call + at most one speculative call per session
    assert [s["visitor_id"] for s, _ in results] == [v["id"] for v in visitors]
    for (session, _), v in zip(results, visitors):
        assert session["status"] == "completed"
        assert_valid(session, v)


def test_mock_end_to_end_on_contract_examples():
    visitors = load_visitors([EXAMPLES])
    assert {v["id"] for v in visitors} == {"A-001", "A-002", "A-003"}
    deps = build_deps(config={"agent_llm": {"provider": "mock"}},
                      safety=SafetyLayer({"judge_provider": "mock"}))
    results = asyncio.run(run_batch(visitors, deps, "mock-run"))
    by_id = {s["visitor_id"]: s for s, _ in results}
    for v in visitors:
        assert_valid(by_id[v["id"]], v)
    assert any(c["tool"] == "screen_osa" for c in by_id["A-002"]["tool_calls"])
    assert by_id["A-002"]["rounds"][-1]["referral_pred"] == "R1"
    assert by_id["A-003"]["safety_events"][0]["source"] == "scale_item9"


# ------------------------------------------------------------------ playbook and config

def test_playbook_v0_sections_match_contract():
    playbook = load_playbook(load_config()["playbook_path"])
    assert list(playbook.sections) == list(SECTIONS)
    assert "screen_mood" in playbook.sections["questioning_strategy"]
    with pytest.raises(ValueError):
        parse_sections("## communication_style\nx\n## plan_rules\ny\n")


def test_config_rejects_bad_caps():
    with pytest.raises(ValueError):
        load_config({"round_turn_cap": {1: 0, 2: 3}})


def test_missing_keys_fall_back_to_mock_agent():
    deps = build_deps(safety=SafetyLayer({"judge_provider": "mock"}))
    assert deps.llm.model_name == "mock(fallback)"


@pytest.mark.xfail(strict=True, reason="contract conflict (reported): repeated passive via screen_mood item 9 has "
                   "action none, which session.safety_events forbids, yet validate.py requires a scale_item9 event")
def test_repeated_passive_then_item9_contract_conflict():
    v = visitor("A-003")
    calls = iter([{"action": "say", "text": "能多说说吗？", "acts": []}, {"action": "tool", "tool": "screen_mood"}])
    llm = ScriptedLLM(lambda s, m: next(calls, {"action": "say", "text": "嗯。", "acts": []}))
    session, trace = run(deps_for(llm=llm, sim=ScriptedSim(["最近很累。", PASSIVE_TEXT, "没有计划。"])), v)
    assert trace["ignored_events"][0]["source"] == "scale_item9"
    assert_valid(session, v)
