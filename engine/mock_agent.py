"""Deterministic offline policy for every subagent task (strategy / response / turn / memory / plan / select).

Not a clinical baseline and not user-facing copy: it exists so the loop, tests and smoke run without keys.
It reads only the structured `state` the engine passes (same information as the prompt).
"""
import re

QUESTION = {
    "schedule_regularity": "先了解一下，你平时几点上床、几点起床？",
    "bed_wakefulness": "躺在床上的时候，你通常是清醒着，还是脑子里在想事情？",
    "worry_rumination": "躺下以后，脑子里会不会一直在想事情、停不下来？",
    "sleep_elsewhere": "在沙发上或者出差住外面的时候，会不会反而容易睡着？",
    "chronotype": "如果放假可以随便睡，你几点会自然犯困、几点自然醒？",
    "screen_in_bed": "上床以后会看手机或者刷视频吗？",
    "weekend_catchup": "周末和工作日的作息差别大吗？",
    "caffeine_alcohol": "下午或晚上会喝咖啡、茶或者酒吗？",
    "snoring_breathing": "家里人有没有说过你打鼾，或者睡觉时呼吸停顿？",
    "mood": "最近心情怎么样，做事还提得起兴趣吗？",
    "health_conditions": "你身体状况怎么样，有没有在看医生的情况？",
}
EXPLORE = {1: ["schedule_regularity", "bed_wakefulness", "chronotype", "screen_in_bed", "snoring_breathing"],
           2: ["sleep_elsewhere", "mood", "health_conditions", "caffeine_alcohol", "weekend_catchup"]}
DISCRIMINATE = {frozenset({"P2", "P3"}): "worry_rumination", frozenset({"P4", "P5"}): "chronotype",
                frozenset({"P1", "P4"}): "weekend_catchup", frozenset({"P1", "P5"}): "screen_in_bed",
                frozenset({"P2", "P5"}): "screen_in_bed"}
SUPPORT = "没关系，这些不一定马上说得清，我们慢慢来。"
VERIFY = "我想确认一下，现在你还有这种念头吗？"
COMPONENTS = {"P1": ["sleep_hygiene", "fixed_risetime"], "P2": ["stimulus_control", "fixed_risetime"],
              "P3": ["worry_time", "cognitive_restructuring"], "P4": ["light_timing", "schedule_shift"],
              "P5": ["digital_curfew", "fixed_risetime"]}


class MockAgentLLM:
    def __init__(self, model_name: str = "mock-agent"):
        self.model_name = model_name

    async def complete_json(self, messages: list[dict], *, task: str, state: dict) -> dict:
        return getattr(self, f"_{task}")(state)

    # ------------------------------------------------------------ loop 1

    def _strategy(self, state: dict) -> dict:
        if state["history_check_required"]:
            return {"action": "say", "strategy": {"type": "verify_safety", "target_topic": "self_harm",
                                                  "contrast": [], "revisit_later": None, "intent": "核验当前是否仍有"}}
        visitor = _visitor_text(state)
        called = {c["tool"] for c in state["tool_calls"]}
        if "screen_osa" not in called and re.search(r"打鼾|憋醒|呼吸.{0,4}停", visitor):
            return {"action": "tool", "tool": "screen_osa", "strategy": {"type": "screen", "intent": "补筛"}}
        if "screen_mood" not in called and re.search(r"低落|提不起|没兴趣", visitor):
            return {"action": "tool", "tool": "screen_mood", "strategy": {"type": "screen", "intent": "补筛"}}
        cls = state["classification"]
        asked = set(state["asked_topics"])
        if cls and cls["attitude"] == "resistant" and state["last_target"]:
            return _say("supportive", None, revisit=state["last_target"])
        for topic in state["deferred_topics"]:
            return _say("revisit", topic)
        if cls and cls["uncertainty"] <= 0.95 and cls["margin"] < 0.25:
            top2 = sorted(cls["weights"], key=lambda p: -cls["weights"][p])[:2]
            topic = DISCRIMINATE.get(frozenset(top2))
            if topic and topic not in asked:
                return _say("discriminate", topic, contrast=top2)
        for topic in EXPLORE[state["round"]]:
            if topic not in asked:
                return _say("explore", topic)
        return {"action": "end_round", "strategy": {"type": "end", "intent": "信息已足够"}}

    def _response(self, state: dict) -> dict:
        strategy = state["strategy"]
        if strategy["type"] == "verify_safety":
            return {"text": VERIFY, "acts": ["emotion_response"]}
        if strategy["type"] == "supportive":
            return {"text": SUPPORT, "acts": ["emotion_response"]}
        topic = strategy.get("target_topic")
        text = QUESTION.get(topic, "能再多说说你的睡眠情况吗？")
        if strategy["type"] == "revisit":
            text = "刚才提到的事，我换个场景再问问：" + text
        return {"text": text, "acts": ["reflection"] if state["agent_texts"] else ["goal_setting"]}

    def _turn(self, state: dict) -> dict:
        result = self._strategy(state)
        if result["action"] == "say":
            result.update(self._response({**state, "strategy": result["strategy"]}))
        return result

    # ------------------------------------------------------------ round end / loop 2

    def _memory(self, state: dict) -> dict:
        return {"summary": "mock 摘要", "facts": [], "open_questions": [], "referral": _referral(state),
                "referral_reason": "mock"}

    def _plan(self, state: dict) -> dict:
        path = state["path_top"]
        components = list(COMPONENTS[path])
        advice = None
        if state["referral"] != "R0":
            components.append("referral_advice")
            advice = "建议到医院相关科室进一步评估。"
        return {
            "plan": {"bedtime": "23:30", "risetime": "07:00", "tib_minutes": 450, "components": components,
                     "rationale_given": True, "referral_advice": advice,
                     "cards": [{"type": "reminder", "title": "固定起床时间", "body": "明早七点起床，先坚持一周。"}]},
            "contraindications_identified": [], "age": None,
            "closing_message": "我们先从固定起床时间开始，每天七点起床，这样身体的节律会慢慢稳定下来。",
        }

    def _select(self, state: dict) -> dict:
        outcome = state["round1_outcome"]
        keep = outcome is not None and outcome["isi_change"] <= -7
        return {"decision": "maintain" if keep else "adjust", "rationale": "mock", "focus": "mock"}


def _say(kind, topic, *, contrast=(), revisit=None):
    return {"action": "say", "strategy": {"type": kind, "target_topic": topic, "contrast": list(contrast),
                                          "revisit_later": revisit, "intent": kind}}


def _visitor_text(state: dict) -> str:
    return "".join(e["text"] for e in state["transcript"] if e["speaker"] == "visitor")


def _referral(state: dict) -> str:
    for call in state["tool_calls"]:
        result = call["result"]
        if call["tool"] == "screen_osa" and result["stop_bang"] >= 3:
            return "R1"
        if call["tool"] == "screen_mood" and (result["phq9"] >= 10 or result["gad7"] >= 10):
            return "R3"
    if re.search(r"腿.{0,8}(?:难受|想动|虫)", _visitor_text(state)):
        return "R2"
    return "R0"
