import asyncio
from dataclasses import asdict
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError
from referencing import Registry, Resource
import yaml

from safety.config import load_config
from safety.judges import JudgeResult
from safety.layer import SafetyLayer, SessionSafetyState
from safety.rules import Rules

ROOT = Path(__file__).resolve().parents[1]


class StubJudge:
    def __init__(self, probs=None, status="ok"):
        self.calls = 0
        self.result = JudgeResult(probs or {"none": 1., "history": 0., "passive": 0., "active": 0.}, status, "stub", 0.1)

    async def classify(self, text):
        self.calls += 1
        return self.result


def assess(layer, text, state=None):
    return asyncio.run(layer.assess_text(text, 1, 1, state or SessionSafetyState()))


@pytest.mark.parametrize("text,level", [("我打算结束自己的生命", "active"), ("我现在想自杀", "active")])
def test_explicit_skips_judge(text, level):
    judge = StubJudge()
    event = assess(SafetyLayer(judge=judge), text)
    assert (event.level, event.source, event.judge_status) == (level, "rule_explicit", "skipped")
    assert event.matched in text
    assert judge.calls == 0


def test_exclusion_only_cancels_ambiguous():
    rules = Rules()
    assert rules.match("撑不下去了").tier == "ambiguous"
    assert rules.match("困死了，但我不想活了").tier == "ambiguous"
    assert rules.match("困死了").tier == "none"
    assert rules.match("困死了，但我现在想自杀").level == "active"
    assert rules.match("我希望睡过去不再醒来，我现在想自杀").level == "active"


@pytest.mark.parametrize("status", ["timeout", "error"])
def test_ambiguous_failure_is_passive(status):
    state = SessionSafetyState()
    event = assess(SafetyLayer(judge=StubJudge(status=status)), "撑不下去了", state)
    assert (event.level, event.source, event.judge_status) == ("passive", "rule_ambiguous", status)
    assert event.judge_probs is None
    assert state.judge_failures == 1


@pytest.mark.parametrize("status", ["timeout", "error"])
def test_no_match_failure_has_no_event_but_counts(status):
    state = SessionSafetyState()
    assert assess(SafetyLayer(judge=StubJudge(status=status)), "最近早醒", state) is None
    assert state.judge_failures == 1
    assert state.judge_results[-1].status == status


@pytest.mark.parametrize("probs,expected", [
    ({"none": .8, "history": 0., "passive": .2, "active": 0.}, "passive"),
    ({"none": .801, "history": 0., "passive": .199, "active": 0.}, None),
    ({"none": .5, "history": 0., "passive": 0., "active": .5}, "active"),
    ({"none": .501, "history": 0., "passive": 0., "active": .499}, "passive"),
])
def test_threshold_boundaries(probs, expected):
    event = assess(SafetyLayer(judge=StubJudge(probs)), "最近早醒")
    assert (event.level if event else None) == expected
    if event:
        assert event.source == "judge"


def test_ambiguous_success_none_does_not_use_failure_fallback():
    event = assess(SafetyLayer(judge=StubJudge()), "撑不下去了")
    assert event is None


def test_ambiguous_can_escalate_to_active():
    event = assess(SafetyLayer(judge=StubJudge({"none": .1, "history": 0., "passive": .2, "active": .7})), "撑不下去了")
    assert (event.level, event.source, event.action) == ("active", "rule_ambiguous+judge", "crisis_protocol")


@pytest.mark.parametrize("mode,status", [("exception", "error"), ("timeout", "timeout")])
def test_layer_bounds_custom_judges_and_records_one_failure(mode, status):
    class BrokenJudge:
        async def classify(self, text):
            if mode == "timeout":
                await asyncio.Event().wait()
            raise RuntimeError("test")

    state = SessionSafetyState()
    layer = SafetyLayer({"judge_timeout_s": .01}, judge=BrokenJudge())
    event = assess(layer, "撑不下去了", state)
    assert event.level == "passive"
    assert event.judge_status == status
    assert state.judge_failures == len(state.judge_results) == 1


def test_item9_and_monotonic_state():
    judge = StubJudge()
    layer = SafetyLayer(judge=judge)
    state = SessionSafetyState()
    assert layer.assess_phq9_item9(0, 1, 0, state) is None
    event = layer.assess_phq9_item9(1, 1, 0, state)
    assert (event.level, event.source, event.action) == ("passive", "scale_item9", "safety_check")
    assert layer.assess_phq9_item9(2, 1, 0, state).action == "none"
    assert assess(layer, "我现在想自杀", state).action == "crisis_protocol"
    judge.result = JudgeResult({"none": 0., "history": 0., "passive": 1., "active": 0.}, "ok", "stub", .1)
    assert assess(layer, "我希望睡过去不再醒来", state).action == "none"
    assert layer.assess_phq9_item9(1, 2, 0, state).action == "none"
    assert state.highest_level == "active"
    assert judge.calls == 1
    assert layer.assess_phq9_item9(1, 1, 0, SessionSafetyState()).action == "safety_check"


@pytest.mark.parametrize("kind", ["explicit", "ambiguous", "timeout", "error", "judge", "scale", "duplicate", "history", "ambiguous_history"])
def test_event_matches_contract(kind):
    common = json.loads((ROOT / "contracts/common.schema.json").read_text())
    session = json.loads((ROOT / "contracts/session.schema.json").read_text())
    registry = Registry().with_resource(common["$id"], Resource.from_contents(common))
    validator = Draft202012Validator(session["properties"]["safety_events"]["items"], registry=registry)
    judge = StubJudge({"none": .2, "history": 0., "passive": .3, "active": .5}, kind if kind in ("timeout", "error") else "ok")
    if kind in ("history", "ambiguous_history"):
        judge = StubJudge({"none": 0., "history": 1., "passive": 0., "active": 0.})
    layer = SafetyLayer(judge=judge)
    state = SessionSafetyState()
    if kind in ("scale", "duplicate"):
        event = layer.assess_phq9_item9(1, 1, 0, state)
        if kind == "duplicate":
            event = layer.assess_phq9_item9(1, 2, 1, state)
    else:
        text = "我现在想自杀" if kind == "explicit" else "最近早醒" if kind in ("judge", "history") else "撑不下去了"
        event = assess(layer, text, state)
    if kind == "duplicate":
        # The local no-action result must be filtered before session serialization.
        assert event.action == "none"
        with pytest.raises(ValidationError):
            validator.validate(event.to_dict())
        return
    validator.validate(json.loads(json.dumps(event.to_dict())))
    assert event.to_dict() == asdict(event)


def test_config_paths_and_expanded_files(tmp_path, monkeypatch):
    config = load_config()
    lexicon = {"explicit": [{"id": f"e{i}", "pattern": f"^样例{i}$", "level": "active", "example": f"样例{i}"} for i in range(120)], "ambiguous": [], "exclude": []}
    (tmp_path / "lexicon.yaml").write_text(yaml.safe_dump(lexicon, allow_unicode=True))
    (tmp_path / "scripts.yaml").write_text(yaml.safe_dump({"history_check": "核验", "history_verify_patterns": ["自定义核验"], "safety_check": "确认安全", "crisis_protocol": "联系：{hotlines}", "hotlines": [{"name": "测试", "number": "占位", "hours": "待核验", "verified": False}]}))
    config.update(lexicon_path="lexicon.yaml", scripts_path="scripts.yaml", tau_flag=.7, tau_active=.9)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config))
    monkeypatch.setenv("JUDGE_PROVIDER", "mock")
    loaded = load_config(path)
    assert loaded["judge_provider"] == "mock"
    layer = SafetyLayer(loaded, judge=StubJudge({"none": .4, "history": 0., "passive": .3, "active": .3}))
    assert assess(layer, "样例119").level == "active"
    assert assess(layer, "普通发言") is None
    assert layer.script_for("safety_check") == "确认安全"
    assert "测试" in layer.script_for("crisis_protocol")
    assert "{hotlines}" not in layer.script_for("crisis_protocol")
    assert layer.script_for("none") == ""
    assert layer.check_verification("自定义核验")
    assert not layer.check_verification("现在你还有这种念头吗？")


@pytest.mark.parametrize("key,value", [("tau_flag", -1), ("tau_active", 1.1), ("judge_timeout_s", 0), ("judge_timeout_s", float("inf")), ("min_tib_minutes", -1), ("phq9_item9_threshold", 1), ("judge_provider", "unknown")])
def test_invalid_config_is_rejected(key, value):
    with pytest.raises(ValueError):
        load_config({key: value})


@pytest.mark.parametrize("probs,expected", [
    ({"none": .1, "history": .7, "passive": .1, "active": .1}, ("passive", "safety_check")),
    ({"none": .101, "history": .7, "passive": .1, "active": .099}, ("none", "history_check")),
    ({"none": .4, "history": .4, "passive": .1, "active": .1}, ("passive", "safety_check")),
    ({"none": .5, "history": .5, "passive": 0., "active": 0.}, ("none", "history_check")),
    ({"none": .501, "history": .499, "passive": 0., "active": 0.}, None),
    ({"none": 0., "history": .5, "passive": 0., "active": .5}, ("active", "crisis_protocol")),
])
def test_history_threshold_priority_and_ties(probs, expected):
    event = assess(SafetyLayer(judge=StubJudge(probs)), "过去的经历")
    assert ((event.level, event.action) if event else None) == expected


def test_history_ambiguous_once_and_escalation():
    layer = SafetyLayer(judge=StubJudge({"none": 0., "history": 1., "passive": 0., "active": 0.}))
    state = SessionSafetyState()
    event = assess(layer, "那时候撑不下去了，现在已经没有了", state)
    assert (event.level, event.action, event.source) == ("none", "history_check", "rule_ambiguous+judge")
    assert state.highest_level == "none"
    assert state.pending_history_check and state.history_check_issued
    assert not state.safety_check_inserted
    assert assess(layer, "过去的经历", state) is None
    # Engine clears pending after checking the reply or inserting fallback.
    state.pending_history_check = False
    assert assess(layer, "过去的经历", state) is None
    assert not state.pending_history_check
    layer.judge = StubJudge({"none": 0., "history": 0., "passive": 1., "active": 0.})
    assert assess(layer, "我希望睡过去不再醒来", state).action == "safety_check"
    layer.judge = StubJudge({"none": 0., "history": 1., "passive": 0., "active": 0.})
    assert assess(layer, "过去的经历", SessionSafetyState()).action == "history_check"


def test_active_suppresses_history_and_clears_pending():
    layer = SafetyLayer(judge=StubJudge({"none": 0., "history": 1., "passive": 0., "active": 0.}))
    state = SessionSafetyState()
    assess(layer, "过去的经历", state)
    assert state.pending_history_check
    assess(layer, "我现在想自杀", state)
    assert not state.pending_history_check
    assert assess(layer, "过去的经历", state) is None
    fresh_active = SessionSafetyState(highest_level="active")
    assert assess(layer, "过去的经历", fresh_active) is None
    assert not fresh_active.pending_history_check and not fresh_active.history_check_issued


@pytest.mark.parametrize("text,expected", [
    ("我想确认一下，现在你已经没有这种念头了吗？", True),
    ("你现在是否还有伤害自己的想法？", True),
    ("目前这些念头还在吗？", True),
    ("现在还有希望不再醒来的想法吗？", True),
    ("我们来讨论睡眠建议。", False),
    ("以前你是否有自伤的想法？", False),
    ("现在你睡得好吗？", False),
    ("现在你已经没有这种念头了。", False),
    ("现在先说作息。以前你是否有自伤的想法？", False),
    ("", False),
])
def test_history_verification(text, expected):
    layer = SafetyLayer(judge=StubJudge())
    assert layer.check_verification(text) is expected
    assert layer.check_verification(layer.script_for("history_check"))


def test_invalid_three_key_judge_falls_back_on_ambiguous():
    state = SessionSafetyState()
    event = assess(SafetyLayer(judge=StubJudge({"none": 1., "passive": 0., "active": 0.})), "撑不下去了", state)
    assert (event.level, event.action, event.source, event.judge_status) == ("passive", "safety_check", "rule_ambiguous", "error")
    assert not state.pending_history_check
