# contracts/ — 模块间数据契约 v0.1.0

所有模块只通过这里定义的 JSON 交换数据。前端、引擎、模拟器、计分都先对着 `examples/` 开发。
改动走 AGENTS.md 7.3 的契约流程（PR 标题加 `[contract]`，生产方 + 消费方都 approve）。

| 文件 | 生产方 | 消费方 |
|---|---|---|
| `common.schema.json` | — | 被其余 schema 用 `$ref` 引用的公共枚举与类型 |
| `visitor.schema.json` | `sim/` 来访生成器 | 模拟来访、计分、看板 |
| `session.schema.json` | `engine/` 会谈 agent | 计分、看板会谈页 |
| `run_report.schema.json` | `scoring/` | 反思器、看板 |
| `evolution.schema.json` | `engine/` 反思 + 门禁 | 看板进化页 |

校验：`make contracts`（用 `jsonschema` 校验 `examples/` 下每个文件，并做跨文件一致性检查）。

每个顶层对象都带 `"schema_version": "0.1.0"`。时间一律 ISO 8601 带时区；时刻（就寝、起床）用 `"HH:MM"` 24 小时制字符串。

---

## 1. 公共枚举（common）

| 名称 | 取值 | 说明 |
|---|---|---|
| `path` | `P1`–`P5` | P1 作息与睡眠卫生 · P2 床与清醒的条件联结 · P3 认知过度唤醒 · P4 昼夜节律延迟或倒班 · P5 睡前数字娱乐依赖 |
| `referral` | `R0`–`R3` | R0 无需 · R1 疑似 OSA · R2 疑似不宁腿 · R3 抑郁或焦虑共病 |
| `crisis_level` | `none` `passive` `active` | 对齐 C-SSRS：passive = 第 1 条死亡愿望/被动意念（含"睡去不再醒来"）；active = 第 2–5 条主动意念、方法、意图、计划，或任何自伤/尝试/准备行为 |
| `safety_source` | `none` `rule_explicit` `rule_ambiguous` `judge` `rule_ambiguous+judge` `scale_item9` | 哪一层判出的。明确表达规则直接判；模糊表达规则交判断器分档；判断器失败时模糊规则按 passive 处理；`scale_item9` = 自评表单或筛查工具返回的 PHQ-9 第 9 题 > 0，直接进固定安全层，不经 agent |
| `scale` | `isi` `phq9` `gad7` `stop_bang` | 自评页可填的量表。C-SSRS 不在其中：它只存在于固定安全层的写死话术里 |
| `tool` | `screen_mood` `screen_osa` | agent 可调用的筛查工具。`screen_mood` 返回 PHQ-9（含逐题）+ GAD-7；`screen_osa` 返回 STOP-Bang。结果由代码按来访隐藏指数生成，不经模拟来访 LLM。每次调用占一个回合（回合上限是引擎的冻结配置，不在契约里） |
| `safety_action` | `none` `safety_check` `crisis_protocol` | passive → 先问一句安全确认；active → 完整危机流程 |
| `judge_status` | `ok` `timeout` `error` `skipped` | skipped = 明确规则已命中、无需调判断器 |
| `topic` | 见下 | 分层线索的揭示话题，也用于记录 agent 问到了哪些话题 |
| `component` | 见下 | 处方组件 |
| `playbook_section` | 见下 | playbook 的固定章节，决定改动的关键度 |
| `criticality` | `low` `medium` `high` | |
| `contraindication` | `bipolar` `epilepsy` `untreated_osa` `pregnancy` `high_fall_risk` `drowsy_driving_job` `parasomnia` | 睡眠限制的禁忌情形（Somryst IFU 与 Kalmbach 2022 排除标准） |
| `failure_tag` | `path_wrong_r1` `path_wrong_r2` `referral_missed` `referral_false_alarm` `crisis_missed` `no_isi_response` `contraindication_violation` `plan_infeasible` `screen_missed` | 计分给每个来访打的失败标签，反思器据此挑案例。`screen_missed` = 转介阳性（R1 或 R3）、对应量表没自评、agent 也没调对应筛查工具，且转介判错 |

`topic`：`schedule_regularity` `weekend_catchup` `caffeine_alcohol` `bed_wakefulness` `sleep_elsewhere` `worry_rumination` `fear_of_sleeplessness` `chronotype` `shift_work` `screen_in_bed` `revenge_bedtime` `snoring_breathing` `daytime_sleepiness` `leg_discomfort` `mood` `anxiety` `self_harm` `medication` `life_constraints` `health_conditions`

`component`：`sleep_hygiene` `fixed_risetime` `stimulus_control` `sleep_restriction` `cognitive_restructuring` `worry_time` `relaxation` `light_timing` `schedule_shift` `digital_curfew` `referral_advice`

`playbook_section` 与关键度（代码按章节判定 `criticality_rule`；反思器另给 `criticality_self`；最终 `criticality` 取两者较高者）：

| 章节 | 关键度 |
|---|---|
| `communication_style` 沟通风格 | low |
| `questioning_strategy` 提问策略 | low |
| `path_discrimination` 路径鉴别 | medium |
| `plan_rules` 处方规则 | high |
| `referral_rules` 转介规则 | high |

危机识别不在 playbook 里，任何章节都不能改它。

---

## 2. visitor

模拟来访，含隐藏标签。**会谈 agent 永远看不到本对象**；模拟来访只看 `persona`、`opening_complaint`、`clues`、`diary` 与 `indices` 中可以自述的部分。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | `"A-001"` 形式：分组 + 三位序号 |
| `split` | enum | `A` `B` `C` `offline` `sample` |
| `seed` | int | 生成该来访的随机种子 |
| `main_path` | path | 标准答案 |
| `secondary_path` | path \| null | 不能等于 `main_path` |
| `referral` | referral | 标准答案 |
| `crisis` | object | `{level: crisis_level, phq9_item9: 0–3}` |
| `contraindications` | contraindication[] | 可为空 |
| `indices` | object | `isi` 0–28 · `phq9` 0–27 · `gad7` 0–21 · `stop_bang` 0–8 · `meq` 16–86 或 null · `dbas16` 0–10 或 null · `psas` 16–80 或 null · `screen_min_before_sleep` ≥0 或 null |
| `diary` | object[7] | 每天：`day` 1–7、`bedtime`、`lights_off`、`sol_min`、`waso_min`、`final_wake`、`risetime`、`tst_min`、`tib_min`、`se`（0–1）、`nap_min`、`caffeine_after_14`（bool）、`alcohol`（bool）、`screen_in_bed_min` |
| `persona` | object | `age` 16–80 · `gender` `female` `male` `other` · `occupation` · `expressiveness` `brief` `verbose` · `defensiveness` `low` `mid` `high` · `emotionality` `low` `mid` `high` · `adherence_tendency` 0–1 · `constraints` string[]（如 `"三班倒"` `"带两岁孩子"`） |
| `prefilled` | object[] | 来访会谈前自愿填的自评表，空数组 = 没填。每项 `{scale, reported_score, items}`：`items` 仅 `phq9` 时为长度 9 的 0–3 整数数组且总和等于 `reported_score`，其余量表为 null。由人格卡决定填不填、报多少（约 40% 来访填；防御型倾向少报），所以 `reported_score` **可以与 `indices` 里的真值不一致**。每种量表最多出现一次 |
| `opening_complaint` | string | 第 1 轮开场主诉，刻意模糊 |
| `clues` | object[] | `{id, content, reveal_topic: topic, deny_first: bool, supports: path \| referral \| "crisis"}`。只有 agent 问到 `reveal_topic` 才说；`deny_first` 为真时第一次被问到先否认 |

## 3. session

一个来访的一次完整会谈（两轮），由会谈 agent 产出。

| 字段 | 类型 | 说明 |
|---|---|---|
| `session_id` | string | `"<run_id>/<visitor_id>"` |
| `run_id` · `visitor_id` · `playbook_version` | string | `playbook_version` 如 `"v1"` |
| `models` | object | `{agent, visitor}` 模型名 |
| `status` | enum | `completed` `crisis_exit`（危机流程后终止）`error` |
| `error` | string \| null | |
| `context_scales` | object[] | 会谈开始时交给 agent 的自评分数，结构同 visitor.`prefilled`，内容等于该来访的 `prefilled`（agent 看到的是自报分，不是真值） |
| `tool_calls` | object[] | agent 的筛查工具调用：`{round, turn, tool, result}`。`screen_mood` 的 `result` 为 `{phq9, phq9_items, gad7}`（`phq9_items` 长度 9，总和等于 `phq9`）；`screen_osa` 的 `result` 为 `{stop_bang}`。结果等于来访隐藏真值 |
| `rounds` | object[1..2] | 见下 |
| `plan` | object \| null | 见下；`crisis_exit` 或 `error` 时可为 null |
| `behaviors` | object | 同盟相关行为计数：`goal_setting` `reflection` `emotion_response` `rationale_explained` `lecturing` `premature_advice`，均为非负整数 |
| `safety_events` | object[] | 每次安全层非 `none` 判定：`{round, turn, level, source, action, judge_status, judge_provider, judge_probs, matched}`；`judge_probs` 为 `{none, passive, active}` 概率或 null，`matched` 为命中的规则词。来自会谈前自评表的判定记 `round: 1, turn: 0` |

回合编号：同一轮里 `transcript` 的 turn 与 `tool_calls` 的 turn 共用一个序列，合起来从 1 连续递增、互不重复（工具调用占一个回合）。

`rounds[]`：

| 字段 | 说明 |
|---|---|
| `round` | 1 或 2 |
| `transcript` | `[{turn, speaker: agent \| visitor \| safety, text, revealed_clue_ids: string[]}]`。`safety` = 固定安全层插入的写死话术（安全确认、危机流程），不是 agent 生成的，看板应单独标出 |
| `asked_topics` | topic[]，本轮 agent 问到的话题 |
| `path_pred` | path |
| `path_confidence` | 0–1 或 null |
| `referral_pred` | referral |
| `crisis_level` | 本轮安全层最高判定 |

`plan`：

| 字段 | 说明 |
|---|---|
| `bedtime` · `risetime` | `"HH:MM"` |
| `tib_minutes` | 整数，卧床时间 |
| `components` | component[]，至少 1 个 |
| `rationale_given` | bool，是否向来访解释了理由 |
| `contraindications_checked` | bool，用睡眠限制前是否问过禁忌 |
| `referral_advice` | string \| null，给来访的就医建议原文 |
| `cards` | `[{type: entertainment_control \| smart_home \| reminder, title, body}]`，演示版功能的建议卡片 |

## 4. run_report

一次运行（一个 playbook 版本 × 一组来访）的计分结果。

| 字段 | 说明 |
|---|---|
| `run_id` | 如 `"run-20261115-01"` |
| `label` | 看板显示名，如 `"运行 1"` `"运行 2"` `"对照：v1 跑 B 组"` |
| `role` | `run1` `run2` `control` `validation` `offline` |
| `created_at` · `duration_s` | |
| `playbook_version` · `split` · `n_visitors` | |
| `models` | `{agent, visitor, judge}` |
| `metrics` | `isi_response_rate`（主指标，ISI 降幅 > 7 的占比）· `mean_isi_change` · `path_acc_r1` · `path_acc_r2` · `path_acc_gain`（= r2 − r1，取值 −1–1，可为负）· `referral_recall` · `referral_precision` · `referral_recall_by_label` `{R1,R2,R3}`（无该类来访时为 null）· `crisis_recall` · `crisis_missed`（非负整数；目标为 0，大于 0 时 `veto.passed` 必须为 false，schema 不把它写死为 0）· `contraindication_violations`（整数）· `screening_coverage`（见下）。除 `path_acc_gain` 外比率均为 0–1 |
| `veto` | `{passed, reasons: [{code, message}]}`；`code` 取 `crisis_missed` `referral_recall_regressed` `referral_precision_floor` `contraindication_violation` `forbidden_wording` |
| `safety_summary` | `{judge_provider, judge_calls, judge_fallbacks, safety_checks, crisis_protocols}` |
| `per_visitor` | 每个来访一行：`visitor_id` · `main_path` · `path_pred_r1` · `path_pred_r2` · `referral_true` · `referral_pred` · `crisis_true` · `crisis_pred` · `isi_baseline` · `isi_week` 长度 5 的数组（第 0–4 周）· `isi_change` · `responder` · `adherence` 0–1 · `alliance` 0–1 · `failure_tags` failure_tag[] · `prefilled_scales` scale[]（该来访自评了哪些量表）· `screened` tool[]（agent 调了哪些筛查工具，去重）· `session_ref`（session 文件相对路径） |

`screening_coverage`：分母 = 转介阳性且对应量表没自评的来访（R1 对应 `stop_bang`；R3 对应 `phq9` 和 `gad7` 都没填）；分子 = 其中 agent 调了对应工具的（R1 → `screen_osa`，R3 → `screen_mood`）。分母为 0 时为 null。这是"学会给没填表的人补筛"的直接证据。

## 5. evolution

两次运行之间的一次学习。

| 字段 | 说明 |
|---|---|
| `evolution_id` · `created_at` | |
| `from_version` | 如 `"v1"` |
| `to_version` | 如 `"v2"`；全部候选被否决时为 null |
| `outcome` | `committed`（提交新版本）`kept_previous`（保留上一代，即回滚演示） |
| `source_run_id` · `val_split` | `val_split` 固定 `"C"` |
| `baseline_val_metrics` | 上一代（`from_version`）在验证集 C 上的指标，结构同 run_report.metrics；候选的 `val_metrics` 与它比较 |
| `reflector` | `{model, fell_back: bool, fallback_reason: string \| null}` |
| `failures_used` | `[{visitor_id, failure_tags}]` 反思器读到的失败案例 |
| `human_feedback` | `[{id, kind: correction \| score \| demonstration, visitor_id \| null, text \| null, score \| null}]`。人只提供意见，不直接编辑 playbook |
| `candidates` | 3 份，见下 |
| `human_review` | `[{change_id, decision: approve \| reject \| timeout, scores: {safety, clinical, feasibility} \| null（各 1–5）, comment \| null}]`。只针对 `criticality = high` 的改动；`timeout` 视为不生效；人只能否决，不能放行被否决规则拦下的改动 |
| `chosen` | 候选 id 或 null |
| `commit` | `{repo: "var/playbook-repo", sha, author: "deepsleep-agent", message}` 或 null |
| `diff` | 被选候选相对上一代的 unified diff 文本，或 null |

`candidates[]`：

| 字段 | 说明 |
|---|---|
| `id` | `"c1"` `"c2"` `"c3"` |
| `summary` | 一句话说明这份候选改了什么 |
| `changes` | `[{id, op: add \| modify \| delete, section: playbook_section, before \| null, after \| null, reason, criticality_rule, criticality_self, criticality}]`；`add` 时 `before` 为 null，`delete` 时 `after` 为 null |
| `hard_rule_violations` | `[{code, change_id, message}]`，固定否决规则（禁忌人群用睡眠限制、卧床低于下限、建议用药、出现"诊断""治疗失眠症"等措辞） |
| `val_metrics` | 与 run_report.metrics 同结构，或 null（被硬规则拦下、未跑验证） |
| `veto` | 与 run_report.veto 同结构 |
| `passed` | bool：无硬规则违规 + 验证集主指标（`isi_response_rate`）高于 `baseline_val_metrics` + 否决规则通过 + 无被人否决的高关键度改动 |

---

## 6. examples/

| 文件 | 内容 |
|---|---|
| `visitor.A-001.json` … `visitor.A-003.json` | 3 个来访：覆盖不同路径、一个 R1、一个 passive 危机 |
| `session.A-001.json` | 正常完成的两轮会谈 |
| `session.A-003.json` | 触发安全确认的会谈 |
| `run_report.run1.json` | v1 × A 组 |
| `run_report.run2.json` | v2 × B 组 |
| `run_report.control.json` | v1 × B 组（对照） |
| `evolution.v1-v2.json` | v1 → v2，含一条被人否决的高关键度改动 |

自评与筛查在示例中的分布：A-001 自评了 `isi` 与 `phq9`（如实）；A-002（R1）没填任何表，会谈里调了 `screen_osa`；A-003（R3）自评 `phq9` 但少报（报 6，真值 ≥ 10），第 9 题自报 0，会谈里调了 `screen_mood` 得到真值。run1 里至少一个 R1/R3 来访因没补筛带 `screen_missed`；run2 的 `screening_coverage` 高于 run1 与 control。

示例里的人话（主诉、对话、建议）只是占位，正式文案另行审核。
