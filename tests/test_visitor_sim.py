import asyncio
import copy

from sim.samples import build_all
from sim.screening import phq9_items, run_tool
from sim.topics import classify_topics
from sim.visitor_sim import SimVisitor

VISITORS = {v['id']: v for v in build_all()}


def run(coro):
    return asyncio.run(coro)


def with_defensiveness(vid, level):
    v = copy.deepcopy(VISITORS[vid])
    v['persona']['defensiveness'] = level
    return v


def test_deny_first_only_when_defensive():
    # sample-005: screen_in_bed 线索 deny_first=True，defensiveness=mid
    sim = SimVisitor(VISITORS['sample-005'])
    first = run(sim.respond('x', ['screen_in_bed']))
    assert first.revealed_clue_ids == [] and first.denied_clue_ids == ['sample-005-c1']
    second = run(sim.respond('x', ['screen_in_bed']))
    assert second.revealed_clue_ids == ['sample-005-c1']
    low = SimVisitor(with_defensiveness('sample-005', 'low'))
    assert run(low.respond('x', ['screen_in_bed'])).revealed_clue_ids == ['sample-005-c1']


def test_reveal_once_and_only_on_topic():
    sim = SimVisitor(VISITORS['sample-001'])
    assert run(sim.respond('x', ['mood'])).revealed_clue_ids == []
    assert run(sim.respond('x', ['weekend_catchup'])).revealed_clue_ids == ['sample-001-c1']
    assert run(sim.respond('x', ['weekend_catchup'])).revealed_clue_ids == []


def test_mock_text_contains_clue_and_schedule():
    sim = SimVisitor(VISITORS['sample-004'])
    reply = run(sim.respond('x', ['schedule_regularity']))
    assert '上床' in reply.text and reply.renderer == 'mock'


class FakeClient:
    model = 'fake-ds'

    def __init__(self, text):
        self.text, self.last_error, self.calls = text, None, 0

    async def complete(self, system, user, max_tokens=300):
        self.calls += 1
        if self.text is None:
            self.last_error = 'boom'
        return self.text


def test_llm_wording_does_not_change_reveal():
    client = FakeClient('随便说点什么')
    sim = SimVisitor(VISITORS['sample-001'], client)
    reply = run(sim.respond('x', ['weekend_catchup']))
    assert reply.text == '随便说点什么' and reply.renderer == 'fake-ds'
    assert reply.revealed_clue_ids == ['sample-001-c1']


def test_llm_failure_falls_back_to_mock():
    sim = SimVisitor(VISITORS['sample-001'], FakeClient(None))
    reply = run(sim.respond('x', ['weekend_catchup']))
    assert reply.renderer == 'mock' and reply.fallback_reason == 'boom'
    assert VISITORS['sample-001']['clues'][0]['content'] in reply.text


def test_topic_fallback_classifier():
    sim = SimVisitor(VISITORS['sample-015'])
    reply = run(sim.respond('周末一般几点起？'))
    assert 'weekend_catchup' in reply.asked_topics
    assert reply.revealed_clue_ids == ['sample-015-c4']
    assert 'screen_in_bed' in classify_topics('睡前会刷手机吗')


def test_screening_from_hidden_indices():
    for v in VISITORS.values():
        mood = run_tool('screen_mood', v)
        assert sum(mood['phq9_items']) == mood['phq9'] == v['indices']['phq9']
        assert mood['phq9_items'][8] == v['crisis']['phq9_item9']
        assert mood['gad7'] == v['indices']['gad7']
        assert run_tool('screen_osa', v) == {'stop_bang': v['indices']['stop_bang']}
    assert phq9_items(27, 3) == [3] * 9
