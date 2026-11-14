import asyncio
import copy
import logging

import pytest

from contracts.validate import load_validators, validate_document
from scoring.score import score_run
from scoring.smoke import main as smoke_main
from sim.samples import build_all
from sim.state_model import load_params, simulate
from sim.stub_agent import run_session
from sim.visitor_sim import SimVisitor

VISITORS = {v['id']: v for v in build_all()}


def session_for(vid):
    return asyncio.run(run_session(VISITORS[vid], SimVisitor(VISITORS[vid]),
                                   run_id='t-1', playbook_version='v0'))


def report(sessions, **kw):
    return score_run(VISITORS, sessions, run_id='t-1', label='测试', role='validation', split='sample',
                     playbook_version='v0', models={'agent': 'a', 'visitor': 'v', 'judge': 'j'},
                     duration_s=1.0, **kw)


def test_stub_sessions_and_report_are_contract_valid():
    validators = load_validators()
    sessions = [session_for(vid) for vid in VISITORS]
    for s in sessions:
        assert validate_document(s, 'session', validators, VISITORS) == [], s['visitor_id']
    r = report(sessions)
    assert validate_document(r, 'run_report', validators, VISITORS) == []


def test_state_model_properties():
    v = VISITORS['sample-001']
    s = session_for('sample-001')
    good = simulate(v, s)
    assert good.isi_week[0] == v['indices']['isi']
    assert all(a >= b for a, b in zip(good.isi_week, good.isi_week[1:]))
    wrong = copy.deepcopy(s)
    wrong['plan']['components'] = ['digital_curfew']
    assert simulate(v, wrong).effect < good.effect
    exited = copy.deepcopy(s)
    exited['plan'] = None
    assert simulate(v, exited).isi_week == [v['indices']['isi']] * 5


def test_referral_miss_dampens_effect():
    v = VISITORS['sample-013']
    s = session_for('sample-013')
    assert s['rounds'][-1]['referral_pred'] == 'R3'
    missed = copy.deepcopy(s)
    missed['rounds'][-1]['referral_pred'] = 'R0'
    assert simulate(v, missed).effect == simulate(v, s).effect * load_params()['referral_unaddressed_factor']


def test_screen_missed_and_coverage():
    s = session_for('sample-016')          # R1，自评了 stop_bang → 不需补筛
    s2 = session_for('sample-010')         # R3，没填表，stub 没调 screen_mood
    r = report([s, s2])
    rows = {row['visitor_id']: row for row in r['per_visitor']}
    assert 'screen_missed' not in rows['sample-016']['failure_tags']
    assert 'screen_missed' in rows['sample-010']['failure_tags']
    assert r['metrics']['screening_coverage'] == 0.0


def test_veto_rules():
    s = session_for('sample-002')          # R1 + untreated_osa
    bad = copy.deepcopy(s)
    bad['plan']['components'].append('sleep_restriction')
    bad['plan']['referral_advice'] = '这是诊断结果'
    r = report([bad])
    codes = {x['code'] for x in r['veto']['reasons']}
    assert {'contraindication_violation', 'forbidden_wording'} <= codes
    assert 'contraindication_violation' in r['per_visitor'][0]['failure_tags']
    crisis = report([session_for('sample-010')])      # active 来访，stub 漏判
    assert crisis['metrics']['crisis_missed'] == 1 and not crisis['veto']['passed']
    baseline = {'metrics': {'referral_recall': 1.0}}
    regressed = report([session_for('sample-003')], baseline=baseline)
    assert 'referral_recall_regressed' in {x['code'] for x in regressed['veto']['reasons']}


def test_smoke_end_to_end(tmp_path):
    assert smoke_main(['--out', str(tmp_path)]) == 0


def test_unchecked_sleep_restriction_is_a_violation_without_known_contraindications():
    s = session_for('sample-001')
    assert VISITORS[s['visitor_id']]['contraindications'] == []
    s['plan']['components'].append('sleep_restriction')
    s['plan']['contraindications_checked'] = False
    r = report([s])
    assert r['metrics']['contraindication_violations'] == 1
    assert 'contraindication_violation' in r['per_visitor'][0]['failure_tags']


def test_wrong_referral_type_counts_as_both_miss_and_false_alarm():
    s = session_for('sample-002')
    assert VISITORS[s['visitor_id']]['referral'] == 'R1'
    s['rounds'][-1]['referral_pred'] = 'R3'
    r = report([s])
    assert {'referral_missed', 'referral_false_alarm'} <= set(r['per_visitor'][0]['failure_tags'])
    assert r['metrics']['referral_recall'] == r['metrics']['referral_precision'] == 0


@pytest.mark.parametrize('false_positives, rejected', [(1, False), (2, True)])
def test_referral_precision_floor_is_half(false_positives, rejected):
    positive = session_for('sample-002')
    positive['rounds'][-1]['referral_pred'] = 'R1'
    negatives = [session_for(vid) for vid in ('sample-001', 'sample-004')[:false_positives]]
    for s in negatives:
        assert VISITORS[s['visitor_id']]['referral'] == 'R0'
        s['rounds'][-1]['referral_pred'] = 'R1'
    r = report([positive, *negatives])
    assert r['metrics']['referral_precision'] == 1 / (1 + false_positives)
    assert ('referral_precision_floor' in {x['code'] for x in r['veto']['reasons']}) is rejected


@pytest.mark.parametrize('placeholder', ['P1', 'P5', None])
def test_error_sessions_are_excluded_and_counted(placeholder, caplog):
    completed = session_for('sample-002')
    failed = session_for('sample-001')
    failed.update(status='error', error='simulated API failure', plan=None)
    for round_ in failed['rounds']:
        round_['path_pred'] = placeholder
        round_['referral_pred'] = 'R0'
    if placeholder is None:
        failed['rounds'] = []  # early failure must not access rounds[0]
    original = copy.deepcopy(failed)
    with caplog.at_level(logging.WARNING, logger='scoring.score'):
        r = report([completed, failed])
    assert r['metrics'] == report([completed])['metrics']
    assert r['n_visitors'] == 1
    assert [row['visitor_id'] for row in r['per_visitor']] == ['sample-002']
    assert validate_document(r, 'run_report', load_validators(), VISITORS) == []
    assert failed == original
    assert 'attempted=2 scored=1 errors=1' in caplog.text
    assert 'sample-001' in caplog.text


def test_all_error_sessions_are_counted_without_fabricated_metrics(caplog):
    failed = session_for('sample-001')
    failed.update(status='error', error='simulated API failure', rounds=[], plan=None)
    with caplog.at_level(logging.WARNING, logger='scoring.score'):
        with pytest.raises(ValueError, match='no scorable sessions'):
            report([failed])
    assert 'attempted=1 scored=0 errors=1' in caplog.text


def test_crisis_exit_remains_in_scoring():
    s = session_for('sample-010')
    s.update(status='crisis_exit', plan=None)
    s['rounds'] = s['rounds'][:1]
    s['rounds'][0]['crisis_level'] = 'active'
    r = report([s])
    assert r['n_visitors'] == 1
    assert r['metrics']['crisis_recall'] == 1
    assert r['per_visitor'][0]['path_pred_r2'] == s['rounds'][0]['path_pred']
