import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from analysis.evo_trial import read,METRICS
OUT=ROOT/'var/astra-light/astra-20261114'; OLD=ROOT/'var/evo-trial/evo-20261114/jev'
e=read(OUT/'evolve/g1/evolution.json'); ins=read(OUT/'evolve/g1/insights.json'); ref=read(OUT/'reflection.json'); m=read(OUT/'manifest.json'); a=read(OUT/'accounting.json')
lines=[]
def add(s=''):lines.append(s)
def table(head,rows):
 add();add('| '+' | '.join(head)+' |');add('| '+' | '.join(['---']*len(head))+' |')
 for row in rows:add('| '+' | '.join(str(x).replace('|','／').replace('\n',' ') for x in row)+' |')
 add()
def f(x):
 if x is None:return 'NA'
 if isinstance(x,bool):return str(x).lower()
 if isinstance(x,float):return f'{x:.4f}'.rstrip('0').rstrip('.')
 return str(x)
def link(p):return f'[{p.name}]({p})'
add('# gpt-6-astra 反思器轻量实测：Jev 轨道，一代进化')
add();add(f'开始：{m["started_at"]}。代码快照：`{m["head"]}`。本次 HTTP 尝试 {a["attempts"]}/1500；包含重试、错误、取消；不是服务商计费条数。')
add();add(f'结果：`{e["outcome"]}`；采纳候选：{e["chosen"] or "无"}；版本：v0 → {e["to_version"] or "v0"}。'+('已跑 r1。' if (OUT/'r1/done.json').exists() else '未跑 r1。'))
add();add('## 实验口径')
add();add('仅 Jev 分类器轨道，保留其既有 Jev→ds flash 自动回退链。A=sample-001…010；C=sample-011…018。复用上一轮 Jev r0 的 run_report、10 份会谈及轨迹；本轮没有重跑 r0。C 基线和各未被硬规则拦截的候选使用同一批 8 人，分别真实调用。')
add();add(f'初始 playbook 直接读取 {link(OLD/"r0/playbook.md")}，本报告保留旧实验版本名 v0；当前代码初始文件已改名为 playbook_v1.md，不将改名当作进化。会谈 prompt、模拟器、计分、安全层、契约与旧快照 `2e806f7` 无 git diff。反思 prompt 与失败案例选择逻辑未改。')
add();add('版本保存使用独立文件快照，不创建 `.git`、不 commit。若 evolution 出现 committed，仅表示采纳和保存，SHA 是内容 SHA256。未提交、未推送。凭据只从指定 .env 读入进程内存。')
add();add('## 反思器实际调用')
add();add(f'请求端点主机：`{m["endpoint_host"]}`；请求设置：OpenAI / gpt-6-astra / xhigh。实际返回模型：`{ref["model"]}`；provider=`{ref["provider"]}`；effort=`{ref["reasoning_effort"]}`；降级={f(ref["fell_back"])}；原因={ref["fallback_reason"] or "无"}。')
table(['尝试','模型','effort','耗时（秒）','reasoning tokens','成功'],[[x['role'],x['model'],x['reasoning_effort'],f(x['duration_s']),x['reasoning_tokens'],f(x['success'])] for x in ref['attempts']])
add('耗时是反思请求、返回解析和候选归一化的墙钟时间，不含后续 C 会谈或审核窗口。reasoning tokens 来自 API usage 元数据。')
add();add('实际选入失败案例：'+ '、'.join(x['visitor_id'] for x in e['failures_used'])+'。人类反馈为空。每例会谈摘录上限 1800 字，不能视为反思器读过每例完整会谈。')
add();add('## 三份候选的改动全文')
for c in e['candidates']:
 add();add(f'### {c["id"]}：{c["summary"]}')
 for ch in c['changes']:
  meta=ins['changes'][ch['id']]
  add();add(f'**{ch["id"]}**：操作 `{ch["op"]}`；章节 `{ch["section"]}`；子智能体 `{meta["subagent"]}`；维度 `{meta["dimension"]}`；关键度 **{ch["criticality"]}**（规则={ch["criticality_rule"]}，模型自评={ch["criticality_self"]}）。')
  if ch['before']:add('\n原文：\n\n```text\n'+ch['before']+'\n```')
  add('\n改动全文：\n\n```text\n'+(ch['after'] or '（删除，不新增文本）')+'\n```')
  add('\n模型所述理由：'+ch['reason'])
 add();add('完整补丁：'+link(OUT/'evolve/g1'/f'{c["id"]}.diff')+'。')
add();add('## 硬规则与 C 组门禁')
add();add('门禁沿用当前冻结配置：ISI 有效率必须严格高于本次 C 基线；危机漏报及禁忌违规为 0；总转介召回不退步；转介精确率下限 0.5。逐转介标签非劣门禁关闭。high 改动的审核窗口为 120 秒、timeout_policy=pass；未提交人工审核结果。')
table(['候选','改动数','硬规则结果','否决原因','ISI 严格提高','最终 passed'],[[c['id'],len(c['changes']),json.dumps(c['hard_rule_violations'],ensure_ascii=False),json.dumps(c['veto'],ensure_ascii=False),f(c['val_metrics']['isi_response_rate']>e['baseline_val_metrics']['isi_response_rate']) if c['val_metrics'] else '未评估',f(c['passed'])] for c in e['candidates']])
cs=[('C 基线 v0',e['baseline_val_metrics'])]+[(c['id'],c['val_metrics']) for c in e['candidates']]
keys=[k for k in METRICS if k!='veto_passed']
table(['指标']+[x[0] for x in cs],[[k]+[f(v.get(k)) if v else '未评估' for _,v in cs] for k in keys])
table(['转介标签召回']+[x[0] for x in cs],[[k]+[f(v['referral_recall_by_label'].get(k)) if v else '未评估' for _,v in cs] for k in ('R1','R2','R3')])
add('比率以 0–1 表示；ISI 平均变化为第 4 周减基线，越负表示下降越多。NA 是分母为零／指标不适用；C 的 8 人没有危机阳性，crisis_recall=NA，不能据此估计危机检出能力。C 每改变 1 人的有效状态，ISI 有效率改变 12.5 个百分点。')
add();add('人工审核记录：`'+json.dumps(e['human_review'],ensure_ascii=False)+'`。')
add();add('## 与上一轮两次 ds flash 反思比较')
add();add('上一轮 Jev g1 输入为本次复用的 r0；g2 输入为旧实验 r1（仍是 v0，但会谈重新生成），两次输入不同。两次实际反思器均为 deepseek-flash；g1 三个候选都过硬规则但未提高主指标，g2 的 c3 被硬规则拦截，另两个未过完整门禁；两代均未采纳。')
if (OUT/'comparison.md').exists():add('\n'+(OUT/'comparison.md').read_text())
add();add('## r0 与 r1')
r0=read(OLD/'r0/run_report.json')['metrics']
if (OUT/'r1/done.json').exists():
 r1=read(OUT/'r1/run_report.json')['metrics']
 table(['指标','r0 / v0','r1 / v1','变化'],[[k,f(r0.get(k)),f(r1.get(k)),f(r1[k]-r0[k]) if isinstance(r1.get(k),(int,float)) and isinstance(r0.get(k),(int,float)) else 'NA'] for k in keys])
else:
 add();add('本次未产生可评分的 r1，不能报告 r0→r1 提升。复用 r0 指标如下。')
 table(['指标','r0 / v0'],[[k,f(r0.get(k))] for k in keys])
add('A 每组仅 10 人，1 人对应 10 个百分点。上一轮未改变 v0 的重复运行，ISI 有效率出现 50%–80% 波动（ds_thinking：80%→50%→70%；Jev：60%→70%→80%）。这是旧实验的观察范围，不是置信区间，也不能把本轮单次差异归因于反思器。4 周 ISI 来自冻结的模拟状态模型，不是真实随访数据。')
add();add('## 执行与核验记录')
table(['批次','可评分人数','HTTP 尝试','墙钟秒','完整评估','契约错误'],[[str(p.parent.relative_to(OUT)),(s:=read(p))['accounting']['scored'],s['http_attempts'],f(s['wall_s']),s['accounting']['evaluation_complete'],json.dumps(s['validation_errors'],ensure_ascii=False)] for p in sorted(OUT.glob('C-g1/*/summary.json'))]+[[str(p.parent.relative_to(OUT)),(s:=read(p))['accounting']['scored'],s['http_attempts'],f(s['wall_s']),s['accounting']['evaluation_complete'],json.dumps(s['validation_errors'],ensure_ascii=False)] for p in OUT.glob('r1/summary.json')])
add('evolution 校验结果：`'+json.dumps(read(OUT/'evolution-validation.json'),ensure_ascii=False)+'`。本次三个候选的 passed 均为 false，未出现审核 timeout 与契约的冲突错误。')
add();add('HTTP 结果为成功 1100、错误 173、取消 188；因此“32/32 会谈完成评分”不表示所有底层请求成功。四批次均 error_count=0、degraded_sessions=0，但报告记录的 provider_switches 分别为基线45、c1=37、c2=46、c3=49；安全判断器 fallback 次数分别为63、57、63、72。Jev 轨道实际包含既定的自动回退。')
add();add('上一轮同一 C 组的两次 v0 基线 ISI 有效率均为75%，本次为87.5%。本次 API 错误、取消及回退与小样本波动共同存在，单轮结果不构成对两种反思器总体效果的排序。')
add();add('产物核验：`'+json.dumps(read(OUT/'integrity.json'),ensure_ascii=False)+'`。')
if (OUT/'audit.json').exists():add('\n独立审计：`'+json.dumps(read(OUT/'audit.json'),ensure_ascii=False)+'`。')
if (OUT/'stopped.json').exists():add('\n门禁结果已落盘后，轻量编排调用本地 evolution 校验器时漏传 visitors 参数，产生 TypeError；随后补齐参数完成离线校验。未重跑反思或 C 会谈，未增加 API 请求。原始停止记录保留。')
add();add('证据：'+ '；'.join(link(OUT/p) for p in ('manifest.json','reflection.json','evolve/g1/evolution.json','evolve/g1/insights.json','accounting.json','http-results.jsonl','done.json'))+'。')
Path('/Users/zhangheqing/bohack/research/codex-tasks/astra-light.md').write_text('\n'.join(lines)+'\n')
print('report written',len('\n'.join(lines)))
