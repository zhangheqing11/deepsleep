import asyncio
import copy

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
