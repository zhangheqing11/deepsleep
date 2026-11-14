"""正式集：契约、样例同口径结构约束、联合分层配额、落盘复现。"""
from collections import Counter
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

from contracts.validate import load_validators, validate_document
from sim.generate import DEFAULT_SEED, generate, manifest, write_dataset
from sim.generate_templates import TEMPLATES
from sim.samples import build_all
from sim.screening import screen_mood

ROOT = Path(__file__).resolve().parents[1]
VISITORS = generate(DEFAULT_SEED)
VALIDATORS = load_validators()
EXPECTED_SIZES = {'A': 45, 'B': 45, 'C': 30, 'offline': 30}
PATHS = ('P1', 'P2', 'P3', 'P4', 'P5')


@pytest.mark.parametrize('v', VISITORS, ids=lambda v: v['id'])
def test_contract_and_sample_constraints(v):
    # 移植 test_sim_samples 的全部逐人结构断言，并收紧主次线索顺序。
    assert validate_document(v, 'visitor', VALIDATORS, {}) == []
    idx, crisis = v['indices'], v['crisis']
    osa = idx['stop_bang'] >= 3
    mood = idx['phq9'] >= 10 or idx['gad7'] >= 10
    assert not (osa and mood)
    assert (v['referral'] == 'R1') == osa
    assert (v['referral'] == 'R3') == mood
    legs = [c for c in v['clues'] if c['supports'] == 'R2']
    assert bool(legs) == (v['referral'] == 'R2')
    if legs:
        assert len(legs) >= 3
        assert all(c['reveal_topic'] == 'leg_discomfort' for c in legs)
        text = ''.join(c['content'] for c in legs)
        assert any(w in text for w in ('走', '活动'))
        assert any(w in text for w in ('夜', '晚'))
        assert any(w in text for w in ('躺', '坐', '静'))
    if v['referral'] in ('R1', 'R3'):
        assert any(c['supports'] == v['referral'] for c in v['clues'])
    main = [i for i, c in enumerate(v['clues']) if c['supports'] == v['main_path']]
    secondary = [i for i, c in enumerate(v['clues']) if c['supports'] == v['secondary_path']]
    assert 2 <= len(main) <= 3
    assert 1 <= len(secondary) <= 2 and min(secondary) > max(main)
    assert {c['supports'] for c in v['clues'] if c['supports'] in PATHS} <= {v['main_path'], v['secondary_path']}
    assert not any(c['deny_first'] for c in v['clues'] if c['supports'] == 'P4')
    risk = [c for c in v['clues'] if c['supports'] == 'crisis']
    assert bool(risk) == (crisis['history'] or crisis['level'] != 'none')
    assert all(c['reveal_topic'] == 'self_harm' for c in risk)
    if crisis['history']:
        assert crisis['level'] == 'none' and crisis['phq9_item9'] == 0
    if crisis['level'] != 'none':
        assert crisis['phq9_item9'] > 0 and v['referral'] == 'R3'
    assert v['persona']['age'] >= 18
    assert len({c['id'] for c in v['clues']}) == len(v['clues'])
    for s in v['prefilled']:
        if s['scale'] == 'phq9':
            assert s['items'][8] <= crisis['phq9_item9']
        if v['persona']['defensiveness'] == 'low':
            assert s['reported_score'] == idx[s['scale']]
        else:
            assert s['reported_score'] < idx[s['scale']]
    screened = screen_mood(v)
    assert sum(screened['phq9_items']) == idx['phq9']
    assert screened['phq9_items'][8] == crisis['phq9_item9']


@pytest.mark.parametrize('seed', [DEFAULT_SEED, 0, 42, -7])
def test_distribution_and_joint_strata(seed):
    visitors = generate(seed)
    assert len(visitors) == 150 and len({v['id'] for v in visitors}) == 150
    assert len({v['seed'] for v in visitors}) == 150
    getters = {
        'path': lambda v: v['main_path'],
        'referral': lambda v: v['referral'],
        'defense': lambda v: v['persona']['defensiveness'],
        'joint': lambda v: (v['main_path'], v['referral'], v['persona']['defensiveness']),
    }
    overall = {key: Counter(fn(v) for v in visitors) for key, fn in getters.items()}
    assert len(overall['joint']) == 60  # 全部 5×4×3 层都有，不仅比较边际分布。
    for split, size in EXPECTED_SIZES.items():
        group = [v for v in visitors if v['split'] == split]
        assert len(group) == size
        assert [v['id'] for v in group] == [f'{split}-{i:03d}' for i in range(1, size + 1)]
        assert Counter(v['referral'] for v in group) == {'R0': size * 3 // 5, **{r: size * 2 // 15 for r in ('R1', 'R2', 'R3')}}
        for key, fn in getters.items():
            observed = Counter(fn(v) for v in group)
            for label, count in overall[key].items():
                target = count * size / 150
                assert math.floor(target) <= observed[label] <= math.ceil(target)
                assert abs(observed[label] / size - count / 150) <= 0.1
        assert sum(bool(v['prefilled']) for v in group) == size * 2 // 5
        assert Counter(v['persona']['defensiveness'] for v in group if v['prefilled']) == dict.fromkeys(('low', 'mid', 'high'), size * 2 // 15)
        assert Counter(v['crisis']['level'] for v in group) == {'none': size - 2, 'passive': 1, 'active': 1}
        assert 2 <= sum(v['crisis']['history'] for v in group) <= 3
        assert sum(any(c['supports'] == 'R0' for c in v['clues']) for v in group) == size // 5
        assert any(v['referral'] == 'R1' and not v['prefilled'] for v in group)
        assert any(v['referral'] == 'R3' and not v['prefilled'] for v in group)
        assert any('bipolar' in v['contraindications'] for v in group)
        assert any('drowsy_driving_job' in v['contraindications'] for v in group)


def test_topic_and_denial_sources():
    # 以实际 domain 表格作为允许的 supports/topic 对；禁忌补充见 plan_veto_rules。
    path_text = (ROOT / 'domain/path_clues.md').read_text()
    referral_text = (ROOT / 'domain/referral_cues.md').read_text()
    allowed = set(re.findall(r'\| ([PR][1-5])-c\d+ \|.*?\| `([a-z_]+)`', path_text + referral_text))
    allowed |= {('R1', 'health_conditions'), ('R1', 'life_constraints'), ('R3', 'health_conditions')}
    for v in VISITORS:
        for c in v['clues']:
            if c['supports'] not in ('R0', 'crisis'):
                assert (c['supports'], c['reveal_topic']) in allowed
            if c['deny_first']:
                assert c['reveal_topic'] in {'sleep_elsewhere', 'fear_of_sleeplessness', 'screen_in_bed',
                                             'snoring_breathing', 'leg_discomfort', 'mood', 'anxiety', 'self_harm'}
    assert all(len(texts) >= 3 for _, _, texts in TEMPLATES.values())


def test_crisis_wording_is_approved_and_cases_are_distinct():
    approved = {c['content'] for v in build_all() for c in v['clues'] if c['supports'] == 'crisis'}
    assert all(c['content'] in approved for v in VISITORS for c in v['clues'] if c['supports'] == 'crisis')
    # 不能仅换 id；人格、线索、日记确实独立生成，开场不编码主路径。
    cases = [json.dumps({k: val for k, val in v.items() if k not in ('id', 'split', 'seed', 'clues')}, sort_keys=True) for v in VISITORS]
    assert len(set(cases)) == 150
    assert len({tuple(c['content'] for c in v['clues']) for v in VISITORS}) == 150
    assert len({v['persona']['occupation'] for v in VISITORS}) >= 12
    assert len({c['content'] for v in VISITORS for c in v['clues']}) > 200
    assert all(not any(p in v['opening_complaint'] for p in PATHS) for v in VISITORS)


@pytest.mark.parametrize('v', VISITORS, ids=lambda v: v['id'])
def test_diary_and_contraindications_are_consistent(v):
    def minutes(time):
        h, m = map(int, time.split(':'))
        return h * 60 + m

    for day in v['diary']:
        tib = (minutes(day['risetime']) - minutes(day['bedtime'])) % 1440
        delay = (minutes(day['lights_off']) - minutes(day['bedtime'])) % 1440
        gap = (minutes(day['risetime']) - minutes(day['final_wake'])) % 1440
        assert tib == day['tib_min']
        assert day['tst_min'] == tib - delay - gap - day['sol_min'] - day['waso_min']
        assert 0 < day['tst_min'] <= tib
        assert day['screen_in_bed_min'] <= delay
    assert ('untreated_osa' in v['contraindications']) == (v['referral'] == 'R1')
    if 'untreated_osa' in v['contraindications']:
        assert any('呼吸暂停' in c['content'] or '呼吸有暂停' in c['content'] for c in v['clues'])
    if 'bipolar' in v['contraindications']:
        assert v['referral'] == 'R3'
        assert any(c['reveal_topic'] == 'health_conditions' and '双相' in c['content'] for c in v['clues'])
    if 'drowsy_driving_job' in v['contraindications']:
        assert v['main_path'] == 'P4' and v['referral'] == 'R1'
        assert '司机' in v['persona']['occupation']
        assert any(c['reveal_topic'] == 'life_constraints' and '叉车' in c['content'] for c in v['clues'])
    if any(c['reveal_topic'] == 'shift_work' for c in v['clues']):
        assert '班' in v['persona']['occupation']


def test_committed_files_and_manifest_match_generator():
    expected = {f'{v["split"]}/{v["id"]}.json': v for v in VISITORS}
    expected['MANIFEST.json'] = manifest(DEFAULT_SEED, VISITORS)
    root = ROOT / 'data/visitors'
    # Only this generator's outputs; data/visitors/interim/ belongs to sim/gen_interim.py.
    ours = [root / 'MANIFEST.json', *(p for split in ('A', 'B', 'C', 'offline') for p in (root / split).glob('*.json'))]
    actual = {str(p.relative_to(root)): json.loads(p.read_text()) for p in ours}
    assert actual == expected


def test_same_seed_byte_identical_across_processes(tmp_path):
    def snapshot(root):
        return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*.json')}

    first, second = tmp_path / 'first', tmp_path / 'second'
    for out, hash_seed in ((first, '1'), (second, '987')):
        result = subprocess.run([sys.executable, '-m', 'sim.generate', '--seed', str(DEFAULT_SEED), '--out', str(out)],
                                cwd=ROOT, env={**os.environ, 'PYTHONHASHSEED': hash_seed},
                                text=True, capture_output=True, check=True)
        assert 'wrote 150 visitors' in result.stdout
    assert snapshot(first) == snapshot(second)
    before = snapshot(first)
    write_dataset(DEFAULT_SEED, first)
    assert snapshot(first) == before
    assert generate(DEFAULT_SEED + 1) != VISITORS


def test_unknown_output_files_are_preserved(tmp_path):
    extra = tmp_path / 'A' / 'A-999.json'
    extra.parent.mkdir()
    extra.write_text('{"external": true}\n')
    with pytest.raises(ValueError, match='额外 JSON'):
        write_dataset(DEFAULT_SEED, tmp_path)
    assert extra.read_text() == '{"external": true}\n'
    assert not (tmp_path / 'MANIFEST.json').exists()
