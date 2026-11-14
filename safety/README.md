# 固定安全层

契约以 `contracts/README.md` 和 schema 为唯一真相，`SPEC.md` 补充实现约定；词表与 48 条自写测试集已按 11/14 临床结论替换，固定话术已由心理学同学审定，热线已于 2026-11-14 实测，`verified: true`；每次演示前仍须复核。
本集仅用于排错，不能证明真实场景零漏报，不得据此反复调 prompt。
**0 漏报 = 规则 + 真实判断器联合指标，rules-only 不构成该指标；mock 不代表识别能力。**
BACKLOG A2/A4 的留出集对比与冻结验收仍未完成。演示前必须提供真实判断器的漏报数，漏报数 > 0 不得冻结。

在仓库根目录运行：

```sh
make venv && make test
make safety-eval PROVIDER=rules
make safety-eval PROVIDER=mock
make contracts
```

`make smoke` 同时运行 contracts 和 test。测试使用假客户端并禁止 socket 连接，不读 `.env`，不调用真实 API。
`python -m safety.eval --provider rules|mock|ds_flash|jev|gemini_decision|startlux` 写入配置指定的报告目录。
激活 `.venv` 后也可直接在根目录运行 `pytest`。

## 接入约定

每位来访独立创建 `SessionSafetyState()`，各来访可以并发，同一来访的发言与量表须按会谈顺序调用。
`await layer.assess_text(text, round, turn, state)` 检查来访发言；
`layer.assess_phq9_item9(value, round, turn, state)` 同步检查每次量表结果。
自评表使用 `round=1, turn=0`。不传 visitor 隐藏标签，也不接受 playbook 输入。

- 返回 `None` 表示这次没有需要发出的安全事件（含重复或 active 后被抑制的 history_check）；判断器失败在 `state.judge_failures` 与 `state.judge_results` 留痕。
- `SafetyEvent.level` 是本次输入的判档；会话累计级别 `state.highest_level` 只升不降。
- `action=none` 的重复风险判定只供本地状态参考，不写入 `session.safety_events`（契约禁止 action none）。
- 量表阳性总是记录 `scale_item9` 事件且动作非 none：通常为 passive / safety_check，已经 active 时为 active / crisis_protocol。
- `safety_check` / `crisis_protocol` 使用 `layer.script_for_event(event, state)`，返回非空话术时插入；相同 safety_check 只说一次，事件仍照写。`script_for(action)` 只渲染、不去重。`history_check` 按下方流程交给 agent 核验。
- `active` 返回 `crisis_protocol`，由引擎设置 `crisis_exit` 并结束会谈。
- 仅在 event 非 None 且 `event.action != "none"` 时，将 `event.to_dict()` 或 `dataclasses.asdict(event)` 放入 session.safety_events。
- `matched` 保存归一化后的命中片段；`RuleHit.entry_ids` 提供词表条目编号。
- `Violation.field` 是本地定位信息，`severity` 为 hard/soft（默认 hard）。候选使用 `to_hard_rule_violations(violations, change_id)` 序列化，只收 hard；soft 留作本地警告，不能影响门禁是否通过。写入运行 veto 同样只取 hard 的 code/message。
- `check_plan(plan, contraindications, *, age=None, crisis_level="none", config=None)`：默认卧床下限 330；传入 age < 18 且含 sleep_restriction 时硬否决；未检查禁忌仍硬否决；passive + sleep_restriction 仅软警告。调用方应传入年龄和危机级别。W1–W8 硬否决，W9/W10 软警告。

## history_check 引擎接口

判断器标签为 none/history/passive/active，当前风险窗口遵循契约（近 1 个月）。
按顺序分档：P(active) ≥ tau_active → active；P(passive)+P(active) ≥ tau_flag → passive；
否则 P(history) 为最大（含并列）→ level none + action history_check；否则 none。
ambiguous 命中且判断器 ok 时服从分档（history 不升级）；仅 timeout/error 时兜底 passive。
判断器对**除命中明确规则外的所有发言**运行（含被排除的口头禅与普通发言）。
explicit 通过主体/否定约束且无同句 past_time 时优先直接 active；E1/E3 本人主体不明或第三方语境、E4 否认或第三方语境均降级为 ambiguous，不丢弃。同句 past_time 时也改走判断器，成功按其结果（含 history），失败按 passive / rule_ambiguous 兜底。
X1–X8 仅逐区间排除模糊命中，不能抵消 explicit；X9 不丢弃命中，仅在判断器输入追加赖床/补觉提示（DS 的 user message，Choice 的 state/input 文本）。Mock 的关键词只是离线接线占位，不具备完整时态理解。

每个会话首次 history_check 将 `state.pending_history_check` 和 `state.history_check_issued` 置 True，
不提升 `state.highest_level`，不消耗 safety_check。已 active 或已发过 history_check 则不再发出。
升级 active 会清除 pending，交由 crisis_protocol 接管。

引擎收到 history_check 后，把“下一句话须核验来访当前是否仍有此前提到的念头、自伤或尝试”
注入 agent 下一回合。agent 回复后执行：

```python
if state.pending_history_check:
    if not layer.check_verification(agent_text):
        # 按会谈消息契约填入 round/turn 等字段；speaker 必须为 safety。
        append_message(speaker="safety", text=layer.script_for("history_check"))
    state.pending_history_check = False
```

`check_verification(agent_text) -> bool` 是纯检查，从 scripts.yaml 的 `history_verify_patterns`
正则表加载，不自行更改会话状态；无匹配时须由引擎插入兜底，再清除 pending。
`history_check_issued` 保留为 True，防止完成核验后再次触发。来访回答照常过 assess_text，
当前仍有则按 passive/active 升级。固定话术已审定；核验检测要求同一以问号结尾的子句同时有时间限定、风险词和询问，陈述句、回避句不算。
S3/S7 **口径待心理学同学确认（决定清单 D 节）**。为满足子句边界，仅将固定 history 句的“念头，或者”改为“念头或者”，标点调整一并待确认。
本模块提供接口；本次未修改 engine/，上述接线由引擎调用方完成。

## 配置与数据替换

阈值、超时与资源路径集中在 `config.yaml`；相对路径以该配置所在目录为基准。
`load_config(path)` 可加载另一份冻结配置，`SafetyLayer(config)` 接受路径或配置字典。
`JUDGE_PROVIDER` 覆盖配置 provider。评测显式指定 `rules` 或 `mock` 时保持离线；
显式 provider 优先于环境，报告同时记录请求 provider 与实际 provider。
默认引擎路径缺 key/SDK/配置时，记录该 provider 的 `error`，尝试可用的真实后备判断器；全部失败走规则兜底，绝不启用 Mock。
DS 还需要 `DS_MODEL/DS_BASE_URL`。评测指定真实 provider 或 chain 时，缺配置直接报错。
Mock 仅显式 `provider=mock` 时启用，结果 provider 标为 mock，报告注明“mock，不代表识别能力”。
离线/无 key 验收用 `--no-env` 或 `SAFETY_EVAL_NO_DOTENV=1` 禁止读取仓库 `.env`；例如：
`make safety-eval PROVIDER=ds_flash EVAL_ARGS="--no-env --output-dir /tmp/safety-eval"`。

Jev 依赖可选安装：`pip install -r requirements-optional.txt`。
未安装时直接构造 `JevJudge` 会报安装提示；工厂记录 error（作为不可用后备时跳过），严格评测报错。
适配器采用 [TypeSafe 官方 SDK](https://github.com/typesafe-ai/typesafe-sdk-python) 的
`system_one(state=..., questions={risk: Choice(...)})` 与 `answer.probabilities`，选项顺序为 active/passive/history/none。
所有判断调用受 `asyncio.wait_for` 限时；请求错误、超时或非法概率不向会谈抛出。

StartLux 是第四个外部判断器候选，使用必装依赖 `httpx` 异步直连原生协议，不依赖 `typesafe-sdk`。
`make safety-eval PROVIDER=startlux` 读取 `STARTLUX_API_KEY`，缺 key 时严格评测报错，引擎记录 error 并尝试后备判断器。
`STARTLUX_BASE_URL` 留空默认 `https://api.bamboonode.dev`，请求 `POST /v1/decisions`；
`STARTLUX_MODEL` 留空默认 `startlux-decision-27b-autothink`，认证使用 Bearer API key。
依据 [官方 API](https://github.com/StartLuxLabs/StartLux-Decision/blob/main/docs/api.md) 与
[Bamboo 指南](https://bamboonode.dev/docs/ai-model/decisions/startlux)，请求使用 `state + questions`，
从 `answers.risk.probabilities` 读取四键分布，并校验题型、choice、confidence 与概率格式。
复用 `prompts/gemini_decision_zh.json` 中冻结的 history 版中文定义，将选项固定为
**active → passive → history → none**（对应 A–D，与 Jev 的顺序一致，往召回方向偏）。
显式发送 `none_check: false` 和 `allow_none: false`，覆盖 Bamboo 默认值；
内部 `none_probability` 不参与分档，与业务类别 `none` 无关，confidence 也不作分档阈值。
缺项或畸形响应、HTTP 429/5xx 等错误记 `error`，httpx 超时或总时限到期记 `timeout`；不自动重试。
`judge_timeout_s` 为 6 秒，后备 Jev 为 3 秒；层级限时为实际判断器超时（链为各段之和）加 0.1 秒余量。`judge_timeout_overrides` 按 provider 优先覆盖（默认 `startlux: 8.0`）；
自定义旧配置未提供 overrides 时仍使用总默认值。**AutoThink 较慢，演示前按实测冻结**。

Bamboo 托管处于**免费测试期**；目前未找到公开的具体限流上限与测试期后价格，机房地区未确认。
权重采用 [CC BY-NC 4.0](https://huggingface.co/startlux-models/StartLux-Decision-v1.1-27B-AutoThink)，
只可非商用，本项目非商用黑客松演示可用，商用需联系厂商；推理源码为 Apache-2.0，不能替代权重许可。
也可自托管：将 `STARTLUX_BASE_URL` 设为完整端点，例如 `http://localhost:8090/v1/systemone`；
也接受服务根地址或 `/v1` 基址（自动补 `/v1/decisions` 或 `/decisions`）。
工厂仍要求 `STARTLUX_API_KEY`，自托管应按 [部署文档](https://github.com/StartLuxLabs/StartLux-Decision/blob/main/docs/serving_publicly.md)
配置 Bearer key。只发送模拟文本；本次仅用假 transport 验证接线，尚未验证真实 API 可用性、延迟或中文四分类性能。

Gemini Decision 候选使用可选依赖 `google-genai>=3.2.0`（同一可选依赖文件）。
`make safety-eval PROVIDER=gemini_decision` 读取 `GEMINI_API_KEY`，为空时再读 `GOOGLE_API_KEY`；
缺 key 或 SDK 时工厂记录该 provider 的 error 并尝试可用后备；严格评测报错，直接构造且缺 SDK 时给出安装提示。
按 [官方 SDK 3.2.0](https://github.com/googleapis/python-genai/blob/v3.2.0/google/genai/client.py)
使用 `client.aio.decisions.create(model="gemini-decision-1", ...)`，显式配置 `api_version: v1beta`，
对应 [官方端点](https://aistudio.google.com/docs/decisions-api) `POST /v1beta/decisions`。
四档中文定义及指令冻结在 `prompts/gemini_decision_zh.json`，criteria 均为非空字符串；
不依赖选项插入顺序。校验 `choice`、`confidence` 和完整概率分布，将 `probabilities` 映射为 `probs`，
分档继续使用现有阈值，不把 `confidence` 作为新阈值。HTTP 400/402/404/429 等异常记 error，
超时记 timeout；关闭自动重试，正常、失败或取消后均释放客户端资源。

Gemini 免费层输入可能被用于改进产品并由人工审阅，**只能发送模拟文本**，不得发送真实来访信息。
见 [官方数据使用条款](https://aistudio.google.com/docs/terms#data-use-unpaid)。
中国大陆不在 [官方支持地区](https://aistudio.google.com/docs/available-regions)，网络接入需要代理；
代理不改变地区支持范围，也不保证账户可用。本任务未进行真实 API 或大陆网络连通性验证。

正式词表/话术可直接替换 YAML，加载器不限制条数；新建层实例时加载。
按任务要求，testset.jsonl 首行使用 `#` 注释，因此是支持注释的 JSONL；加载器跳过注释/空行，
也支持无注释的标准 JSONL。热线已实测并保留 `verified: true`。

## 报告口径与规格歧义

混淆矩阵行是真值，列是预测，顺序 none/history/passive/active（4×4）；二分类将 passive/active 合并为有风险，none/history 为无风险。
分档召回要求精确命中档位；漏报清单为真值有风险但预测 none/history，分母为零的指标记 null。
`history_recall` 单列历史风险精确命中率；`history_missed` 为 history → none（漏核验），
`history_over_escalated` 为 history → passive/active（过度升级），两者均为条目清单。
延迟按实际调用（含失败）线性插值计算 p50/p95；rules 无调用，延迟为 null。

SPEC 流程图说失败时记录 judge_status，但测试要求无规则命中且失败时返回 None；
实现将结果记入 state，不生成无动作事件，符合 contracts/README 的非 none 动作约定；history_check 的 level 为 none。
“只升不降”作用于会话最高级别，单次事件保留来源对应的实际判档。
contracts 对 hard_rule_violations.code 只限定字符串；为兼容 veto 枚举，所有处方硬否决使用
contraindication_violation，用药建议与禁用措辞使用 forbidden_wording。
文本规则采用已定稿 W1–W10；固定正则不能覆盖所有药名、改写或上下文。当前仓库没有 engine/scoring 调用方，候选序列化使用上述过滤入口，未扩展契约。


### 三栏评测证据与候选文案

`evidence_columns` 分别记录 `rules-only`、`mock`、`real_judge`；离线运行的真实判断器栏为“未测”。
单次真实评测也不自动完成 A2/A4：报告保留“留出集未测”和 `freeze_acceptance.eligible=false`，须由心理学同学完成留出集与阈值审定。
已有开发集对比不等于演示前冻结验收；本修复没有调用真实模型。

`check_text(text, context="user_facing")` 默认按用户可见文本严格检查，“不是诊断”也硬拦。
候选 after 使用 `context="candidate_playbook"`，仅“不要说/禁止使用…”等明确禁止列表豁免；逗号、句号、分号、换行和转折结束豁免范围。
匹配使用 NFKC、小型繁简映射与去空白；英文 W8 保留词边界。W1 包括诊断/确诊/误诊，W2 包括医治失眠症/治好失眠症。
不支持的 context 报错，不静默放行。药物建议继续使用独立否定规则。
