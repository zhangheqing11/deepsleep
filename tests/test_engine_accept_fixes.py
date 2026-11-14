"""Offline replay of acceptance evidence; no dependency on the original var/ tree."""
import asyncio
import copy
import json
from pathlib import Path

import pytest

from domain.vetoes import check_plan
from engine.classifier import make_state
from engine.reporting import summarize
from engine.session import SessionRunner, _Round
from test_engine_session import ScriptedLLM, ScriptedSim, deps_for, visitor

EVIDENCE = json.loads((Path(__file__).parent / 'fixtures/accept/regressions.json').read_text())


def replay_runner(case):
    raw = {**copy.deepcopy(case['prescription']), 'contraindications_identified': [], 'age': None}
    llm = ScriptedLLM(plan=lambda *_: copy.deepcopy(raw))
    runner = SessionRunner(deps_for(llm=llm), visitor(), 'accept-regression')
    runner.rounds = [_Round(n) for n in range(1, case['round'] + 1)]
    runner.entries = copy.deepcopy(case['entries'])
    runner.memory = {int(k): v for k, v in copy.deepcopy(case['memory']).items()}
    return runner, llm


@pytest.mark.parametrize('index,baseline', [(0, 600), (1, 470)])
def test_unlabelled_restriction_is_vetoed_rewritten_and_remediated(index, baseline):
    case = EVIDENCE['cases'][index]
    # Original component-only rule accepts both recorded prescriptions.
    assert check_plan(case['prescription']['plan'], []) == []
    runner, llm = replay_runner(case)
    asyncio.run(runner._make_plan(case['round']))
    vetoes = runner.trace['vetoes']
    assert any(v['field'] == 'contraindications_checked' for v in vetoes[0]['violations'])
    assert llm.tasks() == ['plan', 'plan']
    assert '未通过固定规则检查' in llm.calls[1][1][-1]['content']
    assert vetoes[-1]['stage'] == 'plan_remediated' and vetoes[-1]['violations'] == []
    result = runner.plans[case['round']]
    assert result['plan']['tib_minutes'] == baseline
    assert 'sleep_restriction' not in result['plan']['components']
    # Neither the old schedule cards nor the unsafe closing advice may survive.
    assert result['closing_message'] == '' and result['plan']['cards'] == []


def test_closing_reply_is_seen_by_final_classifier_without_extra_agent_calls():
    case = EVIDENCE['cases'][2]
    runner, llm = replay_runner(case)
    runner.turn = 6
    runner.current.transcript = [dict(e) for e in case['entries'] if e['round'] == 2]
    reply = case['closing_turns'][1]['text']
    runner.deps.sim = ScriptedSim([reply])

    class Classifier:
        provider = 'scripted'
        calls = []
        async def classify(self, dialogue):
            self.calls.append(copy.deepcopy(dialogue))
            top = 'P5' if any(e['speaker'] == 'visitor' and e['text'] == reply for e in dialogue) else 'P2'
            return make_state({p: int(p == top) for p in ('P1', 'P2', 'P3', 'P4', 'P5')},
                              'cooperative', 'ok', self.provider, 0)

    classifier = Classifier()
    runner.deps.classifier = classifier
    asyncio.run(runner._close_round())
    assert runner.current.path_pred == 'P5'
    assert len(classifier.calls) == 2 and classifier.calls[-1][-1]['text'] == reply
    assert llm.tasks() == ['memory', 'plan']
    assert runner.turn == 8
    finals = [p for p in runner.trace['path_probs'] if p['final']]
    assert len(finals) == 1 and finals[0]['path_pred'] == 'P5'


def test_original_run_provider_switches_are_separate_from_deterministic_fallbacks():
    results = [({'status': 'completed', 'safety_events': []}, t) for t in EVIDENCE['accounting']]
    summary = summarize(results)
    assert summary['provider_switches'] == 8
    assert summary['degraded_sessions'] == 0


@pytest.mark.parametrize('bedtime,expected', [('23:09', False), ('23:10', True), ('00:10', True)])
def test_schedule_threshold_uses_clock_times_not_claimed_tib(bedtime, expected):
    from engine.plan_postprocess import annotate_restriction
    plan = copy.deepcopy(EVIDENCE['cases'][1]['prescription']['plan'])
    plan.update(bedtime=bedtime, tib_minutes=470, cards=[])
    evidence = annotate_restriction(plan, {'closing_message': ''},
        [{'speaker': 'visitor', 'text': '22:40上床，06:30起床。', 'round': 1, 'turn': 1}], {})
    assert ('sleep_restriction' in plan['components']) == expected
    assert evidence['baseline_minutes'] == 470


@pytest.mark.parametrize('text,expected', [
    ('建议缩短卧床时间。', True), ('减少在床时间。', True),
    ('把十小时卧床缩到七小时左右。', True), ('把卧床时间压到七小时。', True),
    ('这一周先不缩短卧床时间。', False), ('暂不压缩卧床时间。', False),
    ('先不减少在床时间，但建议缩短卧床时间。', True),
    ('下轮再决定要不要压缩卧床时间。', False),
    ('躺下20分钟仍清醒就起身，困了再回床。', False),
])
def test_explicit_restriction_and_scoped_negation(text, expected):
    from engine.plan_postprocess import explicit_restriction
    assert explicit_restriction(text) == expected


def test_unknown_baseline_ignores_agent_proposals_and_logs_warning():
    from engine.plan_postprocess import annotate_restriction
    plan = copy.deepcopy(EVIDENCE['cases'][0]['prescription']['plan'])
    evidence = annotate_restriction(plan, {'closing_message': ''},
        [{'speaker': 'agent', 'text': '22:00上床，08:00起床。'}], {})
    assert evidence['warnings'] == ['tib_baseline_unknown']
    assert 'sleep_restriction' not in plan['components']


@pytest.mark.parametrize('text,minutes', [
    ('上床约22:40，起床约06:30', 470),
    ('通常23:40上床、07:30起床', 470),
    ('一晚上在床上快十个小时，实际睡不到六个小时', 600),
    ('夜间卧床近10小时，实际睡着不到6小时', 600),
    ('晚上九点半上床，早上六点半起来', 540),
    ('二十三点四十上床，早上七点半起床', 470),
    ('实际睡着不到6小时', None),
    ('九点半上床，六点半起来', None),
])
def test_disclosed_baseline_and_memory_only(text, minutes):
    from engine.plan_postprocess import disclosed_tib
    assert disclosed_tib([], {1: {'facts': [text]}})[0] == minutes
    assert disclosed_tib([{'speaker': 'visitor', 'text': text, 'round': 1, 'turn': 1}], {})[0] == minutes


def test_text_only_mismatch_is_vetoed_even_with_unknown_baseline():
    case = copy.deepcopy(EVIDENCE['cases'][1])
    case.update(entries=[], memory={})
    case['prescription']['closing_message'] = '建议减少在床时间。'
    runner, _ = replay_runner(case)
    asyncio.run(runner._make_plan(2))
    evidence = runner.trace['plan_postprocessing'][0]
    assert evidence['warnings'] == ['tib_baseline_unknown', 'sleep_restriction_inconsistent']
    assert any(v['field'] == 'contraindications_checked' for v in runner.trace['vetoes'][0]['violations'])
    assert runner.plans[2]['closing_message'] == ''


def test_known_contraindication_still_vetoes_inferred_component_after_check():
    case = copy.deepcopy(EVIDENCE['cases'][1])
    runner, llm = replay_runner(case)
    runner.current.topics.append('health_conditions')
    original = llm.plan
    def contraindicated(*args):
        return {**original(*args), 'contraindications_identified': ['epilepsy']}
    llm.plan = contraindicated
    asyncio.run(runner._make_plan(2))
    assert any(v['field'] == 'components' for v in runner.trace['vetoes'][0]['violations'])
    assert runner.plans[2]['plan']['tib_minutes'] == 470


def test_checked_without_contraindications_keeps_inferred_restriction():
    case = EVIDENCE['cases'][1]
    runner, llm = replay_runner(case)
    runner.current.topics.append('health_conditions')
    asyncio.run(runner._make_plan(2))
    assert llm.tasks() == ['plan']
    assert 'sleep_restriction' in runner.plans[2]['plan']['components']
    assert runner.plans[2]['plan']['tib_minutes'] == 430


def test_provider_switch_count_does_not_count_cache_or_return_to_primary():
    trace = dict(llm_calls=[
        {'agent': 'classifier', 'status': 'cancelled', 'provider_switches': 1, 'discarded': True},
        {'agent': 'classifier', 'status': 'ok', 'provider': 'mock(fallback)'},
        {'agent': 'classifier', 'status': 'ok', 'provider': 'ds_flash(fallback:jev_unavailable)'},
    ], all_judge_results=[
        {'provider': 'ds_flash', 'status': 'timeout'}, {'provider': 'jev', 'status': 'error'},
        {'provider': 'ds_flash', 'status': 'ok'},
    ], path_probs=[{'provider': 'ds_flash(fallback:jev_error)'}] * 5,
       fallbacks=[{'task': 'plan', 'discarded': False}])
    summary = summarize([({'status': 'completed', 'safety_events': []}, trace)])
    assert summary['provider_switches'] == 2
    assert summary['degraded_sessions'] == 1


def test_baseline_can_be_disclosed_in_separate_replies_or_memory_facts():
    from engine.plan_postprocess import disclosed_tib
    entries = [
        {'speaker': 'visitor', 'text': '22:40上床，06:30起床。', 'round': 1, 'turn': 1},
        {'speaker': 'visitor', 'text': '现在改成23:00上床。', 'round': 2, 'turn': 2},
        {'speaker': 'visitor', 'text': '07:00起床。', 'round': 2, 'turn': 4},
    ]
    assert disclosed_tib(entries, {})[0] == 480
    assert disclosed_tib([], {1: {'facts': ['22:40上床', '06:30起床']}})[0] == 470


def test_no_closing_reply_does_not_add_classifier_or_agent_calls():
    runner, llm = replay_runner(EVIDENCE['cases'][1])
    async def empty_plan(number, **kwargs):
        runner.plans[number] = {'plan': {}, 'closing_message': ''}
    runner._make_plan = empty_plan
    asyncio.run(runner._close_round())
    assert len([c for c in runner.trace['llm_calls'] if c['agent'] == 'classifier']) == 1
    assert llm.tasks() == ['memory']


def test_successful_rewrite_rechecks_the_new_candidate():
    runner, llm = replay_runner(EVIDENCE['cases'][1])
    original = llm.plan
    def rewrite(state, messages):
        result = original(state, messages)
        if '未通过固定规则检查' in messages[-1]['content']:
            result['plan'].update(bedtime='22:40', tib_minutes=470, cards=[])
            result['closing_message'] = '先不缩短卧床时间。'
        return result
    llm.plan = rewrite
    asyncio.run(runner._make_plan(2))
    assert llm.tasks() == ['plan', 'plan']
    assert len(runner.trace['vetoes']) == 2
    assert runner.trace['vetoes'][1]['violations'] == []
    assert 'sleep_restriction' not in runner.plans[2]['plan']['components']
    assert runner.plans[2]['closing_message'] == '先不缩短卧床时间。'
