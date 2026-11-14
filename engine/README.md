# engine/ — 会谈循环（S3）

产出符合 `contracts/session.schema.json` 的会谈记录。反思、门禁、版本库在 S4（`zhq/engine-evolve`）。

```bash
.venv/bin/python -m engine.run --mock                       # 契约示例 3 个来访 + mock agent + mock 来访
.venv/bin/python -m engine.run --visitors data/visitors/A --sim sim.xxx:make_sim --screening sim.xxx:make_screening
```

输出 `var/runs/<run_id>/sessions/<visitor_id>.json`（契约）和 `trace/<visitor_id>.json`（调试用，不是契约：
LLM 原始输出、重试、否决记录、history 核验结果、被丢弃的 action=none 安全事件、推测调用命中数）。

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
- 策略原则（冻结在 `strategy.md`）：路径不确定时选区分度最高的问题；attitude = resistant 时改支持性策略并记 `revisit_later`，合作后回到这些话题；有【安全层指令】时策略必须是 verify_safety。具体鉴别问法放 playbook（可进化），v0 只写了 PC-3 一条。
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
| `playbook_v0.md` | 五个章节严格对应 `playbook_section`；只写"有筛查工具可用"，不写何时用（C3） |
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
- 处方：`check_plan` + 收尾消息/就医建议/卡片的 `check_text`；硬否决重写 1 次，仍不过走冻结兜底（去 sleep_restriction、卧床抬到下限）。`contraindications_checked` 只在问过 `health_conditions` 时为 true。
- 并发：`concurrency.max_sessions` = 50；引擎自己的 ds flash 请求（子智能体 + 分类器）共用 `agent_llm.max_inflight` = 32 的上限（实测 ds flash 48 路无报错、96 路有报错；判断器与模拟来访另算）。

## 与 S2 对接

`engine/interfaces.py` 的 docstring 是接口说明。S2 提供 `module:factory` 两个工厂即可通过 `--sim` / `--screening` 接入；
筛查结果必须等于 `visitor.indices`，`phq9_items[8] == visitor.crisis.phq9_item9`（`contracts/validate.py` 会检查）。

`PlanOutcomeModel.simulate(visitor, plan, context)` 返回 `{isi_week[5], isi_change, adherence, responder}`（可附加字段）；
引擎同时把它放进 `memory["round1_outcome"]`，模拟来访第 2 轮可据此讲这 4 周的情况。
