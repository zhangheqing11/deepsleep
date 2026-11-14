"""PR #6 review counterexamples; independent of the frozen evaluation set."""
import pytest
from safety.judges import MockJudge
from safety.layer import SafetyLayer


@pytest.mark.parametrize("text,expected", [
    ("现在你已经没有这种念头，今晚吃什么？", False),
    ("现在不用问你有没有自杀念头，我们聊睡眠好吗？", False),
    ("现在不用问你有没有自杀念头吗？", False),
    ("目前先不谈自伤好吗？", False),
    ("现在不讨论自伤好吗？", False),
    ("现在我们不需要确认有没有自杀念头吗？", False),
    ("最近你没有自杀念头。", False),
    ("现在怎么样，自伤的想法有吗？", False),
    ("现在有没有自伤念头", False),
    ("以前你有自伤念头吗？", False),
    ("现在你已经没有这种念头了吗？", True),
    ("你目前是否还有自伤的想法？", True),
    ("你最近有没有自杀念头？", True),
    ("你还有这样的念头吗？", True),
    ("自伤的念头现在还在吗?", True),
    ("仍有伤害自己的想法吗？", True),
])
def test_s3_verification_requires_one_current_risk_question_clause(text, expected):
    assert SafetyLayer(judge=MockJudge()).check_verification(text) is expected


