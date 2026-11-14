"""PathClassifier: per-turn path weights + visitor attitude (TheraMind's reaction classifier, domain-specialised).

Frozen before run 1; not part of evolution. The interface takes plain dialogue entries and
returns a PathState, so an LLM, a decision API or a fine-tuned small model can sit behind it.

uncertainty := normalised Shannon entropy of the weights, H(w) / ln 5, in [0, 1]
               (0 = all mass on one path, 1 = uniform). `margin` (top1 - top2) is recorded too.
"""
import asyncio
from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import re
import time
from typing import Protocol, runtime_checkable

from .llm import parse_json_object, TruncatedOutput
from .telemetry import CURRENT_CALL, annotate_response

PATHS = ("P1", "P2", "P3", "P4", "P5")
ATTITUDES = ("cooperative", "resistant")
PROMPT_PATH = Path(__file__).with_name("prompts") / "path_classifier.md"


@dataclass(frozen=True)
class PathState:
    weights: dict[str, float]
    attitude: str
    uncertainty: float
    margin: float
    status: str           # ok | timeout | error
    provider: str
    latency_ms: float

    @property
    def top(self) -> str | None:
        if self.status != "ok":
            return None
        return max(PATHS, key=lambda p: (self.weights[p], -PATHS.index(p)))

    def to_dict(self) -> dict:
        return asdict(self)


def normalise(weights: dict) -> dict[str, float]:
    if set(weights) != set(PATHS):
        raise ValueError(f"weights must have exactly {PATHS}")
    values = {}
    for path in PATHS:
        value = weights[path]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError("weights must be finite and non-negative")
        values[path] = float(value)
    total = sum(values.values())
    if total <= 0:
        raise ValueError("weights must not all be zero")
    return {path: values[path] / total for path in PATHS}


def uncertainty(weights: dict[str, float]) -> float:
    entropy = -sum(w * math.log(w) for w in weights.values() if w > 0)
    return round(entropy / math.log(len(PATHS)), 4)


def margin(weights: dict[str, float]) -> float:
    first, second = sorted(weights.values(), reverse=True)[:2]
    return round(first - second, 4)


def make_state(weights: dict, attitude: str, status: str, provider: str, latency_ms: float) -> PathState:
    weights = normalise(weights)
    if attitude not in ATTITUDES:
        raise ValueError(f"attitude must be one of {ATTITUDES}")
    return PathState(weights, attitude, uncertainty(weights), margin(weights), status, provider, round(latency_ms, 1))


def uniform_state(status: str, provider: str, latency_ms: float) -> PathState:
    """Failure fallback: no evidence -> uniform weights, attitude cooperative."""
    return make_state(dict.fromkeys(PATHS, 1.0), "cooperative", status, provider, latency_ms)


def render_dialogue(dialogue: list[dict]) -> str:
    """Agent and visitor lines only; fixed safety scripts and tool results are not path evidence."""
    label = {"agent": "睡眠管家", "visitor": "来访"}
    return "\n".join(f"{label[e['speaker']]}：{e['text']}" for e in dialogue if e.get("speaker") in label)


@runtime_checkable
class PathClassifier(Protocol):
    provider: str

    async def classify(self, dialogue: list[dict]) -> PathState: ...


class _Bounded:
    """Timeout + exception -> uniform fallback; implementations provide _predict -> (weights, attitude)."""
    provider = "base"

    def __init__(self, timeout_s: float):
        self.timeout_s = timeout_s

    async def classify(self, dialogue: list[dict]) -> PathState:
        started = time.perf_counter()
        try:
            weights, attitude = await asyncio.wait_for(self._predict(render_dialogue(dialogue)), self.timeout_s)
            return make_state(weights, attitude, "ok", self.provider, (time.perf_counter() - started) * 1000)
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            return uniform_state("timeout", self.provider, (time.perf_counter() - started) * 1000)
        except Exception:
            return uniform_state("error", self.provider, (time.perf_counter() - started) * 1000)

    async def _predict(self, text: str):
        raise NotImplementedError


_MOCK_WORDS = {
    "P1": ("周末", "咖啡", "喝两口", "午睡", "看心情", "作息乱", "聚餐"),
    "P2": ("沙发", "一躺到床上就清醒", "酒店", "也没想什么", "硬躺"),
    "P3": ("反复想", "担心", "脑子停不下来", "看时间", "毁掉明天", "复盘"),
    "P4": ("两三点", "凌晨两点", "放假", "夜猫子", "三班倒", "轮班", "自然犯困"),
    "P5": ("短视频", "刷", "游戏", "追剧", "舍不得睡", "手机"),
}
_RESISTANT = re.compile(r"^(?:没有吧|还好|也还好|没什么|不太清楚|不记得了|好像也还好)")


class MockPathClassifier(_Bounded):
    """Deterministic keyword fixture over visitor lines (offline tests / smoke); not a validated classifier."""
    provider = "mock"

    def __init__(self, timeout_s: float = 6.0, *, provider: str = "mock"):
        super().__init__(timeout_s)
        self.provider = provider

    async def _predict(self, text):
        visitor = [line[3:] for line in text.splitlines() if line.startswith("来访：")]
        joined = "".join(visitor)
        weights = {p: 1.0 + 2.0 * sum(joined.count(w) for w in words) for p, words in _MOCK_WORDS.items()}
        attitude = "resistant" if visitor and _RESISTANT.match(visitor[-1]) else "cooperative"
        return weights, attitude


class DsFlashPathClassifier(_Bounded):
    """OpenAI-compatible JSON classifier; same DS_* variables as the agent and the crisis judge."""
    provider = "ds_flash"

    def __init__(self, timeout_s: float, *, temperature: float = 0, client=None,
                 limiter: asyncio.Semaphore | None = None, thinking: str | None = None):
        super().__init__(timeout_s)
        self.limiter = limiter
        self.prompt = PROMPT_PATH.read_text(encoding="utf-8")
        self.model = os.getenv("DS_MODEL", "").strip()
        self.temperature = temperature
        self.thinking = thinking
        if client is None:
            base_url, api_key = os.getenv("DS_BASE_URL", "").strip(), os.getenv("DS_API_KEY", "").strip()
            if not all((self.model, base_url, api_key)):
                raise ValueError("DsFlashPathClassifier requires DS_MODEL, DS_BASE_URL and DS_API_KEY")
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout_s, max_retries=0)
        self.client = client

    async def _predict(self, text):
        if self.limiter is None:
            return await self._call(text)
        async with self.limiter:
            return await self._call(text)

    async def _call(self, text):
        row = CURRENT_CALL.get()
        if row is not None:
            row["request_started"] = True
        response = await self.client.chat.completions.create(
            model=self.model, temperature=self.temperature, response_format={"type": "json_object"},
            **({"extra_body": {"thinking": {"type": self.thinking}}} if self.thinking else {}),
            messages=[{"role": "system", "content": self.prompt}, {"role": "user", "content": text or "（尚无对话）"}])
        annotate_response(response)
        if getattr(response.choices[0], "finish_reason", None) == "length":
            raise TruncatedOutput("classifier completion truncated")
        data = parse_json_object(response.choices[0].message.content or "")
        if not isinstance(data, dict) or set(data) != {"weights", "attitude"}:
            raise ValueError("malformed classifier JSON")
        return data["weights"], data["attitude"]


class JevPathClassifier(_Bounded):
    """TypeSafe `system_one` with two Choice questions; options natively carry probabilities."""
    provider = "jev"

    CRITERIA = {
        "P1": "作息不规律、周末补觉、咖啡因或酒精、长午睡等日常习惯维持睡眠困扰",
        "P2": "一上床就清醒、躺下时脑中无特别内容、换地方反而好睡，床与清醒形成联结",
        "P3": "躺下后反复担心、脑子停不下来、对睡不好的后果灾难化",
        "P4": "生物钟偏晚，不管几点上床都很晚才困，放假按自己节奏睡得好；或轮班",
        "P5": "上床后长时间刷手机、追剧、打游戏，舍不得睡",
    }

    def __init__(self, timeout_s: float, *, client=None):
        super().__init__(timeout_s)
        try:
            from typesafe_sdk import AsyncTypeSafeClient, Choice
        except ImportError as exc:
            raise ImportError("JevPathClassifier requires typesafe-sdk; install requirements-optional.txt") from exc
        self.client_type, self.choice_type = AsyncTypeSafeClient, Choice
        self.api_key = os.getenv("TYPESAFE_API_KEY", "").strip()
        if client is None and not self.api_key:
            raise ValueError("JevPathClassifier requires TYPESAFE_API_KEY")
        if client is None:
            from typesafe_sdk import RetryPolicy
            client = AsyncTypeSafeClient(api_key=self.api_key, timeout=timeout_s, retry=RetryPolicy(max_retries=0))
        self.client = client
        self.prompt = PROMPT_PATH.read_text(encoding="utf-8")

    async def _request(self, client, text):
        response = await client.system_one(state={"text": text or "（尚无对话）"}, questions={
            "path": self.choice_type(instructions=self.prompt, criteria=self.CRITERIA),
            "attitude": self.choice_type(instructions="来访最近一次发言的态度", criteria={
                "cooperative": "愿意说，回答具体", "resistant": "否认、回避、敷衍"}),
        })
        return response.choices["path"].probabilities, response.choices["attitude"].choice

    async def _predict(self, text):
        if self.client is not None:
            return await self._request(self.client, text)
        async with self.client_type(api_key=self.api_key, timeout=self.timeout_s) as client:
            return await self._request(client, text)


def make_classifier(settings: dict, *, limiter: asyncio.Semaphore | None = None) -> PathClassifier:
    """settings = engine config `path_classifier`; missing keys fall back to the mock, labelled."""
    provider, timeout = settings["provider"], settings["timeout_s"]
    if provider == "mock":
        return MockPathClassifier(timeout)
    try:
        if provider == "ds_flash":
            return DsFlashPathClassifier(timeout, temperature=settings.get("temperature", 0), limiter=limiter,
                                         thinking=settings.get("thinking"))
        if provider == "jev":
            try:
                fallback = DsFlashPathClassifier(timeout, limiter=limiter, thinking=settings.get("thinking"))
            except (ValueError, ImportError):
                fallback = None
            try:
                primary = JevPathClassifier(timeout)
            except (ValueError, ImportError):
                if fallback is not None:
                    fallback.provider = "ds_flash(fallback:jev_unavailable)"
                    return fallback
                raise
            return FallbackPathClassifier(primary, fallback) if fallback else primary
    except (ValueError, ImportError):
        return MockPathClassifier(timeout, provider="mock(fallback)")
    raise ValueError(f"unknown path classifier provider {provider}")


class FallbackPathClassifier:
    """Jev first; a failed call uses the real DS client, never a fabricated prediction."""
    provider = "jev->ds_flash"

    def __init__(self, primary, fallback):
        self.primary, self.fallback = primary, fallback

    async def classify(self, dialogue):
        from dataclasses import replace
        first = await self.primary.classify(dialogue)
        if first.status == "ok":
            return first
        row = CURRENT_CALL.get()
        if row is not None:
            row['provider_switches'] = 1  # Retain the switch even if the second leg is cancelled.
        second = await self.fallback.classify(dialogue)
        return replace(second, provider=f"ds_flash(fallback:jev_{first.status})",
                       latency_ms=round(first.latency_ms + second.latency_ms, 1))

    async def aclose(self):
        for classifier in (self.primary, self.fallback):
            client = getattr(classifier, "client", None)
            close = getattr(client, "aclose", None) or getattr(client, "close", None)
            if close:
                await close()
