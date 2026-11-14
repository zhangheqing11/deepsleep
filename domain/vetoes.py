"""Structured plan and playbook text vetoes; callers map field to change_id."""
from dataclasses import dataclass
from functools import lru_cache
import os
import re
import unicodedata
from typing import Literal

import yaml

from safety.config import load_config


@dataclass(frozen=True)
class Violation:
    code: str
    message: str
    field: str
    severity: Literal["hard", "soft"] = "hard"

    def __post_init__(self):
        if self.severity not in ("hard", "soft"):
            raise ValueError("severity must be hard or soft")


@lru_cache(maxsize=8)
def _read_rules(path: str, mtime_ns: int) -> dict:
    # Keyed by mtime so an edited rules file is re-read; avoids re-parsing YAML on every call.
    with open(path, encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def _settings(config):
    # A config already produced by load_config (absolute paths) round-trips unchanged; skip re-reading YAML.
    resolved = isinstance(config, dict) and os.path.isabs(str(config.get("veto_rules_path", "")))
    config = config if resolved else load_config(config)
    path = config["veto_rules_path"]
    return config, _read_rules(path, os.stat(path).st_mtime_ns)


def check_plan(plan, contraindications, *, age=None, crisis_level="none", config=None) -> list[Violation]:
    if plan is None:
        return []
    config, rules = _settings(config)
    violations = []
    if "sleep_restriction" in plan["components"]:
        if set(contraindications) & set(rules["contraindications"]):
            violations.append(Violation("contraindication_violation", rules["plan_messages"]["contraindication"], "components"))
        if plan.get("contraindications_checked") is not True:
            violations.append(Violation("contraindication_violation", rules["plan_messages"]["unchecked"], "contraindications_checked"))
        if age is not None and age < rules["min_age"]:
            violations.append(Violation("contraindication_violation", rules["plan_messages"]["age"], "age"))
        if crisis_level == "passive":
            violations.append(Violation("contraindication_violation", rules["plan_messages"]["passive"], "components", "soft"))
    if plan["tib_minutes"] < config["min_tib_minutes"]:
        violations.append(Violation("contraindication_violation", rules["plan_messages"]["min_tib"], "tib_minutes"))
    return violations


# Only characters used by the fixed wording/medication rules; not a general converter.
_TRADITIONAL = str.maketrans({
    "診": "诊", "斷": "断", "療": "疗", "確": "确", "誤": "误", "為": "为",
    "醫": "医", "慮": "虑", "礙": "碍", "鬱": "郁", "暫": "暂", "寧": "宁",
    "雙": "双", "這": "这", "屬": "属", "於": "于", "藥": "药", "徹": "彻",
    "開": "开", "處": "处", "給": "给", "應": "应", "該": "该", "議": "议",
    "試": "试", "請": "请", "減": "减", "調": "调", "劑": "剂", "換": "换",
})
_PROHIBITION = re.compile(r"(?:不要|禁止|避免|不得|切勿).{0,12}(?:诊断|确诊|误诊|治疗失眠症|治疗失眠)")


def _without_prohibitions(text):
    # Keep sentence/line boundaries before whitespace removal. A prohibition never
    # exempts another clause or medication advice. Contrast starts a new clause.
    parts = re.split(r"([,，。!！?？;；\n]|但是|然而|不过|但|而是)", text)
    return "".join("" if _PROHIBITION.search(re.sub(r"\s+", "", part)) else part for part in parts)


def check_text(text: str, *, config=None, context="user_facing") -> list[Violation]:
    if context not in ("user_facing", "candidate_playbook"):
        raise ValueError("context must be user_facing or candidate_playbook")
    _, rules = _settings(config)
    normalized = unicodedata.normalize("NFKC", text).translate(_TRADITIONAL)
    violations = []
    for rule in rules["text_rules"]:
        wording = normalized
        if context == "candidate_playbook" and rule["id"].startswith("W"):
            wording = _without_prohibitions(wording)
        # Retain the spaced view too, preserving English word boundaries and W8.
        views = (wording, re.sub(r"\s+", "", wording))
        found = False
        for view in views:
            for match in re.finditer(rule["pattern"], view):
                negation = rule.get("negated_prefix_pattern")
                if negation and re.search(negation, view[:match.start()]):
                    continue
                found = True
                break
            if found:
                break
        if found:
            violations.append(Violation(rule["code"], rule["message"], rule["field"], rule.get("severity", "hard")))
    return violations


def to_hard_rule_violations(violations: list[Violation], change_id: str) -> list[dict]:
    """Serialize candidate vetoes; keep soft warnings local and out of the contract."""
    return [{"code": violation.code, "change_id": change_id, "message": violation.message}
            for violation in violations if violation.severity == "hard"]
