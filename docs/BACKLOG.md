# BACKLOG：已有共识、尚未开发的事项

> **给所有 AI 会话**：开工前先扫一眼本文件，确认你要做的事有没有已定的约定。
> 新的共识一旦形成就写进来；做完的移到文末"已完成"，并写上日期和 PR。
> 每项写清：要做什么、为什么这样定、归到哪个 PR 或分支、前置条件、谁来做。
> 维护人：统筹同学（harness 组）。最后更新：2026-11-14 凌晨。

## 进行中的分支（还没合入 main）

| 分支 | 内容 | 状态 |
|---|---|---|
| `zhq/contracts-v0` | 契约 v0.1.0 | [PR #1](https://github.com/zhangheqing11/deepsleep/pull/1) 等前端组和数据科学同学 approve。补丁 2（history_check、批注字段）已推送（`79fc916`）。**验收发现校验器漏检等问题，修复清单见 [`docs/reviews/pr1-contracts-fixes.md`](reviews/pr1-contracts-fixes.md)，修完再合** |
| `zhq/domain-safety` | 安全层骨架：规则 + 判断器（ds flash / Jev / Gemini Decision / Mock），对比工具 `safety/eval.py`，处方否决 `domain/vetoes.py` | 本地提交。基于契约分支，等 PR #1 合并后 rebase 再开 PR |
| `zhq/domain-clinical-v0` | 临床草稿：线索表、危机测试集、词表、处方否决、转介判据、`docs/review-queue.md` | 本地提交。等心理学同学审定 |

## A. 安全层（`safety/`）

| # | 事项 | 约定与理由 | 归属 | 前置条件 |
|---|---|---|---|---|
| A1 | **history_check：过去已结束的风险念头要核验** | 来访谈论过去且已结束、但曾落入风险区的念头、自伤或尝试时，不升级 `crisis_level`（仍为 none）。引擎把核验指令注入 agent 的下一回合，要求 agent 下一句话的目的涵盖核验，例如"我想确认一下，现在你已经没有这种念头了吗？"。agent 没有核验时，安全层补一句固定话术；来访的回答照常过安全层。判断器从三选一改为四选一：none / history / passive / active。**心理学同学 11/14 定**，取代"过去已结束 = none" | 契约写进 PR #1 补丁 2；实现在 `zhq/domain-safety`；注入和核验检测在 `engine/` 会谈循环 | 契约补丁 2（已完成，已推送到 PR #1）；安全层四选一判断器、核验检测已在 `zhq/domain-safety` 本地实现；**引擎侧注入与兜底待做** |
| A2 | 判断器对比：ds flash、Jev、Gemini Decision 1、StartLux-Decision（原点星辉） | ds flash 用 JSON 结构化输出，**够用就优先选它**（国内服务，不依赖 VPN）。Jev 和 Gemini 走心理学同学的美国 VPN，要看延迟能否满足要求。StartLux 的 AutoThink 较慢，超时单独设为 8 秒，按实测冻结；它的权重只能非商用。对比工具是 `python -m safety.eval --provider rules|ds_flash|jev|gemini_decision|startlux` | `zhq/domain-safety` | 测试集定稿（A3）；`.env` 里有 `DS_*`、`TYPESAFE_API_KEY`、`GEMINI_API_KEY`、`STARTLUX_API_KEY` |
| A3 | 用审定后的草稿替换占位数据 | 把 `ds-clinical` 里的词表、测试集换进 `safety/lexicon.yaml` 和 `safety/testset.jsonl`；判断器 prompt 按审定口径同步修改 | `zhq/domain-safety` | 心理学同学审完 `docs/review-queue.md` |
| A4 | 冻结阈值 `tau_flag` / `tau_active` 和判断器选择 | 根据 A2 的结果，由心理学同学拍板召回与误报的取舍，演示前冻结 | `zhq/domain-safety` | A2 |
| A5 | 判断器要对所有发言运行，不能只在命中模糊词时调用 | 草稿手算显示，只靠规则会漏掉 7/24 条阳性：语序变体、不含死亡词的计划、"傻事"这类指代 | 已是现有规格，保持 | — |
| A6 | 不得拿测试集反复调 prompt | 调过 prompt 后，测试集就失去独立性。最终评估要另写一份留出集，最好由另一个人写 | `zhq/domain-safety` | — |

## B. 用户可见文案（统一流程：Sonnet 子代理起草 → 统筹会话验收 → 心理学同学审定）

| # | 文案 | 备注 |
|---|---|---|
| B1 | 安全层固定话术：`safety_check`、`crisis_protocol`、`history_check` 兜底句 | 写在 `safety/scripts.yaml`，speaker 为 `safety`。不出现"诊断"类字样 |
| B2 | 危机热线 | 候选见 `research/1114/3-hotlines.md` 和 `ds-clinical/docs/review-queue.md` 第 3 节。号码由心理学同学逐个核实后才能填 `verified: true` |
| B3 | 自评页（ISI、PHQ-9、GAD-7、可选 STOP-Bang）的题目与说明 | 前端组用；PHQ-9 第 9 题大于 0 直接进安全层 |
| B4 | 转介建议的措辞（R1 / R2 / R3 的科室说法） | `ds-clinical/domain/referral_cues.md` 第 4 节是示例 |

## C. 进化引擎（`engine/`）

| # | 事项 | 约定与理由 | 归属 | 前置条件 |
|---|---|---|---|---|
| C1 | **反思器第一步加"批注"环节（auto_critic）** | 不做成独立子智能体，而是作为反思器流程的第一步。批注 agent 用 ds flash 并行，给每个失败案例写一条带临床理由的批注，few-shot 用心理学同学写的示范。批注进看板等专家确认、驳回或改写，只有确认过的才喂给反思器。人确认有超时，超时的批注不进入。prompt 和 few-shot 赛前冻结。这样现场人的工作量从"写纠正"降到"点确认"，叙事是"专家示范，机器放大" | 字段已进契约补丁 2（`human_feedback.source/status`）；实现归 `engine-evolve` PR | 主循环跑通后再做（**18:00 决策点之前不做**）；C2 |
| C2 | 心理学同学写 3–5 条示范批注 | 不管做不做 C1，都可以直接作为反思器的 few-shot | 放进 `engine/prompts/` | — |
| C3 | playbook v0 的章节严格对应契约 `playbook_section` | communication_style / questioning_strategy / path_discrimination / plan_rules / referral_rules。v0 只说"有筛查工具可用"，**不说什么时候用**，给进化留空间 | `engine/playbook_v0.md` | — |
| C4 | 每轮回合上限是引擎的冻结配置 | 筛查工具调用也占一个回合；这个上限防止 agent 靠"全都筛"刷召回 | `engine/` | — |
| C5 | 人类审核只能否决 | 只针对 high 关键度的改动；超时视为不生效；不能放行被硬规则拦下的改动 | `engine/` gate | 契约已定 |
| C6 | 消融实验（答辩备用） | 反思器换成 ds flash 后是否仍有提升；有批注 vs 无批注 | `analysis/` | 主循环 |

## D. 模拟与计分（`sim/` `scoring/`，11/14 下午交给数据科学同学）

| # | 事项 | 约定 |
|---|---|---|
| D1 | 来访自评 | 约 40% 的来访填表，防御型倾向少报；报的分可以和真值不一致 |
| D2 | 筛查工具的结果由代码按隐藏指数生成 | 不经模拟来访 LLM |
| D3 | `visitor.crisis.history` | 要生成一些有"过去已结束风险史"的来访，用来检验 agent 是否做了核验 |
| D4 | `screening_coverage` / `screen_missed` | 按契约定义计算 |
| D5 | 交接文档 `docs/handoff-algo.md` | 数据科学同学接手前写好 |

## E. 等心理学同学审定后可能要改契约的点

来自 `ds-clinical` 各草稿的"建议新增枚举"，审定后统一走 `[contract]` 流程：
- veto code 加"卧床低于下限""用药建议"；
- failure_tag 加 `referral_wrong_type`；
- contraindication 加年龄下限；
- 一个来访能否同时有多个转介标签（RC-6）。

## F. 路演素材（朱贺恺）

- 睡眠与自杀：Pigeon 2012，RR 2.79，控制抑郁后约 1.9；Türkmen 2026（Nature Mental Health），CBT-I 治疗结束时自杀意念严重度降低，均数比 0.77。出处见 `research/1114/2-sleep-suicide.md`。
- 竞品空白：Sleepio 明确声明不提供危机支持；Somryst 写明不用于紧急情况。
- 安全线叙事："进化过程中安全线始终不动"，v1 和 v2 的危机召回保持不变。

## G. PR #1 契约验收遗留（修复清单）

验收结论：契约本身可用，`make contracts` 通过；但校验器有漏检、示例引用不完整，且缺少 temperature 与状态模型版本的记录。逐项修复清单、验证方法和验收标准见 [`docs/reviews/pr1-contracts-fixes.md`](reviews/pr1-contracts-fixes.md)，完整证据见 [`docs/reviews/pr1-contracts-codex-report.md`](reviews/pr1-contracts-codex-report.md)。修在 `zhq/contracts-v0` 分支，PR #1 修完并复验后再合。

## H. 仓库与流程

- 私有免费仓库开不了分支保护，main 只能靠大家自觉不直接 push。
- 心理学同学之前写的开题调研文档放在主目录根下，还没入库。要入库的话，放到 `docs/research/`。

## 已完成

| 日期 | 事项 | PR |
|---|---|---|
| 2026-11-14 | 共享待办 BACKLOG | [PR #2](https://github.com/zhangheqing11/deepsleep/pull/2) |
| 2026-11-14 | 前后端分工更新（崔秀净后端、王译旋前端并行） | [PR #3](https://github.com/zhangheqing11/deepsleep/pull/3) |
