"""Structured plan and playbook text vetoes; callers map field to change_id."""
from dataclasses import dataclass
from functools import lru_cache
import os
import re
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


def check_text(text: str, *, config=None) -> list[Violation]:
    _, rules = _settings(config)
    violations = []
    for rule in rules["text_rules"]:
        for match in re.finditer(rule["pattern"], text):
            negation = rule.get("negated_prefix_pattern")
            if negation and re.search(negation, text[:match.start()]):
                continue
            violations.append(Violation(rule["code"], rule["message"], rule["field"], rule.get("severity", "hard")))
            break
    return violations


def to_hard_rule_violations(violations: list[Violation], change_id: str) -> list[dict]:
    """Serialize candidate vetoes; keep soft warnings local and out of the contract."""
    return [{"code": violation.code, "change_id": change_id, "message": violation.message}
            for violation in violations if violation.severity == "hard"]
