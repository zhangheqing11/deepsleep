# PR #1（contracts v0.1.0）验收修复清单

> **给修复会话**：你要在 `zhq/contracts-v0` 分支（PR #1）上按本文修。修完后让验收会话复验，再合并。
> 验收日期：2026-11-14　验收对象：PR #1 head `79fc916`　验收方式：Codex 独立验证 + 验收会话人工核对。
> 完整证据（42 个输入变异的逐项记录、AGENTS.md 第 3 节十条对照、依赖版本比较）：[`pr1-contracts-codex-report.md`](pr1-contracts-codex-report.md)。本文里的 F/M 编号都指向该报告。

## 1. 验收结论

**契约本身可用，校验器与示例有缺口，修完再合。**

已确认没问题（不用再动）：
- `make contracts` 退出码 0，10 个示例全 OK，与 PR 描述一致。
- 5 个 schema 共 81 个 `$ref` 全部可解析；核心枚举（P1–P5、R0–R3、crisis 三档、failure_tag、veto code）都通过 `common` 复用，无分叉。
- 对象基本都 `additionalProperties:false`；`$schema` 声明 2020-12 与 `validate.py` 用的 `Draft202012Validator` 一致。
- 示例里没有个人信息、密钥、绝对路径、未核实的热线号码。
- jsonschema 4.18.0 与 4.26.0 对原始示例和 42 个变异的结果相同。
- 按路径换 CWD 运行都通过。

问题的性质：**不是示例数据错，而是校验器没拦住本应拦的矛盾**。42 个变异里 20 个被拒、22 个被放过（22 个里有一部分属于"契约没法表达"，不全是漏检）。校验器是前后端、引擎、数据科学共同依赖的"裁判"，裁判有洞，后面的人会基于它误以为数据没问题。

## 2. 修复范围与规则

- 只改 `contracts/`（含 `contracts/validate.py`、`README.md`、`examples/`）、`Makefile`、`requirements.txt`，以及 P1 里点名的 `docs/PLAN.md` 4.1。
- 凡是**改 schema 字段**的（F07、F08、F16 的枚举化）按 AGENTS.md 7.3 走 `[contract]` 流程：PR 标题保留 `[contract]`，在 PR 里写清新增/变更字段，通知前端组和数据科学同学。只改 `validate.py` 与示例的不算改契约。
- 不要改安全层的危机判据，不碰 `safety/`、`engine/`。
- 修完更新 PR 描述：补上第二个提交（`history_check` 动作、四选一 `judge_label`、`auto_critic` 反馈字段）和本次修复的内容。

## 3. 修复项

### P0：合并前必须修（校验器漏检，涉及锁定决定）

| 编号 | 问题 | 怎么复现 | 要求 |
|---|---|---|---|
| F01 | evolution 门禁不检查危机漏报与转介召回。AGENTS.md 第 3 节第 5 条要求"危机 0 漏报；其他转介不劣于上一代 + 精确率下限"，`validate.py:294-301` 只查硬违规、布尔 `veto` 和 ISI 主指标 | M21：把已选候选 `val_metrics.crisis_missed` 改 1；M22：`referral_recall` 改成低于 `baseline_val_metrics` | `candidates[].passed=true` 时，若 `val_metrics.crisis_missed>0` 或任一 `referral_recall_by_label` 低于基线，报错。复用 run_report 里 `validate.py:264-265` 的危机否决检查，不要重写一份 |
| F02 | PHQ-9 第 9 题阳性可被"冒充处置"：校验只查 `scale_item9` 事件存在与位置，不查内容（`validate.py:153-158`） | M41：保持第 9 题=1，把该事件改成 `level=none, action=history_check` | `source=scale_item9` 的事件必须 `level` 为 passive 或 active，且 `action` 为 `safety_check` 或 `crisis_protocol`；同时在 `session.schema.json` 里用 `if/then` 约束，不只靠 `validate.py` |
| F03 | 危机真值与轮次最高级别、事件动作、判断器概率之间缺一致性检查 | M26：visitor 第 9 题=1 而 `crisis.level` 仍 none；M27：有 passive 事件的轮次 `crisis_level` 改 none；M28：事件升 active 而 action 仍 `safety_check`；M29：`judge_probs` 四项都设 1 | ① `phq9_item9>0` 时 `crisis.level` 不得为 none（`history` 例外要在 README 写明）；② 每轮 `crisis_level` = 该轮事件最高 level；③ active→`crisis_protocol`、passive→`safety_check`；④ `judge_probs` 四项之和约等于 1（容差 1e-3） |
| F06 | `veto.passed` 与 `reasons` 可自相矛盾（M24：`passed=true` 却有 `crisis_missed` 原因）；精确率下限没有字段也没有检查 | M24、M23 | ① `passed=true` ⇔ `reasons` 为空，run_report 与 candidates 两处都查；② 精确率下限：与统筹同学确认数值后写进契约（建议放 `evolution` 的门禁规则字段，带规则版本号），在 F01 的检查里一并执行。**数值未定前，先在 README 标注"下限待定"，不要自己编数** |
| F12 | `examples/` 为空时校验器无输出、退出码 0（`validate.py:367,396`），漏打包示例会静默通过 | E10 | 找不到任何示例文件时返回非零并报错 |

### P1：建议一起修，不修要在 PR 里说明理由

| 编号 | 问题 | 要求 |
|---|---|---|
| F04 | `run_report` 的 `session_ref` 共 24 条，按报告所在目录解析只有 3 条文件存在，21 条指向不存在的文件（`run_report.run1.json:163` 等）；校验器不检查 session/visitor 引用是否存在（M07、M08） | ① 校验器：`session_ref` 指向的文件必须存在，`session.visitor_id` 必须对应已有 visitor；② 示例：要么补齐缺的 session，要么把示例报告里指向不存在文件的条目改成 `null`（并确认 schema 允许）；③ README 写明前端遇到缺失 session 应该怎么显示 |
| F05 | run_report 内部重算不证明明细与事实一致：`isi_baseline` 未参与校验（M25）、`path_wrong_r1` 标签可被删（M30）、`per_visitor` 可重复 visitor_id（M31）、`split` 与明细不符（M32） | `isi_baseline == isi_week[0]`；`per_visitor.visitor_id` 唯一；`path_wrong_r1/r2` 标签由预测与真值推导，像 `screen_missed` 那样双向校验；`split` 与明细 visitor 的 split 一致 |
| F07 | 契约里没有记录 temperature、状态模型版本和参数摘要，锁定决定第 3、7 条（模拟来访 temperature 0；依从/同盟/效果由冻结规则模型算）无法从数据里审计 | **改 schema，走 `[contract]`**：`models` 里加 `temperature`（agent、visitor 各一个）；`run_report` 加 `state_model: {version, params_digest}`；示例同步。字段名定稿前先跟数据科学同学对一下，他们接手 `sim/` `scoring/` |
| F08 | 已提交进化可以 `diff=null`（M33）；`playbook_version` 可为空字符串（M39）；`sha` 只是任意字符串；`source_run_id` 与 from/to 版本不核对 | `outcome=committed` 时 `diff` 必须非 null；版本号加 `minLength:1`（最好加正则 `^v\d+$`）；`sha` 加格式约束；校验 `source_run_id` 对应的 run_report 的 `playbook_version == from_version` |
| F13 | `docs/PLAN.md` 4.1 的字段名与实际 schema 不一致：`crisis_flag`→`rounds[].crisis_level`、`behaviors[]`→object、`crisis_miss`→`crisis_missed`、`reflector_model`→`reflector.model`、候选 `diff`→`changes` | 同步 PLAN 4.1，或在 PLAN 4.1 顶部写"字段以 `contracts/README.md` 为准，本节仅作设计背景"。AGENTS.md 已写"与 PLAN 冲突以 AGENTS 为准"，但前后端 AI 会读 PLAN，要避免它们按旧字段名写代码 |
| F10 | `validate.py:366-375` 总是读内置 `examples/visitor.*.json` 建索引，传入别的 visitor/session 文件会误报（E14） | visitor 索引改为来自命令行传入的文件集合；没传时才用默认目录 |

### P2：有空再修

| 编号 | 问题 | 要求 |
|---|---|---|
| F09 | 候选改动正文（`after`）与建议卡片 `body` 里出现"诊断""治疗失眠症"、或改写危机触发规则时，校验器不拦（M34、M35） | 不要在 `validate.py` 里另写词表；等 `domain/vetoes.py`（在 `zhq/domain-safety` 分支）合并后复用同一份禁用词。现在先在 README 注明"正文语义校验由引擎的 veto 负责，不在契约校验范围" |
| F11 | 日记 `day` 可重复（M36）、`plan.tib_minutes` 可为负（M37）；`1e400` 解码成无穷大能绕过 NaN/Infinity 检查（E11） | `day` 必须是 1–7 的排列；`tib_minutes` 加 `minimum`；数值解码后用 `math.isfinite` 检查 |
| F14 | schema 本身损坏或 `$ref` 断裂时输出 Python traceback（E08、E09），虽然不会错误放行 | 加载 schema 与校验循环外面包一层异常处理，输出一行 FAIL |
| F15 | `requirements.txt` 是 `jsonschema>=4.18` 无上限 | 改成 `jsonschema>=4.18,<5`；4.18.0 与 4.26.0 已验证一致 |
| F16 | `judge_label` 在 `common` 里是孤立定义，无人 `$ref`；`evolution.hard_rule_violations[].code` 是任意字符串（M38 拼错也通过） | `hard_rule_violations.code` 改成枚举（与 `veto` code 对齐或单独定义）；`judge_label` 要么被 `judge_probs` 的键约束引用，要么删掉 |
| F17 | 示例里没有 `crisis_exit`/`error` 会话、active 危机流程、`kept_previous`、反思器回退（`fell_back=true`），前端无法对着示例开发这些状态 | 至少补：1 个 `crisis_exit` 会话、1 个 `kept_previous` 的 evolution、1 个 `fell_back=true` 的 reflector。可以晚于合并补，但要登记到 BACKLOG |

## 4. 验证与验收标准

修复会话自检：

```bash
make contracts     # 原有 10 个示例必须仍然全部 OK
```

**回归测试（必须有）**：把 P0 每一项的变异做成可重复的测试，放在 `contracts/tests/`，用 pytest 或朴素脚本都行。每个用例：复制示例 → 应用一个变异 → 断言 `validate.py` 退出码非 0 且报错信息包含关键词。至少覆盖 M21、M22、M23、M24、M26、M27、M28、M29、M41 和 E10。`Makefile` 里让 `make contracts` 同时跑这组测试。

验收会话复验时的标准：
1. `make contracts` 全绿，测试集全绿。
2. 重新跑 Codex 报告里 M01–M42 的变异，P0 相关的全部被拒，且没有新增"原本能过的示例被误报"。
3. P1 每一项要么已修，要么 PR 评论里有明确的"不修+理由"。
4. PR 描述已更新；涉及 `[contract]` 的字段变化已在 PR 里列清楚，且前端组与数据科学同学已 approve。

## 5. 注意

- 报告里 F18 和部分"低"严重度条目只是核查记录，不是缺陷，不用修。
- 示例里的对话与建议仍是占位文案，正式文案另走审核，不属于本次修复。
- 不要因为修复而降低已有检查（比如放宽容差），修复只加不减。
