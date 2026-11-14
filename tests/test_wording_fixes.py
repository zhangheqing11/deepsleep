"""The review's 26 probes, kept outside the frozen safety testset."""
import pytest
from domain.vetoes import check_text

PROBES = [
    ("为你诊断失眠症", "hard"),
    ("这不是诊断，只是建议。", "hard"),
    ("本工具不提供诊断。", "hard"),
    ("治疗失眠症", "hard"),
    ("治療失眠症", "hard"),
    ("為你診斷", "hard"),
    ("诊　断", "hard"),
    ("治　疗　失　眠　症", "hard"),
    ("医治失眠症", "hard"),
    ("治好失眠症", "hard"),
    ("彻底治好失眠症", "hard"),
    ("你患有焦虑症", "hard"),
    ("我确诊你患上了失眠障碍", "hard"),
    ("我可以确诊。", "hard"),
    ("这次是误诊。", "hard"),
    ("建议就医，接受专业评估。", "none"),
    ("试着固定起床时间。", "none"),
    ("不建议服用安眠药。", "none"),
    ("请勿自行停药或增加剂量。", "none"),
    ("不可以服用安眠药。", "none"),
    ("不要建议服用安眠药。", "none"),
    ("建议服用安眠药。", "hard"),
    ("医生会讨论治疗方案", "soft"),
    ("了解失眠症的知识", "soft"),
    ("不要对来访说诊断为失眠症。", "candidate_exempt"),
    ("禁止说治疗失眠症。", "candidate_exempt"),
]


def severity(violations):
    return "hard" if any(v.severity == "hard" for v in violations) else "soft" if violations else "none"


@pytest.mark.parametrize("text,expected", PROBES, ids=[f"probe-{i:02}" for i in range(1, 27)])
def test_s5_review_probes(text, expected):
    if expected == "candidate_exempt":
        assert severity(check_text(text, context="candidate_playbook")) == "none"
        assert severity(check_text(text)) == "hard"
    else:
        assert severity(check_text(text)) == expected


@pytest.mark.parametrize("context", ["user_facing", "candidate_playbook"])
@pytest.mark.parametrize("text", ["不是诊断", "我可以确诊。", "建议服用安眠药。", "禁止熬夜，给你诊断。", "不要说诊断。治疗失眠症。", "不要说诊断\n治疗失眠症。"])
def test_s6_candidate_exemption_is_local_and_not_general_negation(context, text):
    assert severity(check_text(text, context=context)) == "hard"


@pytest.mark.parametrize("prefix", ["不要", "禁止", "避免", "不得", "切勿"])
def test_s6_only_candidate_prohibition_is_exempt(prefix):
    text = prefix + "对来访说诊断为失眠症。"
    assert check_text(text, context="candidate_playbook") == []
    assert severity(check_text(text, context="user_facing")) == "hard"


@pytest.mark.parametrize("text", ["建议就医评估", "尝试固定起床时间"])
@pytest.mark.parametrize("context", ["user_facing", "candidate_playbook"])
def test_s6_safe_text(context, text):
    assert check_text(text, context=context) == []


@pytest.mark.parametrize("text", ["treatment for insomnia", "ｔｒｅａｔｍｅｎｔ　ｆｏｒ　ｉｎｓｏｍｎｉａ", "cure", "ｃｕｒｅ", "確　診", "誤診", "诊\n断", "醫治失眠症"])
def test_s5_normalization_preserves_english_and_variants(text):
    assert severity(check_text(text)) == "hard"


def test_s6_invalid_context_rejected():
    with pytest.raises(ValueError, match="context"):
        check_text("建议", context="candidate")


@pytest.mark.parametrize("text", ["- 不要对来访说诊断为失眠症。", "输出规则：禁止说治疗失眠症。", "在回答中避免说诊断为失眠症。"])
def test_s6_prohibition_list_with_prefix(text):
    assert check_text(text, context="candidate_playbook") == []
    assert severity(check_text(text)) == "hard"


def test_s6_contrast_and_medication_not_exempted():
    for text in ["禁止说诊断但可以治疗失眠症。", "禁止说诊断并建议服用安眠药。"]:
        assert severity(check_text(text, context="candidate_playbook")) == "hard"
