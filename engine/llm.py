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

    def __init__(self, settings: dict, *, client=None):
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
        self._limit = asyncio.Semaphore(settings["max_inflight"])

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


def make_agent_llm(settings: dict) -> AgentLLM:
    if settings["provider"] == "mock":
        return MockAgentLLM()
    if not all(os.getenv(key, "").strip() for key in ("DS_MODEL", "DS_BASE_URL", "DS_API_KEY")):
        return MockAgentLLM(model_name="mock(fallback)")
    return DsFlashClient(settings)


# --------------------------------------------------------------------------- mock

_QUESTIONS = {
    1: [
        ("schedule", "先了解一下，你平时几点上床、几点起床？"),
        ("bed", "躺在床上的时候，你通常是清醒着，还是脑子里在想事情？"),
        ("chronotype", "如果放假可以随便睡，你几点会自然犯困、几点自然醒？"),
        ("screen", "上床以后会看手机或者刷视频吗？"),
        ("snoring", "家里人有没有说过你打鼾，或者睡觉时呼吸停顿？"),
    ],
    2: [
        ("elsewhere", "在沙发上或者出差住外面的时候，会不会反而容易睡着？"),
        ("mood", "最近心情怎么样，做事还提得起兴趣吗？"),
        ("health", "你身体状况怎么样，有没有在看医生的情况？"),
        ("caffeine", "下午或晚上会喝咖啡、茶或者酒吗？"),
    ],
}
_PATH_WORDS = {
    "P1": ("周末", "咖啡", "酒", "午睡", "看心情"),
    "P2": ("沙发", "清醒", "酒店", "精神"),
    "P3": ("反复想", "担心", "脑子", "看时间"),
    "P4": ("两三点", "两点", "放假", "夜猫子", "倒", "轮班"),
    "P5": ("手机", "短视频", "刷", "游戏", "追剧"),
}


class MockAgentLLM:
    """Deterministic offline policy. Not a clinical baseline; exists so the loop runs without keys."""

    def __init__(self, model_name: str = "mock-agent"):
        self.model_name = model_name

    async def complete_json(self, messages: list[dict], *, task: str, state: dict) -> dict:
        return getattr(self, f"_{task}")(state)

    def _turn(self, state: dict) -> dict:
        if state["history_check_required"]:
            return {"action": "say", "text": "我想确认一下，现在你还有这种念头吗？", "acts": ["emotion_response"]}
        visitor_text = _visitor_text(state)
        called = {call["tool"] for call in state["tool_calls"]}
        if "screen_osa" not in called and re.search(r"打鼾|憋醒|呼吸.{0,4}停", visitor_text):
            return {"action": "tool", "tool": "screen_osa"}
        if "screen_mood" not in called and re.search(r"低落|提不起|没兴趣", visitor_text):
            return {"action": "tool", "tool": "screen_mood"}
        asked = state["agent_texts"]
        for _, question in _QUESTIONS[state["round"]]:
            if question not in asked:
                return {"action": "say", "text": question, "acts": ["reflection"] if asked else ["goal_setting"]}
        return {"action": "end_round"}

    def _assess(self, state: dict) -> dict:
        text = _visitor_text(state)
        scores = {path: sum(text.count(w) for w in words) for path, words in _PATH_WORDS.items()}
        best = max(scores, key=lambda p: (scores[p], -int(p[1])))
        total = sum(scores.values())
        confidence = round(scores[best] / total, 2) if total else 0.2
        return {"path": best if total else "P1", "confidence": confidence, "referral": _referral(state, text)}

    def _plan(self, state: dict) -> dict:
        path = state["last_path"]
        components = {"P1": ["sleep_hygiene", "fixed_risetime"], "P2": ["stimulus_control", "fixed_risetime"],
                      "P3": ["worry_time", "cognitive_restructuring"], "P4": ["light_timing", "schedule_shift"],
                      "P5": ["digital_curfew", "fixed_risetime"]}[path]
        referral = state["last_referral"]
        advice = None
        if referral != "R0":
            components = components + ["referral_advice"]
            advice = "建议到医院相关科室进一步评估。"
        return {
            "plan": {"bedtime": "23:30", "risetime": "07:00", "tib_minutes": 450, "components": components,
                     "rationale_given": True, "referral_advice": advice,
                     "cards": [{"type": "reminder", "title": "固定起床时间", "body": "明早七点起床，先坚持一周。"}]},
            "contraindications_identified": [], "age": None,
            "closing_message": "我们先从固定起床时间开始，每天七点起床，这样身体的节律会慢慢稳定下来。",
        }


def _visitor_text(state: dict) -> str:
    return "".join(e["text"] for e in state["transcript"] if e["speaker"] == "visitor")


def _referral(state: dict, text: str) -> str:
    for call in state["tool_calls"]:
        result = call["result"]
        if call["tool"] == "screen_osa" and result["stop_bang"] >= 3:
            return "R1"
        if call["tool"] == "screen_mood" and (result["phq9"] >= 10 or result["gad7"] >= 10):
            return "R3"
    if re.search(r"腿.{0,8}(?:难受|想动|虫)", text):
        return "R2"
    return "R0"
