"""Reflector: failures + feedback → exactly 3 normalized incremental candidates.

Primary model Opus 5.5; on timeout, API error, refusal or unusable output it falls
back to ds flash automatically (decision #8) and records why. C1 (auto_critic) will
feed approved annotations through ``human_feedback``; nothing else changes here.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
from pathlib import Path
import re

from .config import SECTIONS, SECTION_CRITICALITY, max_criticality, resolve
from .llm import LLMClient

_OPS = ("add", "modify", "delete")
_LEVELS = ("low", "medium", "high")
EMPTY_SUMMARY = "反思器未产出有效候选（占位，不参与验证）。"


@dataclass
class ReflectionResult:
    candidates: list[dict]      # contract-shaped (minus gate fields): id, summary, changes
    model: str
    fell_back: bool
    fallback_reason: str | None
    failures_used: list[dict]
    dropped_changes: list[str]  # internal log, not part of the contract


# -- inputs -----------------------------------------------------------------------------
def select_failures(run_report: dict, config: dict) -> list[dict]:
    rc = config["reflector"]
    priority = {tag: i for i, tag in enumerate(rc["failure_tag_priority"])}
    excluded = set(rc["excluded_failure_tags"])
    rows = []
    for row in run_report["per_visitor"]:
        tags = [t for t in row["failure_tags"] if t not in excluded]
        if tags:
            rank = min(priority.get(t, len(priority)) for t in tags)
            rows.append((rank, -len(tags), row["visitor_id"], row))
    rows.sort(key=lambda r: r[:3])
    return [r[3] for r in rows[: rc["max_failures"]]]


def load_sessions(run_report: dict, base_dir: str | Path) -> dict[str, dict]:
    base = Path(base_dir)
    out = {}
    for row in run_report["per_visitor"]:
        ref = row.get("session_ref")
        if ref and (base / ref).exists():
            out[row["visitor_id"]] = json.loads((base / ref).read_text(encoding="utf-8"))
    return out


def usable_feedback(feedback: list[dict]) -> list[dict]:
    """Contract: human entries are always approved; auto_critic only when approved/edited."""
    return [f for f in feedback if f["source"] == "human" or f["status"] in ("approved", "edited")]


def _transcript(session: dict, limit: int) -> str:
    parts = []
    for rnd in session.get("rounds", []):
        parts.append(f"[第 {rnd['round']} 轮] 判路径 {rnd.get('path_pred')} · 转介 {rnd.get('referral_pred')} · "
                     f"问到话题 {', '.join(rnd.get('asked_topics', [])) or '无'}")
        for turn in rnd.get("transcript", []):
            parts.append(f"{turn['speaker']}: {turn['text']}")
    text = "\n".join(parts)
    return text if len(text) <= limit else text[:limit] + "\n…（截断）"


def _failure_block(row: dict, session: dict | None, limit: int) -> str:
    lines = [
        f"## 案例 {row['visitor_id']}",
        f"- 失败标签：{', '.join(row['failure_tags'])}",
        f"- 真实主路径 {row['main_path']}；第 1 轮判 {row['path_pred_r1']}，第 2 轮判 {row['path_pred_r2']}",
        f"- 真实转介 {row['referral_true']}；判 {row['referral_pred']}",
        f"- 自评量表 {', '.join(row['prefilled_scales']) or '无'}；agent 调用筛查 {', '.join(row['screened']) or '无'}",
        f"- ISI {row['isi_baseline']} → 第 4 周 {row['isi_week'][-1]}（变化 {row['isi_change']}）；依从 {row['adherence']:.2f}；同盟 {row['alliance']:.2f}",
    ]
    if session:
        plan = session.get("plan") or {}
        if plan:
            lines.append(f"- 处方组件：{', '.join(plan.get('components', []))}；卧床 {plan.get('tib_minutes')} 分钟")
        lines.append("```\n" + _transcript(session, limit) + "\n```")
    return "\n".join(lines)


def _read_prompt(path: str) -> str:
    return resolve(path).read_text(encoding="utf-8")


def _fewshot(config: dict) -> str:
    text = re.sub(r"<!--.*?-->", "", _read_prompt(config["reflector"]["prompts"]["fewshot"]), flags=re.S).strip()
    return text or "（暂无）"


def _fill(template: str, values: dict) -> str:
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", str(value))
    return template


def build_prompts(*, playbook_text: str, version: str, run_report: dict, failures: list[dict],
                  sessions: dict, feedback: list[dict], config: dict) -> tuple[str, str]:
    rc = config["reflector"]
    system = _fill(_read_prompt(rc["prompts"]["system"]),
                   {"max_changes": rc["max_changes_per_candidate"], "max_chars": rc["max_change_chars"]})
    feedback_lines = [f"- [{f['kind']}{' · ' + f['visitor_id'] if f['visitor_id'] else ''}] "
                      f"{f['text'] if f['text'] is not None else ''}{' 评分 ' + str(f['score']) if f['score'] is not None else ''}"
                      for f in usable_feedback(feedback)]
    user = _fill(_read_prompt(rc["prompts"]["user"]), {
        "version": version,
        "playbook": playbook_text.strip(),
        "run_label": run_report.get("label", run_report["run_id"]),
        "n_visitors": run_report["n_visitors"],
        "metrics": json.dumps(run_report["metrics"], ensure_ascii=False, indent=1),
        "n_failures": len(failures),
        "failures": "\n\n".join(_failure_block(r, sessions.get(r["visitor_id"]), rc["max_transcript_chars"])
                                for r in failures) or "（无）",
        "feedback": "\n".join(feedback_lines) or "（无）",
        "fewshot": _fewshot(config),
    })
    return system, user


# -- output parsing -------------------------------------------------------------------------
def extract_json(text: str) -> dict:
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("输出中没有 JSON 对象")
    return json.loads(text[start:end + 1])


def _clean_str(value) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def normalize_change(raw: dict, config: dict) -> dict | None:
    rc = config["reflector"]
    if not isinstance(raw, dict):
        return None
    op, section = raw.get("op"), raw.get("section")
    if op not in _OPS or section not in SECTIONS:
        return None
    before, after = _clean_str(raw.get("before")), _clean_str(raw.get("after"))
    if op == "add":
        before = None
    if op == "delete":
        after = None
    if (op in ("add", "modify") and not after) or (op in ("modify", "delete") and not before):
        return None
    if after and len(after) > rc["max_change_chars"]:
        return None
    self_level = raw.get("criticality_self") if raw.get("criticality_self") in _LEVELS else "high"
    rule_level = SECTION_CRITICALITY[section]
    return {"op": op, "section": section, "before": before, "after": after,
            "reason": _clean_str(raw.get("reason")) or "（反思器未给出理由）",
            "criticality_rule": rule_level, "criticality_self": self_level,
            "criticality": max_criticality(rule_level, self_level)}


def normalize(data: dict, config: dict, dropped: list[str]) -> list[dict]:
    """Up to 3 candidates with ≥1 valid change; ids/change ids assigned by position."""
    rc = config["reflector"]
    raw_candidates = data.get("candidates") if isinstance(data, dict) else None
    if not isinstance(raw_candidates, list):
        raise ValueError("JSON 缺少 candidates 列表")
    out = []
    for raw in raw_candidates:
        if len(out) == 3:
            break
        if not isinstance(raw, dict) or not isinstance(raw.get("changes"), list):
            continue
        changes = []
        for index, raw_change in enumerate(raw["changes"]):
            change = normalize_change(raw_change, config)
            if change is None:
                dropped.append(f"候选{len(out) + 1} 第{index + 1}条改动格式无效，已丢弃")
            elif len(changes) >= rc["max_changes_per_candidate"]:
                dropped.append(f"候选{len(out) + 1} 超出每份 {rc['max_changes_per_candidate']} 条上限，已丢弃")
            else:
                changes.append(change)
        if changes:
            out.append({"summary": _clean_str(raw.get("summary")) or "（反思器未给出概述）", "changes": changes})
    return out


def finalize(candidates: list[dict]) -> list[dict]:
    """Pad to exactly 3 and assign contract ids c1..c3, change ids c1-<section>-n."""
    candidates = list(candidates) + [{"summary": EMPTY_SUMMARY, "changes": []}
                                     for _ in range(3 - len(candidates))]
    out = []
    for i, cand in enumerate(candidates, start=1):
        cid = f"c{i}"
        changes = [{"id": f"{cid}-{ch['section']}-{n}", **ch} for n, ch in enumerate(cand["changes"], start=1)]
        out.append({"id": cid, "summary": cand["summary"], "changes": changes})
    return out


# -- orchestration ------------------------------------------------------------------------------
async def _attempt(client: LLMClient, system: str, user: str, timeout_s: float, config: dict,
                   dropped: list[str]) -> list[dict]:
    text = await asyncio.wait_for(client.complete(system, user), timeout=timeout_s)
    candidates = normalize(extract_json(text), config, dropped)
    if not candidates:
        raise ValueError("没有任何格式有效的候选")
    return candidates


def _reason(exc: BaseException) -> str:
    if isinstance(exc, asyncio.TimeoutError):
        return "超时"
    return f"{type(exc).__name__}: {exc}"[:300]


async def reflect(*, playbook_text: str, version: str, run_report: dict, sessions: dict,
                  feedback: list[dict], config: dict, primary: LLMClient | None,
                  fallback: LLMClient | None, primary_error: str | None = None) -> ReflectionResult:
    rc = config["reflector"]
    failures = select_failures(run_report, config)
    system, user = build_prompts(playbook_text=playbook_text, version=version, run_report=run_report,
                                 failures=failures, sessions=sessions, feedback=feedback, config=config)
    failures_used = [{"visitor_id": r["visitor_id"], "failure_tags": r["failure_tags"]} for r in failures]
    dropped: list[str] = []
    reason = primary_error
    if primary is not None:
        try:
            cands = await _attempt(primary, system, user, rc["primary_timeout_s"], config, dropped)
            return ReflectionResult(finalize(cands), primary.model, False, None, failures_used, dropped)
        except Exception as exc:  # noqa: BLE001 - any failure → automatic fallback
            reason = f"主反思器失败（{_reason(exc)}）"
    elif reason is None:
        reason = "未配置主反思器"
    model = rc["primary_model"]
    if fallback is not None:
        model = fallback.model
        try:
            cands = await _attempt(fallback, system, user, rc["fallback_timeout_s"], config, dropped)
            return ReflectionResult(finalize(cands), fallback.model, True, reason, failures_used, dropped)
        except Exception as exc:  # noqa: BLE001
            reason = f"{reason}；降级模型也失败（{_reason(exc)}）"
    else:
        reason = f"{reason}；未配置降级模型"
    return ReflectionResult(finalize([]), model, True, reason, failures_used, dropped)
