"""手写样例来访：契约校验 + 临床口径（path_clues / review-decisions）的结构性检查。"""
import json
from collections import Counter

import pytest

from contracts.validate import load_validators, validate_document
from sim.samples import OUT_DIR, build_all

VISITORS = build_all()
PATHS = ('P1', 'P2', 'P3', 'P4', 'P5')


def test_files_match_specs():
    """sim/visitors/*.json 必须由 python -m sim.samples 生成，不手改。"""
    files = sorted(OUT_DIR.glob('*.json'))
    assert [p.stem for p in files] == [v['id'] for v in VISITORS]
    for path, visitor in zip(files, VISITORS):
        assert json.loads(path.read_text(encoding='utf-8')) == visitor, path.name


@pytest.mark.parametrize('visitor', VISITORS, ids=lambda v: v['id'])
def test_contract_valid(visitor):
    assert validate_document(visitor, 'visitor', load_validators(), {}) == []


def test_distribution():
    assert 15 <= len(VISITORS) <= 20
    per_path = Counter(v['main_path'] for v in VISITORS)
    assert all(3 <= per_path[p] <= 4 for p in PATHS), per_path
    referrals = Counter(v['referral'] for v in VISITORS)
    assert all(referrals[r] >= 2 for r in ('R1', 'R2', 'R3')), referrals
    prefilled = sum(bool(v['prefilled']) for v in VISITORS) / len(VISITORS)
    assert 0.35 <= prefilled <= 0.5, prefilled                      # D1 约 40%
    assert sum(v['crisis']['history'] for v in VISITORS) >= 2       # D3
    levels = Counter(v['crisis']['level'] for v in VISITORS)
    assert levels['passive'] >= 1 and levels['active'] >= 1


def test_smoke_subset_covers_everything():
    first10 = VISITORS[:10]
    assert {v['main_path'] for v in first10} == set(PATHS)
    assert {v['referral'] for v in first10} == {'R0', 'R1', 'R2', 'R3'}
    assert {v['crisis']['level'] for v in first10} == {'none', 'passive', 'active'}
    assert any(v['crisis']['history'] for v in first10)
    # 至少一个"需要补筛"的来访（转介阳性且对应量表没自评）
    assert any(v['referral'] in ('R1', 'R3') and not v['prefilled'] for v in first10)


@pytest.mark.parametrize('visitor', VISITORS, ids=lambda v: v['id'])
def test_referral_matches_indices(visitor):
    """标签按隐藏指数定；每个来访只有一个转介标签（RC-6）。"""
    idx = visitor['indices']
    osa = idx['stop_bang'] >= 3
    mood = idx['phq9'] >= 10 or idx['gad7'] >= 10
    assert not (osa and mood), 'R1/R3 不得重叠'
    expected = 'R1' if osa else 'R3' if mood else None
    if expected:
        assert visitor['referral'] == expected
    else:
        assert visitor['referral'] in ('R0', 'R2')
    leg = [c for c in visitor['clues'] if c['supports'] == 'R2']
    assert (visitor['referral'] == 'R2') == bool(leg)
    if visitor['referral'] == 'R2':
        assert len(leg) >= 3          # RC-2：满足 3 个核心特征就转
    if visitor['referral'] in ('R1', 'R3'):
        assert any(c['supports'] == visitor['referral'] for c in visitor['clues'])


@pytest.mark.parametrize('visitor', VISITORS, ids=lambda v: v['id'])
def test_clue_structure(visitor):
    clues = visitor['clues']
    main = [i for i, c in enumerate(clues) if c['supports'] == visitor['main_path']]
    assert len(main) >= 2
    sec = [i for i, c in enumerate(clues) if c['supports'] == visitor['secondary_path']]
    if visitor['secondary_path']:
        assert 1 <= len(sec) <= 2 and min(sec) > min(main)          # PC-5：次要线索 1–2 条且靠后
    paths = {c['supports'] for c in clues if c['supports'] in PATHS}
    assert paths <= {visitor['main_path'], visitor['secondary_path']}
    assert not any(c['deny_first'] for c in clues if c['supports'] == 'P4')   # P4 不设 deny_first
    crisis_clues = [c for c in clues if c['supports'] == 'crisis']
    if visitor['crisis']['history'] or visitor['crisis']['level'] != 'none':
        assert crisis_clues and all(c['reveal_topic'] == 'self_harm' for c in crisis_clues)
    else:
        assert not crisis_clues
    if visitor['crisis']['history']:
        assert visitor['crisis']['level'] == 'none' and visitor['crisis']['phq9_item9'] == 0


@pytest.mark.parametrize('visitor', VISITORS, ids=lambda v: v['id'])
def test_age_and_prefilled(visitor):
    assert visitor['persona']['age'] >= 18                           # PV-6
    for s in visitor['prefilled']:
        if s['scale'] == 'phq9':
            assert s['items'][8] <= visitor['crisis']['phq9_item9']
