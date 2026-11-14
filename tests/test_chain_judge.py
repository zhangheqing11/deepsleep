import asyncio
import sys

import pytest

from safety.config import load_config
from safety.eval import evaluate, main
from safety.judges import ChainJudge, JudgeResult, make_judge
from safety.layer import SafetyLayer, SessionSafetyState

PROBS = {"none": 0., "history": 0., "passive": 1., "active": 0.}


class FakeJudge:
    def __init__(self, provider, status="ok", *, timeout=.05, delay=0, raises=None):
        self.provider, self.status, self.timeout = provider, status, timeout
        self.delay, self.raises, self.calls = delay, raises, 0

    async def classify(self, text):
        self.calls += 1
        await asyncio.sleep(self.delay)
        if self.raises:
            raise self.raises("offline failure")
        return JudgeResult(PROBS if self.status == "ok" else None, self.status, self.provider, 1.)


@pytest.mark.parametrize("status", ["ok", "timeout", "error"])
def test_first_success_provider_and_attempt_counts(status):
    primary, fallback = FakeJudge("ds_flash", status), FakeJudge("jev")
    layer = SafetyLayer(judge=ChainJudge(primary, [fallback]))
    state = SessionSafetyState()
    event = asyncio.run(layer.assess_text("最近早醒", 1, 1, state))
    assert event.judge_provider == ("ds_flash" if status == "ok" else "jev")
    assert event.judge_status == "ok"
    assert fallback.calls == (status != "ok")
    assert state.judge_failures == (status != "ok")
    assert [r.provider for r in state.judge_results] == (["ds_flash"] if status == "ok" else ["ds_flash", "jev"])


@pytest.mark.parametrize("text,level", [("撑不下去了", "passive"), ("最近早醒", "none")])
@pytest.mark.parametrize("last_status", ["timeout", "error"])
def test_all_fail_retains_rule_fallback(text, level, last_status):
    chain = ChainJudge(FakeJudge("ds_flash", "error"), [FakeJudge("jev", last_status)])
    state = SessionSafetyState()
    event = asyncio.run(SafetyLayer(judge=chain).assess_text(text, 1, 1, state))
    assert (event.level if event else "none") == level
    assert state.judge_failures == 2
    assert [(r.provider, r.status) for r in state.judge_results] == [("ds_flash", "error"), ("jev", last_status)]
    if event:
        assert (event.source, event.judge_provider, event.judge_status) == ("rule_ambiguous", "jev", last_status)


@pytest.mark.parametrize("raises", [TimeoutError, RuntimeError])
def test_raised_failure_tries_next_without_waiting_for_budget(raises):
    chain = ChainJudge(FakeJudge("primary", raises=raises), [FakeJudge("fallback")])
    result = asyncio.run(chain.classify("test"))
    assert result.provider == "fallback"
    assert [r.status for r in result.attempts] == ["timeout" if raises is TimeoutError else "error", "ok"]


def test_outer_timeout_covers_entire_chain_and_bounds_hanging_primary():
    primary = FakeJudge("ds_flash", timeout=.02, delay=1)
    fallback = FakeJudge("jev", timeout=.3, delay=.16)
    chain = ChainJudge(primary, [fallback])
    assert chain.timeout == pytest.approx(.32)
    state = SessionSafetyState()
    event = asyncio.run(SafetyLayer({"judge_timeout_s": .02}, judge=chain).assess_text("最近早醒", 1, 1, state))
    assert event.judge_provider == "jev"
    assert event.judge_status == "ok"
    assert state.judge_failures == 1


def test_multiple_fallbacks_and_concurrent_calls_keep_separate_records():
    chain = ChainJudge(FakeJudge("first", "timeout"), [FakeJudge("second", "error"), FakeJudge("third")])
    async def run():
        return await asyncio.gather(*(chain.classify(str(i)) for i in range(4)))
    results = asyncio.run(run())
    for result in results:
        assert result.provider == "third"
        assert [r.status for r in result.attempts] == ["timeout", "error", "ok"]
    assert len({id(result.attempts) for result in results}) == 4


def setup_primary(monkeypatch):
    monkeypatch.setenv("DS_API_KEY", "offline-placeholder")
    monkeypatch.setenv("DS_MODEL", "offline-model")
    monkeypatch.setenv("DS_BASE_URL", "https://offline.invalid")


@pytest.mark.parametrize("missing", ["key", "sdk"])
def test_unavailable_fallback_skipped_in_engine_but_strict_chain_rejects(monkeypatch, missing):
    setup_primary(monkeypatch)
    if missing == "sdk":
        monkeypatch.setenv("TYPESAFE_API_KEY", "offline-placeholder")
        monkeypatch.setitem(sys.modules, "typesafe_sdk", None)
    judge = make_judge()
    assert judge.provider == "ds_flash"
    assert not isinstance(judge, ChainJudge)
    with pytest.raises(ValueError, match="缺少"):
        make_judge(allow_fallback=False, chain=True)
    assert make_judge(allow_fallback=False).provider == "ds_flash"


def test_factory_timeouts_and_single_provider_evaluation(monkeypatch):
    import safety.judges as judges
    setup_primary(monkeypatch)
    monkeypatch.setenv("TYPESAFE_API_KEY", "offline-placeholder")
    monkeypatch.setattr(judges, "JevJudge", lambda config: FakeJudge("jev", timeout=config["judge_timeout_s"]))
    chain = make_judge()
    assert isinstance(chain, ChainJudge)
    assert (chain.primary.timeout, chain.fallbacks[0].timeout, chain.timeout) == (6., 3., 9.)
    assert make_judge(allow_fallback=False).provider == "ds_flash"
    # A provider override applies to a primary, never to the fallback's 3s budget.
    chain = make_judge({"judge_timeout_overrides": {"ds_flash": 8., "jev": 10.}})
    assert (chain.primary.timeout, chain.fallbacks[0].timeout) == (8., 3.)


@pytest.mark.parametrize("key,value", [
    ("judge_fallbacks", "jev"), ("judge_fallbacks", None),
    ("judge_fallbacks", ["unknown"]), ("judge_fallbacks", ["mock"]),
    ("judge_fallbacks", [{}]), ("judge_fallbacks", [True]),
    ("judge_fallback_timeout_s", 0), ("judge_fallback_timeout_s", -1),
    ("judge_fallback_timeout_s", True), ("judge_fallback_timeout_s", "3"),
    ("judge_fallback_timeout_s", float("inf")), ("judge_fallback_timeout_s", float("nan")),
])
def test_config_rejects_invalid_fallbacks(key, value):
    with pytest.raises(ValueError, match=key):
        load_config({key: value})


def test_eval_chain_records_every_attempt_and_explicit_single_has_no_chain(monkeypatch, tmp_path, capsys):
    import json
    import safety.eval as evaluation
    seen = []
    def factory(config, **kwargs):
        seen.append((config["judge_provider"], kwargs))
        return ChainJudge(FakeJudge("ds_flash", "timeout"), [FakeJudge("jev")])
    monkeypatch.setattr(evaluation, "make_judge", factory)
    monkeypatch.setattr(evaluation, "load_repo_env", lambda: None)
    report = asyncio.run(evaluate([{"id": "1", "text": "最近早醒", "label": "passive"}], "chain"))
    assert seen[-1] == ("ds_flash", {"allow_fallback": False, "chain": True})
    assert report["judge"]["calls"] == 2
    assert report["judge"]["failures"] == 1
    assert report["judge"]["providers"] == {"ds_flash": 1, "jev": 1}
    asyncio.run(evaluate([], "jev"))
    assert seen[-1] == ("jev", {"allow_fallback": False})
    main(["--provider", "chain", "--output-dir", str(tmp_path)])
    assert json.loads(capsys.readouterr().out)["requested_provider"] == "chain"


def test_ds_fallback_missing_sdk_is_skipped(monkeypatch):
    setup_primary(monkeypatch)
    monkeypatch.setenv("STARTLUX_API_KEY", "offline-placeholder")
    monkeypatch.setitem(sys.modules, "openai", None)
    judge = make_judge({"judge_provider": "startlux", "judge_fallbacks": ["ds_flash"]})
    assert judge.provider == "startlux"
    assert judge.timeout == 8.


def test_empty_fallback_list_uses_single_judge(monkeypatch):
    setup_primary(monkeypatch)
    judge = make_judge({"judge_fallbacks": []})
    assert judge.provider == "ds_flash"
    assert judge.timeout == 6.
