"""临时集验收：配额、可追溯语料、标签一致性及实际落盘结果。"""
import json
from collections import Counter

import pytest

from contracts.validate import load_validators, validate_document
from sim.gen_interim import DEFAULT_SEED, OUT_DIR, ROOT, build_all, source_catalog, write_visitors
from sim.samples import build_all as samples


@pytest.fixture(scope='module')
def visitors():
    return build_all()


def test_reproducible_and_seed_changes_output(visitors):
    assert visitors == build_all(DEFAULT_SEED)
    assert visitors != build_all(DEFAULT_SEED + 1)


@pytest.mark.parametrize('seed', [DEFAULT_SEED, 0, 1, 42, -17])
def test_distribution(seed):
    cards = build_all(seed)
    for split, n in [('A', 40), ('C', 32)]:
        group = [v for v in cards if v['split'] == split]
        assert len(group) == n
        assert [v['id'] for v in group] == [f'{split}-{i:03d}' for i in range(1, n + 1)]
        paths = Counter(v['main_path'] for v in group)
        assert set(paths) == {'P1', 'P2', 'P3', 'P4', 'P5'}
        assert max(paths.values()) - min(paths.values()) <= 1
        assert sum(v['secondary_path'] is not None for v in group) == round(n * .3)
        refs = Counter(v['referral'] for v in group)
        assert refs['R0'] == round(n * .6)
        assert all(refs[r] >= 4 for r in ('R1', 'R2', 'R3'))
        assert sum(bool(v['prefilled']) for v in group) == round(n * .4)
        defense = Counter(v['persona']['defensiveness'] for v in group)
        assert defense == {'low': round(n * .4), 'mid': round(n * .4), 'high': n - 2 * round(n * .4)}
        levels = Counter(v['crisis']['level'] for v in group)
        assert 2 <= levels['passive'] <= 3 and 1 <= levels['active'] <= 2
        assert 2 <= sum(v['crisis']['history'] for v in group) <= 3
        assert sum(bool(v['contraindications']) for v in group) >= 3
        for ref in ('R1', 'R3'):
            assert any(v['referral'] == ref and v['prefilled'] and v['persona']['defensiveness'] != 'low' for v in group)


def test_contract_and_referral_invariants(visitors):
    validators = load_validators()
    for v in visitors:
        assert validate_document(v, 'visitor', validators, {}) == [], v['id']
        idx = v['indices']
        assert (idx['stop_bang'] >= 3) == (v['referral'] == 'R1')
        assert (idx['phq9'] >= 10 or idx['gad7'] >= 10) == (v['referral'] == 'R3')
        sources = {c['id'].split('::', 1)[1] for c in v['clues']}
        if v['referral'] == 'R2':
            assert {f'domain/referral_cues.md#R2-c{i}' for i in (1, 2, 3)} <= sources
        else:
            assert not any(c['supports'] == 'R2' for c in v['clues'])
        if v['crisis']['history']:
            assert v['crisis']['level'] == 'none' and v['crisis']['phq9_item9'] == 0
        assert bool([c for c in v['clues'] if c['supports'] == 'crisis']) == (v['crisis']['history'] or v['crisis']['level'] != 'none')
        assert idx['phq9'] >= v['crisis']['phq9_item9']
        for s in v['prefilled']:
            assert s['reported_score'] <= idx[s['scale']]
            if v['persona']['defensiveness'] != 'low':
                assert s['reported_score'] < idx[s['scale']]
            if s['scale'] == 'phq9':
                assert s['items'][8] <= v['crisis']['phq9_item9']
        for day in v['diary']:
            assert 0 < day['tst_min'] <= day['tib_min'] <= 1440
            assert day['screen_in_bed_min'] <= day['tib_min']


def test_provenance_and_clue_order(visitors):
    catalog = source_catalog()
    for v in visitors:
        main_positions, secondary_positions = [], []
        assert len({c['id'] for c in v['clues']}) == len(v['clues'])
        for i, clue in enumerate(v['clues']):
            source = clue['id'].split('::', 1)[1]
            entry = catalog[source]
            assert entry['quote'] in (ROOT / entry['file']).read_text(encoding='utf-8')
            assert clue['content'] == entry['content']
            assert clue['reveal_topic'] == entry['reveal_topic']
            assert clue['supports'] == entry['supports']
            assert clue['deny_first'] == (entry['deny_first'] and v['persona']['defensiveness'] != 'low')
            if clue['supports'] == v['main_path']:
                main_positions.append(i)
            elif clue['supports'] == v['secondary_path']:
                secondary_positions.append(i)
            else:
                assert not clue['supports'].startswith('P')
            if clue['supports'] == 'P4':
                assert not clue['deny_first']
        assert len(main_positions) >= 2
        if v['secondary_path']:
            assert 1 <= len(secondary_positions) <= 2
            assert min(secondary_positions) > max(main_positions)


def test_no_card_or_source_combination_overlap(visitors):
    # Ignore IDs, split, seed, demographics, clue order and cosmetic punctuation.
    combinations = [frozenset(c['id'].split('::', 1)[1] for c in v['clues']) for v in visitors]
    texts = [frozenset(c['content'].strip('。 ') for c in v['clues']) for v in visitors]
    assert len(set(combinations)) == len(visitors)
    assert len(set(texts)) == len(visitors)
    sample_texts = {frozenset(c['content'].strip('。 ') for c in v['clues']) for v in samples()}
    assert set(texts).isdisjoint(sample_texts)


def test_compatible_paths_and_safety_cues(visitors):
    allowed = {('P1', 'P4'), ('P2', 'P3'), ('P3', 'P2'), ('P4', 'P1'), ('P5', 'P1'), ('P5', 'P3'), ('P5', 'P4')}
    for v in visitors:
        ids = {c['id'].split('#')[-1] for c in v['clues']}
        if v['secondary_path']:
            assert (v['main_path'], v['secondary_path']) in allowed
        assert not {'P1-c1', 'P1-c2'} <= ids
        assert not ('P3-c6' in ids and any(x in ids for x in ('P2-c2', 'P2-c4')))
        assert not ('P5-c3' in ids and 'P4' in (v['main_path'], v['secondary_path']))
        if 'R1-c4' in ids:
            assert 'drowsy_driving_job' in v['contraindications']
            assert '司机' in v['persona']['occupation']
        if 'P3-c4' in ids:
            assert v['referral'] != 'R3'  # 白天还行 vs 白天也有情绪困扰


def test_checked_in_files_and_cli_writer(tmp_path, visitors):
    write_visitors(visitors, tmp_path)
    expected = {f"{v['split']}/{v['id']}.json": v for v in visitors}
    for directory in (OUT_DIR, tmp_path):
        files = {str(p.relative_to(directory)): json.loads(p.read_text(encoding='utf-8')) for p in directory.rglob('*.json')}
        assert files == expected


def test_diary_matches_explicit_time_cues(visitors):
    for v in visitors:
        ids = {c['id'].split('#')[-1] for c in v['clues']}
        if 'P2-c3' in ids:
            assert all(abs(d['tib_min'] - 600) <= 5 and d['tst_min'] < 360 for d in v['diary'])
        if 'P4-c1' in ids:
            for d in v['diary'][5:]:
                h, m = map(int, d['lights_off'].split(':'))
                assert 175 <= h * 60 + m + d['sol_min'] <= 190
                assert d['risetime'] == '11:00'
        if 'P5-c1' in ids:
            assert all(60 <= d['screen_in_bed_min'] <= 120 for d in v['diary'])
        if 'P1-c2' in ids:
            assert {d['risetime'] for d in v['diary']} == {'06:00', '09:00'}


def test_do_not_recombine_existing_fully_mappable_samples():
    # sample-003 and sample-006 have three primary cues, like interim cards.
    # Other positive-referral samples have only two, or use excluded shift_work;
    # all interim R0 cards additionally carry an RC-7 near-miss cue.
    reserved = [
        {'P3-c1', 'P3-c2', 'P3-c3', 'R3-c1', 'R3-c3', 'review-C7:sample-003-c6'},
        {'P1-c2', 'P1-c6', 'P1-c4', 'R3-c3', 'R3-c4'},
    ]
    for seed in (DEFAULT_SEED, 0, 1, 42, -17):
        for v in build_all(seed):
            assert {c['id'].split('#')[-1] for c in v['clues']} not in reserved
