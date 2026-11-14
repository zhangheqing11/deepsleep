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
| playbook 格式 | S3 写 `engine/playbook_v0.md` | 每个契约章节一个 `## <playbook_section>` 标题（标题后可跟中文名）；章节内每个非空行是一条规则；行尾带 `<!-- locked -->` 的安全行 agent 不能改或删，是防止进化破坏安全规则的主防线 |
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
- 验证否决：`crisis_missed` > 0 或危机召回低于 baseline（安全线，无容差）；转介召回不劣于 baseline；转介精确率低于 0.5；禁忌违规数大于 0。
- playbook 里标 `<!-- locked -->` 的安全行是主防线，硬规则禁止 agent 修改或删除；危机范围与绕过禁忌症检查的词表是第二道防线，按 B4 保持现有词表。
- 人工审核只针对 high 改动，窗口为 120 秒，默认超时放行；硬规则与验证门禁仍须通过。现行 `contracts/validate.py` 仍把 timeout 视为否决，待契约 v0.1.1 按 B1 对齐，本模块不修改契约。
- 多个通过时：主指标高 → ISI 平均降幅大 → high 改动少 → id 小。
- 反思器：Opus 5.5 超时 / 报错 / refusal / 输出不可用 → 自动降级 ds flash，`reflector.fell_back` 与原因写进 JSON；都失败则 3 份空候选，保留上一代。
