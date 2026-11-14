"""Reflector providers: OpenAI Responses or Anthropic, then ds flash fallback.

All expose ``model`` and ``async complete(system, user) -> str`` and raise on any
failure (timeout, API error, refusal, empty output) so the caller can fall back.
TODO(S3): share the ds flash client with the session loop once engine-session lands.
"""
from __future__ import annotations

import math
import os
import re
from typing import Protocol


class LLMClient(Protocol):
    model: str

    async def complete(self, system: str, user: str) -> str: ...


class LLMError(RuntimeError):
    pass


def error_reason(exc: BaseException) -> str:
    """Do not persist SDK exception bodies (they may echo credentials or inputs)."""
    if isinstance(exc, TimeoutError) or type(exc).__name__ == "APITimeoutError":
        return "超时"
    if isinstance(exc, (LLMError, ValueError)):
        return f"{type(exc).__name__}: {exc}"[:300]
    status = getattr(exc, "status_code", None)
    reason = type(exc).__name__ + (f" (HTTP {status})" if status is not None else "")
    # SDK error codes/parameter names are useful diagnostics without response text.
    for name in ("code", "param"):
        value = getattr(exc, name, None)
        if isinstance(value, str) and re.fullmatch(r"[a-zA-Z0-9_.\[\]-]{1,80}", value):
            reason += f" {name}={value}"
    return reason


def primary_settings(config: dict) -> dict:
    rc = config["reflector"]
    provider = (os.environ.get("REFLECTOR_PROVIDER") or rc["primary_provider"]).strip().lower()
    prefix = "anthropic" if provider == "anthropic" else "primary"
    timeout = float(os.environ.get("REFLECTOR_TIMEOUT_S") or rc["primary_timeout_s"])
    if not math.isfinite(timeout) or timeout <= 0:
        raise LLMError("REFLECTOR_TIMEOUT_S 必须是有限正数")
    return {"provider": provider,
            "model": os.environ.get(rc["primary_model_env"]) or rc[f"{prefix}_model"],
            "effort": os.environ.get("REFLECTOR_REASONING_EFFORT") or rc[f"{prefix}_effort"],
            "timeout_s": timeout}


class OpenAIClient:
    """Native Responses API; SDK retries disabled so one attempt is one request."""

    provider = "openai"

    def __init__(self, model: str, *, timeout_s: float, max_tokens: int, effort: str = "xhigh"):
        from openai import AsyncOpenAI

        if not os.environ.get("OPENAI_API_KEY"):
            raise LLMError("未配置 OPENAI_API_KEY")
        self.model, self.effort, self.timeout_s = model, effort, timeout_s
        self.max_tokens = max_tokens
        self.last_response_metadata: dict = {}
        self._client = AsyncOpenAI(timeout=timeout_s, max_retries=0)

    async def complete(self, system: str, user: str) -> str:
        self.last_response_metadata = {}
        response = await self._client.responses.create(
            model=self.model, instructions=system, input=user,
            reasoning={"effort": self.effort}, max_output_tokens=self.max_tokens,
            store=False,
        )
        details = getattr(getattr(response, "usage", None), "output_tokens_details", None)
        self.last_response_metadata = {
            "model": response.model,
            "reasoning_effort": getattr(getattr(response, "reasoning", None), "effort", None) or self.effort,
            "reasoning_tokens": getattr(details, "reasoning_tokens", None),
        }
        if response.status != "completed":
            raise LLMError(f"反思器响应未完成（{response.status}）")
        if any(getattr(part, "type", None) == "refusal"
               for item in response.output for part in getattr(item, "content", []) or []):
            raise LLMError("反思器模型拒绝了请求（refusal）")
        text = response.output_text.strip()
        if not text:
            raise LLMError("反思器返回空文本")
        return text


class AnthropicClient:
    provider = "anthropic"

    def __init__(self, model: str, *, timeout_s: float, max_tokens: int, effort: str = "high"):
        import anthropic  # lazy: tests and offline runs do not need the SDK

        self.model = model
        self.max_tokens = max_tokens
        self.effort = effort
        self.timeout_s = timeout_s
        self.last_response_metadata: dict = {}
        self._client = anthropic.AsyncAnthropic(timeout=timeout_s, max_retries=0)

    async def complete(self, system: str, user: str) -> str:
        self.last_response_metadata = {}
        response = await self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            output_config={"effort": self.effort},
            messages=[{"role": "user", "content": user}],
        )
        self.last_response_metadata = {"model": response.model}
        if response.stop_reason == "refusal":
            raise LLMError("反思器模型拒绝了请求（refusal）")
        if response.stop_reason == "max_tokens":
            raise LLMError("反思器输出被 max_tokens 截断")
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        if not text:
            raise LLMError("反思器返回空文本")
        return text


class OpenAICompatClient:
    """ds flash via the OpenAI-compatible SDK; model/base/key from DS_* env vars."""

    provider = "deepseek"
    effort = None

    def __init__(self, model: str | None = None, *, timeout_s: float, max_tokens: int = 8000,
                 effort: str | None = None, json_mode: bool = False):
        from openai import AsyncOpenAI

        self.model = model or os.environ.get("DS_MODEL") or ""
        if not self.model:
            raise LLMError("未配置 DS_MODEL，无法降级到 ds flash")
        self.max_tokens = max_tokens
        self.timeout_s = timeout_s
        # effort: None = provider default; low/high/max = thinking enabled at that effort (primary reflector use).
        self.effort = effort
        self.json_mode = json_mode
        self.last_response_metadata: dict = {}
        if not os.environ.get("DS_API_KEY"):
            raise LLMError("未配置 DS_API_KEY，无法降级到 ds flash")
        self._client = AsyncOpenAI(base_url=os.environ.get("DS_BASE_URL") or None,
                                   api_key=os.environ["DS_API_KEY"],
                                   timeout=timeout_s, max_retries=0)

    async def complete(self, system: str, user: str) -> str:
        self.last_response_metadata = {}
        extra = {}
        if self.effort:
            extra.update(reasoning_effort=self.effort, extra_body={"thinking": {"type": "enabled"}})
        if self.json_mode:
            extra["response_format"] = {"type": "json_object"}
        response = await self._client.chat.completions.create(
            model=self.model, temperature=0, max_tokens=self.max_tokens,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}], **extra,
        )
        details = getattr(getattr(response, "usage", None), "completion_tokens_details", None)
        self.last_response_metadata = {"model": response.model,
                                       "reasoning_tokens": getattr(details, "reasoning_tokens", None)}
        if response.choices[0].finish_reason != "stop" or getattr(response.choices[0].message, "refusal", None):
            raise LLMError("ds flash 拒答或输出未完成")
        text = (response.choices[0].message.content or "").strip()
        if not text:
            raise LLMError("ds flash 返回空文本")
        return text


def default_clients(config: dict) -> tuple[LLMClient | None, LLMClient | None, str | None]:
    """Build (primary, fallback, primary_init_error). Construction errors become fallback reasons."""
    rc = config["reflector"]
    primary, fallback, error = None, None, None
    try:
        settings = primary_settings(config)
        provider = settings.pop("provider")
        if provider == "deepseek":
            # Same small model as the session agent, with thinking enabled: REFLECTOR_MODEL (an OpenAI /
            # Anthropic id) does not apply here, the model comes from DS_MODEL.
            primary = OpenAICompatClient(os.environ.get(rc["fallback_model_env"]), timeout_s=settings["timeout_s"],
                                         max_tokens=rc["max_tokens"], effort=rc.get("deepseek_effort", "high"),
                                         json_mode=True)
        else:
            factory = {"openai": OpenAIClient, "anthropic": AnthropicClient}.get(provider)
            if factory is None:
                raise LLMError("不支持的 REFLECTOR_PROVIDER（仅支持 openai / anthropic / deepseek）")
            primary = factory(**settings, max_tokens=rc["max_tokens"])
    except Exception as exc:  # noqa: BLE001 - any init failure means "use fallback"
        error = f"主反思器初始化失败: {error_reason(exc)}"
    try:
        fallback = OpenAICompatClient(os.environ.get(rc["fallback_model_env"]), timeout_s=rc["fallback_timeout_s"],
                                      max_tokens=rc.get("fallback_max_tokens", 8000))
    except Exception:  # noqa: BLE001
        fallback = None
    return primary, fallback, error
