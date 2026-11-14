# engine/ — 会谈循环（S3）

产出符合 `contracts/session.schema.json` 的会谈记录。反思、门禁、版本库在 S4（`zhq/engine-evolve`）。

```bash
.venv/bin/python -m engine.run --mock                       # 契约示例 3 个来访 + mock agent + mock 来访
.venv/bin/python -m engine.run --visitors data/visitors/A --sim sim.xxx:make_sim --screening sim.xxx:make_screening
```

输出 `var/runs/<run_id>/sessions/<visitor_id>.json`（契约）和 `trace/<visitor_id>.json`（调试用，不是契约：
LLM 已解析输出、重试、否决记录、history 核验结果、被丢弃的 action=none 安全事件、推测调用命中数）。

## 架构（按 TheraMind 第 3 节改造，心理学同学 11/14 拍板）

**环 1 会谈内（每个 agent 动作）**，四个子智能体，各自独立 prompt（`prompts/`）与 harness：

| 子智能体 | 调用时机 | 读的 playbook 章节 | 输出 |
|---|---|---|---|
| `PathClassifier`（`classifier.py`，冻结，不进化） | 每个动作前，对累计对话 | 无（固定 prompt） | `weights{P1..P5}`、`attitude`、`uncertainty`、`margin` |
| 策略生成（`prompts/strategy.md`） | 每个动作 | questioning_strategy、path_discrimination | say / tool / end_round + 策略（type、target_topic、contrast、revisit_later、intent） |
| 回复生成（`prompts/response.md`） | 策略为 say 时 | communication_style | text + acts |
| 记忆更新（`prompts/memory.md`） | 每轮结束一次 | referral_rules | 摘要、事实、待问问题、**转介判断** |

- `uncertainty` = 权重的归一化香农熵 H(w)/ln 5（0 = 全部集中在一条路径，1 = 均匀）；另记 `margin` = 第一名减第二名。
- 分类器失败或超时（`path_classifier.timeout_s` = 6）→ 均匀权重、`status` 记 error/timeout，会谈继续。
- 分类器可插拔：`ds_flash`（JSON 输出）、`jev`（TypeSafe 两道 Choice 题）、`mock`；接口只吃对话条目、返回 `PathState`，之后的微调小模型实现同一个 `classify(dialogue)` 即可。Gemini Decision / StartLux 尚未实现，可照 `safety/judges.py` 写。
- 策略原则（冻结在 `strategy.md`）：路径不确定时选区分度最高的问题；attitude = resistant 时改支持性策略并记 `revisit_later`，合作后回到这些话题；有【安全层指令】时策略必须是 verify_safety。具体鉴别问法放 playbook（可进化），v1 只写了 PC-3 一条。
- `pipeline.merge_strategy_response: true` 把策略与回复合并成一次调用（`prompts/turn_merged.md`），用于比较延迟；`--merged` 命令行开关同效。
- 最终 `path_pred` = 本轮结束时分类器权重的 argmax，`path_confidence` = 其权重；`referral_pred` 来自记忆更新。

**环 2 跨会谈**：第 1 轮结束出**试行处方**并讲给来访；第 2 轮开头 f_eval = `PlanOutcomeModel.simulate`（S2 的 4 周状态模型，现为 `stubs.StubOutcomeModel` 占位），f_select = `prompts/select.md`（maintain / adjust，读 plan_rules、referral_rules）。结果与决定写进第 2 轮所有子智能体的上下文，第 2 轮结束出最终处方（契约 `plan`）。

## trace 文件（`trace/<visitor_id>.json`，不是契约）

| 字段 | 内容 |
|---|---|
| `path_probs` | **待 v0.1.1 接入 session JSON**。每个已采用动作一条 `{round, turn, final: false, weights{P1..P5}, attitude, uncertainty, margin, status, provider, latency_ms}`（turn = 被分类的最后一条来访发言）；每轮结束一条 `final: true`（即 path_pred 的来源） |
| `latency_ms` | 每个子智能体 `{n, total, mean, p95}`：classifier / strategy / response（或 turn）/ memory / plan / select |
| `llm_calls` | 每次调用的子智能体、尝试次数、成功与否、原始输出、耗时 |
| `strategies` | 每步策略 |
| `plans` `{"1", "2"}` · `round1_outcome` · `selection` · `memory` | 环 2 的输入输出 |
| `history_checks` · `vetoes` · `ignored_events` · `speculation` | 安全核验、否决、被丢弃的 action=none 事件、推测执行命中/丢弃数 |

## 文件

| 文件 | 内容 |
|---|---|
| `config.yaml` | **冻结配置**：agent 模型参数（temperature 0 等）、`path_classifier`、`pipeline`、每轮回合上限 `round_turn_cap`（C4）、并发 ≤ 50、否决重写次数 |
| `playbook_v1.md` | 五个章节严格对应 `playbook_section`；只写"有筛查工具可用"，不写何时用（C3） |
| `prompts/` | `boundaries.md`（冻结边界，所有子智能体共用）+ 各子智能体 prompt + `path_classifier.md` |
| `session.py` | 双环会谈循环 + 安全层集成 + 处方否决 |
| `classifier.py` · `mock_agent.py` · `llm.py` | 路径分类器；离线 mock 策略；ds flash 客户端（与分类器共用一个在途请求上限） |
| `run.py` | 批量并发与 CLI（`--mock` `--merged` `--sim` `--screening` `--outcome`） |
| `interfaces.py` · `stubs.py` | 与 sim/ 的接口（VisitorSim、ScreeningProvider、PlanOutcomeModel）与占位实现 |
| `topics.py` | 冻结的关键词话题标注（sim 不报告话题时兜底） |

## 安全层集成

- 每条来访发言（含开场、对安全话术的回答、对收尾消息的回答）过 `SafetyLayer.assess_text`，**同步等结果**；等待期间推测执行下一步的整条环 1 流水线（快照固定在判定前），安全层返回任何事件就丢弃。判断器链（ds flash 6 s → Jev → 规则兜底）在 `safety/` 配置里，引擎只调用 `SafetyLayer()`。
- passive → `safety_check` 话术；active → `crisis_protocol`，`status = crisis_exit`，不出处方；history → 【安全层指令】注入下一条发言的策略与回复两个子智能体 → `check_verification` → 未核验插 `history_check` 兜底 → 清 pending；本轮结束仍 pending 则插兜底。
- PHQ-9 第 9 题：自评（round 1 turn 0）与 `screen_mood` 结果都走 `assess_phq9_item9`。
- **问卷阳性 + 口头未透露风险的再核验（2026-11-14 心理学同学审定）**：本场出现 `source=scale_item9`，且普通安全确认后的来访发言没有 passive/active 新事件时，第一轮动作预算耗尽或提前结束后、生成处方及收尾消息前插入固定 `scale_recheck`，speaker 为 `safety`。每场最多一次，不占动作预算；已 active / `crisis_exit` 不触发。回答照常过安全层，active 则立即退出、不出处方。文本重复 passive 的本地 action `none` 也会阻止再核验；重复量表阳性不会重置或重复触发。再核验回答触发的 history 继续由既有兜底核验处理。
  这条规则冻结在会谈代码和 `safety/scripts.yaml`，不进入 playbook 或进化候选。session 安全事件沿用 `safety_check`，trace 的 `scale_rechecks` 记录 `recheck: true`、`counts_toward_cap: false`、原量表事件和再核验事件索引（均为零起始）。`engine/topics.py` 按实际说出的审定问句识别 `self_harm`，供 S2 分层线索回复使用。
  离线回归：`python -m pytest -q tests/test_engine_scale_recheck.py`。其中 sample-010 使用原始 S2 来访和 deny_first 流程，并为其方法表述注入 mock active 判定；默认 MockJudge 的关键词表会把该句判为 passive。这项测试验证再核验及危机退出链路，不代表真实判断器识别能力；真实判据和 mock 默认配置均未修改。
- 处方：`check_plan` + 收尾消息/就医建议/卡片的 `check_text`；硬否决重写 1 次，仍不过走冻结兜底（去 sleep_restriction、卧床抬到下限）。`contraindications_checked` 只在问过 `health_conditions` 时为 true。
- 并发：`concurrency.max_sessions` = 50；引擎自己的 ds flash 请求（子智能体 + 分类器）共用 `agent_llm.max_inflight` = 32 的上限（实测 ds flash 48 路无报错、96 路有报错；判断器与模拟来访另算）。

## 与 S2 对接

`engine/interfaces.py` 的 docstring 是接口说明。S2 提供 `module:factory` 两个工厂即可通过 `--sim` / `--screening` 接入；
筛查结果必须等于 `visitor.indices`，`phq9_items[8] == visitor.crisis.phq9_item9`（`contracts/validate.py` 会检查）。

`PlanOutcomeModel.simulate(visitor, plan, context)` 返回 `{isi_week[5], isi_change, adherence, responder}`（可附加字段）；
引擎同时把它放进 `memory["round1_outcome"]`，模拟来访第 2 轮可据此讲这 4 周的情况。

## S3 fix1：真实输出、降级与统计口径（2026-11-14）

- JSON 模式原本已启用。真实 deepseek-flash 在 800 token 上限下返回 `finish_reason=length`；推理 token 也消耗这一上限。现在按子智能体设置上限（plan 3200，strategy 1600，turn 2200，response/select 1200，memory 1800），先剥离完整 JSON 围栏再解析。
- `length` 不接受部分结果，即使部分结果可以解析；只用两倍上限重试一次。重试仍失败就降级，不再启动另一串解析重试。其他请求/结构错误仍遵循冻结的 `max_retries`。
- 所有子智能体耗尽尝试后使用现有确定性 mock policy 作为固定回退；plan 回退不包含 sleep_restriction，仍经过原处方否决检查。memory 回退不伪造摘要，并保留上一轮已识别的转介。回退记录位于 trace.fallbacks；实际采用的回退任务也标在 session.models.agent 的 `(fallback:...)` 后缀。这里的 completed 表示流程完成，不表示模型全程成功。
- trace.llm_calls 在调用开始时落记录，包含失败/取消/被丢弃的推测调用。`finish_reason`、`truncated`、`max_tokens`、usage 由 agent/classifier 的 OpenAI 响应采集。未收到响应或 mock 时原因是 null；不推断为 stop。`request_started` 区别已发起请求与等待并发额度时取消的调用，逻辑调用数不等于服务商账单。安全判断器的所有尝试（含 none 和 fallback 前失败）取自 `all_judge_results`，不再从 safety_events 反推数量；安全层 API 未提供 finish_reason，S3 不臆造该字段。
- 推测调用直接写本会谈 trace，按 scope 标记 discarded，取消后 await 清理；分类缓存不再重复计入调用/延迟。
- 最终分类超时/错误仍保留均匀权重和原状态用于诊断，但 path_pred 沿用本会谈最近成功分类。没有成功结果时 trace 的 final.path_pred=unknown、unknown_path_rounds 标记该轮。契约不能写 unknown，所以 session 保留兼容占位 P1、path_confidence=null，不能把它作为有效分类。
- `engine.reporting.build_report` 是 S3 → S2 scorer 的统计入口：排除 error 和 unknown 会谈后才调用 scorer；n_visitors 是可评分人数。完整 attempted/completed/error/crisis_exit、完成率、评分覆盖率、排除名单、全样本危机漏报和所有调用统计写进必须一同读取的 summary。任何排除都会令 report.veto.passed=false（契约没有“评估不完整”原因枚举，原因写在 summary）。全部排除时不生成无定义的空样本 report；summary.report_unavailable 说明原因。原始 S2 score_run 直接接 session 的旧入口不会自动获得这些修复，应改接此适配函数。
- 批量 CLI 总是写 summary.json；S2 可导入时加 `--scorer scoring.score:score_run` 生成报表。安全摘要覆盖全部尝试，即使某些会谈未进入可评分子集。
- `engine.adapters_sim` 是可选 S2 薄适配：每会谈独立 simulator、跨轮保留 deny/reveal，按实际 agent/safety 发言标话题，环 2 只把第一轮交给 S2 状态模型。S2 已接入本分支；模块保持延迟导入，方便独立测试。
- 安全事件优先调用新版 `script_for_event(event, state)`，空话术不添加空 transcript、不额外触发来访回复；事件仍保留。旧安全层兼容路径显式记 legacy_safety_api，不能据此宣称完成新版去重集成。

真实验收采用 3 个 S2 来访、每轮 1 次动作、merged agent 为真实 ds flash，其余组件 mock，满足总共不超过 30 次真实请求的限制。它验证 JSON 与会谈执行，不替代默认 5/4 动作、全真实服务或 40–50 人并发验收。完整产物不提交到仓库，见本地 `var/s3-fix1/` 与外部任务总结。

## S3 第二阶段：冻结筛查与低延迟配置

- 第一轮前两个 agent 动作内未主动 `screen_mood`，则在第二个动作后强制调用；提前 `end_round` 也会在收尾前补筛。已进入 `crisis_exit` 的会谈不再继续筛查。强制调用不消耗动作预算；playbook 不变。session.tool_calls 保留正常结果，trace.forced_tool_calls 通过 round/turn/tool_call_index 标明来源（契约不允许增加字段）。
- PHQ-9 第 9 题阳性事件均写入 session.safety_events；重复阳性可以有多个事件，但固定话术是否播报仍交给安全层的 `script_for_event` 去重。
- 默认动作上限 4/3；策略与回复合并；第一轮 memory 与 plan 合并为 `memory_plan`，第二轮读取其记忆与转介。该调用与 plan 保留 high 思考，其他 agent 子任务关闭思考。参数使用 DeepSeek 官方 Chat Completions 的 `extra_body.thinking` 和 `reasoning_effort`。
- 默认路径分类器 Jev，两道 Choice 同一次请求，复用客户端；失败自动尝试真实 ds flash。Jev 不可用时，后续隔一个动作复用分类结果，轮末刷新。失败双方均不能制造成功分类；unknown/错误排除口径仍由 engine.reporting 负责。危机判断器链及超时、阈值不变。
- 用户可见文字经过 `check_text(context="user_facing")`；一次改写仍硬违规则删除整句，trace.vetoes 记录 text_redacted。普通发言、收尾话、就医建议、卡片标题和正文都覆盖。删空时不展示空消息、不凭空添加替代话术；卡片标题或正文为空则移除卡片。
- `sim/` 与 `scoring/` 已在本分支。适配器继续维护跨轮状态和仅第一轮的状态模型输入；`S2RendererClient` 只在 engine 内为真实来访措辞关闭思考，不改 S2 的线索规则。

全真实试跑（凭据只读取显式外部文件；没有 key 时拒绝试跑）：

```bash
/Users/zhangheqing/bohack/ds-safety/.venv/bin/python -m engine.integ_trial --n 3 --run-id unique-precheck
/Users/zhangheqing/bohack/ds-safety/.venv/bin/python -m engine.integ_trial --n 10 --run-id unique-ten
# 离线同一路径：加 --mock
```

每次 run-id 必须唯一，已有目录会拒绝重跑。`--config` 接受冻结配置覆盖 YAML，`--no-merged` 用于受控对照；默认全局真实请求上限 450，由 `var/s3-phase2/request-budget.log` 跨进程累计（HTTP send 前加锁预留，含失败与取消，非服务商账单）。不要删除账本来重复计费；提高 `--budget` 必须取得任务授权。

产物为 `var/integ/<run-id>/` 的 manifest、sessions、trace、calls、summary 和可评分时的 run_report。计分必须同时读 summary.accounting，error 不进入准确率分母。来源摘要标明当前工作区代码，不能把未提交的工作区等同某个 Git 提交。模拟规则模型的 ISI 结果只用于联调，不证明实际干预有效。

## 路演编排

`engine.demo` 将 A 组运行 1、C 组现场基线及候选评估、B 组运行 2 和旧版本 B 组对照连起来。
使用现有 S2 来访适配、筛查、4 周状态模型及 `build_report` / `score_run`；每场仍是两轮，危机退出除外。
运行 2 与对照并发执行，整个命令内的会谈（包括并行 C 组候选）共用 `--max-sessions` 上限。
候选未通过门禁是正常的 `kept_previous`，会用同一版本照常跑 B 组两次，不保证或伪造提升。

在当前 worktree 使用已安装的 Python，不创建环境、不安装依赖：

```bash
PYTHON=/Users/zhangheqing/bohack/deepsleep/.venv/bin/python
# 完整离线彩排，所有模型调用均为 mock，仍走真实状态模型和计分。
make demo-mock
# 同义 CLI；默认样例确定性切分为 A/B/C 各 6 人。
$PYTHON -m engine.demo all --mock --dev --visitors-dir sim/visitors --reset
# 有界彩排可加 --n-a 3 --n-b 3 --n-c 3 --max-sessions 4

# 真实模式：事先在进程环境配置提供方，不由编排器读取外部 .env。
$PYTHON -m engine.demo reset
$PYTHON -m engine.demo run1 --experiment stage-demo --n-a 40 --n-b 40 --n-c 40
$PYTHON -m engine.demo learn --experiment stage-demo
# 现场第二次运行，沿用原实验配置与来访快照。
$PYTHON -m engine.demo run2 --experiment stage-demo
# 一次性执行；--reset 仅 all 支持。
$PYTHON -m engine.demo all --reset --n-a 40 --n-b 40 --n-c 40
```

默认来访目录为 `data/visitors/{A,B,C}/`，目录缺失或组为空时明确报错；不会默默改用开发数据。
`--dev` 从指定目录按 JSON 文件名排序，以索引 `0::3 / 1::3 / 2::3` 切出互不重叠的小组；
`--n-a/--n-b/--n-c` 是各组人数上限，省略则使用整组。来访目录必须位于当前 worktree 内。
开发分组会在内存及实验快照中更新 `split`，不改源 JSON。该小样本划分只用于开发，不能当作正式同分布验证集。

`run1` / `all` 创建新实验，未给 ID 时自动生成；`learn` / `run2` 默认读取最近清单，也可指定 `--experiment`。
首次运行将模式、人数和并发选项保存在 `var/demo/<id>/options.json`，以后命令无需再传；显式传不同值会拒绝。
A/B/C 的完整数据快照存于同目录的 `cohorts.json`，运行 2 与对照读取同一份 B 组快照。
初始与学习后的 playbook 分别存 `original.md` / `learned.md`，因此对照不受后续版本库指针变化影响。
学习前会核对版本库仍是运行 1 的原文与版本。请在首次运行前冻结源码、配置、模型环境变量和 prompts，后续命令不要改动。

Makefile 提供 `demo-reset`、`demo-run1`（顺序执行 run1 + learn）、`demo-run2`、`demo-all`、`demo-mock`。
可以用 `DEMO_PYTHON=/已有环境/bin/python` 指定解释器，`DEMO_ARGS='--experiment rehearsal --n-a 3 ...'` 传选项。
这些新目标不依赖旧的 `venv` 目标，也不改已有目标行为。

真实模式必须提供 `DS_BASE_URL`、`DS_API_KEY`、`DS_MODEL`，沿用冻结配置 temperature 0。
分类器、判断器和反思器选择沿用当前引擎配置及其预置自动降级；缺少 DS 环境直接报错。
当前进化配置默认反思器为 OpenAI `gpt-6-astra`，而 AGENTS.md 的旧设计表写的是 Opus 5.5；编排器不修改这一选择。
如果团队决定用 Opus，需要在首次运行前按 [进化引擎说明](evolve/README.md) 配置并冻结。
`--mock` 明确替换 agent、分类器、判断器、来访渲染和反思器，不初始化真实客户端，即使环境中存在密钥。
mock 反思器生成三个低关键度候选，照常在 C 组评估；mock agent 不因这些措辞调整而变好，因此通常保留上一代。

产物与大屏读取约定：

- `var/demo/experiment.json` 严格保持交接清单的字段；每个阶段开始前公布 ID 与 `state=running`，通过同目录临时文件 + `os.replace` 原子替换，完成为 `done`，异常为 `stage=failed` 并带 `error`。
- 每次更新同时保存 `var/demo/experiment.<id>.json`。学习详情在 `var/evolve/<evolution_id>/{status,evolution,insights}.json`；清单中的学习 `done` 表示完成，采纳与否读取 `evolution.outcome`。
- A/B 及 C 验证批次均在 `var/runs/<run_id>/` 写 `sessions/`、`trace/`、`run_report.json`、`summary.json`。summary 增加 `execution_mode=mock|real`；`real` 仅表示启动模式，是否发生自动降级需同时读 summary 和 trace。
- 完成后打印三方指标、学习结果、最多三条采纳改动摘要、回退命令，并写 `var/demo/<id>/summary.md`。比率分母为零时显示 `N/A`。
- 评估不完整（error 或 unknown 被排除）会保留原始产物并报错，不把部分评分视为阶段成功；C 候选评估失败由既有 evolve 记录并淘汰该候选，C 基线失败则整次学习失败。
- 已完成或失败的阶段不自动重跑，避免重复调用；修复原因后使用新实验 ID。单次只允许一个操作员 demo 命令，进程锁防止覆盖清单。硬断电 / SIGKILL 无法写失败，清单会留在 `running`，需人工检查产物后开新实验。
- `reset` 调用 `PlaybookRepo.reset_to_initial` 并删除最近清单指针，保留历史清单、报告和快照；它会重建独立 playbook git 库，因此旧实验的版本标签不保证还能回滚。日常回退用 `python -m engine.evolve rollback <版本>` 保留版本历史。

完整演示的会谈数为 `N_A + 2×N_B + (1+K)×N_C`，`K` 是实际进入验证的候选数（0–3）。
A/B/C 各 40 人且三个候选都有效时，共 280 场、最多 560 轮；开发模式对应 42 场。
当前 4/3 动作上限及合并策略下，普通完整会谈约需 30–45 次模型请求（agent、分类器、来访措辞、判断器合计），
因此 280 场约 8,400–12,600 次，再加 1 次反思器、必要时 1 次降级反思器。
这是依据调用结构的粗估，不是计费上限：提前退出会减少请求，重试、判断器/分类器降级、额外安全核验和推测执行会增加请求。
本次实现只做 mock 验收，不能据此保证真实模式单次一分钟或主指标提升；高关键度候选仍有既有 120 秒审核窗口。
