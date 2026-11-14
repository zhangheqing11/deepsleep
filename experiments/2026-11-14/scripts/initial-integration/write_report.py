from pathlib import Path
import json
from collections import Counter
from datetime import datetime

ROOT=Path.cwd()
OUT=Path('/Users/zhangheqing/bohack/research/codex-tasks/integ-report.md')
modes=['split','merged']
runs={m:ROOT/'var/integ'/f'integ-real-{m}' for m in modes}
read=lambda p:json.loads(p.read_text())
summaries={m:read(p/'summary.json') for m,p in runs.items()}
reports={m:read(p/'run_report.json') for m,p in runs.items()}
traces={m:{p.stem:read(p) for p in (runs[m]/'trace').glob('*.json')} for m in modes}
sessions={m:{p.stem:read(p) for p in (runs[m]/'sessions').glob('*.json')} for m in modes}
calls={m:read(runs[m]/'calls.json') for m in modes}
manifests={m:read(runs[m]/'manifest.json') for m in modes}
def link(path,line=None):
    path=ROOT/path
    return f'[{path.relative_to(ROOT)}'+(f':{line}' if line else '')+f']({path}'+(f':{line}' if line else '')+')'
def fmt(x):
    if x is None:return 'null（无预测阳性）'
    if isinstance(x,float):return f'{x:.3f}'
    return str(x)
lines=[]
add=lines.append
add('# S2 + 安全层 + S3 本地联调报告')
add(f'\n生成时间：{datetime.now().astimezone().isoformat(timespec="seconds")}。工作区：{ROOT}；分支：zhq/integ-trial。')
add('\n**两组真实 API 均已各跑一次，每组 sample-001..010 并发 10 人；没有额外整组重试，没有 push 或 PR。Git 合并提交未完成：沙箱拒绝创建 worktree 的 index.lock。下述数据来自工作区组合代码，并非已提交的合并分支。**')
add('\n## 1. 合并、冲突和验证')
add('''
起点 HEAD 为 `0d87de8`（S2，PR #16）；待合安全分支 `origin/zhq/domain-safety=86b1257`；S3 来源 `origin/zhq/engine-session=9f84342`。

| 文件 | 工作区已采用的解法 |
|---|---|
| Makefile | 保留 S2 的 scoring.smoke、测试目标，以及安全分支的 safety-eval、EVAL_ARGS、check-keys；再加 S3 的 engine-mock。smoke 同时依赖 contracts 和 test。新增 VENV 变量以使用指定外部虚拟环境。 |
| requirements.txt | 两侧并集：jsonschema、referencing、pyyaml、openai、httpx、pytest；S3 无额外必需依赖。 |
| tests/conftest.py | 保留 S2 的条件式 sys.path 注入；保留安全分支的 offline autouse fixture、SAFETY_EVAL_NO_DOTENV、所有环境变量清理和 socket 联网禁用。S3 同名 fixture 没有额外内容。 |

`git add` 和 `git commit` 均返回：
```
fatal: Unable to create '/Users/zhangheqing/bohack/deepsleep/.git/worktrees/ds-integ/index.lock': Operation not permitted
```
因此第一笔合并还留在 Git 未解决索引状态；后续 `git merge` 也因未解决索引拒绝执行。本会话已提出环境权限修复请求，未绕过受限 Git 元数据。

为继续已授权的联调，只把 S3 的 engine/ 和两份新增测试文件从本地 remote-tracking 对象读入可写工作区，共 31 个文件，逐字节比对一致。没有覆盖安全分支新版文件。S3 对 domain/vetoes.py 的缓存优化已包含在当前安全分支中。该操作是工作区准备，不等同 Git merge。导入清单和 SHA-256 在 `var/integ/s3-export-manifest.json`。

验证结果：
- 指定 Python：`/Users/zhangheqing/bohack/ds-safety/.venv/bin/python`。
- 原有组合代码：`pytest -q --ignore=api` → **552 passed, 1 xfailed**。
- 加入 5 项适配测试后：同一命令 → **557 passed, 1 xfailed**。
- `make -o venv contracts smoke VENV=/Users/zhangheqing/bohack/ds-safety/.venv` 通过；`-o venv` 仅跳过新建/安装虚拟环境，contracts、test、scoring.smoke 均实际执行。
- `python -m scoring.smoke --agent engine.adapters_sim:run_session --run-id integ-mock`：10 人，**21/21 文档合法**（10 visitor + 10 session + 1 run_report）；ISI 30%，路径 r1/r2=70%/80%，危机漏报 2，veto=false。
- 带完整计时器的 mock 试跑：10 人完成，21/21 文档合法，HTTP 请求 **0**。
- 既有 1 项 xfail 保留，未通过改测试掩盖。
- **没有 pip install，没有新增已安装包。** 现成环境已有 openai 3.51.0、httpx 0.28.1、typesafe-sdk 0.7.5（附带 httpx2 2.16.0）、pytest 9.2.0 等。

`contracts/` 相对起点无差异；`safety/` 工作区相对合并索引无额外修改。未改危机判据、阈值、词表或固定安全话术。
''')
add('## 2. 接线改动与测量口径')
add(f'''
- {link(Path("engine/adapters_sim.py"),12)}：S2VisitorSim，把 S3 的 reply 接到同一个 S2 SimVisitor；按会谈 memory 隔离状态，跨轮保留 deny/reveal。拼接上条来访之后的 agent/safety **实际话语**，用 S3 冻结 tag_topics 传给 S2；不使用未说出口的 strategy.target_topic 或隐藏标签。这样“这种念头”的 history 核验可被 S2 识别。
- {link(Path("engine/adapters_sim.py"),48)}：筛查直接调 S2 run_tool，结果来自隐藏量表的纯代码。
- {link(Path("engine/adapters_sim.py"),53)}：环 2 调 S2 simulate；把第一轮试行处方放回 session，并剔除 S3 提前追加的空第二轮，避免 S2 误把第二轮占位 R0 当成已完成转介判断。给 S3 返回 isi_week、isi_change、adherence、responder 及参数版本。
- {link(Path("engine/adapters_sim.py"),66)}：提供 scoring.smoke 要求的 run_session 签名。费用试跑使用下一项批量入口，共享客户端和 S3 32 路请求限流器。
- {link(Path("engine/integ_trial.py"),1)}：本地试跑 CLI、独立计时、状态计数、物理请求尝试统计、会谈/trace/report/校验结果落盘。只在运行内包装方法和 HTTP send，不更改 S3 或安全实现文件。输出目录已存在时拒绝再跑，防误计费。
- {link(Path("tests/test_integ_adapter.py"),1)}：5 项测试涵盖跨轮/跨来访状态隔离、history 话术、环 2 第一轮转介、筛查与 10 人契约、取消调用计时。
- 原有 S2/S3 业务文件未编辑；原有共享文件仅上述冲突并集和 VENV 参数化。没有修改 playbook 或任何 prompt。

两组均为 deepseek-flash 会谈/分类器/模拟来访，temperature=0；安全层默认 chain（ds flash 6s → Jev 3s）。代理每轮动作上限 5/4、agent max_inflight=32、timeout=20s、max_tokens=800 均沿用。唯一为费用约束覆盖的是 agent max_retries 从原值 2 改为 **1**；来访 SDK max_retries=1，Jev SDK 注入 RetryPolicy(max_retries=1)，分类器/危机 ds SDK 不重试。两组之间只切换 merge_strategy_response。

凭据仅由进程直接读取指定外部 .env，没有打印、复制到本目录或写入报告。两组顺序运行，不相互竞争并发额度。

整组墙钟从并发调度开始到全部会谈结果返回并落盘，包含网络等待和会谈保存，不含依赖构建及最终计分/契约校验。单来访计时从会谈启动到 SessionRunner 返回。分位数使用 nearest-rank，n=10 时 p95=max。

“实际请求”是进入 httpx/httpx2 AsyncClient.send 的尝试数，含 SDK 重试、随后被取消的在途请求；它不是服务商计费账单。子智能体计时包含完整 SDK/JSON 解析及等待，不把并行耗时相加当墙钟。trace 的 schema 校验失败另行统计；HTTP 200 不代表应用输出有效。

两组源码摘要相同：**{manifests["split"]["source_sha256"] == manifests["merged"]["source_sha256"]}**。摘要、完整生效配置、参数摘要均见各组 manifest.json。
''')
add('## 3. 两组结果')
add('\n| 指标 | 分开 split | 合并 merged |\n|---|---:|---:|')
rows=[
('整组墙钟（秒）',lambda s:s['wall_s']),
('单来访 p50（秒）',lambda s:s['session_s']['p50']),
('单来访 p95（秒）',lambda s:s['session_s']['p95']),
('单来访 max（秒）',lambda s:s['session_s']['max']),
('completed / crisis_exit / error',lambda s:'/'.join(str(s['statuses'].get(x,0)) for x in ['completed','crisis_exit','error'])),
('实际 LLM 请求尝试',lambda s:s['http_attempts']),
('逻辑调用 error / timeout / cancelled',lambda s:'/'.join(str(s['logical_statuses'].get(x,0)) for x in ['error','timeout','cancelled'])),
('HTTP error / timeout / cancelled',lambda s:'/'.join(str(s['http_statuses'].get(x,0)) for x in ['error','timeout','cancelled'])),
('契约有错文档数（总数 21）',lambda s:len(s['validation_errors'])),
]
for metric in ['isi_response_rate','mean_isi_change','path_acc_r1','path_acc_r2','path_acc_gain','referral_recall','referral_precision','screening_coverage','crisis_missed']:
    rows.append((metric,lambda s,k=metric:s['metrics'][k]))
rows.append(('veto.passed',lambda s:s['veto']['passed']))
for name,fn in rows:
    add('| '+name+' | '+' | '.join(fmt(fn(summaries[m])) for m in modes)+' |')
add('\n比率字段为 0–1；null 表示没有预测阳性，不能写成精确率 100%。错误会谈也进入既有计分器，上表路径指标含错误占位/沿用值，不能当成完整成功会谈的有效性能。没有最终处方的 error 会谈按 S2 规则 ISI 不变。未传上一代 baseline，所以“转介召回不劣于上一代”未验证。')
for m in modes:
    add(f'\n**{m} veto 原因**：'+json.dumps(reports[m]['veto']['reasons'],ensure_ascii=False))
add('\n### 单来访耗时与状态')
add('\n| 来访 | split 秒 / 状态 | merged 秒 / 状态 |\n|---|---|---|')
for vid in sorted(traces['split']):
    add('| '+vid+' | '+' | '.join(f'{traces[m][vid]["wall_s"]:.3f} / {sessions[m][vid]["status"]}' for m in modes)+' |')
add('\n### 子智能体调用与延迟')
add('\n单位 ms。n=实际包装方法调用次数；API=网络尝试数；error/timeout/cancelled 单列，未合并为一个“请求失败”。')
add('\n| 模式 | 子智能体 | n / API | mean | p50 | p95 | max | 状态计数 |\n|---|---|---:|---:|---:|---:|---:|---|')
for m in modes:
    for name,c in summaries[m]['components'].items():
        add(f'| {m} | {name} | {c["n"]} / {c["http_attempts"]} | {c["mean"]:.1f} | {c["p50"]:.1f} | {c["p95"]:.1f} | {c["max"]:.1f} | '+str(c['statuses'])+' |')
add('\n### 错误与回退明细')
for m in modes:
    traced_failures=sum(not r['ok'] for t in traces[m].values() for r in t['llm_calls'])
    fallbacks=sum(r['renderer']=='mock' for t in traces[m].values() for r in t['s2_replies'])
    add(f'\n{m}：原始 S3 trace 的 llm_calls 失败条目 {traced_failures}；独立计时器逻辑状态 {summaries[m]["logical_statuses"]}；模拟来访降级 mock {fallbacks} 次。不同统计范围不可相加。')
    for vid,s in sorted(sessions[m].items()):
        if s['error']:
            add(f'- {vid}: `{s["error"]}`')
    add('HTTP 异常（无 header/body）：'+json.dumps([x for x in calls[m]['http'] if x['status'] in ['error','timeout','http_error']],ensure_ascii=False))
add('\n## 4. 路径分类熵：逐回合与跨轮')
add('\n使用 S3 的归一化 Shannon H/ln(5)，越低表示权重更集中，并不等价分类更正确。序列仅取 trace 中已采用动作及轮末 final；F 表示轮末，T/E 为 timeout/error 回退的均匀分布。未完成的第二轮不补数。')
add('\n| 来访 | split 熵序列 | merged 熵序列 |\n|---|---|---|')
def curve(t):
    pieces=[]
    for i in [1,2]:
        rows=[r for r in t['path_probs'] if r['round']==i]
        seq=['%.3f'%r['uncertainty']+('F' if r['final'] else '')+({'timeout':'T','error':'E'}.get(r['status'],'')) for r in rows]
        pieces.append('r%d: '%i+(' → '.join(seq) if seq else '无记录'))
    return '<br>'.join(pieces)
for vid in sorted(traces['split']):
    add('| '+vid+' | '+' | '.join(curve(traces[m][vid]) for m in modes)+' |')
for m in modes:
    seqs=[t['path_probs'] for t in traces[m].values() if len(t['path_probs'])>=2]
    down=sum(q[-1]['uncertainty']<q[0]['uncertainty'] for q in seqs)
    strict=sum(all(b['uncertainty']<=a['uncertainty'] for a,b in zip(q,q[1:])) and q[-1]['uncertainty']<q[0]['uncertainty'] for q in seqs)
    pairs=[]
    for t in traces[m].values():
        finals={r['round']:r['uncertainty'] for r in t['path_probs'] if r['final']}
        if len(finals)==2:pairs.append(finals)
    add(f'\n{m}：有至少两个记录的 {len(seqs)} 人中，末值低于首值 {down} 人；全程不升且最终下降 {strict} 人。真正同时存在 r1/r2 final 的仅 {len(pairs)} 人，其中 r2 final 低于 r1 final {sum(p[2]<p[1] for p in pairs)} 人。')
add('\n因此只能按上表逐例描述，不能声称熵普遍随回合下降；失败/超时和提前终止会截断曲线。')
add('\n## 5. 两名来访的完整过程摘要')
add('\n选 sample-003（passive 危机真值）与 sample-007（已结束风险史）。下面按每条 transcript 顺序列出；长发言只保留前 180 字并标注，未隐藏回合或 safety 条目。完整文本、工具结果、处方及安全事件均有原始 session JSON。')
for vid in ['sample-003','sample-007']:
    visitor=read(ROOT/'sim/visitors'/f'{vid}.json')
    add(f'\n### {vid}：{visitor["main_path"]}，{visitor["referral"]}，危机标签 {visitor["crisis"]}')
    for m in modes:
        s=sessions[m][vid];t=traces[m][vid]
        add(f'\n**{m}**：{s["status"]}，{t["wall_s"]:.3f}s。原文：{link(runs[m].relative_to(ROOT)/"sessions"/f"{vid}.json")}；trace：{link(runs[m].relative_to(ROOT)/"trace"/f"{vid}.json")}。')
        for r in s['rounds']:
            add(f'\n第 {r["round"]} 轮：path={r["path_pred"]}，referral={r["referral_pred"]}，crisis={r["crisis_level"]}。')
            for e in r['transcript']:
                text=e['text'].replace('\n',' / ')
                short=text if len(text)<=180 else text[:180]+'…（余文见原始 JSON）'
                add(f'- t{e["turn"]} {e["speaker"]}：{short}')
            for tool in s['tool_calls']:
                if tool['round']==r['round']:
                    add(f'- 工具 t{tool["turn"]}：{tool["tool"]} → {tool["result"]}')
        add(f'\n安全事件：{json.dumps(s["safety_events"],ensure_ascii=False)}；history_checks：{json.dumps(t["history_checks"],ensure_ascii=False)}；最终处方：'+('无' if s['plan'] is None else json.dumps(s['plan'],ensure_ascii=False))+'。')
        if s['error']:add(f'终止原因：{s["error"]}。')
add('\n### 安全插话与 history_check 核对')
for m in modes:
    events=[e for s in sessions[m].values() for e in s['safety_events']]
    history=[h for t in traces[m].values() for h in t['history_checks']]
    speakers=sum(e['speaker']=='safety' for s in sessions[m].values() for r in s['rounds'] for e in r['transcript'])
    add(f'\n{m} 全组：safety_events={len(events)}，speaker=safety 条目={speakers}，history_checks={len(history)}。')
add('\n若为 0，结论是本次真实样本路径没有触发相应分支，不能写成“安全插话/history_check 已实测通过”。sample-003 虽隐藏 PHQ-9 第 9 题为 1，但自评第 9 题为 0；隐藏值未直接交给 agent 或安全层。sample-010 无自评且危机线索 deny_first=true；需要问到并再次追问才会透露。sample-004/007 的 history 也只有问到 self_harm 才透露。本次对话询问、筛查不足及提前失败，使端到端漏报与 history 未覆盖同时出现；不能据此归因为安全规则对已见危机文本判断错误。')
add('\n离线适配测试已验证 S3 的“这种念头”话术能驱动 S2 返回“现在没有了”；既有 S3 测试覆盖安全分支，但这与本次真实 API 的覆盖证据不同。')
add('\n## 6. 问题与不一致（按严重程度）')
add(f'''
1. **P0：本次端到端未满足危机 0 漏报。** 两组按各自 run_report 记录 crisis_missed；明确的来访标签见 {link(Path("sim/visitors/sample-003.json"))}、{link(Path("sim/visitors/sample-010.json"))}。S2 按话题透露，且防御型先否认，见 {link(Path("sim/visitor_sim.py"),77)}；S3 正常会谈循环没有代码层强制完成 self_harm 询问/筛查，见 {link(Path("engine/session.py"),156)}。现有证据指向“线索未问出/会谈提前失败”，并不证明 safety 对已见文本漏判。保留当前判据，报告数据供团队审定。
2. **P0：真实输出解析失败可让会谈全部或大批终止。** 精确失败数量见上表和逐例错误。配置 {link(Path("engine/config.yaml"),10)} 的 max_tokens=800；{link(Path("engine/llm.py"),38)} 只读取 message.content 后解析，{link(Path("engine/session.py"),548)} 两次失败后抛 EngineError；{link(Path("engine/session.py"),143)} 将整场会谈写成 error。观察到空/非 JSON 和未闭合字符串。**输出被 token 上限截断是待验证假设**：当前未记录 finish_reason/raw message，不能据错误文本确定唯一根因。为保持试验可比和费用上限，没有现场调 prompt、上限或额外重跑。
3. **P1：error 会谈的路径准确率含占位数据，run_report 缺少直接的完成率。** {link(Path("engine/session.py"),608)} 未有分类结果时填 P1，{link(Path("engine/session.py"),613)} 未有转介时填 R0；{link(Path("scoring/score.py"),56)} 只要没有第二轮就沿用第一轮（原注释只提 crisis_exit，实际上 error 也会如此）。所以完整合法的 run_report 不能单独证明成功会谈质量。本报告额外列出状态和未完成轮次，未改契约。
4. **P1：原始 trace / run_report 会低估调用数与失败数。** {link(Path("engine/session.py"),232)} 推测 step 先用局部 calls，只有 commit_step 才合入 trace；失败或丢弃时记录可失去，{link(Path("engine/session.py"),356)} 仅完成的成功推测才数 discarded_calls。分类缓存也可能让 trace 的 path_probs 复用一次调用的延迟。{link(Path("scoring/score.py"),133)} judge_calls 只数安全事件，安全判为 none 的调用与成功 fallback 前的失败不在事件统计里。本报告用 HTTP send 和独立方法包装保留完整计数，未改正式报表口径。
5. **P1：分类器有 6 秒超时并回退均匀权重。** 见两组 classifier 状态数；{link(Path("engine/classifier.py"),100)} 超时返回 uniform_state，熵为 1，随后仍可进入路径 argmax。{link(Path("engine/classifier.py"),44)} 并列时优先 P1。超时会影响分类结果和熵曲线；不能把 H=1 全解释为来访信息不充分。
6. **P2：环 2 已接入 S2 模型，但模型参数仍为占位，且来访 renderer 不消费四周结果。** {link(Path("sim/params.yaml"),1)} 明示全部占位、版本 0.0-placeholder；{link(Path("engine/session.py"),217)} 将结果放进 sim_memory，S2 respond 的签名与 prompt 仍只有当前话语和线索，见 {link(Path("sim/visitor_sim.py"),135)}，本适配器未额外改动。agent 能看到模型结果并 select，但不能宣称模拟来访已据四周变化作了完整反馈。ISI 数字只用于当前冻结规则模型的联调输出。
7. **P2：新版安全层的固定话术去重接口尚未被 S3 使用（静态集成不一致，本次真实运行未覆盖）。** {link(Path("safety/layer.py"),143)} 提供 script_for_event 去重 safety_check 话术；S3 {link(Path("engine/session.py"),375)} 仍直接调 script_for。若自评和 screen_mood 均产生第 9 题阳性事件，存在重复播报路径；没有擅自修改安全判据或改这条调用。
''')
add('\n## 7. “单次运行约 1 分钟”的数据依据')
for m in modes:
    s=summaries[m]
    over=sum(t['wall_s']>60 for t in traces[m].values())
    add(f'\n- {m}：10 人并发，墙钟 {s["wall_s"]:.3f}s，为 60s 的 {s["wall_s"]/60:.2f} 倍；{over}/10 单来访超过 60s；完成状态 {s["statuses"]}。')
add('\n本次仅有各模式一次、每次 10 人的观测；没有运行正式 40–50 人规模，没有统计重复试验区间。提前失败截短了部分路径，不能把失败会谈时长当作成功两轮时长。仅列数据，不替团队决定演示方案或改冻结参数。')
add('\n## 8. 产物、复现与仍未完成的工作')
for m in modes:
    add(f'\n- {m}：'+', '.join(link(runs[m].relative_to(ROOT)/name) for name in ['manifest.json','summary.json','run_report.json','calls.json'])+'；sessions/ 与 trace/ 存各来访完整产物。')
add('''
\n真实运行命令（已执行，不应再次执行现有 run-id）：
```bash
/Users/zhangheqing/bohack/ds-safety/.venv/bin/python -m engine.integ_trial --run-id integ-real-split
/Users/zhangheqing/bohack/ds-safety/.venv/bin/python -m engine.integ_trial --merged --run-id integ-real-merged
```

尚未完成的是用户要求的两次 Git 合并提交。恢复元数据权限后，需要先提交第一笔合并，再在确认导入文件仍与 s3-export-manifest.json 一致的前提下处理这些临时导入文件，执行真正的第二笔合并；适配层、试跑器和新增测试应作为独立本地提交保留。不要直接删除整个 engine/，其中含本次新增适配代码。当前 Git 仍显示原先 3 个 unmerged 索引项，这不表示文件正文仍有冲突标记。没有 push、PR 或远端写入。
''')
OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.write_text('\n'.join(lines)+'\n')
print(OUT)
