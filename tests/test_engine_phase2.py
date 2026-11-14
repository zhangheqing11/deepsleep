"""Phase 2: frozen screening and fail-closed user-facing wording."""
import json
from pathlib import Path
import pytest
from domain.vetoes import check_text
from engine.adapters_sim import S2Screening, S2VisitorSim, S2OutcomeModel
from engine.session import SessionRunner
from test_engine_session import (SAY, ScriptedLLM, ScriptedSim, deps_for, run, visitor, assert_valid, agent_count)

@pytest.mark.parametrize('early', [False, True])
def test_hidden_item9_forced_screen_even_if_agent_ends_early(early):
    v = json.loads(Path('sim/visitors/sample-003.json').read_text())
    assert v['prefilled'][0]['items'][8] == 0
    deps = deps_for(llm=ScriptedLLM(lambda s,m: {'action':'end_round'} if early else SAY))
    deps.screening = S2Screening()
    session, trace = run(deps, v)
    mood = [c for c in session['tool_calls'] if c['tool'] == 'screen_mood']
    assert len(mood) == 1 and mood[0]['round'] == 1
    assert mood[0]['result']['phq9_items'][8] == 1
    assert any(e['source'] == 'scale_item9' and e['action'] == 'safety_check' for e in session['safety_events'])
    assert trace['forced_tool_calls'][0]['turn'] == mood[0]['turn']
    if not early:
        assert agent_count(session, 1) == deps.config['round_turn_cap'][1] + 1
        assert trace['forced_tool_calls'][0]['after_actions'] == 2
    assert_valid(session, v)

def test_voluntary_mood_screen_is_not_duplicated_by_harness():
    calls=iter([{'action':'tool','tool':'screen_mood'}])
    session, trace=run(deps_for(llm=ScriptedLLM(lambda s,m:next(calls,SAY))), visitor())
    assert len([c for c in session['tool_calls'] if c['tool']=='screen_mood']) == 1
    assert trace['forced_tool_calls'] == []

@pytest.mark.parametrize('merged', [False, True])
def test_persistent_forbidden_sentence_removed_from_spoken_response(merged):
    bad='我能诊断失眠症。能说说你的作息吗？'
    llm=ScriptedLLM(lambda s,m:{'action':'say','text':bad}, response=lambda s,m:{'text':bad,'acts':[]})
    session, trace=run(deps_for(llm=llm,merged=merged),visitor())
    texts=[t['text'] for r in session['rounds'] for t in r['transcript'] if t['speaker']=='agent']
    assert all(not check_text(t) for t in texts)
    assert '能说说你的作息吗？' in texts
    assert any(v['stage']=='text_redacted' for v in trace['vetoes'])
    assert_valid(session, visitor())

def test_persistent_forbidden_plan_fields_removed():
    from engine.mock_agent import MockAgentLLM
    def bad_plan(state,messages):
        p=MockAgentLLM()._plan(state)
        p['closing_message']='我能诊断失眠症。请保持固定起床时间。'
        p['plan']['referral_advice']='我能诊断失眠症。建议就医。'
        p['plan']['cards']=[{'type':'reminder','title':'诊断失眠症','body':'治疗失眠症。记录作息。'}]
        return p
    session, trace=run(deps_for(llm=ScriptedLLM(plan=bad_plan)),visitor())
    assert not check_text(json.dumps(session['plan'],ensure_ascii=False))
    assert all(not check_text(t['text']) for r in session['rounds'] for t in r['transcript'] if t['speaker']=='agent')
    assert_valid(session,visitor())


def test_merged_memory_plan_feeds_round2_and_s2_referral():
    from engine.mock_agent import MockAgentLLM
    class Agent(MockAgentLLM):
        calls=[]
        async def complete_json(self, messages, *, task, state):
            self.calls.append((task,messages,state))
            return await super().complete_json(messages,task=task,state=state)
    llm=Agent()
    deps=deps_for(llm=llm)
    deps.config['pipeline']['merge_memory_plan']=True
    v=visitor('A-003')
    session,trace=run(deps,v)
    assert session['status']=='completed'
    assert [t for t,_,s in llm.calls if s['round']==1 and t in ('memory','plan','memory_plan')] == ['memory_plan']
    assert trace['memory']['1']['referral']=='R3'
    assert session['rounds'][0]['referral_pred']=='R3'
    assert trace['plans']['1']['plan']['referral_advice']
    assert any('第 1 轮记忆' in m[-1]['content'] for t,m,s in llm.calls if s['round']==2)
    assert_valid(session,v)


def test_merged_memory_plan_failure_has_valid_frozen_fallback():
    from engine.mock_agent import MockAgentLLM
    class Agent(MockAgentLLM):
        async def complete_json(self, messages, *, task, state):
            if task=='memory_plan': raise ValueError('malformed')
            return await super().complete_json(messages,task=task,state=state)
    deps=deps_for(llm=Agent());deps.config['pipeline']['merge_memory_plan']=True
    session,trace=run(deps,visitor('A-003'))
    assert session['status']=='completed'
    assert any(f['task']=='memory_plan' for f in trace['fallbacks'])
    assert trace['memory']['1']['referral']=='R3'
    assert trace['plans']['1']['plan']['referral_advice']
    assert_valid(session,visitor('A-003'))


def test_ds_thinking_disabled_for_response_and_high_for_plan():
    import asyncio
    from types import SimpleNamespace as NS
    from engine.llm import DsFlashClient
    from engine.config import load_config
    seen=[]
    async def create(**kw):
        seen.append(kw)
        return NS(choices=[NS(finish_reason='stop',message=NS(content='{}'))],usage=None)
    client=DsFlashClient(load_config()['agent_llm'],client=NS(chat=NS(completions=NS(create=create))))
    async def check():
        for task in ('response','strategy','select','memory','memory_plan','plan'):
            await client.complete_json([],task=task,state={})
    asyncio.run(check())
    assert all(k['extra_body']['thinking']['type']=='disabled' for k in seen[:4])
    assert all(k['reasoning_effort']=='high' for k in seen[4:])


def test_classifier_jev_failure_uses_ds_and_skips_alternate_action_but_refreshes_final():
    import asyncio
    from engine.classifier import FallbackPathClassifier, make_state, uniform_state
    from engine.session import _Round
    class Primary:
        calls=0
        async def classify(self,dialogue):
            self.calls+=1
            return uniform_state('timeout','jev',6000)
    class DS:
        calls=0
        async def classify(self,dialogue):
            self.calls+=1
            return make_state({'P1':1,'P2':8,'P3':1,'P4':1,'P5':1},'cooperative','ok','ds_flash',10)
    primary,ds=Primary(),DS()
    runner=SessionRunner(deps_for(classifier=FallbackPathClassifier(primary,ds)),visitor(),'cadence')
    runner.rounds.append(_Round(1))
    async def check():
        for _ in range(4):
            runner._add('visitor','没有更多信息。')
            assert (await runner._classify(runner.entries)).top=='P2'
        assert primary.calls==ds.calls==2
        runner._add('visitor','收尾补充。')
        assert (await runner._classify_current()).top=='P2'
        assert primary.calls==ds.calls==3
    asyncio.run(check())
    assert len(runner.trace['classifier_reuse'])==2


def test_request_budget_counts_across_instances_and_blocks_before_send(tmp_path):
    from engine.integ_trial import RequestBudget, RequestBudgetExceeded
    path=tmp_path/'calls.log'
    RequestBudget(path,2).reserve()
    RequestBudget(path,2).reserve()
    with pytest.raises(RequestBudgetExceeded): RequestBudget(path,2).reserve()
    assert len(path.read_text().splitlines())==2


def test_all_forbidden_text_is_omitted_without_blank_transcript():
    bad='我能诊断失眠症。'
    llm=ScriptedLLM(lambda s,m:{'action':'say','text':bad},response=lambda s,m:{'text':bad,'acts':[]})
    session,trace=run(deps_for(llm=llm),visitor())
    assert session['status']=='completed'
    assert all(t['text'].strip() for r in session['rounds'] for t in r['transcript'])
    assert all(not check_text(t['text']) for r in session['rounds'] for t in r['transcript'] if t['speaker']=='agent')
    assert_valid(session,visitor())


def test_http_budget_exhaustion_is_visible_and_does_not_send(tmp_path):
    import asyncio
    from engine.integ_trial import RequestBudget, RequestBudgetExceeded, Meter
    class Client:
        async def send(self, request):
            raise AssertionError('network must not be reached')
    meter=Meter(RequestBudget(tmp_path/'empty.log',0))
    with meter.watch_http(Client), pytest.raises(RequestBudgetExceeded):
        asyncio.run(Client().send(None))
    assert meter.summary()['budget_blocked']==1
    assert meter.summary()['http_attempts']==0


def test_budget_exhaustion_cannot_pass_live_evaluation_gate():
    from engine.integ_trial import mark_budget_incomplete
    report={'veto':{'passed':True,'reasons':[]}}
    accounting={'evaluation_complete':True}
    mark_budget_incomplete(report,accounting,1)
    assert report['veto']['passed'] is False
    assert accounting['evaluation_complete'] is False
    assert accounting['real_api_validation_complete'] is False
    assert accounting['incomplete_reason']=='request_budget_exhausted'
    mark_budget_incomplete(None,accounting,1)
