"""Two-round consultation loop (TheraMind §3 dual loop, domain-specialised) -> contract `session`.

Loop 1, every agent action (four sub-agents, each with its own prompt and harness):
  PathClassifier (frozen)  -> {weights P1..P5, attitude, uncertainty}  on the accumulated dialogue
  strategy                 -> say | tool | end_round + strategy (playbook: questioning_strategy, path_discrimination)
  response                 -> text + acts                           (playbook: communication_style)
  (pipeline.merge_strategy_response = true runs strategy + response as one call)
  memory update            -> once per round: summary for round 2 + referral (playbook: referral_rules)
Round end: final classification -> path_pred (argmax) / path_confidence; plan (round 1 provisional, round 2 final;
  playbook: plan_rules, referral_rules) -> vetoes -> closing message -> visitor reply.
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
from dataclasses import dataclass, field
import json
import time

from domain.vetoes import check_plan, check_text
from safety.layer import SafetyLayer, SessionSafetyState
from safety.rules import LEVEL_RANK

from .classifier import PATHS, PathClassifier, PathState
from .interfaces import PlanOutcomeModel, ScreeningProvider, VisitorReply, VisitorSim
from .llm import AgentLLM, LLMError
from .playbook import Playbook
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
        self._cls_cache: tuple[int, PathState] | None = None
        self.trace = {"visitor_id": visitor["id"], "pipeline": self._pipeline_name(),
                      "classifier": getattr(deps.classifier, "provider", type(deps.classifier).__name__),
                      "llm_calls": [], "path_probs": [], "strategies": [], "history_checks": [], "vetoes": [],
                      "plans": {}, "memory": {}, "round1_outcome": None, "selection": None,
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
                continue
            prefetched = await self._agent_says(step, next_left=cap - actions)
        if prefetched is not None:
            prefetched.cancel()
        if not self.crisis:
            await self._flush_history_check()
        await self._close_round()

    async def _close_round(self) -> None:
        rnd = self.current
        rnd.path_state = await self._classify_current()
        self.trace["path_probs"].append({"round": rnd.number, "final": True, **rnd.path_state.to_dict()})
        memory = await self._ask("memory", self._messages("memory", self._snapshot(0)), self._state("memory"),
                                 _valid_memory)
        self.memory[rnd.number] = memory
        self.trace["memory"][str(rnd.number)] = memory
        rnd.referral = memory["referral"]
        if self.crisis:
            return
        await self._make_plan(rnd.number)
        self._add("agent", self.plans[rnd.number]["closing_message"])
        await self._visitor_speaks(speculate=False, record_topics=False)  # a statement, not a question
        if not self.crisis:
            await self._flush_history_check()

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
        """Classifier -> strategy -> response (or merged). Nothing is committed here (may be speculative)."""
        calls: list = []
        cls = await self._classify(snap.entries)
        if self.deps.config["pipeline"]["merge_strategy_response"]:
            result = await self._ask("turn", self._messages("turn", snap, cls), self._state("turn", snap, cls),
                                     _valid_turn, log=calls)
            strategy = result["strategy"]
        else:
            result = await self._ask("strategy", self._messages("strategy", snap, cls),
                                     self._state("strategy", snap, cls), _valid_strategy, log=calls)
            strategy = result["strategy"]
            if result["action"] == "say":
                response = await self._ask("response", self._messages("response", snap, cls, strategy=strategy),
                                           self._state("response", snap, cls, strategy=strategy), _valid_response,
                                           log=calls)
                result = {**result, **response}
        return {**result, "strategy": strategy, "classification": cls, "calls": calls, "snapshot": snap}

    def _commit_step(self, step: dict) -> None:
        snap, cls = step["snapshot"], step["classification"]
        last_turn = next((e["turn"] for e in reversed(snap.entries) if e["speaker"] == "visitor"
                          and e["round"] == snap.round), 0)
        self.trace["path_probs"].append({"round": snap.round, "turn": last_turn, "final": False, **cls.to_dict()})
        self.trace["llm_calls"].extend(step["calls"])
        strategy = step["strategy"]
        self.trace["strategies"].append({"round": snap.round, "action": step["action"], **strategy})
        if strategy.get("revisit_later") and strategy["revisit_later"] not in self.deferred:
            self.deferred.append(strategy["revisit_later"])
        if strategy.get("type") == "revisit" and strategy.get("target_topic") in self.deferred:
            self.deferred.remove(strategy["target_topic"])
        if strategy.get("target_topic"):
            self.last_target = strategy["target_topic"]

    async def _classify(self, entries) -> PathState:
        key = len(entries)
        if self._cls_cache and self._cls_cache[0] == key:
            return self._cls_cache[1]
        state = await self.deps.classifier.classify([dict(e) for e in entries])
        self._cls_cache = (key, state)
        return state

    async def _classify_current(self) -> PathState:
        state = await self._classify(tuple(self.entries))
        self.trace["llm_calls"].append({"agent": "classifier", "task": "classify", "ok": state.status == "ok",
                                        "status": state.status, "ms": state.latency_ms})
        return state

    async def _agent_says(self, step: dict, *, next_left: int):
        step = await self._vet_text(step)
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
        return await self._visitor_speaks(speculate=next_left > 0, next_left=next_left)

    async def _vet_text(self, step: dict) -> dict:
        """Forbidden wording in an agent message: rewrite (response or merged call) with feedback, then keep and log."""
        attempts = self.deps.config["veto_rewrite_attempts"]
        for attempt in range(attempts + 1):
            hard = [v for v in check_text(step["text"], config=self.deps.safety.config) if v.severity == "hard"]
            if not hard:
                return step
            self.trace["vetoes"].append({"stage": "turn", "round": self.current.number, "attempt": attempt,
                                         "violations": [v.__dict__ for v in hard]})
            if attempt == attempts:
                return step
            feedback = "；".join(dict.fromkeys(v.message for v in hard))
            snap, cls = step["snapshot"], step["classification"]
            task = "turn" if self.deps.config["pipeline"]["merge_strategy_response"] else "response"
            validate = _valid_turn if task == "turn" else _valid_response
            retry = await self._ask(task, self._messages(task, snap, cls, strategy=step["strategy"], feedback=feedback),
                                    self._state(task, snap, cls, strategy=step["strategy"]), validate)
            if task == "turn" and retry["action"] != "say":
                return step
            step = {**step, "text": retry["text"], "acts": retry.get("acts", [])}
        return step

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
        spec = asyncio.ensure_future(self._agent_step(self._snapshot(next_left))) if speculate else None
        assess = asyncio.ensure_future(self.deps.safety.assess_text(reply.text, self.current.number, self.turn,
                                                                    self.safety_state))
        try:
            event = await assess
        except BaseException:
            if spec:
                spec.cancel()
            raise
        if spec is not None and event is not None:
            self._discard(spec)
            spec = None
        await self._handle_event(event)
        if spec is not None and self.crisis:
            self._discard(spec)
            spec = None
        return spec

    def _discard(self, task: asyncio.Future) -> None:
        self.trace["speculation"]["discarded"] += 1
        if task.done() and not task.cancelled() and task.exception() is None:
            self.trace["speculation"]["discarded_calls"] += len(task.result()["calls"]) + 1
        task.cancel()

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
        if event.action == "crisis_protocol":
            self._add("safety", self.deps.safety.script_for("crisis_protocol"))
            self.crisis = True
        elif event.action == "safety_check":
            self._add("safety", self.deps.safety.script_for("safety_check"))
            await self._visitor_speaks(speculate=False)

    async def _run_tool(self, tool: str) -> None:
        result = self.deps.screening.screen(self.visitor, tool)
        self.turn += 1
        self.tool_calls.append({"round": self.current.number, "turn": self.turn, "tool": tool, "result": result})
        self.entries.append({"round": self.current.number, "turn": self.turn, "speaker": "tool", "tool": tool,
                             "result": result, "text": "", "revealed_clue_ids": []})
        if tool == "screen_mood":
            event = self.deps.safety.assess_phq9_item9(result["phq9_items"][8], self.current.number, self.turn,
                                                       self.safety_state)
            await self._handle_event(event)

    # ------------------------------------------------------------------ plan

    async def _make_plan(self, number: int) -> None:
        attempts = self.deps.config["veto_rewrite_attempts"]
        feedback, hard = None, []
        snap = self._snapshot(0)
        for attempt in range(attempts + 1):
            result = await self._ask("plan", self._messages("plan", snap, feedback=feedback), self._state("plan"),
                                     _valid_plan)
            plan, extras = self._plan_from(result)
            violations = self._plan_violations(plan, extras)
            hard = [v for v in violations if v.severity == "hard"]
            self.trace["vetoes"].append({"stage": "plan", "round": number, "attempt": attempt,
                                         "violations": [v.__dict__ for v in violations]})
            if not hard:
                break
            feedback = "；".join(dict.fromkeys(v.message for v in hard))
        if hard:
            plan = self._remediate(plan, hard)
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
        else:
            body = prompts[task]
        playbook = "\n\n".join(f"## {name}\n{self.deps.playbook.sections[name]}" for name in SECTIONS_FOR[task])
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
        if task == "memory":
            lines.append(f"本轮已问到的话题：{'、'.join(snap.asked) or '无'}")
        if task == "plan":
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
            "path_top": rnd.path_state.top if rnd.path_state else "P1",
            "referral": rnd.referral or "R0",
            "round1_outcome": self.outcome,
        }

    # ------------------------------------------------------------------ LLM calls

    async def _ask(self, task: str, messages: list[dict], state: dict, validate, *, log: list | None = None) -> dict:
        log = self.trace["llm_calls"] if log is None else log
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
                log.append({"agent": task, "task": task, "attempt": attempt, "ok": False,
                            "error": f"{type(exc).__name__}: {exc}",
                            "ms": round((time.perf_counter() - started) * 1000, 1)})
                continue
            log.append({"agent": task, "task": task, "attempt": attempt, "ok": True, "output": result,
                        "ms": round((time.perf_counter() - started) * 1000, 1)})
            return result
        raise EngineError(f"agent {task} failed after {retries + 1} attempts: {last}")

    def _latency_summary(self) -> dict:
        samples: dict[str, list] = {}
        for call in self.trace["llm_calls"]:
            samples.setdefault(call["agent"], []).append(call["ms"])
        for row in self.trace["path_probs"]:
            if not row["final"]:
                samples.setdefault("classifier", []).append(row["latency_ms"])
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
            state, referral = rnd.path_state, rnd.referral
            if state is None:
                # Only reachable on status=error (or the mid-session snapshot given to f_eval): placeholders keep
                # the record schema-valid (contract has no nullable path_pred); error sessions count as failures.
                path, confidence = "P1", None
            else:
                path, confidence = state.top, round(state.weights[state.top], 4)
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
            "models": {"agent": self.deps.llm.model_name, "visitor": self.deps.sim.model_name},
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


def _hhmm(value) -> None:
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        raise LLMError(f"time must be HH:MM, got {value!r}")
    hours, minutes = value[:2], value[3:]
    if not (hours.isdigit() and minutes.isdigit() and int(hours) < 24 and int(minutes) < 60):
        raise LLMError(f"time must be HH:MM, got {value!r}")


def _minus_minutes(hhmm: str, minutes: int) -> str:
    total = (int(hhmm[:2]) * 60 + int(hhmm[3:]) - minutes) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"
