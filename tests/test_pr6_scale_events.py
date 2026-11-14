"""PR #6 review counterexamples; independent of the frozen evaluation set."""
import asyncio
import json
from pathlib import Path
import subprocess
import sys

import pytest
from safety.judges import JudgeResult
from safety.layer import SafetyLayer, SessionSafetyState

ROOT = Path(__file__).resolve().parents[1]


class FixedJudge:
    def __init__(self, label="passive", status="ok"):
        self.label, self.status, self.calls = label, status, 0

    async def classify(self, text):
        self.calls += 1
        return JudgeResult({k: float(k == self.label) for k in ("none", "history", "passive", "active")}
                           if self.status == "ok" else None, self.status, "offline", 0.)


def test_s2_passive_then_scale_complete_session_validates(tmp_path):
    layer, state = SafetyLayer(judge=FixedJudge()), SessionSafetyState()
    document = json.loads((ROOT / "contracts/examples/session.A-003.json").read_text())
    text = document["rounds"][1]["transcript"][3]["text"]
    first = asyncio.run(layer.assess_text(text, 2, 4, state))
    second = layer.assess_phq9_item9(1, 2, 5, state)
    document["safety_events"] = [first.to_dict(), second.to_dict()]
    path = tmp_path / "session.json"
    path.write_text(json.dumps(document, ensure_ascii=False))
    result = subprocess.run([sys.executable, str(ROOT / "contracts/validate.py"), str(path),
                             "--schema", "session"], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (second.source, second.level, second.action) == ("scale_item9", "passive", "safety_check")


@pytest.mark.parametrize("previous", ["passive", "active"])
def test_s2_every_positive_scale_has_action(previous):
    layer, state = SafetyLayer(judge=FixedJudge(previous)), SessionSafetyState()
    asyncio.run(layer.assess_text("最近早醒", 1, 1, state))
    for turn, value in enumerate((1, 2, 3), 2):
        event = layer.assess_phq9_item9(value, 1, turn, state)
        assert event.source == "scale_item9"
        assert (event.level, event.action) == (("active", "crisis_protocol") if previous == "active"
                                             else ("passive", "safety_check"))
        assert state.highest_level == previous



def test_s2_deduplicates_speech_without_dropping_scale_events():
    layer, state = SafetyLayer(judge=FixedJudge()), SessionSafetyState()
    first = asyncio.run(layer.assess_text("最近早醒", 1, 1, state))
    assert layer.script_for_event(first, state) == layer.script_for("safety_check")
    for turn in (2, 3):
        event = layer.assess_phq9_item9(1, 1, turn, state)
        assert event.action == "safety_check"
        assert layer.script_for_event(event, state) == ""
    active = asyncio.run(layer.assess_text("我现在想自杀", 1, 4, state))
    assert layer.script_for_event(active, state) == layer.script_for("crisis_protocol")
    assert layer.script_for_event(first, SessionSafetyState()) == layer.script_for("safety_check")
