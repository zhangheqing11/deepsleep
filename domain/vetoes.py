"""Structured plan and playbook text vetoes; callers map field to change_id."""
from dataclasses import dataclass
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


def _settings(config):
    config = load_config(config)
    with open(config["veto_rules_path"], encoding="utf-8") as stream:
        rules = yaml.safe_load(stream)
    return config, rules


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
