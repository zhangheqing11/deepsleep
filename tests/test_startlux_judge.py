"""StartLux native wire protocol, exercised only through MockTransport."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys

import httpx
import pytest

from safety.config import load_config
from safety.judges import DsFlashJudge, MockJudge, StartLuxJudge, make_judge


PROBS = {"active": .03, "passive": .02, "history": .9, "none": .05}


def response_body(**overrides):
    return {"answers": {"risk": {
        "type": "choice", "choice": "history", "confidence": .8666667,
        "probabilities": PROBS, **overrides,
    }}, "model": "startlux-decision-27b-autothink"}


def classify(handler, config=None):
    return asyncio.run(StartLuxJudge(
        config, transport=httpx.MockTransport(handler),
    ).classify("以前想过自伤，现在没有了。"))


def test_native_request_order_defaults_and_probability_mapping(monkeypatch):
    monkeypatch.setenv("STARTLUX_API_KEY", "offline-key")
    # Blank optional variables from .env.example must still use defaults.
    monkeypatch.setenv("STARTLUX_BASE_URL", " ")
    monkeypatch.setenv("STARTLUX_MODEL", " ")
    seen = []

    def handler(request):
        seen.append(request)
        assert request.method == "POST"
        assert str(request.url) == "https://api.bamboonode.dev/v1/decisions"
        assert request.headers["authorization"] == "Bearer offline-key"
        assert request.extensions["timeout"]["read"] == 8.0
        body = json.loads(request.content)
        assert body["model"] == "startlux-decision-27b-autothink"
        assert body["state"] == {"text": "以前想过自伤，现在没有了。"}
        assert body["none_check"] is False
        assert body["allow_none"] is False
        assert list(body["questions"]) == ["risk"]
        question = body["questions"]["risk"]
        assert question["type"] == "choice"
        assert list(question["criteria"]) == ["active", "passive", "history", "none"]
        frozen = json.loads((Path(__file__).resolve().parents[1]
                             / "safety/prompts/gemini_decision_zh.json").read_text())
        assert question["criteria"] == frozen["criteria"]
        assert question["instructions"] == frozen["instructions"]
        return httpx.Response(200, json=response_body(none_probability=.99))

    result = classify(handler)
    assert len(seen) == 1
    assert (result.status, result.provider, result.probs) == ("ok", "startlux", PROBS)
    assert result.latency_ms >= 0


@pytest.mark.parametrize("base, expected", [
    ("http://localhost:8090", "http://localhost:8090/v1/decisions"),
    ("http://localhost:8090/v1/", "http://localhost:8090/v1/decisions"),
    ("http://localhost:8090/v1/systemone", "http://localhost:8090/v1/systemone"),
    ("http://localhost:8090/v1/decisions/", "http://localhost:8090/v1/decisions"),
])
def test_custom_endpoint_and_model(base, expected, monkeypatch):
    monkeypatch.setenv("STARTLUX_BASE_URL", base)
    monkeypatch.setenv("STARTLUX_MODEL", "local-model")

    def handler(request):
        assert str(request.url) == expected
        assert json.loads(request.content)["model"] == "local-model"
        return httpx.Response(200, json=response_body())

    assert classify(handler).status == "ok"


@pytest.mark.parametrize("probs", [
    {"none": 1., "passive": 0., "active": 0.},
    {**PROBS, "extra": 0},
    {**PROBS, "none": "0.05"},
    {**PROBS, "none": True},
    {**PROBS, "none": -.1},
    {**PROBS, "history": .1},
    [0., 0., 0., 1.], None,
])
def test_invalid_probabilities_are_error(probs):
    result = classify(lambda request: httpx.Response(
        200, json=response_body(probabilities=probs)))
    assert (result.status, result.probs) == ("error", None)


@pytest.mark.parametrize("body", [
    {}, {"answers": {}}, {"answers": {"risk": []}},
    response_body(choice=None), response_body(choice="unknown"),
    response_body(confidence=None), response_body(confidence=True),
    response_body(confidence=1.1), response_body(type="score"),
])
def test_malformed_answers_are_error(body):
    result = classify(lambda request: httpx.Response(200, json=body))
    assert (result.status, result.probs) == ("error", None)


def test_invalid_json_is_error():
    result = classify(lambda request: httpx.Response(200, text="not JSON"))
    assert (result.status, result.probs) == ("error", None)


@pytest.mark.parametrize("status", [401, 429, 500, 502, 503])
def test_http_errors_do_not_retry_or_raise(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error": "offline failure"})

    result = classify(handler)
    assert (result.status, result.probs) == ("error", None)
    assert len(calls) == 1


@pytest.mark.parametrize("timeout_type", [httpx.ConnectTimeout, httpx.ReadTimeout,
                                         httpx.WriteTimeout, httpx.PoolTimeout])
def test_httpx_timeouts_are_timeout(timeout_type):
    def handler(request):
        raise timeout_type("offline timeout", request=request)

    result = classify(handler)
    assert (result.status, result.probs) == ("timeout", None)


def test_total_timeout_cancels_request_and_closes_transport():
    seen = {}

    async def handler(request):
        try:
            await asyncio.sleep(60)
        finally:
            seen["cancelled"] = True

    class TrackedTransport(httpx.MockTransport):
        async def aclose(self):
            seen["closed"] = True
            await super().aclose()

    result = asyncio.run(StartLuxJudge(
        {"judge_timeout_overrides": {"startlux": .01}},
        transport=TrackedTransport(handler),
    ).classify("模拟发言"))
    assert (result.status, result.probs) == ("timeout", None)
    assert seen == {"cancelled": True, "closed": True}


def test_provider_timeout_overrides_and_default():
    assert StartLuxJudge(transport=httpx.MockTransport(lambda r: None)).timeout == 8.0
    assert DsFlashJudge(client=object()).timeout == 2.5
    assert MockJudge().timeout == 2.5
    assert MockJudge({"judge_timeout_overrides": {"mock": .5}}).timeout == .5
    assert StartLuxJudge({"judge_timeout_s": .3, "judge_timeout_overrides": {}},
                         transport=httpx.MockTransport(lambda r: None)).timeout == .3


@pytest.mark.parametrize("overrides", [None, [], {"startlux": True}, {"startlux": 0},
                                     {"startlux": -1}, {"startlux": "8"},
                                     {"startlux": float("nan")}, {"startlux": float("inf")}])
def test_invalid_timeout_overrides_are_rejected(overrides):
    with pytest.raises(ValueError, match="judge_timeout_overrides"):
        load_config({"judge_timeout_overrides": overrides})


def test_factory_requires_key_and_accepts_env_provider(monkeypatch):
    assert make_judge({"judge_provider": "startlux"}).provider == "mock(fallback)"
    with pytest.raises(ValueError, match="STARTLUX_API_KEY"):
        StartLuxJudge()
    monkeypatch.setenv("STARTLUX_API_KEY", "offline-key")
    monkeypatch.setenv("JUDGE_PROVIDER", "startlux")
    judge = make_judge()
    assert isinstance(judge, StartLuxJudge)
    assert judge.timeout == 8.0


def test_eval_cli_without_key(tmp_path):
    result = subprocess.run([
        sys.executable, "-m", "safety.eval", "--provider", "startlux",
        "--output-dir", str(tmp_path),
    ], cwd=Path(__file__).resolve().parents[1], env=dict(os.environ),
        capture_output=True, text=True, check=True)
    report = json.loads(result.stdout)
    assert report["requested_provider"] == "startlux"
    assert report["provider"] == "mock(fallback)"
    assert report["judge"]["providers"] == {"mock(fallback)": report["judge"]["calls"]}
    saved = list(tmp_path.glob("startlux-*.json"))
    assert len(saved) == 1
    assert json.loads(saved[0].read_text()) == report
