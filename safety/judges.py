"""Bounded async judge adapters. No requests are made during construction."""
import asyncio
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
from time import perf_counter
from typing import Protocol

from .config import load_config

LEVELS = ("none", "passive", "active")


@dataclass(frozen=True)
class JudgeResult:
    probs: dict[str, float] | None
    status: str
    provider: str
    latency_ms: float


class Judge(Protocol):
    async def classify(self, text: str) -> JudgeResult: ...


def validate_probs(probs, tolerance: float) -> dict[str, float]:
    if not isinstance(probs, dict) or set(probs) != set(LEVELS):
        raise ValueError("Expected exactly none/passive/active probabilities")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 1 for v in probs.values()):
        raise ValueError("Invalid probability")
    # Numerical serialization tolerance, not a classification threshold.
    if abs(math.fsum(probs.values()) - 1.0) > tolerance:
        raise ValueError("Probabilities must sum to 1")
    return {level: float(probs[level]) for level in LEVELS}


class _BoundedJudge:
    provider: str

    def __init__(self, config=None):
        self.config = load_config(config)
        self.timeout = self.config["judge_timeout_s"]

    async def classify(self, text: str) -> JudgeResult:
        start = perf_counter()
        probs = None
        try:
            probs = validate_probs(
                await asyncio.wait_for(self._predict(text), timeout=self.timeout),
                self.config["probability_sum_tolerance"],
            )
            status = "ok"
        except TimeoutError:
            status = "timeout"
        except Exception:
            status = "error"
        return JudgeResult(probs, status, self.provider, (perf_counter() - start) * 1000)

    async def _predict(self, text: str) -> dict[str, float]:
        raise NotImplementedError


class MockJudge(_BoundedJudge):
    """Deterministic one-hot keyword fixture, not a validated classifier."""
    provider = "mock"

    def __init__(self, config=None, *, provider="mock"):
        super().__init__(config)
        self.provider = provider

    async def _predict(self, text):
        level = "none"
        for candidate in ("active", "passive"):
            if any(word in text for word in self.config["mock_keywords"][candidate]):
                level = candidate
                break
        return {name: float(name == level) for name in LEVELS}


class DsFlashJudge(_BoundedJudge):
    provider = "ds_flash"

    def __init__(self, config=None, *, client=None):
        super().__init__(config)
        self.prompt = Path(self.config["judge_prompt_path"]).read_text(encoding="utf-8")
        self.client = client
        self.model = os.getenv("DS_MODEL", "").strip()
        self.base_url = os.getenv("DS_BASE_URL", "").strip()
        self.api_key = os.getenv("DS_API_KEY", "").strip()
        if client is None and not all((self.model, self.base_url, self.api_key)):
            raise ValueError("DsFlashJudge requires DS_MODEL, DS_BASE_URL and DS_API_KEY")

    async def _request(self, client, text):
        response = await client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": self.prompt}, {"role": "user", "content": text}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content)
        if not isinstance(data, dict) or set(data) != {"level", "probs"} or data["level"] not in LEVELS:
            raise ValueError("Malformed judge JSON")
        return data["probs"]

    async def _predict(self, text):
        if self.client is not None:
            return await self._request(self.client, text)
        from openai import AsyncOpenAI

        async with AsyncOpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout, max_retries=0) as client:
            return await self._request(client, text)


class JevJudge(_BoundedJudge):
    provider = "jev"

    def __init__(self, config=None, *, client=None):
        super().__init__(config)
        try:
            from typesafe_sdk import AsyncTypeSafeClient, Choice
        except ImportError as exc:
            raise ImportError("JevJudge requires typesafe-sdk; install requirements-optional.txt") from exc
        self.client_type = AsyncTypeSafeClient
        self.choice_type = Choice
        self.client = client
        self.api_key = os.getenv("TYPESAFE_API_KEY", "").strip()
        if client is None and not self.api_key:
            raise ValueError("JevJudge requires TYPESAFE_API_KEY")
        self.prompt = Path(self.config["judge_prompt_path"]).read_text(encoding="utf-8")

    async def _request(self, client, text):
        # Dict insertion order is deliberate: active, passive, none.
        choice = self.choice_type(instructions=self.prompt, criteria={
            "active": "本人当前主动意念、方法、意图、计划或自伤准备、行为",
            "passive": "本人当前死亡愿望或被动意念，含希望睡去不再醒来",
            "none": "无本人当前死亡愿望或自伤信号",
        })
        response = await client.system_one(state={"text": text}, questions={"risk": choice})
        answer = response.choices["risk"]
        if answer.choice not in LEVELS:
            raise ValueError("Unknown Jev choice")
        return answer.probabilities

    async def _predict(self, text):
        if self.client is not None:
            return await self._request(self.client, text)
        async with self.client_type(api_key=self.api_key, timeout=self.timeout) as client:
            return await self._request(client, text)


def make_judge(config=None) -> Judge:
    config = load_config(config)
    provider = config["judge_provider"]
    if provider == "mock":
        return MockJudge(config)
    key = "DS_API_KEY" if provider == "ds_flash" else "TYPESAFE_API_KEY"
    if not os.getenv(key, "").strip():
        return MockJudge(config, provider="mock(fallback)")
    if provider == "ds_flash":
        return DsFlashJudge(config)
    try:
        return JevJudge(config)
    except ImportError:
        return MockJudge(config, provider="mock(fallback)")
