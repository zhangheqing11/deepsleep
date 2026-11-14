"""Adapter contract tests without installing S2 into this S3-only branch."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace

from engine.adapters_sim import S2OutcomeModel, S2VisitorSim


class Sim:
    model_name = 'test-s2'
    def __init__(self, visitor, client=None):
        self.visitor = visitor
        self.n = 0
        self.prompts = []
    def opening(self):
        return self.reply('opening', [])
    def reply(self, text, topics):
        return SimpleNamespace(text=text, asked_topics=topics, revealed_clue_ids=[], denied_clue_ids=[],
                               renderer='mock', fallback_reason=None)
    async def respond(self, prompt, *, asked_topics):
        self.n += 1
        self.prompts.append(prompt)
        return self.reply(str(self.n), asked_topics)


def test_sim_state_isolated_per_session_and_survives_rounds():
    adapter = S2VisitorSim(factory=Sim)
    a, b = {}, {}
    async def check():
        assert (await adapter.reply({'id': 'a'}, 1, [], a)).text == 'opening'
        transcript = [{'speaker': 'visitor', 'text': '过去有过'},
                      {'speaker': 'agent', 'text': '嗯'},
                      {'speaker': 'safety', 'text': '现在还有这种念头吗？'}]
        first = await adapter.reply({'id': 'a'}, 1, transcript, a)
        second = await adapter.reply({'id': 'a'}, 2, transcript, a)
        other = await adapter.reply({'id': 'b'}, 1, transcript, b)
        assert (first.text, second.text, other.text) == ('1', '2', '1')
        assert first.asked_topics == ['self_harm']
        assert a['_s2_sim'].prompts == ['嗯\n现在还有这种念头吗？'] * 2
    asyncio.run(check())


def test_sim_rejects_instance_owned_by_another_visitor():
    import pytest
    adapter = S2VisitorSim(instance=Sim({'id': 'a'}))
    with pytest.raises(ValueError, match='another visitor'):
        asyncio.run(adapter.reply({'id': 'b'}, 1, [], {}))


def test_outcome_strips_round2_placeholder_and_preserves_inputs():
    context = {'session': {'rounds': [{'round': 1, 'referral_pred': 'R1'},
                                    {'round': 2, 'referral_pred': 'R0'}], 'plan': None}}
    plan = {'tib_minutes': 450}
    saved = deepcopy(context)
    def simulate(visitor, session):
        assert session['rounds'] == saved['session']['rounds'][:1]
        assert session['plan'] == plan
        session['plan']['tib_minutes'] = 1
        return SimpleNamespace(to_dict=lambda: {'isi_week': [20, 18, 16, 14, 12], 'adherence': .8})
    result = S2OutcomeModel(simulate).simulate({}, plan, context)
    assert result['isi_change'] == -8 and result['responder'] is True
    assert context == saved and plan['tib_minutes'] == 450
