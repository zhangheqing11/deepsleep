import json
from pathlib import Path

import pytest

from domain.vetoes import check_plan, check_text


@pytest.mark.parametrize("condition", ["bipolar", "epilepsy", "untreated_osa", "pregnancy", "high_fall_risk", "drowsy_driving_job", "parasomnia"])
def test_restriction_blocked_for_each_contraindication(condition):
    plan = {"components": ["sleep_restriction"], "tib_minutes": 360, "contraindications_checked": True}
    violations = check_plan(plan, [condition])
    assert [(v.code, v.field) for v in violations] == [("contraindication_violation", "components")]


def test_plan_bounds_and_checks():
    plan = {"components": ["sleep_restriction"], "tib_minutes": 330, "contraindications_checked": True}
    assert check_plan(plan, []) == []
    assert check_plan(None, []) == []
    plan.update(tib_minutes=329, contraindications_checked=False)
    assert {v.field for v in check_plan(plan, [])} == {"tib_minutes", "contraindications_checked"}
    plan["components"] = ["sleep_hygiene"]
    assert {v.field for v in check_plan(plan, ["bipolar"])} == {"tib_minutes"}
    plan["tib_minutes"] = 330
    assert check_plan(plan, ["bipolar"]) == []


@pytest.mark.parametrize("text", ["为你诊断", "治疗失眠症", "建议服用安眠药", "增加安眠药剂量", "自行停药", "建议用药", "建议吃药", "建议服用药物", "睡前服用褪黑素"])
def test_forbidden_wording_and_medication(text):
    violations = check_text(text)
    assert violations
    common = json.loads((Path(__file__).resolve().parents[1] / "contracts/common.schema.json").read_text())
    codes = common["$defs"]["veto"]["properties"]["reasons"]["items"]["properties"]["code"]["enum"]
    assert all(v.code in codes and v.field == "text" for v in violations)


@pytest.mark.parametrize("text", ["建议就医，咨询医生。", "试着固定起床时间。", "请勿自行停药或增加剂量。", "不建议服用安眠药。"])
def test_safe_wording(text):
    assert check_text(text) == []


def test_negation_does_not_hide_later_medication_advice():
    assert check_text("不要自行停药。但建议服用安眠药。")
    assert check_text("不建议停药但可以增加安眠药剂量。")


def test_tib_threshold_is_configurable():
    plan = {"components": ["sleep_hygiene"], "tib_minutes": 350, "contraindications_checked": True}
    assert check_plan(plan, []) == []
    assert check_plan(plan, [], config={"min_tib_minutes": 360})[0].field == "tib_minutes"
