# 安全层骨架

实现依据仅为 `SPEC.md`；词表、话术与 6 条测试集均为**占位，待心理学同学审定后替换**。
这 6 条的通过率只验证接线和报告流程，不能证明真实场景零漏报。

在仓库根目录运行：

```sh
make venv && make test
make safety-eval PROVIDER=rules
make safety-eval PROVIDER=mock
make contracts
```

`make smoke` 同时运行 contracts 和 test。测试使用假客户端并禁止 socket 连接，不读 `.env`，不调用真实 API。
`python -m safety.eval --provider rules|mock|ds_flash|jev` 写入配置指定的报告目录。
激活 `.venv` 后也可直接在根目录运行 `pytest`。

## 接入约定

每位来访独立创建 `SessionSafetyState()`，各来访可以并发，同一来访的发言与量表须按会谈顺序调用。
`await layer.assess_text(text, round, turn, state)` 检查来访发言；
`layer.assess_phq9_item9(value, round, turn, state)` 同步检查每次量表结果。
自评表使用 `round=1, turn=0`。不传 visitor 隐藏标签，也不接受 playbook 输入。

- 返回 `None` 表示这次没有风险事件；判断器失败在 `state.judge_failures` 与 `state.judge_results` 留痕。
- `SafetyEvent.level` 是本次输入的判档；会话累计级别 `state.highest_level` 只升不降。
- `action=none` 的重复风险事件仍需记录；只在非 none 动作时插入 `layer.script_for(event.action)`。
- `active` 返回 `crisis_protocol`，由引擎设置 `crisis_exit` 并结束会谈。
- `event.to_dict()` 或 `dataclasses.asdict(event)` 可直接放入 session.safety_events。
- `matched` 保存命中的原文片段；`RuleHit.entry_ids` 提供词表条目编号。
- `Violation.field` 是本地定位信息；写入候选时由调用方关联 `change_id`，写入 veto 时只取 code/message。

## 配置与数据替换

阈值、超时与资源路径集中在 `config.yaml`；相对路径以该配置所在目录为基准。
`load_config(path)` 可加载另一份冻结配置，`SafetyLayer(config)` 接受路径或配置字典。
`JUDGE_PROVIDER` 覆盖配置 provider。评测显式指定 `rules` 或 `mock` 时保持离线；
远程模式仍接受环境覆盖，报告同时记录请求 provider 与实际 provider，缺 key 回退标为 `mock(fallback)`。
DS 还需要 `DS_MODEL/DS_BASE_URL`，有 key 但缺这两项会清晰报错，避免误发到其他服务。

Jev 依赖可选安装：`pip install -r requirements-optional.txt`。
未安装时直接构造 `JevJudge` 会报安装提示，工厂回退 mock。
适配器采用 [TypeSafe 官方 SDK](https://github.com/typesafe-ai/typesafe-sdk-python) 的
`system_one(state=..., questions={risk: Choice(...)})` 与 `answer.probabilities`，选项顺序为 active/passive/none。
所有判断调用受 `asyncio.wait_for` 限时；请求错误、超时或非法概率不向会谈抛出。

正式词表/话术可直接替换 YAML，加载器不限制条数；新建层实例时加载。
按任务要求，testset.jsonl 首行使用 `#` 注释，因此是支持注释的 JSONL；加载器跳过注释/空行，
也支持无注释的标准 JSONL。热线占位均标为未核验，不包含虚构电话号码。

## 报告口径与规格歧义

混淆矩阵行是真值，列是预测，顺序 none/passive/active；二分类将 passive/active 合并。
分档召回要求精确命中档位；漏报清单为真值有风险但预测 none，分母为零的指标记 null。
延迟按实际调用（含失败）线性插值计算 p50/p95；rules 无调用，延迟为 null。

SPEC 流程图说失败时记录 judge_status，但测试要求无规则命中且失败时返回 None；
实现将结果记入 state，不生成 none 事件，符合 contracts/README 的非 none 事件约定。
“只升不降”作用于会话最高级别，单次事件保留来源对应的实际判档。
contracts 对 hard_rule_violations.code 只限定字符串；为兼容 veto 枚举，所有处方硬否决使用
contraindication_violation，用药建议与禁用措辞使用 forbidden_wording。
文本硬否决是固定正则，不能覆盖所有药名、改写或上下文；正式规则仍需审定。
