import asyncio
from dataclasses import asdict
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
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
        self.result = JudgeResult(probs or {"none": 1., "passive": 0., "active": 0.}, status, "stub", 0.1)

    async def classify(self, text):
        self.calls += 1
        return self.result


def assess(layer, text, state=None):
    return asyncio.run(layer.assess_text(text, 1, 1, state or SessionSafetyState()))


@pytest.mark.parametrize("text,level", [("我希望睡过去不再醒来", "passive"), ("我现在想自杀", "active")])
def test_explicit_skips_judge(text, level):
    judge = StubJudge()
    event = assess(SafetyLayer(judge=judge), text)
    assert (event.level, event.source, event.judge_status) == (level, "rule_explicit", "skipped")
    assert event.matched in text
    assert judge.calls == 0


def test_exclusion_only_cancels_ambiguous():
    rules = Rules()
    assert rules.match("撑不下去了").tier == "ambiguous"
    assert rules.match("困死了，撑不下去了").tier == "none"
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
    ({"none": .8, "passive": .2, "active": 0.}, "passive"),
    ({"none": .801, "passive": .199, "active": 0.}, None),
    ({"none": .5, "passive": 0., "active": .5}, "active"),
    ({"none": .501, "passive": 0., "active": .499}, "passive"),
])
def test_threshold_boundaries(probs, expected):
    event = assess(SafetyLayer(judge=StubJudge(probs)), "最近早醒")
    assert (event.level if event else None) == expected
    if event:
        assert event.source == "judge"


def test_ambiguous_is_at_least_passive():
    event = assess(SafetyLayer(judge=StubJudge()), "撑不下去了")
    assert (event.level, event.source) == ("passive", "rule_ambiguous+judge")


def test_ambiguous_can_escalate_to_active():
    event = assess(SafetyLayer(judge=StubJudge({"none": .1, "passive": .2, "active": .7})), "撑不下去了")
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
    assert assess(layer, "我希望睡过去不再醒来", state).action == "none"
    assert layer.assess_phq9_item9(1, 2, 0, state).action == "none"
    assert state.highest_level == "active"
    assert judge.calls == 0
    assert layer.assess_phq9_item9(1, 1, 0, SessionSafetyState()).action == "safety_check"


@pytest.mark.parametrize("kind", ["explicit", "ambiguous", "timeout", "error", "judge", "scale", "duplicate"])
def test_event_matches_contract(kind):
    common = json.loads((ROOT / "contracts/common.schema.json").read_text())
    session = json.loads((ROOT / "contracts/session.schema.json").read_text())
    registry = Registry().with_resource(common["$id"], Resource.from_contents(common))
    validator = Draft202012Validator(session["properties"]["safety_events"]["items"], registry=registry)
    judge = StubJudge({"none": .2, "passive": .3, "active": .5}, kind if kind in ("timeout", "error") else "ok")
    layer = SafetyLayer(judge=judge)
    state = SessionSafetyState()
    if kind in ("scale", "duplicate"):
        event = layer.assess_phq9_item9(1, 1, 0, state)
        if kind == "duplicate":
            event = layer.assess_phq9_item9(1, 2, 1, state)
    else:
        text = "我现在想自杀" if kind == "explicit" else "最近早醒" if kind == "judge" else "撑不下去了"
        event = assess(layer, text, state)
    validator.validate(json.loads(json.dumps(event.to_dict())))
    assert event.to_dict() == asdict(event)


def test_config_paths_and_expanded_files(tmp_path, monkeypatch):
    config = load_config()
    lexicon = {"explicit": [{"id": f"e{i}", "pattern": f"^样例{i}$", "level": "active", "example": f"样例{i}"} for i in range(120)], "ambiguous": [], "exclude": []}
    (tmp_path / "lexicon.yaml").write_text(yaml.safe_dump(lexicon, allow_unicode=True))
    (tmp_path / "scripts.yaml").write_text(yaml.safe_dump({"safety_check": "确认安全", "crisis_protocol": "联系：{hotlines}", "hotlines": [{"name": "测试", "number": "占位", "hours": "待核验", "verified": False}]}))
    config.update(lexicon_path="lexicon.yaml", scripts_path="scripts.yaml", tau_flag=.7, tau_active=.9)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config))
    monkeypatch.setenv("JUDGE_PROVIDER", "mock")
    loaded = load_config(path)
    assert loaded["judge_provider"] == "mock"
    layer = SafetyLayer(loaded, judge=StubJudge({"none": .4, "passive": .3, "active": .3}))
    assert assess(layer, "样例119").level == "active"
    assert assess(layer, "普通发言") is None
    assert layer.script_for("safety_check") == "确认安全"
    assert "测试" in layer.script_for("crisis_protocol")
    assert "{hotlines}" not in layer.script_for("crisis_protocol")
    assert layer.script_for("none") == ""


@pytest.mark.parametrize("key,value", [("tau_flag", -1), ("tau_active", 1.1), ("judge_timeout_s", 0), ("judge_timeout_s", float("inf")), ("min_tib_minutes", -1), ("phq9_item9_threshold", 1), ("judge_provider", "unknown")])
def test_invalid_config_is_rejected(key, value):
    with pytest.raises(ValueError):
        load_config({key: value})
