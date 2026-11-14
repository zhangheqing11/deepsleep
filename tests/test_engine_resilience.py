"""Regression coverage for the real ds-flash truncation and S3 accounting failures."""
import asyncio
import copy
import json
from types import SimpleNamespace

import pytest

from engine.classifier import make_state, uniform_state
from engine.config import load_config
from engine.llm import DsFlashClient, LLMError, parse_json_object
from engine.reporting import build_report, summarize
from engine.session import SessionRunner, _Round, _valid_plan
from engine.telemetry import CALL_SCOPE
from test_engine_session import (ScriptedLLM, ScriptedSim, assert_valid, deps_for, run,
                                 visitor, PASSIVE_TEXT, StubJudge, DEFAULT_LABELS)


def response(content, reason='stop'):
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason=reason,
        message=SimpleNamespace(content=content, reasoning_content=''))])


def client_for(replies):
    requests = []
    async def create(**kwargs):
        requests.append(kwargs)
        reply = replies[min(len(requests)-1, len(replies)-1)]
        if isinstance(reply, Exception):
            raise reply
        return reply
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return DsFlashClient(load_config()['agent_llm'], client=client), requests


@pytest.mark.parametrize('text', ['```json\n{"ok": true}\n```', '```JSON\r\n{"ok": true}\r\n```',
                                  '```\n{"ok": true}\n```', '{"ok": true}'])
def test_json_fences(text):
    assert parse_json_object(text) == {'ok': True}


def plan_runner(llm):
    runner = SessionRunner(deps_for(llm=llm), visitor(), 'truncation')
    runner.rounds.append(_Round(1))
    return runner


def test_length_retries_once_with_higher_budget_even_when_json_parses():
    from engine.mock_agent import MockAgentLLM
    plan = MockAgentLLM()._plan({'path_top': 'P1', 'referral': 'R0'})
    llm, requests = client_for([response(json.dumps(plan), 'length'), response(json.dumps(plan))])
    runner = plan_runner(llm)
    runner.deps.config['agent_llm']['max_retries'] = 0
    asyncio.run(runner._make_plan(1))
    assert [r['max_tokens'] for r in requests] == [3200, 6400]
    assert all(r['response_format'] == {'type': 'json_object'} for r in requests)
    calls = runner.trace['llm_calls']
    assert [(c['finish_reason'], c['truncated'], c['ok']) for c in calls] == [
        ('length', True, False), ('stop', False, True)]
    assert not runner.trace['fallbacks']


def test_repeated_length_stops_after_one_retry_and_uses_fixed_plan():
    llm, requests = client_for([response('{"plan":', 'length')])
    runner = plan_runner(llm)
    asyncio.run(runner._make_plan(1))
    assert len(requests) == 2
    assert runner.trace['fallbacks'][0]['task'] == 'plan'
    assert runner.plans[1]['plan']['tib_minutes'] == 450
    assert 'sleep_restriction' not in runner.plans[1]['plan']['components']
    assert 'fallback:plan' in runner._session('completed', None)['models']['agent']


@pytest.mark.parametrize('task', ['strategy', 'response', 'turn', 'memory', 'select', 'plan'])
def test_persistent_subagent_failure_degrades_without_losing_attempts(task):
    class BrokenTask(ScriptedLLM):
        async def complete_json(self, messages, *, task: str, state):
            if task == broken:
                raise LLMError('malformed output')
            return await super().complete_json(messages, task=task, state=state)
    broken = task
    deps = deps_for(llm=BrokenTask(), merged=task == 'turn')
    deps.config['round_turn_cap'] = {1: 1, 2: 1}
    session, trace = run(deps, visitor())
    assert session['status'] == 'completed'
    assert_valid(session, visitor())
    failures = [f for f in trace['fallbacks'] if f['task'] == task]
    calls = [c for c in trace['llm_calls'] if c['task'] == task]
    assert failures and len(calls) == sum(f['attempts'] for f in failures)
    assert all(c['status'] == 'error' and not c['ok'] for c in calls)
    assert f'fallback:{task}' in session['models']['agent']


def test_classifier_timeout_retains_previous_success_across_rounds():
    class Classifier:
        provider = 'test'
        n = 0
        async def classify(self, dialogue):
            self.n += 1
            if self.n == 1:
                return make_state({'P1': 0, 'P2': 0, 'P3': 0, 'P4': 1, 'P5': 0},
                                  'cooperative', 'ok', 'test', 1)
            return uniform_state('timeout', 'test', 6)
    session, trace = run(deps_for(classifier=Classifier()), visitor())
    assert [r['path_pred'] for r in session['rounds']] == ['P4', 'P4']
    assert not trace['unknown_path_rounds']
    assert all(p['prediction_source'] == 'previous_success' for p in trace['path_probs'] if p['final'])
    assert all(p['uncertainty'] == 1 for p in trace['path_probs'] if p['final'])


def test_classifier_without_success_is_unknown_and_excluded():
    class Classifier:
        provider = 'test'
        async def classify(self, dialogue):
            return uniform_state('timeout', 'test', 6)
    session, trace = run(deps_for(classifier=Classifier()), visitor())
    assert session['status'] == 'completed'
    assert trace['unknown_path_rounds'] == [1, 2]
    assert all(p['path_pred'] == 'unknown' for p in trace['path_probs'] if p['final'])
    assert all(r['path_confidence'] is None for r in session['rounds'])
    report, summary = build_report({visitor()['id']: visitor()}, [(session, trace)],
                                   scorer=lambda *a, **k: pytest.fail('must not score unknown placeholders'))
    assert report is None and summary['unknown_path_sessions'] == 1
    assert summary['scored'] == 0 and summary['completion_rate'] == 1
    assert_valid(session, visitor())


def test_classifier_cache_does_not_duplicate_calls_or_latency():
    runner = plan_runner(ScriptedLLM())
    async def check():
        await runner._classify_current()
        await runner._classify_current()
    asyncio.run(check())
    assert len(runner.trace['llm_calls']) == 1
    assert runner._latency_summary()['classifier']['n'] == 1


@pytest.mark.parametrize('mode', ['failed', 'cancelled', 'completed'])
def test_discard_retains_all_speculative_attempts(mode):
    class LLM(ScriptedLLM):
        async def complete_json(self, messages, *, task, state):
            if mode == 'failed':
                raise LLMError('bad json')
            if mode == 'cancelled':
                await asyncio.Event().wait()
            return await super().complete_json(messages, task=task, state=state)
    runner = plan_runner(LLM())
    async def check():
        token = CALL_SCOPE.set(1)
        task = asyncio.create_task(runner._agent_step(runner._snapshot(1)))
        CALL_SCOPE.reset(token)
        task.engine_scope = 1
        runner._tasks.add(task)
        if mode == 'cancelled':
            while not any(c['task'] == 'strategy' for c in runner.trace['llm_calls']):
                await asyncio.sleep(0)
        else:
            await task
        await runner._discard(task)
        # run() drains and freezes the trace without performing extra rounds.
        async def no_round(number):
            pass
        runner._run_round = no_round
        return await runner.run()
    _, trace = asyncio.run(check())
    assert len(trace['llm_calls']) >= 2
    assert all(c['discarded'] for c in trace['llm_calls'])
    assert trace['speculation']['discarded_calls'] == len(trace['llm_calls'])
    if mode != 'completed':
        assert any(c['status'] == ('cancelled' if mode == 'cancelled' else 'error') for c in trace['llm_calls'])
    assert all(c['status'] != 'running' for c in trace['llm_calls'])


def test_error_sessions_are_excluded_and_all_judge_attempts_counted():
    good = run(deps_for(), visitor())
    bad = copy.deepcopy(good)
    bad[0]['status'], bad[0]['error'] = 'error', 'sim failed'
    bad[0]['visitor_id'] = 'A-error'
    bad[1]['all_judge_results'] = [dict(provider='ds_flash', status='timeout'),
                                  dict(provider='jev', status='ok')]
    seen = []
    def score(visitors, sessions, **kwargs):
        seen.extend(sessions)
        return {'n_visitors': len(sessions), 'safety_summary': {}, 'veto': {'passed': True, 'reasons': []}}
    report, summary = build_report({visitor()['id']: visitor(), 'A-error': visitor()}, [good, bad], scorer=score)
    assert seen == [good[0]] and report['n_visitors'] == 1
    assert summary['error_count'] == 1 and summary['completion_rate'] == .5
    assert report['safety_summary']['judge_calls'] == len(good[1]['all_judge_results']) + 2
    assert report['safety_summary']['judge_fallbacks'] == 1
    assert summary['llm_attempts'] == 2 * len(good[1]['llm_calls'])


def test_new_safety_script_api_suppresses_repeat_without_extra_visitor_reply():
    deps = deps_for()
    runner = SessionRunner(deps, visitor(), 'dedup')
    runner.rounds.append(_Round(1))
    from safety.layer import SafetyEvent
    event = SafetyEvent(1, 0, 'passive', 'scale_item9', 'safety_check', 'skipped', 'none', None, '')
    called = []
    def script(event_arg, state):
        called.append((event_arg, state))
        return ''
    deps.safety.script_for_event = script
    asyncio.run(runner._handle_event(event))
    assert called == [(event, runner.safety_state)]
    assert runner.safety_events == [event.to_dict()]
    assert runner.entries == [] and deps.sim.memories == []


def test_invalid_higher_budget_retry_does_not_start_another_retry_chain():
    llm, requests = client_for([response('{', 'length'), response('not JSON')])
    runner = plan_runner(llm)
    asyncio.run(runner._make_plan(1))
    assert len(requests) == 2 and runner.trace['fallbacks'][0]['task'] == 'plan'
