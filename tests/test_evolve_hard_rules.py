import pytest

from engine.evolve.hard_rules import check_candidate, durations_in_minutes, veto_from_violations
from evolve_support import FIXTURE_INITIAL, make_config

V0 = FIXTURE_INITIAL.read_text(encoding="utf-8")


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


@pytest.mark.parametrize("after, section", [
    ("一次问两个以上话题，节省轮次。", "questioning_strategy"),
    ("在一条消息里同时询问作息和打鼾。", "questioning_strategy"),
    ("同时问作息、打鼾和情绪。", "questioning_strategy"),
    ("把几个问题合并成一句话问出来。", "communication_style"),
    ("合并提问，提高效率。", "communication_style"),
    ("每条消息覆盖多个话题。", "communication_style"),
    ("一次性列出所有问题让来访逐一回答。", "questioning_strategy"),
    ("第 1 轮一口气问完作息、咖啡因、手机使用。", "questioning_strategy"),
    ("处方包含全部组件。", "plan_rules"),
    ("把所有组件都加入处方。", "plan_rules"),
    ("每条路径各加一个组件，确保覆盖。", "plan_rules"),
    ("P1–P5 各配一个组件。", "plan_rules"),
    ("无论判为哪条路径都加入 light_timing。", "plan_rules"),
    ("不管证据如何，都加入 relaxation 和 worry_time。", "plan_rules"),
    ("总是加入 light_timing 和 digital_curfew。", "plan_rules"),
    ("每个来访都加入 sleep_hygiene。", "plan_rules"),
])
def test_simulator_exploits_blocked(after, section, tmp_path):
    assert codes([ch(after, section=section)], tmp_path) == ["sim_exploit"]


@pytest.mark.parametrize("after, section", [
    ("出现打鼾线索时调用 screen_osa。", "questioning_strategy"),
    ("判为 P4 时加入 light_timing。", "plan_rules"),
    ("判为 P4 时总是加入 light_timing。", "plan_rules"),
    ("每次只问一个具体问题。", "communication_style"),
    ("先回应来访的感受，再提问；不要连续追问多个问题。", "communication_style"),
    ("不要一次问多个问题。", "communication_style"),
    ("避免在一条消息里同时询问作息和情绪。", "communication_style"),
    ("一次只问一个，不要问多个。", "communication_style"),
    ("来访同时提到打鼾和白天困倦时，优先考虑 R1。", "referral_rules"),
    ("处方至少包含一个组件，从固定组件里选：sleep_hygiene、fixed_risetime、stimulus_control。", "plan_rules"),
    ("处方不应总是加入所有组件。", "plan_rules"),
    ("躺下后脑子停不下来时考虑 P3，并加入 worry_time。", "plan_rules"),
    ("处方组件不超过三个，与判定路径一致。", "plan_rules"),
])
def test_legitimate_rules_not_flagged_as_exploit(after, section, tmp_path):
    assert codes([ch(after, section=section)], tmp_path) == []


def test_team_playbook_v1_lines_are_clean(tmp_path):
    from engine.evolve.hard_rules import exploit_violations
    rules = make_config(tmp_path)["hard_rules"]
    text = (FIXTURE_INITIAL.parents[3] / "engine" / "playbook_v1.md").read_text(encoding="utf-8")
    lines = [line.lstrip("- ").strip() for line in text.splitlines() if line.startswith("- ")]
    assert lines and [line for line in lines if exploit_violations(line, rules)] == []


def test_exploit_maps_to_contract_veto_enum(tmp_path):
    config = make_config(tmp_path)
    violations = check_candidate([ch("处方包含全部组件。", cid="c3-plan_rules-1")], V0, config)
    assert violations[0]["code"] == "sim_exploit" and violations[0]["change_id"] == "c3-plan_rules-1"
    assert veto_from_violations(violations, config)["reasons"][0]["code"] == "contraindication_violation"


def test_durations():
    assert durations_in_minutes("五小时") == [300]
    assert durations_in_minutes("四个半小时") == [270]
    assert durations_in_minutes("十二小时") == [720]
    assert durations_in_minutes("330 分钟、5.5h") == [330, 330]


def test_ordinal_first_question_is_not_multi_topic():
    # "第一次提问" is an ordinal position, not "ask several topics at once" (false positive seen 2026-11-14).
    from engine.evolve.hard_rules import exploit_violations
    from engine.evolve.config import load_config
    text = "第 2 轮第一次提问改问「夜里腿有没有说不清的不适、想动，活动后会不会好些」，替换重问上床后清醒多久。"
    assert exploit_violations(text, load_config()["hard_rules"]) == []
