"""Bounded async judge adapters. No requests are made during construction."""
import asyncio
from dataclasses import dataclass, replace
import json
import logging
import math
import os
import re
from pathlib import Path
from time import perf_counter
from typing import Protocol

import httpx

from .config import load_config

LEVELS = ("none", "history", "passive", "active")


@dataclass(frozen=True)
class JudgeResult:
    probs: dict[str, float] | None
    status: str
    provider: str
    latency_ms: float
    attempts: tuple["JudgeResult", ...] = ()
    warning: str = ""


class Judge(Protocol):
    async def classify(self, text: str) -> JudgeResult: ...


def validate_probs(probs, tolerance: float) -> dict[str, float]:
    if not isinstance(probs, dict) or set(probs) != set(LEVELS):
        raise ValueError("Expected exactly none/history/passive/active probabilities")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 1 for v in probs.values()):
        raise ValueError("Invalid probability")
    # Numerical serialization tolerance, not a classification threshold.
    if abs(math.fsum(probs.values()) - 1.0) > tolerance:
        raise ValueError("Probabilities must sum to 1")
    return {level: float(probs[level]) for level in LEVELS}


class ChainJudge:
    """Sequential failover with invocation-local records, safe for shared use."""
    provider = "chain"

    def __init__(self, primary: Judge, fallbacks):
        self.primary = primary
        self.fallbacks = tuple(fallbacks)
        self.judges = (primary, *self.fallbacks)
        # Built-in adapters expose their effective timeout (including overrides).
        self.timeout = sum(getattr(judge, "timeout", 6.0 if i == 0 else 3.0)
                           for i, judge in enumerate(self.judges))

    async def classify(self, text: str) -> JudgeResult:
        attempts = []
        for i, judge in enumerate(self.judges):
            start = perf_counter()
            provider = getattr(judge, "provider", type(judge).__name__)
            try:
                result = await asyncio.wait_for(
                    judge.classify(text), getattr(judge, "timeout", 6.0 if i == 0 else 3.0),
                )
                if result.status == "ok":
                    validate_probs(result.probs, getattr(judge, "config", {}).get(
                        "probability_sum_tolerance", 0.000001))
                elif result.status not in ("timeout", "error"):
                    raise ValueError("Unexpected judge status")
            except TimeoutError:
                result = JudgeResult(None, "timeout", provider, (perf_counter() - start) * 1000)
            except Exception:
                result = JudgeResult(None, "error", provider, (perf_counter() - start) * 1000)
            attempts.append(result)
            if result.status == "ok":
                break
        return replace(result, attempts=tuple(attempts))


class _BoundedJudge:
    provider: str

    def __init__(self, config=None):
        self.config = load_config(config)
        self.timeout = self.config["judge_timeout_overrides"].get(
            self.provider, self.config["judge_timeout_s"],
        )

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

    async def classify(self, text):
        return replace(await super().classify(text), warning="mock，不代表识别能力")

    async def _predict(self, text):
        level = "none"
        for candidate in ("active", "passive"):
            if any(word in text for word in self.config["mock_keywords"][candidate]):
                level = candidate
                break
        if level != "none" and any(word in text for word in ("以前", "那时候", "早就不", "过去")):
            # Offline fixture only: an explicit current statement takes precedence.
            current = [match.group() for match in re.finditer(
                r"(?:现在|目前|如今|最近|仍然|仍旧|至今|一直)[^，。！？；\n]*", text
            ) if not re.search(r"没有|不再有|不再想|不想自|不想结束|早就不", match.group())]
            level = "history"
            for candidate in ("active", "passive"):
                if any(word in clause for clause in current for word in self.config["mock_keywords"][candidate]):
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
        # Dict insertion order is deliberate: active, passive, history, none.
        choice = self.choice_type(instructions=self.prompt, criteria={
            "active": "本人当前主动意念、方法、意图、计划或自伤准备、行为",
            "passive": "本人当前死亡愿望或被动意念，含希望睡去不再醒来",
            "history": "本人过去且已结束的被动或主动意念、自伤或尝试，当前否认或未表明仍有；是否结束不明时偏向 passive",
            "none": "无本人当前风险信号，也未谈及本人过去已结束的风险史",
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


class StartLuxJudge(_BoundedJudge):
    """Native TypeSafe-compatible HTTP protocol; no SDK or automatic retries."""
    provider = "startlux"

    def __init__(self, config=None, *, transport=None):
        super().__init__(config)
        self.transport = transport
        self.api_key = os.getenv("STARTLUX_API_KEY", "").strip()
        if transport is None and not self.api_key:
            raise ValueError("StartLuxJudge requires STARTLUX_API_KEY")
        self.model = (os.getenv("STARTLUX_MODEL", "").strip()
                      or "startlux-decision-27b-autothink")
        base_url = (os.getenv("STARTLUX_BASE_URL", "").strip()
                    or "https://api.bamboonode.dev").rstrip("/")
        # Accept an origin, a /v1 base, or an explicit native endpoint for self-hosting.
        if base_url.endswith(("/v1/systemone", "/v1/decisions")):
            self.endpoint = base_url
        else:
            self.endpoint = base_url + ("/decisions" if base_url.endswith("/v1") else "/v1/decisions")
        path = Path(__file__).with_name("prompts") / "gemini_decision_zh.json"
        self.question = json.loads(path.read_text(encoding="utf-8"))
        # Reuse the frozen history definitions, but fix A-D order toward recall.
        self.question["criteria"] = {
            level: self.question["criteria"][level]
            for level in ("active", "passive", "history", "none")
        }

    async def _predict(self, text):
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                response = await client.post(
                    self.endpoint,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model, "state": {"text": text},
                        "questions": {"risk": self.question},
                        # Both are on by default at Bamboo; business `none` is a normal option.
                        "none_check": False, "allow_none": False,
                    },
                )
                response.raise_for_status()
                answer = response.json()["answers"]["risk"]
        except httpx.TimeoutException as exc:
            raise TimeoutError("StartLux decision request timed out") from exc
        if answer["type"] != "choice" or answer["choice"] not in LEVELS:
            raise ValueError("Invalid StartLux choice")
        confidence = answer["confidence"]
        if (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
                or not math.isfinite(confidence) or not 0 <= confidence <= 1):
            raise ValueError("Invalid StartLux confidence")
        # _BoundedJudge validates all four probabilities; confidence is not a threshold.
        return answer["probabilities"]


class GeminiDecisionJudge(_BoundedJudge):
    provider = "gemini_decision"

    def __init__(self, config=None, *, client=None):
        super().__init__(config)
        self.client = client
        self.api_key = (os.getenv("GEMINI_API_KEY", "").strip()
                        or os.getenv("GOOGLE_API_KEY", "").strip())
        if client is None:
            try:
                from google import genai
            except ImportError as exc:
                raise ImportError(
                    "GeminiDecisionJudge requires google-genai>=3.2.0; install requirements-optional.txt"
                ) from exc
            self.client_type = genai.Client
            if not self.api_key:
                raise ValueError("GeminiDecisionJudge requires GEMINI_API_KEY or GOOGLE_API_KEY")
        # A separate frozen Choice question avoids the chat judge's JSON-output instruction.
        path = Path(__file__).with_name("prompts") / "gemini_decision_zh.json"
        self.question = json.loads(path.read_text(encoding="utf-8"))
        criteria = self.question["criteria"]
        if (self.question["type"] != "choice"
                or not isinstance(self.question["instructions"], str)
                or not self.question["instructions"].strip()
                or not isinstance(criteria, dict) or set(criteria) != set(LEVELS)
                or not all(isinstance(v, str) and v.strip() for v in criteria.values())):
            raise ValueError("Gemini Choice requires instructions and four nonempty descriptions")

    async def _request(self, client, text):
        # The SDK supports both HTTP transports; normalize their timeout exceptions.
        try:
            import httpx
        except ImportError:
            import httpx2 as httpx
        timeout_errors = (httpx.TimeoutException,)
        try:
            from google.genai._interactions import APITimeoutError
        except ImportError:
            pass  # Injected fake clients also work without the optional SDK.
        else:
            timeout_errors += (APITimeoutError,)
        try:
            response = await client.decisions.create(
                model="gemini-decision-1", input=text, questions={"risk": self.question},
            )
        except timeout_errors as exc:
            raise TimeoutError("Gemini decision request timed out") from exc
        answer = response.answers["risk"]
        if answer.choice not in LEVELS:
            raise ValueError("Unknown Gemini choice")
        confidence = answer.confidence
        if (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
                or not math.isfinite(confidence) or not 0 <= confidence <= 1):
            raise ValueError("Invalid Gemini confidence")
        # Existing safety thresholds consume the full distribution, not choice/confidence.
        return answer.probabilities

    async def _predict(self, text):
        if self.client is not None:
            return await self._request(self.client.aio, text)
        # Close both transports, including on cancellation/error. HttpOptions timeout is ms.
        with self.client_type(api_key=self.api_key, http_options={
            "api_version": "v1beta", "timeout": max(1, math.ceil(self.timeout * 1000)),
            "retry_options": {"attempts": 1},
        }) as client:
            async with client.aio as async_client:
                return await self._request(async_client, text)


class UnavailableJudge:
    """A configuration failure is an error result, never a keyword classifier."""

    def __init__(self, provider, reason):
        self.provider = provider
        self.warning = f"安全警告：判断器 {provider} 不可用（{reason}）；按判断器失败处理，未启用 mock。"
        logging.getLogger(__name__).warning(self.warning)

    async def classify(self, text):
        return JudgeResult(None, "error", self.provider, 0., warning=self.warning)


def _make_single_judge(config, *, allow_fallback=True) -> Judge:
    config = load_config(config)
    provider = config["judge_provider"]
    if provider == "mock":
        return MockJudge(config)
    keys = {
        "ds_flash": ("DS_API_KEY",), "jev": ("TYPESAFE_API_KEY",),
        "gemini_decision": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        "startlux": ("STARTLUX_API_KEY",),
    }[provider]
    if not any(os.getenv(key, "").strip() for key in keys):
        if not allow_fallback:
            raise ValueError(f"评测 {provider} 缺少 API key：请设置 {' 或 '.join(keys)}；未降级 mock。")
        return UnavailableJudge(provider, "缺少 API key")
    try:
        if provider == "ds_flash":
            # Its adapter imports lazily at request time; check availability now
            # so an unavailable fallback is skipped before building the chain.
            from openai import AsyncOpenAI  # noqa: F401
            return DsFlashJudge(config)
        if provider == "startlux":
            return StartLuxJudge(config)
        return GeminiDecisionJudge(config) if provider == "gemini_decision" else JevJudge(config)
    except (ImportError, ValueError) as exc:
        if not allow_fallback:
            raise ValueError(f"评测 {provider} 缺少所需 SDK 或模型配置；未降级 mock。") from None
        return UnavailableJudge(provider, "缺少所需 SDK" if isinstance(exc, ImportError) else "缺少模型配置")


def make_judge(config=None, *, allow_fallback=True, chain=None) -> Judge:
    """Build the configured chain; unavailable primaries return error by default.

    allow_fallback=False keeps a strict constructor for configuration diagnostics;
    evaluation catches configuration failures and reports them without using mock.
    """
    config = load_config(config)
    primary = _make_single_judge(config, allow_fallback=allow_fallback)
    use_chain = allow_fallback if chain is None else chain
    if not use_chain or primary.provider.startswith("mock"):
        return primary
    fallbacks = []
    for provider in config["judge_fallbacks"]:
        fallback_config = {**config, "judge_provider": provider,
                           "judge_timeout_s": config["judge_fallback_timeout_s"],
                           "judge_timeout_overrides": {}}
        try:
            fallback = _make_single_judge(fallback_config, allow_fallback=False)
        except (ValueError, ImportError):
            if not allow_fallback:
                raise
            logging.getLogger(__name__).warning("安全警告：兜底判断器 %s 缺少配置或 SDK，跳过；未启用 mock。", provider)
            continue
        fallbacks.append(fallback)
    return ChainJudge(primary, fallbacks) if fallbacks else primary
