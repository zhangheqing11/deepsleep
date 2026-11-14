"""Provider-boundary tests: SDK is mocked, reflector parsing/fallback is real."""
import asyncio
import json
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest

from engine.evolve import llm
from engine.evolve.config import load_config
from engine.evolve.reflector import reflect
from evolve_support import FIXTURE_INITIAL, MockLLM, change, example, reply

GOOD = reply(*[[change("questioning_strategy", f"先询问作息细节{i}。")] for i in range(3)])


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in ("REFLECTOR_PROVIDER", "REFLECTOR_MODEL", "REFLECTOR_REASONING_EFFORT", "REFLECTOR_TIMEOUT_S"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DS_API_KEY", "test-ds-key")
    monkeypatch.setenv("DS_MODEL", "ds-flash")


def response(**kwargs):
    return NS(**{"status": "completed", "output_text": json.dumps(GOOD), "output": [],
                 "model": "gpt-6-astra", "reasoning": NS(effort="xhigh"),
                 "usage": NS(output_tokens_details=NS(reasoning_tokens=123)), **kwargs})


def sdk(monkeypatch, result=None, error=None):
    create = AsyncMock(return_value=result or response(), side_effect=error)
    clients = []
    def factory(**kwargs):
        client = NS(responses=NS(create=create), chat=NS(completions=NS(
            create=AsyncMock(return_value=NS(model="ds-flash", usage=None,
                choices=[NS(finish_reason="stop", message=NS(content=json.dumps(GOOD), refusal=None))])))))
        clients.append((kwargs, client))
        return client
    monkeypatch.setattr("openai.AsyncOpenAI", factory)
    return create, clients


def run_reflection(config, primary, fallback, error=None):
    return asyncio.run(reflect(playbook_text=FIXTURE_INITIAL.read_text(), version="v1",
        run_report=example("run_report.run1.json"), sessions={}, feedback=[], config=config,
        primary=primary, fallback=fallback, primary_error=error))


def test_openai_responses_success_and_usage(monkeypatch):
    create, clients = sdk(monkeypatch)
    config = load_config()
    primary, fallback, error = llm.default_clients(config)
    result = run_reflection(config, primary, fallback, error)
    assert not result.fell_back
    assert all(c["changes"] for c in result.candidates)
    assert result.provider == "openai" and result.reasoning_effort == "xhigh"
    assert result.model == "gpt-6-astra"
    call = create.call_args.kwargs
    assert call["reasoning"] == {"effort": "xhigh"}
    # JSON is requested by the existing prompt and validated locally. Do not add
    # legacy JSON mode: the initial real request with it returned HTTP 400.
    assert "text" not in call
    assert clients[0][0]["timeout"] == 300
    assert clients[0][0]["max_retries"] == 0
    assert result.attempts[0]["reasoning_tokens"] == 123
    assert result.attempts[0]["duration_s"] >= 0
    assert result.attempts[0]["success"] is True


@pytest.mark.parametrize("case", ["timeout", "error", "json", "empty", "refusal", "incomplete", "unusable"])
def test_openai_failure_falls_back_with_both_attempts(monkeypatch, case):
    result = response()
    error = None
    if case == "timeout":
        error = asyncio.TimeoutError()
    elif case == "error":
        error = RuntimeError("service unavailable")
    elif case == "json":
        result.output_text = "{invalid JSON}"
    elif case == "empty":
        result.output_text = ""
    elif case == "refusal":
        result.output = [NS(type="message", content=[NS(type="refusal", refusal="no")])]
    elif case == "incomplete":
        result.status = "incomplete"
    elif case == "unusable":
        result.output_text = '{"candidates": []}'
    sdk(monkeypatch, result, error)
    config = load_config()
    primary, fallback, init_error = llm.default_clients(config)
    reflection = run_reflection(config, primary, fallback, init_error)
    assert reflection.fell_back and reflection.fallback_reason
    assert reflection.model == "ds-flash" and reflection.provider == "deepseek"
    assert reflection.reasoning_effort is None
    assert len(reflection.candidates) == 3 and all(c["changes"] for c in reflection.candidates)
    assert [a["success"] for a in reflection.attempts] == [False, True]
    assert reflection.attempts[0]["error"]
    assert all(a["duration_s"] >= 0 for a in reflection.attempts)


@pytest.mark.parametrize("provider,model,effort", [
    ("openai", "gpt-6-astra", "xhigh"), ("anthropic", "claude-opus-5-5", "high")])
def test_provider_switch_by_env_or_config(monkeypatch, provider, model, effort):
    sdk(monkeypatch)
    monkeypatch.setattr("anthropic.AsyncAnthropic", lambda **kwargs: NS())
    for config in (load_config({"reflector": {"primary_provider": provider}}), load_config()):
        monkeypatch.setenv("REFLECTOR_PROVIDER", provider)
        primary, _, error = llm.default_clients(config)
        assert error is None
        assert (primary.provider, primary.model, primary.effort) == (provider, model, effort)
        monkeypatch.delenv("REFLECTOR_PROVIDER")
    primary, _, error = llm.default_clients(load_config({"reflector": {"primary_provider": provider}}))
    assert error is None and primary.provider == provider


def test_env_model_effort_and_outer_timeout(monkeypatch):
    sdk(monkeypatch)
    monkeypatch.setenv("REFLECTOR_MODEL", "custom-model")
    monkeypatch.setenv("REFLECTOR_REASONING_EFFORT", "high")
    monkeypatch.setenv("REFLECTOR_TIMEOUT_S", "0.01")
    config = load_config()
    primary, fallback, error = llm.default_clients(config)
    assert (primary.model, primary.effort, primary.timeout_s) == ("custom-model", "high", 0.01)
    async def slow(*args, **kwargs):
        await asyncio.sleep(1)
    primary._client.responses.create = slow
    result = run_reflection(config, primary, fallback, error)
    assert result.fell_back and "超时" in result.fallback_reason
    assert result.attempts[0]["duration_s"] < 0.5


def test_missing_openai_key_falls_back(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    config = load_config()
    primary, _, error = llm.default_clients(config)
    assert primary is None and error
    result = run_reflection(config, primary, MockLLM(GOOD, model="ds-flash"), error)
    assert result.fell_back and all(c["changes"] for c in result.candidates)


def test_anthropic_still_works(monkeypatch):
    sdk(monkeypatch)
    create = AsyncMock(return_value=NS(model="claude-opus-5-5", stop_reason="end_turn",
                                      content=[NS(type="text", text=json.dumps(GOOD))]))
    monkeypatch.setattr("anthropic.AsyncAnthropic", lambda **kwargs: NS(messages=NS(create=create)))
    monkeypatch.setenv("REFLECTOR_PROVIDER", "anthropic")
    config = load_config()
    result = run_reflection(config, *llm.default_clients(config))
    assert not result.fell_back and result.provider == "anthropic"
    assert result.reasoning_effort == "high"
    assert create.call_args.kwargs["output_config"] == {"effort": "high"}
    assert result.attempts[0]["reasoning_tokens"] is None


def test_response_model_and_effort_are_recorded(monkeypatch):
    sdk(monkeypatch, response(model="gpt-6-astra-snapshot", reasoning=NS(effort="high")))
    config = load_config()
    result = run_reflection(config, *llm.default_clients(config))
    assert result.model == "gpt-6-astra-snapshot" and result.reasoning_effort == "high"


def test_usage_not_carried_from_previous_call(monkeypatch):
    create, _ = sdk(monkeypatch)
    config = load_config()
    primary, fallback, error = llm.default_clients(config)
    assert run_reflection(config, primary, fallback, error).attempts[0]["reasoning_tokens"] == 123
    create.side_effect = TimeoutError()
    result = run_reflection(config, primary, fallback, error)
    assert result.attempts[0]["reasoning_tokens"] is None


@pytest.mark.parametrize("provider", ["openai", "unsupported"])
def test_no_clients_never_claims_success(monkeypatch, provider):
    monkeypatch.setenv("REFLECTOR_PROVIDER", provider)
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.delenv("DS_API_KEY")
    config = load_config()
    result = run_reflection(config, *llm.default_clients(config))
    assert result.fell_back and result.model == "unavailable"
    assert result.provider is None and result.attempts == []
    assert all(not c["changes"] for c in result.candidates)


@pytest.mark.parametrize("fall_back", [False, True])
def test_reports_preserve_provider_metadata_without_contract_changes(monkeypatch, tmp_path, fall_back):
    from engine.evolve.pipeline import evolve
    from evolve_support import BASELINE, MockEvaluator, contract_validator, make_config

    sdk(monkeypatch, error=RuntimeError("failure") if fall_back else None)
    # Read-only in-memory repo: no git init/commit needed to verify report serialization.
    repo = NS(init=lambda: None, current_version=lambda: "v1", read=lambda: FIXTURE_INITIAL.read_text())
    config = make_config(tmp_path)
    evolution, insights = asyncio.run(evolve(
        run_report=example("run_report.run1.json"), sessions={}, config=config, repo=repo,
        evaluator=MockEvaluator(), baseline_val_metrics=BASELINE,
        evolution_id="provider-report", return_insights=True))
    assert contract_validator()(evolution) == []
    assert evolution["reflector"]["fell_back"] is fall_back
    assert set(evolution["reflector"]) == {"model", "fell_back", "fallback_reason"}
    metadata = insights["reflector"]
    assert metadata["provider"] == ("deepseek" if fall_back else "openai")
    assert metadata["reasoning_effort"] == (None if fall_back else "xhigh")
    assert len(metadata["attempts"]) == (2 if fall_back else 1)
    path = tmp_path / "var/evolve/provider-report/insights.json"
    assert json.loads(path.read_text())["reflector"] == metadata


def test_sdk_error_diagnostics_exclude_response_body():
    import httpx
    import openai

    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    error = openai.BadRequestError("secret echoed by service", response=httpx.Response(400, request=request),
        body={"message": "secret echoed by service", "type": "invalid_request_error",
              "code": "unsupported_value", "param": "text.format.type"})
    assert llm.error_reason(error) == (
        "BadRequestError (HTTP 400) code=unsupported_value param=text.format.type")
    assert llm.error_reason(openai.APITimeoutError(request=request)) == "超时"


def test_yaml_model_effort_and_timeout(monkeypatch):
    sdk(monkeypatch)
    config = load_config({"reflector": {"primary_model": "config-model", "primary_effort": "high",
                                         "primary_timeout_s": 42}})
    primary, _, error = llm.default_clients(config)
    assert error is None
    assert (primary.model, primary.effort, primary.timeout_s) == ("config-model", "high", 42)
