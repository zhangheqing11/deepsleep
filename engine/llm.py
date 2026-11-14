"""Agent LLM clients: ds flash (OpenAI-compatible) and a deterministic mock.

`complete_json(messages, *, task, state)` returns the parsed JSON object. `state` is a
structured view of the same information the messages carry; the real client ignores
it, the mock policy reads it so tests stay deterministic and offline.
"""
import asyncio
import json
import os
import re
from typing import Protocol, runtime_checkable


class LLMError(RuntimeError):
    pass


@runtime_checkable
class AgentLLM(Protocol):
    model_name: str

    async def complete_json(self, messages: list[dict], *, task: str, state: dict) -> dict: ...


class DsFlashClient:
    """OpenAI-compatible chat client; settings come from engine/config.yaml agent_llm."""

    def __init__(self, settings: dict, *, client=None, limiter: asyncio.Semaphore | None = None):
        self.settings = settings
        self.model = os.getenv("DS_MODEL", "").strip()
        base_url = os.getenv("DS_BASE_URL", "").strip()
        api_key = os.getenv("DS_API_KEY", "").strip()
        if client is None:
            if not all((self.model, base_url, api_key)):
                raise ValueError("DsFlashClient requires DS_MODEL, DS_BASE_URL and DS_API_KEY")
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=settings["timeout_s"], max_retries=0)
        self.client = client
        self.model_name = self.model or "ds-flash"
        # Shared with the ds flash path classifier so the engine's total in-flight ds requests stay bounded.
        self._limit = limiter or asyncio.Semaphore(settings["max_inflight"])

    async def complete_json(self, messages: list[dict], *, task: str, state: dict) -> dict:
        kwargs = dict(model=self.model, messages=messages, temperature=self.settings["temperature"],
                      top_p=self.settings["top_p"], max_tokens=self.settings["max_tokens"])
        if self.settings.get("response_format") == "json_object":
            kwargs["response_format"] = {"type": "json_object"}
        async with self._limit:
            response = await asyncio.wait_for(self.client.chat.completions.create(**kwargs),
                                              self.settings["timeout_s"])
        return parse_json_object(response.choices[0].message.content or "")

    async def aclose(self):
        close = getattr(self.client, "close", None)
        if close:
            await close()


def parse_json_object(text: str) -> dict:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError(f"agent output is not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise LLMError("agent output must be a JSON object")
    return data


def make_agent_llm(settings: dict, *, limiter: asyncio.Semaphore | None = None) -> AgentLLM:
    from .mock_agent import MockAgentLLM
    if settings["provider"] == "mock":
        return MockAgentLLM()
    if not all(os.getenv(key, "").strip() for key in ("DS_MODEL", "DS_BASE_URL", "DS_API_KEY")):
        return MockAgentLLM(model_name="mock(fallback)")
    return DsFlashClient(settings, limiter=limiter)


