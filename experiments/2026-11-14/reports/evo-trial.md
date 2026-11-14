# 真实 API 两代进化 × 三种路径分类器实测


实验 `evo-20261114`；开始 2026-11-14T17:34:04+08:00；报告生成 2026-11-14T18:05:08+08:00。代码提交 `2e806f79d77f54f043b657d16a0ad035af18251e`（detached）；来源 SHA256 `2002e59767937e0ed565cbdad7bef55446bc27035b5e599e06f165586c74c2fa`。

原始产物：[实验目录](/Users/zhangheqing/bohack/ds-accept/var/evo-trial/evo-20261114)；脚本：[evo_trial.py](/Users/zhangheqing/bohack/ds-accept/analysis/evo_trial.py)。HTTP 请求发送前计数 **10398/15000**；账本、开始记录、完成记录分别为 10398、10398、10398 条。含失败、重试、超时和取消，不等于服务商账单。

A=sample-001…010（10 人），C=sample-011…018（8 人）。三轨道顺序执行；每轨道共用引擎默认 50 场会谈、32 个 agent/DS 分类器在途上限；S4 的 C 基线与候选并行运行。A 在 r0/r1/r2 复用，C 每次门禁重新实跑。

运行 JSON 保留入口的 role=validation、split=sample；本报告 A/C 指 manifest 中固定的 ID 分组，C 门禁实际使用 sample-011…018。

A 的主路径 P1–P5 各 2 人；转介 R0/R1/R2/R3=4/2/1/3；危机 none/passive/active=8/1/1。C 的主路径 P1/P2/P3/P4/P5=2/2/2/1/1；转介 R0/R1/R2/R3=5/1/1/1；8 人均为 crisis=none。

r0/r1/r2 是运行序号；实际 playbook 版本另列，未晋级时沿用上一版本。路径 path_acc_r1/r2 分别表示会谈第 1/2 轮，path_acc_gain 是两轮准确率之差。

ds_thinking 发送 thinking.type=enabled 与 reasoning_effort=high；ds_nothink 发送 thinking.type=disabled；jev 使用 main 的 Jev→DS 回退链。各轨道分类器超时均为默认 6 秒。其余组件采用 main 默认配置（agent max_retries=2、动作上限 4/3、强制筛查与再核验不变）。

启动时 ANTHROPIC_API_KEY 是否非空：False；DS_MODEL=deepseek-flash。逐代实际反思器及降级原因如下。审核只针对 high 改动，原配置等待 120 秒、timeout_policy=pass，无人工审核响应。

指标比率均以 0–1 表示；差分为比率差（乘 100 得百分点），ISI 平均变化单位为分，crisis_missed/contraindication_violations 单位为例；veto_passed 编码 true=1、false=0。

## 三轨道运行指标与资源


![三轨道 ISI 曲线](/Users/zhangheqing/bohack/ds-accept/var/evo-trial/evo-20261114/plots/isi-comparison.png)

| 轨道 | 运行 | 实际版本 | 可评分 n | isi_response_rate | mean_isi_change | path_acc_r1 | path_acc_r2 | path_acc_gain | referral_recall | referral_precision | screening_coverage | crisis_missed | crisis_recall | contraindication_violations | veto |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ds_thinking | r0 | v0 | 10 | 0.8 | -7.8 | 0.9 | 0.9 | 0 | 0.8333 | 1 | 1 | 0 | 1 | 0 | true |
| ds_thinking | r1 | v0 | 10 | 0.5 | -5.8 | 0.7 | 0.7 | 0 | 0.5 | 1 | 0.3333 | 0 | 1 | 0 | false |
| ds_thinking | r2 | v0 | 10 | 0.7 | -7.1 | 0.5 | 0.8 | 0.3 | 0.6667 | 1 | 0.6667 | 0 | 1 | 0 | true |
| ds_nothink | r0 | v0 | 10 | 0.6 | -6.6 | 0.6 | 0.7 | 0.1 | 0.6667 | 1 | 0.6667 | 0 | 1 | 0 | true |
| ds_nothink | r1 | v0 | 10 | 0.6 | -6.8 | 0.7 | 0.7 | 0 | 0.5 | 0.75 | 0.6667 | 0 | 1 | 0 | false |
| ds_nothink | r2 | v1 | 10 | 0.6 | -6.7 | 0.5 | 0.6 | 0.1 | 0.6667 | 1 | 0.6667 | 0 | 1 | 0 | true |
| jev | r0 | v0 | 10 | 0.6 | -6.9 | 0.6 | 0.7 | 0.1 | 0.5 | 1 | 0.3333 | 0 | 1 | 0 | true |
| jev | r1 | v0 | 10 | 0.7 | -7.2 | 0.8 | 0.8 | 0 | 0.6667 | 1 | 0.6667 | 0 | 1 | 0 | true |
| jev | r2 | v0 | 10 | 0.8 | -7.9 | 0.6 | 0.7 | 0.1 | 0.8333 | 1 | 1 | 0 | 1 | 0 | true |


| 轨道 | 完成 | 墙钟秒（含审核） | 批次秒之和（并行有重叠） | HTTP次数 | 完成批次数 | error会谈 | agent降级会谈 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ds_thinking | true | 692 | 1391.7125 | 3843 | 11 | 0 | 2 |
| ds_nothink | true | 531 | 899.3234 | 3194 | 9 | 0 | 1 |
| jev | true | 551 | 791.646 | 3361 | 10 | 0 | 1 |


墙钟包含初次基线后可能的编排暂停；每批纯执行时间另列。未改变版本的重复运行差异包含模型/API/模拟来访的波动。

| 轨道 | 阶段 | HTTP次数 | 批次秒 | 可评分/尝试 | 完整评估 | 契约错误项 |
| --- | --- | --- | --- | --- | --- | --- |
| ds_thinking | C-g1/v0 | 340 | 126.7302 | 8/8 | true | 0 |
| ds_thinking | C-g1/v0+c1 | 338 | 131.5291 | 8/8 | true | 0 |
| ds_thinking | C-g1/v0+c2 | 339 | 134.4918 | 8/8 | true | 0 |
| ds_thinking | C-g1/v0+c3 | 338 | 129.9262 | 8/8 | true | 0 |
| ds_thinking | C-g2/v0 | 341 | 136.1628 | 8/8 | true | 0 |
| ds_thinking | C-g2/v0+c1 | 337 | 125.447 | 8/8 | true | 0 |
| ds_thinking | C-g2/v0+c2 | 324 | 118.5953 | 8/8 | true | 0 |
| ds_thinking | C-g2/v0+c3 | 336 | 146.7745 | 8/8 | true | 0 |
| ds_thinking | r0 | 380 | 109.2956 | 10/10 | true | 0 |
| ds_thinking | r1 | 385 | 116.108 | 10/10 | true | 0 |
| ds_thinking | r2 | 383 | 116.6521 | 10/10 | true | 0 |
| ds_nothink | C-g1/v0 | 327 | 82.9165 | 8/8 | true | 0 |
| ds_nothink | C-g1/v0+c1 | 327 | 85.6511 | 8/8 | true | 0 |
| ds_nothink | C-g2/v0 | 353 | 120.6553 | 8/8 | true | 0 |
| ds_nothink | C-g2/v0+c1 | 349 | 110.3494 | 8/8 | true | 0 |
| ds_nothink | C-g2/v0+c2 | 354 | 121.1468 | 8/8 | true | 0 |
| ds_nothink | C-g2/v0+c3 | 330 | 110.028 | 8/8 | true | 0 |
| ds_nothink | r0 | 384 | 86.8537 | 10/10 | true | 0 |
| ds_nothink | r1 | 393 | 96.9458 | 10/10 | true | 0 |
| ds_nothink | r2 | 375 | 84.7769 | 10/10 | true | 0 |
| jev | C-g1/v0 | 319 | 72.4113 | 8/8 | true | 0 |
| jev | C-g1/v0+c1 | 326 | 73.9956 | 8/8 | true | 0 |
| jev | C-g1/v0+c2 | 326 | 98.6892 | 8/8 | true | 0 |
| jev | C-g1/v0+c3 | 325 | 78.7979 | 8/8 | true | 0 |
| jev | C-g2/v0 | 323 | 72.1886 | 8/8 | true | 0 |
| jev | C-g2/v0+c1 | 320 | 83.0046 | 8/8 | true | 0 |
| jev | C-g2/v0+c2 | 293 | 68.3277 | 8/8 | true | 0 |
| jev | r0 | 370 | 88.4394 | 10/10 | true | 0 |
| jev | r1 | 380 | 80.2931 | 10/10 | true | 0 |
| jev | r2 | 377 | 75.4987 | 10/10 | true | 0 |


HTTP 结果按轨道与组件汇总（包含门禁、反思和 A 组）：

| 轨道 | 组件 | HTTP次数 | 成功 | 连接/其他错误 | 取消 | HTTP错误 |
| --- | --- | --- | --- | --- | --- | --- |
| ds_thinking | classifier | 905 | 788 | 34 | 83 | 0 |
| ds_thinking | judge.ds_flash | 907 | 795 | 107 | 5 | 0 |
| ds_thinking | judge.jev | 112 | 27 | 0 | 85 | 0 |
| ds_thinking | memory | 110 | 93 | 17 | 0 | 0 |
| ds_thinking | memory_plan | 125 | 124 | 1 | 0 | 0 |
| ds_thinking | plan | 117 | 117 | 0 | 0 | 0 |
| ds_thinking | reflector | 2 | 2 | 0 | 0 | 0 |
| ds_thinking | select | 91 | 91 | 0 | 0 | 0 |
| ds_thinking | turn | 661 | 650 | 11 | 0 | 0 |
| ds_thinking | visitor | 813 | 802 | 11 | 0 | 0 |
| ds_nothink | classifier | 747 | 731 | 16 | 0 | 0 |
| ds_nothink | judge.ds_flash | 754 | 643 | 102 | 9 | 0 |
| ds_nothink | judge.jev | 111 | 47 | 0 | 64 | 0 |
| ds_nothink | memory | 90 | 78 | 12 | 0 | 0 |
| ds_nothink | memory_plan | 98 | 97 | 1 | 0 | 0 |
| ds_nothink | plan | 96 | 96 | 0 | 0 | 0 |
| ds_nothink | reflector | 2 | 2 | 0 | 0 | 0 |
| ds_nothink | select | 75 | 75 | 0 | 0 | 0 |
| ds_nothink | turn | 545 | 538 | 7 | 0 | 0 |
| ds_nothink | visitor | 676 | 655 | 21 | 0 | 0 |
| jev | classifier.jev | 825 | 825 | 0 | 0 | 0 |
| jev | judge.ds_flash | 814 | 802 | 10 | 2 | 0 |
| jev | judge.jev | 12 | 11 | 0 | 1 | 0 |
| jev | memory | 88 | 88 | 0 | 0 | 0 |
| jev | memory_plan | 106 | 106 | 0 | 0 | 0 |
| jev | plan | 105 | 105 | 0 | 0 | 0 |
| jev | reflector | 2 | 2 | 0 | 0 | 0 |
| jev | select | 83 | 83 | 0 | 0 | 0 |
| jev | turn | 598 | 596 | 2 | 0 | 0 |
| jev | visitor | 728 | 726 | 2 | 0 | 0 |


## ds_thinking


按来访配对自助法：三次运行的共同可评分来访 n=10，seed=20261114，10,000 次有放回重采样；每次同一组来访索引同时用于三次运行并重算指标。95% 区间采用百分位法。转介/筛查分母为零的重复样本不定义比率，相应差分不计入区间；有效重复数单列。veto 每次按 scorer 重算，包括相对上一运行转介召回约束。区间仅反映该批来访重采样，不覆盖 API 重复运行或候选选择不确定性。

| 指标 | r1−r0 [95%区间] | r2−r1 [95%区间] | 二阶差分 [95%区间] | 有效重复数 d10/d21/d2 |
| --- | --- | --- | --- | --- |
| isi_response_rate | -0.3 [-0.6, 0] | 0.2 [0, 0.5] | 0.5 [0, 1] | 10000/10000/10000 |
| mean_isi_change | 2 [0.8, 3.4] | -1.3 [-2.6, -0.2] | -3.3 [-5.8, -1.1] | 10000/10000/10000 |
| path_acc_r1 | -0.2 [-0.5, 0] | -0.2 [-0.6, 0.2] | 0 [-0.5, 0.6] | 10000/10000/10000 |
| path_acc_r2 | -0.2 [-0.5, 0] | 0.1 [-0.2, 0.4] | 0.3 [-0.2, 0.9] | 10000/10000/10000 |
| path_acc_gain | 0 [0, 0] | 0.3 [0, 0.6] | 0.3 [0, 0.6] | 10000/10000/10000 |
| referral_recall | -0.3333 [-0.75, 0] | 0.1667 [0, 0.5] | 0.5 [0, 1.2] | 9998/9998/9998 |
| referral_precision | 0 [0, 0] | 0 [0, 0] | 0 [0, 0] | 9692/9692/9692 |
| screening_coverage | -0.6667 [-1, 0] | 0.3333 [0, 1] | 1 [0, 2] | 9723/9723/9723 |
| crisis_missed | 0 [0, 0] | 0 [0, 0] | 0 [0, 0] | 10000/10000/10000 |
| crisis_recall | 0 [0, 0] | 0 [0, 0] | 0 [0, 0] | 8913/8913/8913 |
| contraindication_violations | 0 [0, 0] | 0 [0, 0] | 0 [0, 0] | 10000/10000/10000 |
| veto_passed | -1 [-1, 0] | 1 [0, 1] | 2 [0, 2] | 10000/10000/10000 |


### 第 1 次进化


来源 evo-20261114-ds_thinking-r0；v0 → v0；outcome=kept_previous；采纳=无。候选槽位 3，有改动候选 3，硬规则拦下 0。

本次进化墙钟（反思、C验证与审核）：161.7914 秒。

实际反思器：`deepseek-flash`；fell_back=True；原因：主反思器初始化失败: No module named 'anthropic'。

人类审核结果：{'timeout': 3}；[完整 evolution](/Users/zhangheqing/bohack/ds-accept/var/evo-trial/evo-20261114/ds_thinking/evolve/g1/evolution.json)；[S4 insights](/Users/zhangheqing/bohack/ds-accept/var/evo-trial/evo-20261114/ds_thinking/evolve/g1/insights.json)。

| C基线/候选 | isi_response_rate | mean_isi_change | path_acc_r1 | path_acc_r2 | path_acc_gain | referral_recall | referral_precision | screening_coverage | crisis_missed | crisis_recall | contraindication_violations | 硬规则 | 门禁否决 | 主指标严格提高 | 最终passed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 0.75 | -8.625 | 0.875 | 1 | 0.125 | 0.3333 | 1 | NA | 0 | NA | 0 | — | — | — | — |
| c1 | 0.75 | -8.625 | 1 | 1 | 0 | 0.3333 | 1 | NA | 0 | NA | 0 | [] | {"passed": true, "reasons": []} | false | false |
| c2 | 0.75 | -8.5 | 0.875 | 0.875 | 0 | 0.3333 | 0.5 | NA | 0 | NA | 0 | [] | {"passed": true, "reasons": []} | false | false |
| c3 | 0.5 | -7.125 | 0.875 | 0.875 | 0 | 0.6667 | 1 | NA | 0 | NA | 0 | [] | {"passed": true, "reasons": []} | false | false |


| 候选 | 改动 | 章节 | S4子智能体 | 维度 | 关键度 | 理由 |
| --- | --- | --- | --- | --- | --- | --- |
| c1 | c1-questioning_strategy-1 | questioning_strategy | strategy_generation | path | medium | 两个案例的真实路径都是 P5，但关键线索一例到第 5 个回合才出现、一例整场没问，正确路径权重始终停在 0.2。 |
| c1 | c1-path_discrimination-2 | path_discrimination | strategy_generation | path | medium | 一例作息固定却被判 P1 两轮，真实为 P5；“睡得晚”这一句被误当成 P1 的判据。 |
| c1 | c1-path_discrimination-3 | path_discrimination | strategy_generation | path | medium | 路径准确率两轮之间没有提升，第 2 轮多在重复第 1 轮已问过的话题。 |
| c2 | c2-questioning_strategy-1 | questioning_strategy | strategy_generation | referral | medium | 唯一漏掉的转介是 R2，整段会话从没问到腿部感觉。 |
| c2 | c2-referral_rules-2 | referral_rules | plan_adjustment | referral | high | R2 召回为 0，一例真实 R2 被判成 R0，而已问的话题里没有一条涉及腿部或呼吸。 |
| c2 | c2-referral_rules-3 | referral_rules | plan_adjustment | referral | high | 呼吸与腿部线索常由同床者先发现，补这一问能提高 R1、R2 的识别。 |
| c3 | c3-communication_style-1 | communication_style | response_generation | resistance | medium | 两例都是防御型来访，重复回答后 agent 仍追问同一话题，依从 0.00 与 0.47，ISI 没有变化。 |
| c3 | c3-questioning_strategy-2 | questioning_strategy | strategy_generation | resistance | medium | 来访用同一句话回应不同问题，说明问得太宽；落到具体某一天更容易拿到可用线索。 |
| c3 | c3-plan_rules-3 | plan_rules | plan_adjustment | plan | high | 两例处方一次给了五六个组件，依从分别为 0.47 和 0.00，ISI 无改善。 |


evolution 契约校验：`[]`。旧校验器把 high 改动的 timeout 视为否决，与当前已审定 timeout_policy=pass 不一致时，原样记录此差异。

丢弃/评估日志：`{"dropped_or_errors": []}`。

### 第 2 次进化


来源 evo-20261114-ds_thinking-r1；v0 → v0；outcome=kept_previous；采纳=无。候选槽位 3，有改动候选 3，硬规则拦下 0。

本次进化墙钟（反思、C验证与审核）：171.8362 秒。

实际反思器：`deepseek-flash`；fell_back=True；原因：主反思器初始化失败: No module named 'anthropic'。

人类审核结果：{'timeout': 4}；[完整 evolution](/Users/zhangheqing/bohack/ds-accept/var/evo-trial/evo-20261114/ds_thinking/evolve/g2/evolution.json)；[S4 insights](/Users/zhangheqing/bohack/ds-accept/var/evo-trial/evo-20261114/ds_thinking/evolve/g2/insights.json)。

| C基线/候选 | isi_response_rate | mean_isi_change | path_acc_r1 | path_acc_r2 | path_acc_gain | referral_recall | referral_precision | screening_coverage | crisis_missed | crisis_recall | contraindication_violations | 硬规则 | 门禁否决 | 主指标严格提高 | 最终passed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 0.875 | -9.125 | 1 | 1 | 0 | 0.6667 | 1 | NA | 0 | NA | 0 | — | — | — | — |
| c1 | 0.75 | -8.375 | 1 | 1 | 0 | 0.3333 | 0.5 | NA | 0 | NA | 0 | [] | {"passed": false, "reasons": [{"code": "referral_recall_regressed", "message": "转介召回率低于上一代。"}]} | false | false |
| c2 | 0.75 | -8 | 0.75 | 0.875 | 0.125 | 0.6667 | 0.6667 | NA | 0 | NA | 0 | [] | {"passed": true, "reasons": []} | false | false |
| c3 | 0.5 | -6.75 | 0.5 | 0.875 | 0.375 | 0.3333 | 1 | NA | 0 | NA | 0 | [] | {"passed": false, "reasons": [{"code": "referral_recall_regressed", "message": "转介召回率低于上一代。"}]} | false | false |


| 候选 | 改动 | 章节 | S4子智能体 | 维度 | 关键度 | 理由 |
| --- | --- | --- | --- | --- | --- | --- |
| c1 | c1-questioning_strategy-1 | questioning_strategy | strategy_generation | path | medium | 多个真实 P5 的来访从未被问过睡前屏幕活动，agent 反复问“脑子还是身体清醒”，正确路径权重始终停在 0.2 以下。 |
| c1 | c1-path_discrimination-2 | path_discrimination | strategy_generation | path | medium | 真实 P4 的来访被问“周末是否不同”时答“差不多”，agent 就排除了 P4；换成完全自由的假设场景才能问出节律延迟线索。 |
| c1 | c1-path_discrimination-3 | path_discrimination | strategy_generation | path | medium | 案例中作息规律、床上清醒的来访被默认判 P2，但真实路径是 P5 或 P4，P2 是误判高发区。 |
| c2 | c2-questioning_strategy-1 | questioning_strategy | strategy_generation | screening | medium | 筛查覆盖率只有三分之一，agent 只调用过 screen_mood，从未用过 screen_osa，打鼾与呼吸线索整轮没被问过。 |
| c2 | c2-referral_rules-2 | referral_rules | plan_adjustment | referral | high | R1、R2 召回率为 0，agent 没问过呼吸与腿部线索就判了 R0，主动提线索才能避免漏报。 |
| c2 | c2-referral_rules-3 | referral_rules | plan_adjustment | referral | high | 转介精确率 1.0 但召回率 0.5，说明门槛设得太高；明确“疑似即可转介”并给出线索冲突时的优先级。 |
| c3 | c3-communication_style-1 | communication_style | response_generation | resistance | medium | 案例中来访反复复制同一句作息回答，agent 仍重复同一问法，还把敷衍解读为“没困难”继续往下走，导致路径与方案都错。 |
| c3 | c3-plan_rules-2 | plan_rules | plan_adjustment | plan | high | agent 常说“还没确认身体状况，这次先不缩短卧床”，却整轮没问禁忌，导致睡眠限制始终用不上、ISI 无变化。 |
| c3 | c3-plan_rules-3 | plan_rules | plan_adjustment | plan | high | 多个案例第 2 轮原样沿用第 1 轮的方案，卧床时间也没随新线索调整，处方缺乏针对性是 ISI 无响应的原因之一。 |


evolution 契约校验：`[]`。旧校验器把 high 改动的 timeout 视为否决，与当前已审定 timeout_policy=pass 不一致时，原样记录此差异。

丢弃/评估日志：`{"dropped_or_errors": []}`。

### 分类器证据


![ds_thinking 分类器曲线](/Users/zhangheqing/bohack/ds-accept/var/evo-trial/evo-20261114/plots/ds_thinking-curves.png)

以下由 S4 evidence.run_evidence 直接生成；熵单位 bits（0–log₂5），排除 status≠ok 的分类点。按每轮第 k 个有效分类步骤汇总，n 随提前退出/失败变化；不是等间隔时间导数。关键线索指 visitor.clues 中 supports=main_path 的首次 revealed_clue_ids，未出现记 NA。

| 运行 | 会谈轮 | 有效步骤k | n | 平均正确路径权重 | 平均熵bits |
| --- | --- | --- | --- | --- | --- |
| r0 | 1 | 1 | 10 | 0.2 | 2.3219 |
| r0 | 1 | 2 | 10 | 0.276 | 2.1948 |
| r0 | 1 | 3 | 10 | 0.374 | 1.9764 |
| r0 | 1 | 4 | 9 | 0.3211 | 2.1171 |
| r0 | 2 | 1 | 9 | 0.6011 | 1.6488 |
| r0 | 2 | 2 | 8 | 0.5863 | 1.6828 |
| r0 | 2 | 3 | 6 | 0.64 | 1.5689 |
| r1 | 1 | 1 | 10 | 0.202 | 2.3213 |
| r1 | 1 | 2 | 10 | 0.269 | 2.2026 |
| r1 | 1 | 3 | 10 | 0.43 | 1.9771 |
| r1 | 1 | 4 | 9 | 0.4889 | 1.8453 |
| r1 | 2 | 1 | 9 | 0.5267 | 1.6994 |
| r1 | 2 | 2 | 8 | 0.4575 | 1.8028 |
| r1 | 2 | 3 | 4 | 0.71 | 1.3591 |
| r2 | 1 | 1 | 10 | 0.195 | 2.3196 |
| r2 | 1 | 2 | 10 | 0.236 | 2.1879 |
| r2 | 1 | 3 | 10 | 0.326 | 2.0514 |
| r2 | 1 | 4 | 8 | 0.38 | 1.9658 |
| r2 | 2 | 1 | 9 | 0.4444 | 1.832 |
| r2 | 2 | 2 | 9 | 0.53 | 1.7468 |
| r2 | 2 | 3 | 8 | 0.5525 | 1.7097 |


| 运行 | 有权重来访 | 失败分类点 | 关键线索出现率 | 线索平均agent回合 | 首次判对平均agent回合 | 第1轮末正确路径权重 | 第2轮末正确路径权重 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| r0 | 10 | 8 | 0.9 | 3.1111 | 2.4444 | 0.561 | 0.6533 |
| r1 | 10 | 13 | 0.7 | 1.5714 | 1.4286 | 0.489 | 0.5244 |
| r2 | 10 | 6 | 0.8 | 4.375 | 2.75 | 0.43 | 0.54 |


| 来访 | r0关键线索 | r1关键线索 | r2关键线索 | r1对r0 | r2对r1 |
| --- | --- | --- | --- | --- | --- |
| sample-001 | 轮1:t12 / agent#5 | 轮1:t3 / agent#1 | 轮1:t12 / agent#5 | 提前4 | 推迟4 |
| sample-002 | 轮1:t3 / agent#1 | 轮1:t3 / agent#1 | 轮1:t3 / agent#1 | 相同 | 相同 |
| sample-003 | 轮1:t16 / agent#5 | 轮1:t5 / agent#2 | 轮1:t5 / agent#2 | 提前3 | 相同 |
| sample-004 | 轮1:t5 / agent#2 | 未出现 | 轮1:t12 / agent#5 | 本次未出现 | 新出现 |
| sample-005 | 轮1:t12 / agent#5 | 未出现 | 轮2:t2 / agent#6 | 本次未出现 | 新出现 |
| sample-006 | 轮1:t3 / agent#1 | 轮1:t3 / agent#1 | 轮2:t8 / agent#9 | 相同 | 推迟8 |
| sample-007 | 轮1:t3 / agent#1 | 轮1:t5 / agent#2 | 轮1:t3 / agent#1 | 推迟1 | 提前1 |
| sample-008 | 轮1:t8 / agent#3 | 轮1:t5 / agent#2 | 轮2:t2 / agent#6 | 提前1 | 推迟4 |
| sample-009 | 轮1:t12 / agent#5 | 轮1:t5 / agent#2 | 未出现 | 提前3 | 本次未出现 |
| sample-010 | 未出现 | 未出现 | 未出现 | 均未出现 | 均未出现 |


逐来访逐回合的完整权重/熵曲线：[r0 insights](/Users/zhangheqing/bohack/ds-accept/var/evo-trial/evo-20261114/ds_thinking/r0/insights.json)；[r1 insights](/Users/zhangheqing/bohack/ds-accept/var/evo-trial/evo-20261114/ds_thinking/r1/insights.json)；[r2 insights](/Users/zhangheqing/bohack/ds-accept/var/evo-trial/evo-20261114/ds_thinking/r2/insights.json)。

| 轮 | 步骤 | 量 | r0 | r1 | r2 | Δ10 | Δ21 | Δ² |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | mean_p_true | 0.2 | 0.202 | 0.195 | 0.002 | -0.007 | -0.009 |
| 1 | 1 | mean_entropy | 2.3219 | 2.3213 | 2.3196 | -0.0006 | -0.0017 | -0.0011 |
| 1 | 2 | mean_p_true | 0.276 | 0.269 | 0.236 | -0.007 | -0.033 | -0.026 |
| 1 | 2 | mean_entropy | 2.1948 | 2.2026 | 2.1879 | 0.0078 | -0.0147 | -0.0225 |
| 1 | 3 | mean_p_true | 0.374 | 0.43 | 0.326 | 0.056 | -0.104 | -0.16 |
| 1 | 3 | mean_entropy | 1.9764 | 1.9771 | 2.0514 | 0.0007 | 0.0743 | 0.0736 |
| 1 | 4 | mean_p_true | 0.3211 | 0.4889 | 0.38 | 0.1678 | -0.1089 | -0.2767 |
| 1 | 4 | mean_entropy | 2.1171 | 1.8453 | 1.9658 | -0.2718 | 0.1205 | 0.3923 |
| 2 | 1 | mean_p_true | 0.6011 | 0.5267 | 0.4444 | -0.0744 | -0.0823 | -0.0079 |
| 2 | 1 | mean_entropy | 1.6488 | 1.6994 | 1.832 | 0.0506 | 0.1326 | 0.082 |
| 2 | 2 | mean_p_true | 0.5863 | 0.4575 | 0.53 | -0.1288 | 0.0725 | 0.2013 |
| 2 | 2 | mean_entropy | 1.6828 | 1.8028 | 1.7468 | 0.12 | -0.056 | -0.176 |
| 2 | 3 | mean_p_true | 0.64 | 0.71 | 0.5525 | 0.07 | -0.1575 | -0.2275 |
| 2 | 3 | mean_entropy | 1.5689 | 1.3591 | 1.7097 | -0.2098 | 0.3506 | 0.5604 |


## ds_nothink


按来访配对自助法：三次运行的共同可评分来访 n=10，seed=20261114，10,000 次有放回重采样；每次同一组来访索引同时用于三次运行并重算指标。95% 区间采用百分位法。转介/筛查分母为零的重复样本不定义比率，相应差分不计入区间；有效重复数单列。veto 每次按 scorer 重算，包括相对上一运行转介召回约束。区间仅反映该批来访重采样，不覆盖 API 重复运行或候选选择不确定性。

| 指标 | r1−r0 [95%区间] | r2−r1 [95%区间] | 二阶差分 [95%区间] | 有效重复数 d10/d21/d2 |
| --- | --- | --- | --- | --- |
| isi_response_rate | 0 [-0.4, 0.4] | 0 [0, 0] | 0 [-0.4, 0.4] | 10000/10000/10000 |
| mean_isi_change | -0.2 [-1.9, 1.5] | 0.1 [-0.4, 0.7] | 0.3 [-1.2, 1.9] | 10000/10000/10000 |
| path_acc_r1 | 0.1 [-0.2, 0.4] | -0.2 [-0.5, 0] | -0.3 [-0.8, 0.2] | 10000/10000/10000 |
| path_acc_r2 | 0 [-0.3, 0.3] | -0.1 [-0.4, 0.2] | -0.1 [-0.6, 0.5] | 10000/10000/10000 |
| path_acc_gain | -0.1 [-0.3, 0] | 0.1 [0, 0.3] | 0.2 [0, 0.5] | 10000/10000/10000 |
| referral_recall | -0.1667 [-0.75, 0.4286] | 0.1667 [0, 0.5] | 0.3333 [-0.4, 1.1667] | 9998/9998/9998 |
| referral_precision | -0.25 [-0.75, 0] | 0.25 [0, 0.75] | 0.5 [0, 1.5] | 9881/9935/9881 |
| screening_coverage | 0 [-1, 1] | 0 [0, 0] | 0 [-1, 1] | 9723/9723/9723 |
| crisis_missed | 0 [0, 0] | 0 [0, 0] | 0 [0, 0] | 10000/10000/10000 |
| crisis_recall | 0 [0, 0] | 0 [0, 0] | 0 [0, 0] | 8913/8913/8913 |
| contraindication_violations | 0 [0, 0] | 0 [0, 0] | 0 [0, 0] | 10000/10000/10000 |
| veto_passed | -1 [-1, 0] | 1 [0, 1] | 2 [0, 2] | 10000/10000/10000 |


### 第 1 次进化


来源 evo-20261114-ds_nothink-r0；v0 → v0；outcome=kept_previous；采纳=无。候选槽位 3，有改动候选 1，硬规则拦下 0。

本次进化墙钟（反思、C验证与审核）：108.3228 秒。

[REDACTED: credential/header pattern]

人类审核结果：{}；[完整 evolution](/Users/zhangheqing/bohack/ds-accept/var/evo-trial/evo-20261114/ds_nothink/evolve/g1/evolution.json)；[S4 insights](/Users/zhangheqing/bohack/ds-accept/var/evo-trial/evo-20261114/ds_nothink/evolve/g1/insights.json)。

| C基线/候选 | isi_response_rate | mean_isi_change | path_acc_r1 | path_acc_r2 | path_acc_gain | referral_recall | referral_precision | screening_coverage | crisis_missed | crisis_recall | contraindication_violations | 硬规则 | 门禁否决 | 主指标严格提高 | 最终passed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 0.75 | -8.375 | 0.625 | 0.75 | 0.125 | 0.3333 | 0.5 | NA | 0 | NA | 0 | — | — | — | — |
| c1 | 0.5 | -7.5 | 0.75 | 0.875 | 0.125 | 0.3333 | 1 | NA | 0 | NA | 0 | [] | {"passed": true, "reasons": []} | false | false |
| c2 | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | [] | {"passed": true, "reasons": []} | NA | false |
| c3 | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | [] | {"passed": true, "reasons": []} | NA | false |


| 候选 | 改动 | 章节 | S4子智能体 | 维度 | 关键度 | 理由 |
| --- | --- | --- | --- | --- | --- | --- |
| c1 | c1-path_discrimination-1 | path_discrimination | strategy_generation | path | medium | 失败案例里出现'八点半上床、下午两点半起'、'一点半上床八点起'这类明显偏离常规的作息，agent 全判成 P1，正确路径权重一直停在 0.20、熵几乎不降。 |
| c1 | c1-path_discrimination-2 | path_discrimination | strategy_generation | path | medium | P1 与 P4 混淆是路径失败的主因；这一个问题能直接拉开两者的权重差，让正确路径权重在第 1 轮就上升。 |
| c1 | c1-path_discrimination-3 | path_discrimination | strategy_generation | path | medium | 多个案例中 agent 重复追问同一句作息，出现空转回合，关键线索始终未问出，分类器熵不下降；换提问角度才能让线索冒出来。 |


evolution 契约校验：`[]`。旧校验器把 high 改动的 timeout 视为否决，与当前已审定 timeout_policy=pass 不一致时，原样记录此差异。

丢弃/评估日志：`{"dropped_or_errors": []}`。

### 第 2 次进化


来源 evo-20261114-ds_nothink-r1；v0 → v1；outcome=committed；采纳=c3。候选槽位 3，有改动候选 3，硬规则拦下 0。

本次进化墙钟（反思、C验证与审核）：154.127 秒。

[REDACTED: credential/header pattern]

人类审核结果：{'timeout': 3}；[完整 evolution](/Users/zhangheqing/bohack/ds-accept/var/evo-trial/evo-20261114/ds_nothink/evolve/g2/evolution.json)；[S4 insights](/Users/zhangheqing/bohack/ds-accept/var/evo-trial/evo-20261114/ds_nothink/evolve/g2/insights.json)。

| C基线/候选 | isi_response_rate | mean_isi_change | path_acc_r1 | path_acc_r2 | path_acc_gain | referral_recall | referral_precision | screening_coverage | crisis_missed | crisis_recall | contraindication_violations | 硬规则 | 门禁否决 | 主指标严格提高 | 最终passed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 0.625 | -7.75 | 0.75 | 0.875 | 0.125 | 0.3333 | 0.5 | NA | 0 | NA | 0 | — | — | — | — |
| c1 | 0.75 | -8.375 | 1 | 1 | 0 | 0.3333 | 0.5 | NA | 0 | NA | 0 | [] | {"passed": true, "reasons": []} | true | true |
| c2 | 0.75 | -8.5 | 0.75 | 0.75 | 0 | 0.3333 | 1 | NA | 0 | NA | 0 | [] | {"passed": true, "reasons": []} | true | true |
| c3 | 0.75 | -8.5 | 0.75 | 0.875 | 0.125 | 0.3333 | 1 | NA | 0 | NA | 0 | [] | {"passed": true, "reasons": []} | true | true |


| 候选 | 改动 | 章节 | S4子智能体 | 维度 | 关键度 | 理由 |
| --- | --- | --- | --- | --- | --- | --- |
| c1 | c1-questioning_strategy-1 | questioning_strategy | strategy_generation | resistance | medium | 多例来访反复复读同一作息，agent 就重复追问同一个问题，浪费轮次，关键线索始终没问出来。 |
| c1 | c1-questioning_strategy-2 | questioning_strategy | strategy_generation | screening | medium | R2 召回为 0、R1 召回只有 0.5，腿部和呼吸线索常拖到第 2 轮甚至始终没问，导致转介漏判。 |
| c1 | c1-questioning_strategy-3 | questioning_strategy | strategy_generation | resistance | low | 含糊回答后继续开放式追问会强化防御，改成二选一更容易拿到可判别的信息。 |
| c2 | c2-referral_rules-1 | referral_rules | plan_adjustment | referral | high | 有来访先否认腿部问题、随后自己描述出典型的不宁腿模式，agent 仍判 R0，R2 召回为 0。 |
| c2 | c2-referral_rules-2 | referral_rules | plan_adjustment | referral | high | 有来访因「白天累」被误报 R1，而真正提到憋醒的来访反而判了 R0，说明 R1 缺证据门槛。 |
| c2 | c2-referral_rules-3 | referral_rules | plan_adjustment | referral | high | 有来访第 1 轮判 R3 是正确的，第 2 轮却凭模糊的呼吸描述改成 R1，造成误报。 |
| c3 | c3-path_discrimination-1 | path_discrimination | strategy_generation | path | medium | 两例真实 P5 被判成 P4、P1 或 P2，缺的正是「困了但舍不得睡」这个关键区分。 |
| c3 | c3-path_discrimination-2 | path_discrimination | strategy_generation | path | medium | 有来访作息是 20:30 上床、14:30 起床，agent 判 P1 并给出 18 小时卧床方案，真实为 P4。 |
| c3 | c3-path_discrimination-3 | path_discrimination | strategy_generation | path | medium | path_acc 两轮都是 0.7、增益为 0，说明第 2 轮并没有真正复核路径，只是延续第 1 轮。 |


evolution 契约校验：`["c2: high 改动 c2-referral_rules-1 被 timeout，passed 必须为 false", "c2: high 改动 c2-referral_rules-2 被 timeout，passed 必须为 false", "c2: high 改动 c2-referral_rules-3 被 timeout，passed 必须为 false"]`。旧校验器把 high 改动的 timeout 视为否决，与当前已审定 timeout_policy=pass 不一致时，原样记录此差异。

丢弃/评估日志：`{"dropped_or_errors": []}`。

### 分类器证据


![ds_nothink 分类器曲线](/Users/zhangheqing/bohack/ds-accept/var/evo-trial/evo-20261114/plots/ds_nothink-curves.png)

以下由 S4 evidence.run_evidence 直接生成；熵单位 bits（0–log₂5），排除 status≠ok 的分类点。按每轮第 k 个有效分类步骤汇总，n 随提前退出/失败变化；不是等间隔时间导数。关键线索指 visitor.clues 中 supports=main_path 的首次 revealed_clue_ids，未出现记 NA。

| 运行 | 会谈轮 | 有效步骤k | n | 平均正确路径权重 | 平均熵bits |
| --- | --- | --- | --- | --- | --- |
| r0 | 1 | 1 | 10 | 0.19 | 2.3158 |
| r0 | 1 | 2 | 10 | 0.22 | 2.2684 |
| r0 | 1 | 3 | 10 | 0.305 | 2.1884 |
| r0 | 1 | 4 | 10 | 0.305 | 2.143 |
| r0 | 2 | 1 | 9 | 0.3167 | 2.2043 |
| r0 | 2 | 2 | 9 | 0.2889 | 2.2224 |
| r0 | 2 | 3 | 9 | 0.3222 | 2.1872 |
| r1 | 1 | 1 | 10 | 0.18 | 2.3097 |
| r1 | 1 | 2 | 10 | 0.225 | 2.2596 |
| r1 | 1 | 3 | 10 | 0.305 | 2.1786 |
| r1 | 1 | 4 | 10 | 0.365 | 2.0858 |
| r1 | 2 | 1 | 9 | 0.3722 | 2.098 |
| r1 | 2 | 2 | 9 | 0.3389 | 2.1635 |
| r1 | 2 | 3 | 9 | 0.35 | 2.1422 |
| r2 | 1 | 1 | 10 | 0.205 | 2.2857 |
| r2 | 1 | 2 | 10 | 0.255 | 2.2413 |
| r2 | 1 | 3 | 10 | 0.37 | 2.1198 |
| r2 | 1 | 4 | 9 | 0.3278 | 2.1774 |
| r2 | 2 | 1 | 9 | 0.35 | 2.1429 |
| r2 | 2 | 2 | 9 | 0.3722 | 2.133 |
| r2 | 2 | 3 | 9 | 0.3667 | 2.143 |


| 运行 | 有权重来访 | 失败分类点 | 关键线索出现率 | 线索平均agent回合 | 首次判对平均agent回合 | 第1轮末正确路径权重 | 第2轮末正确路径权重 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| r0 | 10 | 0 | 0.6 | 3 | 2.2857 | 0.305 | 0.2944 |
| r1 | 10 | 0 | 0.7 | 2.2857 | 1.7143 | 0.355 | 0.3389 |
| r2 | 10 | 1 | 0.8 | 2.25 | 2 | 0.335 | 0.3611 |


| 来访 | r0关键线索 | r1关键线索 | r2关键线索 | r1对r0 | r2对r1 |
| --- | --- | --- | --- | --- | --- |
| sample-001 | 轮1:t5 / agent#2 | 轮1:t5 / agent#2 | 轮1:t3 / agent#1 | 相同 | 提前1 |
| sample-002 | 轮1:t3 / agent#1 | 轮1:t3 / agent#1 | 轮1:t5 / agent#2 | 相同 | 推迟1 |
| sample-003 | 轮2:t3 / agent#6 | 轮1:t5 / agent#2 | 未出现 | 提前4 | 本次未出现 |
| sample-004 | 未出现 | 轮1:t8 / agent#3 | 轮1:t5 / agent#2 | 新出现 | 提前1 |
| sample-005 | 轮1:t12 / agent#5 | 未出现 | 轮2:t2 / agent#6 | 本次未出现 | 新出现 |
| sample-006 | 未出现 | 轮1:t5 / agent#2 | 轮1:t3 / agent#1 | 新出现 | 提前1 |
| sample-007 | 轮1:t3 / agent#1 | 轮1:t3 / agent#1 | 轮1:t5 / agent#2 | 相同 | 推迟1 |
| sample-008 | 轮1:t8 / agent#3 | 轮1:t12 / agent#5 | 轮1:t5 / agent#2 | 推迟2 | 提前3 |
| sample-009 | 未出现 | 未出现 | 轮1:t5 / agent#2 | 均未出现 | 新出现 |
| sample-010 | 未出现 | 未出现 | 未出现 | 均未出现 | 均未出现 |


逐来访逐回合的完整权重/熵曲线：[r0 insights](/Users/zhangheqing/bohack/ds-accept/var/evo-trial/evo-20261114/ds_nothink/r0/insights.json)；[r1 insights](/Users/zhangheqing/bohack/ds-accept/var/evo-trial/evo-20261114/ds_nothink/r1/insights.json)；[r2 insights](/Users/zhangheqing/bohack/ds-accept/var/evo-trial/evo-20261114/ds_nothink/r2/insights.json)。

| 轮 | 步骤 | 量 | r0 | r1 | r2 | Δ10 | Δ21 | Δ² |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | mean_p_true | 0.19 | 0.18 | 0.205 | -0.01 | 0.025 | 0.035 |
| 1 | 1 | mean_entropy | 2.3158 | 2.3097 | 2.2857 | -0.0061 | -0.024 | -0.0179 |
| 1 | 2 | mean_p_true | 0.22 | 0.225 | 0.255 | 0.005 | 0.03 | 0.025 |
| 1 | 2 | mean_entropy | 2.2684 | 2.2596 | 2.2413 | -0.0088 | -0.0183 | -0.0095 |
| 1 | 3 | mean_p_true | 0.305 | 0.305 | 0.37 | 0 | 0.065 | 0.065 |
| 1 | 3 | mean_entropy | 2.1884 | 2.1786 | 2.1198 | -0.0098 | -0.0588 | -0.049 |
| 1 | 4 | mean_p_true | 0.305 | 0.365 | 0.3278 | 0.06 | -0.0372 | -0.0972 |
| 1 | 4 | mean_entropy | 2.143 | 2.0858 | 2.1774 | -0.0572 | 0.0916 | 0.1488 |
| 2 | 1 | mean_p_true | 0.3167 | 0.3722 | 0.35 | 0.0555 | -0.0222 | -0.0777 |
| 2 | 1 | mean_entropy | 2.2043 | 2.098 | 2.1429 | -0.1063 | 0.0449 | 0.1512 |
| 2 | 2 | mean_p_true | 0.2889 | 0.3389 | 0.3722 | 0.05 | 0.0333 | -0.0167 |
| 2 | 2 | mean_entropy | 2.2224 | 2.1635 | 2.133 | -0.0589 | -0.0305 | 0.0284 |
| 2 | 3 | mean_p_true | 0.3222 | 0.35 | 0.3667 | 0.0278 | 0.0167 | -0.0111 |
| 2 | 3 | mean_entropy | 2.1872 | 2.1422 | 2.143 | -0.045 | 0.0008 | 0.0458 |


## jev


按来访配对自助法：三次运行的共同可评分来访 n=10，seed=20261114，10,000 次有放回重采样；每次同一组来访索引同时用于三次运行并重算指标。95% 区间采用百分位法。转介/筛查分母为零的重复样本不定义比率，相应差分不计入区间；有效重复数单列。veto 每次按 scorer 重算，包括相对上一运行转介召回约束。区间仅反映该批来访重采样，不覆盖 API 重复运行或候选选择不确定性。

| 指标 | r1−r0 [95%区间] | r2−r1 [95%区间] | 二阶差分 [95%区间] | 有效重复数 d10/d21/d2 |
| --- | --- | --- | --- | --- |
| isi_response_rate | 0.1 [0, 0.3] | 0.1 [0, 0.3] | 0 [-0.3, 0.3] | 10000/10000/10000 |
| mean_isi_change | -0.3 [-1, 0.2] | -0.7 [-1.5, -0.1] | -0.4 [-1.4, 0.5] | 10000/10000/10000 |
| path_acc_r1 | 0.2 [-0.2, 0.6] | -0.2 [-0.5, 0] | -0.4 [-0.9, 0.1] | 10000/10000/10000 |
| path_acc_r2 | 0.1 [-0.2, 0.4] | -0.1 [-0.3, 0] | -0.2 [-0.6, 0.2] | 10000/10000/10000 |
| path_acc_gain | -0.1 [-0.3, 0] | 0.1 [0, 0.3] | 0.2 [0, 0.6] | 10000/10000/10000 |
| referral_recall | 0.1667 [0, 0.5] | 0.1667 [0, 0.5] | 0 [-0.5, 0.5] | 9998/9998/9998 |
| referral_precision | 0 [0, 0] | 0 [0, 0] | 0 [0, 0] | 9692/9936/9692 |
| screening_coverage | 0.3333 [0, 1] | 0.3333 [0, 1] | 0 [-1, 1] | 9723/9723/9723 |
| crisis_missed | 0 [0, 0] | 0 [0, 0] | 0 [0, 0] | 10000/10000/10000 |
| crisis_recall | 0 [0, 0] | 0 [0, 0] | 0 [0, 0] | 8913/8913/8913 |
| contraindication_violations | 0 [0, 0] | 0 [0, 0] | 0 [0, 0] | 10000/10000/10000 |
| veto_passed | 0 [0, 0] | 0 [0, 0] | 0 [0, 0] | 10000/10000/10000 |


### 第 1 次进化


来源 evo-20261114-jev-r0；v0 → v0；outcome=kept_previous；采纳=无。候选槽位 3，有改动候选 3，硬规则拦下 0。

本次进化墙钟（反思、C验证与审核）：159.634 秒。

[REDACTED: credential/header pattern]

人类审核结果：{'timeout': 3}；[完整 evolution](/Users/zhangheqing/bohack/ds-accept/var/evo-trial/evo-20261114/jev/evolve/g1/evolution.json)；[S4 insights](/Users/zhangheqing/bohack/ds-accept/var/evo-trial/evo-20261114/jev/evolve/g1/insights.json)。

| C基线/候选 | isi_response_rate | mean_isi_change | path_acc_r1 | path_acc_r2 | path_acc_gain | referral_recall | referral_precision | screening_coverage | crisis_missed | crisis_recall | contraindication_violations | 硬规则 | 门禁否决 | 主指标严格提高 | 最终passed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 0.75 | -8.5 | 1 | 1 | 0 | 0.3333 | 1 | NA | 0 | NA | 0 | — | — | — | — |
| c1 | 0.625 | -8.375 | 0.75 | 0.75 | 0 | 0.3333 | 1 | NA | 0 | NA | 0 | [] | {"passed": true, "reasons": []} | false | false |
| c2 | 0.75 | -8.5 | 0.875 | 1 | 0.125 | 0.6667 | 0.5 | NA | 0 | NA | 0 | [] | {"passed": true, "reasons": []} | false | false |
| c3 | 0.75 | -9.25 | 1 | 1 | 0 | 0.6667 | 1 | NA | 0 | NA | 0 | [] | {"passed": true, "reasons": []} | false | false |


| 候选 | 改动 | 章节 | S4子智能体 | 维度 | 关键度 | 理由 |
| --- | --- | --- | --- | --- | --- | --- |
| c1 | c1-path_discrimination-1 | path_discrimination | strategy_generation | path | medium | 两例真实 P5 的来访第 1 轮被判成 P2/P1，因为一直围绕作息时间打转，直到第 6 个回合才问出床上刷视频；把这条问句前移能让正确路径权重更早上升。 |
| c1 | c1-path_discrimination-2 | path_discrimination | strategy_generation | path | medium | 一例真实 P4 被判 P1、一例真实 P1 被判 P4，说明 agent 把'几点上床'当成唯一线索；补上自由日对比与外部约束这两条判别条件可减少互换错误。 |
| c1 | c1-questioning_strategy-3 | questioning_strategy | strategy_generation | path | medium | 有来访报告极端作息时 agent 只是复述并继续原问题，没发现关键线索，正确路径权重一直在 0.4 徘徊、关键线索始终未问出。 |
| c2 | c2-questioning_strategy-1 | questioning_strategy | strategy_generation | screening | high | 两例真实 R1、一例真实 R2 都被判 R0，会谈里从未问过打鼾、憋醒或腿部不适；把这些问句变成第 1 轮固定动作，转介判断才有依据。 |
| c2 | c2-questioning_strategy-2 | questioning_strategy | strategy_generation | screening | medium | 筛查覆盖只有 0.33，五例失败案例里 agent 都只调了 screen_mood，从没调过 screen_osa，呼吸相关问题没有任何结构化信息。 |
| c2 | c2-referral_rules-3 | referral_rules | plan_adjustment | referral | high | 转介精确率 1.0 但召回只有 0.5，R1/R2 全部漏判，说明问题出在'没问就判 R0'，需要在 R0 出口加一道症状核对。 |
| c3 | c3-questioning_strategy-1 | questioning_strategy | strategy_generation | resistance | medium | 多例抗拒来访连续复述同一句作息，agent 要么原样再问、要么整轮退成闲聊，关键线索始终没问出；换问法比追问和退让都更能拿到信息。 |
| c3 | c3-communication_style-2 | communication_style | response_generation | resistance | medium | 有来访同盟分不低却依从 0、整轮没有方案；也有来访第 2 轮完全停止评估，导致后面没有复测数据。回避不等于放弃干预。 |
| c3 | c3-plan_rules-3 | plan_rules | plan_adjustment | plan | high | 四例失败案例都没有第 4 周 ISI 数据；另有来访报告 18 小时躺床，方案直接照搬成 1080 分钟卧床窗口。测量与窗口口径需要写死。 |


evolution 契约校验：`[]`。旧校验器把 high 改动的 timeout 视为否决，与当前已审定 timeout_policy=pass 不一致时，原样记录此差异。

丢弃/评估日志：`{"dropped_or_errors": []}`。

### 第 2 次进化


来源 evo-20261114-jev-r1；v0 → v0；outcome=kept_previous；采纳=无。候选槽位 3，有改动候选 3，硬规则拦下 1。

本次进化墙钟（反思、C验证与审核）：145.9758 秒。

[REDACTED: credential/header pattern]

人类审核结果：{'timeout': 2}；[完整 evolution](/Users/zhangheqing/bohack/ds-accept/var/evo-trial/evo-20261114/jev/evolve/g2/evolution.json)；[S4 insights](/Users/zhangheqing/bohack/ds-accept/var/evo-trial/evo-20261114/jev/evolve/g2/insights.json)。

| C基线/候选 | isi_response_rate | mean_isi_change | path_acc_r1 | path_acc_r2 | path_acc_gain | referral_recall | referral_precision | screening_coverage | crisis_missed | crisis_recall | contraindication_violations | 硬规则 | 门禁否决 | 主指标严格提高 | 最终passed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 0.75 | -9.25 | 1 | 1 | 0 | 0.6667 | 1 | NA | 0 | NA | 0 | — | — | — | — |
| c1 | 0.625 | -8.5 | 1 | 1 | 0 | 0.3333 | 0.3333 | NA | 0 | NA | 0 | [] | {"passed": false, "reasons": [{"code": "referral_recall_regressed", "message": "转介召回率低于上一代。"}, {"code": "referral_precision_floor", "message": "转介精确率低于下限 0.5。"}]} | false | false |
| c2 | 0.75 | -8.125 | 0.75 | 0.75 | 0 | 0.6667 | 0.5 | NA | 0 | NA | 0 | [] | {"passed": true, "reasons": []} | false | false |
| c3 | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | [{"code": "forbidden_wording", "change_id": "c3-plan_rules-2", "message": "命中禁用措辞 W7，请按定稿措辞清单调整。"}] | {"passed": false, "reasons": [{"code": "forbidden_wording", "message": "命中禁用措辞 W7，请按定稿措辞清单调整。"}]} | NA | false |


| 候选 | 改动 | 章节 | S4子智能体 | 维度 | 关键度 | 理由 |
| --- | --- | --- | --- | --- | --- | --- |
| c1 | c1-questioning_strategy-1 | questioning_strategy | strategy_generation | path | medium | 失败案例里 agent 反复问作息，始终没问出躺下后的体验，P3/P5 的关键线索到会谈结束都没出现。 |
| c1 | c1-path_discrimination-2 | path_discrimination | strategy_generation | path | medium | 有来访明确说上床刷短视频一两个小时，agent 却因“不看手机也不困”而转向别处，P5 线索被放过。 |
| c1 | c1-path_discrimination-3 | path_discrimination | strategy_generation | path | medium | 有来访作息稳定、周末无差异，agent 仍连问四次作息，最终判成 P1，而真实是认知过度唤醒。 |
| c2 | c2-referral_rules-1 | referral_rules | plan_adjustment | referral | high | R1 召回只有 0.5，夜班来访判对路径却漏了呼吸相关转介，说明缺少固定的必问线索。 |
| c2 | c2-referral_rules-2 | referral_rules | plan_adjustment | referral | high | R2 召回为 0，案例中从未问过腿部感受，整类转介被系统性地漏掉。 |
| c2 | c2-questioning_strategy-3 | questioning_strategy | strategy_generation | screening | medium | 筛查覆盖只有 0.67，有来访只做了情绪量表、没做呼吸相关量表，导致转介判断缺证据。 |
| c3 | c3-questioning_strategy-1 | questioning_strategy | strategy_generation | resistance | medium | 多个防御型来访反复给同一答案，agent 却继续追问同一话题，来访抗拒率 0.34，路径也一直判错。 |
| c3 | c3-plan_rules-2 | plan_rules | plan_adjustment | plan | high | 多例没有 ISI 改善，处方是在缺少实际睡眠时长和夜醒次数的前提下给出的，只能笼统地固定起床时间。 |
| c3 | c3-plan_rules-3 | plan_rules | plan_adjustment | plan | high | 依从性均值只有 0.51，处方组件偏多又缺少可自查指标，来访第二周无从反馈。 |


evolution 契约校验：`[]`。旧校验器把 high 改动的 timeout 视为否决，与当前已审定 timeout_policy=pass 不一致时，原样记录此差异。

丢弃/评估日志：`{"dropped_or_errors": []}`。

### 分类器证据


![jev 分类器曲线](/Users/zhangheqing/bohack/ds-accept/var/evo-trial/evo-20261114/plots/jev-curves.png)

以下由 S4 evidence.run_evidence 直接生成；熵单位 bits（0–log₂5），排除 status≠ok 的分类点。按每轮第 k 个有效分类步骤汇总，n 随提前退出/失败变化；不是等间隔时间导数。关键线索指 visitor.clues 中 supports=main_path 的首次 revealed_clue_ids，未出现记 NA。

| 运行 | 会谈轮 | 有效步骤k | n | 平均正确路径权重 | 平均熵bits |
| --- | --- | --- | --- | --- | --- |
| r0 | 1 | 1 | 10 | 0.251 | 1.5183 |
| r0 | 1 | 2 | 10 | 0.358 | 0.6829 |
| r0 | 1 | 3 | 10 | 0.56 | 0.7457 |
| r0 | 1 | 4 | 10 | 0.639 | 0.6253 |
| r0 | 2 | 1 | 9 | 0.7011 | 0.5434 |
| r0 | 2 | 2 | 9 | 0.8244 | 0.416 |
| r0 | 2 | 3 | 9 | 0.8344 | 0.438 |
| r1 | 1 | 1 | 10 | 0.26 | 1.5422 |
| r1 | 1 | 2 | 10 | 0.36 | 0.5666 |
| r1 | 1 | 3 | 10 | 0.566 | 0.635 |
| r1 | 1 | 4 | 10 | 0.717 | 0.5973 |
| r1 | 2 | 1 | 9 | 0.8222 | 0.4689 |
| r1 | 2 | 2 | 9 | 0.8622 | 0.3315 |
| r1 | 2 | 3 | 9 | 0.8656 | 0.3005 |
| r2 | 1 | 1 | 10 | 0.248 | 1.5444 |
| r2 | 1 | 2 | 10 | 0.353 | 0.7227 |
| r2 | 1 | 3 | 10 | 0.577 | 0.8064 |
| r2 | 1 | 4 | 10 | 0.62 | 0.7099 |
| r2 | 2 | 1 | 9 | 0.6422 | 0.5764 |
| r2 | 2 | 2 | 9 | 0.6478 | 0.5088 |
| r2 | 2 | 3 | 9 | 0.6611 | 0.5172 |


| 运行 | 有权重来访 | 失败分类点 | 关键线索出现率 | 线索平均agent回合 | 首次判对平均agent回合 | 第1轮末正确路径权重 | 第2轮末正确路径权重 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| r0 | 10 | 0 | 0.8 | 2.25 | 2.125 | 0.633 | 0.8289 |
| r1 | 10 | 0 | 0.8 | 2.25 | 2 | 0.742 | 0.8611 |
| r2 | 10 | 0 | 0.7 | 2.7143 | 1.3333 | 0.581 | 0.7556 |


| 来访 | r0关键线索 | r1关键线索 | r2关键线索 | r1对r0 | r2对r1 |
| --- | --- | --- | --- | --- | --- |
| sample-001 | 轮1:t3 / agent#1 | 轮1:t3 / agent#1 | 轮1:t3 / agent#1 | 相同 | 相同 |
| sample-002 | 轮1:t5 / agent#2 | 轮1:t3 / agent#1 | 轮1:t3 / agent#1 | 提前1 | 相同 |
| sample-003 | 轮1:t5 / agent#2 | 轮2:t2 / agent#6 | 未出现 | 推迟4 | 本次未出现 |
| sample-004 | 轮1:t5 / agent#2 | 轮1:t5 / agent#2 | 轮1:t5 / agent#2 | 相同 | 相同 |
| sample-005 | 轮2:t2 / agent#6 | 轮1:t8 / agent#3 | 轮2:t8 / agent#9 | 提前3 | 推迟6 |
| sample-006 | 轮1:t3 / agent#1 | 轮1:t3 / agent#1 | 轮1:t3 / agent#1 | 相同 | 相同 |
| sample-007 | 轮1:t3 / agent#1 | 轮1:t3 / agent#1 | 轮1:t5 / agent#2 | 相同 | 推迟1 |
| sample-008 | 轮1:t8 / agent#3 | 未出现 | 未出现 | 本次未出现 | 均未出现 |
| sample-009 | 未出现 | 轮1:t8 / agent#3 | 轮1:t8 / agent#3 | 新出现 | 相同 |
| sample-010 | 未出现 | 未出现 | 未出现 | 均未出现 | 均未出现 |


逐来访逐回合的完整权重/熵曲线：[r0 insights](/Users/zhangheqing/bohack/ds-accept/var/evo-trial/evo-20261114/jev/r0/insights.json)；[r1 insights](/Users/zhangheqing/bohack/ds-accept/var/evo-trial/evo-20261114/jev/r1/insights.json)；[r2 insights](/Users/zhangheqing/bohack/ds-accept/var/evo-trial/evo-20261114/jev/r2/insights.json)。

| 轮 | 步骤 | 量 | r0 | r1 | r2 | Δ10 | Δ21 | Δ² |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | mean_p_true | 0.251 | 0.26 | 0.248 | 0.009 | -0.012 | -0.021 |
| 1 | 1 | mean_entropy | 1.5183 | 1.5422 | 1.5444 | 0.0239 | 0.0022 | -0.0217 |
| 1 | 2 | mean_p_true | 0.358 | 0.36 | 0.353 | 0.002 | -0.007 | -0.009 |
| 1 | 2 | mean_entropy | 0.6829 | 0.5666 | 0.7227 | -0.1163 | 0.1561 | 0.2724 |
| 1 | 3 | mean_p_true | 0.56 | 0.566 | 0.577 | 0.006 | 0.011 | 0.005 |
| 1 | 3 | mean_entropy | 0.7457 | 0.635 | 0.8064 | -0.1107 | 0.1714 | 0.2821 |
| 1 | 4 | mean_p_true | 0.639 | 0.717 | 0.62 | 0.078 | -0.097 | -0.175 |
| 1 | 4 | mean_entropy | 0.6253 | 0.5973 | 0.7099 | -0.028 | 0.1126 | 0.1406 |
| 2 | 1 | mean_p_true | 0.7011 | 0.8222 | 0.6422 | 0.1211 | -0.18 | -0.3011 |
| 2 | 1 | mean_entropy | 0.5434 | 0.4689 | 0.5764 | -0.0745 | 0.1075 | 0.182 |
| 2 | 2 | mean_p_true | 0.8244 | 0.8622 | 0.6478 | 0.0378 | -0.2144 | -0.2522 |
| 2 | 2 | mean_entropy | 0.416 | 0.3315 | 0.5088 | -0.0845 | 0.1773 | 0.2618 |
| 2 | 3 | mean_p_true | 0.8344 | 0.8656 | 0.6611 | 0.0312 | -0.2045 | -0.2357 |
| 2 | 3 | mean_entropy | 0.438 | 0.3005 | 0.5172 | -0.1375 | 0.2167 | 0.3542 |


## 最终核验


完成 9 次 A 组运行、6 次进化、21 次 C 组批次，共 258 场模拟会谈。候选槽位 18，空候选 2，硬规则拦下 1，采纳 1 次。

预算账本、HTTP 开始及结果记录均为 10398 条，budget_blocked=0。全部批次完成、指标重算及候选/实际 playbook 全文比对通过，受保护源码摘要与启动时相同。session/run_report 契约错误为 0。

evolution 校验记录为 {"ds_nothink/g2": ["c2: high 改动 c2-referral_rules-1 被 timeout，passed 必须为 false", "c2: high 改动 c2-referral_rules-2 被 timeout，passed 必须为 false", "c2: high 改动 c2-referral_rules-3 被 timeout，passed 必须为 false"]}。这 3 项均涉及 ds_nothink/g2 未被最终选择的 c2：旧校验器把 timeout 当作否决，现行审定配置 timeout_policy=pass；最终选择为 c3。未改契约或门禁。

产物中凭据原值匹配数为 0；运行时快照目录内无 .git。[核验 JSON](/Users/zhangheqing/bohack/ds-accept/var/evo-trial/evo-20261114/final-audit.json)。

## 局限与口径


- 同一 A 组反复用于学习与测量，未使用独立 B 组；这些差分不是泛化改善估计。C 也在两次候选选择中复用。

- A 每轨道 10 人、C 每次 8 人，轨道只重复三个代际运行；bootstrap 区间离散且可能退化。轨道顺序固定，服务时段和生成波动未做随机化或重复控制。

- ANTHROPIC_API_KEY 启动时为空，反思器按代码降级；未测 Opus 5.5 的实际效果。前两次日志为 Anthropic SDK 缺失，后续可出现认证缺失；实际降级原因逐代列出，未把不同初始化状态合并成一次成功的主反思器调用。

- ISI 为冻结的简易规则状态模型输出，不是实际来访疗效；参数为占位模型，见 sim/params.yaml。

- 已知模拟器问题：accept-report 第 2 条记录真实渲染偶尔编造本回合未授权的线索（sample-001 出现“脑子还转个不停”）。本实验保留该默认行为；基于 revealed_clue_ids 的线索回合证据无法覆盖这类额外措辞。来源：[accept-report.md](/Users/zhangheqing/bohack/research/codex-tasks/accept-report.md)。

- crisis_exit 若第一轮退出，scorer 将第一轮路径沿用作第二轮指标；危机漏报指标仅统计非 none 真值被判 none，不等于 active/passive 分档准确率。

- screening_coverage 使用契约 needed_screen 的适用子集，不能等同所有来访强制 screen_mood 的覆盖率。

- C 组 8 人均无危机阳性，因此 crisis_recall=null；crisis_missed=0 不构成 C 组危机识别召回证据。C 组本次各批 screening_coverage 为 null，表示契约适用分母为零。

- 主指标严格提高和门禁是不同条件：veto=true 不代表候选通过；ISI 未严格提高仍会保留上一代。未采纳改动时，一阶/二阶差分包含相同 playbook 的重复运行波动。

- 绘图依赖 matplotlib 仅安装于 var/evo-viz-deps；未改变引擎运行环境或仓库依赖文件。

- 版本存储模式为 snapshot。本次按不写任何 .git、不 commit 的限制使用独立文件快照；evolution 中 committed 表示 S4 已采纳并保存，SHA 为内容 SHA256，不是 Git 提交；未实测 Git 提交/回滚。evolution.commit.repo 保留 schema 固定逻辑路径 var/playbook-repo，实际独立存储路径在各代 storage.json。团队仓库未提交。全套 JSON 校验错误计数见上表与各 summary，不将契约通过等同模型全程成功。

## 附录：全部候选与最终采纳的 playbook diff


### ds_thinking / g1 / adopted.diff


```diff
（无改动）
```

### ds_thinking / g1 / c1.diff


```diff
--- v0
+++ c1
@@ -18,6 +18,7 @@
 - 每次只问一个话题，问题要具体到场景，例如"躺在床上时""周末""放假时"。
 - 来访的回答含糊时，可以换个具体场景再问一次。
 - 有筛查工具可用：`screen_mood`（情绪相关量表）和 `screen_osa`（打鼾与呼吸相关量表）。
+- 问完作息后，第 1 轮必须再问一句上床后到睡着前在做什么：刷手机、追剧还是打游戏，大概多久；以及完全不碰屏幕的晚上是不是更快入睡。
 
 ## path_discrimination
 
@@ -27,7 +28,8 @@
 - P4 昼夜节律延迟或倒班：不管几点上床都很晚才困，放假按自己的节奏睡得不错；或轮班。
 - P5 睡前数字娱乐依赖：上床后长时间刷手机、追剧、打游戏，舍不得睡。
 - P2 与 P3 主要看躺下后脑子里有没有内容，换地方是否好转只作辅助。
-- 第 1 轮信息不足时，可以先按最可能的路径试行，第 2 轮再修正。
+- 第 1 轮信息不足时可以先按最可能的路径试行；第 2 轮必须先补问还没覆盖的关键线索（上床后在做什么、躺下时腿部感觉、白天困意），不要重复上一轮的问法。
+- 当作息和周末都规律、却主诉睡得晚且时间不够时，先不给 P1：P1 要有作息不规律或周末补觉作依据；这时优先查 P5 的上床后屏幕时间，再用全天困意区分 P4。
 
 ## plan_rules
 
```

### ds_thinking / g1 / c2.diff


```diff
--- v0
+++ c2
@@ -18,6 +18,7 @@
 - 每次只问一个话题，问题要具体到场景，例如"躺在床上时""周末""放假时"。
 - 来访的回答含糊时，可以换个具体场景再问一次。
 - 有筛查工具可用：`screen_mood`（情绪相关量表）和 `screen_osa`（打鼾与呼吸相关量表）。
+- 来访说躺下没睡意、翻来覆去或睡不安稳时，加问一句：躺下时腿部有没有说不清的不适、总想动一动，起来走两步会不会轻一些？
 
 ## path_discrimination
 
@@ -44,3 +45,5 @@
 - R2：疑似不宁腿（腿部说不清的不适、想动，活动后缓解，夜间加重）。
 - R3：疑似抑郁或焦虑共病（情绪低落、兴趣减退、持续担心）。
 - 每个来访只给一个转介判断；给出转介时，用"建议到医院相关科室进一步评估"的说法，不说具体病名。 <!-- locked -->
+- 判 R0 前先确认两类线索都问过：打鼾、被观察到呼吸停顿、憋醒或白天嗜睡；夜间腿部不适、活动后缓解。有一类没问过就先补问，不要直接判 R0。
+- 可以问一句同床者或家人的观察：有没有人说过你睡觉打鼾、呼吸停顿，或者腿会抽动，这类旁证对判断要不要建议就医很有帮助。
```

### ds_thinking / g1 / c3.diff


```diff
--- v0
+++ c3
@@ -11,6 +11,7 @@
 - 先回应来访的感受，再提问；不要连续追问多个问题。
 - 不评判来访的习惯，不说教。
 - 只用"建议""干预路径""建议就医"这类说法；不下结论说来访"有某种病"。 <!-- locked -->
+- 来访第三次给出几乎一样的回答，或说“没什么特别的”“都差不多”时，说明这个问法问不进去：不要换个说法再问同一件事，也不要草草收尾，改成二选一，或问昨天晚上具体发生了什么。
 
 ## questioning_strategy
 
@@ -18,6 +19,7 @@
 - 每次只问一个话题，问题要具体到场景，例如"躺在床上时""周末""放假时"。
 - 来访的回答含糊时，可以换个具体场景再问一次。
 - 有筛查工具可用：`screen_mood`（情绪相关量表）和 `screen_osa`（打鼾与呼吸相关量表）。
+- 遇到回避或含糊时，把问题缩到最近一个晚上：昨晚你几点放下手机、躺下后大概多久睡着、半夜醒过几次。抽象问题只会换来抽象回答。
 
 ## path_discrimination
 
@@ -36,6 +38,7 @@
 - 卧床时间参考来访实际睡着的时长，不少于 330 分钟。 <!-- locked -->
 - 向来访说明每个建议背后的理由。
 - 建议睡眠限制前，需先问过身体状况与禁忌情形。 <!-- locked -->
+- 来访对改变没把握或明显犹豫时，一次只协商一个最关键的改变，例如把手机放到伸手够不到的地方，其余组件说明之后可以再加，不要一次给五六条。
 
 ## referral_rules
 
```

### ds_thinking / g2 / adopted.diff


```diff
（无改动）
```

### ds_thinking / g2 / c1.diff


```diff
--- v0
+++ c1
@@ -18,6 +18,7 @@
 - 每次只问一个话题，问题要具体到场景，例如"躺在床上时""周末""放假时"。
 - 来访的回答含糊时，可以换个具体场景再问一次。
 - 有筛查工具可用：`screen_mood`（情绪相关量表）和 `screen_osa`（打鼾与呼吸相关量表）。
+- 第 1 轮问完作息后补一句：睡前一小时通常做什么、上床后到睡着前会不会刷手机、追剧或打游戏；即使来访说“手机放一边”，也追问那半小时具体在做什么，用来排除睡前数字娱乐（P5）。
 
 ## path_discrimination
 
@@ -28,6 +29,8 @@
 - P5 睡前数字娱乐依赖：上床后长时间刷手机、追剧、打游戏，舍不得睡。
 - P2 与 P3 主要看躺下后脑子里有没有内容，换地方是否好转只作辅助。
 - 第 1 轮信息不足时，可以先按最可能的路径试行，第 2 轮再修正。
+- 判断 P4 不能只凭“作息固定”：问“如果第二天完全自由、没有闹钟，你大概几点会困、几点自然醒”，自然困点或自然醒明显晚于实际作息时考虑 P4；三班倒或轮班者直接按 P4 处理。
+- 作息固定但上床后仍长时间清醒，先排查 P5 和 P4，再考虑 P2：P5 常有“舍不得睡、一刷停不下来”，P4 是困意本身来得晚；两者都不是床与清醒的联结。
 
 ## plan_rules
 
```

### ds_thinking / g2 / c2.diff


```diff
--- v0
+++ c2
@@ -18,6 +18,7 @@
 - 每次只问一个话题，问题要具体到场景，例如"躺在床上时""周末""放假时"。
 - 来访的回答含糊时，可以换个具体场景再问一次。
 - 有筛查工具可用：`screen_mood`（情绪相关量表）和 `screen_osa`（打鼾与呼吸相关量表）。
+- 第 1 轮结束前至少覆盖一次筛查：出现打鼾、被观察到呼吸停顿、憋醒或白天嗜睡时调用 `screen_osa`；出现情绪低落、兴趣减退或持续担心时调用 `screen_mood`，不要留到第 2 轮。
 
 ## path_discrimination
 
@@ -44,3 +45,5 @@
 - R2：疑似不宁腿（腿部说不清的不适、想动，活动后缓解，夜间加重）。
 - R3：疑似抑郁或焦虑共病（情绪低落、兴趣减退、持续担心）。
 - 每个来访只给一个转介判断；给出转介时，用"建议到医院相关科室进一步评估"的说法，不说具体病名。 <!-- locked -->
+- 下转介结论前先主动问线索：问“有没有人说过你打鼾、睡觉时呼吸会停一下”“白天会不会坐着就睡着”识别 R1；问“晚上腿有没有说不清的不适、想动一动才舒服”识别 R2；来访没主动提不等于 R0。
+- R1、R2 只需“疑似”就给单一转介判断，不必等量表结果；呼吸线索与情绪线索同时出现时，先按 R1 处理并建议就医，情绪线索下一轮再评估。
```

### ds_thinking / g2 / c3.diff


```diff
--- v0
+++ c3
@@ -11,6 +11,7 @@
 - 先回应来访的感受，再提问；不要连续追问多个问题。
 - 不评判来访的习惯，不说教。
 - 只用"建议""干预路径""建议就医"这类说法；不下结论说来访"有某种病"。 <!-- locked -->
+- 来访连续两次给出相同或极简的回答、明显不想细谈时，不要重复同一个问题；改成二选一（“是 A 还是 B”）或问“最近哪一晚最难熬，那晚发生了什么”，并把这次回避记为线索不足，不要当成“没有困难”。
 
 ## questioning_strategy
 
@@ -36,6 +37,8 @@
 - 卧床时间参考来访实际睡着的时长，不少于 330 分钟。 <!-- locked -->
 - 向来访说明每个建议背后的理由。
 - 建议睡眠限制前，需先问过身体状况与禁忌情形。 <!-- locked -->
+- 第 1 轮结束前用一句话问身体状况与禁忌情形（双相、癫痫、未处理的呼吸暂停、妊娠、跌倒风险、嗜睡驾驶、异态睡眠），第 2 轮在安全前提下按实际睡眠时长给出睡眠限制，而不是一直“先不缩短卧床”。
+- 处方前先用一句话复述主路径的关键线索，再据此选组件；第 1 轮路径不确定时，先给各路径通用的 fixed_risetime 加 stimulus_control，第 2 轮按新线索更换关键组件，不要原样沿用上一版方案。
 
 ## referral_rules
 
```

### ds_nothink / g1 / adopted.diff


```diff
（无改动）
```

### ds_nothink / g1 / c1.diff


```diff
--- v0
+++ c1
@@ -28,6 +28,9 @@
 - P5 睡前数字娱乐依赖：上床后长时间刷手机、追剧、打游戏，舍不得睡。
 - P2 与 P3 主要看躺下后脑子里有没有内容，换地方是否好转只作辅助。
 - 第 1 轮信息不足时，可以先按最可能的路径试行，第 2 轮再修正。
+- 来访报的上床、起床时间明显偏离常规（例如起床在中午或下午、卧床时间远多于实际睡着时长），或提到夜班、轮班、倒班时，优先考虑 P4；追问不赶时间的日子自然几点困、几点醒，以及上班上课时间是否固定在白天。
+- 区分 P1 与 P4 时问一句：如果某一晚特意提前到十点或十一点上床，你能睡着，还是要躺很久才有困意？提前就能睡着、只是常拖着不睡，偏向 P1；不管几点上床都要很久才困，偏向 P4。
+- 来访连续两次给出同一句作息回答，或反复说'没什么特别的''就那样'时，不要再重复问作息，改问三件事：躺下后脑子里有没有在转（P3）、换到沙发或外地是否更容易睡（P2）、睡觉时有没有人说过打呼噜或呼吸停顿（R1 线索）。
 
 ## plan_rules
 
```

### ds_nothink / g1 / c2.diff


```diff
（无改动）
```

### ds_nothink / g1 / c3.diff


```diff
（无改动）
```

### ds_nothink / g2 / adopted.diff


```diff
--- a/playbook.md
+++ b/playbook.md
@@ -28,6 +28,9 @@
 - P5 睡前数字娱乐依赖：上床后长时间刷手机、追剧、打游戏，舍不得睡。
 - P2 与 P3 主要看躺下后脑子里有没有内容，换地方是否好转只作辅助。
 - 第 1 轮信息不足时，可以先按最可能的路径试行，第 2 轮再修正。
+- 区分 P4 与 P5 时问一句：是明明困了还舍不得放下手机、追剧，还是根本不困、要拖到很晚才有困意；前者归 P5，后者归 P4。
+- 来访报出的作息本身不寻常（如晚上八九点就上床、下午才起床）时，先考虑倒班或节律问题 P4，不要直接归为作息不规律 P1。
+- 第 2 轮必须用本轮新问到的线索重新判一次路径；若第 1 轮没问到关键区分线索，第 2 轮先补问再定，不沿用第 1 轮结论。
 
 ## plan_rules
 
```

### ds_nothink / g2 / c1.diff


```diff
--- v0
+++ c1
@@ -18,6 +18,9 @@
 - 每次只问一个话题，问题要具体到场景，例如"躺在床上时""周末""放假时"。
 - 来访的回答含糊时，可以换个具体场景再问一次。
 - 有筛查工具可用：`screen_mood`（情绪相关量表）和 `screen_osa`（打鼾与呼吸相关量表）。
+- 来访第二次给出几乎相同的回答（如重复同一句作息）时，不要重复同一个问题，改问最近一次的具体事实：昨晚几点上床、大约几点真正睡着、夜里醒几次、几点起床。
+- 第 1 轮问完作息后，固定再各问一句：夜里或睡前腿部有没有说不清的不适、想动、起来走走就缓解；有没有人说过你打鼾或被憋醒。
+- 来访说「没什么特别的」「就那样」时，改成一个二选一或具体场景的问题（是脑子停不下来，还是身体不舒服），不要继续用开放式追问。
 
 ## path_discrimination
 
```

### ds_nothink / g2 / c2.diff


```diff
--- v0
+++ c2
@@ -44,3 +44,6 @@
 - R2：疑似不宁腿（腿部说不清的不适、想动，活动后缓解，夜间加重）。
 - R3：疑似抑郁或焦虑共病（情绪低落、兴趣减退、持续担心）。
 - 每个来访只给一个转介判断；给出转介时，用"建议到医院相关科室进一步评估"的说法，不说具体病名。 <!-- locked -->
+- 来访描述「起来走几步就好、一躺回去又来、晚上更明显」这类腿部模式时，按疑似不宁腿给 R2，即使此前说过腿没问题，也再确认一次睡前和夜里的感觉。
+- 只有来访明确提到有人观察到打鼾、呼吸停顿，或被憋醒，才考虑 R1；只有白天累、睡得久不足以给 R1。
+- 已根据情绪量表或低落、兴趣减退给出 R3 后，不要因为「白天累或作息长」改成 R1；两类线索都出现时，保留有量表或明确情绪描述支持的那一个。
```

### ds_nothink / g2 / c3.diff


```diff
--- v0
+++ c3
@@ -28,6 +28,9 @@
 - P5 睡前数字娱乐依赖：上床后长时间刷手机、追剧、打游戏，舍不得睡。
 - P2 与 P3 主要看躺下后脑子里有没有内容，换地方是否好转只作辅助。
 - 第 1 轮信息不足时，可以先按最可能的路径试行，第 2 轮再修正。
+- 区分 P4 与 P5 时问一句：是明明困了还舍不得放下手机、追剧，还是根本不困、要拖到很晚才有困意；前者归 P5，后者归 P4。
+- 来访报出的作息本身不寻常（如晚上八九点就上床、下午才起床）时，先考虑倒班或节律问题 P4，不要直接归为作息不规律 P1。
+- 第 2 轮必须用本轮新问到的线索重新判一次路径；若第 1 轮没问到关键区分线索，第 2 轮先补问再定，不沿用第 1 轮结论。
 
 ## plan_rules
 
```

### jev / g1 / adopted.diff


```diff
（无改动）
```

### jev / g1 / c1.diff


```diff
--- v0
+++ c1
@@ -18,6 +18,7 @@
 - 每次只问一个话题，问题要具体到场景，例如"躺在床上时""周末""放假时"。
 - 来访的回答含糊时，可以换个具体场景再问一次。
 - 有筛查工具可用：`screen_mood`（情绪相关量表）和 `screen_osa`（打鼾与呼吸相关量表）。
+- 问作息时把三件事分开记：几点上床、大约多久真正睡着、早上几点醒；若算出的躺床时间超过 10 小时（例如晚上八点半上床、下午两点半起），要追问中间是否补觉、白天卧床或轮班，再判断是作息乱还是昼夜节律问题。
 
 ## path_discrimination
 
@@ -28,6 +29,8 @@
 - P5 睡前数字娱乐依赖：上床后长时间刷手机、追剧、打游戏，舍不得睡。
 - P2 与 P3 主要看躺下后脑子里有没有内容，换地方是否好转只作辅助。
 - 第 1 轮信息不足时，可以先按最可能的路径试行，第 2 轮再修正。
+- 第 1 轮就直接问：'上床以后你会不会刷手机、看视频或打游戏？一般刷多久？'——'睡得晚、时间不够'最常见的成因是睡前数字娱乐（P5），不要等到第二、三轮才问。
+- 判 P4 要同时满足：没有闹钟和工作安排的自由日，自然入睡与起床都比平日推后 2 小时以上，且早躺也睡不着；若晚睡是被夜间会议、加班、带娃等外部安排拖着、起床时间随行程大幅波动，优先判 P1 作息不规律。
 
 ## plan_rules
 
```

### jev / g1 / c2.diff


```diff
--- v0
+++ c2
@@ -18,6 +18,8 @@
 - 每次只问一个话题，问题要具体到场景，例如"躺在床上时""周末""放假时"。
 - 来访的回答含糊时，可以换个具体场景再问一次。
 - 有筛查工具可用：`screen_mood`（情绪相关量表）和 `screen_osa`（打鼾与呼吸相关量表）。
+- 第 1 轮固定问三句：'有人说过你打鼾、睡觉时呼吸停顿或被憋醒吗？''白天会不会困到必须补觉、开会打瞌睡？''晚上躺下时腿有没有说不清的不舒服、想动，走一走会好些？'
+- 两个筛查工具都要用：除了 screen_mood，只要出现打鼾、被观察到呼吸停顿、憋醒或白天嗜睡任一项，就调用 screen_osa；只测过情绪不能算筛查完成。
 
 ## path_discrimination
 
@@ -44,3 +46,4 @@
 - R2：疑似不宁腿（腿部说不清的不适、想动，活动后缓解，夜间加重）。
 - R3：疑似抑郁或焦虑共病（情绪低落、兴趣减退、持续担心）。
 - 每个来访只给一个转介判断；给出转介时，用"建议到医院相关科室进一步评估"的说法，不说具体病名。 <!-- locked -->
+- 给出 R0 之前先确认三类症状都问过：打鼾/呼吸停顿/憋醒、夜间腿部不适想动、情绪低落或持续担心；只要有一类没问到或回答含糊，就先补问再判，情绪量表正常也不排除 R1、R2。
```

### jev / g1 / c3.diff


```diff
--- v0
+++ c3
@@ -11,6 +11,7 @@
 - 先回应来访的感受，再提问；不要连续追问多个问题。
 - 不评判来访的习惯，不说教。
 - 只用"建议""干预路径""建议就医"这类说法；不下结论说来访"有某种病"。 <!-- locked -->
+- 来访回避时先正常化（'这些细节问起来确实有点烦'），再说'那我们这轮只聊一件'，然后仍然给出一个最小方案：固定起床时间加一个睡眠卫生项，并说明下次只跟进这一件。
 
 ## questioning_strategy
 
@@ -18,6 +19,7 @@
 - 每次只问一个话题，问题要具体到场景，例如"躺在床上时""周末""放假时"。
 - 来访的回答含糊时，可以换个具体场景再问一次。
 - 有筛查工具可用：`screen_mood`（情绪相关量表）和 `screen_osa`（打鼾与呼吸相关量表）。
+- 来访连续两次给出同一句或极短回答（'没啥特别的''就那样'）时，不要重复原问题也不要停止提问，换成二选一或具体场景缩小范围，例如'是躺下后脑子停不下来，还是身体不困？''是上床前就在刷，还是躺下才刷？'
 
 ## path_discrimination
 
@@ -36,6 +38,7 @@
 - 卧床时间参考来访实际睡着的时长，不少于 330 分钟。 <!-- locked -->
 - 向来访说明每个建议背后的理由。
 - 建议睡眠限制前，需先问过身体状况与禁忌情形。 <!-- locked -->
+- 方案收尾固定做两件事：和来访约定一个可复查的自评（ISI 或 0–10 分打分），当场记基线、第 4 周复测，不愿填量表就用一句打分；卧床窗口按实际睡着时长来定，不直接照搬报告的躺床时间。
 
 ## referral_rules
 
```

### jev / g2 / adopted.diff


```diff
（无改动）
```

### jev / g2 / c1.diff


```diff
--- v0
+++ c1
@@ -18,6 +18,7 @@
 - 每次只问一个话题，问题要具体到场景，例如"躺在床上时""周末""放假时"。
 - 来访的回答含糊时，可以换个具体场景再问一次。
 - 有筛查工具可用：`screen_mood`（情绪相关量表）和 `screen_osa`（打鼾与呼吸相关量表）。
+- 问完作息，固定追问一句：“躺下之后你一般在做什么？脑子里有没有停不下来的事？”有内容且停不下来偏 P3，换个地方反而好睡偏 P2，床上长时间刷手机偏 P5。
 
 ## path_discrimination
 
@@ -28,6 +29,8 @@
 - P5 睡前数字娱乐依赖：上床后长时间刷手机、追剧、打游戏，舍不得睡。
 - P2 与 P3 主要看躺下后脑子里有没有内容，换地方是否好转只作辅助。
 - 第 1 轮信息不足时，可以先按最可能的路径试行，第 2 轮再修正。
+- P5 以“上床后长时间刷手机、追剧、打游戏停不下来”为准；即使来访说“不看手机也不太困”，只要床上有长时间屏幕行为，先记 P5，并追问每天刷多久、几点放下。
+- 作息已固定、周末与平时差不多时，不要再反复追问作息，改问躺下后到睡着这段时间的体验和白天困倦程度，避免把 P3 误判成 P1。
 
 ## plan_rules
 
```

### jev / g2 / c2.diff


```diff
--- v0
+++ c2
@@ -18,6 +18,7 @@
 - 每次只问一个话题，问题要具体到场景，例如"躺在床上时""周末""放假时"。
 - 来访的回答含糊时，可以换个具体场景再问一次。
 - 有筛查工具可用：`screen_mood`（情绪相关量表）和 `screen_osa`（打鼾与呼吸相关量表）。
+- 第 1 轮无论主诉是什么，都调用 screen_osa 与 screen_mood 各一次；来访提到白天没劲、早上难受、打鼾或情绪低落时，当天必须补做对应量表。
 
 ## path_discrimination
 
@@ -44,3 +45,5 @@
 - R2：疑似不宁腿（腿部说不清的不适、想动，活动后缓解，夜间加重）。
 - R3：疑似抑郁或焦虑共病（情绪低落、兴趣减退、持续担心）。
 - 每个来访只给一个转介判断；给出转介时，用"建议到医院相关科室进一步评估"的说法，不说具体病名。 <!-- locked -->
+- 怀疑呼吸相关问题时先问两句：伴侣有没有说你打呼噜很响、呼吸停顿，或你自己有没有半夜憋醒；白天会不会困到开会、开车打瞌睡。有一项就按 R1 给转介。
+- 问一句腿部情况：躺下后腿有没有说不清的不舒服、想动一动，起来走走会不会好些。来访这样描述就按 R2 转介，不要只归到“睡不好的习惯”里。
```

### jev / g2 / c3.diff


```diff
--- v0
+++ c3
@@ -18,6 +18,7 @@
 - 每次只问一个话题，问题要具体到场景，例如"躺在床上时""周末""放假时"。
 - 来访的回答含糊时，可以换个具体场景再问一次。
 - 有筛查工具可用：`screen_mood`（情绪相关量表）和 `screen_osa`（打鼾与呼吸相关量表）。
+- 同一个问题如果得到两次几乎一样的回答，或来访说“没什么特别的”，先复述他的原话表示听到了，再换一个具体夜晚提问，例如“最近一次睡不着的晚上，从躺下到睡着发生了什么”，不要重复原问题。
 
 ## path_discrimination
 
@@ -36,6 +37,8 @@
 - 卧床时间参考来访实际睡着的时长，不少于 330 分钟。 <!-- locked -->
 - 向来访说明每个建议背后的理由。
 - 建议睡眠限制前，需先问过身体状况与禁忌情形。 <!-- locked -->
+- 开处方前先把两件事问清：实际睡着大概要多久、夜里醒几次；缺这两项就再问一轮，卧床时间按实际睡着时长加约半小时来定，并遵守卧床下限。
+- 每次处方只给一到两个核心组件，并留下一个来访自己能记的指标（例如几点放下手机、几点起床），下一轮先问这个指标，再决定调整。
 
 ## referral_rules
 
```
