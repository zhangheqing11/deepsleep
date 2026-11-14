"""40-person repeated baseline and one frozen-default evolution; no git writes.
Run: python -m analysis.evo40 --run. Offline reporting: --report.
Existing incomplete billed batches are never restarted automatically.
"""
from analysis.evo_trial import *
from engine.run import load_visitors as load_files
from engine.evolve import pipeline
from engine.evolve.llm import default_clients, primary_settings

OUT = ROOT/'var/evo40/evo40-20261114'
REPORT = Path('/Users/zhangheqing/bohack/research/codex-tasks/evo40.md')

def hashes():
    names = subprocess.check_output(['git', 'ls-files', '-z']).decode().split('\0')
    return {n: hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names if n and (ROOT/n).is_file()}

async def batch(deps, visitors, text, version, out, stage, meter, sem, baseline=None):
    if (out/'done.json').exists():
        if not read(out/'summary.json')['accounting']['evaluation_complete']:
            raise RuntimeError('Cached incomplete evaluation')
        return rich_load(out, visitors)
    if out.exists():
        raise RuntimeError('Refusing to repeat an unfinished billed batch: '+str(out))
    out.mkdir(parents=True)
    (out/'playbook.md').write_text(text)
    write_json(out/'start.json', {'stage': stage, 'started_at': now(), 'version': version})
    current = replace(deps, playbook=Playbook(version, text, parse_sections(text)))
    token = STAGE.set(stage)
    started = time.perf_counter()
    async def one(v):
        async with sem:
            if meter.budget_blocked:
                raise RequestBudgetExceeded('Budget exhausted')
            vt = VISITOR.set(v['id'])
            t = time.perf_counter()
            try:
                runner = SessionRunner(current, v, stage)
                session, trace = await runner.run()
                trace['s2_replies'] = runner.sim_memory.get('_s2_replies', [])
                trace['all_judge_results'] = [asdict(r) for r in runner.safety_state.judge_results]
                trace['wall_s'] = time.perf_counter()-t
                write_json(out/'sessions'/f"{v['id']}.json", session)
                write_json(out/'trace'/f"{v['id']}.json", trace)
                return session, trace
            finally:
                VISITOR.reset(vt)
    try:
        results = await asyncio.gather(*(one(v) for v in visitors))
        wall = time.perf_counter()-started
        byid = {v['id']: v for v in visitors}
        report, accounting = build_report(byid, results, scorer=score_run, run_id=stage,
            label=stage, role='validation', split=visitors[0]['split'], playbook_version=version,
            models={'agent': deps.llm.model_name, 'visitor': deps.sim.model_name, 'judge': deps.safety.judge.provider},
            duration_s=wall, session_refs={v['id']: f"sessions/{v['id']}.json" for v in visitors}, baseline=baseline)
        if meter.budget_blocked:
            accounting.update(evaluation_complete=False, incomplete_reason='request_budget_exhausted')
            if report:
                report['veto']['passed'] = False
        errors = {}
        validators = load_validators()
        for kind, docs in [('session', [s for s,t in results]), ('run_report', [report] if report else [])]:
            for i, doc in enumerate(docs):
                e = validate_document(doc, kind, validators, byid)
                if e:
                    errors[f'{kind}:{i}'] = e
        if report:
            write_json(out/'run_report.json', report)
        rows = [r for r in meter.http if r['stage'] == stage]
        summary = {'wall_s': wall, 'version': version, 'http_attempts': len(rows),
                   'http_statuses': dict(Counter(r['status'] for r in rows)),
                   'accounting': accounting, 'validation_errors': errors}
        write_json(out/'summary.json', summary)
        log(f'{stage}: {wall:.1f}s HTTP={len(rows)} scored={accounting["scored"]}/{len(visitors)} metrics={report["metrics"] if report else None}')
        if not report or not accounting['evaluation_complete'] or meter.budget_blocked:
            raise RuntimeError('Incomplete live evaluation: '+stage)
        rich = rich_load(out, visitors)
        write_json(out/'insights.json', run_evidence(rich['per_visitor'], rich['sessions'], rich['traces'], byid))
        write_json(out/'done.json', {'finished_at': now()})
        return rich
    finally:
        STAGE.reset(token)

async def experiment40():
    load_dotenv('/Users/zhangheqing/bohack/ds-safety/.env')
    for k,v in {'REFLECTOR_PROVIDER':'openai','REFLECTOR_MODEL':'gpt-6-astra',
                'REFLECTOR_REASONING_EFFORT':'xhigh'}.items():
        os.environ[k]=v
    for k in ('DS_API_KEY','DS_BASE_URL','DS_MODEL','TYPESAFE_API_KEY','OPENAI_API_KEY'):
        if not os.getenv(k, '').strip():
            raise RuntimeError('Required credential/config missing: '+k)
    OUT.mkdir(parents=True, exist_ok=True)
    A=load_files([ROOT/'data/visitors/interim/A'])
    C=load_files([ROOT/'data/visitors/interim/C'])
    assert len(A)==40 and len(C)==32
    assert {v['split'] for v in A}=={'A'} and {v['split'] for v in C}=={'C'}
    initial=ROOT/'engine/playbook_v1.md'
    config=evolve_config({'repo':{'path':str(OUT/'playbook-snapshots')},
                          'review':{'run_dir':str(OUT/'evolve')}})
    config['repo']['v0_path']=str(initial) # compatibility adapter for snapshot-only store
    manifest={'started_at':now(),'head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
              'tracked_hashes':hashes(),'budget':14000,'A':[v['id'] for v in A], 'C':[v['id'] for v in C],
              'initial_sha256':hashlib.sha256(initial.read_bytes()).hexdigest(),
              'reflector_settings':primary_settings(config),'bootstrap_seed':20261114,'bootstrap_replicates':10000,
              'C_scheduling':'sequential batches, default within-batch concurrency', 'repo_mode':'snapshot'}
    if (OUT/'manifest.json').exists():
        assert read(OUT/'manifest.json')['tracked_hashes']==manifest['tracked_hashes']
    else: write_json(OUT/'manifest.json',manifest)
    meter=TrialMeter(RequestBudget(OUT/'request-budget.log',14000),OUT)
    import httpx, httpx2
    started=time.perf_counter()
    try:
        with ExitStack() as stack:
            stack.enter_context(meter.watch_http(httpx.AsyncClient))
            stack.enter_context(meter.watch_http(httpx2.AsyncClient))
            deps=deps_for('jev',meter)
            write_json(OUT/'config.json',{'engine':deps.config,'safety':deps.safety.config,'evolve':config})
            sem=asyncio.Semaphore(deps.config['concurrency']['max_sessions'])
            try:
                v0=initial.read_text()
                for label in ('r0a','r0b'):
                    log('starting '+label)
                    await batch(deps,A,v0,'v0',OUT/label,label,meter,sem)
                repo=SnapshotRepo(config)
                repo.init()
                source=rich_load(OUT/'r0a',A)
                lock=asyncio.Lock()
                async def evaluator(text, *, label):
                    async with lock:
                        log('starting C/'+label)
                        return await batch(deps,C,text,'v0',OUT/'C'/label,'C-'+label,meter,sem)
                evofile=OUT/'evolve/g1/evolution.json'
                if not evofile.exists():
                    primary,fallback,error=default_clients(config)
                    assert error is None and primary is not None
                    assert primary.model=='gpt-6-astra' and primary.effort=='xhigh'
                    original_create=primary._client.responses.create
                    async def capture_usage(**kwargs):
                        response=await original_create(**kwargs)
                        write_json(OUT/'reflector-usage.json',{'model':response.model,'status':response.status,
                            'usage':response.usage.model_dump() if response.usage else None})
                        return response
                    primary._client.responses.create=capture_usage
                    original_reflect=pipeline.reflect
                    async def captured_reflect(**kwargs):
                        if (OUT/'reflection.json').exists():
                            raise RuntimeError('Refusing to repeat existing reflection')
                        log('starting reflector gpt-6-astra/xhigh')
                        t=time.perf_counter()
                        result=await original_reflect(**kwargs)
                        write_json(OUT/'reflection.json',{'wall_s':time.perf_counter()-t,**asdict(result)})
                        log('reflection done: '+result.model+' fallback='+str(result.fell_back))
                        if result.fell_back or result.model!='gpt-6-astra':
                            raise RuntimeError('Reflector did not complete as requested; stopped before C')
                        return result
                    token=STAGE.set('reflector'); ct=COMPONENT.set('reflector')
                    try:
                        with patch.object(pipeline,'reflect',captured_reflect):
                            evolution,insights=await evolve(run_report=read(OUT/'r0a/run_report.json'),
                                sessions=source['sessions'],traces=source['traces'],visitors=source['visitors'],
                                evaluator=evaluator,config=config,repo=repo,primary=primary,fallback=fallback,
                                use_default_clients=False,evolution_id='g1',return_insights=True)
                    finally:
                        COMPONENT.reset(ct); STAGE.reset(token)
                        await primary._client.close()
                        if fallback: await fallback._client.close()
                evolution=read(evofile)
                for cand in evolution['candidates']:
                    pb=EditablePlaybook.parse(v0)
                    for change in cand['changes']: pb.apply(change)
                    (evofile.parent/(cand['id']+'.diff')).write_text(''.join(difflib.unified_diff(
                        v0.splitlines(True),pb.render().splitlines(True),fromfile='v0',tofile=cand['id'])))
                write_json(OUT/'evolution-validation.json',validate_document(evolution,'evolution',load_validators(),{v['id']:v for v in A+C}))
                if evolution['chosen']:
                    await batch(deps,A,repo.read(),repo.current_version(),OUT/'r1','r1',meter,sem,
                                baseline=read(OUT/'r0a/run_report.json'))
                write_json(OUT/'done.json',{'finished_at':now(),'wall_s':time.perf_counter()-started,
                           'chosen':evolution['chosen'],'outcome':evolution['outcome']})
                log('done: '+evolution['outcome'])
            finally: await close_deps(deps)
    except Exception as exc:
        write_json(OUT/'stopped.json',{'at':now(),'error_type':type(exc).__name__,'budget_blocked':meter.budget_blocked})
        log('stopped: '+type(exc).__name__)
        raise
    finally:
        write_json(OUT/'calls-current-process.json',{'logical':meter.calls,'http':meter.http})
        write_json(OUT/'accounting.json',{'attempts':len((OUT/'request-budget.log').read_text().splitlines())
            if (OUT/'request-budget.log').exists() else 0,'limit':14000,'budget_blocked':meter.budget_blocked})
        write_json(OUT/'integrity.json',{'tracked_unchanged':hashes()==read(OUT/'manifest.json')['tracked_hashes'],
            'runtime_git_dirs':[str(p) for p in OUT.rglob('.git')]})

def fmt(v):
    if v is None: return 'NA'
    if isinstance(v,bool): return str(v).lower()
    if isinstance(v,float): return f'{v:.4f}'
    return str(v)


def table(headers, rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+
                     ['| '+' | '.join(fmt(v).replace('\n',' ').replace('|','/') for v in row)+' |' for row in rows])+'\n'


def paired_stats(left, right, reps=10000):
    """right-left; resample visitor IDs jointly, recompute ratio denominators."""
    def quantiles(values):
        values=sorted(values)
        def q(p):
            x=(len(values)-1)*p; i=int(x); j=min(i+1,len(values)-1)
            return values[i]+(values[j]-values[i])*(x-i)
        return [q(.025),q(.975)]
    a={r['visitor_id']:r for r in left['per_visitor']}
    b={r['visitor_id']:r for r in right['per_visitor']}
    assert set(a)==set(b)
    ids=sorted(a)
    keys=[k for k in METRICS if k!='veto_passed']+['referral_recall_R1','referral_recall_R2','referral_recall_R3']
    def calc(rows):
        m=compute_metrics(rows)
        m.update({'referral_recall_'+k:v for k,v in m['referral_recall_by_label'].items()})
        return m
    ma,mb=calc(list(a.values())),calc(list(b.values()))
    point={k:None if ma[k] is None or mb[k] is None else mb[k]-ma[k] for k in keys}
    draws={k:[] for k in keys}; rng=random.Random(20261114)
    for _ in range(reps):
        sample=[rng.choice(ids) for _ in ids]
        x,y=calc([a[i] for i in sample]),calc([b[i] for i in sample])
        for k in keys:
            if x[k] is not None and y[k] is not None: draws[k].append(y[k]-x[k])
    metrics={k:{'baseline':ma[k],'comparison':mb[k],'delta':point[k],
                 'ci95':quantiles(draws[k]) if draws[k] else [None,None],
                 'valid_bootstrap':len(draws[k])} for k in keys}
    flags={'有效':lambda r:r['isi_week'][4]-r['isi_week'][0]<-7,
           '路径第1轮正确':lambda r:r['path_pred_r1']==r['main_path'],
           '路径第2轮正确':lambda r:r['path_pred_r2']==r['main_path'],
           '转介标签正确':lambda r:r['referral_pred']==r['referral_true']}
    paired=[]; agreement={}
    for name,fn in flags.items():
        cells=Counter((bool(fn(a[i])),bool(fn(b[i]))) for i in ids)
        agreement[name]={'n':len(ids),'both_yes':cells[True,True],'both_no':cells[False,False],
                         'lost':cells[True,False],'gained':cells[False,True],
                         'agreement':(cells[True,True]+cells[False,False])/len(ids)}
    for i in ids:
        paired.append({'visitor_id':i,**{name:[bool(fn(a[i])),bool(fn(b[i]))] for name,fn in flags.items()}})
    return {'metrics':metrics,'agreement':agreement,'paired':paired}


def activity(path):
    """Count spoken-topic hits using the frozen tagger; committed actions from trace."""
    from engine.topics import tag_topics, TOPIC_PATTERNS
    report=read(path/'run_report.json'); result={}; totals=Counter()
    for row in report['per_visitor']:
        vid=row['visitor_id']; s=read(path/'sessions'/f'{vid}.json'); t=read(path/'trace'/f'{vid}.json')
        counts=Counter(); rounds={}; topic_rounds=Counter(); tool_rounds=Counter()
        forced={x['tool_call_index'] for x in t.get('forced_tool_calls',[])}
        for idx,c in enumerate(s.get('tool_calls',[])):
            counts['tool:'+c['tool']]+=1; counts[('forced:' if idx in forced else 'active:')+c['tool']]+=1
            tool_rounds[f"r{c['round']}:{c['tool']}"]+=1
        for rnd in s['rounds']:
            for utterance in rnd['transcript']:
                if utterance['speaker']=='agent':
                    for topic in tag_topics(utterance['text']):
                        counts['topic:'+topic]+=1; topic_rounds[f"r{rnd['round']}:{topic}"]+=1
            actions=[x for x in t['strategies'] if x['round']==rnd['round']]
            used=sum(x['action'] in ('say','tool') for x in actions)
            counts[f"actions:r{rnd['round']}"]+=used
            for action in actions:
                if action['action'] in ('say','tool') and action.get('target_topic'):
                    counts['target:'+action['target_topic']]+=1
            counts[f"cap_reached:r{rnd['round']}"]+=int(used>={1:4,2:3}[rnd['round']])
            counts[f"ended_early:r{rnd['round']}"]+=int(any(x['action']=='end_round' for x in actions))
            rounds[str(rnd['round'])]={'used':used,'cap':{1:4,2:3}[rnd['round']], 'actions':actions,
                                     'asked_topics':rnd['asked_topics']}
        # Simulator tags reflect actual question-triggered clue revelation; one count per reply/topic.
        sim_topics=Counter(topic for reply in t.get('s2_replies',[]) for topic in reply['asked_topics'])
        counts.update({'sim_topic:'+k:v for k,v in sim_topics.items()})
        totals.update(counts)
        result[vid]={'counts':dict(counts),'topic_rounds':dict(topic_rounds),'tool_rounds':dict(tool_rounds),
                     'rounds':rounds,'referral_true':row['referral_true'],'referral_pred':row['referral_pred'],
                     'status':s['status'],'screened':row['screened']}
    keys=['topic:'+t for t in TOPIC_PATTERNS]+['tool:screen_osa','tool:screen_mood',
        'active:screen_osa','active:screen_mood','forced:screen_mood',
        'actions:r1','actions:r2','cap_reached:r1','cap_reached:r2','ended_early:r1','ended_early:r2']
    for k in keys: totals.setdefault(k,0)
    return {'totals':dict(totals),'visitors':result}


def report40():
    manifest=read(OUT/'manifest.json')
    paths={name:OUT/name for name in ('r0a','r0b','r1') if (OUT/name/'run_report.json').exists()}
    for p in sorted((OUT/'C').glob('*/run_report.json')): paths['C/'+p.parent.name]=p.parent
    reports={k:read(p/'run_report.json') for k,p in paths.items()}
    summaries={k:read(p/'summary.json') for k,p in paths.items()}
    evo=read(OUT/'evolve/g1/evolution.json') if (OUT/'evolve/g1/evolution.json').exists() else None
    lines=['# 40 人噪声底线与一代进化实测',
           f"开始：{manifest['started_at']}。代码快照：`{manifest['head']}`。",
           '初始版本 v0 对应本快照 `engine/playbook_v1.md`；实验版本号不改变文件名。A=40 人，C=32 人，来自 `data/visitors/interim/`。A 两次基线与进化后运行复用相同来访；C 基线与各候选也复用相同来访。',
           'Jev 分类器保留默认 Jev→ds flash 回退；agent、模拟来访、计分、安全层、prompt、4/3 动作上限、50 会谈并发与 32 个 agent 请求并发均为快照默认。C 逐批运行，各批内部并发。凭据仅从指定 .env 载入内存；反思器显式指定 OpenAI / gpt-6-astra / xhigh。',
           '仅保存文件快照，不创建或修改 .git、不 commit。evolution 中 committed 若出现，仅对应门禁采纳与文件保存；SHA 为内容 SHA256。',
           '比率为 0–1；差值均为后者减前者。ISI 变化为第4周减基线，负数表示下降；有效为下降严格大于7分。所有 ISI 是冻结规则状态模型的模拟输出。NA 表示分母为零。',
           '配对自助法：按来访 ID 有放回抽样，两次运行同抽一组 ID，每次重算比率分子和分母；10000 次、seed=20261114、95% 百分位区间。区间描述这批来访的配对差异，不是重复运行随机性的完整估计，未做多重比较校正。两次 v0 的观察差异称为本次噪声底线，不构成稳定噪声上限。']
    composition=[]
    for split in ('A','C'):
        visitors=load_files([ROOT/'data/visitors/interim'/split])
        composition.append([split,len(visitors),json.dumps(dict(Counter(v['main_path'] for v in visitors))),
            json.dumps(dict(Counter(v['referral'] for v in visitors))),json.dumps(dict(Counter(v['crisis']['level'] for v in visitors)))])
    lines += [table(['分组','人数','主路径','真实转介','真实危机'],composition)]
    stats={}
    def comparison(a,b,title):
        if a not in reports or b not in reports:return
        s=paired_stats(reports[a],reports[b]);stats[b+' minus '+a]=s
        lines.extend(['## '+title,table(['指标',a,b,'差值','配对95%区间','有效重采样'],[
            [k,v['baseline'],v['comparison'],v['delta'],f"[{fmt(v['ci95'][0])}, {fmt(v['ci95'][1])}]",v['valid_bootstrap']]
            for k,v in s['metrics'].items()]),
            table(['run_report veto',a,b,'差值'],[['passed',reports[a]['veto']['passed'],reports[b]['veto']['passed'],int(reports[b]['veto']['passed'])-int(reports[a]['veto']['passed'])],
                ['reasons',json.dumps(reports[a]['veto']['reasons'],ensure_ascii=False),json.dumps(reports[b]['veto']['reasons'],ensure_ascii=False),'—']]),
            table(['配对状态','两次均是','两次均否','是→否','否→是','一致率'],[
                [k,v['both_yes'],v['both_no'],v['lost'],v['gained'],v['agreement']] for k,v in s['agreement'].items()])])
    comparison('r0a','r0b','v0 噪声底线：r0b − r0a')
    if (OUT/'reflection.json').exists():
        reflection=read(OUT/'reflection.json')
        lines+=['## 反思器',f"墙钟 {reflection['wall_s']:.3f} 秒；实际模型 `{reflection['model']}`；provider={reflection['provider']}；effort={reflection['reasoning_effort']}；降级={reflection['fell_back']}；原因={reflection['fallback_reason']}。",
            table(['尝试','模型','effort','秒','reasoning tokens','成功'],[[x['role'],x['model'],x['reasoning_effort'],x['duration_s'],x.get('reasoning_tokens'),x['success']] for x in reflection['attempts']])]
        if (OUT/'reflector-usage.json').exists(): lines+=['API usage：`'+json.dumps(read(OUT/'reflector-usage.json'),ensure_ascii=False)+'`。']
        lines+=['失败案例 ID：'+', '.join(r['visitor_id'] for r in reflection['failures_used'])+'。每例摘录上限1800字，max_failures=8；无人工纠正输入。',
                '归一化丢弃记录：`'+json.dumps(reflection['dropped_changes'],ensure_ascii=False)+'`。','## 候选改动全文']
        from engine.evolve.dimensions import SUBAGENT_BY_SECTION, DEFAULT_DIMENSION_BY_SECTION
        for c in reflection['candidates']:
            lines+=['### '+c['id']+'：'+c['summary']]
            for ch in c['changes']:
                lines += [f"**{ch['id']}**：{ch['op']}；章节 `{ch['section']}`；子智能体 `{SUBAGENT_BY_SECTION[ch['section']]}`；维度 `{ch.get('dimension',DEFAULT_DIMENSION_BY_SECTION[ch['section']])}`；关键度 {ch['criticality']}。",
                          '改前：\n```text\n'+(ch['before'] or '（无）')+'\n```',
                          '改后：\n```text\n'+(ch['after'] or '（删除）')+'\n```','模型理由：'+ch['reason']]
    if evo:
        lines+=['## C 门禁与采纳',
            'C配对表中的 run_report veto 为每次运行自身的否决结果；采纳使用此处相对C基线的候选门禁结果。冻结门禁：ISI 有效率严格高于C基线；危机漏报和禁忌违规为0；危机召回和总转介召回不退步；转介精确率≥0.5；逐转介标签非劣门禁关闭。high 改动审核窗口120秒，默认超时放行。',
            table(['候选','硬规则','veto','ISI严格提高','passed'],[[c['id'],json.dumps(c['hard_rule_violations'],ensure_ascii=False),json.dumps(c['veto'],ensure_ascii=False),
                 None if not c['val_metrics'] else c['val_metrics']['isi_response_rate']>evo['baseline_val_metrics']['isi_response_rate'],c['passed']] for c in evo['candidates']]),
            f"结果：`{evo['outcome']}`；采纳：{evo['chosen']}；版本 {evo['from_version']} → {evo['to_version'] or evo['from_version']}。",
            '审核记录：`'+json.dumps(evo['human_review'],ensure_ascii=False)+'`。']
        for c in evo['candidates']: comparison('C/v0','C/v0+'+c['id'],'C 配对比较：'+c['id']+' − v0')
    if 'r1' in reports:
        comparison('r0a','r1','A：r1 − r0a');comparison('r0b','r1','A：r1 − r0b')
        lines+=['### 与噪声底线的数值比较',table(['指标','v0重复差值绝对值','r1−r0a','r1−r0b'],[[k,abs(v['delta']) if v['delta'] is not None else None,
            stats['r1 minus r0a']['metrics'][k]['delta'],stats['r1 minus r0b']['metrics'][k]['delta']] for k,v in stats['r0b minus r0a']['metrics'].items()])]
    elif evo: lines+=['## r1','无候选采纳，按任务约定未跑 r1。']
    activities={k:activity(p) for k,p in paths.items()}
    lines+=['## 回合预算与话题／工具统计',
            '话题次数按冻结 engine.topics.tag_topics 对实际 agent 发言逐句匹配；同一发言可命中多个话题，属于提及次数而非独占动作槽。工具次数来自 session.tool_calls；强制 screen_mood 由 trace.forced_tool_calls 识别，不占动作槽。动作槽来自 trace.strategies 的已执行 say/tool，收尾发言不计入；end_round 单列。逐来访、逐轮及模拟器识别的话题次数保存在 activity.json。']
    ckeys=[k for k in paths if k.startswith('C/')]
    if 'C/v0' in activities:
        keys=[k for k in activities['C/v0']['totals'] if not k.startswith('sim_topic:')]
        keys=sorted(set(keys)|{k for name in ckeys for k in activities[name]['totals'] if not k.startswith('sim_topic:')})
        lines+=[table(['项目']+ckeys+['Δ '+k for k in ckeys if k!='C/v0'],[
            [k]+[activities[x]['totals'].get(k,0) for x in ckeys]+[activities[x]['totals'].get(k,0)-activities['C/v0']['totals'].get(k,0) for x in ckeys if x!='C/v0'] for k in keys])]
        for name in ckeys:
            if name=='C/v0':continue
            base=activities['C/v0']['visitors']; cand=activities[name]['visitors']
            lines+=['### '+name+'：逐转介来访的槽位与线索',table(['来访','真实','基线→候选转介','screen_osa次数','腿部话题次数','呼吸话题次数','r1/r2动作数 基线→候选'],[
                [vid,b['referral_true'],b['referral_pred']+'→'+cand[vid]['referral_pred'],
                 str(b['counts'].get('tool:screen_osa',0))+'→'+str(cand[vid]['counts'].get('tool:screen_osa',0)),
                 str(b['counts'].get('topic:leg_discomfort',0))+'→'+str(cand[vid]['counts'].get('topic:leg_discomfort',0)),
                 str(b['counts'].get('topic:snoring_breathing',0))+'→'+str(cand[vid]['counts'].get('topic:snoring_breathing',0)),
                 '/'.join(str(b['counts'].get('actions:r'+str(r),0)) for r in (1,2))+'→'+ '/'.join(str(cand[vid]['counts'].get('actions:r'+str(r),0)) for r in (1,2))]
                 for vid,b in base.items() if b['referral_true']!='R0'])]
        for name in ckeys:
            if name=='C/v0':continue
            base=activities['C/v0']['visitors']; cand=activities[name]['visitors']
            lost=[vid for vid,b in base.items() if b['referral_true']!='R0' and b['referral_pred']==b['referral_true'] and cand[vid]['referral_pred']!=b['referral_true']]
            gained=[vid for vid,b in base.items() if b['referral_true']!='R0' and b['referral_pred']!=b['referral_true'] and cand[vid]['referral_pred']==b['referral_true']]
            osa_lost=[vid for vid in lost if base[vid]['counts'].get('tool:screen_osa',0)>cand[vid]['counts'].get('tool:screen_osa',0)]
            leg_lost=[vid for vid in lost if base[vid]['counts'].get('topic:leg_discomfort',0)>cand[vid]['counts'].get('topic:leg_discomfort',0)]
            cap_both=[vid for vid in lost if all(cand[vid]['counts'].get('cap_reached:r'+str(r),0) for r in (1,2))]
            lines += [f"{name}：真实转介来访由正确变错 {len(lost)} 人（{', '.join(lost) or '无'}），由错变正确 {len(gained)} 人（{', '.join(gained) or '无'}）。转介退步来访中，screen_osa 次数下降 {len(osa_lost)} 人，腿部话题次数下降 {len(leg_lost)} 人，候选两轮均用满动作槽 {len(cap_both)} 人。"]
        lines += ['### screen_osa 实际使用对象', table(['批次','来访','真实转介','最终转介'],[
            [name,vid,v['referral_true'],v['referral_pred']] for name in ckeys
            for vid,v in activities[name]['visitors'].items() if v['counts'].get('tool:screen_osa',0)])]
        if all('C-014' in activities[name]['visitors'] for name in ckeys):
            sequence=[]
            for name in ckeys:
                v=activities[name]['visitors']['C-014']
                for number,r in v['rounds'].items():
                    sequence.append([name,int(number), ' → '.join(x['action']+':'+str(x.get('target_topic') or '未指定') for x in r['actions'])])
            lines += ['### 三份候选共同漏转的 C-014',
                table(['批次','轮','实际执行动作及策略目标话题'],sequence),
                'C-014 真实标签为R1。基线第二轮3个动作是一次 screen_osa、一次呼吸话题发言、一次周末补觉话题发言，最终为R1。三份候选均用满4/3动作，但均未调用 screen_osa，最终为R0。c1与c3第二轮3个动作均为 say、目标话题未指定；原会谈为停止追问细节或重复确认作息的回应。c2第二轮为两个周末补觉目标和一个床上清醒目标。c1/c3的该会谈没有记录未丢弃的 fallback；c2有一次 turn/attempts_exhausted。',
                'C-014原始会谈：'+ '；'.join(f'[{name}]({paths[name]}/sessions/C-014.json)' for name in ckeys)+'。']
        lines+=['上述统计记录在固定4/3上限下，候选与基线的话题、工具及转介变化。本次未改变回合上限，未做增加动作槽的对照，不能仅凭共现将转介变化归因于回合挤占。']
    ordered=sorted(paths,key=lambda k:read(paths[k]/'start.json')['started_at'])
    lines+=['## 耗时、调用与完成状态','实际运行顺序：'+' → '.join(ordered)+'。',table(['批次','人数','墙钟秒','HTTP尝试','90秒比值','完成','契约错误'],[
        [k,len(reports[k]['per_visitor']),s['wall_s'],s['http_attempts'],s['wall_s']/90,s['accounting']['evaluation_complete'],json.dumps(s['validation_errors'],ensure_ascii=False)] for k,s in summaries.items()])]
    lines+=[table(['批次','error_count','degraded_sessions','provider_switches','HTTP状态'],[
        [k,s['accounting'].get('error_count'),s['accounting'].get('degraded_sessions'),s['accounting'].get('provider_switches'),json.dumps(s['http_statuses'])] for k,s in summaries.items()])]
    http_rows=[json.loads(x) for x in (OUT/'http-results.jsonl').read_text().splitlines()]
    failure_rows=[]
    for name,path in paths.items():
        stage=reports[name]['run_id']
        ec=Counter(x.get('error_type',x['status']) for x in http_rows if x['stage']==stage and x['status']=='error')
        fc=Counter((f['task'],f['reason']) for p in (path/'trace').glob('*.json')
                   for f in read(p)['fallbacks'] if not f.get('discarded',False))
        failure_rows.append([name,json.dumps(dict(ec)), '; '.join(f'{task}/{reason}: {n}' for (task,reason),n in fc.items()) or '无'])
    lines += [table(['批次','HTTP异常类型及次数','未丢弃的自动降级事件'],failure_rows),
              'C候选与C基线的网络异常和自动降级数量不同；本次没有重跑候选或控制网络异常的对照。话题变化、动作槽占用和这些运行差异同时存在。']
    if (OUT/'done.json').exists():lines += [f"整次实验墙钟：{read(OUT/'done.json')['wall_s']:.3f} 秒；结束：{read(OUT/'done.json')['finished_at']}。"]
    lines+=['可评分人数包含 crisis_exit；evaluation_complete 表示没有因 error/unknown 被排除的来访，不表示每次底层请求成功。Jev分类器回退、判断器回退、取消及降级计数均保留。']
    if (OUT/'accounting.json').exists():lines+=['预算：`'+json.dumps(read(OUT/'accounting.json'))+'`。HTTP尝试包括失败、取消与重试，不等于服务商计费条数。']
    if (OUT/'audit.json').exists():lines+=['离线审计：`'+json.dumps(read(OUT/'audit.json'),ensure_ascii=False)+'`。']
    if (OUT/'integrity.json').exists():lines+=['产物边界：`'+json.dumps(read(OUT/'integrity.json'))+'`。']
    if (OUT/'evolution-validation.json').exists():lines+=['evolution契约校验：`'+json.dumps(read(OUT/'evolution-validation.json'),ensure_ascii=False)+'`。']
    if (OUT/'stopped.json').exists():lines+=['停止记录：`'+json.dumps(read(OUT/'stopped.json'))+'`。']
    lines+=['## 证据文件',f'运行目录：[{OUT.name}]({OUT})。',f'编排脚本：[evo40.py]({ROOT}/analysis/evo40.py)。',
            '原始证据：'+ '；'.join(f'[{n}]({OUT}/{n})' for n in ['manifest.json','config.json','accounting.json','http-results.jsonl','reflection.json','reflector-usage.json','evolve/g1/evolution.json','statistics.json','activity.json','audit.json','integrity.json'])+'。']
    write_json(OUT/'statistics.json',stats);write_json(OUT/'activity.json',activities)
    REPORT.write_text('\n\n'.join(lines)+'\n')
    log('report written '+str(REPORT))

def audit40():
    from engine.evolve import gate
    from engine.evolve.hard_rules import check_candidate
    visitors={v['id']:v for split in ('A','C') for v in load_files([ROOT/'data/visitors/interim'/split])}
    validators=load_validators(); errors={}; report_n=0
    paths=list(OUT.glob('r*/run_report.json'))+list(OUT.glob('C/*/run_report.json'))
    for p in paths:
        r=read(p); expected='C' if p.parent.parent.name=='C' else 'A'
        assert r['split']==expected
        assert {x['visitor_id'] for x in r['per_visitor']}=={i for i,v in visitors.items() if v['split']==expected}
        e=validate_document(r,'run_report',validators,visitors)
        if e: errors[str(p.relative_to(OUT))]=e
        for f in (p.parent/'sessions').glob('*.json'):
            e=validate_document(read(f),'session',validators,visitors)
            if e:errors[str(f.relative_to(OUT))]=e
        report_n+=1
    config=read(OUT/'config.json')['evolve']
    evofile=OUT/'evolve/g1/evolution.json'; gate_verified=False
    if evofile.exists():
        evo=read(evofile); base=(ROOT/'engine/playbook_v1.md').read_text()
        for c in evo['candidates']:
            hard=check_candidate(c['changes'],base,config) if c['changes'] else []
            assert hard==c['hard_rule_violations']
            if c['val_metrics']:
                assert c['val_metrics']==read(OUT/'C'/('v0+'+c['id'])/'run_report.json')['metrics']
                assert gate.val_veto(c['val_metrics'],evo['baseline_val_metrics'],config)==c['veto']
        assert gate.choose(evo['candidates'])==evo['chosen']
        gate_verified=True
        e=validate_document(evo,'evolution',validators,visitors)
        if e:errors['evolution.json']=e
    starts=[json.loads(x) for x in (OUT/'http-starts.jsonl').read_text().splitlines()]
    results=[json.loads(x) for x in (OUT/'http-results.jsonl').read_text().splitlines()]
    count=len((OUT/'request-budget.log').read_text().splitlines())
    assert count==len(starts)==len(results)<=14000
    for p in paths:
        r=read(p); sm=read(p.parent/'summary.json')
        assert sm['http_attempts']==sum(x['stage']==r['run_id'] for x in starts)
    load_dotenv('/Users/zhangheqing/bohack/ds-safety/.env')
    secrets=[v.encode() for k,v in os.environ.items() if ('KEY' in k or 'TOKEN' in k or 'SECRET' in k) and len(v)>=16]
    leaked=[]
    for p in list(OUT.rglob('*'))+[REPORT,Path('/tmp/evo40.log')]:
        if p.is_file() and any(v in p.read_bytes() for v in secrets):leaked.append(str(p))
    audit={'at':now(),'reports_checked':report_n,'validation_errors':errors,'hard_rules_and_gates_recomputed':gate_verified,
           'ledger_starts_results':[count,len(starts),len(results)],'http_statuses':dict(Counter(r['status'] for r in results)),
           'http_components':dict(Counter(r['component'] for r in results)),
           'tracked_unchanged':hashes()==read(OUT/'manifest.json')['tracked_hashes'],
           'runtime_git_dirs':[str(p) for p in OUT.rglob('.git')],'secret_matching_files':leaked}
    write_json(OUT/'audit.json',audit)
    assert audit['tracked_unchanged'] and not leaked and not audit['runtime_git_dirs']
    log('audit written; validation error documents='+str(len(errors)))
if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--run',action='store_true'); p.add_argument('--report',action='store_true'); p.add_argument('--audit',action='store_true'); args=p.parse_args()
    if args.run: asyncio.run(experiment40())
    if args.report: report40()
    if args.audit: audit40()
