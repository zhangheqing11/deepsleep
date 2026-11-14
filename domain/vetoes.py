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


_TRADITIONAL = str.maketrans({
    "診": "诊", "斷": "断", "療": "疗", "為": "为", "醫": "医", "確": "确", "誤": "误",
    "憂": "忧", "鬱": "郁", "礙": "碍", "慮": "虑", "屬": "属", "於": "于", "雙": "双",
    "寧": "宁", "癒": "愈", "藥": "药", "開": "开", "處": "处", "給": "给", "徹": "彻",
    "對": "对", "來": "来", "訪": "访", "說": "说", "請": "请", "議": "议", "應": "应",
    "該": "该", "劑": "剂", "調": "调", "減": "减", "換": "换", "詞": "词", "語": "语",
})

# Only a scoped prohibition list in candidate instructions is exempt. A comma,
# sentence break, newline or change of direction ends the list. Medication
# advice retains its separate existing negation checks.
_PROHIBITION = re.compile(
    r"(?:^|(?<=[，,。.!！？?；;\n]))[^\S\n]*(?:[-*][^\S\n]*)?"
    r"(?:不要|禁止|不得|不可|不能|请勿|切勿)(?:对来访|向来访|给来访)?"
    r"(?:说|使用|输出|出现|包含|写|提及)(?:以下)?(?:措辞|词语|字样|词汇)?[：:]?"
    r"(?:(?!但|然而|而要|却|可以|应该|建议)[^，,。.!！？?；;\n])*"
)


def check_text(text: str, *, context: Literal["user_facing", "candidate_playbook"] = "user_facing",
               config=None) -> list[Violation]:
    if context not in ("user_facing", "candidate_playbook"):
        raise ValueError("context must be user_facing or candidate_playbook")
    _, rules = _settings(config)
    normalized = unicodedata.normalize("NFKC", text).translate(_TRADITIONAL)
    # Keep line boundaries for prohibition scope before removing whitespace.
    scoped = re.sub(r"[^\S\n]+", "", normalized)
    candidate = _PROHIBITION.sub("", scoped) if context == "candidate_playbook" else scoped
    violations = []
    for rule in rules["text_rules"]:
        wording = rule["id"].startswith("W")
        checked = candidate if wording else scoped
        # English word boundaries and spaces carry meaning in W8.
        if rule["id"] == "W8":
            checked = _PROHIBITION.sub("", normalized) if context == "candidate_playbook" else normalized
        else:
            checked = re.sub(r"\s+", "", checked)
        for match in re.finditer(rule["pattern"], checked):
            negation = rule.get("negated_prefix_pattern")
            if negation and re.search(negation, checked[:match.start()]):
                continue
            violations.append(Violation(rule["code"], rule["message"], rule["field"], rule.get("severity", "hard")))
            break
    return violations


def to_hard_rule_violations(violations: list[Violation], change_id: str) -> list[dict]:
    """Serialize candidate vetoes; keep soft warnings local and out of the contract."""
    return [{"code": violation.code, "change_id": change_id, "message": violation.message}
            for violation in violations if violation.severity == "hard"]
