"""Frozen questionnaire/denial recheck, approved 2026-11-14; fully offline."""
import asyncio
import json
from pathlib import Path

import pytest

from engine.adapters_sim import S2OutcomeModel, S2Screening, S2VisitorSim
from engine.interfaces import VisitorReply
from engine.run import build_deps
from engine.session import SessionRunner
from engine.topics import tag_topics
from safety.judges import MockJudge
from safety.layer import SafetyLayer
from test_engine_session import (
    ACTIVE_TEXT, CAPS, HISTORY_TEXT, PASSIVE_TEXT, SAY, ScriptedLLM,
    agent_count, assert_valid, deps_for, run, visitor,
)

RECHECK = "刚才问卷里那一题，你可能只是随手填的，或者不想多说，这都没关系。不过我想再问一次：最近有没有想过具体怎么做、做过什么准备？现在你安全吗？"
DENIAL = "没有，没有这种想法。"


class CheckReplies:
    model_name = "offline-recheck-visitor"

    def __init__(self, first=DENIAL, second=DENIAL, opening="最近睡不好。"):
        self.first, self.second, self.opening = first, second, opening

    async def reply(self, visitor, round, transcript, memory):
        if not transcript:
            text = self.opening
        elif transcript[-1]["speaker"] == "safety":
            text = self.second if transcript[-1]["text"] == RECHECK else self.first
        else:
            text = "嗯，还好。"
        return VisitorReply(text, [], None)


def rechecks(session):
    return [t for r in session["rounds"] for t in r["transcript"]
            if t["speaker"] == "safety" and t["text"] == RECHECK]


def test_approved_script_and_spoken_topic():
    assert SafetyLayer(judge=MockJudge()).script_for("scale_recheck") == RECHECK
    assert tag_topics(RECHECK) == ["self_harm"]


@pytest.mark.parametrize("merged", [False, True])
@pytest.mark.parametrize("cap,early", [(5, False), (1, False), (5, True)])
def test_positive_scale_denial_rechecks_once_before_plan_without_using_action_budget(merged, cap, early):
    v = visitor("A-003")
    llm = ScriptedLLM(lambda s, m: {"action": "end_round"} if early else SAY)
    deps = deps_for(llm=llm, sim=CheckReplies(), merged=merged)
    deps.config["round_turn_cap"][1] = cap
    session, trace = run(deps, v)
    assert session["status"] == "completed"
    assert len(rechecks(session)) == 1
    check = rechecks(session)[0]
    transcript = session["rounds"][0]["transcript"]
    assert check in transcript
    index = transcript.index(check)
    assert transcript[index + 1]["text"] == DENIAL
    assert transcript[index + 2]["speaker"] == "agent"  # closing, after plan
    plan_calls = [messages for task, messages, state in llm.calls if task == "plan" and state["round"] == 1]
    assert RECHECK in str(plan_calls)
    assert agent_count(session, 1) == (0 if early else cap) + 1
    assert agent_count(session, 2) == (0 if early else CAPS[2]) + 1
    rows = trace["scale_rechecks"]
    assert len(rows) == 1 and rows[0]["recheck"] is True
    assert rows[0]["counts_toward_cap"] is False
    event = session["safety_events"][rows[0]["safety_event_index"]]
    assert (event["round"], event["turn"], event["source"], event["action"]) == (
        1, check["turn"], "scale_item9", "safety_check")
    assert_valid(session, v)


@pytest.mark.parametrize("first,opening", [(ACTIVE_TEXT, "最近睡不好。"), (DENIAL, ACTIVE_TEXT)])
def test_active_never_rechecks(first, opening):
    v = visitor("A-003")
    session, _ = run(deps_for(sim=CheckReplies(first=first, opening=opening)), v)
    assert session["status"] == "crisis_exit" and not rechecks(session)
    assert_valid(session, v)


def test_negative_scale_never_rechecks():
    v = visitor()
    session, _ = run(deps_for(sim=CheckReplies()), v)
    assert session["status"] == "completed" and not rechecks(session)
    assert_valid(session, v)


def test_disclosed_passive_after_check_suppresses_recheck_even_with_action_none():
    v = visitor("A-003")
    session, trace = run(deps_for(sim=CheckReplies(first=PASSIVE_TEXT)), v)
    assert session["status"] == "completed" and not rechecks(session)
    assert any(e["level"] == "passive" and e["action"] == "none" for e in trace["ignored_events"])
    assert_valid(session, v)


def test_second_answer_active_exits_before_any_plan():
    v = visitor("A-003")
    llm = ScriptedLLM()
    session, trace = run(deps_for(llm=llm, sim=CheckReplies(second=ACTIVE_TEXT)), v)
    assert len(rechecks(session)) == 1
    assert session["status"] == "crisis_exit" and session["plan"] is None
    assert session["rounds"][0]["crisis_level"] == "active" and len(session["rounds"]) == 1
    assert session["safety_events"][-1]["action"] == "crisis_protocol"
    assert not trace["plans"] and "plan" not in llm.tasks()
    assert_valid(session, v)


def test_repeated_positive_scales_and_two_rounds_still_only_recheck_once():
    v = visitor("A-003")
    v["prefilled"] = [{"scale": "phq9", "reported_score": 7, "items": [1, 1, 1, 1, 1, 1, 0, 0, 1]}]
    deps = deps_for(sim=CheckReplies(), llm=ScriptedLLM(lambda s, m: {"action": "tool", "tool": "screen_mood"}))
    session, _ = run(deps, v)
    assert session["status"] == "completed" and len(rechecks(session)) == 1
    assert len([e for e in session["safety_events"] if e["source"] == "scale_item9"]) > 2
    assert_valid(session, v)


def test_history_answer_to_recheck_keeps_existing_history_fallback():
    v = visitor("A-003")
    session, trace = run(deps_for(sim=CheckReplies(second=HISTORY_TEXT)), v)
    assert session["status"] == "completed" and len(rechecks(session)) == 1
    assert trace["history_checks"][-1]["at_round_end"] is True
    assert session["safety_events"][-1]["action"] == "history_check"
    assert_valid(session, v)


def test_s2_sample010_denies_first_then_reveals_and_exits():
    v = json.loads(Path("sim/visitors/sample-010.json").read_text())
    # MockJudge's default three active keywords miss this S2 method disclosure.
    # Stub the judge response for this exact utterance, not the simulator or live criteria.
    judge = MockJudge()
    judge.config["mock_keywords"]["active"].append("这几周会冒出不想活的念头，还想过具体要怎么做。")
    deps = build_deps(config={"agent_llm": {"provider": "mock"}, "path_classifier": {"provider": "mock"}},
                      sim=S2VisitorSim(), screening=S2Screening(), outcome=S2OutcomeModel(),
                      safety=SafetyLayer(judge=judge))
    runner = SessionRunner(deps, v, "sample010-recheck")
    session, trace = asyncio.run(runner.run())
    assert session["status"] == "crisis_exit" and session["plan"] is None
    assert len(rechecks(session)) == 1 and not trace["plans"]
    replies = runner.sim_memory["_s2_replies"]
    denied = [i for i, r in enumerate(replies) if "sample-010-c5" in r["denied_clue_ids"]]
    assert denied and "sample-010-c5" in replies[-1]["revealed_clue_ids"]
    transcript = session["rounds"][0]["transcript"]
    check_index = transcript.index(rechecks(session)[0])
    assert "sample-010-c5" in transcript[check_index + 1]["revealed_clue_ids"]
    assert session["safety_events"][-1]["level"] == "active"
    assert_valid(session, v)
