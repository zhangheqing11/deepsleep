"""Per-visitor safety state and contract-shaped events; engine owns crisis_exit."""
import asyncio
from dataclasses import asdict, dataclass, field
from time import perf_counter

import yaml

from .config import load_config
from .judges import Judge, JudgeResult, make_judge, validate_probs
from .rules import LEVEL_RANK, Rules


@dataclass
class SessionSafetyState:
    highest_level: str = "none"
    safety_check_inserted: bool = False
    judge_failures: int = 0
    judge_results: list[JudgeResult] = field(default_factory=list)


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
        elif previous != "active" and not state.safety_check_inserted:
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
        start = perf_counter()
        provider = getattr(self.judge, "provider", type(self.judge).__name__)
        try:
            result = await asyncio.wait_for(self.judge.classify(text), self.config["judge_timeout_s"])
            provider = result.provider
            if result.status == "ok":
                validate_probs(result.probs, self.config["probability_sum_tolerance"])
            elif result.status not in ("timeout", "error"):
                raise ValueError("Unexpected judge status")
        except TimeoutError:
            result = JudgeResult(None, "timeout", provider, (perf_counter() - start) * 1000)
        except Exception:
            result = JudgeResult(None, "error", provider, (perf_counter() - start) * 1000)
        state.judge_results.append(result)
        if result.status != "ok":
            state.judge_failures += 1
        level = "none"
        if result.status == "ok":
            if result.probs["active"] >= self.config["tau_active"]:
                level = "active"
            elif result.probs["passive"] + result.probs["active"] >= self.config["tau_flag"]:
                level = "passive"
        if hit.tier == "ambiguous":
            level = max((level, "passive"), key=LEVEL_RANK.__getitem__)
            source = "rule_ambiguous+judge" if result.status == "ok" else "rule_ambiguous"
        else:
            source = "judge"
        if level == "none":
            return None
        return self._event(level, source, round, turn, state, result=result, matched=hit.matched)

    def assess_phq9_item9(self, value: int, round: int, turn: int, state: SessionSafetyState) -> SafetyEvent | None:
        self._check_position(round, turn)
        if type(value) is not int or not 0 <= value <= 3:
            raise ValueError("PHQ-9 item 9 must be an integer from 0 to 3")
        if value <= self.config["phq9_item9_threshold"]:
            return None
        return self._event("passive", "scale_item9", round, turn, state, matched="PHQ-9 item 9 > 0")

    def script_for(self, action: str) -> str:
        if action == "none":
            return ""
        if action not in ("safety_check", "crisis_protocol"):
            raise ValueError(f"Unknown safety action: {action}")
        hotlines = "；".join(
            f"{entry['name']}：{entry['number']}（{entry['hours']}；{'已核验' if entry['verified'] else '未核验，占位'}）"
            for entry in self.scripts["hotlines"]
        )
        return self.scripts[action].replace("{hotlines}", hotlines)
