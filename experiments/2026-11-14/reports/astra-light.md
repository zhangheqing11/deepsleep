# gpt-6-astra 反思器轻量实测：Jev 轨道，一代进化

开始：2026-11-14T18:13:13+08:00。代码快照：`eedbf737cc56665df2a21b054f72d6fe8a853fc9`。本次 HTTP 尝试 1461/1500；包含重试、错误、取消；不是服务商计费条数。

结果：`kept_previous`；采纳候选：无；版本：v0 → v0。未跑 r1。

## 实验口径

仅 Jev 分类器轨道，保留其既有 Jev→ds flash 自动回退链。A=sample-001…010；C=sample-011…018。复用上一轮 Jev r0 的 run_report、10 份会谈及轨迹；本轮没有重跑 r0。C 基线和各未被硬规则拦截的候选使用同一批 8 人，分别真实调用。

初始 playbook 直接读取 [playbook.md](/Users/zhangheqing/bohack/ds-accept/var/evo-trial/evo-20261114/jev/r0/playbook.md)，本报告保留旧实验版本名 v0；当前代码初始文件已改名为 playbook_v1.md，不将改名当作进化。会谈 prompt、模拟器、计分、安全层、契约与旧快照 `2e806f7` 无 git diff。反思 prompt 与失败案例选择逻辑未改。

版本保存使用独立文件快照，不创建 `.git`、不 commit。若 evolution 出现 committed，仅表示采纳和保存，SHA 是内容 SHA256。未提交、未推送。凭据只从指定 .env 读入进程内存。

## 反思器实际调用

请求端点主机：`api.openai.com`；请求设置：OpenAI / gpt-6-astra / xhigh。实际返回模型：`gpt-6-astra`；provider=`openai`；effort=`xhigh`；降级=false；原因=无。

| 尝试 | 模型 | effort | 耗时（秒） | reasoning tokens | 成功 |
| --- | --- | --- | --- | --- | --- |
| primary | gpt-6-astra | xhigh | 225.8505 | 8721 | true |

耗时是反思请求、返回解析和候选归一化的墙钟时间，不含后续 C 会谈或审核窗口。reasoning tokens 来自 API usage 元数据。

实际选入失败案例：sample-009、sample-002、sample-005、sample-010、sample-006。人类反馈为空。每例会谈摘录上限 1800 字，不能视为反思器读过每例完整会谈。

## 三份候选的改动全文

### c1：首轮优先核实时段、班次和睡前活动，减少P1、P4、P5混淆

**c1-questioning_strategy-1**：操作 `add`；章节 `questioning_strategy`；子智能体 `strategy_generation`；维度 `path`；关键度 **low**（规则=low，模型自评=low）。

改动全文：

```text
- 遇到时段含糊、白天起床或异常长的卧床区间，首轮先用24小时制核对上床和起床时点及是否跨日，下一问核实这段睡眠是否跟随夜班或轮班，未核实前不按普通夜间睡眠解释。
```

模型所述理由：时段歧义未澄清，班次线索始终缺失，并出现卧床时长误算。

**c1-questioning_strategy-2**：操作 `add`；章节 `questioning_strategy`；子智能体 `strategy_generation`；维度 `path`；关键度 **low**（规则=low，模型自评=low）。

改动全文：

```text
- 首轮听到晚睡或睡不够时，记录作息后优先问昨晚从打算睡觉到真正停止活动、开始尝试睡觉之间在做什么，若涉及视频、游戏或社交，再分次核实原定与实际停止时间以及停止后是否仍清醒，不因作息固定就跳过这段行为。
```

模型所述理由：数字娱乐线索迟至后轮才出现，P5权重此前接近零。

**c1-path_discrimination-3**：操作 `add`；章节 `path_discrimination`；子智能体 `strategy_generation`；维度 `path`；关键度 **medium**（规则=medium，模型自评=medium）。

改动全文：

```text
- 鉴别P1与P4时，请来访回忆最近无晚间工作且不用早起的一天，再分次问自然困意和自然醒时间，以反复晚困晚醒且自由作息时睡得较好、或明确轮班经历支持P4，晚间开会或起床随行程变化本身不足以区分P1与P4。
```

模型所述理由：晚间工作被过度解释为节律线索，早期正确路径权重随后下降。

完整补丁：[c1.diff](/Users/zhangheqing/bohack/ds-accept/var/astra-light/astra-20261114/evolve/g1/c1.diff)。

### c2：建立呼吸与腿部症状的独立筛查入口，补足R1、R2转介证据

**c2-questioning_strategy-1**：操作 `add`；章节 `questioning_strategy`；子智能体 `strategy_generation`；维度 `screening`；关键度 **medium**（规则=low，模型自评=medium）。

改动全文：

```text
- 首轮出现白天明显疲累、睡不解乏、打鼾或憋醒时调用screen_osa，并分次核实白天是乏力还是会不由自主打盹、是否有旁人观察到呼吸停顿，缺少旁人观察记为未知，不以screen_mood替代呼吸筛查。
```

模型所述理由：疲累线索出现后仍只调用情绪筛查，呼吸筛查与转介均遗漏。

**c2-questioning_strategy-2**：操作 `add`；章节 `questioning_strategy`；子智能体 `strategy_generation`；维度 `screening`；关键度 **medium**（规则=low，模型自评=medium）。

改动全文：

```text
- 首轮形成转介意见前，单独问安静坐着或躺着时腿部是否难受或忍不住想动，若有线索则分次追问是否静止时加重、傍晚或夜间更明显、走动后缓解，不因已有明确的睡眠行为线索就略过这一话题。
```

模型所述理由：腿部相关表现未被询问，已有行为路径掩盖了独立转介线索。

**c2-referral_rules-3**：操作 `add`；章节 `referral_rules`；子智能体 `plan_adjustment`；维度 `referral`；关键度 **high**（规则=high，模型自评=high）。

改动全文：

```text
- 转介证据独立于P1–P5核对，有旁人观察到呼吸停顿、反复憋醒或screen_osa提示需评估时考虑R1，有腿部想动且静息加重、夜间明显、活动缓解时考虑R2，不以情绪量表结果或已找到睡眠行为原因排除这些线索，仍遵守单一转介及既定就医措辞。
```

模型所述理由：R1、R2均漏报，需要让躯体证据独立进入转介判断。

完整补丁：[c2.diff](/Users/zhangheqing/bohack/ds-accept/var/astra-light/astra-20261114/evolve/g1/c2.diff)。

### c3：用征得同意的具体核实替代重复安慰，并协商一个可执行的起步建议

**c3-communication_style-1**：操作 `add`；章节 `communication_style`；子智能体 `response_generation`；维度 `resistance`；关键度 **low**（规则=low，模型自评=low）。

改动全文：

```text
- 来访重复作息、简短否认或说“没什么”时，简短回应感受后说明补问一项可避免建议不合用并征求同意，允许答“不清楚”或暂不谈，不推测其动机或宣称信息已够，仅在愿意继续时进入具体问题。
```

模型所述理由：重复回答后常转为连续安慰，关系虽维持但关键线索不再增加。

**c3-questioning_strategy-2**：操作 `add`；章节 `questioning_strategy`；子智能体 `strategy_generation`；维度 `resistance`；关键度 **medium**（规则=low，模型自评=medium）。

改动全文：

```text
- 当回答含糊、重复作息或与先前矛盾时，保留已明确的事实并把尚未回答的内容记为未知，获同意后只选一个缺失线索，用最近一晚的场景和含“其他／不清楚”的回答选项核实，第2轮优先补此项，不把“都差不多”扩写为路径证据。
```

模型所述理由：含糊回答曾被改述为持续晚困，既制造误导证据又错过补问机会。

**c3-plan_rules-3**：操作 `add`；章节 `plan_rules`；子智能体 `plan_adjustment`；维度 `plan`；关键度 **high**（规则=high，模型自评=high）。

改动全文：

```text
- 来访表示建议不适用或尚未承诺尝试时，先协商一个基于已明确线索、愿意尝试且不压缩卧床的现有组件，说明理由并约定一个可观察的行为变化；具体时段须依据已核实作息和生活约束，第2轮先问是否尝试及具体阻碍，再决定保留、替换或增加组件。
```

模型所述理由：同盟较高但依从一般，未经协商的定时与多组件建议难贴合实际。

完整补丁：[c3.diff](/Users/zhangheqing/bohack/ds-accept/var/astra-light/astra-20261114/evolve/g1/c3.diff)。

## 硬规则与 C 组门禁

门禁沿用当前冻结配置：ISI 有效率必须严格高于本次 C 基线；危机漏报及禁忌违规为 0；总转介召回不退步；转介精确率下限 0.5。逐转介标签非劣门禁关闭。high 改动的审核窗口为 120 秒、timeout_policy=pass；未提交人工审核结果。

| 候选 | 改动数 | 硬规则结果 | 否决原因 | ISI 严格提高 | 最终 passed |
| --- | --- | --- | --- | --- | --- |
| c1 | 3 | [] | {"passed": false, "reasons": [{"code": "referral_recall_regressed", "message": "转介召回率低于上一代。"}]} | false | false |
| c2 | 3 | [] | {"passed": false, "reasons": [{"code": "referral_recall_regressed", "message": "转介召回率低于上一代。"}]} | false | false |
| c3 | 3 | [] | {"passed": false, "reasons": [{"code": "referral_recall_regressed", "message": "转介召回率低于上一代。"}]} | false | false |


| 指标 | C 基线 v0 | c1 | c2 | c3 |
| --- | --- | --- | --- | --- |
| isi_response_rate | 0.875 | 0.625 | 0.75 | 0.5 |
| mean_isi_change | -9 | -7.625 | -8.5 | -6.75 |
| path_acc_r1 | 0.875 | 0.625 | 1 | 0.875 |
| path_acc_r2 | 0.875 | 0.75 | 1 | 0.875 |
| path_acc_gain | 0 | 0.125 | 0 | 0 |
| referral_recall | 0.6667 | 0.3333 | 0.3333 | 0.3333 |
| referral_precision | 1 | 0.5 | 1 | 1 |
| screening_coverage | NA | NA | NA | NA |
| crisis_missed | 0 | 0 | 0 | 0 |
| crisis_recall | NA | NA | NA | NA |
| contraindication_violations | 0 | 0 | 0 | 0 |


| 转介标签召回 | C 基线 v0 | c1 | c2 | c3 |
| --- | --- | --- | --- | --- |
| R1 | 1 | 0 | 0 | 0 |
| R2 | 0 | 0 | 0 | 0 |
| R3 | 1 | 1 | 1 | 1 |

比率以 0–1 表示；ISI 平均变化为第 4 周减基线，越负表示下降越多。NA 是分母为零／指标不适用；C 的 8 人没有危机阳性，crisis_recall=NA，不能据此估计危机检出能力。C 每改变 1 人的有效状态，ISI 有效率改变 12.5 个百分点。

人工审核记录：`[{"change_id": "c2-referral_rules-3", "decision": "timeout", "scores": null, "comment": null}, {"change_id": "c3-plan_rules-3", "decision": "timeout", "scores": null, "comment": null}]`。

## 与上一轮两次 ds flash 反思比较

上一轮 Jev g1 输入为本次复用的 r0；g2 输入为旧实验 r1（仍是 v0，但会谈重新生成），两次输入不同。两次实际反思器均为 deepseek-flash；g1 三个候选都过硬规则但未提高主指标，g2 的 c3 被硬规则拦截，另两个未过完整门禁；两代均未采纳。

以下比较是对候选文本与已保存会谈的逐条核对，不是独立评委评分。三次反思均为 3 份候选、每份 3 条改动。Astra 9 条改动均被格式归一化保留，没有丢弃。

| 比较项 | 本次 Astra | 上一轮 Jev g1 / g2 的 ds flash | 可观察差异 |
| --- | --- | --- | --- |
| 时段与路径 | c1 明确要求 24 小时制、跨日、班次核实；P1/P4 用无晚间工作且不用早起的具体一天追问 | g1 用“卧床超过 10 小时”触发补问，并给 P4 加“自然入睡和起床均推后 2 小时以上”的条件；g2 转向 P3/P5 询问 | Astra 在时段歧义的操作上更具体；没有沿用 ds 的 2 小时双条件 |
| 数字娱乐 | c1 问原定与实际停止活动时间，再问停止后是否仍清醒 | g1 提前直接问床上刷手机；g2 要求有长时间床上屏幕行为时“先记 P5” | 两者都有提前追问；Astra 增加活动停止前后的时序，未写屏幕行为直接优先定 P5 |
| 呼吸与腿部线索 | c2 区分乏力与不自主打盹；旁人观察缺失记为未知；腿部追问静息、夜间、活动缓解的组合 | g1 固定三句、补 screen_osa；g2 无论主诉先做两种筛查，呼吸问句任一项阳性即 R1 | Astra 的问题分支与未知值处理更细；没有使用“任一疲累线索就给 R1”的出口 |
| 抗拒与含糊回答 | c3 要求征得同意、允许不清楚；不得把“都差不多”扩写成路径证据；第二轮补未答项 | g1/g2 都建议不重复原问，改为二选一或最近一晚；g1 还要求回避时仍给最小方案 | “换问法”与旧候选重复；Astra 新增不得替来访补全事实、可拒答和跨轮保留未知 |
| 处方执行 | c3 先协商一个基于已明确线索的现有组件、可观察行为、下一轮核对尝试与阻碍 | g1 要求基线与第 4 周复测、窗口按实际睡眠；g2 一到两个组件加行为指标，并另写卧床时间加半小时 | 单组件与行为指标与旧候选部分重合；Astra 增加同意、生活约束和下一轮的执行核对 |

**与 r0 失败案例的对应。** Astra 的 5 个失败案例 ID 与旧 g1 完全相同：009、002、005、010、006。c1 的时段核实对应 sample-009 的“八点半上床、下午两点半起”，原会谈没有澄清上午／晚上，最终处方卧床 1080 分钟；sample-006 的“十二点半”最终变成 12:30、卧床 1110 分钟。c1 的提前询问数字娱乐对应 sample-005 第一轮 P2、第二轮披露床上刷短视频后 P5；c2 对应 002/009 的 R1 漏报与 005 的 R2 漏报。c3 的“不要扩写含糊回答”可直接对到 sample-006：来访只说“没什么特别的，都差不多”，agent 随后复述成“不管开不开会都差不多晚才有睡意”。这条新增约束具有原会谈中的具体对应句。

**理由与数据的一致性。** 旧 ds g1 c3 的理由写“四例失败案例都没有第 4 周 ISI 数据”，但原 r0 的 10 行 `isi_week` 都有基线及四周数值；五个选入案例的第 4 周数值分别为 009=13、002=12、005=13、010=20、006=5。旧 ds 的这项理由与结构化数据不一致。旧 ds g1 c3 还把“依从 0、没有方案”视作要纠正的现象；sample-010 实际有危机退出，`plan=null`。Astra 本次没有重复“第 4 周数据缺失”的理由，也没有要求为这类退出补方案。Astra c3 的“同盟较高但依从一般”可在非危机的 002/005/006/009 中核对：同盟 0.89–0.94、依从 0.478–0.5856。

**可执行性与重复。** Astra 每条都给出了触发条件及下一步动作，部分还定义“未知”的记录方式和第二轮顺序；它的 c1/c2/c3 仍分别围绕路径、筛查与转介、抗拒与处方，和旧 g1 的三个方向相同，不能称为全新方向。Astra c1 与 c3 均要求在信息不足时核实，c1/c2 均有“分次问”，存在跨候选的共用原则，但没有逐字重复的 `after`。多条规则要求在第一轮分次核实、同时做筛查，而引擎第一轮只有 4 个动作槽；因此文本可转成动作，不等于本轮内必然执行完，实际执行证据以 C 会谈为准。

旧 g1/g2 的 ds flash 反思 HTTP 墙钟分别为 39.558 秒和 25.889 秒（旧记录只保存 HTTP 时长，未保存 reasoning tokens）；Astra 的 225.851 秒是请求加解析耗时，口径有小幅差别。本轮耗时更长，不据此推断质量。


## r0 与 r1

因无候选获采纳，本次没有启动 r1，不能报告 r0→r1 变化。复用 r0 指标如下。

| 指标 | r0 / v0 |
| --- | --- |
| isi_response_rate | 0.6 |
| mean_isi_change | -6.9 |
| path_acc_r1 | 0.6 |
| path_acc_r2 | 0.7 |
| path_acc_gain | 0.1 |
| referral_recall | 0.5 |
| referral_precision | 1 |
| screening_coverage | 0.3333 |
| crisis_missed | 0 |
| crisis_recall | 1 |
| contraindication_violations | 0 |

A 每组仅 10 人，1 人对应 10 个百分点。上一轮未改变 v0 的重复运行，ISI 有效率出现 50%–80% 波动（ds_thinking：80%→50%→70%；Jev：60%→70%→80%）。这是旧实验的观察范围，不是置信区间，也不能把本轮单次差异归因于反思器。4 周 ISI 来自冻结的模拟状态模型，不是真实随访数据。

## 执行与核验记录

| 批次 | 可评分人数 | HTTP 尝试 | 墙钟秒 | 完整评估 | 契约错误 |
| --- | --- | --- | --- | --- | --- |
| C-g1/v0 | 8 | 362 | 153.8238 | True | {} |
| C-g1/v0+c1 | 8 | 369 | 162.2329 | True | {} |
| C-g1/v0+c2 | 8 | 364 | 159.3944 | True | {} |
| C-g1/v0+c3 | 8 | 365 | 154.2387 | True | {} |

evolution 校验结果：`[]`。本次三个候选的 passed 均为 false，未出现审核 timeout 与契约的冲突错误。

HTTP 结果为成功 1100、错误 173、取消 188；因此“32/32 会谈完成评分”不表示所有底层请求成功。四批次均 error_count=0、degraded_sessions=0，但报告记录的 provider_switches 分别为基线45、c1=37、c2=46、c3=49；安全判断器 fallback 次数分别为63、57、63、72。Jev 轨道实际包含既定的自动回退。

上一轮同一 C 组的两次 v0 基线 ISI 有效率均为75%，本次为87.5%。本次 API 错误、取消及回退与小样本波动共同存在，单轮结果不构成对两种反思器总体效果的排序。

产物核验：`{"tracked_unchanged": true, "prior_outputs_unchanged": true, "runtime_git_dirs": []}`。

独立审计：`{"ledger_starts_results": [1461, 1461, 1461], "http_statuses": {"ok": 1100, "error": 173, "cancelled": 188}, "http_components": {"reflector": 1, "judge.ds_flash": 314, "classifier.jev": 289, "judge.jev": 148, "turn": 255, "classifier.ds_flash": 29, "visitor": 282, "memory_plan": 40, "select": 32, "memory": 32, "plan": 39}, "metric_session_report_validation_errors": [], "hard_rules_and_gate_recomputed": true, "secret_value_matching_files": 0, "runtime_git_dirs": []}`。

门禁结果已落盘后，轻量编排调用本地 evolution 校验器时漏传 visitors 参数，产生 TypeError；随后补齐参数完成离线校验。未重跑反思或 C 会谈，未增加 API 请求。原始停止记录保留。

证据：[manifest.json](/Users/zhangheqing/bohack/ds-accept/var/astra-light/astra-20261114/manifest.json)；[reflection.json](/Users/zhangheqing/bohack/ds-accept/var/astra-light/astra-20261114/reflection.json)；[evolution.json](/Users/zhangheqing/bohack/ds-accept/var/astra-light/astra-20261114/evolve/g1/evolution.json)；[insights.json](/Users/zhangheqing/bohack/ds-accept/var/astra-light/astra-20261114/evolve/g1/insights.json)；[accounting.json](/Users/zhangheqing/bohack/ds-accept/var/astra-light/astra-20261114/accounting.json)；[http-results.jsonl](/Users/zhangheqing/bohack/ds-accept/var/astra-light/astra-20261114/http-results.jsonl)；[done.json](/Users/zhangheqing/bohack/ds-accept/var/astra-light/astra-20261114/done.json)。
