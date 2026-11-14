"""Per-visitor safety state and contract-shaped events; engine owns crisis_exit."""
import asyncio
from dataclasses import asdict, dataclass, field, replace
import logging
import re
from time import perf_counter

import yaml

from .config import load_config
from .judges import Judge, JudgeResult, make_judge, validate_probs
from .rules import LEVEL_RANK, Rules


@dataclass
class SessionSafetyState:
    highest_level: str = "none"
    safety_check_inserted: bool = False
    safety_check_spoken: bool = False
    judge_failures: int = 0
    judge_results: list[JudgeResult] = field(default_factory=list)
    pending_history_check: bool = False
    history_check_issued: bool = False


@dataclass(frozen=True)
class SafetyEvent:
    round: int
    turn: int
    level: str
    source: str
    action: str
    judge_status: str
    judge_provider: str
    judge_probs: dict[str, float] | None
    matched: str

    def to_dict(self) -> dict:
        return asdict(self)


class SafetyLayer:
    def __init__(self, config=None, *, judge: Judge | None = None):
        self.config = load_config(config)
        self.rules = Rules(self.config["lexicon_path"])
        self.judge = judge if judge is not None else make_judge(self.config)
        with open(self.config["scripts_path"], encoding="utf-8") as stream:
            self.scripts = yaml.safe_load(stream)
        self.history_verify_patterns = {
            name: re.compile(pattern)
            for name, pattern in self.scripts["history_verify_patterns"].items()
        }

    @staticmethod
    def _check_position(round, turn):
        if type(round) is not int or round not in (1, 2) or type(turn) is not int or turn < 0:
            raise ValueError("round must be 1 or 2; turn must be a nonnegative integer")

    def _event(self, level, source, round, turn, state, *, result=None, matched=""):
        # Event.level records this assessment; highest_level is the monotonic session verdict.
        previous = state.highest_level
        state.highest_level = max((previous, level), key=LEVEL_RANK.__getitem__)
        action = "none"
        if level == "active":
            action = "crisis_protocol"
            state.pending_history_check = False
        elif level == "passive" and previous != "active" and not state.safety_check_inserted:
            action = "safety_check"
            state.safety_check_inserted = True
        return SafetyEvent(round, turn, level, source, action,
                           result.status if result else "skipped",
                           result.provider if result else "none",
                           result.probs if result and result.status == "ok" else None, matched)

    async def assess_text(self, text: str, round: int, turn: int, state: SessionSafetyState) -> SafetyEvent | None:
        self._check_position(round, turn)
        hit = self.rules.match(text)
        if hit.tier == "explicit":
            return self._event(hit.level, "rule_explicit", round, turn, state, matched=hit.matched)
        judge_text = text + (f"\n上下文提示：{hit.context_hint}" if hit.context_hint else "")
        start = perf_counter()
        provider = getattr(self.judge, "provider", type(self.judge).__name__)
        try:
            result = await asyncio.wait_for(self.judge.classify(judge_text), getattr(self.judge, "timeout", self.config["judge_timeout_s"]) + 0.1)
            provider = result.provider
            if result.status == "ok":
                validate_probs(result.probs, self.config["probability_sum_tolerance"])
            elif result.status not in ("timeout", "error"):
                raise ValueError("Unexpected judge status")
        except TimeoutError:
            result = JudgeResult(None, "timeout", provider, (perf_counter() - start) * 1000)
        except Exception:
            result = JudgeResult(None, "error", provider, (perf_counter() - start) * 1000)
        attempts = result.attempts or (result,)
        state.judge_results.extend(attempts)
        state.judge_failures += sum(attempt.status != "ok" for attempt in attempts)
        if result.status != "ok":
            logging.getLogger(__name__).warning(
                "安全警告：判断器 %s status=%s；模糊规则按 passive，无规则命中不升级。",
                result.provider, result.status,
            )
        level = "none"
        history = False
        if result.status == "ok":
            if result.probs["active"] >= self.config["tau_active"]:
                level = "active"
            elif result.probs["passive"] + result.probs["active"] >= self.config["tau_flag"]:
                level = "passive"
            elif result.probs["history"] == max(result.probs.values()):
                history = True
        if hit.tier == "ambiguous":
            if result.status != "ok":
                level = "passive"
            source = "rule_ambiguous+judge" if result.status == "ok" else "rule_ambiguous"
        else:
            source = "judge"
        if history:
            if state.highest_level == "active" or state.history_check_issued:
                return None
            state.history_check_issued = True
            state.pending_history_check = True
            return SafetyEvent(round, turn, "none", source, "history_check", result.status,
                               result.provider, result.probs, hit.matched)
        if level == "none":
            return None
        return self._event(level, source, round, turn, state, result=result, matched=hit.matched)

    def assess_phq9_item9(self, value: int, round: int, turn: int, state: SessionSafetyState) -> SafetyEvent | None:
        self._check_position(round, turn)
        if type(value) is not int or not 0 <= value <= 3:
            raise ValueError("PHQ-9 item 9 must be an integer from 0 to 3")
        if value <= self.config["phq9_item9_threshold"]:
            return None
        # Positive scale evidence must survive serialization even after a text check.
        level = "active" if state.highest_level == "active" else "passive"
        event = self._event(level, "scale_item9", round, turn, state, matched="PHQ-9 item 9 > 0")
        if level == "passive":
            event = replace(event, action="safety_check")
        return event

    def check_verification(self, agent_text: str) -> bool:
        """Check the next agent reply; the engine clears the per-session pending flag."""
        patterns = self.history_verify_patterns
        for sentence in re.findall(r"[^。！？!?；;\n]+[。！？!?；;\n]", agent_text):
            if not sentence.endswith(("？", "?")):
                continue
            has_time = False
            # Keep the question mark on its own clause; only time carries forward.
            for clause in re.split(r"[，,：:]", sentence):
                has_time = has_time or bool(patterns["time"].search(clause))
                if (has_time
                        and patterns["risk"].search(clause)
                        and patterns["question"].search(clause)
                        and not patterns["avoidance"].search(clause)):
                    return True
        return False

    def script_for(self, action: str) -> str:
        if action == "none":
            return ""
        if action not in ("history_check", "safety_check", "crisis_protocol"):
            raise ValueError(f"Unknown safety action: {action}")
        # 用户可见：每条一行"名称：号码"；verified 只供演示前复核，不展示给来访
        hotlines = "\n".join(
            f"{entry['name']}：{entry['number']}" for entry in self.scripts["hotlines"]
        )
        return self.scripts[action].replace("{hotlines}", hotlines)

    def script_for_event(self, event: SafetyEvent, state: SessionSafetyState) -> str:
        """Render once for safety_check; never remove an event from the audit trail."""
        if event.action == "safety_check":
            if state.safety_check_spoken:
                return ""
            state.safety_check_spoken = True
        return self.script_for(event.action)
