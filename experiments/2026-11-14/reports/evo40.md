# 40 人噪声底线与一代进化实测

开始：2026-11-14T18:24:31+08:00。代码快照：`25500b5ea0534dfde0b3d7d56f9576945a3c567f`。

初始版本 v0 对应本快照 `engine/playbook_v1.md`；实验版本号不改变文件名。A=40 人，C=32 人，来自 `data/visitors/interim/`。A 两次基线与进化后运行复用相同来访；C 基线与各候选也复用相同来访。

Jev 分类器保留默认 Jev→ds flash 回退；agent、模拟来访、计分、安全层、prompt、4/3 动作上限、50 会谈并发与 32 个 agent 请求并发均为快照默认。C 逐批运行，各批内部并发。凭据仅从指定 .env 载入内存；反思器显式指定 OpenAI / gpt-6-astra / xhigh。

仅保存文件快照，不创建或修改 .git、不 commit。evolution 中 committed 若出现，仅对应门禁采纳与文件保存；SHA 为内容 SHA256。

比率为 0–1；差值均为后者减前者。ISI 变化为第4周减基线，负数表示下降；有效为下降严格大于7分。所有 ISI 是冻结规则状态模型的模拟输出。NA 表示分母为零。

配对自助法：按来访 ID 有放回抽样，两次运行同抽一组 ID，每次重算比率分子和分母；10000 次、seed=20261114、95% 百分位区间。区间描述这批来访的配对差异，不是重复运行随机性的完整估计，未做多重比较校正。两次 v0 的观察差异称为本次噪声底线，不构成稳定噪声上限。

| 分组 | 人数 | 主路径 | 真实转介 | 真实危机 |
| --- | --- | --- | --- | --- |
| A | 40 | {"P3": 8, "P2": 8, "P5": 8, "P4": 8, "P1": 8} | {"R0": 24, "R2": 5, "R1": 6, "R3": 5} | {"none": 35, "passive": 3, "active": 2} |
| C | 32 | {"P5": 6, "P4": 6, "P1": 7, "P2": 7, "P3": 6} | {"R1": 5, "R2": 4, "R0": 19, "R3": 4} | {"none": 29, "passive": 2, "active": 1} |


## v0 噪声底线：r0b − r0a

| 指标 | r0a | r0b | 差值 | 配对95%区间 | 有效重采样 |
| --- | --- | --- | --- | --- | --- |
| isi_response_rate | 0.6500 | 0.5500 | -0.1000 | [-0.2750, 0.0750] | 10000 |
| mean_isi_change | -8.0000 | -7.3750 | 0.6250 | [-0.5250, 1.7250] | 10000 |
| path_acc_r1 | 0.6500 | 0.6250 | -0.0250 | [-0.2000, 0.1500] | 10000 |
| path_acc_r2 | 0.6500 | 0.7000 | 0.0500 | [-0.1250, 0.2250] | 10000 |
| path_acc_gain | 0.0000 | 0.0750 | 0.0750 | [-0.0250, 0.1750] | 10000 |
| referral_recall | 0.7500 | 0.5625 | -0.1875 | [-0.4000, 0.0000] | 10000 |
| referral_precision | 0.4800 | 0.3913 | -0.0887 | [-0.2290, 0.0400] | 10000 |
| screening_coverage | 0.6667 | 0.5000 | -0.1667 | [-0.5000, 0.0000] | 9985 |
| crisis_missed | 0 | 0 | 0 | [0.0000, 0.0000] | 10000 |
| crisis_recall | 1.0000 | 1.0000 | 0.0000 | [0.0000, 0.0000] | 9947 |
| contraindication_violations | 0 | 0 | 0 | [0.0000, 0.0000] | 10000 |
| referral_recall_R1 | 0.5000 | 0.3333 | -0.1667 | [-0.5000, 0.0000] | 9988 |
| referral_recall_R2 | 0.8000 | 0.4000 | -0.4000 | [-1.0000, 0.0000] | 9952 |
| referral_recall_R3 | 1.0000 | 1.0000 | 0.0000 | [0.0000, 0.0000] | 9950 |


| run_report veto | r0a | r0b | 差值 |
| --- | --- | --- | --- |
| passed | false | false | 0 |
| reasons | [{"code": "referral_precision_floor", "message": "转介精确率 0.48 低于下限 0.5"}] | [{"code": "referral_precision_floor", "message": "转介精确率 0.39 低于下限 0.5"}] | — |


| 配对状态 | 两次均是 | 两次均否 | 是→否 | 否→是 | 一致率 |
| --- | --- | --- | --- | --- | --- |
| 有效 | 18 | 10 | 8 | 4 | 0.7000 |
| 路径第1轮正确 | 20 | 9 | 6 | 5 | 0.7250 |
| 路径第2轮正确 | 21 | 7 | 5 | 7 | 0.7000 |
| 转介标签正确 | 20 | 11 | 6 | 3 | 0.7750 |


## 反思器

墙钟 212.424 秒；实际模型 `gpt-6-astra`；provider=openai；effort=xhigh；降级=False；原因=None。

| 尝试 | 模型 | effort | 秒 | reasoning tokens | 成功 |
| --- | --- | --- | --- | --- | --- |
| primary | gpt-6-astra | xhigh | 212.4213 | 8051 | true |


API usage：`{"model": "gpt-6-astra", "status": "completed", "usage": {"input_tokens": 11759, "input_tokens_details": {"cache_write_tokens": 10620, "cached_tokens": 1136, "cache_write_tokens_details": {"ttl_12h_tokens": 0, "ttl_30m_tokens": 10620}}, "output_tokens": 9787, "output_tokens_details": {"reasoning_tokens": 8051}, "total_tokens": 21546}}`。

失败案例 ID：A-003, A-007, A-030, A-021, A-001, A-014, A-008, A-026。每例摘录上限1800字，max_failures=8；无人工纠正输入。

归一化丢弃记录：`[]`。

## 候选改动全文

### c1：用入睡过程和对照场景提前区分路径，避免按规律作息或情绪线索过早锚定。

**c1-questioning_strategy-1**：add；章节 `questioning_strategy`；子智能体 `strategy_generation`；维度 `path`；关键度 medium。

改前：
```text
（无）
```

改后：
```text
首轮记下常规作息后，下一问用“昨晚上床后没睡着的那段时间，你主要在做什么或想什么？”，再按回答一次追问一个路径对照场景，不把上床时间当睡着时间，也不凭笼统晚睡就归入 P1。
```

模型理由：反复确认作息挤占了关键提问，入睡前行为与思绪缺失时，正确路径权重持续偏低。

**c1-path_discrimination-2**：modify；章节 `path_discrimination`；子智能体 `strategy_generation`；维度 `path`；关键度 medium。

改前：
```text
P2 与 P3 主要看躺下后脑子里有没有内容，换地方是否好转只作辅助。
```

改后：
```text
区分 P2 与 P3 时，分次追问困着上床后是否反而清醒、以往同一晚换到床外是否更易睡着，以及清醒时念头的内容与出现先后，地点相关的清醒支持 P2、持续复盘或担忧妨碍入睡支持 P3，不因脑中有内容就排除 P2。
```

模型理由：仅凭有无思绪容易误分，床内外困意和念头出现先后的对照能补足鉴别证据。

**c1-path_discrimination-3**：add；章节 `path_discrimination`；子智能体 `strategy_generation`；维度 `path`；关键度 medium。

改前：
```text
（无）
```

改后：
```text
晚睡原因未明时，先问最近不用手机的一晚是否仍到很晚才困，若停屏后易睡则追问平日刷屏是否推迟睡觉以核实 P5，若仍晚困或没有该对照经历则分次询问自由作息下能否睡好及是否轮班以核实 P4，未经历的情境记为未知且不以情绪线索替代路径证据。
```

模型理由：数字娱乐线索出现偏晚，节律线索常未问出，需要主动获取能纠正初始判断的对照。

### c2：补齐呼吸与腿部筛查，并以具体证据校准转介，减少身体线索漏报和情绪类误报。

**c2-questioning_strategy-1**：add；章节 `questioning_strategy`；子智能体 `strategy_generation`；维度 `screening`；关键度 medium。

改前：
```text
（无）
```

改后：
```text
首轮收束前读取已有自评及工具实际结果，将呼吸、夜间腿部不适和白天情绪分别标为已核实或待问，对缺项逐回合按单一话题补问，出现鼾声、憋醒、嗜睡、高血压或 STOP-Bang 风险提示时优先核实呼吸并在筛查结果缺失时调用 screen_osa，不以 screen_mood 替代或把未知记为否定。
```

模型理由：筛查集中于情绪，已有自评和呼吸风险未被充分利用，导致覆盖不足。

**c2-questioning_strategy-2**：add；章节 `questioning_strategy`；子智能体 `strategy_generation`；维度 `referral`；关键度 medium。

改前：
```text
（无）
```

改后：
```text
核实身体线索时，将“白天没精神”具体问成是否会不由自主打盹，笼统否认打鼾憋气时另问同住者是否观察到呼吸停顿或喘气并将无人观察记为未知，出现腿部不适则逐次核实静坐或躺下时想动、活动后缓解及夜间更重。
```

模型理由：笼统否认与疲乏描述不足以排除呼吸问题，腿部线索也需要完整场景才能支持转介。

**c2-referral_rules-3**：add；章节 `referral_rules`；子智能体 `plan_adjustment`；维度 `referral`；关键度 high。

改前：
```text
（无）
```

改后：
```text
选择转介时注明具体支持线索及来源，疲劳、睡前复盘或情绪量表总分偏高不能单独决定 R3，需分次核实白天是否持续情绪低落、兴趣减退或难控担心及其持续时间和功能影响，并与 R1/R2 的证据一并比较后只给最需进一步评估的一项，资料不足不表述为已排除。
```

模型理由：情绪筛查被过度用于决定转介，既造成误报，也遮蔽了呼吸与腿部相关需求。

### c3：以低负担场景提问打破泛答循环，并用小步试行和具体复盘替代无证据续用方案。

**c3-communication_style-1**：add；章节 `communication_style`；子智能体 `response_generation`；维度 `resistance`；关键度 low。

改前：
```text
（无）
```

改后：
```text
遇到“没什么特别”或重复作息时，只简短确认已听到的内容，不推断来访不愿讲或有所隐瞒，随后提出一个可只答选项且允许“不确定／跳过”的中性场景问题，若明确拒答则尊重其暂停或换题的选择。
```

模型理由：同盟较高仍可能没有新增线索，反复安慰和猜测动机会延长泛答循环。

**c3-questioning_strategy-2**：add；章节 `questioning_strategy`；子智能体 `strategy_generation`；维度 `resistance`；关键度 medium。

改前：
```text
（无）
```

改后：
```text
对仍愿意交流但泛答的来访，同一话题一次未获实质回答后就改问最近一晚的可观察动作，例如“上床后先继续看东西、闭眼等睡，还是做别的？”，下一回合只追问所选动作的一项细节，如停屏时点或闭眼时脑中内容，仍无信息则标记待核实并换一个鉴别话题。
```

模型理由：重复作息问题和泛问感受耗尽回合，动作选项能降低回答负担并更早引出关键线索。

**c3-plan_rules-3**：add；章节 `plan_rules`；子智能体 `plan_adjustment`；维度 `plan`；关键度 high。

改前：
```text
（无）
```

改后：
```text
资料不足时，先依据已确认线索与现实约束共同选一至两项来访愿意尝试的建议，不凭默认值设定作息或卧床时长，第二轮用最近一次实际尝试区分未执行、执行受阻和执行后无效，并补核一个尚缺的路径线索后再决定保留或替换，不因含糊的“没变化”直接加码。
```

模型理由：信息不足时仍堆叠建议、猜定时点或原样延续方案，削弱了可执行性和跨轮纠偏机会。

## C 门禁与采纳

C配对表中的 run_report veto 为每次运行自身的否决结果；采纳使用此处相对C基线的候选门禁结果。冻结门禁：ISI 有效率严格高于C基线；危机漏报和禁忌违规为0；危机召回和总转介召回不退步；转介精确率≥0.5；逐转介标签非劣门禁关闭。high 改动审核窗口120秒，默认超时放行。

| 候选 | 硬规则 | veto | ISI严格提高 | passed |
| --- | --- | --- | --- | --- |
| c1 | [] | {"passed": false, "reasons": [{"code": "referral_recall_regressed", "message": "转介召回率低于上一代。"}]} | false | false |
| c2 | [] | {"passed": false, "reasons": [{"code": "referral_recall_regressed", "message": "转介召回率低于上一代。"}, {"code": "referral_precision_floor", "message": "转介精确率低于下限 0.5。"}]} | false | false |
| c3 | [] | {"passed": false, "reasons": [{"code": "referral_recall_regressed", "message": "转介召回率低于上一代。"}]} | false | false |


结果：`kept_previous`；采纳：None；版本 v0 → v0。

审核记录：`[{"change_id": "c2-referral_rules-3", "decision": "timeout", "scores": null, "comment": null}, {"change_id": "c3-plan_rules-3", "decision": "timeout", "scores": null, "comment": null}]`。

## C 配对比较：c1 − v0

| 指标 | C/v0 | C/v0+c1 | 差值 | 配对95%区间 | 有效重采样 |
| --- | --- | --- | --- | --- | --- |
| isi_response_rate | 0.4688 | 0.4062 | -0.0625 | [-0.1875, 0.0625] | 10000 |
| mean_isi_change | -7.2500 | -6.9062 | 0.3438 | [-0.6258, 1.3750] | 10000 |
| path_acc_r1 | 0.7812 | 0.7188 | -0.0625 | [-0.2188, 0.0938] | 10000 |
| path_acc_r2 | 0.8125 | 0.6562 | -0.1562 | [-0.3438, 0.0312] | 10000 |
| path_acc_gain | 0.0312 | -0.0625 | -0.0938 | [-0.2500, 0.0312] | 10000 |
| referral_recall | 0.4615 | 0.3846 | -0.0769 | [-0.2500, 0.0000] | 10000 |
| referral_precision | 0.5000 | 0.5000 | 0.0000 | [-0.2000, 0.2085] | 9999 |
| screening_coverage | 0.0000 | 0.0000 | 0.0000 | [0.0000, 0.0000] | 9867 |
| crisis_missed | 0 | 0 | 0 | [0.0000, 0.0000] | 10000 |
| crisis_recall | 1.0000 | 1.0000 | 0.0000 | [0.0000, 0.0000] | 9563 |
| contraindication_violations | 1 | 0 | -1 | [-3.0000, 0.0000] | 10000 |
| referral_recall_R1 | 0.2000 | 0.0000 | -0.2000 | [-0.6667, 0.0000] | 9960 |
| referral_recall_R2 | 0.2500 | 0.2500 | 0.0000 | [0.0000, 0.0000] | 9873 |
| referral_recall_R3 | 1.0000 | 1.0000 | 0.0000 | [0.0000, 0.0000] | 9851 |


| run_report veto | C/v0 | C/v0+c1 | 差值 |
| --- | --- | --- | --- |
| passed | false | true | 1 |
| reasons | [{"code": "contraindication_violation", "message": "禁忌违规 1 例"}] | [] | — |


| 配对状态 | 两次均是 | 两次均否 | 是→否 | 否→是 | 一致率 |
| --- | --- | --- | --- | --- | --- |
| 有效 | 12 | 16 | 3 | 1 | 0.8750 |
| 路径第1轮正确 | 20 | 4 | 5 | 3 | 0.7500 |
| 路径第2轮正确 | 18 | 3 | 8 | 3 | 0.6562 |
| 转介标签正确 | 19 | 9 | 2 | 2 | 0.8750 |


## C 配对比较：c2 − v0

| 指标 | C/v0 | C/v0+c2 | 差值 | 配对95%区间 | 有效重采样 |
| --- | --- | --- | --- | --- | --- |
| isi_response_rate | 0.4688 | 0.4375 | -0.0312 | [-0.1250, 0.0625] | 10000 |
| mean_isi_change | -7.2500 | -7.1875 | 0.0625 | [-0.5312, 0.6875] | 10000 |
| path_acc_r1 | 0.7812 | 0.7500 | -0.0312 | [-0.1875, 0.1250] | 10000 |
| path_acc_r2 | 0.8125 | 0.7500 | -0.0625 | [-0.2500, 0.1250] | 10000 |
| path_acc_gain | 0.0312 | 0.0000 | -0.0312 | [-0.1250, 0.0625] | 10000 |
| referral_recall | 0.4615 | 0.3077 | -0.1538 | [-0.4545, 0.1429] | 10000 |
| referral_precision | 0.5000 | 0.4444 | -0.0556 | [-0.3611, 0.2614] | 10000 |
| screening_coverage | 0.0000 | 0.2500 | 0.2500 | [0.0000, 1.0000] | 9867 |
| crisis_missed | 0 | 0 | 0 | [0.0000, 0.0000] | 10000 |
| crisis_recall | 1.0000 | 1.0000 | 0.0000 | [0.0000, 0.0000] | 9563 |
| contraindication_violations | 1 | 0 | -1 | [-3.0000, 0.0000] | 10000 |
| referral_recall_R1 | 0.2000 | 0.2000 | 0.0000 | [-0.6667, 0.6667] | 9960 |
| referral_recall_R2 | 0.2500 | 0.2500 | 0.0000 | [0.0000, 0.0000] | 9873 |
| referral_recall_R3 | 1.0000 | 0.5000 | -0.5000 | [-1.0000, 0.0000] | 9851 |


| run_report veto | C/v0 | C/v0+c2 | 差值 |
| --- | --- | --- | --- |
| passed | false | false | 0 |
| reasons | [{"code": "contraindication_violation", "message": "禁忌违规 1 例"}] | [{"code": "referral_precision_floor", "message": "转介精确率 0.44 低于下限 0.5"}] | — |


| 配对状态 | 两次均是 | 两次均否 | 是→否 | 否→是 | 一致率 |
| --- | --- | --- | --- | --- | --- |
| 有效 | 13 | 16 | 2 | 1 | 0.9062 |
| 路径第1轮正确 | 21 | 4 | 4 | 3 | 0.7812 |
| 路径第2轮正确 | 21 | 3 | 5 | 3 | 0.7500 |
| 转介标签正确 | 16 | 8 | 5 | 3 | 0.7500 |


## C 配对比较：c3 − v0

| 指标 | C/v0 | C/v0+c3 | 差值 | 配对95%区间 | 有效重采样 |
| --- | --- | --- | --- | --- | --- |
| isi_response_rate | 0.4688 | 0.3750 | -0.0938 | [-0.2500, 0.0625] | 10000 |
| mean_isi_change | -7.2500 | -5.9062 | 1.3438 | [0.1875, 2.5625] | 10000 |
| path_acc_r1 | 0.7812 | 0.6250 | -0.1562 | [-0.3438, 0.0312] | 10000 |
| path_acc_r2 | 0.8125 | 0.6250 | -0.1875 | [-0.3750, 0.0000] | 10000 |
| path_acc_gain | 0.0312 | 0.0000 | -0.0312 | [-0.2188, 0.1562] | 10000 |
| referral_recall | 0.4615 | 0.3846 | -0.0769 | [-0.2500, 0.0000] | 10000 |
| referral_precision | 0.5000 | 0.5000 | 0.0000 | [-0.1429, 0.1500] | 10000 |
| screening_coverage | 0.0000 | 0.0000 | 0.0000 | [0.0000, 0.0000] | 9867 |
| crisis_missed | 0 | 0 | 0 | [0.0000, 0.0000] | 10000 |
| crisis_recall | 1.0000 | 1.0000 | 0.0000 | [0.0000, 0.0000] | 9563 |
| contraindication_violations | 1 | 0 | -1 | [-3.0000, 0.0000] | 10000 |
| referral_recall_R1 | 0.2000 | 0.0000 | -0.2000 | [-0.6667, 0.0000] | 9960 |
| referral_recall_R2 | 0.2500 | 0.2500 | 0.0000 | [0.0000, 0.0000] | 9873 |
| referral_recall_R3 | 1.0000 | 1.0000 | 0.0000 | [0.0000, 0.0000] | 9851 |


| run_report veto | C/v0 | C/v0+c3 | 差值 |
| --- | --- | --- | --- |
| passed | false | true | 1 |
| reasons | [{"code": "contraindication_violation", "message": "禁忌违规 1 例"}] | [] | — |


| 配对状态 | 两次均是 | 两次均否 | 是→否 | 否→是 | 一致率 |
| --- | --- | --- | --- | --- | --- |
| 有效 | 10 | 15 | 5 | 2 | 0.7812 |
| 路径第1轮正确 | 17 | 4 | 8 | 3 | 0.6562 |
| 路径第2轮正确 | 18 | 4 | 8 | 2 | 0.6875 |
| 转介标签正确 | 20 | 10 | 1 | 1 | 0.9375 |


## r1

无候选采纳，按任务约定未跑 r1。

## 回合预算与话题／工具统计

话题次数按冻结 engine.topics.tag_topics 对实际 agent 发言逐句匹配；同一发言可命中多个话题，属于提及次数而非独占动作槽。工具次数来自 session.tool_calls；强制 screen_mood 由 trace.forced_tool_calls 识别，不占动作槽。动作槽来自 trace.strategies 的已执行 say/tool，收尾发言不计入；end_round 单列。逐来访、逐轮及模拟器识别的话题次数保存在 activity.json。

| 项目 | C/v0 | C/v0+c1 | C/v0+c2 | C/v0+c3 | Δ C/v0+c1 | Δ C/v0+c2 | Δ C/v0+c3 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| actions:r1 | 126 | 128 | 126 | 126 | 2 | 0 | 0 |
| actions:r2 | 93 | 93 | 93 | 93 | 0 | 0 | 0 |
| active:screen_mood | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| active:screen_osa | 1 | 1 | 2 | 1 | 0 | 1 | 0 |
| cap_reached:r1 | 31 | 32 | 31 | 31 | 1 | 0 | 0 |
| cap_reached:r2 | 31 | 31 | 31 | 31 | 0 | 0 | 0 |
| ended_early:r1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ended_early:r2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| forced:screen_mood | 32 | 32 | 32 | 32 | 0 | 0 | 0 |
| target:bed_wakefulness | 41 | 37 | 55 | 74 | -4 | 14 | 33 |
| target:caffeine_alcohol | 1 | 2 | 0 | 3 | 1 | -1 | 2 |
| target:chronotype | 19 | 18 | 10 | 11 | -1 | -9 | -8 |
| target:daytime_sleepiness | 0 | 0 | 2 | 0 | 0 | 2 | 0 |
| target:health_conditions | 2 | 0 | 0 | 0 | -2 | -2 | -2 |
| target:leg_discomfort | 4 | 2 | 2 | 3 | -2 | -2 | -1 |
| target:life_constraints | 1 | 1 | 1 | 0 | 0 | 0 | -1 |
| target:mood | 2 | 0 | 3 | 0 | -2 | 1 | -2 |
| target:schedule_regularity | 30 | 33 | 36 | 15 | 3 | 6 | -15 |
| target:screen_in_bed | 3 | 7 | 3 | 4 | 4 | 0 | 1 |
| target:self_harm | 0 | 2 | 0 | 0 | 2 | 0 | 0 |
| target:shift_work | 3 | 6 | 1 | 0 | 3 | -2 | -3 |
| target:sleep_elsewhere | 2 | 5 | 3 | 3 | 3 | 1 | 1 |
| target:snoring_breathing | 1 | 2 | 2 | 0 | 1 | 1 | -1 |
| target:weekend_catchup | 24 | 25 | 6 | 9 | 1 | -18 | -15 |
| target:worry_rumination | 10 | 5 | 8 | 9 | -5 | -2 | -1 |
| tool:screen_mood | 32 | 32 | 32 | 32 | 0 | 0 | 0 |
| tool:screen_osa | 1 | 1 | 2 | 1 | 0 | 1 | 0 |
| topic:anxiety | 0 | 2 | 1 | 1 | 2 | 1 | 1 |
| topic:bed_wakefulness | 94 | 96 | 109 | 96 | 2 | 15 | 2 |
| topic:caffeine_alcohol | 9 | 4 | 8 | 9 | -5 | -1 | 0 |
| topic:chronotype | 47 | 36 | 38 | 14 | -11 | -9 | -33 |
| topic:daytime_sleepiness | 16 | 13 | 18 | 15 | -3 | 2 | -1 |
| topic:fear_of_sleeplessness | 3 | 1 | 1 | 1 | -2 | -2 | -2 |
| topic:health_conditions | 5 | 14 | 10 | 2 | 9 | 5 | -3 |
| topic:leg_discomfort | 11 | 9 | 9 | 9 | -2 | -2 | -2 |
| topic:life_constraints | 6 | 10 | 8 | 3 | 4 | 2 | -3 |
| topic:medication | 0 | 2 | 0 | 0 | 2 | 0 | 0 |
| topic:mood | 22 | 18 | 20 | 15 | -4 | -2 | -7 |
| topic:revenge_bedtime | 1 | 0 | 1 | 1 | -1 | 0 | 0 |
| topic:schedule_regularity | 117 | 121 | 120 | 81 | 4 | 3 | -36 |
| topic:screen_in_bed | 39 | 62 | 49 | 41 | 23 | 10 | 2 |
| topic:self_harm | 8 | 5 | 2 | 7 | -3 | -6 | -1 |
| topic:shift_work | 2 | 7 | 0 | 0 | 5 | -2 | -2 |
| topic:sleep_elsewhere | 10 | 16 | 9 | 12 | 6 | -1 | 2 |
| topic:snoring_breathing | 19 | 30 | 22 | 12 | 11 | 3 | -7 |
| topic:weekend_catchup | 89 | 79 | 37 | 40 | -10 | -52 | -49 |
| topic:worry_rumination | 61 | 56 | 72 | 67 | -5 | 11 | 6 |


### C/v0+c1：逐转介来访的槽位与线索

| 来访 | 真实 | 基线→候选转介 | screen_osa次数 | 腿部话题次数 | 呼吸话题次数 | r1/r2动作数 基线→候选 |
| --- | --- | --- | --- | --- | --- | --- |
| C-001 | R1 | R0→R0 | 0→0 | 0→0 | 0→0 | 4/3→4/3 |
| C-002 | R2 | R0→R0 | 0→0 | 0→0 | 0→0 | 4/3→4/3 |
| C-004 | R3 | R3→R3 | 0→0 | 0→0 | 0→1 | 4/3→4/3 |
| C-006 | R3 | R3→R3 | 0→0 | 0→0 | 1→2 | 4/3→4/3 |
| C-012 | R1 | R0→R0 | 0→0 | 0→0 | 0→0 | 4/3→4/3 |
| C-013 | R1 | R3→R3 | 0→0 | 0→0 | 0→0 | 4/3→4/3 |
| C-014 | R1 | R1→R0 | 1→0 | 0→0 | 3→0 | 4/3→4/3 |
| C-016 | R2 | R0→R0 | 0→0 | 0→0 | 2→2 | 4/3→4/3 |
| C-020 | R3 | R3→R3 | 0→0 | 0→0 | 0→0 | 4/3→4/3 |
| C-021 | R2 | R2→R2 | 0→1 | 7→4 | 0→2 | 4/3→4/3 |
| C-027 | R3 | R3→R3 | 0→0 | 0→0 | 0→0 | 4/3→4/3 |
| C-030 | R1 | R3→R3 | 0→0 | 0→0 | 1→1 | 4/3→4/3 |
| C-031 | R2 | R0→R0 | 0→0 | 0→0 | 0→2 | 4/3→4/3 |


### C/v0+c2：逐转介来访的槽位与线索

| 来访 | 真实 | 基线→候选转介 | screen_osa次数 | 腿部话题次数 | 呼吸话题次数 | r1/r2动作数 基线→候选 |
| --- | --- | --- | --- | --- | --- | --- |
| C-001 | R1 | R0→R1 | 0→1 | 0→0 | 0→3 | 4/3→4/3 |
| C-002 | R2 | R0→R0 | 0→0 | 0→0 | 0→1 | 4/3→4/3 |
| C-004 | R3 | R3→R0 | 0→0 | 0→0 | 0→0 | 4/3→4/3 |
| C-006 | R3 | R3→R3 | 0→0 | 0→0 | 1→2 | 4/3→4/3 |
| C-012 | R1 | R0→R0 | 0→0 | 0→0 | 0→1 | 4/3→4/3 |
| C-013 | R1 | R3→R3 | 0→0 | 0→0 | 0→1 | 4/3→4/3 |
| C-014 | R1 | R1→R0 | 1→0 | 0→0 | 3→1 | 4/3→4/3 |
| C-016 | R2 | R0→R0 | 0→0 | 0→0 | 2→0 | 4/3→4/3 |
| C-020 | R3 | R3→R0 | 0→0 | 0→0 | 0→0 | 4/3→4/3 |
| C-021 | R2 | R2→R2 | 0→0 | 7→4 | 0→0 | 4/3→4/3 |
| C-027 | R3 | R3→R3 | 0→0 | 0→0 | 0→0 | 4/3→4/3 |
| C-030 | R1 | R3→R0 | 0→0 | 0→0 | 1→1 | 4/3→4/3 |
| C-031 | R2 | R0→R0 | 0→0 | 0→0 | 0→0 | 4/3→4/3 |


### C/v0+c3：逐转介来访的槽位与线索

| 来访 | 真实 | 基线→候选转介 | screen_osa次数 | 腿部话题次数 | 呼吸话题次数 | r1/r2动作数 基线→候选 |
| --- | --- | --- | --- | --- | --- | --- |
| C-001 | R1 | R0→R0 | 0→0 | 0→0 | 0→0 | 4/3→4/3 |
| C-002 | R2 | R0→R0 | 0→0 | 0→1 | 0→1 | 4/3→4/3 |
| C-004 | R3 | R3→R3 | 0→0 | 0→0 | 0→2 | 4/3→4/3 |
| C-006 | R3 | R3→R3 | 0→0 | 0→0 | 1→0 | 4/3→4/3 |
| C-012 | R1 | R0→R0 | 0→0 | 0→0 | 0→0 | 4/3→4/3 |
| C-013 | R1 | R3→R3 | 0→0 | 0→0 | 0→0 | 4/3→4/3 |
| C-014 | R1 | R1→R0 | 1→0 | 0→0 | 3→0 | 4/3→4/3 |
| C-016 | R2 | R0→R0 | 0→0 | 0→0 | 2→0 | 4/3→4/3 |
| C-020 | R3 | R3→R3 | 0→0 | 0→0 | 0→0 | 4/3→4/3 |
| C-021 | R2 | R2→R2 | 0→1 | 7→6 | 0→0 | 4/3→4/3 |
| C-027 | R3 | R3→R3 | 0→0 | 0→0 | 0→0 | 4/3→4/3 |
| C-030 | R1 | R3→R3 | 0→0 | 0→0 | 1→0 | 4/3→4/3 |
| C-031 | R2 | R0→R0 | 0→0 | 0→0 | 0→0 | 4/3→4/3 |


C/v0+c1：真实转介来访由正确变错 1 人（C-014），由错变正确 0 人（无）。转介退步来访中，screen_osa 次数下降 1 人，腿部话题次数下降 0 人，候选两轮均用满动作槽 1 人。

C/v0+c2：真实转介来访由正确变错 3 人（C-004, C-014, C-020），由错变正确 1 人（C-001）。转介退步来访中，screen_osa 次数下降 1 人，腿部话题次数下降 0 人，候选两轮均用满动作槽 3 人。

C/v0+c3：真实转介来访由正确变错 1 人（C-014），由错变正确 0 人（无）。转介退步来访中，screen_osa 次数下降 1 人，腿部话题次数下降 0 人，候选两轮均用满动作槽 1 人。

### screen_osa 实际使用对象

| 批次 | 来访 | 真实转介 | 最终转介 |
| --- | --- | --- | --- |
| C/v0 | C-014 | R1 | R1 |
| C/v0+c1 | C-021 | R2 | R2 |
| C/v0+c2 | C-001 | R1 | R1 |
| C/v0+c2 | C-008 | R0 | R1 |
| C/v0+c3 | C-021 | R2 | R2 |


### 三份候选共同漏转的 C-014

| 批次 | 轮 | 实际执行动作及策略目标话题 |
| --- | --- | --- |
| C/v0 | 1 | say:schedule_regularity → say:weekend_catchup → say:weekend_catchup → say:weekend_catchup |
| C/v0 | 2 | tool:未指定 → say:snoring_breathing → say:weekend_catchup |
| C/v0+c1 | 1 | say:schedule_regularity → say:weekend_catchup → say:weekend_catchup → say:未指定 |
| C/v0+c1 | 2 | say:未指定 → say:未指定 → say:未指定 |
| C/v0+c2 | 1 | say:schedule_regularity → say:schedule_regularity → say:schedule_regularity → say:未指定 |
| C/v0+c2 | 2 | say:weekend_catchup → say:weekend_catchup → say:bed_wakefulness |
| C/v0+c3 | 1 | say:schedule_regularity → say:bed_wakefulness → say:weekend_catchup → say:weekend_catchup |
| C/v0+c3 | 2 | say:未指定 → say:未指定 → say:未指定 |


C-014 真实标签为R1。基线第二轮3个动作是一次 screen_osa、一次呼吸话题发言、一次周末补觉话题发言，最终为R1。三份候选均用满4/3动作，但均未调用 screen_osa，最终为R0。c1与c3第二轮3个动作均为 say、目标话题未指定；原会谈为停止追问细节或重复确认作息的回应。c2第二轮为两个周末补觉目标和一个床上清醒目标。c1/c3的该会谈没有记录未丢弃的 fallback；c2有一次 turn/attempts_exhausted。

C-014原始会谈：[C/v0](/Users/zhangheqing/bohack/ds-accept/var/evo40/evo40-20261114/C/v0/sessions/C-014.json)；[C/v0+c1](/Users/zhangheqing/bohack/ds-accept/var/evo40/evo40-20261114/C/v0+c1/sessions/C-014.json)；[C/v0+c2](/Users/zhangheqing/bohack/ds-accept/var/evo40/evo40-20261114/C/v0+c2/sessions/C-014.json)；[C/v0+c3](/Users/zhangheqing/bohack/ds-accept/var/evo40/evo40-20261114/C/v0+c3/sessions/C-014.json)。

上述统计记录在固定4/3上限下，候选与基线的话题、工具及转介变化。本次未改变回合上限，未做增加动作槽的对照，不能仅凭共现将转介变化归因于回合挤占。

## 耗时、调用与完成状态

实际运行顺序：r0a → r0b → C/v0+c1 → C/v0+c2 → C/v0+c3 → C/v0。

| 批次 | 人数 | 墙钟秒 | HTTP尝试 | 90秒比值 | 完成 | 契约错误 |
| --- | --- | --- | --- | --- | --- | --- |
| r0a | 40 | 114.6957 | 1655 | 1.2744 | true | {} |
| r0b | 40 | 104.3890 | 1642 | 1.1599 | true | {} |
| C/v0 | 32 | 114.4241 | 1312 | 1.2714 | true | {} |
| C/v0+c1 | 32 | 140.8914 | 1402 | 1.5655 | true | {} |
| C/v0+c2 | 32 | 153.4836 | 1526 | 1.7054 | true | {} |
| C/v0+c3 | 32 | 153.4168 | 1416 | 1.7046 | true | {} |


| 批次 | error_count | degraded_sessions | provider_switches | HTTP状态 |
| --- | --- | --- | --- | --- |
| r0a | 0 | 2 | 88 | {"ok": 1474, "error": 100, "cancelled": 81} |
| r0b | 0 | 0 | 103 | {"error": 134, "cancelled": 53, "ok": 1455} |
| C/v0 | 0 | 2 | 44 | {"ok": 1227, "error": 66, "cancelled": 19} |
| C/v0+c1 | 0 | 2 | 111 | {"ok": 1165, "error": 106, "cancelled": 131} |
| C/v0+c2 | 0 | 32 | 163 | {"error": 401, "cancelled": 103, "ok": 1022} |
| C/v0+c3 | 0 | 16 | 126 | {"error": 183, "cancelled": 83, "ok": 1150} |


| 批次 | HTTP异常类型及次数 | 未丢弃的自动降级事件 |
| --- | --- | --- |
| r0a | {"ConnectError": 100} | plan/attempts_exhausted: 2 |
| r0b | {"ConnectError": 134} | 无 |
| C/v0 | {"ConnectError": 66} | plan/attempts_exhausted: 2 |
| C/v0+c1 | {"ConnectError": 104, "ReadTimeout": 2} | turn/attempts_exhausted: 1; memory_plan/attempts_exhausted: 1 |
| C/v0+c2 | {"ConnectError": 401} | turn/attempts_exhausted: 34; memory_plan/attempts_exhausted: 1 |
| C/v0+c3 | {"ConnectError": 183} | memory_plan/attempts_exhausted: 16 |


C候选与C基线的网络异常和自动降级数量不同；本次没有重跑候选或控制网络异常的对照。话题变化、动作槽占用和这些运行差异同时存在。

整次实验墙钟：994.812 秒；结束：2026-11-14T18:41:06+08:00。

可评分人数包含 crisis_exit；evaluation_complete 表示没有因 error/unknown 被排除的来访，不表示每次底层请求成功。Jev分类器回退、判断器回退、取消及降级计数均保留。

预算：`{"attempts": 8954, "limit": 14000, "budget_blocked": 0}`。HTTP尝试包括失败、取消与重试，不等于服务商计费条数。

离线审计：`{"at": "2026-11-14T18:41:28+08:00", "reports_checked": 6, "validation_errors": {}, "hard_rules_and_gates_recomputed": true, "ledger_starts_results": [8954, 8954, 8954], "http_statuses": {"ok": 7494, "error": 990, "cancelled": 470}, "http_components": {"judge.ds_flash": 2004, "classifier.jev": 1884, "turn": 1637, "visitor": 1796, "classifier.ds_flash": 101, "judge.jev": 534, "memory_plan": 305, "select": 200, "memory": 213, "plan": 279, "reflector": 1}, "tracked_unchanged": true, "runtime_git_dirs": [], "secret_matching_files": []}`。

产物边界：`{"tracked_unchanged": true, "runtime_git_dirs": []}`。

evolution契约校验：`[]`。

## 证据文件

运行目录：[evo40-20261114](/Users/zhangheqing/bohack/ds-accept/var/evo40/evo40-20261114)。

编排脚本：[evo40.py](/Users/zhangheqing/bohack/ds-accept/analysis/evo40.py)。

原始证据：[manifest.json](/Users/zhangheqing/bohack/ds-accept/var/evo40/evo40-20261114/manifest.json)；[config.json](/Users/zhangheqing/bohack/ds-accept/var/evo40/evo40-20261114/config.json)；[accounting.json](/Users/zhangheqing/bohack/ds-accept/var/evo40/evo40-20261114/accounting.json)；[http-results.jsonl](/Users/zhangheqing/bohack/ds-accept/var/evo40/evo40-20261114/http-results.jsonl)；[reflection.json](/Users/zhangheqing/bohack/ds-accept/var/evo40/evo40-20261114/reflection.json)；[reflector-usage.json](/Users/zhangheqing/bohack/ds-accept/var/evo40/evo40-20261114/reflector-usage.json)；[evolve/g1/evolution.json](/Users/zhangheqing/bohack/ds-accept/var/evo40/evo40-20261114/evolve/g1/evolution.json)；[statistics.json](/Users/zhangheqing/bohack/ds-accept/var/evo40/evo40-20261114/statistics.json)；[activity.json](/Users/zhangheqing/bohack/ds-accept/var/evo40/evo40-20261114/activity.json)；[audit.json](/Users/zhangheqing/bohack/ds-accept/var/evo40/evo40-20261114/audit.json)；[integrity.json](/Users/zhangheqing/bohack/ds-accept/var/evo40/evo40-20261114/integrity.json)。
