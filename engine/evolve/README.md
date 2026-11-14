# engine/evolve — 环 3 跨来访进化：反思 → 硬规则 → 门禁 → 只否决审核 → playbook 版本库

三环（参照 TheraMind）：环 1 会谈内、环 2 同一来访跨轮由 S3 完成；环 3 是本模块，从一批来访的失败里改写 playbook。
感知层（PathClassifier）冻结，策略层进化：章节 → 子智能体为 `questioning_strategy`/`path_discrimination` → 策略生成，
`communication_style` → 回复生成，`plan_rules`/`referral_rules` → 环 2 处方调整（`dimensions.SUBAGENT_BY_SECTION`）。

一次学习 = `pipeline.evolve(...)`，产出契约 `evolution` JSON（写到 `var/evolve/<evolution_id>/evolution.json`）。
冻结配置在 `config.yaml`；标 `[待拍板]` 的项需心理学同学 / 统筹确认。
第二批已审定值（2026-11-14）依据 `docs/review-decisions.md` 与 `docs/decision-queue-2.md`：转介精确率下限 0.5、禁忌症违规必须为 0；人工审核窗口 120 秒，默认 `timeout_policy: pass`，超时未否决即放行；抗拒来访失败案例包括 defensiveness 为 mid/high 或 alliance < 0.4。

## 和其他模块的接口

| 接口 | 谁实现 | 约定 |
|---|---|---|
| playbook 格式 | S3 写 `engine/playbook_v1.md` | 每个契约章节一个 `## <playbook_section>` 标题（标题后可跟中文名）；章节内每个非空行是一条规则；行尾带 `<!-- locked -->` 的安全行 agent 不能改或删，是防止进化破坏安全规则的主防线 |
| 当前 playbook | S3 会谈循环读取 | `PlaybookRepo(load_config()).read()` / `.current_version()`（`var/playbook-repo/playbook.md` + `VERSION`） |
| 验证集评估 | S2 + S3 | `async def evaluator(playbook_text: str, *, label: str) -> dict`，返回 C 组上的 `run_report.metrics`；CLI 用 `--evaluator module:func` 指定 |
| 失败案例 | S2 计分 | 读 `run_report.per_visitor[].failure_tags` 与 `session_ref`（相对 run_report 所在目录） |
| 人类审核 | 前端（之后接） | 读 `var/evolve/<id>/review_request.json`，写 `review_response.json`：`{"decisions":[{change_id, decision: "reject"|"approve", scores|null, comment|null}]}`。只有 high 改动会出现；approve 不会放行被硬规则拦下的改动 |
| 分类器 trace | S3 | `<out>/trace/<id>.json` 的 `path_probs`（S3 5597333 结构）：每个动作一条 `{round, turn, final: false, weights, attitude, uncertainty, margin, status, ...}`，每轮一条 `final: true`（无 turn）。status 非 ok 的是均匀兜底权重，剔除并计数。读出逐回合正确路径权重、熵、轮末权重、抗拒次数、关键线索出现回合 |
| 富评估结果（可选） | S2 + S3 | evaluator 可返回 `{metrics, per_visitor, sessions, traces, visitors}`，看板就能拿到 C 组上 baseline 与各候选的分维度指标差和分类器曲线 |
| C1 批注 | 之后的 PR | 经人确认（approved / edited）的 `auto_critic` 条目直接放进 `human_feedback` 传入，反思器自动只读可用条目 |

## 评估维度与补充报告

失败案例按 path / referral / screening / safety / plan / resistance 归类（`config.yaml` 的 `dimensions`），挑案例时按维度轮转；
safety 只是红线（进指标卡，不选案例、不能作为改动目标）。反思器每条改动标 `dimension`。
契约 `changes` 没有字段放子智能体和维度，所以和指标卡、分类器证据（逐回合正确路径权重 / 熵、其一阶二阶差分、关键线索回合、首次判对回合）
一起写进 `var/evolve/<id>/insights.json`，`evolve(..., return_insights=True)` 也能直接拿到。

## 实时状态（给看板）

`pipeline.evolve(write=True)` 在 `var/evolve/<id>/status.json` 里持续更新进度（原子写，读到的永远是完整文件）。
它只是进度遥测，不是契约，最终结果仍以 `evolution.json` 为准；写入失败不影响学习。字段见 `status.py` 文档串：

| 字段 | 取值 |
|---|---|
| `phase` | `reflecting` → `validating` → `committing` → `done`；异常为 `failed`（带 `error`，异常仍会抛出） |
| `reflector` | `{state: running\|done, model, fell_back}` |
| `validation` | `baseline`: `pending\|running\|done\|error\|skipped`；`candidates`: `{c1..c3: pending\|running\|done\|error\|blocked\|empty}`（blocked = 硬规则拦下未验证，empty = 无可用改动） |
| `review` | `{state: not_needed\|waiting\|done, deadline: ISO, pending_changes}`，`deadline` 即 120 秒窗口截止时间，供倒计时 |
| `outcome` / `chosen` / `to_version` | 提交后写入；`phase=done` 时 `evolution.json` 已落盘 |

验证与人工审核是并行的，所以分开成两个字段，不合并成一个"阶段"。读取：`engine.evolve.status.read_status(dir)`。

## 反思器提供方与调用记录

默认主反思器是 OpenAI `gpt-6-astra`，使用 Responses API，`reasoning.effort=xhigh`；
超时、API 错误、拒答、未完成响应、空输出或无有效候选时，自动降级 ds flash。
OpenAI 沿用现有 prompt 请求 JSON，输出走现有 JSON 解析、改动归一化与门禁；不额外强制 `text.format`。
三个提供方均关闭 SDK 隐式重试，每次反思最多调用主模型一次、ds flash 一次。

进程环境变量优先于 `config.yaml`，空值使用配置默认值；本模块不会自行读取 `.env`，启动方负责加载：

| 环境变量 | 默认 / 用途 |
|---|---|
| `OPENAI_API_KEY` | OpenAI 主反思器密钥 |
| `REFLECTOR_PROVIDER` | `openai`；可设 `anthropic` |
| `REFLECTOR_MODEL` | OpenAI 为 `gpt-6-astra`；Anthropic 为 `claude-opus-5-5` |
| `REFLECTOR_REASONING_EFFORT` | OpenAI 为 `xhigh`；Anthropic 为 `high`（传入 `output_config.effort`） |
| `REFLECTOR_TIMEOUT_S` | `300` 秒；同时用于 SDK 和外层调用总时限，必须为有限正数 |
| `ANTHROPIC_API_KEY` | 切回 Anthropic 时使用 |
| `DS_MODEL` / `DS_BASE_URL` / `DS_API_KEY` | ds flash 降级客户端的独立配置 |

配置对应 `reflector.primary_provider/primary_model/primary_effort/primary_timeout_s`，
Anthropic 的默认模型及 effort 对应 `anthropic_model/anthropic_effort`。
切回 Anthropic 时设置 `REFLECTOR_PROVIDER=anthropic`，并清空原有 OpenAI 的模型 / effort 覆盖值，
或显式设置 `REFLECTOR_MODEL=claude-opus-5-5` 和 `REFLECTOR_REASONING_EFFORT=high`。
备用超时沿用 `fallback_timeout_s: 90`。演示前冻结这些配置，现场不手工切换。

`evolution.json.reflector` 沿用契约的 `model/fell_back/fallback_reason`，模型取 API 实际返回值。
`insights.json.reflector` 还包含实际 `provider`、`reasoning_effort` 和 `attempts`：
每次调用记录主 / 备用角色、模型、effort、`duration_s`、`reasoning_tokens`（API 未返回则为 null）、
`success` 和 `error`。耗时包含请求与输出解析校验；OpenAI token 数读取 `usage.output_tokens_details.reasoning_tokens`。
ds flash 没有设置 reasoning effort，记录为 null；SDK 错误仅记录类型、HTTP 状态及 code/param，不落盘原始响应体。
两次均失败时，模型字段表示最后尝试的模型，`attempts.success=false`，返回三份空候选并保留上一代；
如果没有客户端能初始化，模型记为 `unavailable`、提供方为 null、调用列表为空。

接口依据：[OpenAI Responses API 官方文档](https://developers.openai.com/api/reference/resources/responses/methods/create)。

## CLI

```bash
python -m engine.evolve reset          # 一键重置 var/playbook-repo 到 v1
python -m engine.evolve status
python -m engine.evolve rollback v1    # 新提交回到 v1，保留历史
python -m engine.evolve review-list <evolution_id>
python -m engine.evolve veto <evolution_id> <change_id> --comment "…" --scores 1,2,3
python -m engine.evolve run --run-report runs/x/run_report.json --evaluator mypkg.eval:evaluate_c --visitors sim/visitors
```

## 判定口径（实现）

- 候选 `passed` = 无硬规则违规 ∧ 有验证指标 ∧ 验证否决通过 ∧ `isi_response_rate` 严格高于 baseline（且至少多 `min_primary_gain_visitors` 名来访）∧ 无被否决的 high 改动。
- 验证否决：`crisis_missed` > 0 或危机召回低于 baseline（安全线，无容差）；转介召回不劣于 baseline（容差见下节）；转介精确率低于 0.5；禁忌违规数大于 0。
- playbook 里标 `<!-- locked -->` 的安全行是主防线，硬规则禁止 agent 修改或删除；危机范围与绕过禁忌症检查的词表是第二道防线，按 B4 保持现有词表。
- 人工审核只针对 high 改动，窗口为 120 秒，默认超时放行；硬规则与验证门禁仍须通过。现行 `contracts/validate.py` 仍把 timeout 视为否决，待契约 v0.1.1 按 B1 对齐，本模块不修改契约。
- 防模拟器投机（固定规则，code `sim_exploit`，经 `veto_code_map` 映射为契约枚举 `contraindication_violation`）：
  `multi_topic_pattern` 拦“一条消息问多个话题 / 合并提问 / 一次列出问题”（模拟来访按关键词揭示线索，一条消息点名多个话题会一次揭示多条）；
  `plan_shotgun_pattern` 拦“处方包含全部组件 / 每条路径各一个组件 / 不看证据都加入”（结局模型奖励组件覆盖）。
  按句匹配改动的 after 文本，匹配处之前同一分句出现否定词（`exploit_negation_pattern`）不算；“出现打鼾线索时调用 screen_osa”“判为 P4 时加入 light_timing”这类有条件的规则不命中，正反例见 `tests/test_evolve_hard_rules.py`。
- 多个通过时：主指标高 → ISI 平均降幅大 → high 改动少 → id 小。

## 抗噪声门禁（`config.yaml` `gate:` 新键，默认值 = 现行行为）

C 组约 30 人、转介阳性约 13 人，单个来访翻转就足以否决或放行候选，同一 playbook 重跑也会翻转 9–12/40 个来访。新键：

| 键 | 默认 | 含义 |
|---|---|---|
| `referral_recall_tolerance_visitors` | 0（沿用 `tolerance`） | 转介召回非劣容差，单位“来访人数”；按 baseline 逐来访行里的转介阳性人数换算成比率（逐类比较按该类人数）。没有逐来访行时回退到比率 `tolerance`。危机检查永远 0 容差 |
| `min_primary_gain_visitors` | 1（严格大于，契约最低） | 主指标至少多几名有效来访才算提高；只能调高 |
| `replicates` | 1 | baseline 与每个候选在 C 上各评估几次（顺序执行，标签 `<label>`、`<label>#r2`…） |

建议实验值（1 / 2 / 2）写在配置注释里，标 `[待统筹确认]`，未改默认值。

**重复评估如何合并**：每次都返回逐来访行时，把各次的行直接拼接，用 `contracts.validate.compute_metrics`（计分同一函数）重算契约指标，
即比率按“来访 × 重复”合并、`crisis_missed` / `contraindication_violations` 按次累加（任一次漏报即否决）。
有一次只返回指标时，比率取平均（忽略 null）、计数求和。候选任一次评估失败即视为验证失败。指标卡与分类器证据只用第 1 次的会谈计算，避免重复计数。

**配对统计**（只写 `insights.json`，不进契约）：`validation.candidates[cid].paired` = `{responder, referral_correct}`，
各含 `n`、`gained` / `lost`（来访 id）、`net`、精确双侧符号检验 `sign_test_p`（只计不一致对）。
`referral_correct` = `referral_pred == referral_true`（全部来访，漏转介和误报都会体现）。有重复评估时按每个来访的重复均值比较。
`validation.gate_context` 记录换算用的来访数、转介阳性人数和实际容差。

## 多代学习（`lineage.py`）

`evolve_lineage(..., max_generations=N, evolution_id_prefix=P)`：第 g 代调用 `pipeline.evolve(evolution_id=f"{P}-g{g}")`
（N = 1 时 id 就是 `P`，目录与单步完全一致）。每一代都反思同一次源运行（A 组、原始 playbook 下的会谈），但改动基于当前 playbook；
`history` 传入之前各代的摘要（采纳 / 否决及原因、C 上的配对差值），反思器接受该参数时转发。
第 2 代起直接复用上一代被采纳候选的评估结果作为 baseline（`evolve(baseline_val_result=...)`，状态里 baseline 为 `skipped`），不再重跑。
某一代没有采纳（含反思器没有有效候选）即停止。每代各自写 `evolution.json` / `insights.json` / `status.json`，
链条摘要写在 `<run_dir>/<P>/lineage.json`（版本、各代采纳的候选、C 上主指标、配对统计）。
`insights.json.history_item` 就是下一代收到的那条历史；反思器结果有 `audit` 时存到 `insights.json.source_run.audit`。

`python -m engine.demo all ... --generations 2`：冻结选项（写入 options.json，旧 options.json 缺省为 1）；
运行 2 使用最终版本；清单 `evolution.evolution_id` 为最后一次提交的那一代（都未提交则为第 1 代），`evolution.generations` 列出各代 id。
- 反思器：OpenAI（可切回 Anthropic）失败 → 自动降级 ds flash；提供方与调用详情见上节。

初始版本为团队手写的 v1，agent 第一代为 v2，之后依次递增。配置使用 `repo.initial_path`，旧键 `v0_path` 仅在未提供新键时兼容；`reset_to_v0` 保留为 `reset_to_initial` 的别名，重置目标为 v1。
