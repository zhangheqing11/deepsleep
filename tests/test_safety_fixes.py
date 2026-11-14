"""PR #6 regression cases; synthetic inputs, no real model calls."""
import asyncio
import json
from pathlib import Path
import subprocess
import sys

import httpx
import pytest

from safety.eval import evaluate
from safety.judges import JudgeResult, MockJudge, StartLuxJudge, make_judge
from safety.layer import SafetyLayer, SessionSafetyState

ROOT = Path(__file__).resolve().parents[1]


class PassiveJudge:
    provider = "stub"

    async def classify(self, text):
        return JudgeResult(dict(none=0., history=0., passive=1., active=0.), "ok", self.provider, 0.)


@pytest.mark.parametrize("provider", [None, "ds_flash", "jev", "startlux", "gemini_decision"])
def test_s1_missing_keys_are_error_not_mock(provider, caplog):
    layer = SafetyLayer(None if provider is None else {"judge_provider": provider})
    state = SessionSafetyState()
    event = asyncio.run(layer.assess_text("撑不下去了", 1, 1, state))
    assert event is not None
    assert (event.level, event.action, event.judge_status) == ("passive", "safety_check", "error")
    assert not event.judge_provider.startswith("mock")
    assert state.judge_failures >= 1
    assert "WARNING" in caplog.text and "判断器" in caplog.text


def test_s1_mock_is_explicit_and_labelled():
    judge = make_judge({"judge_provider": "mock"})
    assert isinstance(judge, MockJudge)
    result = asyncio.run(judge.classify("普通发言"))
    assert result.status == "ok" and result.provider == "mock"
    assert result.warning == "mock，不代表识别能力"


def build_sequence_session():
    session = json.loads((ROOT / "contracts/examples/session.A-003.json").read_text())
    layer, state = SafetyLayer(judge=PassiveJudge()), SessionSafetyState()
    text = session["rounds"][1]["transcript"][3]["text"]
    event = asyncio.run(layer.assess_text(text, 2, 4, state))
    scale = layer.assess_phq9_item9(session["tool_calls"][0]["result"]["phq9_items"][8], 2, 5, state)
    session["safety_events"] = [event.to_dict(), scale.to_dict()]
    return session


def test_s2_full_session_sequence_validates(tmp_path):
    path = tmp_path / "session.sequence.json"
    path.write_text(json.dumps(build_sequence_session(), ensure_ascii=False))
    result = subprocess.run([sys.executable, "contracts/validate.py", str(path), "--schema", "session"],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("previous", ["none", "passive", "active"])
@pytest.mark.parametrize("value", [1, 2, 3])
def test_s2_every_positive_scale_has_action(previous, value):
    layer = SafetyLayer(judge=PassiveJudge())
    state = SessionSafetyState(highest_level=previous, safety_check_inserted=True)
    event = layer.assess_phq9_item9(value, 2, 5, state)
    assert event.source == "scale_item9"
    assert (event.level, event.action) == (("active", "crisis_protocol") if previous == "active" else ("passive", "safety_check"))


def test_s2_script_dedup_does_not_remove_scale_event():
    layer, state = SafetyLayer(judge=PassiveJudge()), SessionSafetyState()
    text = asyncio.run(layer.assess_text("撑不下去了", 2, 4, state))
    assert layer.script_for_event(text, state) == layer.script_for("safety_check")
    scale = layer.assess_phq9_item9(1, 2, 5, state)
    assert scale.action == "safety_check"
    assert layer.script_for_event(scale, state) == ""
    active = asyncio.run(layer.assess_text("我现在想自杀", 2, 6, state))
    assert layer.script_for_event(active, state) == layer.script_for("crisis_protocol")


@pytest.mark.parametrize("text,expected", [
    ("现在你已经没有这种念头，今晚吃什么？", False),
    ("现在不用问你有没有自杀念头，我们聊睡眠好吗？", False),
    ("现在不用问你有没有自杀念头？", False),
    ("现在你已经没有这种念头了。", False),
    ("现在睡得好吗？以前有没有自杀念头？", False),
    ("目前你还有伤害自己的想法吗？", True),
    ("你仍有这种念头吗？", True),
    ("你还有自杀念头吗？", True),
    ("最近有没有想死的想法？", True),
    ("现在是不是还有这样的念头？", True),
    ("现在有自杀念头吗", False),
    ("现在你已经没有这种念头，今晚吃什么?", False),
])
def test_s3_same_question_clause(text, expected):
    assert SafetyLayer(judge=PassiveJudge()).check_verification(text) is expected


def test_s4_startlux_27s_response_survives_layer_25s_default():
    async def handler(request):
        await asyncio.sleep(2.7)
        return httpx.Response(200, json={"answers": {"risk": {
            "type": "choice", "choice": "active", "confidence": 1.,
            "probabilities": dict(none=0., history=0., passive=0., active=1.),
        }}})
    judge = StartLuxJudge({"judge_timeout_s": 2.5}, transport=httpx.MockTransport(handler))
    assert judge.timeout == 8.
    state = SessionSafetyState()
    event = asyncio.run(SafetyLayer({"judge_timeout_s": 2.5}, judge=judge).assess_text("最近早醒", 1, 1, state))
    assert (event.level, event.judge_status, event.judge_provider) == ("active", "ok", "startlux")
    assert state.judge_failures == 0


@pytest.mark.parametrize("provider", ["rules", "mock", "ds_flash"])
def test_s8_report_three_columns_and_missing_real_result(provider):
    report = asyncio.run(evaluate([{"id": "test", "text": "撑不下去了", "label": "passive"}], provider))
    columns = report["evaluation_columns"]
    assert set(columns) == {"rules-only", "mock", "真实判断器"}
    assert columns["真实判断器"]["status"] == "未测"
    if provider == "mock":
        assert "mock，不代表识别能力" in report["warnings"]
    if provider == "ds_flash":
        assert report["judge"]["statuses"] == {"error": 1}
        assert report["warnings"] and report["provider"] != "mock"


def test_s9_all_nonexplicit_utterances_call_judge():
    class Counting(PassiveJudge):
        calls = 0

        async def classify(self, text):
            self.calls += 1
            return await super().classify(text)
    judge = Counting()
    layer = SafetyLayer(judge=judge)
    for text in ["最近早醒", "撑不下去了", "困死了", "以前想自杀，现在没有了"]:
        asyncio.run(layer.assess_text(text, 1, 1, SessionSafetyState()))
    assert judge.calls == 4
    event = asyncio.run(layer.assess_text("我现在想自杀", 1, 1, SessionSafetyState()))
    assert judge.calls == 4 and event.judge_status == "skipped"


def test_s1_missing_ds_model_configuration_is_error(monkeypatch, caplog):
    monkeypatch.setenv("DS_API_KEY", "offline-placeholder")
    layer = SafetyLayer()
    state = SessionSafetyState()
    event = asyncio.run(layer.assess_text("撑不下去了", 1, 1, state))
    assert (event.level, event.judge_status) == ("passive", "error")
    assert "缺少模型配置" in caplog.text


def test_s1_missing_primary_still_uses_available_fallback(monkeypatch):
    import safety.judges as judges
    class AvailableFallback(PassiveJudge):
        provider = "jev"
        timeout = 3.
    monkeypatch.setenv("TYPESAFE_API_KEY", "offline-placeholder")
    monkeypatch.setattr(judges, "JevJudge", lambda config: AvailableFallback())
    state = SessionSafetyState()
    event = asyncio.run(SafetyLayer().assess_text("普通发言", 1, 1, state))
    assert (event.judge_provider, event.judge_status) == ("jev", "ok")
    assert [(r.provider, r.status) for r in state.judge_results] == [("ds_flash", "error"), ("jev", "ok")]
    assert state.judge_failures == 1


@pytest.mark.parametrize("failure", [False, True])
def test_s8_real_column_uses_successful_adapter_results(monkeypatch, failure):
    class SimulatedRemote(PassiveJudge):
        provider = "ds_flash"
        async def classify(self, text):
            if failure and text == "失败":
                return JudgeResult(None, "error", self.provider, 1.)
            return await super().classify(text)
    monkeypatch.setattr("safety.eval.make_judge", lambda *a, **kw: SimulatedRemote())
    rows = [{"id": text, "text": text, "label": "passive"} for text in ["成功", "失败"]]
    report = asyncio.run(evaluate(rows, "ds_flash"))
    column = report["evaluation_columns"]["真实判断器"]
    assert column["status"] == ("已测（含失败，见警告）" if failure else "已测")
    assert column["risk_recall"] == (0.5 if failure else 1.)
    assert report["evaluation_columns"]["mock"]["status"] == "未测"
    assert bool(report["warnings"]) is failure


@pytest.mark.parametrize("text,expected", [
    ("谢谢你愿意说出来，这不容易，我只想确认现在的情况：最近一个月，你还有没有这样的念头，或者伤害自己的行为？", True),
    ("我想确认一下，现在你已经没有这种念头了吗？", True),
    ("现在你已经没有这种念头，今晚吃什么？", False),
    ("现在不用问你有没有自杀念头，我们聊睡眠好吗？", False),
    ("你最近还有想死的念头吗？", True),
    ("我不想问你现在有没有自杀的想法。", False),
    ("现在你还好吗，今晚吃什么？", False),
    ("你现在已经没有这种念头。", False),
    ("今晚吃什么？现在有没有自杀的想法呢？", True),
    # 泛指的"想法/念头"不是风险词：不能把它们当作已核验（否则会少补一次固定话术）
    ("现在你有什么想法吗？", False),
    ("现在你对睡眠有什么念头吗？", False),
    ("你最近睡得怎么样，有没有想法让作息规律一点？", False),
    ("你最近还有这样的念头吗？", True),
    ("现在：有没有这样的念头，或者伤害自己的行为？", True),
    ("现在,有没有这样的念头,或者伤害自己的行为?", True),
    ("有没有这样的念头，现在睡得好吗？", False),
    ("现在已经没有这种念头，有没有睡好？", False),
    ("现在没有这种念头，睡得好吗？", False),
    ("近 1 个月，有自伤行为？", True),
    ("近一个月，有自伤行为？", True),
])
def test_s3_clause_level_verification(text, expected):
    assert SafetyLayer(judge=PassiveJudge()).check_verification(text) is expected


@pytest.mark.parametrize("boundary", ["。", "！", "!", "？", "?", "；", ";", "\n"])
def test_s3_time_does_not_cross_sentence_boundary(boundary):
    layer = SafetyLayer(judge=PassiveJudge())
    assert not layer.check_verification(f"现在先聊睡眠{boundary}有没有自伤的想法？")


@pytest.mark.parametrize("avoid", [
    "不用", "不必", "无需", "不要", "不需要", "没必要", "不能", "不会",
    "别", "不想", "不打算", "避免", "禁止", "不再",
])
def test_s3_avoiding_risk_question_is_not_verification(avoid):
    assert not SafetyLayer(judge=PassiveJudge()).check_verification(
        f"现在{avoid}继续确认你有没有自杀的想法？"
    )


def test_s3_reviewed_history_script_is_unchanged():
    assert SafetyLayer(judge=PassiveJudge()).script_for("history_check") == (
        "谢谢你愿意说出来，这不容易，我只想确认现在的情况：最近一个月，你还有没有这样的念头，或者伤害自己的行为？"
    )
