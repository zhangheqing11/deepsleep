import asyncio
from types import SimpleNamespace

import httpx
try:
    import httpx2
except ImportError:
    httpx2 = None

TRANSPORTS = [httpx] + ([httpx2] if httpx2 is not None else [])
import pytest
from openai import APIConnectionError

from engine.adapters_sim import S2RendererClient, make_s2_sim
from engine.config import load_config
from engine.evolve.pipeline import evolve
from engine.network import retry_connection
from engine.telemetry import record_call
from evolve_support import BASELINE, MockLLM, change, example, make_config, reply
from test_engine_resilience import client_for, plan_runner, response


@pytest.mark.parametrize('error', [error for transport in TRANSPORTS
                                  for error in (transport.ConnectError('offline'), transport.ReadTimeout('slow'))])
def test_agent_retries_transport_with_exponential_delays_and_counts(monkeypatch, error):
    waits = []
    async def sleep(delay):
        waits.append(delay)
    monkeypatch.setattr('engine.network.asyncio.sleep', sleep)
    wrapped = APIConnectionError(request=httpx.Request('POST', 'https://example.test'))
    wrapped.__cause__ = error
    client, calls = client_for([wrapped, error, response('{"ok": true}')])
    rows = []
    async def run():
        with record_call(rows, 'agent', 'turn'):
            return await client.complete_json([], task='turn', state={})
    assert asyncio.run(run()) == {'ok': True}
    assert waits == [.5, 1.0]
    assert len(calls) == 3
    assert rows[0]['network_retries'] == 2
    assert client.network_stats == {'attempts': 3, 'retries': 2}


@pytest.mark.parametrize('transport', TRANSPORTS)
def test_exhausted_transport_does_not_restart_outer_retry_loop(transport):
    client, calls = client_for([transport.ConnectError('offline')])
    client.settings['network_retry']['backoff_s'] = 0
    runner = plan_runner(client)
    asyncio.run(runner._make_plan(1))
    assert len(calls) == 3
    assert len(runner.trace['fallbacks']) == 1


@pytest.mark.parametrize('status', [400, 401, 429, 500])
def test_http_status_never_retried_at_either_layer(status):
    request = httpx.Request('POST', 'https://example.test')
    exc = httpx.HTTPStatusError('status failure', request=request,
                               response=httpx.Response(status, request=request))
    client, calls = client_for([exc])
    asyncio.run(plan_runner(client)._make_plan(1))
    assert len(calls) == 1


@pytest.mark.parametrize('transport', TRANSPORTS)
def test_renderer_retries_then_falls_back_and_counts(transport):
    calls = []
    async def create(**kwargs):
        calls.append(kwargs)
        raise transport.ReadTimeout('slow')
    client = S2RendererClient(SimpleNamespace(model='test'), network_retry={'backoff_s': 0})
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    assert asyncio.run(client.complete('s', 'u')) is None
    assert len(calls) == 3 and client.last_error == 'ReadTimeout'
    assert client.network_stats['retries'] == 2


def test_cancel_during_backoff_is_not_swallowed(monkeypatch):
    async def request():
        raise httpx.ConnectError('offline')
    async def sleep(delay):
        raise asyncio.CancelledError()
    monkeypatch.setattr('engine.network.asyncio.sleep', sleep)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(retry_connection(request, {}))


def test_template_keeps_s2_deny_reveal_state_without_client():
    from sim.visitor_sim import SimVisitor
    visitor = example('visitor.A-001.json')
    # Use a known defensive clue; actual S2 decides first denial then reveal.
    visitor['persona']['defensiveness'] = 'high'
    clue = visitor['clues'][0]
    clue['deny_first'] = True
    adapter = make_s2_sim(load_config({'visitor_renderer': 'template'}))
    assert adapter.client is None and adapter.model_name == 'template'
    async def run():
        direct = SimVisitor(visitor)
        memory = {}
        assert (await adapter.reply(visitor, 1, [], memory)).text == direct.opening().text
        transcript = [{'speaker': 'agent', 'text': '你在床上清醒时在想什么？'}]
        from engine.topics import tag_topics
        clue['reveal_topic'] = tag_topics(transcript[0]['text'])[0]
        for round_no in (1, 2):
            expected = await direct.respond(transcript[0]['text'], asked_topics=tag_topics(transcript[0]['text']))
            actual = await adapter.reply(visitor, round_no, transcript, memory)
            assert actual.text == expected.text
        assert memory['_s2_replies'][1]['denied_clue_ids'] == [clue['id']]
        assert clue['id'] in memory['_s2_replies'][2]['revealed_clue_ids']
    asyncio.run(run())


def test_invalid_renderer_and_retry_config_rejected():
    with pytest.raises(ValueError):
        load_config({'visitor_renderer': 'bad'})
    with pytest.raises(ValueError):
        load_config({'agent_llm': {'network_retry': {'max_retries': -1}}})


class FilelessRepo:
    def init(self): pass
    def current_version(self): return 'v1'
    def read(self):
        from evolve_support import FIXTURE_INITIAL
        return FIXTURE_INITIAL.read_text()


def test_gate_baseline_then_candidates_never_overlap(tmp_path):
    active, peak, labels = 0, 0, []
    async def evaluator(text, *, label):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        labels.append(label)
        await asyncio.sleep(.001)
        active -= 1
        return BASELINE.copy()
    candidates = [[change('communication_style', f'先确认第{i}个具体困扰。')] for i in range(3)]
    asyncio.run(evolve(run_report=example('run_report.run1.json'), sessions={},
        evaluator=evaluator, config=make_config(tmp_path), repo=FilelessRepo(),
        primary=MockLLM(reply(*candidates)), use_default_clients=False, evolution_id='ordered'))
    assert peak == 1
    assert labels == ['v1', 'v1+c1', 'v1+c2', 'v1+c3']


def test_gate_baseline_failure_stops_before_candidates_and_cleans_review(tmp_path, monkeypatch):
    from engine.evolve import pipeline
    labels, review_closed = [], []
    async def evaluator(text, *, label):
        labels.append(label)
        await asyncio.sleep(.01)
        raise RuntimeError('baseline failed')
    async def collect(*args, **kwargs):
        try:
            await asyncio.sleep(60)
        finally:
            review_closed.append(True)
    monkeypatch.setattr(pipeline.review, 'collect', collect)
    candidates = [[change('communication_style', '先确认具体困扰。')], [], []]
    with pytest.raises(RuntimeError, match='baseline failed'):
        asyncio.run(evolve(run_report=example('run_report.run1.json'), sessions={},
            evaluator=evaluator, config=make_config(tmp_path), repo=FilelessRepo(),
            primary=MockLLM(reply(*candidates)), use_default_clients=False, evolution_id='failed'))
    assert labels == ['v1'] and review_closed == [True]


def test_trial_http_limit_budget_and_host_ledger(tmp_path):
    from analysis.gate_support import TrialMeter, RequestBudget, RequestBudgetExceeded
    import json
    class Client:
        active = peak = sends = 0
        async def send(self, request):
            self.active += 1
            self.peak = max(self.peak, self.active)
            self.sends += 1
            await asyncio.sleep(.001)
            self.active -= 1
            return httpx.Response(200)
    meter = TrialMeter(RequestBudget(tmp_path/'budget.log', 5), tmp_path, http_limit=2)
    client = Client()
    async def run():
        with meter.watch_http(Client):
            return await asyncio.gather(*(client.send(httpx.Request('POST', 'https://example.test'))
                                          for _ in range(8)), return_exceptions=True)
    results = asyncio.run(run())
    assert client.sends == 5 and client.peak == 2
    assert sum(isinstance(r, RequestBudgetExceeded) for r in results) == 3
    assert len((tmp_path/'budget.log').read_text().splitlines()) == 5
    rows = [json.loads(s) for s in (tmp_path/'http-results.jsonl').read_text().splitlines()]
    assert len(rows) == 5 and max(r['inflight'] for r in rows) == 2
    assert {r['host'] for r in rows} == {'example.test'}


@pytest.mark.parametrize('renderer', ['llm', 'template'])
def test_real_demo_renderer_still_requires_agent_credentials(renderer):
    from engine.demo import make_deps
    with pytest.raises(ValueError, match='DS_'):
        make_deps({'mock': False, 'visitor_renderer': renderer})


def test_run_cli_explicit_llm_renderer_uses_s2_factory(tmp_path, monkeypatch):
    from engine import run as cli
    from engine.stubs import MockVisitorSim
    sim = MockVisitorSim()
    choices, captured = [], {}
    def factory(config, **kwargs):
        choices.append(config['visitor_renderer'])
        return sim
    def deps(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(llm=SimpleNamespace(model_name='mock'),
                               classifier=SimpleNamespace(provider='mock'),
                               safety=SimpleNamespace(judge=SimpleNamespace(provider='mock')))
    async def batch(*args, **kwargs):
        return []
    monkeypatch.setattr('engine.adapters_sim.make_s2_sim', factory)
    monkeypatch.setattr(cli, 'load_dotenv', lambda: None)
    monkeypatch.setattr(cli, 'load_visitors', lambda paths: [])
    monkeypatch.setattr(cli, 'build_deps', deps)
    monkeypatch.setattr(cli, 'run_batch', batch)
    assert cli.main(['--visitor-renderer','llm','--out',str(tmp_path)]) == 0
    assert choices == ['llm'] and captured['sim'] is sim
