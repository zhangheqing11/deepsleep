# engine/evolve — 环 3 跨来访进化：反思 → 硬规则 → 门禁 → 只否决审核 → playbook 版本库

三环（参照 TheraMind）：环 1 会谈内、环 2 同一来访跨轮由 S3 完成；环 3 是本模块，从一批来访的失败里改写 playbook。
感知层（PathClassifier）冻结，策略层进化：章节 → 子智能体为 `questioning_strategy`/`path_discrimination` → 策略生成，
`communication_style` → 回复生成，`plan_rules`/`referral_rules` → 环 2 处方调整（`dimensions.SUBAGENT_BY_SECTION`）。

一次学习 = `pipeline.evolve(...)`，产出契约 `evolution` JSON（写到 `var/evolve/<evolution_id>/evolution.json`）。
冻结配置在 `config.yaml`；标 `[待拍板]` 的项需心理学同学 / 统筹确认。

## 和其他模块的接口

| 接口 | 谁实现 | 约定 |
|---|---|---|
| playbook 格式 | S3 写 `engine/playbook_v0.md` | 每个契约章节一个 `## <playbook_section>` 标题（标题后可跟中文名）；章节内每个非空行是一条规则；行尾带 `<!-- locked -->` 的行 agent 不能改或删（建议给"睡眠限制前检查禁忌"等安全条目加上） |
| 当前 playbook | S3 会谈循环读取 | `PlaybookRepo(load_config()).read()` / `.current_version()`（`var/playbook-repo/playbook.md` + `VERSION`） |
| 验证集评估 | S2 + S3 | `async def evaluator(playbook_text: str, *, label: str) -> dict`，返回 C 组上的 `run_report.metrics`；CLI 用 `--evaluator module:func` 指定 |
| 失败案例 | S2 计分 | 读 `run_report.per_visitor[].failure_tags` 与 `session_ref`（相对 run_report 所在目录） |
| 人类审核 | 前端（之后接） | 读 `var/evolve/<id>/review_request.json`，写 `review_response.json`：`{"decisions":[{change_id, decision: "reject"|"approve", scores|null, comment|null}]}`。只有 high 改动会出现；approve 不会放行被硬规则拦下的改动 |
| 分类器 trace | S3 | `<out>/trace/<id>.json` 中 `path_probs: [{round, turn, probs: {P1..P5}}]`（也接受 `classifier`/`weights` 等写法，或 transcript 每条的 `path_probs`）。读出逐回合正确路径权重、熵、关键线索出现回合 |
| 富评估结果（可选） | S2 + S3 | evaluator 可返回 `{metrics, per_visitor, sessions, traces, visitors}`，看板就能拿到 C 组上 baseline 与各候选的分维度指标差和分类器曲线 |
| C1 批注 | 之后的 PR | 经人确认（approved / edited）的 `auto_critic` 条目直接放进 `human_feedback` 传入，反思器自动只读可用条目 |

## 评估维度与补充报告

失败案例按 path / referral / screening / safety / plan / resistance 归类（`config.yaml` 的 `dimensions`），挑案例时按维度轮转；
safety 只是红线（进指标卡，不选案例、不能作为改动目标）。反思器每条改动标 `dimension`。
契约 `changes` 没有字段放子智能体和维度，所以和指标卡、分类器证据（逐回合正确路径权重 / 熵、其一阶二阶差分、关键线索回合、首次判对回合）
一起写进 `var/evolve/<id>/insights.json`，`evolve(..., return_insights=True)` 也能直接拿到。

## CLI

```bash
python -m engine.evolve reset          # 一键重置 var/playbook-repo 到 v0
python -m engine.evolve status
python -m engine.evolve rollback v1    # 新提交回到 v1，保留历史
python -m engine.evolve review-list <evolution_id>
python -m engine.evolve veto <evolution_id> <change_id> --comment "…" --scores 1,2,3
python -m engine.evolve run --run-report runs/x/run_report.json --evaluator mypkg.eval:evaluate_c --visitors sim/visitors
```

## 判定口径（实现）

- 候选 `passed` = 无硬规则违规 ∧ 有验证指标 ∧ 验证否决通过 ∧ `isi_response_rate` 严格高于 baseline ∧ 无被否决的 high 改动。
- 验证否决：`crisis_missed` > 0 或危机召回低于 baseline（安全线，无容差）；转介召回不劣于 baseline；转介精确率下限；禁忌违规数上限。
- 多个通过时：主指标高 → ISI 平均降幅大 → high 改动少 → id 小。
- 反思器：Opus 5.5 超时 / 报错 / refusal / 输出不可用 → 自动降级 ds flash，`reflector.fell_back` 与原因写进 JSON；都失败则 3 份空候选，保留上一代。
