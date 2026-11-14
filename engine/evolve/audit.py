"""Run audit: purely empirical tables over one run's own outcomes and labels.

The reflector gets *measuring instruments, not answers*: every number here is counted from
this run's sessions, traces, visitor cards and scored outcomes (the same post-hoc labels it
already sees per failure case). Nothing is imported from the frozen state model and no
clinical threshold, keyword list or path→component map is encoded here; the reflector has
to induce rules from the tables itself.

``build_audit`` returns a JSON-serialisable dict that keeps visitor-id lists for every count
(traceability); ``render_audit`` turns it into compact Chinese text for the prompt.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import re

from ..topics import tag_topics

_SUPPORT_FROM_ID = re.compile(r"#((?:P|R)\d)-")
_TIMINGS = ("r1_before_close", "r1_after_close", "r2_before_close", "r2_after_close", "never")
_TIMING_LABELS = {"r1_before_close": "第1轮收尾前", "r1_after_close": "第1轮收尾消息之后",
                  "r2_before_close": "第2轮收尾前", "r2_after_close": "第2轮收尾消息之后", "never": "从未"}
_COND_LABELS = {"referral_wrong": "转介判错(真≠R0)", "plan_missing_common": "缺同路径有效者常用组件",
                "no_plan": "无处方(危机出口)", "none": "以上都不是"}


def _cfg(config: dict | None) -> dict:
    defaults = {"max_render_chars": 7000, "common_component_share": 0.5, "min_cell_n": 2,
                "exclude_scales": ["isi"], "max_list_values": 16,
                "tools": ["screen_mood", "screen_osa"], "exclude_clue_supports": ["crisis"]}
    defaults.update((config or {}).get("audit") or {})
    return defaults


def _kn(k: int, n: int) -> str:
    return f"{k}/{n}"


def _sorted(ids) -> list[str]:
    return sorted(set(ids))


# -- per-session reconstruction ---------------------------------------------------------------
def _clue_index(visitor: dict | None) -> dict[str, dict]:
    out = {}
    for clue in (visitor or {}).get("clues", []) or []:
        out[clue["id"]] = {"topic": clue.get("reveal_topic"), "supports": clue.get("supports"),
                           "deny_first": bool(clue.get("deny_first"))}
    return out


def _clue_meta(cid: str, clues: dict) -> dict:
    if cid in clues:
        return clues[cid]
    m = _SUPPORT_FROM_ID.search(cid)
    return {"topic": None, "supports": m.group(1) if m else None, "deny_first": False}


def _forced_keys(trace: dict | None) -> set[tuple]:
    return {(f.get("round"), f.get("turn"), f.get("tool")) for f in (trace or {}).get("forced_tool_calls") or []
            if f.get("forced", True)}


def session_events(session: dict, trace: dict | None, visitor: dict | None) -> dict:
    """Asks (agent messages), replies and tool calls of one session, in order, with reveal timing."""
    clues = _clue_index(visitor)
    completed = session.get("status") == "completed"
    replies_meta = list((trace or {}).get("s2_replies") or [])
    visitor_turns = [t for rnd in session.get("rounds", []) for t in rnd.get("transcript", [])
                     if t.get("speaker") == "visitor"]
    aligned = len(replies_meta) == len(visitor_turns)
    asks, replies, seen_clues, asked_before = [], [], set(), set()
    first_reveal: dict[str, dict] = {}
    v_index = 0
    for rnd in session.get("rounds", []):
        r = rnd["round"]
        transcript = rnd.get("transcript", [])
        agent_idx = [i for i, t in enumerate(transcript) if t.get("speaker") == "agent"]
        last_agent = agent_idx[-1] if agent_idx else None
        current = None
        after_close = False
        for i, t in enumerate(transcript):
            if t.get("speaker") == "agent":
                closing = completed and i == last_agent
                topics = tag_topics(t.get("text", ""))
                current = {"round": r, "turn": t.get("turn"), "topics": topics, "closing": closing,
                           "reask_topics": [x for x in topics if x in asked_before] if not closing else [],
                           "new_clues": [], "denied": [], "replied": False}
                if closing:
                    after_close = True
                else:
                    asked_before.update(topics)
                asks.append(current)
                continue
            if t.get("speaker") != "visitor":
                continue
            meta = replies_meta[v_index] if aligned else {}
            v_index += 1
            new = [c for c in (t.get("revealed_clue_ids") or []) if c not in seen_clues]
            seen_clues.update(new)
            denied = list(meta.get("denied_clue_ids") or [])
            timing = f"r{r}_{'after' if after_close else 'before'}_close"
            for c in new:
                first_reveal.setdefault(c, {"round": r, "turn": t.get("turn"), "timing": timing})
            reply = {"round": r, "turn": t.get("turn"), "new_clues": new, "denied": denied,
                     "opening": current is None, "after_close": after_close}
            replies.append(reply)
            if current is not None and not current["replied"]:
                current.update(new_clues=new, denied=denied, replied=True)
    forced = _forced_keys(trace)
    tools = [{"round": c.get("round"), "turn": c.get("turn"), "tool": c.get("tool"),
              "forced": (c.get("round"), c.get("turn"), c.get("tool")) in forced, "result": c.get("result") or {}}
             for c in session.get("tool_calls") or []]
    return {"asks": asks, "replies": replies, "tools": tools, "first_reveal": first_reveal,
            "clues": clues, "trace_aligned": aligned, "completed": completed}


def _scores(session: dict, tools: list[dict], exclude: set[str]) -> dict:
    """scale → {value, source}; tool results win over pre-session self-reports."""
    out = {}
    for s in session.get("context_scales") or []:
        name, value = s.get("scale"), s.get("reported_score")
        if name and name not in exclude and isinstance(value, (int, float)):
            out[name] = {"value": value, "source": "self_report"}
    for call in tools:
        for key, value in call["result"].items():
            if key not in exclude and isinstance(value, (int, float)) and not isinstance(value, bool):
                out[key] = {"value": value, "source": call["tool"]}
    return out


# -- audit -----------------------------------------------------------------------------------------
def build_audit(run_report: dict, sessions: dict | None, traces: dict | None, visitors: dict | None,
                config: dict | None = None) -> dict:
    ac = _cfg(config)
    sessions, traces, visitors = sessions or {}, traces or {}, visitors or {}
    rows = sorted(run_report.get("per_visitor", []), key=lambda r: r["visitor_id"])
    caps = _turn_caps()
    exclude = set(ac["exclude_scales"])
    skip_supports = set(ac["exclude_clue_supports"])  # crisis clues belong to the fixed safety layer

    ev: dict[str, dict] = {}
    for row in rows:
        vid = row["visitor_id"]
        if vid in sessions:
            ev[vid] = session_events(sessions[vid], traces.get(vid), visitors.get(vid))

    def is_crisis(row):
        # Only sessions the fixed safety layer ended early; crisis handling is not editable.
        return (sessions.get(row["visitor_id"]) or {}).get("status") == "crisis_exit"

    crisis_ids = [r["visitor_id"] for r in rows if is_crisis(r)]
    core = [r for r in rows if r["visitor_id"] not in crisis_ids]

    def plan_of(vid):
        s = sessions.get(vid) or {}
        return (s.get("plan") or {}) if s.get("status", "completed") == "completed" else {}

    # ---- plan: component kits of responders per true main path ----
    comp_by_vid = {r["visitor_id"]: set(plan_of(r["visitor_id"]).get("components") or []) for r in rows}
    resp_by_path: dict[str, list[str]] = defaultdict(list)
    for r in core:
        if r["responder"] and plan_of(r["visitor_id"]):
            resp_by_path[r["main_path"]].append(r["visitor_id"])
    common: dict[str, list[str]] = {}
    for path, vids in resp_by_path.items():
        cnt = Counter(c for v in vids for c in comp_by_vid[v])
        common[path] = sorted(c for c, k in cnt.items() if k / len(vids) >= ac["common_component_share"])

    # ---- 1. loss overview ----
    combos: dict[str, list[str]] = defaultdict(list)
    cond_ids: dict[str, list[str]] = {k: [] for k in _COND_LABELS}
    missing_detail: dict[str, list[str]] = {}
    for r in rows:
        if r["responder"]:
            continue
        vid = r["visitor_id"]
        conds = []
        if r["referral_true"] != "R0" and r["referral_pred"] != r["referral_true"]:
            conds.append("referral_wrong")
        plan = plan_of(vid)
        if not plan:
            conds.append("no_plan")
        else:
            missing = [c for c in common.get(r["main_path"], []) if c not in comp_by_vid[vid]]
            if missing:
                conds.append("plan_missing_common")
                missing_detail[vid] = missing
        if not conds:
            conds = ["none"]
        for c in conds:
            cond_ids[c].append(vid)
        combos["+".join(conds)].append(vid)

    def rate_by(key_fn, subset):
        groups: dict[str, list[dict]] = defaultdict(list)
        for r in subset:
            groups[key_fn(r)].append(r)
        return {k: {"responders": _sorted(x["visitor_id"] for x in g if x["responder"]),
                    "ids": _sorted(x["visitor_id"] for x in g)} for k, g in sorted(groups.items())}

    referral_pos = [r for r in rows if r["referral_true"] != "R0"]
    overview = {
        "n": len(rows), "responders": _sorted(r["visitor_id"] for r in rows if r["responder"]),
        "crisis_excluded": _sorted(crisis_ids),
        "non_responder_conditions": {k: _sorted(v) for k, v in cond_ids.items()},
        "non_responder_combos": {k: _sorted(v) for k, v in sorted(combos.items(), key=lambda kv: (-len(kv[1]), kv[0]))},
        "plan_missing_detail": missing_detail,
        "common_components_by_path": common,
        "by_true_referral": rate_by(lambda r: r["referral_true"], rows),
        "by_true_path": rate_by(lambda r: r["main_path"], rows),
        "by_referral_correct_pos": rate_by(lambda r: "correct" if r["referral_pred"] == r["referral_true"] else "wrong",
                                          referral_pos),
    }

    # ---- 2. referral ----
    confusion: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in core:
        cell = confusion[r["referral_true"]].setdefault(r["referral_pred"] or "none", {"ids": [], "responders": []})
        cell["ids"].append(r["visitor_id"])
        if r["responder"]:
            cell["responders"].append(r["visitor_id"])
    tool_names = sorted(set(ac["tools"]) | {c["tool"] for e in ev.values() for c in e["tools"]})
    tools_by_label: dict[str, dict] = {}
    topic_asked: dict[str, dict] = {}
    clue_timing: dict[str, dict] = {}
    scores_by_cell: dict[str, dict] = {}
    scale_names: set[str] = set()
    labels = sorted({r["referral_true"] for r in core})
    for label in labels:
        group = [r for r in core if r["referral_true"] == label]
        ids = [r["visitor_id"] for r in group]
        per_tool = {}
        for tool in tool_names:
            buckets = {"r1_forced": [], "r1_proactive": [], "r2_forced": [], "r2_proactive": [], "never": []}
            for vid in ids:
                calls = [c for c in ev.get(vid, {}).get("tools", []) if c["tool"] == tool]
                if not calls:
                    buckets["never"].append(vid)
                for c in calls:
                    buckets[f"r{c['round']}_{'forced' if c['forced'] else 'proactive'}"].append(vid)
            per_tool[tool] = {k: _sorted(v) for k, v in buckets.items()}
        tools_by_label[label] = {"ids": ids, "tools": per_tool}
        asked = {"r1": [], "r2_only": [], "never": [], "no_clue": []}
        timing = {t: [] for t in _TIMINGS}
        for vid in ids:
            e = ev.get(vid)
            if not e:
                continue
            ref_clues = [cid for cid, m in e["clues"].items() if m["supports"] == label]
            topics = {e["clues"][c]["topic"] for c in ref_clues} - {None}
            if not ref_clues:
                asked["no_clue"].append(vid)
                continue
            rounds = {a["round"] for a in e["asks"] if not a["closing"] and topics & set(a["topics"])}
            asked["r1" if 1 in rounds else "r2_only" if 2 in rounds else "never"].append(vid)
            firsts = [e["first_reveal"][c] for c in ref_clues if c in e["first_reveal"]]
            if firsts:
                first = min(firsts, key=lambda f: (f["round"], f["turn"] or 0))
                timing[first["timing"]].append(vid)
            else:
                timing["never"].append(vid)
        topic_asked[label] = asked
        clue_timing[label] = timing
    for r in core:
        vid = r["visitor_id"]
        if vid not in sessions:
            continue
        sc = _scores(sessions[vid], ev[vid]["tools"], exclude)
        scale_names.update(sc)
        key = f"{r['referral_true']}->{r['referral_pred']}"
        scores_by_cell.setdefault(key, []).append({"visitor_id": vid, **{k: v["value"] for k, v in sc.items()},
                                                   "_sources": {k: v["source"] for k, v in sc.items()}})
    referral = {"confusion": confusion, "tools_by_label": tools_by_label, "topic_asked": topic_asked,
                "clue_timing": clue_timing, "scales": sorted(scale_names), "scores_by_cell": scores_by_cell}

    # ---- 3. questioning efficiency ----
    core_ids = [r["visitor_id"] for r in core if r["visitor_id"] in ev]
    per_topic: dict[str, dict] = defaultdict(lambda: {"r1": 0, "r2": 0, "yield": 0, "nothing": 0, "ids": set()})
    reask_wasted, reask_topic = [], Counter()
    replies_total, replies_empty = 0, 0
    first_topics = Counter()
    first_ids: dict[str, list] = defaultdict(list)
    after_close = {1: Counter(), 2: Counter()}
    after_close_ids = {1: [], 2: []}
    distinct = {1: [], 2: []}
    actions = {1: Counter(), 2: Counter()}
    multi_topic, ask_total = 0, 0
    for vid in core_ids:
        e = ev[vid]
        clues = e["clues"]
        first = next((a for a in e["asks"] if not a["closing"]), None)
        key = "+".join(first["topics"]) if first and first["topics"] else "(无话题)"
        first_topics[key] += 1
        first_ids[key].append(vid)
        for rnd in (1, 2):
            asks = [a for a in e["asks"] if a["round"] == rnd and not a["closing"]]
            if not any(a["round"] == rnd for a in e["asks"]):
                continue
            distinct[rnd].append(len({t for a in asks for t in a["topics"]}))
            n_tools = sum(1 for c in e["tools"] if c["round"] == rnd and not c["forced"])
            actions[rnd][len(asks) + n_tools] += 1
        for a in e["asks"]:
            if a["closing"]:
                continue
            ask_total += 1
            multi_topic += len(a["topics"]) >= 2
            topics_new = {_clue_meta(c, clues)["topic"] for c in a["new_clues"]}
            for t in a["topics"]:
                pt = per_topic[t]
                pt[f"r{a['round']}"] += 1
                pt["ids"].add(vid)
                if t in topics_new or (None in topics_new and a["new_clues"]):
                    pt["yield"] += 1
                if not a["new_clues"]:
                    pt["nothing"] += 1
            if a["reask_topics"] and not a["new_clues"]:
                reask_wasted.append(vid)
                reask_topic.update(a["reask_topics"])
        for rep in e["replies"]:
            if rep["opening"]:
                continue
            replies_total += 1
            replies_empty += not rep["new_clues"]
            late = [c for c in rep["new_clues"] if _clue_meta(c, clues)["supports"] not in skip_supports]
            if rep["after_close"] and late:
                for c in late:
                    after_close[rep["round"]][_clue_meta(c, clues)["topic"] or "?"] += 1
                after_close_ids[rep["round"]].append(vid)
    questioning = {
        "per_topic": {t: {**{k: v for k, v in d.items() if k != "ids"}, "ids": _sorted(d["ids"])}
                      for t, d in sorted(per_topic.items(), key=lambda kv: -(kv[1]["r1"] + kv[1]["r2"]))},
        "asks_total": ask_total, "multi_topic_asks": multi_topic,
        "reask_no_new": {"count": len(reask_wasted), "ids": _sorted(reask_wasted), "topics": dict(reask_topic.most_common())},
        "replies_total": replies_total, "replies_no_new": replies_empty,
        "first_question_topics": {k: _sorted(first_ids[k]) for k, _ in first_topics.most_common()},
        "after_close_reveals": {f"r{r}": {"clues": sum(after_close[r].values()), "topics": dict(after_close[r].most_common()),
                                          "ids": _sorted(after_close_ids[r])} for r in (1, 2)},
        "mean_distinct_topics": {f"r{r}": round(sum(v) / len(v), 2) if v else None for r, v in distinct.items()},
        "actions_used": {f"r{r}": {"cap": caps.get(r), "hist": dict(sorted(actions[r].items()))} for r in (1, 2)},
    }

    # ---- 4. path ----
    path_conf: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    unasked = Counter()
    unasked_ids: dict[str, list] = defaultdict(list)
    wrong_ids = []
    for r in core:
        vid = r["visitor_id"]
        path_conf[r["main_path"]][r.get("path_pred_r2") or "none"].append(vid)
        if r.get("path_pred_r2") == r["main_path"] or vid not in ev:
            continue
        wrong_ids.append(vid)
        e = ev[vid]
        topics = {m["topic"] for m in e["clues"].values() if m["supports"] == r["main_path"]} - {None}
        asked = {t for a in e["asks"] if not a["closing"] for t in a["topics"]}
        for t in sorted(topics - asked):
            unasked[t] += 1
            unasked_ids[t].append(vid)
    path = {"confusion_r2": {k: {p: _sorted(v) for p, v in sorted(d.items())} for k, d in sorted(path_conf.items())},
            "wrong_r2": _sorted(wrong_ids),
            "true_clue_topics_never_asked": {t: _sorted(unasked_ids[t]) for t, _ in unasked.most_common()}}

    # ---- 5. plan ----
    planned = [r for r in core if plan_of(r["visitor_id"])]
    freq = Counter(c for r in planned for c in comp_by_vid[r["visitor_id"]])
    cells = {}
    for p in sorted({r["main_path"] for r in planned}):
        group = [r for r in planned if r["main_path"] == p]
        row_cells = {}
        for comp in sorted({c for r in group for c in comp_by_vid[r["visitor_id"]]}):
            has = [r for r in group if comp in comp_by_vid[r["visitor_id"]]]
            lacks = [r for r in group if comp not in comp_by_vid[r["visitor_id"]]]
            if len(has) < ac["min_cell_n"] or len(lacks) < ac["min_cell_n"]:
                continue
            row_cells[comp] = {"with": {"responders": _sorted(x["visitor_id"] for x in has if x["responder"]),
                                        "ids": _sorted(x["visitor_id"] for x in has)},
                               "without": {"responders": _sorted(x["visitor_id"] for x in lacks if x["responder"]),
                                           "ids": _sorted(x["visitor_id"] for x in lacks)}}
        cells[p] = {"ids": _sorted(r["visitor_id"] for r in group),
                    "responders": _sorted(r["visitor_id"] for r in group if r["responder"]), "components": row_cells}
    plan = {"n_planned": len(planned), "component_freq": dict(freq.most_common()),
            "mean_components": round(sum(len(comp_by_vid[r["visitor_id"]]) for r in planned) / len(planned), 2) if planned else None,
            "by_path": cells}

    # ---- 6. deny-first ----
    denials = []
    for vid in core_ids:
        e = ev[vid]
        for idx, rep in enumerate(e["replies"]):
            for cid in rep["denied"]:
                if _clue_meta(cid, e["clues"])["supports"] in skip_supports:
                    continue
                topic = _clue_meta(cid, e["clues"])["topic"]
                later = [a for a in e["asks"] if not a["closing"] and (a["round"], a["turn"] or 0) > (rep["round"], rep["turn"] or 0)]
                reasked = bool(topic) and any(topic in a["topics"] for a in later)
                fr = e["first_reveal"].get(cid)
                revealed = bool(fr) and (fr["round"], fr["turn"] or 0) > (rep["round"], rep["turn"] or 0)
                via_reask = revealed and any(topic in a["topics"] and (a["round"], a["turn"] or 0) < (fr["round"], fr["turn"] or 0)
                                             for a in later) if topic else False
                denials.append({"visitor_id": vid, "clue": cid, "topic": topic, "round": rep["round"],
                                "reasked": reasked, "revealed_later": revealed,
                                "revealed_after_reask": via_reask})
    deny = {"denials": denials,
            "trace_missing": _sorted(v for v in core_ids if not ev[v]["trace_aligned"])}

    # ---- loss groups (for picking representative failure cases), largest first ----
    groups = {
        "referral_missed": [r["visitor_id"] for r in core if r["referral_true"] != "R0" and r["referral_pred"] != r["referral_true"]],
        "referral_false_alarm": [r["visitor_id"] for r in core if r["referral_true"] == "R0" and r["referral_pred"] != "R0"],
        "plan_missing_common": [v for v in cond_ids["plan_missing_common"] if v not in crisis_ids],
        "nonresponder_other": [v for v in cond_ids["none"] if v not in crisis_ids],
        "path_wrong_r2": list(wrong_ids),
    }
    loss_groups = {k: _sorted(v) for k, v in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])) if v}

    return {"n_visitors": len(rows), "n_core": len(core), "overview": overview, "referral": referral,
            "loss_groups": loss_groups,
            "questioning": questioning, "path": path, "plan": plan, "deny": deny,
            "missing_sessions": _sorted(r["visitor_id"] for r in rows if r["visitor_id"] not in sessions),
            "visitor_cards": sum(1 for r in rows if r["visitor_id"] in visitors)}


def _turn_caps() -> dict[int, int]:
    try:
        from ..config import load_config
        return dict(load_config()["round_turn_cap"])
    except Exception:  # noqa: BLE001 - audit must not fail on config problems
        return {}


# -- rendering ----------------------------------------------------------------------------------
def _cell(d: dict) -> str:
    return _kn(len(d["responders"]), len(d["ids"]))


def _values_line(cell: list[dict], scales: list[str], limit: int) -> str:
    tuples = sorted("/".join(str(v.get(s, "-")) for s in scales) for v in cell)
    shown = tuples[:limit]
    return ", ".join(shown) + (f" …(+{len(tuples) - limit})" if len(tuples) > limit else "")


def render_audit(audit: dict, config: dict | None = None) -> str:
    ac = _cfg(config)
    o, ref, q, pa, pl, de = (audit[k] for k in ("overview", "referral", "questioning", "path", "plan", "deny"))
    n = audit["n_visitors"]
    L = []
    nonresp = n - len(o["responders"])
    L.append("## A. 损失总览")
    L.append(f"来访 {n}，ISI 有效 {_kn(len(o['responders']), n)}，未有效 {nonresp}。"
             + (f"危机出口 {len(o['crisis_excluded'])} 个不计入 B–F 表。" if o["crisis_excluded"] else ""))
    L.append("未有效者按可观察条件（可重叠）：" + "；".join(
        f"{_COND_LABELS[k]} {len(v)}" for k, v in o["non_responder_conditions"].items()))
    L.append("组合：" + "；".join(f"{'+'.join(_COND_LABELS[c] for c in k.split('+'))} {len(v)}"
                               for k, v in o["non_responder_combos"].items()))
    if o["common_components_by_path"]:
        L.append(f"（“常用组件”= 同真路径有效者中 ≥{int(_cfg(config)['common_component_share'] * 100)}% 用过的组件："
                 + "；".join(f"{p} {','.join(c) or '无'}" for p, c in sorted(o["common_components_by_path"].items())) + "）")
        miss = Counter(c for v in o["plan_missing_detail"].values() for c in v)
        if miss:
            L.append("未有效者缺的常用组件：" + "，".join(f"{c} {k}" for c, k in miss.most_common()))
    L.append("有效率·按真转介：" + "；".join(f"{k} {_cell(v)}" for k, v in o["by_true_referral"].items()))
    L.append("有效率·按真主路径：" + "；".join(f"{k} {_cell(v)}" for k, v in o["by_true_path"].items()))
    if o["by_referral_correct_pos"]:
        lab = {"correct": "判对", "wrong": "判错"}
        L.append("真转介≠R0 中有效率：" + "；".join(f"{lab[k]} {_cell(v)}" for k, v in o["by_referral_correct_pos"].items()))

    L.append("## B. 转介")
    L.append("混淆（真→判：人数，其中有效）：" + "；".join(
        f"{t}→{p} {len(c['ids'])}(有效{len(c['responders'])})"
        for t, row in sorted(ref["confusion"].items()) for p, c in sorted(row.items())))
    for label, info in ref["tools_by_label"].items():
        m = len(info["ids"])
        parts = []
        for tool, b in info["tools"].items():
            bits = [f"{k.replace('_forced', '强制').replace('_proactive', '主动')} {len(v)}"
                    for k, v in b.items() if k != "never" and v]
            parts.append(f"{tool} 调用 {_kn(m - len(b['never']), m)}" + (f"（{'，'.join(bits)}）" if bits else ""))
        L.append(f"真{label}(n={m}) 工具：" + "；".join(parts))
    scales = ref["scales"]
    if scales:
        L.append(f"量表分（每人一组 {'/'.join(scales)}，- = 无数据；工具结果优先于会前自评）：")
        for key, cell in sorted(ref["scores_by_cell"].items()):
            if any(s in v for v in cell for s in scales):
                t, p = key.split("->")
                L.append(f"  真{t}判{p} n={len(cell)}: {_values_line(cell, scales, ac['max_list_values'])}")
    L.append("本人转介线索话题（该来访 supports=真标签 的线索的 reveal_topic）是否被问到（不含收尾消息）：")
    for label, a in ref["topic_asked"].items():
        m = sum(len(v) for k, v in a.items() if k != "no_clue")
        if not m:
            continue
        L.append(f"  真{label}: 第1轮问到 {_kn(len(a['r1']), m)}，仅第2轮 {_kn(len(a['r2_only']), m)}，从未 {_kn(len(a['never']), m)}")
    L.append("转介线索首次出现时机：")
    for label, tm in ref["clue_timing"].items():
        m = sum(len(v) for v in tm.values())
        if m:
            L.append(f"  真{label}: " + "，".join(f"{_TIMING_LABELS[k]} {_kn(len(v), m)}" for k, v in tm.items() if v))

    L.append("## C. 提问效率（不含收尾消息）")
    L.append(f"提问 {q['asks_total']} 次，其中一条消息含 ≥2 话题 {_kn(q['multi_topic_asks'], q['asks_total'])}；"
             f"来访回复无新线索 {_kn(q['replies_no_new'], q['replies_total'])}；"
             f"重问已问过的话题且无新线索 {q['reask_no_new']['count']} 次（"
             + "，".join(f"{t} {k}" for t, k in list(q["reask_no_new"]["topics"].items())[:8]) + "）")
    L.append("按话题（r1问/r2问，问出该话题新线索/回复无任何新线索）：" + "；".join(
        f"{t} {d['r1']}/{d['r2']} 得{d['yield']} 空{d['nothing']}" for t, d in q["per_topic"].items()))
    L.append("第1句提问的话题：" + "；".join(f"{k} {len(v)}" for k, v in q["first_question_topics"].items()))
    for r in ("r1", "r2"):
        ac_r = q["after_close_reveals"][r]
        L.append(f"{r} 收尾消息之后才出现的线索 {ac_r['clues']} 条（{len(ac_r['ids'])} 人），话题："
                 + ("，".join(f"{t} {k}" for t, k in ac_r["topics"].items()) or "无"))
    L.append("每轮不同话题数均值 " + "，".join(f"{r} {v}" for r, v in q["mean_distinct_topics"].items())
             + "；动作数（提问+主动工具）/上限：" + "；".join(
                 f"{r} 上限{d['cap']}: " + "，".join(f"{k}次×{v}" for k, v in d["hist"].items())
                 for r, d in q["actions_used"].items()))

    L.append("## D. 路径（第2轮）")
    L.append("混淆：" + "；".join(f"真{t}→" + ",".join(f"{p} {len(v)}" for p, v in row.items())
                               for t, row in pa["confusion_r2"].items()))
    if pa["true_clue_topics_never_asked"]:
        L.append(f"判错的 {len(pa['wrong_r2'])} 人中，真路径线索话题从未被问到：" + "，".join(
            f"{t} {len(v)}" for t, v in pa["true_clue_topics_never_asked"].items()))

    L.append("## E. 处方")
    L.append(f"有处方 {pl['n_planned']} 人，平均组件数 {pl['mean_components']}；频次：" + "，".join(
        f"{c} {k}" for c, k in pl["component_freq"].items()))
    L.append(f"按真主路径 × 组件 → 有效（有该组件 k/n | 无 k/n；两侧 n≥{ac['min_cell_n']} 才列）：")
    for p, info in pl["by_path"].items():
        cells = "；".join(f"{c} 有{_cell(d['with'])}|无{_cell(d['without'])}" for c, d in info["components"].items())
        L.append(f"  {p}(有效{_cell(info)}): {cells or '无可比单元'}")

    L.append("## F. 先否认的线索")
    dn = de["denials"]
    if dn:
        L.append(f"来访否认 {len(dn)} 次；之后 agent 重问该话题 {_kn(sum(d['reasked'] for d in dn), len(dn))}，"
                 f"之后线索出现 {_kn(sum(d['revealed_later'] for d in dn), len(dn))}"
                 f"（其中由重问带出 {sum(d['revealed_after_reask'] for d in dn)}，其余由收尾消息或其他话题带出）；话题："
                 + "，".join(f"{t} {k}" for t, k in Counter(d['topic'] or '?' for d in dn).most_common()))
    else:
        L.append("无否认记录（或缺 trace）。")
    text = "\n".join(L)
    cap = ac["max_render_chars"]
    return text if len(text) <= cap else text[:cap - 12] + "\n…（审计截断）"
