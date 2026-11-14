# 固定安全层

契约以 `contracts/README.md` 和 schema 为唯一真相，`SPEC.md` 补充实现约定；词表与 48 条自写测试集已按 11/14 临床结论替换，固定话术已由心理学同学于 11/14 审定，热线已于 11/14 电话实测并标 verified=true，演示前逐一复核。
本集仅用于排错，不能证明真实场景零漏报，不得据此反复调 prompt。
**0 漏报 = 规则 + 真实判断器联合指标，rules-only 不构成。** mock 仅验证接线，不代表识别能力。演示前必须取得真实判断器漏报数；漏报数 > 0 不得冻结，A2/A4 的验证要求仍保留。

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
- PHQ-9 第 9 题 > 0 总是写入 `source=scale_item9` 事件：既往 active 则 active / crisis_protocol，否则 passive / safety_check，绝不因去重返回 action=none。
- 写入事件后，用 `layer.script_for_event(event, state)` 渲染安全话术；返回空串时不追加消息。它只去重 safety_check 话术，事件照写；`script_for(action)` 是不带状态的模板渲染接口。`history_check` 按下方流程交给 agent 核验。
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
**除命中明确规则外的所有发言都交给判断器**；explicit 无同句 past_time 时优先直接 active；同句 past_time 时改走判断器，成功按其结果（含 history），失败按 passive / rule_ambiguous 兜底。
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
词表加载（risk / question / time / avoidance 四项正则），不自行更改会话状态；无匹配时须由引擎插入兜底，再清除 pending。
`history_check_issued` 保留为 True，防止完成核验后再次触发。来访回答照常过 assess_text，
当前仍有则按 passive/active 升级。固定话术已审定，包含标点在内保持原文不变。核验检测按句末标点（。！？!?；; 或换行）分句，只检查以问号结尾的句子，再按逗号或冒号分小句。风险词与疑问形式（含小句自身的问号）须在同一个小句内，且该小句不能含回避核验表达；时间词可以在该小句内或同一句的前面小句中。时间不跨句继承，不从后文借用；任一句成立即返回 True。
本模块提供接口；本次未修改 engine/，上述接线由引擎调用方完成。

## 配置与数据替换

阈值、超时与资源路径集中在 `config.yaml`；相对路径以该配置所在目录为基准。
`load_config(path)` 可加载另一份冻结配置，`SafetyLayer(config)` 接受路径或配置字典。
`JUDGE_PROVIDER` 覆盖配置 provider。评测显式指定 `rules` 或 `mock` 时保持离线；
显式 provider 优先于环境覆盖；报告同时记录请求 provider 与实际 provider。默认安全层缺 key、SDK 或 DS 模型配置时返回 error 判断器并输出醒目日志；可用的后备判断器仍按冻结链尝试，全部失败时模糊规则按 passive。
MockJudge 仅在显式 provider=mock 时构造，结果带 `warning="mock，不代表识别能力"`；不会自动回退 Mock。DS 还需要 `DS_MODEL/DS_BASE_URL`。

Jev 依赖可选安装：`pip install -r requirements-optional.txt`。
未安装时直接构造 `JevJudge` 会报安装提示；安全层工厂返回 error 判断器或跳过不可用的后备判断器，并写警告。
适配器采用 [TypeSafe 官方 SDK](https://github.com/typesafe-ai/typesafe-sdk-python) 的
`system_one(state=..., questions={risk: Choice(...)})` 与 `answer.probabilities`，选项顺序为 active/passive/history/none。
所有判断调用受 `asyncio.wait_for` 限时；请求错误、超时或非法概率不向会谈抛出。

StartLux 是第四个外部判断器候选，使用必装依赖 `httpx` 异步直连原生协议，不依赖 `typesafe-sdk`。
`make safety-eval PROVIDER=startlux` 读取 `STARTLUX_API_KEY`，缺 key 时继续生成 error 评测报告并写警告，不调用 mock。
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
`judge_timeout_s` 默认 6 秒，`judge_timeout_overrides` 按 provider 优先覆盖（默认 `startlux: 8.0`）；
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
缺 key 或 SDK 未安装时安全层工厂返回 error 判断器；评测继续生成带警告的报告，直接构造且缺 SDK 时给出安装提示。
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

词表与话术已定稿；经授权更新 YAML 后，新建层实例时加载，加载器不限制条数。
按任务要求，testset.jsonl 首行使用 `#` 注释，因此是支持注释的 JSONL；加载器跳过注释/空行，
也支持无注释的标准 JSONL。热线 verified 已于 2026-11-14 电话实测改为 true，演示前须再核验一次。

## 报告口径与规格歧义

混淆矩阵行是真值，列是预测，顺序 none/history/passive/active（4×4）；二分类将 passive/active 合并为有风险，none/history 为无风险。
分档召回要求精确命中档位；漏报清单为真值有风险但预测 none/history，分母为零的指标记 null。
`history_recall` 单列历史风险精确命中率；`history_missed` 为 history → none（漏核验），
`history_over_escalated` 为 history → passive/active（过度升级），两者均为条目清单。
延迟按实际调用（含失败）线性插值计算 p50/p95；rules 无调用，延迟为 null。

SPEC 流程图说失败时记录 judge_status，但测试要求无规则命中且失败时返回 None；
实现将结果记入 state，不生成无动作事件，符合 contracts/README 的非 none 动作约定；history_check 的 level 为 none。
“只升不降”作用于会话最高级别；量表阳性事件继承既往 active，避免已升级后重新发 safety_check。
contracts 对 hard_rule_violations.code 只限定字符串；为兼容 veto 枚举，所有处方硬否决使用
contraindication_violation，用药建议与禁用措辞使用 forbidden_wording。
文本规则采用已定稿 W1–W10；固定正则不能覆盖所有药名、改写或上下文。当前仓库没有 engine/scoring 调用方，候选序列化使用上述过滤入口，未扩展契约。

评测 JSON 的 `evaluation_columns` 始终分为 `rules-only`、`mock`、`真实判断器` 三栏。每次都计算 rules-only 对照；仅显式 mock 才计算 mock 栏；本次没有任何成功的真实判断结果时，真实判断器栏标“未测”，历史报告不自动混入。部分真实请求成功、部分失败时标注“已测（含失败，见警告）”，不得忽略失败数。缺 key 时 CLI 不启动即退出，而是生成带 warnings、error 次数和“未测”标记的报告；退出 0 只表示报告生成成功。已有真实对比文档不因本次离线修复被重新认证。

`check_text(text, context="user_facing")` 为默认严格语境，“不是诊断”也硬拦。候选 `changes[].after` 调用 `context="candidate_playbook"`，才豁免以“不要/禁止/避免/不得/切勿”引导且 12 字内出现诊断类或治疗失眠措辞的禁止子句；逗号、句号、换行及转折后另行检测，不豁免用药建议。非法 context 报错。文本先 NFKC、最小繁简映射，再去空白匹配；同时保留带空白视图，保证英文词边界不丢失。W1 含诊断/确诊/误诊，W2 包含医治/治好失眠变体；W9/W10 仍为 soft。
