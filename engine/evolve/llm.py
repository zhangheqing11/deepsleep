"""LLM clients for the reflector: Opus 5.5 (Anthropic SDK) primary, ds flash fallback.

Both expose ``model`` and ``async complete(system, user) -> str`` and raise on any
failure (timeout, API error, refusal, empty output) so the caller can fall back.
TODO(S3): share the ds flash client with the session loop once engine-session lands.
"""
from __future__ import annotations

import os
from typing import Protocol


class LLMClient(Protocol):
    model: str

    async def complete(self, system: str, user: str) -> str: ...


class LLMError(RuntimeError):
    pass


class AnthropicClient:
    def __init__(self, model: str, *, timeout_s: float, max_tokens: int, effort: str = "high"):
        import anthropic  # lazy: tests and offline runs do not need the SDK

        self.model = model
        self.max_tokens = max_tokens
        self.effort = effort
        self._client = anthropic.AsyncAnthropic(timeout=timeout_s, max_retries=1)

    async def complete(self, system: str, user: str) -> str:
        response = await self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            output_config={"effort": self.effort},
            messages=[{"role": "user", "content": user}],
        )
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

    def __init__(self, model: str | None = None, *, timeout_s: float, max_tokens: int = 8000):
        from openai import AsyncOpenAI

        self.model = model or os.environ.get("DS_MODEL") or ""
        if not self.model:
            raise LLMError("未配置 DS_MODEL，无法降级到 ds flash")
        self.max_tokens = max_tokens
        self._client = AsyncOpenAI(base_url=os.environ.get("DS_BASE_URL") or None,
                                   api_key=os.environ.get("DS_API_KEY") or None,
                                   timeout=timeout_s, max_retries=1)

    async def complete(self, system: str, user: str) -> str:
        response = await self._client.chat.completions.create(
            model=self.model, temperature=0, max_tokens=self.max_tokens,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        text = (response.choices[0].message.content or "").strip()
        if not text:
            raise LLMError("ds flash 返回空文本")
        return text


def default_clients(config: dict) -> tuple[LLMClient | None, LLMClient | None, str | None]:
    """Build (primary, fallback, primary_init_error). Construction errors become fallback reasons."""
    rc = config["reflector"]
    primary, fallback, error = None, None, None
    model = os.environ.get(rc["primary_model_env"]) or rc["primary_model"]
    try:
        primary = AnthropicClient(model, timeout_s=rc["primary_timeout_s"], max_tokens=rc["max_tokens"],
                                  effort=rc["primary_effort"])
    except Exception as exc:  # noqa: BLE001 - any init failure means "use fallback"
        error = f"主反思器初始化失败: {exc}"
    try:
        fallback = OpenAICompatClient(os.environ.get(rc["fallback_model_env"]), timeout_s=rc["fallback_timeout_s"])
    except Exception:  # noqa: BLE001
        fallback = None
    return primary, fallback, error
