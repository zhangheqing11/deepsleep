import asyncio
import json

from engine.evolve.audit import build_audit, render_audit
from engine.evolve.reflector import (build_prompts, gate_rules_text, history_text, reflect,
                                     select_failures_by_audit)
from evolve_support import FIXTURE_INITIAL, MockLLM, change, example, make_config, reply


def _row(vid, path, ref_true, ref_pred, responder, tags, pred_r2=None):
    return {"visitor_id": vid, "main_path": path, "path_pred_r1": pred_r2 or path, "path_pred_r2": pred_r2 or path,
            "referral_true": ref_true, "referral_pred": ref_pred, "crisis_true": "none", "crisis_pred": "none",
            "isi_baseline": 18, "isi_week": [18, 10], "isi_change": -8 if responder else -2, "responder": responder,
            "adherence": 0.6, "alliance": 0.9, "failure_tags": tags, "session_ref": f"sessions/{vid}.json",
            "prefilled_scales": [], "screened": []}


def _t(turn, speaker, text, revealed=()):
    return {"turn": turn, "speaker": speaker, "text": text, "revealed_clue_ids": list(revealed)}


def _session(vid, rounds, components, tools=(), status="completed", scales=()):
    return {"visitor_id": vid, "status": status, "rounds": rounds, "tool_calls": list(tools),
            "context_scales": list(scales),
            "plan": {"components": components} if components else None}


def _clue(vid, name, topic, supports, deny=False):
    return {"id": f"{vid}::domain/x.md#{supports}-{name}", "reveal_topic": topic, "supports": supports,
            "deny_first": deny}


# V1: true R0 judged R3, no response; re-asks schedule with nothing new; snoring clue only after closing.
V1 = _session("V1", [
    {"round": 1, "transcript": [
        _t(1, "visitor", "睡不好"),
        _t(2, "agent", "你平时几点上床？"),
        _t(3, "visitor", "23点"),
        _t(4, "agent", "那起床时间呢？"),
        _t(5, "visitor", "7点"),
        _t(7, "agent", "我想问问你会打鼾吗？"),
        _t(8, "visitor", "没有"),
        _t(9, "agent", "先固定起床时间试两周。"),
        _t(10, "visitor", "好，对了家里说我打呼", ["V1::domain/x.md#R0-c1"]),
    ]},
    {"round": 2, "transcript": [
        _t(1, "agent", "你会打鼾吗？"),
        _t(2, "visitor", "好像会", ["V1::domain/x.md#P1-c1"]),
        _t(3, "agent", "继续固定起床。"),
        _t(4, "visitor", "好"),
    ]}],
    ["fixed_risetime"],
    tools=[{"round": 1, "turn": 6, "tool": "screen_mood", "result": {"phq9": 7, "gad7": 3, "phq9_items": [1] * 9}}])
TRACE1 = {"forced_tool_calls": [{"round": 1, "turn": 6, "tool": "screen_mood", "forced": True}],
          "s2_replies": [{"revealed_clue_ids": [], "denied_clue_ids": []},
                         {"revealed_clue_ids": [], "denied_clue_ids": []},
                         {"revealed_clue_ids": [], "denied_clue_ids": []},
                         {"revealed_clue_ids": [], "denied_clue_ids": ["V1::domain/x.md#P1-c1"]},
                         {"revealed_clue_ids": ["V1::domain/x.md#R0-c1"], "denied_clue_ids": []},
                         {"revealed_clue_ids": ["V1::domain/x.md#P1-c1"], "denied_clue_ids": []},
                         {"revealed_clue_ids": [], "denied_clue_ids": []}]}
# V2: true R1 judged R1, responder; proactive screen_osa; snoring asked in round 1 and revealed before closing.
V2 = _session("V2", [
    {"round": 1, "transcript": [
        _t(1, "visitor", "睡不好"),
        _t(2, "agent", "晚上会打鼾吗？"),
        _t(3, "visitor", "会，还憋醒", ["V2::domain/x.md#R1-c1"]),
        _t(5, "agent", "先固定起床时间。"),
        _t(6, "visitor", "好"),
    ]}],
    ["fixed_risetime", "sleep_hygiene"],
    tools=[{"round": 1, "turn": 4, "tool": "screen_osa", "result": {"stop_bang": 5}}],
    scales=[{"scale": "isi", "reported_score": 18, "items": None}, {"scale": "phq9", "reported_score": 4, "items": None}])
V3 = _session("V3", [{"round": 1, "transcript": [_t(1, "visitor", "x"), _t(2, "agent", "安全")]}], None, status="crisis_exit")
V4 = _session("V4", [{"round": 1, "transcript": [_t(1, "visitor", "x"), _t(2, "agent", "周末会补觉吗？"),
                                                  _t(3, "visitor", "会"), _t(4, "agent", "固定起床。")]}],
              ["fixed_risetime", "sleep_hygiene"])
RUN = {"run_id": "t", "label": "t", "n_visitors": 4,
       "metrics": example("run_report.run1.json")["metrics"],
       "per_visitor": [
           _row("V1", "P1", "R0", "R3", False, ["referral_false_alarm", "no_isi_response"]),
           _row("V2", "P1", "R1", "R1", True, []),
           {**_row("V3", "P1", "R0", "R3", False, ["crisis_missed"]), "crisis_true": "active"},
           _row("V4", "P1", "R0", "R0", True, []),
       ]}
SESSIONS = {"V1": V1, "V2": V2, "V3": V3, "V4": V4}
VISITORS = {
    "V1": {"id": "V1", "clues": [_clue("V1", "c1", "snoring_breathing", "R0"), _clue("V1", "c1", "snoring_breathing", "P1", True)]},
    "V2": {"id": "V2", "clues": [_clue("V2", "c1", "snoring_breathing", "R1")]},
}


def _audit(tmp_path, traces=None, visitors=None):
    return build_audit(RUN, SESSIONS, {"V1": TRACE1} if traces is None else traces,
                       VISITORS if visitors is None else visitors, make_config(tmp_path))


def test_overview_conditions_and_rates(tmp_path):
    o = _audit(tmp_path)["overview"]
    assert o["responders"] == ["V2", "V4"] and o["crisis_excluded"] == ["V3"]
    assert o["common_components_by_path"]["P1"] == ["fixed_risetime", "sleep_hygiene"]
    assert o["non_responder_conditions"]["plan_missing_common"] == ["V1"]
    assert o["plan_missing_detail"]["V1"] == ["sleep_hygiene"]
    assert o["non_responder_conditions"]["no_plan"] == ["V3"]
    assert o["by_true_referral"]["R0"] == {"responders": ["V4"], "ids": ["V1", "V3", "V4"]}
    assert o["by_referral_correct_pos"]["correct"]["ids"] == ["V2"]


def test_referral_tables(tmp_path):
    ref = _audit(tmp_path)["referral"]
    assert ref["confusion"]["R0"]["R3"]["ids"] == ["V1"]          # crisis exit V3 excluded
    assert "V3" not in json.dumps(ref)
    r0_tools = ref["tools_by_label"]["R0"]["tools"]
    assert r0_tools["screen_mood"]["r1_forced"] == ["V1"] and r0_tools["screen_osa"]["never"] == ["V1", "V4"]
    assert ref["tools_by_label"]["R1"]["tools"]["screen_osa"]["r1_proactive"] == ["V2"]
    assert ref["scales"] == ["gad7", "phq9", "stop_bang"]         # isi excluded, phq9_items list ignored
    v1 = ref["scores_by_cell"]["R0->R3"][0]
    assert (v1["phq9"], v1["gad7"], v1["_sources"]["phq9"]) == (7, 3, "screen_mood")
    v2 = ref["scores_by_cell"]["R1->R1"][0]
    assert v2["stop_bang"] == 5 and v2["_sources"]["phq9"] == "self_report"
    assert ref["topic_asked"]["R1"]["r1"] == ["V2"] and ref["topic_asked"]["R0"]["r1"] == ["V1"]
    assert ref["clue_timing"]["R1"]["r1_before_close"] == ["V2"]
    assert ref["clue_timing"]["R0"]["r1_after_close"] == ["V1"]


def test_questioning_efficiency(tmp_path):
    q = _audit(tmp_path)["questioning"]
    assert q["reask_no_new"]["count"] == 1 and q["reask_no_new"]["topics"] == {"schedule_regularity": 1}
    assert q["after_close_reveals"]["r1"]["clues"] == 1 and q["after_close_reveals"]["r1"]["topics"] == {"snoring_breathing": 1}
    assert q["per_topic"]["snoring_breathing"]["r1"] == 2 and q["per_topic"]["snoring_breathing"]["r2"] == 1
    assert q["per_topic"]["snoring_breathing"]["yield"] == 2         # V2 r1 and V1 r2
    # V1 r1: 3 asks + forced tool (not counted); V2 r1: 1 ask + 1 proactive tool
    assert q["actions_used"]["r1"]["hist"] == {1: 1, 2: 1, 3: 1}
    assert q["actions_used"]["r1"]["cap"] == 4


def test_deny_and_plan(tmp_path):
    audit = _audit(tmp_path)
    (d,) = audit["deny"]["denials"]
    assert d["visitor_id"] == "V1" and d["reasked"] and d["revealed_later"] and d["revealed_after_reask"]
    plan = audit["plan"]
    assert plan["component_freq"] == {"fixed_risetime": 3, "sleep_hygiene": 2}
    assert plan["by_path"]["P1"]["components"] == {}                # n<2 on one side → no cell


def test_render_compact_deterministic_and_tolerant(tmp_path):
    audit = _audit(tmp_path)
    json.dumps(audit)
    text = render_audit(audit, make_config(tmp_path))
    assert text == render_audit(_audit(tmp_path), make_config(tmp_path))
    assert "2/4" in text and "V1" not in text and "## B. 转介" in text
    short = render_audit(audit, make_config(tmp_path, audit={"max_render_chars": 300}))
    assert len(short) <= 300 and short.endswith("（审计截断）")
    bare = build_audit(RUN, SESSIONS, {}, {}, make_config(tmp_path))       # no traces, no cards
    render_audit(bare, make_config(tmp_path))
    assert build_audit({"per_visitor": []}, {}, {}, {}, None)["n_visitors"] == 0


def test_failure_selection_follows_loss_groups(tmp_path):
    config = make_config(tmp_path, reflector={"max_failures": 2})
    audit = _audit(tmp_path)
    picked = [r["visitor_id"] for r in select_failures_by_audit(RUN, audit, config, VISITORS)]
    assert picked == ["V1"]                                          # V3 has only crisis_missed


def test_gate_rules_and_history_text(tmp_path):
    config = make_config(tmp_path)
    config["gate"].update(min_primary_gain_visitors=2, referral_recall_tolerance_visitors=1)
    text = gate_rules_text(config)
    assert "严格高于" in text and "至少多 2 个" in text and "少召回 1 人" in text and "0.5" in text
    gen = {"generation": 1, "from_version": "v1", "to_version": None, "candidates": [
        {"id": "c1", "summary": "问打鼾", "outcome": "rejected", "reasons": ["主指标未提升"],
         "delta": {"n": 40, "isi_responders": 22, "gained": 2, "lost": 3, "referral_recall": 0.6,
                   "referral_precision": None, "path_acc_r2": None, "screening_coverage": 0.5},
         "changes": [{"op": "add", "section": "questioning_strategy", "before": None, "after": "很长" * 100}]}]}
    h = history_text([gen, {**gen, "generation": 2}], limit=100000)
    assert h.index("第 1 代") < h.index("第 2 代") and "门禁拒绝" in h and "0.60" in h and "…" in h
    one = history_text([gen, {**gen, "generation": 2}], limit=len(h) // 2 + 20)
    assert "更早 1 代略" in one and "第 2 代" in one
    assert "第一代" in history_text(None)


def test_prompts_include_audit_gate_budget_history(tmp_path):
    config = make_config(tmp_path)
    system, user = build_prompts(playbook_text=FIXTURE_INITIAL.read_text(encoding="utf-8"), version="v1",
                                 run_report=RUN, failures=[RUN["per_visitor"][0]], sessions=SESSIONS, feedback=[],
                                 config=config, visitors=VISITORS, history=[{"generation": 1, "from_version": "v1",
                                                                             "to_version": "v2", "candidates": []}])
    assert "{{" not in system + user
    assert "## A. 损失总览" in user and "门禁规则" in user and "第 1 轮 4 次" in user and "第 1 代" in user
    assert "questioning_strategy" in user and "预计修复" in system


def test_reflect_returns_audit_and_accepts_history(tmp_path):
    good = reply([change("questioning_strategy", "第 1 轮问一次打鼾。")], [change("referral_rules", "量表分低时给 R0。")],
                 [change("plan_rules", "按路径选组件。")])
    llm = MockLLM(good)
    result = asyncio.run(reflect(playbook_text=FIXTURE_INITIAL.read_text(encoding="utf-8"), version="v1",
                                 run_report=RUN, sessions=SESSIONS, feedback=[], config=make_config(tmp_path),
                                 primary=llm, fallback=None, traces={"V1": TRACE1}, visitors=VISITORS, history=[]))
    assert result.audit["overview"]["responders"] == ["V2", "V4"]
    assert [f["visitor_id"] for f in result.failures_used] == ["V1"]
    assert "运行审计" in llm.calls[0][1]
