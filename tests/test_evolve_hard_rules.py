import pytest

from engine.evolve.hard_rules import check_candidate, durations_in_minutes, veto_from_violations
from evolve_support import FIXTURE_V0, make_config

V0 = FIXTURE_V0.read_text(encoding="utf-8")


def ch(after, section="plan_rules", op="add", before=None, cid="c1-x-1"):
    return {"id": cid, "op": op, "section": section, "before": before, "after": after}


def codes(changes, tmp_path):
    return [v["code"] for v in check_candidate(changes, V0, make_config(tmp_path))]


@pytest.mark.parametrize("after, expected", [
    ("即使存在未处理的呼吸暂停风险，也统一安排五小时卧床窗口。", "contraindication_violation"),  # contract example c1
    ("卧床时间设为 5 小时。", "contraindication_violation"),
    ("睡眠窗口压缩到四个半小时。", "contraindication_violation"),
    ("可以跳过禁忌检查直接开始睡眠限制。", "contraindication_violation"),
    ("建议睡前服用褪黑素。", "forbidden_wording"),
    ("根据线索给出诊断。", "forbidden_wording"),
    ("这套方法可以治疗失眠症。", "forbidden_wording"),
    ("来访提到轻生念头时继续聊作息。", "crisis_scope"),
])
def test_blocked(after, expected, tmp_path):
    assert expected in codes([ch(after)], tmp_path)


@pytest.mark.parametrize("after", [
    "在床上清醒超过 20 分钟就离床，困了再回来。",
    "卧床时间不少于 6 小时。",
    "卧床时间设为 5.5 小时。",
    "每周按睡眠效率调整卧床时间，每次只减少 15 分钟。",
    "起床后 1 小时内到户外见光。",
    "不建议自行服用安眠药，有需要请咨询医生。",
    "建议睡眠限制前先确认禁忌情形。",
])
def test_allowed(after, tmp_path):
    assert codes([ch(after)], tmp_path) == []


def test_soft_wording_stays_out_of_contract(tmp_path):
    assert codes([ch("这是一种非药物的改善方式，不同于治疗。", section="communication_style")], tmp_path) == []


def test_locked_line_cannot_be_modified_or_deleted(tmp_path):
    locked = "建议睡眠限制前必须先检查禁忌情形。"
    assert codes([ch("改写", op="modify", before=locked)], tmp_path) == ["locked_rule"]
    assert codes([ch(None, op="delete", before=locked)], tmp_path) == ["locked_rule"]
    assert codes([ch("处方从固定起床时间和光照开始。", op="modify", before="处方从固定起床时间开始。")], tmp_path) == []


def test_deleting_crisis_text_is_also_out_of_scope(tmp_path):
    assert "crisis_scope" in codes([ch(None, op="delete", before="有自伤念头时转安全层")], tmp_path)


def test_violation_carries_change_id_and_maps_to_veto_enum(tmp_path):
    config = make_config(tmp_path)
    violations = check_candidate([ch("出现轻生念头时由 agent 自行判断。", cid="c2-plan_rules-1")], V0, config)
    assert violations[0]["change_id"] == "c2-plan_rules-1"
    veto = veto_from_violations(violations, config)
    assert veto["passed"] is False and veto["reasons"][0]["code"] == "crisis_missed"


def test_durations():
    assert durations_in_minutes("五小时") == [300]
    assert durations_in_minutes("四个半小时") == [270]
    assert durations_in_minutes("十二小时") == [720]
    assert durations_in_minutes("330 分钟、5.5h") == [330, 330]
