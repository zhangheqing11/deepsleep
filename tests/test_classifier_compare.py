"""Offline regression checks for sampling, leakage boundaries and statistics."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from analysis.classifier_compare import (
    CAPTURE, CONFIGS, DSRecorder, bootstrap, collect_dataset, match_clue,
    session_prefixes, summarize,
)


def fixture_session():
    card = dict(id='sample-001', main_path='P2', secondary_path='P3',
                persona={'defensiveness': 'low'}, clues=[
                    dict(id='c1', supports='P2', content='我一躺到床上反而越来越精神，翻来覆去一两个小时。')])
    session = dict(session_id='run/sample-001', run_id='run', visitor_id='sample-001',
                   models={'agent': 'deepseek-flash', 'visitor': 'mock'}, status='completed', rounds=[
        {'round': 1, 'transcript': [
            dict(turn=1, speaker='visitor', text='睡不好。', revealed_clue_ids=['c1']),
            dict(turn=2, speaker='agent', text='我一躺到床上反而越来越精神，翻来覆去一两个小时？'),
            dict(turn=3, speaker='safety', text='安全话术'),
            dict(turn=4, speaker='visitor', text='我不知道。')]},
        {'round': 2, 'transcript': [
            dict(turn=1, speaker='visitor', text=card['clues'][0]['content'], revealed_clue_ids=['c1'])]}])
    return session, card


def test_prefixes_are_cumulative_and_clue_requires_visitor_text():
    session, card = fixture_session()
    prefixes, events = session_prefixes(session, card)
    assert [p['k'] for p in prefixes] == [1, 2, 3]
    assert [p['round'] for p in prefixes] == [1, 1, 2]
    assert len(prefixes[-1]['dialogue']) == 4
    assert all(set(e) == {'speaker', 'text'} for p in prefixes for e in p['dialogue'])
    assert [e['k'] for e in events] == [3]  # Neither ID alone nor the agent question counts.
    assert match_clue('完全不相干', card['clues'][0]['content']) is None


def test_collect_deduplicates_and_preserves_clue_pair_and_final(tmp_path):
    directory, cards = tmp_path/'sessions', tmp_path/'cards'
    directory.mkdir()
    cards.mkdir()
    session, card = fixture_session()
    (cards/'sample-001.json').write_text(json.dumps(card))
    for name in ('one', 'duplicate'):
        (directory/f'{name}.json').write_text(json.dumps(session))
    session['models']['agent'] = 'mock-agent'
    (directory/'mock.json').write_text(json.dumps(session))
    dataset = collect_dataset([directory], cards, target=2)
    assert dataset['counts']['sessions'] == 1
    assert dataset['counts']['unique_prefixes'] == 3
    assert dataset['counts']['selected_unique_prefixes'] == 2
    assert [p['k'] for p in dataset['sessions'][0]['prefixes'] if p['selected']] == [2, 3]
    assert len(dataset['excluded']) == 1
    assert len(dataset['sessions'][0]['duplicate_sources']) == 1
    with pytest.raises(ValueError, match='too small'):
        collect_dataset([directory], cards, target=1)


def test_cluster_bootstrap_preserves_session_multiplicity():
    metric = bootstrap([[0]*10, [1]*10], repetitions=500)
    assert metric['value'] == .5
    assert metric['ci95'] == [0, 1]
    assert metric['sessions'] == 2
    assert bootstrap([])['ci95'] is None


def test_failures_are_not_uniform_predictions_and_brier_is_multiclass():
    doc = {'dataset': {'sessions': [dict(session_id='s', main_path='P2', defensiveness='low',
            first_clue_k=2, prefixes=[dict(k=1, sample_id='a'), dict(k=2, sample_id='b')])]}, 'results': []}
    for config in CONFIGS:
        doc['results'] += [dict(config=config, sample_id='a', status='ok', top='P1',
                               weights={p: .2 for p in ('P1','P2','P3','P4','P5')},
                               uncertainty=1, attitude='cooperative', latency_ms=100, usage=None),
                           dict(config=config, sample_id='b', status='timeout', top=None,
                                weights=None, uncertainty=None, latency_ms=15001, usage=None)]
    metrics = summarize(doc, repetitions=30)
    for m in metrics.values():
        assert m['final_accuracy_all']['value'] == 0
        assert 'final_accuracy_valid' not in m
        assert m['brier']['value'] == pytest.approx(.8)
        assert m['brier']['n'] == 1
        assert m['calls']['over_6s'] == 1
        assert m['clue_pairs'] == []


def test_thinking_proxy_forwards_existing_prompt_and_explicit_high():
    captured = {}

    async def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(model='test', usage=None, choices=[SimpleNamespace(
            message=SimpleNamespace(content='{}', reasoning_content='reason'))])

    async def run():
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        token = CAPTURE.set({})
        try:
            await DSRecorder(client, True).create(messages=[{'role': 'system', 'content': 'unchanged'}],
                                                  extra_body={'thinking': {'type': 'enabled'}})
        finally:
            CAPTURE.reset(token)

    asyncio.run(run())
    assert captured['reasoning_effort'] == 'high'
    assert captured['messages'][0]['content'] == 'unchanged'
    assert captured['extra_body'] == {'thinking': {'type': 'enabled'}}


def test_dry_run_never_loads_credentials_or_calls_api(tmp_path, monkeypatch):
    import analysis.classifier_compare as compare
    directory, cards = tmp_path/'sessions', tmp_path/'cards'
    directory.mkdir()
    cards.mkdir()
    session, card = fixture_session()
    (directory/'one.json').write_text(json.dumps(session))
    (cards/'sample-001.json').write_text(json.dumps(card))

    def forbidden(*args, **kwargs):
        pytest.fail('Dry run accessed credentials or API')

    monkeypatch.setattr(compare, 'load_env', forbidden)
    monkeypatch.setattr(compare, 'run_calls', forbidden)
    output = tmp_path/'results.json'
    compare.main(['--dry-run', '--source', str(directory), '--cards', str(cards),
                  '--target', '2', '--output', str(output), '--env', str(tmp_path/'nonexistent.env')])
    assert not output.exists()
    data = json.loads((tmp_path/'results.dry-run.json').read_text())
    assert not data['results']
    assert len(data['dataset']['samples']) == 2
