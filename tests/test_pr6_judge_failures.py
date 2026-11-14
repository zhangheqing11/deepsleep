"""PR #6 review counterexamples; independent of the frozen evaluation set."""
import asyncio

import pytest
from safety.judges import JudgeResult, MockJudge, make_judge
from safety.layer import SafetyLayer, SessionSafetyState


class FixedJudge:
    def __init__(self, label="passive", status="ok"):
        self.label, self.status, self.calls = label, status, 0

    async def classify(self, text):
        self.calls += 1
        return JudgeResult({k: float(k == self.label) for k in ("none", "history", "passive", "active")}
                           if self.status == "ok" else None, self.status, "offline", 0.)


def test_s1_default_missing_keys_preserves_ambiguous_fallback():
    state = SessionSafetyState()
    event = asyncio.run(SafetyLayer().assess_text("我只想早点解脱", 1, 1, state))
    assert event is not None
    assert (event.level, event.action, event.source, event.judge_status) == (
        "passive", "safety_check", "rule_ambiguous", "error")
    assert event.judge_probs is None
    assert all(r.status == "error" and not r.provider.startswith("mock") for r in state.judge_results)
    assert state.judge_failures == len(state.judge_results) > 0


@pytest.mark.parametrize("provider", ["ds_flash", "jev", "gemini_decision", "startlux"])
def test_s1_unavailable_provider_is_never_a_successful_mock(provider):
    judge = make_judge({"judge_provider": provider, "judge_fallbacks": []})
    assert not isinstance(judge, MockJudge)
    result = asyncio.run(judge.classify("普通发言"))
    assert (result.status, result.provider, result.probs) == ("error", provider, None)



def test_s1_missing_primary_can_use_available_real_fallback(monkeypatch):
    import safety.judges as judges
    monkeypatch.setenv("TYPESAFE_API_KEY", "offline-placeholder")

    class AvailableJudge(FixedJudge):
        provider = "jev"

    monkeypatch.setattr(judges, "JevJudge", lambda config: AvailableJudge())
    state = SessionSafetyState()
    event = asyncio.run(SafetyLayer().assess_text("最近早醒", 1, 1, state))
    assert event.level == "passive" and event.judge_status == "ok"
    assert [r.status for r in state.judge_results] == ["error", "ok"]
    assert state.judge_results[0].provider == "ds_flash"


def test_s1_partial_ds_configuration_reports_error(monkeypatch):
    monkeypatch.setenv("DS_API_KEY", "offline-placeholder")
    result = asyncio.run(make_judge().classify("最近早醒"))
    assert (result.status, result.provider, result.probs) == ("error", "ds_flash", None)


def test_s1_no_env_cli_never_opens_dotenv(monkeypatch, tmp_path):
    import safety.eval as evaluation
    monkeypatch.delenv("SAFETY_EVAL_NO_DOTENV", raising=False)

    def forbidden():
        pytest.fail("--no-env must not read dotenv")

    monkeypatch.setattr(evaluation, "load_repo_env", forbidden)
    with pytest.raises(SystemExit) as error:
        evaluation.main(["--no-env", "--provider", "ds_flash", "--output-dir", str(tmp_path)])
    assert error.value.code == 2
    assert not list(tmp_path.iterdir())
