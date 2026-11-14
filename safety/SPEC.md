# safety/ 与 domain/vetoes 实现规格 v0

> 安全层**不参与进化**：词表、阈值、判断器 prompt、话术在演示前冻结，playbook 改不到这里。
> 数据结构以 `contracts/README.md` 为准（`crisis_level`、`safety_source`、`safety_action`、`judge_status`、session.`safety_events`）。

## 1. 数据文件（11/14 词表与测试集定稿；话术已审定、热线已实测）

| 文件 | 内容 |
|---|---|
| `safety/lexicon.yaml` | `explicit`（一律 `level: active`）、`ambiguous`、`exclude`（X1–X8 只排除重叠的模糊命中，X9 仅上下文提示），以及 `past_time`（同句 explicit 改道判断器）。每条 `{id, pattern(正则), level?, example}` |
| `safety/scripts.yaml` | 固定话术：`history_check`（核验过去已结束风险当前是否仍有的兜底）、`history_verify_patterns`（核验正则表）、`safety_check`（被动意念时插入的一句安全确认）、`crisis_protocol`（主动意念时的完整话术，含热线占位 `{hotlines}`）、`hotlines` 列表 `[{name, number, verified: bool}]`，渲染为每行"名称：号码"。话术已定稿（11/14） |
| `safety/config.yaml` | `judge_provider: ds_flash \| jev \| gemini_decision \| startlux \| mock`、`judge_timeout_s: 6.0`、`judge_fallbacks: [jev]`、`judge_fallback_timeout_s: 3.0`、`judge_timeout_overrides: {startlux: 8.0}`（AutoThink 较慢，演示前按实测冻结）、`tau_flag`（P(passive)+P(active) ≥ 此值至少判 passive，默认 0.2）、`tau_active`（P(active) ≥ 此值判 active，默认 0.5） |
| `safety/testset.jsonl` | 独立测试集，每行 `{id, text, label: none\|history\|passive\|active, cssrs, difficulty}`；48 条自写样本（none 21、history 3、passive 14、active 10）；不得复制公开数据或据此反复调 prompt |

**判断器选择（2026-11-14 心理学同学定）**：ds flash 为主判断器，单次超时 6s；timeout/error 立即切 Jev，单次超时 3s；再失败走原规则兜底（模糊档 passive，非模糊档 none）。StartLux 主判断器的 8s 覆盖保留；每个兜底固定使用 `judge_fallback_timeout_s`，不使用 provider 超时覆盖。`tau_flag=0.2` / `tau_active=0.5` 不变，待留出集冻结。

## 2. 判定流程（每条**来访**发言、每次量表结果都过一遍）

```
text ─▶ rules.match(text)
         ├─ explicit 通过主体/否定约束且同句无 past_time ─▶ active，source = rule_explicit，judge_status = skipped
         ├─ explicit 命中且同句有 past_time ─▶ 与 ambiguous 相同的 judge 路径
         ├─ ambiguous 命中（且未被 exclude 抵消）─▶ judge
         │      ├─ ok      ─▶ 按阈值分档（含 history → level none + history_check；ok 时不强制 passive），source = rule_ambiguous+judge
         │      └─ 失败    ─▶ level = passive，source = rule_ambiguous，judge_status = timeout|error
         └─ 都没命中 ─▶ judge
                ├─ ok ─▶ 按阈值分档（含 history_check），source = judge
                └─ 其余 ─▶ none（判断器失败时记录 judge_status，但不升级）
量表：PHQ-9 第 9 题 > 0 ─▶ passive / safety_check（已 active 则 active / crisis_protocol），source = scale_item9（不调判断器，动作永不为 none）
```

- X1–X8 逐命中按区间重叠排除 ambiguous，**不能抵消 explicit**；X9 不丢弃命中，向判断器 user/state/input 文本追加“上下文提示：赖床/补觉语境”。不改 system prompt 或 Choice criteria。past_time 不是 exclude；按 `。！？!?；;\n` 切句，逗号不切句，别句当前 explicit 优先直接 active。
- history 分档：先检查 P(active) ≥ tau_active，再检查 P(passive)+P(active) ≥ tau_flag；均未达到且 P(history) 为最大（含并列）时，level none + history_check，否则 none。history_check 同一会话只发一次，已 active 后不发，不提高最高 level。判断器失败且 ambiguous 命中时仍兜底 passive。
- 判断器对**除命中明确规则外的所有发言**运行；明确规则允许 skipped。
- 动作：passive → `safety_check`；active → `crisis_protocol`。同一来访只升不降：已 active 后不再插 safety_check；已触发过 safety_check 后，文本重复 passive 仍可返回本地 action none（不入契约）。量表阳性始终保留动作非 none 的事件；`script_for_event(event, state)` 用独立 `safety_check_spoken` 标记去重话术，不能过滤量表事件。
- **量表阳性后的固定再核验（2026-11-14 心理学同学审定，冻结、不参与进化）**：本场出现过 `source=scale_item9`，且普通 `safety_check` 播报后的来访回答一直没有产生 passive/active 新事件，则在第一轮动作预算耗尽或提前结束后、处方和收尾消息前，由引擎插入一次 `speaker=safety` 的 `scale_recheck` 原文。只问一次、不占 agent 动作预算；已 active / `crisis_exit` 不触发。重复 passive 即使 action 为本地 `none` 也算透露风险，重复量表阳性不算口头透露。回答仍走完整安全层，active 当场触发 `crisis_protocol` / `crisis_exit`；`history_check` 的既有处理保持不变。
  `script_for("scale_recheck")` 读取 `scripts.yaml` 审定话术，独立于普通确认话术去重。契约事件沿用原量表证据和 `action=safety_check`，定位到再核验发言的 round/turn；`trace.scale_rechecks[]` 记录 `recheck: true`、`counts_toward_cap: false` 以及原事件/再核验事件索引，不改契约枚举、风险判据或 S4 硬规则。
- active 后会谈状态应变为 `crisis_exit`（由引擎执行，安全层只返回动作）。

## 3. 代码结构（Python 3.11+，asyncio）

| 模块 | 职责 |
|---|---|
| `safety/rules.py` | 加载 lexicon，`match(text) -> RuleHit(tier, entry_ids, level)` |
| `safety/judges.py` | `Judge` 协议：`async classify(text) -> JudgeResult(probs={none,history,passive,active}, status, provider, latency_ms)`。实现：`MockJudge`（确定性，按关键词给概率，供 smoke 与测试）、`DsFlashJudge`（OpenAI 兼容 SDK，读 `DS_BASE_URL/DS_API_KEY/DS_MODEL`，temperature 0，JSON 输出 `{"level": ..., "probs": {...}}`，解析失败算 error）、`JevJudge`（`typesafe_sdk` 的 `AsyncTypeSafeClient` + `Choice`，选项顺序 **active, passive, history, none**——利用其偏前选项的倾向往召回方向偏；读 `TYPESAFE_API_KEY`）。`GeminiDecisionJudge`（`google-genai>=3.2.0`，`genai.Client(http_options={"api_version": "v1beta"})`，`client.aio.decisions.create(model="gemini-decision-1", ...)` 用 Choice 题，四个选项 key 为 `none`/`history`/`passive`/`active`，criteria 为各档中文定义（服务端按 key 的 UTF-8 字节序排序，选项顺序无法利用）；读 `GEMINI_API_KEY`；调用细节以 `research/1114/5-gemini-decision.md` 第 2 节官方示例为准）。所有实现都包 `asyncio.wait_for(timeout)`，异常与超时转 status，不抛出。`ChainJudge(primary, fallbacks)` 按顺序调用，首个 ok 即返回，否则返回最后一次失败；返回结果的 provider 属于实际给出结果的判断器，`attempts` 元组保存本次调用的全部尝试，互不共享。`make_judge(config)` 按配置构造链；引擎模式主判断器缺 key/SDK/配置时用 UnavailableJudge 返回该 provider 的 error（无请求），继续尝试可用后备，兜底缺 key/SDK 则跳过，绝不以 mock 冒充该兜底 |
| `safety/layer.py` | `SafetyLayer(config).assess_text(text, round, turn, state) -> SafetyEvent \| None` 与 `assess_phq9_item9(value, round, turn, state)`；`SessionSafetyState` 记最高 level、是否已插过 safety_check、`pending_history_check` 与 `history_check_issued`；`check_verification(agent_text) -> bool` 从 scripts.yaml 正则表检测 agent 是否核验，返回 False 时引擎插入 speaker safety 的 history_check 固定话术，完成后清除 pending；active 清除 pending；`SafetyEvent` 序列化后**必须符合** contracts session.`safety_events` 项结构；`script_for(action)` 从 scripts.yaml 取话术（填入热线）；`script_for_event(event, state)` 负责安全确认话术去重 |
| `safety/prompts/judge_zh.md` | 判断器 system prompt（冻结）。要点：判断说话人本人当前（近 1 个月）是否有死亡愿望/自杀念头及过去已结束的风险史；C-SSRS 第 1 条 = passive（含"睡过去不再醒来"类），第 2–5 条或任何自伤准备/行为 = active；谈论他人、新闻、夸张口头禅（困死了、累死了、笑死）、单纯想多睡/赖床 = none；过去已结束但当时达 passive/active 的念头、自伤或尝试且当前否认或未表明仍有 = history；当前仍有按 passive/active，拿不准是否结束偏向 passive |
| `safety/eval.py` | `python -m safety.eval --provider rules\|mock\|ds_flash\|jev [--testset path]`：逐条跑，输出混淆矩阵（4×4，none/history/passive/active）、"有风险 vs 无风险"二分类召回/精确率、history/passive/active 各自召回（二分类 history 算无风险；history → none 单列漏核验，history → passive/active 单列过度升级）、漏报条目清单、判断器 p50/p95 延迟与失败数；`rules` = 只用规则层（ambiguous 命中算 passive）。结果另存 `var/safety-eval/<provider>-<时间>.json` |
| `domain/vetoes.py` | 处方与 playbook 硬否决：`check_plan(plan, contraindications, *, age=None, crisis_level="none", config=None) -> list[Violation]`（禁忌人群用 sleep_restriction；`tib_minutes` < 下限，默认 330；`components` 含 sleep_restriction 但 `contraindications_checked` 为 false）；`check_text(text, *, context="user_facing") -> list[Violation]`（禁用措辞、用药建议，规则放 `domain/veto_rules.yaml`）。`Violation(code, message, field, severity="hard")`；severity 只取 hard/soft。age < 18 且含 sleep_restriction 硬否决，passive + sleep_restriction 软警告；W1–W8 hard、W9/W10 soft。候选用 `to_hard_rule_violations(violations, change_id)` 过滤 soft 后序列化，code 与契约 `hard_rule_violations[].code` / `veto.reasons[].code` 取值一致 |

安全层外层 `asyncio.wait_for` 使用实际主判断器超时 + 所有已构造兜底超时之和 + 0.1s 余量，避免提前取消兜底。`state.judge_results` 逐次记录全部尝试，`state.judge_failures` 按失败尝试累加；主失败后兜底成功仍计一次失败。

评测显式 `--provider ds_flash|jev|gemini_decision|startlux` 只测单家（`allow_fallback=False`），缺配置/SDK 报错；`--provider chain` 测配置中的链，同样不允许缺 key/SDK 时静默跳过。报告的 calls/failures/providers/延迟统计以单次尝试为单位。`--timeout` 覆盖主判断器超时，链中兜底仍使用配置的单次超时。

## 4. 测试（pytest，全部离线，不花 API 钱）

- `StartLuxJudge`：httpx 异步原生 `state + questions` 请求，默认 Bamboo `/v1/decisions` 与 `startlux-decision-27b-autothink`，读 `STARTLUX_API_KEY/STARTLUX_BASE_URL/STARTLUX_MODEL`；自托管可指定完整 `/v1/systemone` 端点。复用 `prompts/gemini_decision_zh.json` 四档定义，固定 active/passive/history/none 顺序，顶层 `none_check=false, allow_none=false`。校验 `answers.risk` 的 choice/confidence/四键 probabilities；不把 confidence 或内部 none_probability 当阈值。缺 key 时引擎记 error 并尝试可用后备、严格评测报错，超时记 timeout，HTTP 或格式错误记 error，不重试。
- `judge_timeout_overrides` 为可选 provider → 正有限秒数映射，优先于 `judge_timeout_s`；未覆盖的 provider 保持默认。工厂与 eval CLI 支持 `startlux`，依赖 `httpx` 写入主 requirements。
- StartLux 通过 `httpx.MockTransport` 覆盖正常返回、概率缺项/格式异常、HTTP 429/5xx、传输超时与总超时取消、请求顺序和关闭额外 none 检测，以及无 key 的 CLI 明确报错。
- 无同句 past_time 的 explicit 直接 active 且 judge 不被调用；有 past_time 则验证四档成功结果与失败兜底；exclude 只抵消重叠的 ambiguous，不能抵消 explicit；X9 只作提示。
- ambiguous + 判断器超时 → passive / rule_ambiguous / timeout；判断器异常同理。
- 无规则命中 + 判断器失败 → 返回 None（在 state 里按每次尝试记录失败计数）。
- 阈值分档：构造四键 probs 验证 tau_flag / tau_active 边界、history 最大值及并列边界；ambiguous + history 仍 level none + history_check。
- history_check 的核验正反例、同会话只发一次、active 后抑制、history 事件通过契约子 schema。
- item9 = 0 无事件；= 1 → passive / scale_item9。
- 只升不降、safety_check 不重复。
- SafetyEvent 序列化后用 `contracts/session.schema.json` 里 safety_events 项的子 schema 校验通过。
- `check_plan` / `check_text` 正反例各若干。
- `python -m safety.eval --provider rules` 与 `--provider mock` 在 48 条定稿测试集上能跑通并输出报告。

## 5. 依赖与配置

- `requirements.txt` 增加：`pyyaml`、`openai`、`pytest`；`typesafe-sdk` 作为可选依赖（`requirements-optional.txt`），未安装时 JevJudge 构造报清晰错误；引擎模式作主判断器时记录 error、作兜底时跳过；评测时报错。
- `.env.example` 增加 `TYPESAFE_API_KEY=`、`JUDGE_PROVIDER=`（覆盖 config.yaml）。
- `Makefile`：`test`（pytest）、`safety-eval PROVIDER=rules`；`smoke` 追加 `test`。


## 6. PR #6 验收补充口径（2026-11-14）

- **S3：口径已由心理学同学确认（2026-11-14，review-decisions 第二批 D1/D2）**。核验必须在同一个以问号结尾的子句内同时包含时间限定（现在/目前/最近/还/仍等）、风险词和询问；逗号/冒号/句号/分号/换行均分隔子句。陈述句与“不用问/先不谈”等回避句不算。固定 history 兜底话术已审定，本次仅删除“念头，或者”之间的逗号以符合边界；该标点调整已确认。
- **S7：口径已由心理学同学确认（2026-11-14，review-decisions 第二批 D1/D2）**。E1/E3 增加本人主体约束，第三方或主体不明时改为 ambiguous；E4 增加否定与主体约束。原始命中保留，不因语境被丢弃。判断器成功时按结果分档、失败时 passive。另一子句的本人明确风险仍优先 active。词表中的 `explicit_context` 与条目约束在运行前冻结。
- **S8：0 漏报 = 规则 + 真实判断器联合指标，rules-only 不构成该指标**。评测输出 `evidence_columns` 三栏：rules-only、mock、real_judge。mock 标“mock，不代表识别能力”；离线评测的真实判断器栏标“未测”，真实开发集单次结果不能替代 A2/A4 留出集验收。
- A2/A4 留出集对比与冻结验收仍未完成（不修改本任务范围外的 BACKLOG）。**演示前必须有真实判断器的漏报数，漏报数 > 0 不得冻结**。报告默认 `freeze_acceptance.eligible=false`，即使单次零漏报也须人工审定。
- **S5/S6**：文本匹配前 NFKC、去空白、小型繁简映射（无新依赖）；英文 W8 保留词界。W1 含确诊/误诊，W2 含医治/治好失眠症。用户文案始终字面严格检查；仅 candidate_playbook 中明确的否定式禁止列表豁免，豁免不跨句/换行/转折，不覆盖其他肯定建议。
- **S10**：三段固定话术已于 11/14 审定，热线已由心理学同学实测，保持 `verified: true`，每次演示前复核。
- 本次不实现 S11 的 engine 接线和 S12 的其他否决规则，不据单元测试声称其已完成。

## 冻结状态（2026-11-14 下午，心理学同学审定）

- 判断器链：ds flash（6s）→ Jev（3s）→ 规则兜底；`tau_flag` 0.2、`tau_active` 0.5。**已冻结**，演示前不得改。
- 依据：开发集 48 条（`safety/testset.jsonl`）召回 24/24、精确率 1.00；独立留出集 40 条（`safety/holdout.jsonl`，Codex 起草、未参考开发集，心理学同学审定标签）漏报 0、风险召回 21/21、精确率 1.00、p95 约 3.4 秒。
- 留出集只用于冻结验收，不得据此调规则或 prompt；之后若改动判断器或词表，须另写新留出集。
