"""Two-round consultation loop (TheraMind §3 dual loop, domain-specialised) -> contract `session`.

Loop 1, every agent action (sub-agents with frozen prompts and harness):
  PathClassifier (frozen)  -> {weights P1..P5, attitude, uncertainty}  on the accumulated dialogue
  strategy                 -> say | tool | end_round + strategy (playbook: questioning_strategy, path_discrimination)
  response                 -> text + acts                           (playbook: communication_style)
  (pipeline.merge_strategy_response = true runs strategy + response as one call)
  memory update            -> round 1 combined with plan; round 2 separate referral/summary
Round end: classification -> plan (round 1 provisional, round 2 final;
  playbook: plan_rules, referral_rules) -> vetoes -> closing message -> visitor reply -> final classification.
Loop 2, start of round 2: f_eval = PlanOutcomeModel on the round-1 plan (4-week simulation),
  f_select = maintain | adjust (playbook: plan_rules, referral_rules); both feed round-2 strategy and plan.

Safety (unchanged rules, see safety/SPEC.md): every visitor utterance -> SafetyLayer.assess_text;
  passive -> safety_check script; active -> crisis_protocol + crisis_exit; history -> instruction injected into
  the next agent message (strategy + response), check_verification, fixed fallback, pending cleared;
  PHQ-9 item 9 from prefilled scales (turn 0) and screen_mood results.
While the crisis judge runs, the whole loop-1 pipeline for the next action runs speculatively on a snapshot;
  any safety event discards it.
"""
import asyncio
from dataclasses import asdict, dataclass, field
import json
import re
import time

from domain.vetoes import check_plan, check_text
from safety.layer import SafetyLayer, SessionSafetyState
from safety.rules import LEVEL_RANK

from .classifier import PATHS, PathClassifier, PathState
from .interfaces import PlanOutcomeModel, ScreeningProvider, VisitorReply, VisitorSim
from .llm import AgentLLM, LLMError, TruncatedOutput
from .mock_agent import MockAgentLLM
from .telemetry import CALL_SCOPE, record_call
from .playbook import Playbook, strip_locks
from .plan_postprocess import annotate_restriction, disclosed_tib, explicit_restriction
from .topics import TOPIC_PATTERNS, tag_topics

SCHEMA_VERSION = "0.1.0"
REFERRALS = ("R0", "R1", "R2", "R3")
TOOLS = ("screen_mood", "screen_osa")
COMPONENTS = ("sleep_hygiene", "fixed_risetime", "stimulus_control", "sleep_restriction", "cognitive_restructuring",
              "worry_time", "relaxation", "light_timing", "schedule_shift", "digital_curfew", "referral_advice")
CONTRAINDICATIONS = ("bipolar", "epilepsy", "untreated_osa", "pregnancy", "high_fall_risk", "drowsy_driving_job",
                     "parasomnia")
BEHAVIORS = ("goal_setting", "reflection", "emotion_response", "rationale_explained", "lecturing", "premature_advice")
STRATEGY_TYPES = ("explore", "discriminate", "supportive", "revisit", "verify_safety", "psychoeducation", "screen",
                  "end")
CARD_TYPES = ("entertainment_control", "smart_home", "reminder")
SPEAKER_LABEL = {"agent": "你", "visitor": "来访", "safety": "【安全层】"}
# Which playbook sections each sub-agent reads (the evolution surface per sub-agent).
SECTIONS_FOR = {
    "strategy": ("questioning_strategy", "path_discrimination"),
    "response": ("communication_style",),
    "turn": ("questioning_strategy", "path_discrimination", "communication_style"),
    "memory": ("referral_rules",),
    "plan": ("plan_rules", "referral_rules"),
    "memory_plan": ("plan_rules", "referral_rules"),
    "select": ("plan_rules", "referral_rules"),
}
# Agent-facing only (never shown to the visitor); example sentence from BACKLOG A1.
HISTORY_INSTRUCTION = ("【安全层指令】来访刚刚谈到过去曾有过、现已结束的风险念头或行为。你的下一句话必须核验来访现在"
                       "（近一个月到此刻）是否仍有这种念头，例如“我想确认一下，现在你已经没有这种念头了吗？”。")


class EngineError(RuntimeError):
    pass


@dataclass
class EngineDeps:
    llm: AgentLLM
    classifier: PathClassifier
    sim: VisitorSim
    screening: ScreeningProvider
    outcome: PlanOutcomeModel
    safety: SafetyLayer
    playbook: Playbook
    config: dict
    prompts: dict[str, str]


@dataclass
class _Round:
    number: int
    transcript: list = field(default_factory=list)
    topics: list = field(default_factory=list)
    level: str = "none"
    path_state: PathState | None = None
    referral: str | None = None
    path_pred: str | None = None
    path_confidence: float | None = None


@dataclass(frozen=True)
class _Snapshot:
    """Everything a loop-1 step reads, frozen before the safety layer can change session state."""
    round: int
    left: int
    entries: tuple
    pending_history: bool
    deferred: tuple
    asked: tuple
    last_target: str | None


class SessionRunner:
    def __init__(self, deps: EngineDeps, visitor: dict, run_id: str):
        self.deps = deps
        self.visitor = visitor
        self.run_id = run_id
        self.safety_state = SessionSafetyState()
        self.rounds: list[_Round] = []
        self.entries: list[dict] = []
        self.tool_calls: list[dict] = []
        self.safety_events: list[dict] = []
        self._scale_event_index: int | None = None
        self._safety_check_asked = False
        self._risk_disclosed_after_check = False
        self._scale_recheck_done = False
        self.behaviors = dict.fromkeys(BEHAVIORS, 0)
        self.turn = 0
        self.crisis = False
        self.plans: dict[int, dict] = {}
        self.memory: dict[int, dict] = {}
        self.outcome: dict | None = None
        self.selection: dict | None = None
        self.deferred: list[str] = []
        self.last_target: str | None = None
        self.sim_memory: dict = {}
        self._last_path: PathState | None = None
        self._tasks: set[asyncio.Task] = set()
        self._scope_number = 0
        self._discarded_scopes: set[int] = set()
        self._cls_cache: tuple[int, PathState] | None = None
        self._cls_skipped = False
        self.trace = {"visitor_id": visitor["id"], "pipeline": self._pipeline_name(),
                      "classifier": getattr(deps.classifier, "provider", type(deps.classifier).__name__),
                      "fallbacks": [], "llm_calls": [], "path_probs": [], "strategies": [], "history_checks": [], "vetoes": [],
                      "plans": {}, "memory": {}, "round1_outcome": None, "selection": None, "forced_tool_calls": [],
                      "scale_rechecks": [],
                      "speculation": {"used": 0, "discarded": 0, "discarded_calls": 0}, "ignored_events": []}

    def _pipeline_name(self) -> str:
        return "merged" if self.deps.config["pipeline"]["merge_strategy_response"] else "split"

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
        except Exception as exc:  # contract records the failure instead of crashing the run
            status, error = "error", f"{type(exc).__name__}: {exc}"
        # Drain every speculative task before returning telemetry, also on session failure.
        for task in self._tasks:
            if not task.done():
                self._discarded_scopes.add(task.engine_scope)
                task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        for call in self.trace["llm_calls"]:
            call["discarded"] = call["scope"] in self._discarded_scopes
        self.trace["speculation"]["discarded_calls"] = sum(c["discarded"] for c in self.trace["llm_calls"])
        for fallback in self.trace["fallbacks"]:
            fallback["discarded"] = fallback["scope"] in self._discarded_scopes
        self.trace["all_judge_results"] = [asdict(r) for r in self.safety_state.judge_results]
        self.trace["status"] = status
        self.trace["completed"] = status == "completed"
        self.trace["error_count"] = int(status == "error")
        self.trace["unknown_path_rounds"] = [r.number for r in self.rounds if r.path_pred is None]
        self.trace["duration_s"] = round(time.perf_counter() - started, 3)
        self.trace["judge_failures"] = self.safety_state.judge_failures
        self.trace["latency_ms"] = self._latency_summary()
        return self._session(status, error), self.trace

    # ------------------------------------------------------------------ rounds

    @property
    def current(self) -> _Round:
        return self.rounds[-1]

    async def _run_round(self, number: int) -> None:
        self.rounds.append(_Round(number))
        self.turn = 0
        self.deferred, self.last_target = [], None
        if number == 1:
            await self._visitor_speaks(speculate=False)
            for scale in self.visitor["prefilled"]:
                if scale["scale"] == "phq9" and not self.crisis:
                    event = self.deps.safety.assess_phq9_item9(scale["items"][8], 1, 0, self.safety_state)
                    await self._handle_event(event)
        else:
            await self._evaluate_and_select()
        cap = self.deps.config["round_turn_cap"][number]
        actions, prefetched = 0, None
        while actions < cap and not self.crisis:
            if prefetched is not None:
                step, prefetched = await prefetched, None
                self.trace["speculation"]["used"] += 1
            else:
                step = await self._agent_step(self._snapshot(cap - actions))
            self._commit_step(step)
            if step["action"] == "end_round":
                break
            actions += 1
            if step["action"] == "tool":
                await self._run_tool(step["tool"])
            else:
                # Do not speculate across an imminent mandatory screening result.
                next_left = 0 if number == 1 and actions == 2 and not self._mood_screened() else cap - actions
                prefetched = await self._agent_says(step, next_left=next_left)
            if number == 1 and actions >= 2 and not self.crisis:
                await self._ensure_mood_screen(actions)
        if prefetched is not None:
            await self._discard(prefetched)
        if number == 1 and not self.crisis:
            await self._ensure_mood_screen(actions)  # covers early end_round and caps below two
        if not self.crisis:
            await self._flush_history_check()
        if number == 1 and not self.crisis:
            await self._recheck_scale()
            if not self.crisis:
                await self._flush_history_check()
        await self._close_round()

    async def _close_round(self) -> None:
        rnd = self.current
        await self._set_round_path()
        last_visitor = sum(e['speaker'] == 'visitor' for e in self.entries)
        merged = rnd.number == 1 and self.deps.config["pipeline"].get("merge_memory_plan", False) and not self.crisis
        if not merged:
            memory = await self._ask("memory", self._messages("memory", self._snapshot(0)), self._state("memory"),
                                     _valid_memory)
            self._save_memory(memory)
        if not self.crisis:
            await self._make_plan(rnd.number, merged_memory=merged)
            if self.plans[rnd.number]["closing_message"]:
                self._add("agent", self.plans[rnd.number]["closing_message"])
                await self._visitor_speaks(speculate=False, record_topics=False)
            if not self.crisis:
                await self._flush_history_check()
        # Include closing and any safety-followup replies, without another agent action.
        if sum(e['speaker'] == 'visitor' for e in self.entries) > last_visitor:
            await self._set_round_path()
        effective = rnd.path_state if rnd.path_state.status == "ok" else self._last_path
        self.trace["path_probs"].append({"round": rnd.number, "final": True, **rnd.path_state.to_dict(),
                                         "path_pred": rnd.path_pred or "unknown",
                                         "prediction_source": "current" if rnd.path_state.status == "ok" else
                                         "previous_success" if effective else "unknown"})

    async def _set_round_path(self) -> None:
        rnd = self.current
        rnd.path_state = await self._classify_current()
        effective = rnd.path_state if rnd.path_state.status == "ok" else self._last_path
        rnd.path_pred = effective.top if effective else None
        rnd.path_confidence = round(effective.weights[effective.top], 4) if effective else None

    async def _evaluate_and_select(self) -> None:
        """Loop 2: f_eval (4-week simulation of the round-1 plan) then f_select (maintain | adjust)."""
        plan = self.plans.get(1)
        if plan is None:
            return
        context = {"session": self._session("completed", None)}
        outcome = self.deps.outcome.simulate(self.visitor, plan["plan"], context)
        _valid_outcome(outcome)
        self.outcome = outcome
        self.trace["round1_outcome"] = outcome
        self.sim_memory["round1_outcome"] = outcome
        self.selection = await self._ask("select", self._messages("select", self._snapshot(0)), self._state("select"),
                                         _valid_select)
        self.trace["selection"] = self.selection

    # ------------------------------------------------------------------ loop 1

    def _snapshot(self, left: int) -> _Snapshot:
        return _Snapshot(self.current.number, left, tuple(dict(e) for e in self.entries),
                         self.safety_state.pending_history_check, tuple(self.deferred),
                         tuple(t for r in self.rounds if r.number == self.current.number for t in r.topics),
                         self.last_target)

    async def _agent_step(self, snap: _Snapshot) -> dict:
        """Classifier -> strategy -> response. Only telemetry is committed here; the action may be discarded."""
        cls = await self._classify(snap.entries)
        if self.deps.config["pipeline"]["merge_strategy_response"]:
            result = await self._ask("turn", self._messages("turn", snap, cls), self._state("turn", snap, cls),
                                     _valid_turn)
            strategy = result["strategy"]
        else:
            result = await self._ask("strategy", self._messages("strategy", snap, cls),
                                     self._state("strategy", snap, cls), _valid_strategy)
            strategy = result["strategy"]
            if result["action"] == "say":
                response = await self._ask("response", self._messages("response", snap, cls, strategy=strategy),
                                           self._state("response", snap, cls, strategy=strategy), _valid_response)
                result = {**result, **response}
        return {**result, "strategy": strategy, "classification": cls, "snapshot": snap}

    def _commit_step(self, step: dict) -> None:
        snap, cls = step["snapshot"], step["classification"]
        last_turn = next((e["turn"] for e in reversed(snap.entries) if e["speaker"] == "visitor"
                          and e["round"] == snap.round), 0)
        self.trace["path_probs"].append({"round": snap.round, "turn": last_turn, "final": False, **cls.to_dict()})

        strategy = step["strategy"]
        self.trace["strategies"].append({"round": snap.round, "action": step["action"], **strategy})
        if strategy.get("revisit_later") and strategy["revisit_later"] not in self.deferred:
            self.deferred.append(strategy["revisit_later"])
        if strategy.get("type") == "revisit" and strategy.get("target_topic") in self.deferred:
            self.deferred.remove(strategy["target_topic"])
        if strategy.get("target_topic"):
            self.last_target = strategy["target_topic"]

    async def _classify(self, entries, *, final: bool = False) -> PathState:
        key = len(entries)
        if self._cls_cache and self._cls_cache[0] == key:
            return self._cls_cache[1]
        if (not final and self._cls_cache and not self._cls_skipped
                and "fallback:jev" in self._cls_cache[1].provider):
            self._cls_skipped = True
            self.trace.setdefault("classifier_reuse", []).append(
                {"round": self.current.number, "turn": self.turn, "reason": "jev_unavailable_alternate_action"})
            return self._cls_cache[1]
        self._cls_skipped = False
        with record_call(self.trace["llm_calls"], "classifier", "classify") as row:
            state = await self.deps.classifier.classify([dict(e) for e in entries])
        row.update(ok=state.status == "ok", status=state.status, provider=state.provider)
        self._cls_cache = (key, state)
        if state.status == "ok":
            self._last_path = state
        return state

    async def _classify_current(self) -> PathState:
        return await self._classify(tuple(self.entries), final=True)

    async def _agent_says(self, step: dict, *, next_left: int):
        step = await self._vet_text(step)
        if step["text"]:
            for act in step.get("acts") or []:
                self.behaviors[act] += 1
            self._add("agent", step["text"])
        if self.safety_state.pending_history_check:
            verified = self.deps.safety.check_verification(step["text"])
            self.trace["history_checks"].append({"round": self.current.number, "turn": self.turn,
                                                  "verified_by_agent": verified})
            if not verified:
                self._add("safety", self.deps.safety.script_for("history_check"))
            self.safety_state.pending_history_check = False
        if not step["text"] and self.entries[-1]["speaker"] != "safety":
            return None
        return await self._visitor_speaks(speculate=next_left > 0, next_left=next_left)

    async def _vet_text(self, step: dict) -> dict:
        """Rewrite once, then remove offending user-facing sentences before display."""
        attempts = self.deps.config["veto_rewrite_attempts"]
        for attempt in range(attempts + 1):
            hard = [v for v in check_text(step["text"], config=self.deps.safety.config) if v.severity == "hard"]
            if not hard:
                return step
            self.trace["vetoes"].append({"stage": "turn", "round": self.current.number, "attempt": attempt,
                                         "violations": [v.__dict__ for v in hard]})
            if attempt == attempts:
                return {**step, "text": self._redact_text(step["text"], "turn")}
            feedback = "；".join(dict.fromkeys(v.message for v in hard))
            snap, cls = step["snapshot"], step["classification"]
            task = "turn" if self.deps.config["pipeline"]["merge_strategy_response"] else "response"
            validate = _valid_turn if task == "turn" else _valid_response
            retry = await self._ask(task, self._messages(task, snap, cls, strategy=step["strategy"], feedback=feedback),
                                    self._state(task, snap, cls, strategy=step["strategy"]), validate)
            if task == "turn" and retry["action"] != "say":
                return {**step, "text": self._redact_text(step["text"], "turn")}
            step = {**step, "text": retry["text"], "acts": retry.get("acts", [])}
        return step

    def _redact_text(self, text: str, field: str) -> str:
        # Keep delimiters; an unpunctuated final sentence is checked too.
        sentences = re.findall(r"[^。！？!?；;\n]+[。！？!?；;\n]*|[。！？!?；;\n]+", text)
        removed, kept = [], []
        for sentence in sentences:
            hard = [v for v in check_text(sentence, context="user_facing", config=self.deps.safety.config)
                    if v.severity == "hard"]
            (removed if hard else kept).append(sentence)
        clean = "".join(kept).strip()
        # Normalisation can match across a newline; fail closed if sentence splitting missed it.
        if any(v.severity == "hard" for v in check_text(clean, context="user_facing", config=self.deps.safety.config)):
            removed.extend(kept)
            clean = ""
        if removed:
            self.trace["vetoes"].append({"stage": "text_redacted", "round": self.current.number,
                                         "field": field, "removed_sentences": removed})
        return clean

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

    async def _recheck_scale(self) -> None:
        """Frozen 11/14 rule: once after round-1 actions, before memory/plan/closing.

        Reuse the original scale evidence; this is a follow-up action, not a new
        assessment. Ordinary safety_check speech dedup must not swallow it.
        """
        if (self.current.number != 1 or self.crisis or self.safety_state.highest_level == "active"
                or self._scale_event_index is None or not self._safety_check_asked
                or self._risk_disclosed_after_check or self._scale_recheck_done):
            return
        self._scale_recheck_done = True
        event = {**self.safety_events[self._scale_event_index], "round": 1, "turn": self.turn + 1,
                 "action": "safety_check"}
        self.trace["scale_rechecks"].append({
            "round": 1, "turn": event["turn"], "recheck": True, "counts_toward_cap": False,
            "trigger_event_index": self._scale_event_index, "safety_event_index": len(self.safety_events),
        })
        self.safety_events.append(event)
        self._add("safety", self.deps.safety.script_for("scale_recheck"))
        await self._visitor_speaks(speculate=False)

    async def _visitor_speaks(self, *, speculate: bool, next_left: int = 0, record_topics: bool = True):
        """Visitor answers; the next loop-1 step may run while the crisis judge works (discarded on any event)."""
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
            self._scope_number += 1
            token = CALL_SCOPE.set(self._scope_number)
            try:
                spec = asyncio.create_task(self._agent_step(self._snapshot(next_left)))
            finally:
                CALL_SCOPE.reset(token)
            spec.engine_scope = self._scope_number
            self._tasks.add(spec)
        assess = asyncio.ensure_future(self.deps.safety.assess_text(reply.text, self.current.number, self.turn,
                                                                    self.safety_state))
        try:
            event = await assess
        except BaseException:
            if spec:
                await self._discard(spec)
            raise
        if spec is not None and event is not None:
            await self._discard(spec)
            spec = None
        # Count text disclosures even when repeated passive has local action=none
        # and is omitted from contract events. Later positive scales are not disclosures.
        if self._safety_check_asked and event is not None and event.level in ("passive", "active"):
            self._risk_disclosed_after_check = True
        await self._handle_event(event)
        if spec is not None and self.crisis:
            await self._discard(spec)
            spec = None
        return spec

    async def _discard(self, task: asyncio.Task) -> None:
        self.trace["speculation"]["discarded"] += 1
        self._discarded_scopes.add(task.engine_scope)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def _handle_event(self, event) -> None:
        if event is None:
            return
        rnd = self.current
        rnd.level = max((rnd.level, event.level), key=LEVEL_RANK.__getitem__)
        if event.action == "none":
            # Contract forbids action "none" in safety_events; keep it in the trace (reported conflict).
            self.trace["ignored_events"].append(event.to_dict())
            return
        self.safety_events.append(event.to_dict())
        if event.source == "scale_item9" and self._scale_event_index is None:
            self._scale_event_index = len(self.safety_events) - 1
        if event.action == "crisis_protocol":
            self._add("safety", self._event_script(event))
            self.crisis = True
        elif event.action == "safety_check":
            script = self._event_script(event)
            if script:
                self._add("safety", script)
                self._safety_check_asked = True
                await self._visitor_speaks(speculate=False)

    def _event_script(self, event):
        helper = getattr(self.deps.safety, "script_for_event", None)
        if helper is not None:
            return helper(event, self.safety_state)
        # Legacy S1 exports: no dedup API; trace the compatibility path explicitly.
        self.trace["legacy_safety_api"] = True
        return self.deps.safety.script_for(event.action)

    def _mood_screened(self) -> bool:
        return any(c["round"] == 1 and c["tool"] == "screen_mood" for c in self.tool_calls)

    async def _ensure_mood_screen(self, actions: int) -> None:
        if not self._mood_screened():
            await self._run_tool("screen_mood", forced_after=actions)

    async def _run_tool(self, tool: str, *, forced_after: int | None = None) -> None:
        result = self.deps.screening.screen(self.visitor, tool)
        self.turn += 1
        self.tool_calls.append({"round": self.current.number, "turn": self.turn, "tool": tool, "result": result})
        # tool_calls/result are closed schemas: identify the exact existing call in trace.
        if forced_after is not None:
            self.trace["forced_tool_calls"].append({"round": self.current.number, "turn": self.turn,
                "tool": tool, "tool_call_index": len(self.tool_calls) - 1, "forced": True,
                "after_actions": forced_after, "counts_toward_cap": False})
        self.entries.append({"round": self.current.number, "turn": self.turn, "speaker": "tool", "tool": tool,
                             "result": result, "text": "", "revealed_clue_ids": []})
        if tool == "screen_mood":
            event = self.deps.safety.assess_phq9_item9(result["phq9_items"][8], self.current.number, self.turn,
                                                       self.safety_state)
            await self._handle_event(event)

    # ------------------------------------------------------------------ plan

    def _save_memory(self, memory: dict) -> None:
        self.memory[self.current.number] = memory
        self.trace["memory"][str(self.current.number)] = memory
        self.current.referral = memory["referral"]

    async def _make_plan(self, number: int, *, merged_memory: bool = False) -> None:
        attempts = self.deps.config["veto_rewrite_attempts"]
        feedback, hard = None, []
        snap = self._snapshot(0)
        task = "memory_plan" if merged_memory else "plan"
        for attempt in range(attempts + 1):
            result = await self._ask(task, self._messages(task, snap, feedback=feedback), self._state(task),
                                     _valid_memory_plan if merged_memory else _valid_plan)
            if merged_memory:
                self._save_memory(result["memory"])
            plan, extras = self._plan_from(result)
            evidence = annotate_restriction(plan, extras, self.entries, self.memory)
            self.trace.setdefault("plan_postprocessing", []).append(
                {"round": number, "attempt": attempt, **evidence})
            violations = self._plan_violations(plan, extras)
            hard = [v for v in violations if v.severity == "hard"]
            self.trace["vetoes"].append({"stage": "plan", "round": number, "attempt": attempt,
                                         "violations": [v.__dict__ for v in violations]})
            if not hard:
                break
            feedback = "；".join(dict.fromkeys(v.message for v in hard))
        if hard:
            restriction_vetoed = "sleep_restriction" in plan["components"] and any(
                v.code == "contraindication_violation" and v.field in
                {"components", "contraindications_checked", "age"} for v in hard)
            plan = self._remediate(plan, hard)
            if restriction_vetoed:
                baseline, _ = disclosed_tib(self.entries, self.memory)
                if baseline is not None:
                    plan["tib_minutes"] = max(baseline, plan["tib_minutes"])
                    plan["bedtime"] = _minus_minutes(plan["risetime"], plan["tib_minutes"])
                # Removing a label alone leaves the rejected prescription in prose/cards.
                extras["closing_message"] = ""
                plan["cards"] = []
                if explicit_restriction(plan["referral_advice"] or ""):
                    plan["referral_advice"] = None
            extras["closing_message"] = self._redact_text(extras["closing_message"], "closing_message")
            plan["referral_advice"] = self._redact_text(plan["referral_advice"] or "", "referral_advice") or None
            for card in plan["cards"]:
                for field in ("title", "body"):
                    card[field] = self._redact_text(card[field], f"cards.{field}")
            plan["cards"] = [c for c in plan["cards"] if c["title"] and c["body"]]
            remaining = [v for v in self._plan_violations(plan, extras) if v.severity == "hard"]
            self.trace["vetoes"].append({"stage": "plan_remediated", "round": number,
                                         "violations": [v.__dict__ for v in remaining]})
        self.plans[number] = {"plan": plan, "closing_message": extras["closing_message"]}
        self.trace["plans"][str(number)] = self.plans[number]
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
        violations = check_plan(plan, extras["contraindications"], age=extras["age"],
                                crisis_level=self.safety_state.highest_level, config=self.deps.safety.config)
        texts = [extras["closing_message"], plan["referral_advice"] or ""] + [c["title"] + c["body"]
                                                                              for c in plan["cards"]]
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

    # ------------------------------------------------------------------ prompts

    def _messages(self, task: str, snap: _Snapshot, cls: PathState | None = None, *, strategy: dict | None = None,
                  feedback: str | None = None) -> list[dict]:
        prompts = self.deps.prompts
        if task == "turn":
            body = (prompts["strategy"] + "\n\n" + prompts["response"] + "\n\n# 输出格式（以此为准）\n"
                    + prompts["turn_merged"])
        elif task == "memory_plan":
            body = (prompts["memory"] + "\n\n" + prompts["plan"] + "\n\n" + prompts["memory_plan"])
        else:
            body = prompts[task]
        playbook = "\n\n".join(f"## {name}\n{strip_locks(self.deps.playbook.sections[name])}"
                             for name in SECTIONS_FOR[task])
        system = (f"{prompts['boundaries'].strip()}\n\n{body.strip()}\n\n# Playbook（{self.deps.playbook.version}，"
                  f"仅本模块相关章节）\n{playbook}")
        lines = [f"任务：{task}", f"当前：第 {snap.round} 轮。"]
        if task in ("strategy", "turn"):
            lines.append(f"本轮你还剩 {snap.left} 次动作（发言或调用筛查工具各占一次）。")
        scales = self.visitor["prefilled"]
        lines.append("来访会谈前自评：" + ("；".join(f"{s['scale']} 自报 {s['reported_score']} 分"
                                                   + (f"（逐题 {s['items']}）" if s["items"] else "")
                                                   for s in scales) if scales else "未填写"))
        if snap.round == 2 and 1 in self.memory:
            lines.append("第 1 轮记忆：" + json.dumps({k: self.memory[1][k] for k in ("summary", "facts",
                                                                                   "open_questions")},
                                                    ensure_ascii=False))
        if snap.round == 2 and self.outcome is not None:
            lines.append("第 1 轮处方：" + json.dumps(self.plans[1]["plan"], ensure_ascii=False))
            lines.append("第 1 轮处方 4 周模拟结果：" + json.dumps(
                {k: self.outcome[k] for k in ("isi_week", "isi_change", "adherence")}, ensure_ascii=False))
        if self.selection is not None and task != "select":
            lines.append("第 2 轮方案决定：" + json.dumps(self.selection, ensure_ascii=False))
        lines.append("会谈记录：")
        for entry in snap.entries:
            if entry["speaker"] == "tool":
                lines.append(f"[第{entry['round']}轮] 你调用了 {entry['tool']}，结果：{json.dumps(entry['result'])}")
            else:
                lines.append(f"[第{entry['round']}轮] {SPEAKER_LABEL[entry['speaker']]}：{entry['text']}")
        if not snap.entries:
            lines.append("（尚无）")
        if cls is not None and task in ("strategy", "turn"):
            lines.append("路径分类器：" + json.dumps({"weights": {p: round(w, 3) for p, w in cls.weights.items()},
                                                    "attitude": cls.attitude, "uncertainty": cls.uncertainty},
                                                   ensure_ascii=False))
            lines.append("待稍后追问的话题：" + ("、".join(snap.deferred) if snap.deferred else "无"))
        if strategy is not None and task == "response":
            lines.append("本步策略：" + json.dumps(strategy, ensure_ascii=False))
        if task in ("memory", "memory_plan"):
            lines.append(f"本轮已问到的话题：{'、'.join(snap.asked) or '无'}")
        if task in ("plan", "memory_plan"):
            rnd = self.current
            lines.append(f"路径分类器最终权重：{json.dumps(rnd.path_state.weights if rnd.path_state else {})}；"
                         f"本轮转介判断：{rnd.referral}")
            lines.append("第 1 轮会谈已结束，请给出先试行的处方。" if snap.round == 1 else "会谈已结束，请给出最终处方。")
        if task in ("strategy", "response", "turn") and snap.pending_history:
            lines.append(HISTORY_INSTRUCTION)
        if feedback:
            lines.append(f"上一版输出未通过固定规则检查：{feedback}。请修改后重新输出。")
        return [{"role": "system", "content": system}, {"role": "user", "content": "\n".join(lines)}]

    def _state(self, task: str, snap: _Snapshot | None = None, cls: PathState | None = None, *,
               strategy: dict | None = None) -> dict:
        """Structured twin of the prompt for the offline mock policy."""
        snap = snap or self._snapshot(0)
        rnd = self.current
        return {
            "task": task, "round": snap.round, "turns_left": snap.left,
            "history_check_required": snap.pending_history,
            "transcript": [e for e in snap.entries if e["speaker"] != "tool"],
            "agent_texts": [e["text"] for e in snap.entries if e["speaker"] == "agent"],
            "tool_calls": [dict(c) for c in self.tool_calls],
            "context_scales": self.visitor["prefilled"],
            "classification": cls.to_dict() if cls else None,
            "asked_topics": list(snap.asked), "deferred_topics": list(snap.deferred), "last_target": snap.last_target,
            "strategy": strategy,
            "path_top": rnd.path_pred or "unknown",
            "referral": rnd.referral or "R0",
            "round1_outcome": self.outcome,
        }

    # ------------------------------------------------------------------ LLM calls

    async def _ask(self, task: str, messages: list[dict], state: dict, validate) -> dict:
        retries = self.deps.config["agent_llm"]["max_retries"]
        truncation_retried = False
        attempt, failures = 0, 0
        request_state = dict(state)
        while True:
            try:
                with record_call(self.trace["llm_calls"], task, task, attempt=attempt) as row:
                    row["phase"] = "request_and_parse"
                    result = await self.deps.llm.complete_json(messages, task=task, state=request_state)
                    row["output"] = result
                    row["phase"] = "validation"
                    validate(result)
                return result
            except asyncio.CancelledError:
                raise
            except TruncatedOutput:
                if truncation_retried:
                    break
                settings = self.deps.config["agent_llm"]
                limit = settings.get("max_tokens_by_task", {}).get(task, settings["max_tokens"])
                request_state["_max_tokens"] = limit * settings.get("truncation_retry_multiplier", 2)
                truncation_retried = True
            except Exception:
                if truncation_retried or failures >= retries:
                    break
                failures += 1
            attempt += 1
        # Frozen deterministic policy only sees the same public state as the agent.
        fallback_state = dict(state)
        if fallback_state["path_top"] == "unknown":
            fallback_state["path_top"] = "P1"  # generic plan only; never a classification
        result = await MockAgentLLM().complete_json(messages, task=task, state=fallback_state)
        if task in ("memory", "memory_plan"):
            memory = result["memory"] if task == "memory_plan" else result
            memory["summary"] = "摘要生成失败；后续以原始会谈记录为准。"
            memory["referral_reason"] = "固定规则回退"
            if memory["referral"] == "R0":
                memory["referral"] = next((r.referral for r in reversed(self.rounds) if r.referral), "R0")
            if task == "memory_plan":
                result.update(MockAgentLLM()._plan({**fallback_state, "referral": memory["referral"]}))
        validate(result)
        self.trace["fallbacks"].append({"round": state["round"], "task": task,
                                        "reason": "attempts_exhausted", "attempts": attempt + 1,
                                        "scope": CALL_SCOPE.get()})
        return result

    def _latency_summary(self) -> dict:
        samples: dict[str, list] = {}
        for call in self.trace["llm_calls"]:
            samples.setdefault(call["agent"], []).append(call["ms"])
        summary = {}
        for agent, values in samples.items():
            ordered = sorted(values)
            summary[agent] = {"n": len(values), "total": round(sum(values), 1),
                              "mean": round(sum(values) / len(values), 1),
                              "p95": ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]}
        return summary

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
            referral = rnd.referral
            # Contract cannot encode unknown; confidence=null and trace carry this distinction.
            # engine.reporting excludes these records, and all error sessions, from scored cohorts.
            path, confidence = rnd.path_pred or "P1", rnd.path_confidence
            rounds.append({"round": rnd.number, "transcript": list(rnd.transcript), "asked_topics": list(rnd.topics),
                           "path_pred": path, "path_confidence": confidence,
                           "referral_pred": referral or "R0", "crisis_level": rnd.level})
        final = self.plans.get(2)
        return {
            "schema_version": SCHEMA_VERSION,
            "session_id": f"{self.run_id}/{self.visitor['id']}",
            "run_id": self.run_id,
            "visitor_id": self.visitor["id"],
            "playbook_version": self.deps.playbook.version,
            "models": {"agent": self.deps.llm.model_name + (
                "(fallback:" + ",".join(sorted({f["task"] for f in self.trace["fallbacks"]
                                               if f["scope"] not in self._discarded_scopes})) + ")"
                if any(f["scope"] not in self._discarded_scopes for f in self.trace["fallbacks"]) else ""),
                       "visitor": self.deps.sim.model_name},
            "status": status,
            "error": error,
            "rounds": rounds,
            "plan": final["plan"] if status == "completed" and final else None,
            "behaviors": dict(self.behaviors),
            "safety_events": list(self.safety_events),
            "context_scales": self.visitor["prefilled"],
            "tool_calls": list(self.tool_calls),
        }


# ---------------------------------------------------------------------- validators

def _valid_strategy_obj(data: dict) -> None:
    strategy = data.get("strategy")
    if not isinstance(strategy, dict):
        raise LLMError("strategy object required")
    if strategy.get("type") not in STRATEGY_TYPES:
        raise LLMError(f"unknown strategy type {strategy.get('type')}")
    for key in ("target_topic", "revisit_later"):
        if strategy.get(key) not in (None, *TOPIC_PATTERNS):
            strategy[key] = None
    contrast = strategy.get("contrast") or []
    strategy["contrast"] = [p for p in contrast if p in PATHS] if isinstance(contrast, list) else []
    strategy.setdefault("intent", "")


def _valid_strategy(data: dict) -> None:
    action = data.get("action")
    if action == "tool":
        if data.get("tool") not in TOOLS:
            raise LLMError(f"unknown tool {data.get('tool')}")
    elif action not in ("say", "end_round"):
        raise LLMError(f"unknown action {action}")
    _valid_strategy_obj(data)


def _valid_response(data: dict) -> None:
    if not isinstance(data.get("text"), str) or not data["text"].strip():
        raise LLMError("response requires non-empty text")
    acts = data.get("acts") or []
    if not isinstance(acts, list):
        raise LLMError("acts must be a list")
    data["acts"] = [a for a in acts if a in BEHAVIORS]


def _valid_turn(data: dict) -> None:
    _valid_strategy(data)
    if data["action"] == "say":
        _valid_response(data)


def _valid_memory(data: dict) -> None:
    if data.get("referral") not in REFERRALS:
        raise LLMError("memory requires referral R0-R3")
    if not isinstance(data.get("summary"), str):
        raise LLMError("memory requires summary")
    for key in ("facts", "open_questions"):
        value = data.get(key) or []
        data[key] = [str(v) for v in value] if isinstance(value, list) else []
    data.setdefault("referral_reason", "")


def _valid_select(data: dict) -> None:
    if data.get("decision") not in ("maintain", "adjust"):
        raise LLMError("select decision must be maintain or adjust")
    data.setdefault("rationale", "")
    data.setdefault("focus", "")


def _valid_outcome(data: dict) -> None:
    weeks = data.get("isi_week")
    if not isinstance(weeks, list) or len(weeks) != 5 or any(
            isinstance(w, bool) or not isinstance(w, (int, float)) for w in weeks):
        raise EngineError("outcome model must return isi_week with 5 numbers")
    adherence = data.get("adherence")
    if isinstance(adherence, bool) or not isinstance(adherence, (int, float)) or not 0 <= adherence <= 1:
        raise EngineError("outcome model adherence must be within 0..1")
    if not isinstance(data.get("isi_change"), (int, float)) or not isinstance(data.get("responder"), bool):
        raise EngineError("outcome model must return isi_change and responder")


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


def _valid_memory_plan(data: dict) -> None:
    if not isinstance(data.get("memory"), dict):
        raise LLMError("memory_plan requires a memory object")
    _valid_memory(data["memory"])
    _valid_plan(data)


def _hhmm(value) -> None:
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        raise LLMError(f"time must be HH:MM, got {value!r}")
    hours, minutes = value[:2], value[3:]
    if not (hours.isdigit() and minutes.isdigit() and int(hours) < 24 and int(minutes) < 60):
        raise LLMError(f"time must be HH:MM, got {value!r}")


def _minus_minutes(hhmm: str, minutes: int) -> str:
    total = (int(hhmm[:2]) * 60 + int(hhmm[3:]) - minutes) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"
