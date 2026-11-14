# 2026-11-14 实测归档：给数据科学同学的 agent

本目录保存当日已经产生的报告和模拟实验产物，归档过程未调用模型或外部 API。不要把复现命令当作待自动执行的任务。仓库快照为 `58c256c7e7ddad8f5d59604e72693667e9eb3f3c`（归档时 HEAD 与本地 origin/main 相同，未 fetch）；分支 `zhq/experiments-1114`，未提交。

先读本页与 [逐批运行索引](RUN_INDEX.md)，再按实验查报告、summary 和会谈。**所有 ISI 都是冻结规则状态模型的四周模拟结果，不是临床疗效证据。** 只收任务指定模拟实验，没有引入真实用户会谈。原报告中的历史待办、分支、验收数字保留其当时含义，不代表当前 main 的状态。

## 1. 实验总表

时间统一按 UTC+08:00 展示，以产物内 started_at / created_at / finished_at 为准；只有缺少内嵌时间的文件才查 [MANIFEST.json](MANIFEST.json) 的 source_mtime_utc。表按交接要求的实验阶段排列，实验实际有重叠，分类器对比的报告时间早于 10 人验收；严格按产物时间排列的 70 份运行报告见 [RUN_INDEX.md](RUN_INDEX.md)，机器可读版本为 [RUN_INDEX.json](RUN_INDEX.json)。r0/r1/r2 是不同运行，路径 r1/r2 是同一会谈的两轮；不能混用。

下表 ISI、路径、转介以百分比表示，pp 表示百分点；危机“漏报 0”按历史 scorer 的风险识别口径，**不自动等同 active 升级与退出成功**。转介按“召回/精确”排列；NA 是无分母。HTTP 是实际发送尝试（含失败、重试、取消），不等于账单，也不等于只统计 agent 的 llm_attempts。

| 实验与产物时间 | 目的及配置（分类器；实际反思器；人数；动作上限；渲染） | 主要结果与资源 | 结论边界 | 报告与数据 |
|---|---|---|---|---|
| 判断器对比、开发/留出链评测；早期占位 07:32–09:49，链评测 14:55:09 / 14:57:30，规则留出 15:18:17 | 安全层选型与漏报检查；四方判断器 DS/Jev/Gemini/StartLux；无路径分类或反思；开发 48 条、留出 40 条；静态文本，无会谈轮数/渲染 | 四方开发集风险召回均 24/24，DS active 10/10；链开发召回/精确 100/100、漏报 0、49 次 judge；链留出原标签召回 95.45%、精确 100%、漏报 1（HO-34），40 次 judge，p50/p95 2.36/3.42 秒；规则留出漏报 10 | 开发集参与 prompt/阈值设计；HO-34 后经审定改为 history，见 [E0 决策](../../docs/review-decisions.md) 与 [当前留出集](../../safety/holdout.jsonl)；原 JSON 不追溯改标签。带 mock(fallback) 的 Gemini/StartLux 早期文件不是真实判断器成绩；无 ISI/路径/转介指标 | [仓库原对比报告](../../docs/judge-comparison-2026-11-14.md)、[复核](reports/recheck.summary.md)、[修复](reports/pr6-fixes.summary.md)；[safety-eval](data/safety-eval/FILES.md) |
| 首次联调；15:01:00 mock，15:03:40 split，15:06:22 merged（报告完成时间） | 比较策略/回复拆分和合并；DS 分类器，无反思；sample-001…010，各 10 人；5/4；DS 来访，另有 instrument-mock | split/merged：134.301/153.449 秒、337/317 HTTP；两组均 10 error；历史报表 ISI 0/0、路径 r1 40/40、r2 50/60、转介召回 0/0、精确 NA、危机漏报各 2。mock 为 0 HTTP | 全 error；旧计分口径仍输出 10 行，不能视为有效性能，不能与后续排除 error 的报表直接比较 | [integ-report](reports/integ-report.md)；[initial-integration](data/initial-integration/FILES.md) |
| S3 fix1 与二阶段；fix1 15:15:43；phase2 15:25:28–15:31:08 | 修截断、强制筛查、降延迟；fix1 mock 分类/判断、DS agent、模拟来访确定性，3 人（001/002/007）、1/1；phase2 Jev→DS、无反思，真实预检 3 人及 10 人批次、4/3、DS 渲染 | fix1：3 completed，ISI 100、路径 66.67/66.67、转介 100/100、漏报 0，最长 55.806 秒；24 会谈请求+2 探针=26。phase2 预检 73.58 秒/115 HTTP；10 人 49.23 秒/332 HTTP、ISI 60、路径 80/90、转介 66.67/100、风险漏报 0；阶段总预算 450/450 | fix1 不是全真实系统；phase2 预算阻断 110 次、全部 10 人使用固定降级、evaluation_complete=false；sample-010 active 只触发 passive 确认，未 crisis_exit。49 秒不能证明完整真实验收达标；raw 报告也保留 | [fix1](reports/s3-fix1.summary.md)、[phase2](reports/s3-phase2.summary.md)；[s3](data/s3/FILES.md) |
| 10 人验收；16:53:33–16:54:51 | 完整真实批次；Jev→DS；无反思；sample-001…010；4/3；DS 来访，合并 turn 与首轮 memory_plan | 9 completed+1 crisis_exit、0 error；ISI 70、路径 70/70、转介 66.67/80、风险召回 2/2；进程 78.193 秒，引擎 77.309 秒；381/600 HTTP，6 ConnectError、2 取消；agent/renderer 固定降级 0 | 仅一次小样本；服务商切换 8 次仍存在；状态模型占位。首次联调/S3 缺口不能由这一批之外推到所有场景 | [验收](reports/accept-report.md)、[修复](reports/accept-fixes.summary.md)；[accept-ten](data/accept-ten/FILES.md) |
| 分类器三方对比；报告 15:45:48（按交接阶段放在验收之后） | DS 思考开/关/Jev，相同前缀；无反思/新会谈；36 场历史真实 agent 会谈、10 张卡、150 唯一前缀/181 位置；不同来源轮数；重放固定文本，不新渲染 | 最终前缀准确率 86.11/75/86.11；全选回合 58.56/53.59/55.80；p50 3303.7/1154.1/285.4 ms，p95 6252.0/1762.1/453.7 ms；各 150 调用，共 450；无 ISI/转介/危机评价 | 会谈 bootstrap CI 不覆盖同输入重复 API 噪声；含早期 error 会谈的已有前缀。不能据此直接断定端到端效果 | [clf-compare](reports/clf-compare.md)；[main 原始结果](../../analysis/out/classifier_compare.json)、[抽样清单](../../analysis/out/classifier_compare.dry-run.json)，不重复复制 |
| 三分类器两代进化；17:34:04–18:05:08（报告生成） | DS 思考开/关/Jev 三轨；实际反思均降级 deepseek-flash；A=sample 001–010，C=011–018，10/8；4/3；DS 来访；轨道顺序、每代 C 版本并行 | A 三次 ISI：思考开 80→50→70，关 60→60→60，Jev 60→70→80；r2 路径分别 90→70→80、70→70→60、70→80→70；转介逐批见索引，所有 A 风险漏报 0；10398 HTTP；轨道墙钟 692/531/551 秒 | 只有不思考轨道第二代采纳至旧命名 v1，其他运行沿用 v0；A 复用不是独立 B。Jev 同版本涨 20pp 本身就是波动证据；不要把版本名与 main 初始 v1 混用 | [evo-trial](reports/evo-trial.md)；[evo-trial](data/evo-trial/FILES.md) |
| astra 轻量；18:13:13–18:20:11 | Jev；实际 gpt-6-astra/xhigh 未降级；复用上轮 Jev A10 r0，C8；4/3；DS 渲染；C 基线和候选并行 | 反思 225.85 秒；1461/1500 HTTP。C ISI 基线 87.5、候选 62.5/75/50；路径 r2 基线 87.5、候选 75/100/87.5；转介召回基线 66.67、候选均 33.33，精确 50/100/100；危机样本 0、漏报计数 0；未采纳、未跑 r1 | C 仅 8 人且没有危机阳性，不支持安全召回外推；高路径准确率不等于 ISI 或转介改善；复用 A 的调用不重复计入本轮 | [astra-light](reports/astra-light.md)、[反思器接入](reports/refl-openai.summary.md)；[astra-light](data/astra-light/FILES.md) |
| 40 人噪声底线+一代进化；18:24:31–18:41:06 | Jev；gpt-6-astra/xhigh 未降级，212.42 秒；interim A40/C32；4/3；DS 渲染；50 会谈/32 agent 并发；C 按 c1→c2→c3→基线逐批 | 两次 A ISI 65→55（−10pp）；路径 65/65→62.5/70；转介 75/48→56.25/39.13；风险漏报均 0，ISI 配对一致 70%。基线 114.70/104.39 秒；总 994.81 秒、8954 HTTP。C ISI 46.875 vs 40.625/43.75/37.5，无采纳、无 r1 | A 两次均转介精确率触发否决；C 基线有 1 条禁忌违规。各批 66–401 HTTP 异常，旧运行不应当干净效果估计；没有新 B 组 | [evo40](reports/evo40.md)、[临时来访](reports/visitors80.summary.md)；[evo40](data/evo40/FILES.md) |
| 另一统筹会话彩排；mock 18:21:30；真实 small-1 18:26:54 失败；small-2 18:30:49–18:37:40 报告，端到端约 9 分钟 | ds-demo 是 mock 6/6/6；主目录 small-2 为 Jev、gpt-6-astra 未降级、正式集 A/B/C 各 5、4/3、DS 渲染 | 真实运行1/2/对照 ISI 40/20/20，路径 r2 20/80/60，转介 100/100、0/0、0/NA；危机阳性 0、漏报计数 0；批次 127.94/118.90/121.03 秒。C ISI 基线 60 vs 60/60/40，未采纳；全系统 HTTP 未记录，不能用 llm_attempts 顶替 | run2 与 control 同 v1、同 B，路径 80 vs 60 是非确定性；run2 转介精确率 0 被否决；small-1 因缺配置终止，不是一次成功评测。mock 与真实分目录 | [现场原摘要](data/rehearsal/deepsleep/demo/rehearsal-small-2/summary.md)；[rehearsal](data/rehearsal/FILES.md) |
| gate-fix；首批 18:48:46 起停止；第二批 18:58:01 起，最后 r1 19:45:53 | Jev；首次 astra 300 秒超时→DS 23 秒解析失败；调整反思超时后 astra 234.93 秒成功；interim A40/C32、4/3、template；8 会谈/全 HTTP 16 并发；C 基线先行、顺序候选 | 新 A ISI 57.5/65，r1 72.5；路径 r2 65/67.5/75，转介 56.25/42.86、62.5/43.48、81.25/50；风险漏报均 0；C c3 56.25 vs 基线 43.75 被采纳。A 三批 283.54/426.80/422.47 秒；总账 10227/12000 HTTP，含停止首批 2293 | 不是“进行中”：已有完整报告与审计。改变了网络并发、重试、渲染及反思超时；不能单因素归因。r1 比 r0b 的 ISI +7.5pp，配对区间跨 0；A 被重复使用，不是独立 B。保留失败反思与停止批次，不以恢复结果覆盖失败 | [gate-fix](reports/gate-fix.md)；[gate-fix](data/gate-fix/FILES.md) |

## 2. 已知问题、噪声及使用边界

1. **同 playbook 重跑足以产生 10 人约 20–30pp 变化。** 这只是本次观察幅度，不是统计噪声上限。40 人旧批次 ISI −10pp，配对一致率 70%，配对 95% 区间 [−27.5pp, +7.5pp]。gate-fix 模板渲染下两次基线仍 +7.5pp，表明只令来访确定性并未令系统确定性。
2. **门禁并行与网络错误会污染候选比较。** evo-trial/astra 与真实彩排的 C 版本并行；evo40 驱动已有串行锁，不能误写为“四版本同时跑”。它仍有批内高并发与大量连接失败，C 基线又最后执行。gate-fix 原生门禁改为基线先行、逐候选，且全客户端共享并发限额；异常减少与多项改动同时发生，尚不能证明哪个因素导致改善。
3. **模拟来访 LLM 渲染偶尔添加卡片未提供的线索。** revealed_clue_ids 是模拟器计划揭示的线索，不能代替实际发言审查。结合 s2_replies 的 text、renderer、fallback_reason 和 session 原文核对；固定 temperature=0 不保证确定性或忠实渲染。
4. **四周状态模型及分布仍为占位。** 替换 sim/params.yaml 后可用已有 visitor/session 离线重算，但应保存新参数版本、摘要和独立输出，保留旧报告作为历史证据。不能只覆盖旧 ISI。临时 A40/C32 和正式 A45/B45/C30 各有共享模板局限。
5. **回合挤占仅是待检验疑点。** evo40 的 C-014：基线第二轮调用 screen_osa 并预测 R1；三候选都用满 4/3 动作且未筛查，最终 R0。其中 c2 有 turn 降级，c1/c3 无未丢弃降级；未做改变动作槽数的对照，不能仅凭共现得出因果结论。包内对应路径是 `evo40-20261114/C/{v0,v0+c1,v0+c2,v0+c3}/sessions/C-014.json`。
6. **安全历史结果不能混合口径。** safety 留出原 HO-34 标签及修订、phase2 active 未退出、scorer 的非 none 风险召回是不同问题。mock 的零漏报、无危机阳性的 NA、真实危机样本的召回应分别看；不能从单次 0 推断总体零漏报。
7. **完成、评分、门禁通过、版本采纳是四件事。** summary 中 error/unknown/excluded、预算阻断、evaluation_complete 必须和 run_report 一起读取。旧实验的 `committed` 可表示文件快照采纳，SHA 为内容 SHA256，不一定是 git commit；真实 git 导出明确在 rehearsal/ds-demo/playbook-repo 下。

## 3. 目录、字段和读取方式

[MANIFEST.json](MANIFEST.json) 为每个来源文件记录绝对来源、源修改时间、源/归档 SHA256、大小、是否脱敏、目标路径；包内文件还记录 member。除列明的脱敏，归档文件字节与来源一致；JSON 的旧绝对路径和旧模型版本名不重写。报告原始绝对链接可按 manifest 的 source 找到 destination/member。本页与 FILES.md 使用可携带的相对链接。

| 数据目录 | 内容与专属字段 |
|---|---|
| [safety-eval](data/safety-eval/FILES.md) | 10 份历史 JSON；provider/requested_provider 区分请求与实际模型；judge.providers/statuses/calls 为实际链路；confusion_matrix 行真值、列预测；predictions/missed 是逐条模拟文本；freeze_acceptance 是当时验收状态，不是当前结论。无会谈压缩包。四方对比原报告在仓库 docs；其 var/eval 原始四方文件不在本次指定 safety-eval 来源中，不伪造补齐。 |
| [initial-integration](data/initial-integration/FILES.md) | 三批 manifest/config、calls、summary、旧 run_report；s3-export-manifest 记录当时导入源码，保留历史全 error 数据；sessions/traces 两包。 |
| [s3](data/s3/FILES.md) | integ/runs/s3-fix1/s3-phase2 子树；探针 probe、requests、离线 cap_measurement；*.raw.json 为预算标记修正前的原值；源码脚本移入 scripts/s3，原路径映射在 manifest。 |
| [accept-ten](data/accept-ten/FILES.md) | integ/ 下唯一真实 10 人批次；accept/ 下进程/预算/验收摘要与日志。日志已扫描，无鉴权头内容。 |
| [evo-trial](data/evo-trial/FILES.md) | 每轨 r0/r1/r2 与 C-g1/C-g2；evolve/g* 的候选、审核、采纳、diff；playbook-snapshots；plots；http-starts/results、request-budget、statistics 等按原名称保留。历史 C role/split 可能仍写 validation/sample，A/C 应按 manifest 的 ID 分组读。 |
| [astra-light](data/astra-light/FILES.md) | 复用 A 的证据指向 evo-trial/jev/r0；这里只新增 C-g1 与反思、校验、停机记录；reflection 包括实际模型、usage、候选和失败选择；未跑 r1 是有效状态，不是漏归档。 |
| [evo40](data/evo40/FILES.md) | r0a/r0b、C 各版本、statistics、audit、integrity、accounting；statistics 的 paired/bootstrap 描述固定这批 ID 的配对不确定性，不是重复运行方差的完整估计。未采纳，故无 r1。 |
| [rehearsal](data/rehearsal/FILES.md) | deepsleep/ 为真实彩排；ds-demo/ 为 mock。cohorts.json 保存实际卡片，options.json 保存人数/模式；experiment*.json 是编排阶段指针；runs 是会谈/评分；evolve 是门禁。沿 experiment ID 补收主目录对应 runs/evolve，以免只有摘要没有证据。playbook-repo 的 .git 未复制，仅导出工作文本、每提交版本文本、diff 和 git-log.txt。 |
| [gate-fix](data/gate-fix/FILES.md) | 从 gate-fix.md 引用的 ds-gate 只读补收。停止首批、r2 完整重测、reflector-failed-attempt、网络审计和 validation 同存；http-starts/results 新增主机、精确时间、在途数，旧 evo40 主机只是组件映射推断。根账本与批次账本可能重叠，不可简单累加。 |

**契约与非契约字段：**

- `run_report.json` 对应 [contracts/run_report.schema.json](../../contracts/run_report.schema.json)：run_id、playbook_version、role/split、models、n_visitors、duration_s、metrics、per_visitor、veto、safety_summary。历史产物按当时版本生成，本次只检查 JSON 可读与完整性，不把 `make contracts` 10 个示例通过冒充所有历史产物通过当前契约。`session_ref` 原路径可按包成员检索。
- `sessions.tar.gz` 内保留完整 session，结构见 [session 契约](../../contracts/session.schema.json)：rounds、transcript、tool_calls、path/referral 预测、safety_events、plan、status。部分历史文件的模型尾注标记采用过的降级。
- `summary.json` 非契约：attempted/scored/excluded、completion_rate、error/unknown、degraded_sessions、provider_switches、evaluation_complete、crisis_missed_all_attempts；早期在 accounting 内，后期可能顶层。`completed` 可能指有终态，不保证全程真实调用。calls 的逻辑父调用和子调用可能重叠，不能把其耗时/调用数直接相加。
- `traces.tar.gz` 非契约：path_probs/classifier 为逐动作分类及熵、attitude；llm_calls 是任务调用与耗时/finish_reason/usage；fallbacks/speculation/discarded 描述回退和被丢弃的推测结果；forced_tool_calls/scale_rechecks/history_checks 记录强制筛查和核验；s2_replies 是模拟器揭示/否认与渲染；all_judge_results 含 none/失败的完整链判断；plans/plan_postprocessing/vetoes 说明处方后处理；round1_outcome/selection 说明跨轮反馈。
- `insights.json` 非契约：summary.by_step 的 n/p_true/entropy；visitors[id].curve 的 round/turn/agent_turn/p_true/entropy/correct/attitude；关键线索回合、首个正确回合、抗拒率、d1/d2 差分。不同回合 n 可能不同；不要把这些差分当成固定队列导数。insights 熵通常为自然对数原值，分类器对比报告用 H/ln(5) 归一化，不能直接混画。
- `evolution.json` 对应进化契约；候选 changes、硬规则/val_veto、val_metrics、chosen/outcome、from/to_version 用于复核门禁。status/log/insights/reflection、calls、HTTP JSONL、manifest 为辅助非契约证据。反思器配置模型不等于实际模型，优先看 reflector.model/fell_back 与 reflection 的 attempts。

各实验 FILES.md 列出包内成员、文件字节、记录数及会谈发言条数。JSON 对象按 1 条记录，数组按元素数；会谈发言额外统计 `rounds[].transcript`，不是去重来访人数。重复尝试、不同版本、备份原件分别保留。无单文件或压缩包超过 20 MiB。

离线读取例子（仓库根运行，解压到新建临时目录）：

```sh
mkdir -p /tmp/deepsleep-evo40-archive
 tar -tzf experiments/2026-11-14/data/evo40/sessions.tar.gz
 tar -xzf experiments/2026-11-14/data/evo40/sessions.tar.gz -C /tmp/deepsleep-evo40-archive
 tar -xzf experiments/2026-11-14/data/evo40/traces.tar.gz -C /tmp/deepsleep-evo40-archive
```

## 4. 复现入口与代码快照

[脚本索引](scripts/README.md) 区分当前 main 已有入口与不在 main 的历史驱动。所有历史脚本以源码快照保留，**不会因为被归档就自动执行**。它们含旧路径、旧版本文件名或历史内部接口；先按来源 manifest 的源码提交/摘要准备独立实验副本，再改输出路径与导入根目录。不要直接在本归档目录运行真实驱动，它们可能载入本机配置、调用付费模型并写回旧 var 路径。

| 实验 | 原入口/参数；本次只记录 |
|---|---|
| 安全评测 | `python -m safety.eval --provider chain`，具体 testset 及超时以每份 JSON 和原报告为准；规则和 mock 文件不可替代真实 provider。 |
| 首次联调 | 旧快照 `python -m engine.integ_trial --run-id integ-real-split`；`--merged --run-id integ-real-merged`。旧默认与当前不同，按归档 manifest.config 重建。 |
| S3 | scripts/s3/s3-fix1 下 probe.py/live.py/offline_s2.py；scripts/s3/s3-phase2 下 probe.py/measure_caps.py/component_bench.py。component_bench 只准备过，不能声称执行；完整参数见报告。 |
| 10 人验收 | `python -m engine.integ_trial --n 10 --run-id accept-ten-20261114-165333 --budget 600 --budget-file var/accept/accept-ten-20261114-165333-budget.log`，历史另传只读配置文件参数；不要复用这个 run-id 发起新批次。 |
| 分类器对比 | `python analysis/classifier_compare.py --dry-run` / `--analyze-only` 是已有数据的离线入口；`--resume` 会补发真实调用。原始输入索引、seed、prompt 摘要在 analysis/out。 |
| 三轨两代 | 历史 `analysis/evo_trial.py --id evo-20261114 --budget 15000 --repo-mode snapshot`；`--report-only` 为历史报告生成入口，但依赖旧路径及可选绘图环境。 |
| astra 轻量 | 历史 `var/astra-light/run_light.py`，audit.py/finalize.py/report.py；归档在 scripts/astra-light。配置和 A 来源写死在脚本/manifest，先核对。 |
| evo40 | 历史 `python -m analysis.evo40 --run`；`--audit`、`--report` 读取旧产物，脚本在 scripts/ds-accept/analysis。 |
| 彩排 | 当前 `make demo-run1`（运行1+学习）、`make demo-run2`（运行2+对照）；或 `python -m engine.demo all --n-a 5 --n-b 5 --n-c 5 --experiment <新ID>`；实际 cohort/options 已归档。`make demo-mock` 是离线模式，但会写运行目录及独立版本库，不在本任务执行。 |
| gate-fix | 历史 `python -m analysis.gate_fix --run`；停止/恢复逻辑见 gate_resume.py、gate_finalize.py；配置恢复改动不是无人工干预的纯进化增益。脚本位于 scripts/ds-gate/analysis，依赖该实验尚未合入的引擎实现，不能直接用当前 main 代替。 |

## 5. 安全扫描、排除和校验

最终离线验收：**1227 passed**（19.68 秒）；**10/10 契约示例通过**；密钥/认证头/环境文件扫描 **0 命中**，2595 条来源记录的归档摘要全部一致。归档约 40 MB（以 validation/sizes.txt 的 du 输出为准），所有文件小于 20 MB。

归档前逐来源扫描，归档后扫描所有落盘文件与 gzip 解压后的每个成员；检查密钥常见前缀、认证 scheme/头名称、任意以 API_KEY 结尾的变量赋值、环境配置文件路径。匹配只报告位置，不输出敏感内容。扫描器在 [scripts/verify_archive.py](scripts/verify_archive.py)，同时检查 JSON 可读、路径安全、20 MiB 限制与 manifest SHA256。扫描规则采用分段字节串，避免扫描脚本自身的规则文本产生自命中。

安全处理清单（源文件未改）：

- reports/evo-trial.md 的原第 313、343、473、509 行含认证头相关错误串，删除整行并留脱敏标记。
- evo-trial 中 ds_nothink/jev × g1/g2 的 evolution.json：删除 `/reflector/fallback_reason` 原值，替换为脱敏标记；model/fell_back 等结果保留。其余 JSON 字段不变。
- plots/ds_thinking-curves.png 的二进制字节偶然命中模式，保守排除；同名 SVG 保留。这不是确认发现了可用密钥。
- 两个 demo/.lock 排除；所有 .git、环境配置文件、缓存、依赖目录及依赖安装日志不收。evo-viz-deps 与 evo-viz-install.log 不在来源收集范围。普通实验日志、HTTP 账本已扫描后保留。
- 判断器已有报告仅引用 docs 路径；分类器原始结果仅引用 analysis/out，未复制、未改。它们不是新增归档文件，归档字节数不计其体积。

校验命令（均离线）：

```sh
python3 experiments/2026-11-14/scripts/verify_archive.py
PYTHONDONTWRITEBYTECODE=1 /Users/zhangheqing/bohack/ds-safety/.venv/bin/python experiments/2026-11-14/scripts/validate_checkout.py
make -o .venv/.requirements-installed contracts
 du -sh experiments/2026-11-14
 du -sh experiments/2026-11-14/* experiments/2026-11-14/data/*
```

验收细节见 [validation/README.md](validation/README.md)。初次裸 worktree 测试缺少被忽略的 privacy SFT 导出；通过现有生成器在临时目录生成，临时链接后执行指定 `pytest -q --ignore=api`，无源码/数据修补，结束移除链接。make 使用临时 .venv 链接指向指定已有环境，`-o` 只跳过安装前置项，10 个契约示例实际验证，结束移除链接。测试自身在 pytest 临时目录创建测试版 git 库；未触碰当前或来源仓库的 Git 元数据，也没有对项目 commit。

## 6. 建议继续补充的方向（不预设结论）

- 更大样本、多次重复、独立 B/offline 的噪声底线，区分模拟来访采样与模型调用随机性。
- 固定其他配置的 LLM/template 渲染对照，逐条核对新增/丢失线索与跨轮状态。
- 门禁顺序跑、同并发/重试配置下的重复测量，单列网络异常、降级、排除及候选排序影响。
- 替换有出处的状态模型参数后对现有会谈离线重算，保留旧参数结果，并报告敏感性与参数不确定性。
- 对 C-014 等疑点做话题/工具预算与动作上限的受控比较，保留安全规则固定边界。
