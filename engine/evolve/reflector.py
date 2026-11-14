"""Reflector: failures + feedback → exactly 3 normalized incremental candidates.

Primary provider OpenAI (optionally Anthropic); on timeout, API error, refusal or unusable output it falls
back to ds flash automatically (decision #8) and records why. C1 (auto_critic) will
feed approved annotations through ``human_feedback``; nothing else changes here.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import time

from . import audit as au
from . import dimensions as dims
from . import evidence as ev
from .config import SECTIONS, SECTION_CRITICALITY, max_criticality, resolve
from .llm import LLMClient, error_reason

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
    failure_dimensions: dict    # visitor_id → dimensions (ring-3 insight, not in the contract)
    scorecard: dict
    evidence: dict
    provider: str | None = None
    reasoning_effort: str | None = None
    attempts: list[dict] = field(default_factory=list)
    audit: dict = field(default_factory=dict)   # run audit tables shown to the reflector (traceable ids)


# -- inputs -----------------------------------------------------------------------------
def select_failures(run_report: dict, config: dict, visitors: dict | None = None) -> list[dict]:
    """Failure rows, round-robin across editable dimensions; within one, by tag priority."""
    rc = config["reflector"]
    visitors = visitors or {}
    priority = {tag: i for i, tag in enumerate(rc["failure_tag_priority"])}
    excluded = set(rc["excluded_failure_tags"])
    queues: dict[str, list] = {d: [] for d in config["dimensions"]["order"]}
    for row in run_report["per_visitor"]:
        tags = [t for t in row["failure_tags"] if t not in excluded]
        if not tags:
            continue
        rank = (min(priority.get(t, len(priority)) for t in tags), -len(tags), row["visitor_id"])
        for d in dims.classify(row, visitors.get(row["visitor_id"]), config):
            if d in queues:
                queues[d].append((rank, row))
    for queue in queues.values():
        queue.sort(key=lambda item: item[0])
    picked, seen = [], set()
    while len(picked) < rc["max_failures"] and any(queues.values()):
        for queue in queues.values():
            while queue and queue[0][1]["visitor_id"] in seen:
                queue.pop(0)
            if queue and len(picked) < rc["max_failures"]:
                row = queue.pop(0)[1]
                seen.add(row["visitor_id"])
                picked.append(row)
    return picked


def select_failures_by_audit(run_report: dict, audit: dict, config: dict,
                             visitors: dict | None = None) -> list[dict]:
    """Round-robin over the audit's loss groups, largest first, so each big loss has a case.

    Within a group: non-responders first, then failure-tag priority, then id. Rows whose only
    tags are excluded (crisis) are never picked; groups come from ``audit['loss_groups']``.
    """
    rc = config["reflector"]
    groups = audit.get("loss_groups") or {}
    if not groups:
        return select_failures(run_report, config, visitors)
    rows = {r["visitor_id"]: r for r in run_report["per_visitor"]}
    priority = {tag: i for i, tag in enumerate(rc["failure_tag_priority"])}
    excluded = set(rc["excluded_failure_tags"])

    def tags(row):
        return [t for t in row["failure_tags"] if t not in excluded]

    def rank(row):
        return (bool(row["responder"]), min((priority.get(t, len(priority)) for t in tags(row)), default=len(priority)),
                row["visitor_id"])

    queues = [sorted((rows[v] for v in ids if v in rows and tags(rows[v])), key=rank) for ids in groups.values()]
    picked, seen = [], set()
    while len(picked) < rc["max_failures"] and any(queues):
        for queue in queues:
            while queue and queue[0]["visitor_id"] in seen:
                queue.pop(0)
            if queue and len(picked) < rc["max_failures"]:
                row = queue.pop(0)
                seen.add(row["visitor_id"])
                picked.append(row)
    return picked


def load_traces(run_report: dict, base_dir: str | Path) -> dict[str, dict]:
    """S3 layout: <out>/sessions/<id>.json next to <out>/trace/<id>.json (debug, not a contract)."""
    base = Path(base_dir)
    out = {}
    for row in run_report["per_visitor"]:
        vid = row["visitor_id"]
        ref = Path(row.get("session_ref") or f"sessions/{vid}.json")
        for candidate in (base / ref.parent.parent / "trace" / f"{vid}.json", base / "trace" / f"{vid}.json"):
            if candidate.exists():
                out[vid] = json.loads(candidate.read_text(encoding="utf-8"))
                break
    return out


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


def _failure_block(row: dict, session: dict | None, limit: int, row_dims: list[str] | None = None,
                   evidence_line: str | None = None) -> str:
    lines = [
        f"## 案例 {row['visitor_id']}",
        f"- 失败维度：{'、'.join(dims.DIMENSION_LABELS[d] for d in row_dims or []) or '未归类'}",
        f"- 失败标签：{', '.join(row['failure_tags'])}",
        f"- 真实主路径 {row['main_path']}；第 1 轮判 {row['path_pred_r1']}，第 2 轮判 {row['path_pred_r2']}",
        f"- 真实转介 {row['referral_true']}；判 {row['referral_pred']}",
        f"- 自评量表 {', '.join(row['prefilled_scales']) or '无'}；agent 调用筛查 {', '.join(row['screened']) or '无'}",
        f"- ISI {row['isi_baseline']} → 第 4 周 {row['isi_week'][-1]}（变化 {row['isi_change']}）；依从 {row['adherence']:.2f}；同盟 {row['alliance']:.2f}",
    ]
    if evidence_line:
        lines.append(f"- 分类器证据：{evidence_line}")
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


def _scorecard_text(card: dict) -> str:
    lines = []
    for d in dims.DIMENSIONS:
        lines.append(f"- {dims.DIMENSION_LABELS[d]}：{json.dumps(card[d], ensure_ascii=False)}")
    lines.append("- 各维度失败案例数：" + "，".join(
        f"{dims.DIMENSION_LABELS[d]} {n}" for d, n in card["failures_by_dimension"].items()))
    return "\n".join(lines)


_OUTCOME_LABELS = {"adopted": "已采纳", "rejected": "门禁拒绝", "blocked": "固定规则拦截", "empty": "空候选"}


def _fmt(value) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}" if isinstance(value, float) else str(value)


def history_text(history: list[dict] | None, limit: int = 3000, change_chars: int = 80) -> str:
    """Earlier generations' candidates and their gate outcomes, newest last, oldest dropped first."""
    if not history:
        return "（无：这是第一代反思）"
    blocks = []
    for gen in history:
        lines = [f"第 {gen.get('generation', '?')} 代：{gen.get('from_version', '?')} → "
                 f"{gen.get('to_version') or '未产生新版本'}"]
        for cand in gen.get("candidates") or []:
            d = cand.get("delta") or {}
            stats = (f"验证 n={_fmt(d.get('n'))} 有效 {_fmt(d.get('isi_responders'))}"
                     f"（新增 {_fmt(d.get('gained'))} / 丢失 {_fmt(d.get('lost'))}）"
                     f" 转介召回 {_fmt(d.get('referral_recall'))} 精确 {_fmt(d.get('referral_precision'))}"
                     f" 路径r2 {_fmt(d.get('path_acc_r2'))} 筛查覆盖 {_fmt(d.get('screening_coverage'))}")
            reasons = "；".join(str(r) for r in cand.get("reasons") or []) or "无"
            lines.append(f"- {cand.get('id', '?')} [{_OUTCOME_LABELS.get(cand.get('outcome'), cand.get('outcome'))}] "
                         f"{cand.get('summary', '')} | {stats} | 原因：{reasons}")
            for ch in cand.get("changes") or []:
                body = ch.get("after") or ch.get("before") or ""
                body = body if len(body) <= change_chars else body[:change_chars] + "…"
                lines.append(f"  · {ch.get('op')} {ch.get('section')}：{body}")
        blocks.append("\n".join(lines))
    dropped = 0
    while len(blocks) > 1 and sum(len(b) + 1 for b in blocks) > limit:
        blocks.pop(0)
        dropped += 1
    text = "\n".join(blocks)
    if len(text) > limit:
        text = text[:limit - 6] + "\n…（截断）"
    return (f"（更早 {dropped} 代略）\n" if dropped else "") + text


def gate_rules_text(config: dict) -> str:
    """Plain-language gate requirements, read defensively from ``config['gate']``."""
    g = config.get("gate") or {}
    tol = g.get("tolerance") or 0
    lines = []
    gain = g.get("min_primary_gain_visitors")
    lines.append(f"- 主指标 {g.get('primary_metric', 'isi_response_rate')}（4 周 ISI 有效率）必须严格高于当前版本"
                 + (f"，且至少多 {gain} 个有效来访" if isinstance(gain, int) and gain > 1 else "") + "。")
    if isinstance(g.get("replicates"), int) and g["replicates"] > 1:
        lines.append(f"- 当前版本和每个候选都在验证集上各跑 {g['replicates']} 次后合并比较，偶然的单次波动不算数。")
    if g.get("referral_recall_non_inferior", True):
        tol_v = g.get("referral_recall_tolerance_visitors")
        slack = (f"最多容许比当前版本少召回 {tol_v} 人" if tol_v
                 else f"容差 {tol}" if tol else "不允许任何下降")
        lines.append(f"- 转介召回率不得低于当前版本（{slack}）。")
    if g.get("referral_recall_by_label_non_inferior"):
        lines.append("- R1、R2、R3 各类召回率也分别不得低于当前版本。")
    if g.get("referral_precision_floor") is not None:
        lines.append(f"- 转介精确率不得低于 {g['referral_precision_floor']}（把不需要转介的来访判成转介会拉低它）。")
    if g.get("contraindication_violations_max") is not None:
        lines.append(f"- 禁忌违规次数不得超过 {g['contraindication_violations_max']}。")
    lines.append(f"- 危机漏报不得超过 {g.get('crisis_missed_max', 0)}，危机召回不得下降（由固定安全层负责，你不改也不需要改）。")
    lines.append("- 验证前还要通过固定规则检查（安全边界、锁定行、措辞、格式等）；通过门禁的候选最多采纳一份（主指标最高者）。")
    lines.append("- 验证集是同分布的新来访、样本不大：只对个别来访有效的改动很难稳定胜出，针对大类损失的改动更容易通过。")
    return "\n".join(lines)


_MODULE_LABELS = {"turn": "每回合提问/调用工具（turn）", "strategy": "提问策略（strategy）",
                  "response": "回复措辞（response）", "memory": "轮末记忆与转介判断（memory）",
                  "plan": "处方（plan）", "memory_plan": "轮末记忆 + 转介判断 + 写处方（memory_plan）",
                  "select": "第 2 轮决定保持或调整处方（select）"}


def budget_text() -> str:
    """Per-round action caps (engine config) and which module sees which playbook section."""
    lines = []
    pipeline: dict = {}
    try:
        from ..config import load_config as load_engine_config
        engine = load_engine_config()
        caps = engine["round_turn_cap"]
        pipeline = engine.get("pipeline") or {}
        lines.append(f"- 每轮动作上限：第 1 轮 {caps[1]} 次，第 2 轮 {caps[2]} 次。一次提问或一次主动调用筛查工具各占 1 次；"
                     "系统强制的筛查和每轮最后的收尾消息（给方案）不占。")
    except Exception:  # noqa: BLE001 - prompt must still build without engine config
        lines.append("- 每轮动作数有上限（读取引擎配置失败）；一次提问或一次主动调用筛查工具各占 1 次。")
    lines.append("- 收尾消息之后来访才说出的线索，本轮判断已用不上（第 1 轮的可留到第 2 轮，第 2 轮的完全用不上）。")
    lines.append("- 要新增一个提问或工具调用，必须同时写明挤掉哪个提问或把什么提前，不能超出上限。")
    try:
        from ..session import SECTIONS_FOR
    except Exception:  # noqa: BLE001
        SECTIONS_FOR = {}
    if SECTIONS_FOR:
        modules = (["turn"] if pipeline.get("merge_strategy_response", True) else ["strategy", "response"]) \
            + (["memory_plan"] if pipeline.get("merge_memory_plan", True) else ["memory", "plan"]) + ["select"]
        lines.append("- 章节可见性（每个模块只看到、只能执行这些章节里的规则）：")
        lines.extend(f"  · {_MODULE_LABELS.get(m, m)} 看 {'、'.join(SECTIONS_FOR[m])}" for m in modules if m in SECTIONS_FOR)
    return "\n".join(lines)


def build_prompts(*, playbook_text: str, version: str, run_report: dict, failures: list[dict],
                  sessions: dict, feedback: list[dict], config: dict, visitors: dict | None = None,
                  traces: dict | None = None, evidence: dict | None = None, audit: dict | None = None,
                  history: list[dict] | None = None) -> tuple[str, str]:
    rc = config["reflector"]
    visitors = visitors or {}
    evidence = evidence or ev.run_evidence(failures, sessions, traces or {}, visitors)
    if audit is None:
        audit = au.build_audit(run_report, sessions, traces or {}, visitors, config)
    card = dims.scorecard(run_report, visitors, config)
    system = _fill(_read_prompt(rc["prompts"]["system"]),
                   {"max_changes": rc["max_changes_per_candidate"], "max_chars": rc["max_change_chars"]})
    # Optional reflection skill: a frozen, model-agnostic working procedure (method only, no domain
    # answers) appended to the system prompt so a small model can follow the same steps.
    skill_path = rc["prompts"].get("skill")
    if skill_path:
        system = system.rstrip() + "\n\n" + _read_prompt(skill_path).strip() + "\n"
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
        "scorecard": _scorecard_text(card),
        "evidence_summary": json.dumps({k: v for k, v in evidence["summary"].items() if k != "by_step"},
                                       ensure_ascii=False),
        "failures": "\n\n".join(
            _failure_block(r, sessions.get(r["visitor_id"]), rc["max_transcript_chars"],
                           dims.classify(r, visitors.get(r["visitor_id"]), config),
                           ev.describe(evidence["visitors"][r["visitor_id"]]) if r["visitor_id"] in evidence["visitors"] else None)
            for r in failures) or "（无）",
        "audit": au.render_audit(audit, config),
        "gate_rules": gate_rules_text(config),
        "budget": budget_text(),
        "history": history_text(history, rc.get("history_max_chars", 3000)),
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
    dimension = raw.get("dimension")
    if dimension == "safety":
        return None  # safety is a red line, never a target
    if dimension not in dims.EDITABLE_DIMENSIONS:
        dimension = dims.DEFAULT_DIMENSION_BY_SECTION[section]
    return {"op": op, "section": section, "before": before, "after": after, "dimension": dimension,
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
                   dropped: list[str], attempts: list[dict], role: str) -> list[dict]:
    started = time.perf_counter()
    attempt = {"role": role, "provider": getattr(client, "provider", None), "model": client.model,
               "reasoning_effort": getattr(client, "effort", None), "reasoning_tokens": None,
               "success": False, "error": None}
    try:
        text = await asyncio.wait_for(client.complete(system, user),
                                      timeout=getattr(client, "timeout_s", timeout_s))
        candidates = normalize(extract_json(text), config, dropped)
        if not candidates:
            raise ValueError("没有任何格式有效的候选")
        attempt["success"] = True
        return candidates
    except Exception as exc:
        attempt["error"] = error_reason(exc)
        raise
    finally:
        attempt.update(getattr(client, "last_response_metadata", {}))
        attempt["duration_s"] = round(time.perf_counter() - started, 6)
        attempts.append(attempt)


async def reflect(*, playbook_text: str, version: str, run_report: dict, sessions: dict,
                  feedback: list[dict], config: dict, primary: LLMClient | None,
                  fallback: LLMClient | None, primary_error: str | None = None,
                  traces: dict | None = None, visitors: dict | None = None,
                  history: list[dict] | None = None) -> ReflectionResult:
    rc = config["reflector"]
    visitors = visitors or {}
    audit = au.build_audit(run_report, sessions, traces or {}, visitors, config)
    if rc.get("failure_selection", "audit") == "audit":
        failures = select_failures_by_audit(run_report, audit, config, visitors)
    else:
        failures = select_failures(run_report, config, visitors)
    evidence = ev.run_evidence(run_report["per_visitor"], sessions, traces or {}, visitors)
    system, user = build_prompts(playbook_text=playbook_text, version=version, run_report=run_report,
                                 failures=failures, sessions=sessions, feedback=feedback, config=config,
                                 visitors=visitors, evidence=evidence, audit=audit, history=history)
    failures_used = [{"visitor_id": r["visitor_id"], "failure_tags": r["failure_tags"]} for r in failures]
    insight = {"failure_dimensions": {r["visitor_id"]: dims.classify(r, visitors.get(r["visitor_id"]), config)
                                      for r in failures},
               "scorecard": dims.scorecard(run_report, visitors, config), "evidence": evidence}
    dropped: list[str] = []
    attempts: list[dict] = []

    def finish(candidates: list[dict], fell_back: bool, reason: str | None) -> ReflectionResult:
        # No constructed client means no model was actually called.
        actual = attempts[-1] if attempts else {}
        return ReflectionResult(finalize(candidates), actual.get("model", "unavailable"),
                                fell_back, reason, failures_used, dropped, **insight,
                                provider=actual.get("provider"), reasoning_effort=actual.get("reasoning_effort"),
                                attempts=attempts, audit=audit)

    reason = primary_error
    if primary is not None:
        try:
            cands = await _attempt(primary, system, user, rc["primary_timeout_s"], config, dropped, attempts, "primary")
            return finish(cands, False, None)
        except Exception as exc:  # noqa: BLE001 - any failure → automatic fallback
            reason = f"主反思器失败（{error_reason(exc)}）"
    elif reason is None:
        reason = "未配置主反思器"
    if fallback is not None:
        try:
            cands = await _attempt(fallback, system, user, rc["fallback_timeout_s"], config, dropped, attempts, "fallback")
            return finish(cands, True, reason)
        except Exception as exc:  # noqa: BLE001
            reason = f"{reason}；降级模型也失败（{error_reason(exc)}）"
    else:
        reason = f"{reason}；未配置降级模型"
    return finish([], True, reason)
