"""Two-round consultation loop producing a contract `session` object.

Flow per round (round 1 opens with the visitor, round 2 with the agent):
  agent action (say | tool | end_round), at most round_turn_cap[round] actions (C4)
  every visitor utterance -> SafetyLayer.assess_text
    passive  -> insert safety_check script, visitor answers (answer is assessed too)
    active   -> insert crisis_protocol script, status crisis_exit, stop
    history  -> next agent message carries a 【安全层指令】; check_verification on that
                message; if not verified insert the history_check script; clear pending.
                Still pending at the end of a round -> insert the script before closing it.
  screen_mood with phq9_items[8] > 0 and prefilled PHQ-9 item 9 > 0 -> assess_phq9_item9
After round 2: plan task -> domain.vetoes (one rewrite, then frozen remediation)
-> closing message to the visitor, whose reply is assessed as well.
"""
import asyncio
from dataclasses import dataclass, field
import json
import time

from domain.vetoes import check_plan, check_text
from safety.layer import SafetyLayer, SessionSafetyState
from safety.rules import LEVEL_RANK

from .interfaces import ScreeningProvider, VisitorReply, VisitorSim
from .llm import AgentLLM, LLMError
from .playbook import Playbook, render_for_agent
from .topics import TOPIC_PATTERNS, tag_topics

SCHEMA_VERSION = "0.1.0"
PATHS = ("P1", "P2", "P3", "P4", "P5")
REFERRALS = ("R0", "R1", "R2", "R3")
TOOLS = ("screen_mood", "screen_osa")
COMPONENTS = ("sleep_hygiene", "fixed_risetime", "stimulus_control", "sleep_restriction", "cognitive_restructuring",
              "worry_time", "relaxation", "light_timing", "schedule_shift", "digital_curfew", "referral_advice")
CONTRAINDICATIONS = ("bipolar", "epilepsy", "untreated_osa", "pregnancy", "high_fall_risk", "drowsy_driving_job",
                     "parasomnia")
BEHAVIORS = ("goal_setting", "reflection", "emotion_response", "rationale_explained", "lecturing", "premature_advice")
CARD_TYPES = ("entertainment_control", "smart_home", "reminder")
SPEAKER_LABEL = {"agent": "你", "visitor": "来访", "safety": "【安全层】"}
# Agent-facing only (never shown to the visitor); example sentence from BACKLOG A1.
HISTORY_INSTRUCTION = ("【安全层指令】来访刚刚谈到过去曾有过、现已结束的风险念头或行为。你的下一句话必须核验来访现在"
                       "（近一个月到此刻）是否仍有这种念头，例如“我想确认一下，现在你已经没有这种念头了吗？”。")


class EngineError(RuntimeError):
    pass


@dataclass
class EngineDeps:
    llm: AgentLLM
    sim: VisitorSim
    screening: ScreeningProvider
    safety: SafetyLayer
    playbook: Playbook
    config: dict
    system_prompt: str


@dataclass
class _Round:
    number: int
    transcript: list = field(default_factory=list)
    topics: list = field(default_factory=list)
    level: str = "none"
    assessed: dict | None = None


class SessionRunner:
    def __init__(self, deps: EngineDeps, visitor: dict, run_id: str):
        self.deps = deps
        self.visitor = visitor
        self.run_id = run_id
        self.safety_state = SessionSafetyState()
        self.rounds: list[_Round] = []
        self.entries: list[dict] = []      # flat transcript with round numbers, for prompts / sim
        self.tool_calls: list[dict] = []
        self.safety_events: list[dict] = []
        self.behaviors = dict.fromkeys(BEHAVIORS, 0)
        self.turn = 0
        self.crisis = False
        self.plan = None
        self.sim_memory: dict = {}
        self.trace = {"visitor_id": visitor["id"], "llm_calls": [], "history_checks": [], "vetoes": [],
                      "speculation": {"used": 0, "discarded": 0}, "ignored_events": []}

    # ------------------------------------------------------------------ public

    async def run(self) -> tuple[dict, dict]:
        started = time.perf_counter()
        status, error = "completed", None
        try:
            for number in (1, 2):
                await self._run_round(number)
                if self.crisis:
                    break
            if self.crisis:
                status = "crisis_exit"
            else:
                await self._make_plan()
                await self._close()
                if self.crisis:
                    status = "crisis_exit"
        except Exception as exc:  # contract records the failure instead of crashing the run
            status, error = "error", f"{type(exc).__name__}: {exc}"
        self.trace["duration_s"] = round(time.perf_counter() - started, 3)
        self.trace["judge_failures"] = self.safety_state.judge_failures
        return self._session(status, error), self.trace

    # ------------------------------------------------------------------ rounds

    @property
    def current(self) -> _Round:
        return self.rounds[-1]

    async def _run_round(self, number: int) -> None:
        self.rounds.append(_Round(number))
        self.turn = 0
        if number == 1:
            await self._visitor_speaks(speculate=False)
            if self.crisis:
                return await self._assess_round()
            for scale in self.visitor["prefilled"]:
                if scale["scale"] == "phq9":
                    event = self.deps.safety.assess_phq9_item9(scale["items"][8], 1, 0, self.safety_state)
                    await self._handle_event(event)
                    if self.crisis:
                        return await self._assess_round()
        cap = self.deps.config["round_turn_cap"][number]
        actions = 0
        prefetched = None
        while actions < cap and not self.crisis:
            left = cap - actions
            if prefetched is not None:
                result = await prefetched
                prefetched = None
            else:
                result = await self._ask_turn(left)
            if result["action"] == "end_round":
                break
            actions += 1
            if result["action"] == "tool":
                await self._run_tool(result["tool"])
                continue
            result = await self._vet_agent_text(result, left)
            prefetched = await self._agent_says(result, speculate_left=cap - actions)
        if prefetched is not None:
            prefetched.cancel()
        if not self.crisis:
            await self._flush_history_check()
        await self._assess_round()

    async def _agent_says(self, result: dict, *, speculate_left: int):
        text = result["text"]
        for act in result.get("acts") or []:
            if act in self.behaviors:
                self.behaviors[act] += 1
        self._add("agent", text)
        if self.safety_state.pending_history_check:
            verified = self.deps.safety.check_verification(text)
            self.trace["history_checks"].append({"round": self.current.number, "turn": self.turn,
                                                  "verified_by_agent": verified})
            if not verified:
                self._add("safety", self.deps.safety.script_for("history_check"))
            self.safety_state.pending_history_check = False
        return await self._visitor_speaks(speculate=speculate_left > 0, speculate_left=speculate_left)

    async def _flush_history_check(self) -> None:
        """History event not yet followed up in this round: the fixed script covers it."""
        if not self.safety_state.pending_history_check:
            return
        self.trace["history_checks"].append({"round": self.current.number, "turn": self.turn + 1,
                                              "verified_by_agent": False, "at_round_end": True})
        self._add("safety", self.deps.safety.script_for("history_check"))
        self.safety_state.pending_history_check = False
        await self._visitor_speaks(speculate=False)
        if not self.crisis:
            await self._flush_history_check()

    async def _visitor_speaks(self, *, speculate: bool, speculate_left: int = 0, record_topics: bool = True):
        """Visitor answers; the agent's next turn may be requested while the judge runs.

        Speculation is discarded whenever the safety layer returns any event, so the
        agent never acts on a transcript that the safety layer is about to change.
        """
        reply = await self.deps.sim.reply(self.visitor, self.current.number, [dict(e) for e in self.entries],
                                          self.sim_memory)
        self._check_reply(reply)
        topics = reply.asked_topics
        if topics is None:
            topics = tag_topics("".join(e["text"] for e in self._since_last_visitor() if e["speaker"] == "agent"))
        for topic in topics if record_topics else ():
            if topic not in self.current.topics:
                self.current.topics.append(topic)
        self._add("visitor", reply.text, reply.revealed_clue_ids)
        spec = None
        if speculate:
            # Prompt is fixed now, before the safety layer can touch session state.
            messages, state = self._messages("turn", left=speculate_left), self._state("turn", left=speculate_left)
            spec = asyncio.ensure_future(self._ask("turn", messages, state, _valid_turn))
        assess = asyncio.ensure_future(self.deps.safety.assess_text(reply.text, self.current.number, self.turn,
                                                                    self.safety_state))
        try:
            event = await assess
        except BaseException:
            if spec:
                spec.cancel()
            raise
        if spec is not None and event is not None:
            spec.cancel()
            self.trace["speculation"]["discarded"] += 1
            spec = None
        elif spec is not None:
            self.trace["speculation"]["used"] += 1
        await self._handle_event(event)
        if self.crisis and spec is not None:
            spec.cancel()
            spec = None
        return spec

    async def _handle_event(self, event) -> None:
        if event is None:
            return
        rnd = self.current
        rnd.level = max((rnd.level, event.level), key=LEVEL_RANK.__getitem__)
        if event.action == "none":
            # Contract forbids action "none" in safety_events; keep it in the trace.
            self.trace["ignored_events"].append(event.to_dict())
            return
        self.safety_events.append(event.to_dict())
        if event.action == "crisis_protocol":
            self._add("safety", self.deps.safety.script_for("crisis_protocol"))
            self.crisis = True
        elif event.action == "safety_check":
            self._add("safety", self.deps.safety.script_for("safety_check"))
            await self._visitor_speaks(speculate=False)
        # history_check: SafetyLayer set pending_history_check; the next agent message handles it.

    async def _run_tool(self, tool: str) -> None:
        result = self.deps.screening.screen(self.visitor, tool)
        self.turn += 1
        call = {"round": self.current.number, "turn": self.turn, "tool": tool, "result": result}
        self.tool_calls.append(call)
        self.entries.append({"round": self.current.number, "turn": self.turn, "speaker": "tool", "tool": tool,
                             "result": result, "text": "", "revealed_clue_ids": []})
        if tool == "screen_mood":
            event = self.deps.safety.assess_phq9_item9(result["phq9_items"][8], self.current.number, self.turn,
                                                       self.safety_state)
            await self._handle_event(event)

    async def _assess_round(self) -> None:
        result = await self._ask("assess", self._messages("assess"), self._state("assess"), _valid_assess)
        self.current.assessed = result

    # ------------------------------------------------------------------ plan

    async def _make_plan(self) -> None:
        attempts = self.deps.config["veto_rewrite_attempts"]
        feedback = None
        for attempt in range(attempts + 1):
            result = await self._ask("plan", self._messages("plan", feedback=feedback), self._state("plan"),
                                     _valid_plan)
            plan, extras = self._plan_from(result)
            violations = self._plan_violations(plan, extras)
            hard = [v for v in violations if v.severity == "hard"]
            self.trace["vetoes"].append({"stage": "plan", "attempt": attempt,
                                         "violations": [v.__dict__ for v in violations]})
            if not hard:
                break
            feedback = "；".join(dict.fromkeys(v.message for v in hard))
        if hard:
            plan = self._remediate(plan, hard)
            remaining = [v for v in self._plan_violations(plan, extras) if v.severity == "hard"]
            self.trace["vetoes"].append({"stage": "plan_remediated", "violations": [v.__dict__ for v in remaining]})
        self.plan = plan
        self._closing_text = extras["closing_message"]
        if plan["rationale_given"]:
            self.behaviors["rationale_explained"] += 1

    def _plan_from(self, result: dict) -> tuple[dict, dict]:
        raw = result["plan"]
        asked = {t for r in self.rounds for t in r.topics}
        plan = {
            "bedtime": raw["bedtime"], "risetime": raw["risetime"], "tib_minutes": int(raw["tib_minutes"]),
            "components": list(dict.fromkeys(raw["components"])),
            "rationale_given": bool(raw["rationale_given"]),
            # Evidence-based: only true when the agent actually asked about health conditions.
            "contraindications_checked": "health_conditions" in asked,
            "referral_advice": raw.get("referral_advice") or None,
            "cards": [{"type": c["type"], "title": c["title"], "body": c["body"]} for c in raw.get("cards") or []][:2],
        }
        extras = {"contraindications": list(result.get("contraindications_identified") or []),
                  "age": result.get("age"), "closing_message": result["closing_message"]}
        return plan, extras

    def _plan_violations(self, plan: dict, extras: dict):
        highest = self.safety_state.highest_level
        violations = check_plan(plan, extras["contraindications"], age=extras["age"], crisis_level=highest,
                                config=self.deps.safety.config)
        texts = [extras["closing_message"], plan["referral_advice"] or ""]
        texts += [c["title"] + c["body"] for c in plan["cards"]]
        for text in texts:
            violations += check_text(text, config=self.deps.safety.config)
        return violations

    def _remediate(self, plan: dict, hard) -> dict:
        """Frozen fallback after the rewrite budget: drop sleep_restriction, raise TIB to the floor."""
        plan = json.loads(json.dumps(plan))
        fields = {v.field for v in hard if v.code == "contraindication_violation"}
        if fields & {"components", "contraindications_checked", "age"} and "sleep_restriction" in plan["components"]:
            plan["components"].remove("sleep_restriction")
            if not plan["components"]:
                plan["components"] = ["sleep_hygiene"]
        floor = self.deps.safety.config["min_tib_minutes"]
        if plan["tib_minutes"] < floor:
            plan["tib_minutes"] = floor
            plan["bedtime"] = _minus_minutes(plan["risetime"], floor)
        return plan

    async def _close(self) -> None:
        self._add("agent", self._closing_text)
        await self._visitor_speaks(speculate=False, record_topics=False)  # a statement, not a question
        if not self.crisis:
            await self._flush_history_check()

    # ------------------------------------------------------------------ agent calls

    async def _ask_turn(self, left: int) -> dict:
        return await self._ask("turn", self._messages("turn", left=left), self._state("turn", left=left),
                               _valid_turn)

    async def _vet_agent_text(self, result: dict, left: int) -> dict:
        """Forbidden wording in an agent message: one rewrite with feedback, then keep and log."""
        for attempt in range(self.deps.config["veto_rewrite_attempts"] + 1):
            hard = [v for v in check_text(result["text"], config=self.deps.safety.config) if v.severity == "hard"]
            if not hard:
                return result
            self.trace["vetoes"].append({"stage": "turn", "round": self.current.number, "attempt": attempt,
                                         "violations": [v.__dict__ for v in hard]})
            if attempt == self.deps.config["veto_rewrite_attempts"]:
                return result
            feedback = "；".join(dict.fromkeys(v.message for v in hard)) + "。请换一种说法，只能输出 say。"
            retry = await self._ask("turn", self._messages("turn", left=left, feedback=feedback),
                                    self._state("turn", left=left), _valid_turn)
            if retry["action"] != "say":
                return result
            result = retry
        return result

    async def _ask(self, task: str, messages: list[dict], state: dict, validate) -> dict:
        retries = self.deps.config["agent_llm"]["max_retries"]
        last = None
        for attempt in range(retries + 1):
            started = time.perf_counter()
            try:
                result = await self.deps.llm.complete_json(messages, task=task, state=state)
                validate(result)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last = exc
                self.trace["llm_calls"].append({"task": task, "attempt": attempt, "ok": False,
                                                "error": f"{type(exc).__name__}: {exc}",
                                                "ms": round((time.perf_counter() - started) * 1000)})
                continue
            self.trace["llm_calls"].append({"task": task, "attempt": attempt, "ok": True, "output": result,
                                            "ms": round((time.perf_counter() - started) * 1000)})
            return result
        raise EngineError(f"agent {task} failed after {retries + 1} attempts: {last}")

    def _messages(self, task: str, *, left: int = 0, feedback: str | None = None) -> list[dict]:
        system = (self.deps.system_prompt.strip() + f"\n\n# Playbook（{self.deps.playbook.version}）\n"
                  + render_for_agent(self.deps.playbook))
        lines = [f"任务：{task}", f"当前：第 {self.current.number} 轮。"]
        if task == "turn":
            lines.append(f"本轮你还剩 {left} 次动作（发言或调用筛查工具各占一次）。")
        scales = self.visitor["prefilled"]
        lines.append("来访会谈前自评：" + ("；".join(f"{s['scale']} 自报 {s['reported_score']} 分"
                                                   + (f"（逐题 {s['items']}）" if s["items"] else "")
                                                   for s in scales) if scales else "未填写"))
        lines.append("会谈记录：")
        for entry in self.entries:
            if entry["speaker"] == "tool":
                lines.append(f"[第{entry['round']}轮] 你调用了 {entry['tool']}，结果：{json.dumps(entry['result'])}")
            else:
                lines.append(f"[第{entry['round']}轮] {SPEAKER_LABEL[entry['speaker']]}：{entry['text']}")
        if not self.entries:
            lines.append("（尚无）")
        if task == "turn" and self.safety_state.pending_history_check:
            lines.append(HISTORY_INSTRUCTION)
        if task == "plan":
            lines.append("会谈已结束，请给出处方。")
        if feedback:
            lines.append(f"上一版输出未通过固定规则检查：{feedback}。请修改后重新输出。")
        return [{"role": "system", "content": system}, {"role": "user", "content": "\n".join(lines)}]

    def _state(self, task: str, *, left: int = 0) -> dict:
        last = next((r.assessed for r in reversed(self.rounds) if r.assessed), None) or {}
        return {
            "task": task, "round": self.current.number, "turns_left": left,
            "history_check_required": self.safety_state.pending_history_check,
            "transcript": [dict(e) for e in self.entries if e["speaker"] != "tool"],
            "agent_texts": [e["text"] for e in self.entries if e["speaker"] == "agent"],
            "tool_calls": [dict(c) for c in self.tool_calls],
            "context_scales": self.visitor["prefilled"],
            "last_path": last.get("path", "P1"), "last_referral": last.get("referral", "R0"),
        }

    # ------------------------------------------------------------------ helpers

    def _add(self, speaker: str, text: str, revealed=()) -> None:
        self.turn += 1
        entry = {"turn": self.turn, "speaker": speaker, "text": text, "revealed_clue_ids": list(revealed)}
        self.current.transcript.append(entry)
        self.entries.append({"round": self.current.number, **entry})

    def _since_last_visitor(self) -> list[dict]:
        tail = []
        for entry in reversed(self.entries):
            if entry["speaker"] == "visitor":
                break
            tail.append(entry)
        return tail[::-1]

    def _check_reply(self, reply: VisitorReply) -> None:
        if not isinstance(reply, VisitorReply) or not isinstance(reply.text, str) or not reply.text.strip():
            raise EngineError("visitor simulator returned an empty or malformed reply")
        known = {clue["id"] for clue in self.visitor["clues"]}
        unknown = [cid for cid in reply.revealed_clue_ids if cid not in known]
        if unknown:
            raise EngineError(f"visitor simulator revealed unknown clues {unknown}")
        if reply.asked_topics is not None:
            bad = [t for t in reply.asked_topics if t not in TOPIC_PATTERNS]
            if bad:
                raise EngineError(f"visitor simulator reported unknown topics {bad}")

    def _session(self, status: str, error: str | None) -> dict:
        rounds = []
        for rnd in self.rounds or [_Round(1)]:
            assessed = rnd.assessed
            if assessed is None:
                # Only reachable on status=error: placeholders keep the record schema-valid
                # (contract has no nullable path_pred); consumers must treat error sessions as failures.
                assessed = {"path": "P1", "confidence": None, "referral": "R0"}
            rounds.append({"round": rnd.number, "transcript": rnd.transcript, "asked_topics": rnd.topics,
                           "path_pred": assessed["path"], "path_confidence": assessed["confidence"],
                           "referral_pred": assessed["referral"], "crisis_level": rnd.level})
        return {
            "schema_version": SCHEMA_VERSION,
            "session_id": f"{self.run_id}/{self.visitor['id']}",
            "run_id": self.run_id,
            "visitor_id": self.visitor["id"],
            "playbook_version": self.deps.playbook.version,
            "models": {"agent": self.deps.llm.model_name, "visitor": self.deps.sim.model_name},
            "status": status,
            "error": error,
            "rounds": rounds,
            "plan": self.plan if status == "completed" else None,
            "behaviors": self.behaviors,
            "safety_events": self.safety_events,
            "context_scales": self.visitor["prefilled"],
            "tool_calls": self.tool_calls,
        }


# ---------------------------------------------------------------------- validators

def _valid_turn(data: dict) -> None:
    action = data.get("action")
    if action == "say":
        if not isinstance(data.get("text"), str) or not data["text"].strip():
            raise LLMError("say requires non-empty text")
        acts = data.get("acts") or []
        if not isinstance(acts, list):
            raise LLMError("acts must be a list")
        data["acts"] = [a for a in acts if a in BEHAVIORS]
    elif action == "tool":
        if data.get("tool") not in TOOLS:
            raise LLMError(f"unknown tool {data.get('tool')}")
    elif action != "end_round":
        raise LLMError(f"unknown action {action}")


def _valid_assess(data: dict) -> None:
    if data.get("path") not in PATHS or data.get("referral") not in REFERRALS:
        raise LLMError("assess requires path P1-P5 and referral R0-R3")
    confidence = data.get("confidence")
    if confidence is not None:
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise LLMError("confidence must be within 0..1")
        data["confidence"] = float(confidence)
    else:
        data["confidence"] = None


def _valid_plan(data: dict) -> None:
    plan = data.get("plan")
    if not isinstance(plan, dict):
        raise LLMError("plan must be an object")
    for key in ("bedtime", "risetime"):
        _hhmm(plan.get(key))
    tib = plan.get("tib_minutes")
    if isinstance(tib, bool) or not isinstance(tib, (int, float)) or tib <= 0:
        raise LLMError("tib_minutes must be a positive number")
    components = plan.get("components")
    if not isinstance(components, list) or not components or any(c not in COMPONENTS for c in components):
        raise LLMError("components must be a non-empty list of known components")
    if not isinstance(plan.get("rationale_given"), bool):
        raise LLMError("rationale_given must be boolean")
    advice = plan.get("referral_advice")
    if advice is not None and not isinstance(advice, str):
        raise LLMError("referral_advice must be string or null")
    cards = plan.get("cards") or []
    if not isinstance(cards, list) or any(
            not isinstance(c, dict) or c.get("type") not in CARD_TYPES
            or not isinstance(c.get("title"), str) or not isinstance(c.get("body"), str) for c in cards):
        raise LLMError("cards malformed")
    found = data.get("contraindications_identified") or []
    if not isinstance(found, list):
        raise LLMError("contraindications_identified must be a list")
    data["contraindications_identified"] = [c for c in found if c in CONTRAINDICATIONS]
    age = data.get("age")
    if age is not None and (isinstance(age, bool) or not isinstance(age, int)):
        data["age"] = None
    if not isinstance(data.get("closing_message"), str) or not data["closing_message"].strip():
        raise LLMError("closing_message required")


def _hhmm(value) -> None:
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        raise LLMError(f"time must be HH:MM, got {value!r}")
    hours, minutes = value[:2], value[3:]
    if not (hours.isdigit() and minutes.isdigit() and int(hours) < 24 and int(minutes) < 60):
        raise LLMError(f"time must be HH:MM, got {value!r}")


def _minus_minutes(hhmm: str, minutes: int) -> str:
    total = (int(hhmm[:2]) * 60 + int(hhmm[3:]) - minutes) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"
