"""PR #6 review counterexamples; independent of the frozen evaluation set."""
import asyncio

import httpx
from safety.judges import JudgeResult, StartLuxJudge
from safety.layer import SafetyLayer, SessionSafetyState


class FixedJudge:
    def __init__(self, label="passive", status="ok"):
        self.label, self.status, self.calls = label, status, 0

    async def classify(self, text):
        self.calls += 1
        return JudgeResult({k: float(k == self.label) for k in ("none", "history", "passive", "active")}
                           if self.status == "ok" else None, self.status, "offline", 0.)


def test_s4_startlux_27_second_reply_survives_layer_timeout():
    async def handler(request):
        await asyncio.sleep(2.7)
        return httpx.Response(200, json={"answers": {"risk": {
            "type": "choice", "choice": "active", "confidence": 1.,
            "probabilities": {"none": 0., "history": 0., "passive": 0., "active": 1.},
        }}})
    config = {"judge_timeout_s": 2.5}
    judge = StartLuxJudge(config, transport=httpx.MockTransport(handler))
    assert judge.timeout == 8.
    event = asyncio.run(SafetyLayer(config, judge=judge).assess_text(
        "最近早醒", 1, 1, SessionSafetyState()))
    assert event is not None
    assert (event.level, event.judge_status, event.judge_provider) == ("active", "ok", "startlux")


def test_s4_layer_allows_sum_of_chain_budgets():
    from safety.judges import ChainJudge

    class DelayedJudge(FixedJudge):
        def __init__(self, timeout, delay, status):
            super().__init__("active", status)
            self.timeout, self.delay = timeout, delay

        async def classify(self, text):
            await asyncio.sleep(self.delay)
            return await super().classify(text)

    primary, fallback = DelayedJudge(.15, 1, "error"), DelayedJudge(.3, .2, "ok")
    chain = ChainJudge(primary, [fallback])
    state = SessionSafetyState()
    event = asyncio.run(SafetyLayer({"judge_timeout_s": .05}, judge=chain).assess_text("最近早醒", 1, 1, state))
    assert event is not None and (event.level, event.judge_status) == ("active", "ok")
    assert [r.status for r in state.judge_results] == ["timeout", "ok"]
