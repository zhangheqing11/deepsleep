import asyncio

import pytest

from engine.evolve.reflector import (EMPTY_SUMMARY, build_prompts, finalize, normalize, reflect,
                                     select_failures, usable_feedback)
from evolve_support import FIXTURE_INITIAL, MockLLM, change, example, make_config, reply

RUN = example("run_report.run1.json")
SESSIONS = {s["visitor_id"]: s for s in (example(f"session.A-00{i}.json") for i in (1, 2, 3))}
GOOD = reply(
    [change("questioning_strategy", "来访提到打鼾且没填 STOP-Bang 时，先调用 screen_osa。")],
    [change("path_discrimination", "在床外容易困、回床后清醒时，优先考虑 P2。", self_level="low")],
    [change("plan_rules", "处方先固定起床时间，再讨论上床时间。", self_level="low")],
)


def run(coro):
    return asyncio.run(coro)


def _reflect(config, primary=None, fallback=None, feedback=()):
    return run(reflect(playbook_text=FIXTURE_INITIAL.read_text(encoding="utf-8"), version="v1", run_report=RUN,
                       sessions=SESSIONS, feedback=list(feedback), config=config,
                       primary=primary, fallback=fallback))


def test_three_candidates_with_ids_and_criticality(tmp_path):
    result = _reflect(make_config(tmp_path), primary=MockLLM(GOOD, model="claude-opus-5-5"))
    assert result.model == "claude-opus-5-5" and not result.fell_back and result.fallback_reason is None
    assert [c["id"] for c in result.candidates] == ["c1", "c2", "c3"]
    path_change = result.candidates[1]["changes"][0]
    assert path_change["id"] == "c2-path_discrimination-1"
    assert (path_change["criticality_rule"], path_change["criticality_self"], path_change["criticality"]) == ("medium", "low", "medium")
    assert result.candidates[2]["changes"][0]["criticality"] == "high"


def test_failures_selected_by_priority_and_crisis_excluded(tmp_path):
    config = make_config(tmp_path)
    rows = select_failures(RUN, config)
    assert rows, "run1 example has failures"
    assert all(set(r["failure_tags"]) - {"crisis_missed"} for r in rows)
    # round-robin across dimensions: the first picks come from different dimensions
    from engine.evolve.dimensions import classify
    first_dims = [set(classify(r, None, config)) for r in rows[:3]]
    assert len(set.union(*first_dims)) >= 2


def test_prompt_contains_playbook_failures_and_fewshot_placeholder(tmp_path):
    config = make_config(tmp_path)
    feedback = example("evolution.v1-v2.json")["human_feedback"]
    system, user = build_prompts(playbook_text=FIXTURE_INITIAL.read_text(encoding="utf-8"), version="v1", run_report=RUN,
                                 failures=select_failures(RUN, config), sessions=SESSIONS, feedback=feedback,
                                 config=config)
    assert "{{" not in system + user
    assert "## plan_rules" in user and "（暂无）" in user
    approved = [f["text"] for f in usable_feedback(feedback)]
    rejected = [f["text"] for f in feedback if f["status"] == "rejected"]
    assert all(t in user for t in approved) and not any(t in user for t in rejected)


@pytest.mark.parametrize("primary", [
    MockLLM(error=RuntimeError("503")),
    MockLLM("这不是 JSON"),
    MockLLM({"candidates": [{"summary": "x", "changes": [{"op": "rename"}]}]}),
])
def test_falls_back_to_ds_flash(tmp_path, primary):
    fallback = MockLLM(GOOD, model="ds-flash")
    result = _reflect(make_config(tmp_path), primary=primary, fallback=fallback)
    assert result.model == "ds-flash" and result.fell_back and result.fallback_reason
    assert len(result.candidates) == 3 and all(c["changes"] for c in result.candidates)


def test_primary_timeout_falls_back(tmp_path):
    config = make_config(tmp_path, reflector={"primary_timeout_s": 0.01})
    result = _reflect(config, primary=MockLLM(GOOD, delay=1.0), fallback=MockLLM(GOOD, model="ds-flash"))
    assert result.fell_back and "超时" in result.fallback_reason


def test_both_fail_yields_three_empty_candidates(tmp_path):
    result = _reflect(make_config(tmp_path), primary=MockLLM(error=RuntimeError("x")),
                      fallback=MockLLM(error=RuntimeError("y")))
    assert result.fell_back and "降级模型也失败" in result.fallback_reason
    assert [c["summary"] for c in result.candidates] == [EMPTY_SUMMARY] * 3
    assert all(c["changes"] == [] for c in result.candidates)


def test_no_primary_configured_uses_fallback(tmp_path):
    result = _reflect(make_config(tmp_path), fallback=MockLLM(GOOD, model="ds-flash"))
    assert result.fell_back and result.model == "ds-flash"


def test_normalize_drops_invalid_and_caps(tmp_path):
    config = make_config(tmp_path, reflector={"max_changes_per_candidate": 2, "max_change_chars": 20})
    dropped = []
    data = {"candidates": [
        {"summary": "a", "changes": [
            change("questioning_strategy", "问作息", before="不该有"),          # add: before forced to None
            {"op": "add", "section": "crisis_rules", "after": "x"},          # bad section
            change("communication_style", "很长" * 20),                        # too long
            {"op": "modify", "section": "plan_rules", "before": None, "after": "x"},  # modify w/o before
            change("path_discrimination", "问床外困意"),
            change("referral_rules", "第三条超过上限"),
        ]},
        {"summary": "b", "changes": [{"op": "delete", "section": "plan_rules", "before": "处方从固定起床时间开始。",
                                      "after": "应被清空", "reason": "r", "criticality_self": "bogus"}]},
    ]}
    out = normalize(data, config, dropped)
    assert len(out[0]["changes"]) == 2 and out[0]["changes"][0]["before"] is None
    delete = out[1]["changes"][0]
    assert delete["after"] is None and delete["criticality_self"] == "high"
    assert len(dropped) == 4
    assert out[0]["changes"][1]["dimension"] == "path"          # inferred from path_discrimination
    assert len(finalize(out)) == 3


def test_dimension_field_validated_and_safety_dropped(tmp_path):
    config = make_config(tmp_path)
    data = {"candidates": [{"summary": "a", "changes": [
        {**change("questioning_strategy", "补筛规则"), "dimension": "screening"},
        {**change("communication_style", "先共情"), "dimension": "bogus"},
        {**change("questioning_strategy", "改安全"), "dimension": "safety"},
    ]}]}
    dropped = []
    out = normalize(data, config, dropped)
    assert [c["dimension"] for c in out[0]["changes"]] == ["screening", "resistance"]
    assert len(dropped) == 1


def test_prompt_has_scorecard_dimensions_and_evidence(tmp_path):
    config = make_config(tmp_path)
    visitors = {v["id"]: v for v in (example(f"visitor.A-00{i}.json") for i in (1, 2, 3))}
    failures = select_failures(RUN, config, visitors)
    system, user = build_prompts(playbook_text=FIXTURE_INITIAL.read_text(encoding="utf-8"), version="v1", run_report=RUN,
                                 failures=failures, sessions=SESSIONS, feedback=[], config=config, visitors=visitors)
    assert "策略生成" in system and "dimension" in system
    assert "分维度指标卡" in user and "安全（红线，不可改）" in user and "失败维度" in user
    assert "分类器证据" in user


def test_load_traces_s3_layout(tmp_path):
    import json
    from engine.evolve.reflector import load_traces
    (tmp_path / "sessions").mkdir()
    (tmp_path / "trace").mkdir()
    (tmp_path / "trace" / "A-001.json").write_text(json.dumps({"path_probs": []}), encoding="utf-8")
    report = {"per_visitor": [{"visitor_id": "A-001", "session_ref": "sessions/A-001.json"},
                              {"visitor_id": "A-002", "session_ref": "sessions/A-002.json"}]}
    assert set(load_traces(report, tmp_path)) == {"A-001"}
