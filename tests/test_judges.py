import asyncio
import json
import sys
from types import SimpleNamespace

import pytest

from safety.config import load_config
from safety.judges import DsFlashJudge, JevJudge, MockJudge, make_judge


PROBS = {"none": .1, "history": 0., "passive": .3, "active": .6}


@pytest.fixture
def fake_typesafe(monkeypatch):
    class Choice:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    monkeypatch.setitem(sys.modules, "typesafe_sdk", SimpleNamespace(AsyncTypeSafeClient=object, Choice=Choice))


@pytest.mark.parametrize("provider", ["ds_flash", "jev"])
@pytest.mark.parametrize("mode,expected", [("ok", "ok"), ("invalid", "error"), ("timeout", "timeout"), ("exception", "error")])
def test_adapters_offline(provider, mode, expected, fake_typesafe, monkeypatch):
    requests = []
    monkeypatch.setenv("DS_MODEL", "test-model")
    config = load_config({"judge_timeout_s": .01})

    async def request(**kwargs):
        requests.append(kwargs)
        if mode == "timeout":
            await asyncio.Event().wait()
        if mode == "exception":
            raise RuntimeError("simulated service failure")
        if provider == "ds_flash":
            content = "not json" if mode == "invalid" else json.dumps({"level": "active", "probs": PROBS})
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
        return SimpleNamespace(choices={"risk": SimpleNamespace(choice="active", probabilities={} if mode == "invalid" else PROBS)})

    if provider == "ds_flash":
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=request)))
        judge = DsFlashJudge(config, client=client)
    else:
        judge = JevJudge(config, client=SimpleNamespace(system_one=request))
    result = asyncio.run(judge.classify("测试发言"))
    assert (result.status, result.provider) == (expected, provider)
    assert result.latency_ms >= 0
    assert result.probs == (PROBS if mode == "ok" else None)
    if provider == "ds_flash":
        assert requests[0]["temperature"] == 0
        assert requests[0]["model"] == "test-model"
        assert requests[0]["response_format"] == {"type": "json_object"}
        assert "只输出 JSON" in requests[0]["messages"][0]["content"]
    else:
        assert list(requests[0]["questions"]["risk"].criteria) == ["active", "passive", "history", "none"]
        assert "近 1 个月" in requests[0]["questions"]["risk"].instructions


@pytest.mark.parametrize("bad", [
    {"none": 1., "history": 0., "passive": 0.},
    {"none": -1., "history": 0., "passive": 1., "active": 1.},
    {"none": float("nan"), "history": 0., "passive": 0., "active": 0.},
    {"none": float("inf"), "history": 0., "passive": 0., "active": 0.},
    {"none": True, "history": 0., "passive": 0., "active": 0.},
    {"none": .1, "history": 0., "passive": .1, "active": .1},
    {"none": "1", "history": 0., "passive": 0., "active": 0.},
    {"none": 1., "history": 0., "passive": 0., "active": 0., "extra": 0.},
])
def test_invalid_probabilities_become_error(bad):
    async def request(**kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"level": "none", "probs": bad})))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=request)))
    result = asyncio.run(DsFlashJudge(client=client).classify("test"))
    assert (result.status, result.probs) == ("error", None)


@pytest.mark.parametrize("provider", ["ds_flash", "jev"])
def test_missing_keys_fall_back(provider):
    judge = make_judge({"judge_provider": provider})
    assert not isinstance(judge, MockJudge)
    assert asyncio.run(judge.classify("普通发言")).status == "error"
    assert judge.provider == provider


def test_missing_optional_sdk(monkeypatch):
    monkeypatch.setitem(sys.modules, "typesafe_sdk", None)
    monkeypatch.setenv("TYPESAFE_API_KEY", "offline-test-key")
    with pytest.raises(ImportError, match="requirements-optional.txt"):
        JevJudge()
    assert asyncio.run(make_judge({"judge_provider": "jev"}).classify("普通发言")).status == "error"


def test_environment_provider_override(monkeypatch):
    monkeypatch.setenv("JUDGE_PROVIDER", "mock")
    assert make_judge().provider == "mock"
    assert asyncio.run(make_judge({"judge_provider": "ds_flash"}).classify("普通发言")).status == "error"


def test_mock_is_deterministic_and_bounded(monkeypatch):
    judge = MockJudge({"judge_timeout_s": .01})
    first = asyncio.run(judge.classify("我想结束生命"))
    assert first.probs == asyncio.run(judge.classify("我想结束生命")).probs
    assert first.probs["active"] == 1.

    async def blocked(text):
        await asyncio.Event().wait()

    monkeypatch.setattr(judge, "_predict", blocked)
    assert asyncio.run(judge.classify("test")).status == "timeout"


@pytest.mark.parametrize("provider", ["ds_flash", "jev"])
def test_real_adapter_constructor_uses_env_and_closes_fake_client(provider, monkeypatch, fake_typesafe):
    """Exercise SDK construction branch without credentials or network calls."""
    seen = {}

    class Client:
        def __init__(self, **kwargs):
            seen.update(kwargs)
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            seen["closed"] = True

        async def create(self, **kwargs):
            seen["model"] = kwargs["model"]
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"level": "active", "probs": PROBS})))])

        async def system_one(self, **kwargs):
            return SimpleNamespace(choices={"risk": SimpleNamespace(choice="active", probabilities=PROBS)})

    monkeypatch.setenv("DS_API_KEY", "offline-key")
    monkeypatch.setenv("DS_BASE_URL", "https://offline.invalid/v1")
    monkeypatch.setenv("DS_MODEL", "offline-model")
    monkeypatch.setenv("TYPESAFE_API_KEY", "offline-key")
    if provider == "ds_flash":
        import openai
        monkeypatch.setattr(openai, "AsyncOpenAI", Client)
    else:
        monkeypatch.setattr(sys.modules["typesafe_sdk"], "AsyncTypeSafeClient", Client)
    judge = make_judge({"judge_provider": provider, "judge_timeout_s": .3})
    assert asyncio.run(judge.classify("测试")).status == "ok"
    assert seen["api_key"] == "offline-key"
    assert seen["timeout"] == .3
    assert seen["closed"] is True
    if provider == "ds_flash":
        assert seen["base_url"] == "https://offline.invalid/v1"
        assert seen["model"] == "offline-model"
        assert seen["max_retries"] == 0


@pytest.mark.parametrize("provider", ["ds_flash", "jev"])
@pytest.mark.parametrize("include_history", [True, False])
def test_history_four_key_parsing(provider, include_history, fake_typesafe):
    probs = {"none": .1, "history": .9, "passive": 0., "active": 0.}
    if not include_history:
        probs = {"none": 1., "passive": 0., "active": 0.}

    async def request(**kwargs):
        if provider == "ds_flash":
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                content=json.dumps({"level": "history", "probs": probs})))])
        return SimpleNamespace(choices={"risk": SimpleNamespace(choice="history", probabilities=probs)})

    judge = (DsFlashJudge(client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=request))))
             if provider == "ds_flash" else JevJudge(client=SimpleNamespace(system_one=request)))
    result = asyncio.run(judge.classify("以前自伤过，现在没有了"))
    assert result.status == ("ok" if include_history else "error")
    assert result.probs == (probs if include_history else None)


@pytest.mark.parametrize("text,label", [
    ("以前有过不想活的念头，现在没有了", "history"),
    ("那时候曾经自伤过", "history"),
    ("早就不想自杀了", "history"),
    ("过去想结束生命，现在已经不再有了", "history"),
    ("以前想多睡一会儿", "none"),
    ("以前有过，现在仍然想自杀", "active"),
    ("以前有过，现在仍然不想活", "passive"),
    ("以前自伤过，现在仍然不想活", "passive"),
    ("以前自伤过，现在没有自伤，但最近希望不再醒来", "passive"),
])
def test_mock_history_keywords(text, label):
    result = asyncio.run(MockJudge().classify(text))
    assert result.status == "ok"
    assert result.probs[label] == 1.


def test_x9_hint_in_jev_state_not_instructions(fake_typesafe):
    from safety.layer import SafetyLayer, SessionSafetyState

    captured = {}

    async def request(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(choices={"risk": SimpleNamespace(choice="none", probabilities={
            "none": 1., "history": 0., "passive": 0., "active": 0.,
        })})

    judge = JevJudge(client=SimpleNamespace(system_one=request))
    asyncio.run(SafetyLayer(judge=judge).assess_text("周末不想醒", 1, 1, SessionSafetyState()))
    assert captured["state"]["text"] == "周末不想醒\n上下文提示：赖床/补觉语境"
    assert captured["questions"]["risk"].instructions == judge.prompt
    assert "上下文提示" not in str(captured["questions"]["risk"].criteria)
