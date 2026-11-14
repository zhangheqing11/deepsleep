# 安全层骨架

契约以 `contracts/README.md` 和 schema 为唯一真相，`SPEC.md` 补充实现约定；词表、话术与 8 条测试集均为**占位，待心理学同学审定后替换**。
这 8 条的通过率只验证接线和报告流程，不能证明真实场景零漏报。

在仓库根目录运行：

```sh
make venv && make test
make safety-eval PROVIDER=rules
make safety-eval PROVIDER=mock
make contracts
```

`make smoke` 同时运行 contracts 和 test。测试使用假客户端并禁止 socket 连接，不读 `.env`，不调用真实 API。
`python -m safety.eval --provider rules|mock|ds_flash|jev|gemini_decision` 写入配置指定的报告目录。
激活 `.venv` 后也可直接在根目录运行 `pytest`。

## 接入约定

每位来访独立创建 `SessionSafetyState()`，各来访可以并发，同一来访的发言与量表须按会谈顺序调用。
`await layer.assess_text(text, round, turn, state)` 检查来访发言；
`layer.assess_phq9_item9(value, round, turn, state)` 同步检查每次量表结果。
自评表使用 `round=1, turn=0`。不传 visitor 隐藏标签，也不接受 playbook 输入。

- 返回 `None` 表示这次没有需要发出的安全事件（含重复或 active 后被抑制的 history_check）；判断器失败在 `state.judge_failures` 与 `state.judge_results` 留痕。
- `SafetyEvent.level` 是本次输入的判档；会话累计级别 `state.highest_level` 只升不降。
- `action=none` 的重复风险判定只供本地状态参考，不写入 `session.safety_events`（契约禁止 action none）。
- `safety_check` / `crisis_protocol` 直接插入 `layer.script_for(event.action)`；`history_check` 按下方流程交给 agent 核验。
- `active` 返回 `crisis_protocol`，由引擎设置 `crisis_exit` 并结束会谈。
- 仅在 event 非 None 且 `event.action != "none"` 时，将 `event.to_dict()` 或 `dataclasses.asdict(event)` 放入 session.safety_events。
- `matched` 保存命中的原文片段；`RuleHit.entry_ids` 提供词表条目编号。
- `Violation.field` 是本地定位信息；写入候选时由调用方关联 `change_id`，写入 veto 时只取 code/message。

## history_check 引擎接口

判断器标签为 none/history/passive/active，当前风险窗口遵循契约（近 1 个月）。
按顺序分档：P(active) ≥ tau_active → active；P(passive)+P(active) ≥ tau_flag → passive；
否则 P(history) 为最大（含并列）→ level none + action history_check；否则 none。
ambiguous 命中且判断器 ok 时服从分档（history 不升级）；仅 timeout/error 时兜底 passive。
explicit 规则仍优先，未经判断器。Mock 的关键词只是离线接线占位，不具备完整时态理解。

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
当前仍有则按 passive/active 升级。正则及兜底文案均为占位，正式文本需审定。
本模块提供接口；本次未修改 engine/，上述接线由引擎调用方完成。

## 配置与数据替换

阈值、超时与资源路径集中在 `config.yaml`；相对路径以该配置所在目录为基准。
`load_config(path)` 可加载另一份冻结配置，`SafetyLayer(config)` 接受路径或配置字典。
`JUDGE_PROVIDER` 覆盖配置 provider。评测显式指定 `rules` 或 `mock` 时保持离线；
远程模式仍接受环境覆盖，报告同时记录请求 provider 与实际 provider，缺 key 回退标为 `mock(fallback)`。
DS 还需要 `DS_MODEL/DS_BASE_URL`，有 key 但缺这两项会清晰报错，避免误发到其他服务。

Jev 依赖可选安装：`pip install -r requirements-optional.txt`。
未安装时直接构造 `JevJudge` 会报安装提示，工厂回退 mock。
适配器采用 [TypeSafe 官方 SDK](https://github.com/typesafe-ai/typesafe-sdk-python) 的
`system_one(state=..., questions={risk: Choice(...)})` 与 `answer.probabilities`，选项顺序为 active/passive/history/none。
所有判断调用受 `asyncio.wait_for` 限时；请求错误、超时或非法概率不向会谈抛出。

Gemini Decision 候选使用可选依赖 `google-genai>=3.2.0`（同一可选依赖文件）。
`make safety-eval PROVIDER=gemini_decision` 读取 `GEMINI_API_KEY`，为空时再读 `GOOGLE_API_KEY`；
缺 key 或 SDK 未安装时工厂回退 `mock(fallback)`，直接构造且缺 SDK 时给出安装提示。
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
也支持无注释的标准 JSONL。热线占位均标为未核验，不包含虚构电话号码。

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
文本硬否决是固定正则，不能覆盖所有药名、改写或上下文；正式规则仍需审定。
