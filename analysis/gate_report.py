"""Offline, evidence-only Chinese report for the gate stability experiment."""
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path

from analysis.gate_fix import OUT, PRIOR, BUDGET, REPORT, ROOT, fmt, table, paired_stats, hashes, read, write_json
from analysis.gate_diagnose import OLD, diagnose
from contracts.validate import load_validators, validate_document
from engine.config import load_dotenv
from engine.evolve import gate
from engine.evolve.hard_rules import check_candidate
from engine.run import load_visitors


def records(root):
    return [json.loads(x) for x in (root/'http-results.jsonl').read_text().splitlines()]


def audit():
    import os
    visitors = {v['id']: v for split in ('A','C') for v in load_visitors([ROOT/'data/visitors/interim'/split])}
    validators = load_validators()
    errors = {}
    paths = list(OUT.glob('r*/run_report.json'))+list(OUT.glob('C/*/run_report.json'))
    for path in paths:
        for p, kind in [(path, 'run_report')]+[(p, 'session') for p in (path.parent/'sessions').glob('*.json')]:
            e = validate_document(read(p), kind, validators, visitors)
            if e:
                errors[str(p.relative_to(OUT))] = e
        expected = {i for i,v in visitors.items() if v['split'] == ('C' if path.parent.parent.name == 'C' else 'A')}
        assert {r['visitor_id'] for r in read(path)['per_visitor']} == expected
    evo = read(OUT/'evolve/g1/evolution.json')
    cfg = read(OUT/'config.json')['evolve']
    base = (ROOT/'engine/playbook_v1.md').read_text()
    for candidate in evo['candidates']:
        hard = check_candidate(candidate['changes'], base, cfg) if candidate['changes'] else []
        assert hard == candidate['hard_rule_violations']
        if candidate['val_metrics']:
            assert candidate['val_metrics'] == read(OUT/'C'/('v0+'+candidate['id'])/'run_report.json')['metrics']
            assert gate.val_veto(candidate['val_metrics'], evo['baseline_val_metrics'], cfg) == candidate['veto']
    assert gate.choose(evo['candidates']) == evo['chosen']
    e = validate_document(evo, 'evolution', validators, visitors)
    if e:
        errors['evolution.json'] = e
    rows = records(OUT)
    starts = [json.loads(x) for x in (OUT/'http-starts.jsonl').read_text().splitlines()]
    count = len(BUDGET.read_text().splitlines())
    prior_count = len((PRIOR/'request-budget.log').read_text().splitlines())
    prior_rows = records(PRIOR)
    assert prior_count == len(prior_rows)
    assert count == prior_count + len(rows) <= 12000
    assert len(rows) == len(starts)
    assert len({r['id'] for r in rows}) == len(rows)
    assert max(r['inflight'] for r in rows) <= 16
    assert all(r['component'] != 'visitor' for r in rows)
    for path in paths:
        report = read(path)
        assert read(path.parent/'summary.json')['http_attempts'] == sum(r['stage']==report['run_id'] for r in rows)
    manifest = read(OUT/'manifest.json')
    source_changes = [n for n,h in manifest['source_hashes'].items()
                      if hashlib.sha256(Path(n).read_bytes()).hexdigest() != h]
    assert hashes() == manifest['tracked_hashes'] and not source_changes
    load_dotenv('/Users/zhangheqing/bohack/ds-safety/.env')
    secrets = [v.encode() for k,v in os.environ.items() if any(w in k for w in ('KEY','TOKEN','SECRET')) and len(v)>=16]
    leaked = [str(p) for p in list(OUT.rglob('*'))+list(PRIOR.rglob('*'))+[REPORT, Path('/tmp/gate-fix-run.log'),Path('/tmp/gate-fix-run-r2.log')]
              if p.is_file() and any(s in p.read_bytes() for s in secrets)]
    git_dirs = list(OUT.rglob('.git'))
    assert not leaked and not git_dirs
    result = {'reports': len(paths), 'validation_errors': errors, 'gate_recomputed': True,
              'http_starts_results_budget': [len(starts), len(rows), count], 'prior_aborted_attempts': prior_count,
              'max_inflight': max(r['inflight'] for r in rows), 'visitor_http_requests': 0,
              'source_changes_during_run': source_changes, 'tracked_unchanged_during_run': True,
              'runtime_git_dirs': [], 'secret_matching_files': leaked}
    write_json(OUT/'audit.json', result)
    return result


def render():
    diagnosis = diagnose(OUT/'diagnosis.json')
    manifest = read(OUT/'manifest.json')
    old_manifest = read(OLD/'manifest.json')
    evo = read(OUT/'evolve/g1/evolution.json')
    reflection = read(OUT/'reflection.json')
    paths = {p.parent.relative_to(OUT).as_posix(): p.parent for p in
             list(OUT.glob('r*/run_report.json'))+list(OUT.glob('C/*/run_report.json'))}
    reports = {k: read(p/'run_report.json') for k,p in paths.items()}
    stats = {'noise': paired_stats(reports['r0a'], reports['r0b'])}
    old_noise = read(OLD/'statistics.json')['r0b minus r0a']
    for c in evo['candidates']:
        if c['val_metrics']:
            stats[c['id']] = paired_stats(reports['C/v0'], reports['C/v0+'+c['id']])
    if 'r1' in reports:
        for baseline in ('r0a','r0b'):
            stats['r1-'+baseline] = paired_stats(reports[baseline], reports['r1'])
    write_json(OUT/'statistics.json', stats)
    lines = ['# 门禁稳定性修复与 A40 重测',
        f"开始：{manifest['started_at']}；基于代码 `{manifest['head']}`，分支 `zhq/evolve-gate-stability`，工作区改动未提交。上一轮代码 `{old_manifest['head']}`。",
        'A40 与 C32 复用上一轮 interim 来访文件；本次实验初始版本称 v0，对应 engine/playbook_v1.md。ISI 来自冻结规则状态模型。比率为 0–1；差值为后者减前者，mean_isi_change 为第4周减基线，负数表示下降；有效为下降严格大于7分。',
        '## 上一轮网络诊断',
        '旧账本未记录 URL、主机或精确在途数；时间戳精度为1秒。按组件、SDK和当前配置映射：会谈、来访、classifier.ds_flash、judge.ds_flash 使用 api.deepseek.com；classifier.jev、judge.jev 使用 api.typesafe.ai；反思器使用 api.openai.com。主机是配置映射推断，不是旧请求记录直接证明。',
        table(['组件','异常类型','次数'], [[r['component'],r['error'],r['count']] for r in diagnosis['errors']]),
        '988 次 ConnectError 中，按上述映射 ds flash 为899次、TypeSafe 为89次；OpenAI反思器0次；Jev安全判断器0次。另有来访渲染 ReadTimeout 2次。',
        '近似在途数：将每条请求开始时间置于其记录秒的起点，以该时刻加耗时估计结束时间，再计算开始时未结束的请求数。同一秒内请求被归到同一时刻，因此下表不是实际峰值，也不能证明并发造成连接失败。',
        table(['旧批次','HTTP尝试','异常','近似在途中位数','近似在途最大值'], [[r[k] for k in ('stage','attempts','errors','approx_inflight_median','approx_inflight_max')] for r in diagnosis['stages']]),
        table(['近似在途区间','请求数','异常数','异常比例'], [[r['range'],r['attempts'],r['errors'],r['errors']/r['attempts']] for r in diagnosis['bins']]),
        '上一轮脚本已有 evaluator 锁，实际顺序为 r0a → r0b → c1 → c2 → c3 → C基线，并未同时评估四个C版本。本次原生门禁固定基线先行，再顺序评估候选；实验将会谈并发从50降至8、agent上限从32降至16，并在所有HTTP客户端发送层共用16在途上限。旧近似0–16区间异常7/203，作为保守选择的观察依据；无无错误阈值证据。',
        '## 代码与验证',
        'engine/evolve/pipeline.py：C基线先完成，再逐候选评估；人类审核同时运行，异常或取消时清理未结束任务。',
        'engine/network.py、llm.py、adapters_sim.py、session.py：ConnectError / ReadTimeout（含SDK显式cause包装）最多重试2次，等待0.5、1秒；可配置。请求状态错误不重试，外层解析重试不重复执行已耗尽的连接重试。重试计入客户端统计和会谈trace，HTTP账本按每次实际发送计数。安全判断器、分类器的既有回退规则未改。',
        'engine/config.yaml、config.py、run.py、demo.py、adapters_sim.py：visitor_renderer 支持 llm / template，默认llm。template 调用 S2 原有 mock_text，不请求来访LLM；保留分层线索、deny_first与跨轮状态。demo/run 提供 --visitor-renderer。',
        'analysis/gate_fix.py、gate_support.py：复用上一轮编排与统计，12000次硬预算、文件快照版本库、HTTP主机/时间/在途数账本；已付费但未完成批次不会自动重跑。',
        '测试：`/Users/zhangheqing/bohack/ds-safety/.venv/bin/python -m pytest -q --ignore=api`：1175 passed。初次定向测试56 passed（3.83秒）；最终稳定性回归18 passed（0.46秒）。`make -o .venv/.requirements-installed contracts` 通过，临时.venv符号链接指向指定现有环境，跳过环境安装；没有新增依赖。`git diff --check` 通过。',
        '新旧运行中，来访数据、sim/、scoring/、safety/、contracts/、初始playbook与prompt共151个受跟踪文件哈希相同；本次未修改这些文件。未修改工作树.git、未commit；实验版本使用文件内容SHA256。现有版本库单元测试在pytest临时目录验证git行为。',
        '首次修复运行使用httpx异常类型，审计发现当前OpenAI SDK实际使用httpx2，连接重试未命中。该次运行已停止并保留2293次HTTP账本；修复为兼容两套异常类后，重新完整运行A40两次及一代进化。首次修复运行不纳入下列噪声比较，2293次请求仍计入12000次总预算。',
        '## 新旧噪声底线',
        '两次v0的观察差异不等于噪声上限。本次同时改变渲染、重试和并发，并在不同时间运行；新旧差异不能单独归因于template。配对自助法按相同来访ID同步抽样，10000次，seed=20261114，95%百分位区间，未做多重比较校正。',
        table(['指标','旧r0a','旧r0b','旧差值','新r0a','新r0b','新差值','新配对95%区间'], [
            [k,old_noise['metrics'][k]['baseline'],old_noise['metrics'][k]['comparison'],old_noise['metrics'][k]['delta'],
             v['baseline'],v['comparison'],v['delta'],str(v['ci95'])] for k,v in stats['noise']['metrics'].items()]),
        table(['配对状态','旧一致率','新一致率','新是→否','新否→是'], [[k,old_noise['agreement'][k]['agreement'],v['agreement'],v['lost'],v['gained']] for k,v in stats['noise']['agreement'].items()]),
        '## 一代进化与门禁',
        f"反思器实际模型：{reflection['model']}；provider={reflection['provider']}；effort={reflection['reasoning_effort']}；墙钟{reflection['wall_s']:.3f}秒；fallback={reflection['fell_back']}。失败案例："+', '.join(x['visitor_id'] for x in reflection['failures_used'])+'。无人工纠正输入。',
        '门禁保持原配置：ISI有效率严格提高；危机漏报和禁忌违规为0；危机召回和总转介召回不退步；转介精确率至少0.5；逐转介标签非劣门禁关闭。high改动审核120秒，原配置超时放行。',
        table(['候选','硬规则','否决原因','通过'], [[c['id'],json.dumps(c['hard_rule_violations'],ensure_ascii=False),json.dumps(c['veto'],ensure_ascii=False),c['passed']] for c in evo['candidates']]),
        f"结果：{evo['outcome']}；采纳：{evo['chosen']}；版本：{evo['from_version']} → {evo['to_version'] or evo['from_version']}。",
        '审核记录：`'+json.dumps(evo['human_review'],ensure_ascii=False)+'`。']
    for c in evo['candidates']:
        lines += [f"### {c['id']}：{c['summary']}"]
        if c['id'] in stats:
            lines += [table(['指标','C基线','候选','配对差值','配对95%区间'], [[k,v['baseline'],v['comparison'],v['delta'],str(v['ci95'])] for k,v in stats[c['id']]['metrics'].items()])]
        lines += ['改动文件：['+c['id']+'.diff]('+str(OUT/'evolve/g1'/(c['id']+'.diff'))+')。']
    lines += ['## r1 对比']
    if 'r1' in reports:
        for baseline in ('r0a','r0b'):
            lines += [table(['指标',baseline,'r1','差值','配对95%区间'], [[k,v['baseline'],v['comparison'],v['delta'],str(v['ci95'])] for k,v in stats['r1-'+baseline]['metrics'].items()])]
    else:
        lines += ['无候选采纳，按任务条件未运行r1。']
    rows, old_rows = records(OUT), records(OLD)
    prior_rows = records(PRIOR)
    prior_span = max(datetime.fromisoformat(r['at']).timestamp()+r['ms']/1000 for r in prior_rows)-min(datetime.fromisoformat(r['at']).timestamp() for r in prior_rows)
    comparison = []
    for k,p in paths.items():
        new = read(p/'summary.json')
        old = read(OLD/k/'summary.json') if (OLD/k/'summary.json').exists() else None
        er = Counter(r.get('error_type', r['status']) for r in rows if r['stage']==reports[k]['run_id'] and r['status'] in ('error','http_error'))
        comparison.append([k,old['wall_s'] if old else None,new['wall_s'],
                           old['http_attempts'] if old else None,new['http_attempts'],
                           (old['http_statuses'].get('error',0)+old['http_statuses'].get('http_error',0)) if old else None,sum(er.values()),
                           old['accounting']['degraded_sessions'] if old else None,new['accounting']['degraded_sessions'],
                           old['accounting']['provider_switches'] if old else None,new['accounting']['provider_switches']])
    lines += ['## 网络异常、降级与耗时',
        '旧新c1/c2/c3是各自反思器生成的不同候选，仅按序号列示运行质量；不构成同一playbook的配对网络实验。cancelled单列，包含原有推测执行丢弃与超时取消，不全部视为网络故障。',
        table(['批次','旧秒','新秒','旧HTTP','新HTTP','旧异常','新异常','旧降级会谈','新降级会谈','旧provider切换','新provider切换'],comparison),
        table(['主机','组件','请求数','异常数','取消数'], [[host,comp,len(subset),sum(r['status'] in ('error','http_error') for r in subset),sum(r['status']=='cancelled' for r in subset)]
            for host,comp in sorted({(r['host'],r['component']) for r in rows})
            for subset in [[r for r in rows if (r['host'],r['component'])==(host,comp)]]]),
        table(['批次','异常类型','HTTP状态','未丢弃的降级事件'], [[k,
            json.dumps(dict(Counter(r.get('error_type',r['status']) for r in rows if r['stage']==report['run_id'] and r['status'] in ('error','http_error')))),
            json.dumps(dict(Counter(r['status'] for r in rows if r['stage']==report['run_id']))),
            json.dumps(dict(Counter(f['task']+'/'+f['reason'] for p in (paths[k]/'trace').glob('*.json') for f in read(p)['fallbacks'] if not f.get('discarded'))))] for k,report in reports.items()]),
        table(['本次实际在途数','请求数','异常数','异常比例'], [[f'{lo}–{hi}',len(subset),sum(r['status'] in ('error','http_error') for r in subset),
                sum(r['status'] in ('error','http_error') for r in subset)/len(subset) if subset else None]
            for lo,hi in ((1,4),(5,8),(9,12),(13,16)) for subset in [[r for r in rows if lo<=r['inflight']<=hi]]]),
        f"本次实际在途峰值：{max(r['inflight'] for r in rows)}。来访LLM请求数：{sum(r['component']=='visitor' for r in rows)}。客户端连接重试统计（retries为触发退避的次数，取消可能发生在下次发送前）：`{json.dumps(read(OUT/'network-retries.json'))}`。",
        f"被停止的首次修复运行HTTP时间跨度：{prior_span:.3f}秒；请求2293次，单独保存于 [{PRIOR.name}]({PRIOR})。",
        f"正式重测整次实验墙钟：{read(OUT/'done.json')['wall_s']:.3f}秒；结束：{read(OUT/'done.json')['finished_at']}。预算：`{json.dumps(read(OUT/'accounting.json'))}`。",
        '## 审计与证据',
        '审计：`'+json.dumps(read(OUT/'audit.json'),ensure_ascii=False)+'`。',
        f'运行目录：[{OUT.name}]({OUT})；编排脚本：[gate_fix.py]({ROOT}/analysis/gate_fix.py)。',
        '证据文件：'+'；'.join(f'[{name}]({OUT}/{name})' for name in ('diagnosis.json','manifest.json','config.json','http-results.jsonl','reflection.json','statistics.json','evolve/g1/evolution.json','audit.json'))+'。']
    REPORT.write_text('\n\n'.join(lines)+'\n')


if __name__ == '__main__':
    audit()
    render()
    audit()  # scan the freshly rendered report too
