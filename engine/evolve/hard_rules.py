"""Fixed hard rules for candidate playbook changes. Not evolvable.

Combines ``domain.vetoes.check_text`` (wording / medication advice, shared with the
session loop) with playbook-specific rules: crisis scope, TIB floor, contraindication
bypass, locked lines, and anti-gaming rules (``sim_exploit``: one message asking several topics,
which exploits keyword-driven clue reveal; plans that stack components regardless of evidence,
which exploits the outcome model). Soft warnings from ``domain.vetoes`` stay out of the contract.
"""
from __future__ import annotations

import re

import yaml

from domain.vetoes import Violation, check_text, to_hard_rule_violations
from safety.config import load_config as load_safety_config

from .playbook import Playbook

_CN_DIGITS = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_DURATION = re.compile(
    r"(\d+(?:\.\d+)?|[一二两三四五六七八九十]+)\s*(?:个)?\s*(半)?\s*(小时|钟头|h\b|hours?|分钟|min)"
)
_SENTENCE = re.compile(r"[^。；;！？!?\n]+")


def _cn_number(text: str) -> float:
    if text.replace(".", "", 1).isdigit():
        return float(text)
    if text == "十":
        return 10.0
    if "十" in text:
        tens, _, ones = text.partition("十")
        return float((_CN_DIGITS.get(tens, 1)) * 10 + _CN_DIGITS.get(ones, 0))
    return float(_CN_DIGITS.get(text, 0))


def durations_in_minutes(sentence: str) -> list[float]:
    out = []
    for number, half, unit in _DURATION.findall(sentence):
        value = _cn_number(number) + (0.5 if half else 0.0)
        out.append(value * 60 if unit in ("小时", "钟头", "h", "hour", "hours") else value)
    return out


EXPLOIT_MESSAGES = {
    "multi_topic_pattern": "规则要求一条消息同时问多个话题或合并提问，会利用模拟来访按关键词一次揭示多条线索的漏洞；属于固定否决规则。",
    "plan_shotgun_pattern": "规则要求处方不看证据地堆叠组件（全部组件、每条路径各一个或无条件加入），会利用结局模型对组件覆盖的奖励；属于固定否决规则。",
}


def _exploit_hit(text: str, pattern: str, negation: str | None) -> bool:
    """True if ``pattern`` matches a sentence and the clause before the match is not negated
    (so "不要连续追问多个问题" / "避免一次问多个话题" stay legal)."""
    for sentence in _SENTENCE.findall(text):
        for match in re.finditer(pattern, sentence, re.IGNORECASE):
            clause = re.split(r"[，,：:]", sentence[:match.start()])[-1]
            if negation and re.search(negation, clause):
                continue
            return True
    return False


def exploit_violations(text: str, rules: dict) -> list[Violation]:
    """Fixed anti-gaming rules: candidate text that instructs simulator exploits (code ``sim_exploit``)."""
    out = []
    negation = rules.get("exploit_negation_pattern")
    for key, message in EXPLOIT_MESSAGES.items():
        pattern = rules.get(key)
        if pattern and _exploit_hit(text, pattern, negation):
            out.append(Violation("sim_exploit", message, "text"))
    return out


def _safety_settings():
    config = load_safety_config()
    with open(config["veto_rules_path"], encoding="utf-8") as stream:
        rules = yaml.safe_load(stream)
    return config, rules


def check_change(change: dict, playbook: Playbook, config: dict) -> list[Violation]:
    rules = config["hard_rules"]
    safety_config, veto_rules = _safety_settings()
    violations: list[Violation] = []
    after = change.get("after") or ""
    before = change.get("before") or ""

    if after:
        violations.extend(check_text(after))
    for text in filter(None, (after, before if change["op"] != "add" else "")):
        if re.search(rules["crisis_scope_pattern"], text):
            violations.append(Violation("crisis_scope", "危机识别由固定安全层处理，不在 playbook 内，任何章节都不能改动相关内容。", "text"))
            break
    if after and re.search(rules["contraindication_bypass_pattern"], after):
        violations.append(Violation("contraindication_violation", veto_rules["plan_messages"]["unchecked"], "text"))
    if after:
        floor = safety_config["min_tib_minutes"]
        for sentence in _SENTENCE.findall(after):
            if not re.search(rules["tib_context_pattern"], sentence, re.IGNORECASE):
                continue
            if any(rules["tib_min_plausible_minutes"] <= minutes < floor for minutes in durations_in_minutes(sentence)):
                violations.append(Violation("contraindication_violation", veto_rules["plan_messages"]["min_tib"], "text"))
                break
    if after:
        violations.extend(exploit_violations(after, rules))
    if change["op"] in ("modify", "delete") and before:
        index = playbook.find_line(change["section"], before)
        if index is not None and rules["locked_marker"] in playbook.sections[change["section"]].lines[index]:
            violations.append(Violation("locked_rule", "该条为锁定规则，agent 不能修改或删除。", "text"))
    return violations


def check_candidate(changes: list[dict], playbook_text: str, config: dict) -> list[dict]:
    """Contract ``hard_rule_violations`` for one candidate (hard severity only)."""
    playbook = Playbook.parse(playbook_text)
    out: list[dict] = []
    for change in changes:
        out.extend(to_hard_rule_violations(check_change(change, playbook, config), change["id"]))
    return out


def veto_from_violations(violations: list[dict], config: dict) -> dict:
    code_map = config["hard_rules"]["veto_code_map"]
    reasons, seen = [], set()
    for violation in violations:
        code = code_map.get(violation["code"], "contraindication_violation")
        key = (code, violation["message"])
        if key not in seen:
            seen.add(key)
            reasons.append({"code": code, "message": violation["message"]})
    return {"passed": not reasons, "reasons": reasons}
