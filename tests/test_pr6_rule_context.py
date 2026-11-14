"""S7 and S9: route uncertain context to the judge, preserving failure fallback."""
import asyncio

import pytest

from safety.judges import JudgeResult
from safety.layer import SafetyLayer, SessionSafetyState
from safety.rules import Rules


class Judge:
    def __init__(self, status="ok", label="none"):
        self.status, self.label, self.calls = status, label, 0

    async def classify(self, text):
        self.calls += 1
        return JudgeResult({k: float(k == self.label) for k in ("none", "history", "passive", "active")}
                           if self.status == "ok" else None, self.status, "offline", 0.)


@pytest.mark.parametrize("text", [
    "我朋友想自杀，我很担心他。",
    "新闻说有人写好了遗书，我自己没有这些想法。",
    "我没有跳楼的想法。",
    "我的朋友想结束自己的生命。",
    "我担心他想自杀。",
    "我看到新闻说有人写好了遗书。",
    "我不想跳河。",
    "我并没有想过跳楼。",
    "我对跳楼没有任何想法。",
    "写好了遗书。",
])
@pytest.mark.parametrize("status", ["ok", "error", "timeout"])
def test_s7_third_party_denial_and_unknown_subject_route_not_drop(text, status):
    assert Rules().match(text).tier == "ambiguous"
    judge, state = Judge(status), SessionSafetyState()
    event = asyncio.run(SafetyLayer(judge=judge).assess_text(text, 1, 1, state))
    assert judge.calls == 1
    if status == "ok":
        assert event is None and state.highest_level == "none"
    else:
        assert (event.level, event.action, event.source, event.judge_status) == (
            "passive", "safety_check", "rule_ambiguous", status)


@pytest.mark.parametrize("text", [
    "我现在想自杀。", "我已经写好了遗书。", "我想跳楼。",
    "朋友想自杀，但我也想自杀。", "我朋友写好了遗书。我也写好了遗书。",
    "我没有跳楼的想法，但我现在想自杀。",
])
def test_s7_current_self_explicit_still_skips_judge(text):
    judge = Judge()
    event = asyncio.run(SafetyLayer(judge=judge).assess_text(text, 1, 1, SessionSafetyState()))
    assert (event.level, event.source, event.action) == ("active", "rule_explicit", "crisis_protocol")
    assert judge.calls == 0


@pytest.mark.parametrize("text", ["普通睡眠问题", "困死了", "我没有跳楼的想法。", "撑不下去了"])
def test_s9_every_nonexplicit_utterance_calls_judge(text):
    judge = Judge()
    asyncio.run(SafetyLayer(judge=judge).assess_text(text, 1, 1, SessionSafetyState()))
    assert judge.calls == 1


def test_s7_downgraded_context_can_still_escalate_on_judge_evidence():
    judge = Judge(label="active")
    event = asyncio.run(SafetyLayer(judge=judge).assess_text("我没有跳楼的想法。", 1, 1, SessionSafetyState()))
    assert judge.calls == 1
    assert (event.level, event.source) == ("active", "rule_ambiguous+judge")
