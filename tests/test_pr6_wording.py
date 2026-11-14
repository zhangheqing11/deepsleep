"""All 26 review probes plus candidate-prohibition scope counterexamples."""
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


@pytest.mark.parametrize("text,expected", PROBES, ids=[f"probe-{n:02d}" for n in range(1,27)])
def test_s5_s6_all_26_review_probes(text, expected):
    if expected == "candidate_exempt":
        violations = check_text(text, context="candidate_playbook")
        assert not [v for v in violations if v.severity == "hard"]
        assert any(v.severity == "hard" for v in check_text(text))
    else:
        violations = check_text(text)
        actual = "hard" if any(v.severity == "hard" for v in violations) else "soft" if violations else "none"
        assert actual == expected


@pytest.mark.parametrize("text", [
    "这不是诊断。", "我可以确诊。", "为你治疗失眠症。",
    "不要谈别的，诊断为失眠症。", "禁止说诊断。可以治疗失眠症。",
    "不要说诊断，但可以说治疗失眠症。",
    "不要说诊断；诊断为失眠症。",
    "不要说诊断\n诊断为失眠症。",
    "不要担心，我可以诊断。",
    "不要说诊断而要说治疗失眠症。",
])
def test_s6_candidate_does_not_exempt_assertions_or_other_clauses(text):
    for context in ("user_facing", "candidate_playbook"):
        assert any(v.severity == "hard" for v in check_text(text, context=context))


@pytest.mark.parametrize("text", [
    "不要对来访说诊断为失眠症。", "禁止说治疗失眠症。",
    "不要说“诊断”或“治疗失眠症”。", "禁止使用：诊断、治疗失眠症。",
    "不要對來訪說診斷為失眠症。",
])
def test_s6_only_candidate_prohibition_lists_are_exempt(text):
    assert not any(v.severity == "hard" for v in check_text(text, context="candidate_playbook"))
    assert any(v.severity == "hard" for v in check_text(text, context="user_facing"))


@pytest.mark.parametrize("text", ["ＤＩＡＧＮＯＳＩＳ", "treatment for insomnia", "诊\n断", "確診", "誤診", "醫治失眠症"])
def test_s5_normalization_and_existing_english_rules(text):
    assert any(v.severity == "hard" for v in check_text(text))


def test_s6_unknown_context_rejected():
    with pytest.raises(ValueError, match="context"):
        check_text("诊断", context="typo")
