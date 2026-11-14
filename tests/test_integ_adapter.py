import asyncio
from copy import deepcopy

from engine.adapters_sim import S2OutcomeModel, S2Screening, S2VisitorSim, run_session
from engine.integ_trial import Meter, distribution
from contracts.validate import load_validators, validate_document
from scoring.smoke import load_visitors
from sim.screening import run_tool
from sim.state_model import simulate
from sim.visitor_sim import SimVisitor


def test_s2_state_survives_round_change_and_does_not_leak_across_visitors():
    visitor = deepcopy(load_visitors(n=10)[4])
    visitor["persona"]["defensiveness"] = "high"
    visitor["clues"] = [{"id": "test-clue", "reveal_topic": "screen_in_bed",
                         "supports": "P5", "content": "每天刷手机三个小时。", "deny_first": True}]
    adapter = S2VisitorSim()
    memory = {}

    async def run():
        assert (await adapter.reply(visitor, 1, [], memory)).text == visitor["opening_complaint"]
        transcript = [{"speaker": "agent", "text": "睡前会刷手机吗？"}]
        first = await adapter.reply(visitor, 1, transcript, memory)
        second = await adapter.reply(visitor, 2, transcript, memory)
        assert first.revealed_clue_ids == []
        assert second.revealed_clue_ids == ["test-clue"]
        other = await adapter.reply(visitor, 1, transcript, {})
        assert other.revealed_clue_ids == []
    asyncio.run(run())


def test_history_check_uses_spoken_safety_text_and_returns_current_status():
    visitor = load_visitors(n=7)[6]
    adapter = S2VisitorSim()
    memory = {}
    async def run():
        await adapter.reply(visitor, 1, [], memory)
        sim = memory["_s2_sim"]
        sim.revealed.update(c["id"] for c in visitor["clues"] if c["supports"] == "crisis")
        reply = await adapter.reply(visitor, 1, [
            {"speaker": "visitor", "text": "过去有过。"},
            {"speaker": "agent", "text": "嗯。"},
            {"speaker": "safety", "text": "现在还有这种念头吗？"}], memory)
        assert reply.asked_topics == ["self_harm"]
        assert "现在没有了" in reply.text
    asyncio.run(run())


def test_outcome_uses_round1_referral_not_empty_round2_and_does_not_mutate():
    visitor = next(v for v in load_visitors(n=10) if v["referral"] != "R0")
    plan = {"components": ["sleep_hygiene", "fixed_risetime"], "tib_minutes": 480,
            "rationale_given": True}
    context = {"session": {"plan": None, "behaviors": {},
                          "rounds": [{"round": 1, "referral_pred": visitor["referral"]},
                                     {"round": 2, "referral_pred": "R0"}]}}
    saved = deepcopy(context)
    result = S2OutcomeModel().simulate(visitor, plan, context)
    expected = simulate(visitor, {**context["session"], "plan": plan,
                                 "rounds": context["session"]["rounds"][:1]})
    assert result["isi_week"] == expected.isi_week
    assert result["effect"] == expected.effect
    assert result["isi_change"] == expected.isi_week[-1] - expected.isi_week[0]
    assert context == saved


def test_screening_and_ten_sessions_obey_contracts():
    validators = load_validators()
    visitors = load_visitors(n=10)
    async def run():
        for visitor in visitors:
            for tool in ("screen_mood", "screen_osa"):
                assert S2Screening().screen(visitor, tool) == run_tool(tool, visitor)
        sessions = await asyncio.gather(*(run_session(v, SimVisitor(v), run_id="test-integ",
                                                       playbook_version="v1") for v in visitors))
        for session in sessions:
            assert session["status"] != "error"
            assert validate_document(session, "session", validators, {v["id"]: v for v in visitors}) == []
    asyncio.run(run())


def test_meter_keeps_cancelled_calls_and_nearest_rank_percentiles():
    class Client:
        async def call(self):
            raise asyncio.CancelledError
    client, meter = Client(), Meter()
    meter.wrap(client, "call", "classifier")
    async def run():
        try:
            await client.call()
        except asyncio.CancelledError:
            pass
    asyncio.run(run())
    assert meter.calls[0]["status"] == "cancelled"
    assert distribution(list(range(1, 11)))["p95"] == 10


def test_trial_uses_engine_accounting_to_exclude_error_sessions(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    from engine.integ_trial import trial
    from engine.session import SessionRunner
    original = SessionRunner.run
    async def with_error(self):
        session, trace = await original(self)
        if self.visitor['id'] == 'sample-001':
            session.update(status='error', error='synthetic test failure', plan=None)
            trace.update(status='error', completed=False, error_count=1)
        return session, trace
    monkeypatch.setattr(SessionRunner, 'run', with_error)
    out = tmp_path / 'trial'
    args = SimpleNamespace(mock=True, run_id=str(out), n=3, merged=True, config=None)
    assert asyncio.run(trial(args)) == 1
    summary = json.loads((out / 'summary.json').read_text())
    report = json.loads((out / 'run_report.json').read_text())
    assert summary['http_attempts'] == 0
    assert summary['accounting']['attempted'] == 3
    assert summary['accounting']['scored'] == report['n_visitors'] == 2
    assert summary['accounting']['excluded'] == [{'visitor_id': 'sample-001', 'reason': 'session_error'}]
    assert summary['validation_errors'] == {}
