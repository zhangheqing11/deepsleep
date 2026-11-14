# safety/ 与 domain/vetoes 实现规格 v0

> 安全层**不参与进化**：词表、阈值、判断器 prompt、话术在演示前冻结，playbook 改不到这里。
> 数据结构以 `contracts/README.md` 为准（`crisis_level`、`safety_source`、`safety_action`、`judge_status`、session.`safety_events`）。

## 1. 数据文件（内容待心理学同学审定，先放最小占位）

| 文件 | 内容 |
|---|---|
| `safety/lexicon.yaml` | 三档：`explicit`（每条带 `level: passive \| active`）、`ambiguous`、`exclude`（只作用于 ambiguous）。每条 `{id, pattern(正则), level?, example}` |
| `safety/scripts.yaml` | 固定话术：`history_check`（核验过去已结束风险当前是否仍有的兜底）、`history_verify_patterns`（核验正则表）、`safety_check`（被动意念时插入的一句安全确认）、`crisis_protocol`（主动意念时的完整话术，含热线占位 `{hotlines}`）、`hotlines` 列表 `[{name, number, hours, verified: bool}]`。文案为占位，正式文案另行审核 |
| `safety/config.yaml` | `judge_provider: ds_flash \| jev \| gemini_decision \| mock`、`judge_timeout_s: 2.5`、`tau_flag`（P(passive)+P(active) ≥ 此值至少判 passive，默认 0.2）、`tau_active`（P(active) ≥ 此值判 active，默认 0.5） |
| `safety/testset.jsonl` | 独立测试集，每行 `{id, text, label: none\|history\|passive\|active, cssrs, difficulty}`；先放 8 条占位（含 2 条 history） |

## 2. 判定流程（每条**来访**发言、每次量表结果都过一遍）

```
text ─▶ rules.match(text)
         ├─ explicit 命中 ─▶ level = 条目 level，source = rule_explicit，judge_status = skipped
         ├─ ambiguous 命中（且未被 exclude 抵消）─▶ judge
         │      ├─ ok      ─▶ 按阈值分档（含 history → level none + history_check；ok 时不强制 passive），source = rule_ambiguous+judge
         │      └─ 失败    ─▶ level = passive，source = rule_ambiguous，judge_status = timeout|error
         └─ 都没命中 ─▶ judge
                ├─ ok ─▶ 按阈值分档（含 history_check），source = judge
                └─ 其余 ─▶ none（判断器失败时记录 judge_status，但不升级）
量表：PHQ-9 第 9 题 > 0 ─▶ level = passive，source = scale_item9（不调判断器）
```

- exclude 只能抵消 ambiguous，**不能抵消 explicit**。
- history 分档：先检查 P(active) ≥ tau_active，再检查 P(passive)+P(active) ≥ tau_flag；均未达到且 P(history) 为最大（含并列）时，level none + history_check，否则 none。history_check 同一会话只发一次，已 active 后不发，不提高最高 level。判断器失败且 ambiguous 命中时仍兜底 passive。
- 动作：passive → `safety_check`；active → `crisis_protocol`。同一来访只升不降：已 active 后不再插 safety_check；已触发过 safety_check 后再次 passive 不重复插话术（仍记事件）。
- active 后会谈状态应变为 `crisis_exit`（由引擎执行，安全层只返回动作）。

## 3. 代码结构（Python 3.11+，asyncio）

| 模块 | 职责 |
|---|---|
| `safety/rules.py` | 加载 lexicon，`match(text) -> RuleHit(tier, entry_ids, level)` |
| `safety/judges.py` | `Judge` 协议：`async classify(text) -> JudgeResult(probs={none,history,passive,active}, status, provider, latency_ms)`。实现：`MockJudge`（确定性，按关键词给概率，供 smoke 与测试）、`DsFlashJudge`（OpenAI 兼容 SDK，读 `DS_BASE_URL/DS_API_KEY/DS_MODEL`，temperature 0，JSON 输出 `{"level": ..., "probs": {...}}`，解析失败算 error）、`JevJudge`（`typesafe_sdk` 的 `AsyncTypeSafeClient` + `Choice`，选项顺序 **active, passive, history, none**——利用其偏前选项的倾向往召回方向偏；读 `TYPESAFE_API_KEY`）。`GeminiDecisionJudge`（`google-genai>=3.2.0`，`genai.Client(http_options={"api_version": "v1beta"})`，`client.aio.decisions.create(model="gemini-decision-1", ...)` 用 Choice 题，四个选项 key 为 `none`/`history`/`passive`/`active`，criteria 为各档中文定义（服务端按 key 的 UTF-8 字节序排序，选项顺序无法利用）；读 `GEMINI_API_KEY`；调用细节以 `research/1114/5-gemini-decision.md` 第 2 节官方示例为准）。所有实现都包 `asyncio.wait_for(timeout)`，异常与超时转 status，不抛出。`make_judge(config)` 工厂；缺 key 时回退 MockJudge 并在 provider 字段标 `mock(fallback)` |
| `safety/layer.py` | `SafetyLayer(config).assess_text(text, round, turn, state) -> SafetyEvent \| None` 与 `assess_phq9_item9(value, round, turn, state)`；`SessionSafetyState` 记最高 level、是否已插过 safety_check、`pending_history_check` 与 `history_check_issued`；`check_verification(agent_text) -> bool` 从 scripts.yaml 正则表检测 agent 是否核验，返回 False 时引擎插入 speaker safety 的 history_check 固定话术，完成后清除 pending；active 清除 pending；`SafetyEvent` 序列化后**必须符合** contracts session.`safety_events` 项结构；`script_for(action)` 从 scripts.yaml 取话术（填入热线） |
| `safety/prompts/judge_zh.md` | 判断器 system prompt（冻结）。要点：判断说话人本人当前（近 1 个月）是否有死亡愿望/自杀念头及过去已结束的风险史；C-SSRS 第 1 条 = passive（含"睡过去不再醒来"类），第 2–5 条或任何自伤准备/行为 = active；谈论他人、新闻、夸张口头禅（困死了、累死了、笑死）、单纯想多睡/赖床 = none；过去已结束但当时达 passive/active 的念头、自伤或尝试且当前否认或未表明仍有 = history；当前仍有按 passive/active，拿不准是否结束偏向 passive |
| `safety/eval.py` | `python -m safety.eval --provider rules\|mock\|ds_flash\|jev [--testset path]`：逐条跑，输出混淆矩阵（4×4，none/history/passive/active）、"有风险 vs 无风险"二分类召回/精确率、history/passive/active 各自召回（二分类 history 算无风险；history → none 单列漏核验，history → passive/active 单列过度升级）、漏报条目清单、判断器 p50/p95 延迟与失败数；`rules` = 只用规则层（ambiguous 命中算 passive）。结果另存 `var/safety-eval/<provider>-<时间>.json` |
| `domain/vetoes.py` | 处方与 playbook 硬否决：`check_plan(plan, contraindications) -> list[Violation]`（禁忌人群用 sleep_restriction；`tib_minutes` < 下限，默认 300；`components` 含 sleep_restriction 但 `contraindications_checked` 为 false）；`check_text(text) -> list[Violation]`（禁用措辞、用药建议，规则放 `domain/veto_rules.yaml`）。`Violation(code, message, field)`，code 与契约 `hard_rule_violations[].code` / `veto.reasons[].code` 取值一致 |

## 4. 测试（pytest，全部离线，不花 API 钱）

- explicit 命中直接判档且 judge 不被调用；exclude 抵消 ambiguous 但不抵消 explicit。
- ambiguous + 判断器超时 → passive / rule_ambiguous / timeout；判断器异常同理。
- 无规则命中 + 判断器失败 → 返回 None（只在 state 里记一次失败计数）。
- 阈值分档：构造四键 probs 验证 tau_flag / tau_active 边界、history 最大值及并列边界；ambiguous + history 仍 level none + history_check。
- history_check 的核验正反例、同会话只发一次、active 后抑制、history 事件通过契约子 schema。
- item9 = 0 无事件；= 1 → passive / scale_item9。
- 只升不降、safety_check 不重复。
- SafetyEvent 序列化后用 `contracts/session.schema.json` 里 safety_events 项的子 schema 校验通过。
- `check_plan` / `check_text` 正反例各若干。
- `python -m safety.eval --provider rules` 与 `--provider mock` 在占位测试集上能跑通并输出报告。

## 5. 依赖与配置

- `requirements.txt` 增加：`pyyaml`、`openai`、`pytest`；`typesafe-sdk` 作为可选依赖（`requirements-optional.txt`），未安装时 JevJudge 构造报清晰错误、工厂回退 mock。
- `.env.example` 增加 `TYPESAFE_API_KEY=`、`JUDGE_PROVIDER=`（覆盖 config.yaml）。
- `Makefile`：`test`（pytest）、`safety-eval PROVIDER=rules`；`smoke` 追加 `test`。
