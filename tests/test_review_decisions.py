"""11/14 approved routing and veto boundaries; all judges are offline fakes."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import yaml

from domain.vetoes import Violation, check_plan, check_text, to_hard_rule_violations
from safety.judges import DsFlashJudge, GeminiDecisionJudge, JudgeResult, StartLuxJudge
from safety.layer import SafetyLayer, SessionSafetyState
from safety.rules import Rules


class Judge:
    def __init__(self, label="history", status="ok"):
        self.label, self.status, self.inputs = label, status, []

    async def classify(self, text):
        self.inputs.append(text)
        return JudgeResult({key: float(key == self.label) for key in ("none", "history", "passive", "active")}, self.status, "test", 0.)


def assess(judge, text):
    state = SessionSafetyState()
    event = asyncio.run(SafetyLayer(judge=judge).assess_text(text, 1, 1, state))
    return event, state


@pytest.mark.parametrize("time", ["以前", "那时候", "高中的时候", "多年前", "三年前", "早就不"])
def test_past_time_routes_explicit_to_history_verification(time):
    text = f"{time}拿刀片划手臂，现在已经没有了"
    judge = Judge()
    event, state = assess(judge, text)
    assert judge.inputs == [text]
    assert (event.level, event.action, event.source) == ("none", "history_check", "rule_ambiguous+judge")
    assert state.pending_history_check and state.highest_level == "none"
    assert Rules().match(text).past_time_ids


@pytest.mark.parametrize("label", ["none", "history", "passive", "active"])
def test_past_time_obeys_successful_judge(label):
    event, _ = assess(Judge(label), "以前我想自杀，现在又想起来")
    if label == "none":
        assert event is None
    else:
        assert event.source == "rule_ambiguous+judge"
        assert event.action == {"history": "history_check", "passive": "safety_check", "active": "crisis_protocol"}[label]


@pytest.mark.parametrize("status", ["error", "timeout"])
def test_past_time_failure_does_not_drop_risk(status):
    event, state = assess(Judge(status=status), "高中的时候拿刀片划手臂，困死了，现在没有了")
    assert (event.level, event.source, event.judge_status) == ("passive", "rule_ambiguous", status)
    assert state.judge_failures == 1


@pytest.mark.parametrize("separator", ["。", "！", "？", "；", ";", "\n"])
def test_past_time_does_not_cross_sentence_or_cancel_current_explicit(separator):
    judge = Judge()
    event, _ = assess(judge, "以前睡不好" + separator + "我现在想自杀")
    assert event.level == "active" and event.source == "rule_explicit"
    assert judge.inputs == []
    assert Rules().match("以前我想自杀" + separator + "我现在想自杀").tier == "explicit"


def test_recent_act_and_sleep_past_word_are_not_history_markers():
    rules = Rules()
    for text in ("上周我拿刀在手腕上比划，现在后悔没继续", "我买了一包药，打算一次性全吃，让自己彻底睡过去"):
        assert rules.match(text).tier == "explicit"


@pytest.mark.parametrize("status", ["ok", "timeout", "error"])
def test_x9_retains_ambiguous_and_only_adds_context(status):
    text = "周末不想醒，其实是不想面对生活"
    judge = Judge("none", status)
    event, _ = assess(judge, text)
    assert judge.inputs == [text + "\n上下文提示：赖床/补觉语境"]
    assert Rules().match(text).tier == "ambiguous"
    assert event is None if status == "ok" else event.level == "passive"
    assert not Rules().match("周末睡得好。撑不下去了").context_hint


def test_exclusions_are_per_match_and_never_cancel_explicit():
    rules = Rules()
    assert rules.match("困死了，今晚我也不想活了").tier == "ambiguous"
    assert rules.match("困死了，今天我想自杀").tier == "explicit"
    assert rules.match("高中的时候我想自杀，困死了").tier == "ambiguous"
    assert rules.match("我不想自杀").tier == "ambiguous"
    assert rules.match("我没想过自杀").tier == "ambiguous"
    assert rules.match("我想自\u200b 杀").tier == "explicit"


def plan(tib=330, restriction=True, checked=True):
    return {"components": ["sleep_restriction" if restriction else "sleep_hygiene"], "tib_minutes": tib, "contraindications_checked": checked}


@pytest.mark.parametrize("tib,blocked", [(300, True), (329, True), (330, False), (331, False)])
@pytest.mark.parametrize("restriction", [True, False])
def test_floor_for_all_plans(tib, blocked, restriction):
    violations = check_plan(plan(tib, restriction), [])
    assert bool(violations) is blocked
    assert all(v.severity == "hard" for v in violations)


@pytest.mark.parametrize("age,restriction,blocked", [(17, True, True), (18, True, False), (22, True, False), (None, True, False), (17, False, False)])
def test_age_only_blocks_under_18_sleep_restriction(age, restriction, blocked):
    violations = check_plan(plan(restriction=restriction), [], age=age)
    assert bool(violations) is blocked
    assert all(v.field == "age" and v.severity == "hard" for v in violations)


def test_passive_soft_warning_and_unchecked_hard_veto_serialize_separately():
    soft = check_plan(plan(), [], crisis_level="passive")
    assert len(soft) == 1 and soft[0].severity == "soft"
    assert to_hard_rule_violations(soft, "C1") == []
    violations = check_plan(plan(329, checked=False), [], age=17, crisis_level="passive")
    assert [v.field for v in violations if v.severity == "hard"] == ["contraindications_checked", "age", "tib_minutes"]
    hard = to_hard_rule_violations(violations, "C1")
    assert len(hard) == 3
    assert all(set(row) == {"code", "message", "change_id"} and row["change_id"] == "C1" for row in hard)
    assert check_plan(plan(restriction=False), [], age=17, crisis_level="passive") == []
    with pytest.raises(ValueError):
        Violation("test", "test", "text", "invalid")


@pytest.mark.parametrize("text,severity", [("诊断", "hard"), ("治疗失眠", "hard"), ("你患有焦虑症", "hard"), ("你这是抑郁", "hard"), ("您是患者", "hard"), ("根治", "hard"), ("给你开药", "hard"), ("We can cure insomnia", "hard"), ("医生会讨论治疗方案", "soft"), ("了解失眠症的知识", "soft")])
def test_all_wording_rules_have_approved_severity(text, severity):
    violations = check_text(text)
    assert violations and any(v.severity == severity for v in violations)
    hard = to_hard_rule_violations(violations, "C2")
    assert bool(hard) is (severity == "hard")


def test_final_data_shapes_and_levels():
    root = Path(__file__).resolve().parents[1]
    lexicon = yaml.safe_load((root / "safety/lexicon.yaml").read_text())
    assert len(lexicon["explicit"]) == 7 and all(e["level"] == "active" for e in lexicon["explicit"])
    assert len(lexicon["past_time"]) == 4
    lines = (root / "safety/testset.jsonl").read_text().splitlines()
    assert lines[0] == "# 自写样本，不得复制公开数据；不得据此反复调 prompt"
    rows = [json.loads(line) for line in lines[1:]]
    assert len(rows) == 48 and len({r["id"] for r in rows}) == 48
    assert all(set(row) == {"id", "text", "label", "cssrs", "difficulty"} for row in rows)
    assert [r["id"] for r in rows if r["label"] == "history"] == ["NEG-18", "NEG-19", "NEG-20"]


def test_x9_hint_only_in_ds_user_message():
    captured = {}
    async def create(**kwargs):
        captured.update(kwargs)
        data = {"level": "none", "probs": {"none": 1., "history": 0., "passive": 0., "active": 0.}}
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(data)))])
    judge = DsFlashJudge(client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    assess(judge, "周末不想醒")
    assert captured["messages"][0] == {"role": "system", "content": judge.prompt}
    assert captured["messages"][1]["content"] == "周末不想醒\n上下文提示：赖床/补觉语境"


def test_x9_hint_in_gemini_input_not_question():
    captured = {}
    async def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(answers={"risk": SimpleNamespace(choice="none", confidence=1., probabilities={"none": 1., "history": 0., "passive": 0., "active": 0.})})
    judge = GeminiDecisionJudge(client=SimpleNamespace(aio=SimpleNamespace(decisions=SimpleNamespace(create=create))))
    assess(judge, "周末不想醒")
    assert captured["input"] == "周末不想醒\n上下文提示：赖床/补觉语境"
    assert "上下文提示" not in json.dumps(captured["questions"], ensure_ascii=False)


def test_x9_hint_in_startlux_state_not_question():
    captured = {}
    def handler(request):
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"answers": {"risk": {"type": "choice", "choice": "none", "confidence": 1., "probabilities": {"none": 1., "history": 0., "passive": 0., "active": 0.}}}})
    assess(StartLuxJudge(transport=httpx.MockTransport(handler)), "周末不想醒")
    assert captured["state"]["text"] == "周末不想醒\n上下文提示：赖床/补觉语境"
    assert "上下文提示" not in json.dumps(captured["questions"], ensure_ascii=False)
