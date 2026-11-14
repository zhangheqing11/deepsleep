"""Decisions protocol tests: no google-genai installation or network needed."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

try:
    import httpx
except ImportError:
    import httpx2 as httpx
import pytest

from safety.judges import GeminiDecisionJudge, MockJudge, make_judge


PROBS = {"none": .1, "history": 0., "passive": .3, "active": .6}


def response(**overrides):
    return SimpleNamespace(answers={"risk": SimpleNamespace(
        **{"choice": "active", "probabilities": PROBS, "confidence": .6, **overrides}
    )})


def fake_client(request):
    return SimpleNamespace(aio=SimpleNamespace(decisions=SimpleNamespace(create=request)))


def test_gemini_success_and_frozen_question():
    async def request(**kwargs):
        assert kwargs["model"] == "gemini-decision-1"
        assert kwargs["input"] == "模拟发言"
        question = kwargs["questions"]["risk"]
        assert question["type"] == "choice"
        assert set(question["criteria"]) == set(PROBS)
        assert all(isinstance(v, str) and v.strip() for v in question["criteria"].values())
        assert "近 1 个月" in question["instructions"]
        assert "拿不准时偏向 passive" in question["instructions"]
        assert "不再醒来" in question["criteria"]["passive"]
        assert "自伤准备" in question["criteria"]["active"]
        assert "明确否认" in question["criteria"]["none"]
        return response()

    result = asyncio.run(GeminiDecisionJudge(client=fake_client(request)).classify("模拟发言"))
    assert (result.status, result.provider, result.probs) == ("ok", "gemini_decision", PROBS)
    assert result.latency_ms >= 0


@pytest.mark.parametrize("bad", [
    {"none": 1., "history": 0., "passive": 0.},
    {"none": -1., "history": 0., "passive": 1., "active": 1.},
    {"none": float("nan"), "history": 0., "passive": 0., "active": 0.},
    {"none": float("inf"), "history": 0., "passive": 0., "active": 0.},
    {"none": True, "history": 0., "passive": 0., "active": 0.},
    {"none": .1, "history": 0., "passive": .1, "active": .1},
    {"none": "1", "history": 0., "passive": 0., "active": 0.},
    {**PROBS, "extra": 0.}, None, [],
])
def test_gemini_invalid_probabilities(bad):
    async def request(**kwargs):
        return response(probabilities=bad)

    result = asyncio.run(GeminiDecisionJudge(client=fake_client(request)).classify("模拟发言"))
    assert (result.status, result.probs) == ("error", None)


@pytest.mark.parametrize("answer", [
    response(choice="unknown"), response(confidence=float("nan")),
    response(confidence=True), response(confidence=".6"), response(confidence=2),
    SimpleNamespace(answers={}), SimpleNamespace(answers={"risk": SimpleNamespace(choice="active")}),
])
def test_gemini_malformed_answers(answer):
    async def request(**kwargs):
        return answer

    result = asyncio.run(GeminiDecisionJudge(client=fake_client(request)).classify("模拟发言"))
    assert (result.status, result.probs) == ("error", None)


@pytest.mark.parametrize("mode", ["deadline", "transport", "sdk"])
def test_gemini_timeout(mode, monkeypatch):
    class APITimeoutError(Exception):
        pass

    monkeypatch.setitem(sys.modules, "google.genai._interactions",
                        SimpleNamespace(APITimeoutError=APITimeoutError))

    async def request(**kwargs):
        if mode == "transport":
            raise httpx.ReadTimeout("offline timeout")
        if mode == "sdk":
            raise APITimeoutError("offline SDK timeout")
        await asyncio.Event().wait()

    result = asyncio.run(GeminiDecisionJudge(
        {"judge_timeout_s": .01}, client=fake_client(request)
    ).classify("模拟发言"))
    assert (result.status, result.probs) == ("timeout", None)


@pytest.mark.parametrize("code", [400, 402, 404, 429, 500])
def test_gemini_http_errors(code):
    async def request(**kwargs):
        request = httpx.Request("POST", "https://offline.invalid/v1beta/decisions")
        raise httpx.HTTPStatusError("offline error", request=request,
                                    response=httpx.Response(code, request=request))

    result = asyncio.run(GeminiDecisionJudge(client=fake_client(request)).classify("模拟发言"))
    assert (result.status, result.probs) == ("error", None)


def test_gemini_missing_key():
    judge = make_judge({"judge_provider": "gemini_decision"})
    assert not isinstance(judge, MockJudge)
    result = asyncio.run(judge.classify("模拟发言"))
    assert (result.provider, result.status, result.probs) == ("gemini_decision", "error", None)


def test_gemini_missing_sdk(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "offline-key")
    monkeypatch.setitem(sys.modules, "google.genai", None)
    monkeypatch.setitem(sys.modules, "google", SimpleNamespace())
    with pytest.raises(ImportError, match="requirements-optional.txt"):
        GeminiDecisionJudge()
    assert asyncio.run(make_judge({"judge_provider": "gemini_decision"}).classify("普通发言")).status == "error"


@pytest.mark.parametrize("key", ["GEMINI_API_KEY", "GOOGLE_API_KEY"])
@pytest.mark.parametrize("status", ["ok", "error", "timeout"])
def test_gemini_sdk_construction_and_cleanup(monkeypatch, key, status):
    seen = {}

    class AsyncClient:
        def __init__(self):
            self.decisions = SimpleNamespace(create=self.create)

        async def create(self, **kwargs):
            if status == "error":
                raise RuntimeError("offline error")
            if status == "timeout":
                await asyncio.Event().wait()
            return response()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            seen["async_closed"] = True

    class Client:
        def __init__(self, **kwargs):
            seen.update(kwargs)
            self.aio = AsyncClient()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            seen["sync_closed"] = True

    monkeypatch.setenv(key, "offline-key")
    monkeypatch.setitem(sys.modules, "google", SimpleNamespace(genai=SimpleNamespace(Client=Client)))
    judge = make_judge({"judge_provider": "gemini_decision", "judge_timeout_s": .01})
    assert asyncio.run(judge.classify("模拟发言")).status == status
    assert seen["api_key"] == "offline-key"
    assert seen["http_options"]["api_version"] == "v1beta"
    assert seen["http_options"]["timeout"] == 10
    assert seen["http_options"]["retry_options"] == {"attempts": 1}
    assert seen["async_closed"] and seen["sync_closed"]


def test_gemini_eval_cli_without_key(tmp_path):
    result = subprocess.run([
        sys.executable, "-m", "safety.eval", "--provider", "gemini_decision",
        "--output-dir", str(tmp_path),
    ], cwd=Path(__file__).resolve().parents[1], env={**os.environ, **{"GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}},
        capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    assert "评测 gemini_decision 缺少 API key" in result.stderr
    report = json.loads(result.stdout)
    assert report["provider"] == "gemini_decision"
    assert report["judge"]["statuses"] == {"error": 46}
    assert report["warnings"]
    assert report["evaluation_columns"]["真实判断器"]["status"] == "未测"
    assert len(list(tmp_path.iterdir())) == 1


@pytest.mark.parametrize("include_history", [True, False])
def test_gemini_history_four_key_parsing(include_history):
    probs = {"none": 0., "history": 1., "passive": 0., "active": 0.}
    if not include_history:
        probs = {"none": 1., "passive": 0., "active": 0.}

    async def request(**kwargs):
        assert "过去且已结束" in kwargs["questions"]["risk"]["criteria"]["history"]
        return response(choice="history", probabilities=probs, confidence=1.)

    result = asyncio.run(GeminiDecisionJudge(client=fake_client(request)).classify("模拟历史风险"))
    assert result.status == ("ok" if include_history else "error")
    assert result.probs == (probs if include_history else None)
