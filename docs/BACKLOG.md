# BACKLOG：已有共识、尚未开发的事项

> **给所有 AI 会话**：开工前先扫一眼本文件，确认你要做的事有没有已定的约定。
> 新的共识一旦形成就写进来；做完的移到文末"已完成"，并写上日期和 PR。
> 每项写清：要做什么、为什么这样定、归到哪个 PR 或分支、前置条件、谁来做。
> 维护人：统筹同学（harness 组）。最后更新：2026-11-14 晚（集成）。

## 集成现状（2026-11-14 晚，集成总控会话）

各组件已全部合入 main 并接通：**来访生成 → 编排器（会谈 + 计分 + 进化）→ 后端只读接口 → 前端控制台**。

| 环节 | 现状 | PR |
|---|---|---|
| 来访 | `data/visitors/{A,B,C,offline}` 45/45/30/30，`python -m sim.generate`（确定性，模板占位，待数据科学同学替换）；另有进化实测用临时集 `data/visitors/interim/` | #34 #36 #35 |
| 编排 | `python -m engine.demo reset / run1 / learn / run2 / all`；`make demo-run1`（运行 1 + 学习）、`make demo-run2`（运行 2 + 对照）、`make demo-mock`（零 API）；状态写 `var/demo/experiment.json`；读仓库根 `.env` | #33 #37 |
| playbook 版本 | 初始版本 v1，agent 第一代 v2（`reset_to_v0` 保留为别名） | #31 |
| 学习进度 | `var/evolve/<id>/status.json`（反思 / 候选验证 / 审核倒计时 / 提交） | #29 |
| 后端 | `API_DATA_SOURCE=files`（默认）只读 `var/`；`/runs`、`/demo/experiment`、`/evolutions*`、`/playbook/*`、`/runs/{id}/evidence`；`POST /runs` → 501 `RUNS_VIA_CLI`；`API_SERVE_WEB=1` 同源托管 `web/dist`。规格见 `api/READ_API.md` | #38 |
| 前端 | 默认 http；运行列表读后端；「当前实验」卡 + 三方对比；进化页读真实进化、进度与版本 diff | #39 |
| 家居 / 日程 | 只做 mock 展示，不进会谈（团队 11/14 定）；直传文件已移到 `mocks/user_context/` | #32 |

**路演启动（操作员机器）**：`cd web && npm run build`，然后 `API_DATA_SOURCE=files API_SERVE_WEB=1 .venv/bin/python -m uvicorn api.main:app --host 0.0.0.0 --port 8000`（单进程，不 --reload），浏览器开 `http://<IP>:8000/`；终端执行 `make demo-run1`、`make demo-run2`。

**集成遗留**

| # | 事项 | 状态 |
|---|---|---|
| IN1 | 单次运行耗时远超 AGENTS §2「约 1 分钟」：会谈数 = N_A + 2·N_B + (1+K)·N_C；5/5/5 真实彩排运行 1 约 2 分钟、反思器 gpt-6-astra xhigh 数分钟。需定现场规模 | 待统筹定 |
| IN2 | 新增前端界面文字约 80 条（#39 PR 描述）未走 B 节文案流程 | 待复核 |
| IN3 | 实验清单没写计划人数，`/runs/{id}` 的 `progress.total` 为 null | 小改，编排器 |
| IN4 | AGENTS §3 第 8 条写反思器 Opus 5.5，main 已改为 OpenAI gpt-6-astra（#30），文档未同步 | 待统筹确认后改 AGENTS |
| IN5 | 进化后台 devconsole（`docs/handoff-admin-dashboard.md`，另一会话）可直接复用 #38 的只读接口，不必另做 B1/B2 | 通知对应会话 |

## 并行开发计划（统筹会话 11/14 10:00 定）

工作模式：统筹会话只做总控。每个能并行的 PR 各开一个 Opus（medium）会话，会话内按规则调用 Codex（执行、测试、后端）和 Sonnet（用户可见文案）。Opus 会话可以自行审核、验收；只有关键判断才提交给心理学同学：临床或安全判据、用户可见文案、契约改动、push 或合并。

| 会话 / 分支 | 范围 | 基于 | 依赖与冲突 |
|---|---|---|---|
| S1 判断器对比（A2/A4） | 代码、数据、话术已在 PR #6 完成。剩下：在 `.env` 配好各家 key、准备好 VPN 后，跑五家真实对比；整理结果，交心理学同学拍板判断器选择与阈值，冻结后开小 PR | `zhq/domain-safety` 合并后的 main | 需要 key；不阻塞 S2–S4（S3 可先用 mock 判断器） |
| S2 `zhq/sim-scoring-min` | 最小版来访生成：按 `domain/path_clues.md` 每条路径 3–4 个手写来访，共 15–20 个，含自评、history、R1–R3；模拟来访（ds flash，分层线索，deny_first）+ mock；简易 4 周状态模型（`sim/params.yaml`，标明是占位）；计分产出 run_report；`make smoke` 用 10 个来访 + mock LLM；`docs/handoff-algo.md` | main | 只依赖契约；session 结构以契约示例为准 |
| S3 `zhq/engine-session` | 会谈循环：两轮对话、每轮判路径和转介、处方；`engine/playbook_v1.md`（章节对应 playbook_section，不写何时筛查）；ds flash 客户端；接安全层（每条来访发言过安全层；history_check 注入与兜底；passive 插安全确认；active 走 crisis_exit）；筛查工具；回合上限；40–50 路并发；产出 session JSON | `zhq/domain-safety` | 依赖安全层接口；跑端到端需要 S2 的来访和计分 |
| S4 `zhq/engine-evolve` | 反思器（Opus 5.5，失败降级 ds flash）→ 3 份增量候选（按章节标关键度）→ 硬规则（`domain/vetoes.py`）→ 验证集 C 门禁（`baseline_val_metrics`）→ 人类审核只能否决 → `var/playbook-repo` 独立 git、一键重置 v1 → evolution JSON。批注环节（C1）等主循环跑通后再做 | `zhq/domain-safety` | 先对着契约示例和 mock 开发；端到端需要 S2 和 S3 |

共享文件（`Makefile`、`requirements.txt`）只做最小追加，合并时以 rebase 解决冲突。PR #1 已于 11/14 合并，新分支一律基于 main。

## A. 安全层（`safety/`）

| # | 事项 | 约定与理由 | 归属 | 前置条件 |
|---|---|---|---|---|
| A1 | **history_check：过去已结束的风险念头要核验** | 来访谈论过去且已结束、但曾落入风险区的念头、自伤或尝试时，不升级 `crisis_level`（仍为 none）。引擎把核验指令注入 agent 的下一回合，要求 agent 下一句话的目的涵盖核验，例如"我想确认一下，现在你已经没有这种念头了吗？"。agent 没有核验时，安全层补一句固定话术；来访的回答照常过安全层。判断器从三选一改为四选一：none / history / passive / active。**心理学同学 11/14 定**，取代"过去已结束 = none" | 契约写进 PR #1 补丁 2；实现在 `zhq/domain-safety`；注入和核验检测在 `engine/` 会谈循环 | 契约补丁 2（已完成，已推送到 PR #1）；安全层四选一判断器、核验检测已在 `zhq/domain-safety` 本地实现；**引擎侧注入与兜底待做** |
| A2 | 判断器对比：ds flash、Jev、Gemini Decision 1、StartLux-Decision（原点星辉） | ds flash 用 JSON 结构化输出，**够用就优先选它**（国内服务，不依赖 VPN）。Jev 和 Gemini 走心理学同学的美国 VPN，要看延迟能否满足要求。StartLux 的 AutoThink 较慢，超时单独设为 8 秒，按实测冻结；它的权重只能非商用。对比工具是 `python -m safety.eval --provider rules|ds_flash|jev|gemini_decision|startlux` | `zhq/domain-safety` | 测试集定稿（A3）；`.env` 里有 `DS_*`、`TYPESAFE_API_KEY`、`GEMINI_API_KEY`、`STARTLUX_API_KEY` |
| A3 | 用审定后的草稿替换占位数据 | 把 `ds-clinical` 里的词表、测试集换进 `safety/lexicon.yaml` 和 `safety/testset.jsonl`；判断器 prompt 按审定口径同步修改 | `zhq/domain-safety` | 心理学同学审完 `docs/review-queue.md` |
| A4 | 冻结阈值 `tau_flag` / `tau_active` 和判断器选择 | 根据 A2 的结果，由心理学同学拍板召回与误报的取舍，演示前冻结 | `zhq/domain-safety` | A2 |
| A5 | 判断器要对所有发言运行，不能只在命中模糊词时调用 | 草稿手算显示，只靠规则会漏掉 7/24 条阳性：语序变体、不含死亡词的计划、"傻事"这类指代 | 已是现有规格，保持 | — |
| A6 | 不得拿测试集反复调 prompt | 调过 prompt 后，测试集就失去独立性。最终评估要另写一份留出集，最好由另一个人写 | `zhq/domain-safety` | — |
| A7 | **判断器方案已定（心理学同学 11/14 午）** | 四家真实对比见 `docs/judge-comparison-2026-11-14.md`（只算开发集结果）。主判断器 ds flash（active 10/10、无 VPN），**同步等结果**，超时 6 秒；超时或报错立刻切 Jev（p95 1.1s，history 3/3）；Jev 也失败走规则兜底。不采用"后台判断、晚一回合"，也不采用"只在会后判一次"：active 要当场介入，history_check 要求下一句核验。阈值 `tau_flag`/`tau_active` 仍待留出集（A6）后冻结 | `zhq/domain-safety`（PR #6）：判断器链已实现（8851901，295 测试通过）；真实链在开发集上召回 24/24、精确率 1.00、四类全对，p95 4.9s。待推送 | — |
| A8 | 会后整体复判 / 判断器带上下文 | 单句判断器看不到跨回合累积的暗示。会后对整场对话复判一次，用于计分审计和第二轮记忆，不替代实时判断；或给实时判断器带最近 2–3 回合上下文 | 主循环跑通后再定 | 主循环 |

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
| C3 | playbook v1 的章节严格对应契约 `playbook_section` | communication_style / questioning_strategy / path_discrimination / plan_rules / referral_rules。v1 只说"有筛查工具可用"，**不说什么时候用**，给进化留空间 | `engine/playbook_v1.md` | — |
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
- **已同意**：session 新增 `path_probs`（每回合和最终的 P1–P5 权重向量），并进 v0.1.1（心理学同学 11/14 午定）。S3 先写进 trace，不改 `contracts/`。
- 建议（未定）：审核超时时 `validate.py` 要求 `passed=false`，与"超时视为不生效即放行"冲突，建议只对 reject 检查（S4 报告）；已插过 safety_check 后再判 passive 时 action 只能是 none，但 schema 不允许，且与 PHQ-9 第 9 题事件要求冲突（S3 报告）；`veto.reasons.code` 加 `hard_rule`（S4 报告）。

## F. 路演素材（朱贺恺）

- 睡眠与自杀：Pigeon 2012，RR 2.79，控制抑郁后约 1.9；Türkmen 2026（Nature Mental Health），CBT-I 治疗结束时自杀意念严重度降低，均数比 0.77。出处见 `research/1114/2-sleep-suicide.md`。
- 竞品空白：Sleepio 明确声明不提供危机支持；Somryst 写明不用于紧急情况。
- 安全线叙事："进化过程中安全线始终不动"，v1 和 v2 的危机召回保持不变。

## G. 契约 v0.1.1 修复（PR #1 验收遗留）

验收结论：契约本身可用，`make contracts` 通过；但校验器有漏检、示例引用不完整，且缺少 temperature 与状态模型版本的记录。逐项修复清单、验证方法和验收标准见 [`docs/reviews/pr1-contracts-fixes.md`](reviews/pr1-contracts-fixes.md)，完整证据见 [`docs/reviews/pr1-contracts-codex-report.md`](reviews/pr1-contracts-codex-report.md)。PR #1 已作为 v0.1.0 合入 main；已有字段保持稳定，F07、F08、F16 会新增或收紧字段，依赖方在 v0.1.1 合入时同步。修复走独立分支和 `[contract]` PR，复验后合并。

**状态（2026-11-14，统筹同学说"不着急改，先记下"）**：修复已由 Codex 做完并经验收会话独立复验，做成本地分支 `zhq/contracts-v0.1.1`（提交 `1ef9c1b`，只在统筹同学本机 `deepsleep` 仓库里，**未 push、未开 PR**）。`make contracts` 全绿，55 项测试（1 项预期失败 M23），验收会话手工变异 11 项全部符合预期。要推送前先定下面四件事：

| # | 待定事项 | 说明 | 谁定 |
|---|---|---|---|
| G1 | `schema_version` 升级方式 | 该分支把 `models.temperature`（session 与 run_report）和 run_report 的 `state_model` 设为**必填**，这是对 v0.1.0 的不兼容变更，但 `schema_version` 仍是 `"0.1.0"`、README 标题也没改。建议升到 `0.2.0`（备选 `0.1.1`）；`engine/` `sim/` 还没写，现在改成本最低 | 统筹同学 |
| G2 | F06 精确率下限数值 | 目前只在 README 标"下限待定"，M23 为预期失败；数值定了才能在门禁里执行，并决定"无预测阳性时 precision=null"怎么处理、门禁规则字段与版本号怎么放 | 统筹同学 + 朱贺恺 |
| G3 | F07/F08/F16 字段名确认 | `models.temperature{agent,visitor}`、`state_model{version,params_digest}`、版本号 `^v\d+$`、sha 为 40/64 位十六进制、`hard_rule_violations.code` 复用 veto code 枚举。按 AGENTS.md 7.3 要通知前端组与数据科学同学 | 数据科学同学 + 前端组 |
| G4 | F17 状态示例未做 | 没有 `crisis_exit`、`error`、active 危机流程、`kept_previous`、反思器回退（`fell_back=true`）的示例，前端暂时无法对着示例开发这些状态 | 修复分支之后补 |

另：该分支一并新增了 34 个占位示例（13 个 visitor、21 个 session），用来让 `run_report.session_ref` 全部指向存在的文件；这些是合成占位，不是临床内容。

## J. 评审遗留清单（2026-11-14 批次 2：PR #6–#10）

验收会话审完 #6、#7、#8、#9、#10、#12：#8、#10、#7、#6 已合并；#9 待修；#12（design 原型）审完待作者修，不建议原样合并。**修之前先读对应清单**，每份清单有问题、证据、要求和验收标准。

| PR | 状态 | 清单 | 要点 |
|---|---|---|---|
| [#6](https://github.com/zhangheqing11/deepsleep/pull/6) 危机安全层 | **已合并**（`ac6322d`） | [`pr6-safety-fixes.md`](reviews/pr6-safety-fixes.md) | 以另一会话的修复版本合入，心理学同学确认（含 S7 的降级交判断器做法、`history_check` 话术去掉"念头，或者"中的一个逗号）。合并后 main 上验收：505 项测试通过，`make smoke` 通过，S1/S2/S4/S6 独立探针全过。剩余缺口见下
| [#9](https://github.com/zhangheqing11/deepsleep/pull/9) 资源清单 | **待修后再合** | [`pr9-resources-fixes.md`](reviews/pr9-resources-fixes.md) | 移到 `docs/`、§8.2 与已合并契约冲突、Hill 表被误用、十余处事实更正 |
| [#7](https://github.com/zhangheqing11/deepsleep/pull/7) 临床内容 | 已合并 | [`pr7-pr10-followups.md`](reviews/pr7-pr10-followups.md) A 节 | 文档承诺的硬否决规则 V3–V6、V9、F2–F6 等在 #6 里没有实现，需 `zhq/domain-vetoes-v2` |
| [#10](https://github.com/zhangheqing11/deepsleep/pull/10) 后端 Mock | 已合并 | 同上 B 节 | `mocks/fixtures.py:17` 写死 `schema_version == "0.1.0"`，契约升版本的 PR 必须同步改（G1） |
| [#8](https://github.com/zhangheqing11/deepsleep/pull/8) 并行计划 | 已合并 | — | — |

另外登记两项：
- **S3 engine-session 会话的验收项**：`history_check` 自动补话术、`speaker=safety`、来访回答再过安全层的**端到端测试**（#6 只有接口约定，没有端到端证据）。
- **`zhq/domain-vetoes-v2`**：实现 #7 描述的未落地硬否决规则，先定 V3–V6 的输入接口（询问记录、OSA 筛查结果、最终 R1 预测）。

**PR #6 合并后的剩余缺口（低风险，不挡演示，择机处理）**：
- **L1 核验检测漏识别**：agent 问"你最近还有想死的念头吗？"这类真实核验问句，`check_verification` 判为未核验，系统会多补一次固定话术。方向是安全的（多问一次），但会让会谈显得重复。
- **L2 英文禁用词多空白**：`we will  treat   insomnia`（词间多个空格）没被 W8 拦住，因为 W8 的英文部分对空白数量敏感。中文变体和繁简、全角空格拆字都已拦住。
- **L3 话术与审定原文差一个逗号**：main 上 `history_check` 为"……还有没有这样的念头或者伤害自己的行为？"，审定原文是"……念头，或者……"。这是为了让固定话术本身通过子句级核验检测而做的改动，心理学同学已确认没问题；记在这里以便日后对照。
- **S11**（history_check 自动补话术、`speaker=safety`、来访回答再过安全层的端到端测试）和 **S12**（`zhq/domain-vetoes-v2`，实现 V3–V6、V9、F2–F6、T3、S1）仍未做。
- 分支 `zhq/domain-safety-review-fixes` 是验收会话做的一份等价修复，已不需要，可以删除。

## H. 仓库与流程

- 私有免费仓库开不了分支保护，main 只能靠大家自觉不直接 push。
- 心理学同学之前写的开题调研文档放在主目录根下，还没入库。要入库的话，放到 `docs/research/`。

## I. 架构：三环（参照 TheraMind，心理学同学 11/14 午定）

参照 Hu et al. 2026（TheraMind，WWW '26，arXiv 2510.25758）的双环架构，扩展为三环。TheraMind 的 cross-session 只在同一病人的多次会谈之间调整疗法，没有跨病人学习；第三环是我们的贡献。叙事："感知层冻结，策略层进化"。

| 环 | 范围 | 内容 | 归属 |
|---|---|---|---|
| 环 1 会谈内 | 每回合 | 四个子智能体，各自独立 harness：① `PathClassifier`（替代 reaction classifier 的领域特化版）每回合输出 P1–P5 权重 + attitude（合作/抗拒，保留原版维度）+ uncertainty，run1 前冻结；② 策略生成（不确定时选区分度最高的问题，抗拒时转支持性策略）；③ 回复生成；④ 记忆更新（每轮结束一次） | S3 |
| 环 2 跨会谈 | 同一来访 第一轮 → 第二轮 | 评估第一轮处方在 4 周模拟中的效果，再决定沿用或调整（TheraMind 的 f_eval / f_select） | S3 |
| 环 3 跨来访进化 | run1 → run2 | 反思器多维评估（路径、转介、筛查、处方与否决、抗拒处理；安全只做红线）→ 增量改 playbook；章节对应子智能体：`questioning_strategy`/`path_discrimination` → 策略，`communication_style` → 回复，`plan_rules`/`referral_rules` → 环 2 | S4 |

| # | 事项 | 约定 | 状态 |
|---|---|---|---|
| I1 | 路径集合 | 沿用 P1–P5，最终 `path_pred` 仍为单一主路径，权重向量另记 | Codex 在核对文献分型与 P1–P5 是否对齐（`research/1114/7-insomnia-paths.md`），有出入再议 |
| I2 | 子智能体分开调用的延迟 | 每次调用记录延迟，留"策略 + 回复合并为一次调用"的开关；主循环跑通后用模拟测试，结合路演要求决定 | 待测 |
| I3 | 路径分类器选型 | 接口可插拔（ds flash / Jev / Gemini / StartLux / mock）。测评集用 S2 对话按回合截前缀，独立生成器防泄漏；指标：逐回合准确率与熵曲线、线索敏感度、校准度（Brier）、延迟。最好的一家进主循环并冻结 | 等 S2 对话；另开会话 |
| I4 | 微调小模型（S5） | **已决定不做**（心理学同学与数据科学同学 11/14 下午定）：用自己的模拟数据训练和测试，容易被追问泄漏；本地模型赢不了 API 就没有讲点；run1 前冻结的时间风险大。路径分类器继续用 API（按 I3 对比结果选 ds flash 或 Jev） | 已定 |
| I6 | 本地脱敏层（`privacy/`） | 放在来访每条输入之后、任何云端 API 调用之前，替换可识别信息；临床信息（钟点、时长、症状、用药、自伤表述）不改。路线与调研见 `research/1114/8-zh-deid.md`。S3 之后只需在调用 API 前接一个钩子 | **数据科学同学负责**，不归 harness 组；待定：契约存原文还是脱敏文本、是否加"已脱敏"标记 |
| I5 | 进化证据 | 分类器冻结，进步应体现为 agent 问出更多关键线索：逐回合正确路径权重 / 熵曲线、关键线索出现回合，进 evolution 报告；"一阶导 / 二阶导"等主循环跑通后测 | S4 |

## 已完成

| 日期 | 事项 | PR |
|---|---|---|
| 2026-11-14 | 共享待办 BACKLOG | [PR #2](https://github.com/zhangheqing11/deepsleep/pull/2) |
| 2026-11-14 | 契约 v0.1.0（schema + 示例 + 校验器） | [PR #1](https://github.com/zhangheqing11/deepsleep/pull/1) |
| 2026-11-14 | 并行开发计划 | [PR #8](https://github.com/zhangheqing11/deepsleep/pull/8) |
| 2026-11-14 | 后端 Mock 联调接口 | [PR #10](https://github.com/zhangheqing11/deepsleep/pull/10) |
| 2026-11-14 | 临床内容定稿 | [PR #7](https://github.com/zhangheqing11/deepsleep/pull/7) |
| 2026-11-14 | 前后端分工更新（崔秀净后端、王译旋前端并行） | [PR #3](https://github.com/zhangheqing11/deepsleep/pull/3) |
| 2026-11-14 | 临床内容定稿（线索表、处方否决、转介判据、审核结论） | [PR #7](https://github.com/zhangheqing11/deepsleep/pull/7) |
| 2026-11-14 | 并行开发计划（S1–S4） | [PR #8](https://github.com/zhangheqing11/deepsleep/pull/8) |
