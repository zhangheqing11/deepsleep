# PR #7、#10 合并后的遗留项

> #7（临床内容定稿，纯文档）和 #10（后端 Mock 接口）于 2026-11-14 验收通过并合并。以下是验收时发现、不阻塞合并、但需要后续处理的事项。
> 证据：[`raw/pr7-clinical-consistency-review.md`](raw/pr7-clinical-consistency-review.md)、[`raw/pr10-api-review.md`](raw/pr10-api-review.md)。

## A. PR #7（临床内容）

验收范围只到"与代码契约、与其他文档是否一致"。**临床内容本身的对错没有验证**，由心理学同学负责（`docs/review-decisions.md` 记录了他的审核结论，47 项逐条勾选"文本已落实"，不代表临床专家逐条认可）。

已确认一致：32 条词表正则与 48 条测试样例和 PR #6 完全一致；审核结论已落实到草稿。

**4 项高严重度**（都是"文档承诺的硬规则在 PR #6 的代码里没有对应检查"，是代码缺实现，不是文档错）：

| 编号 | 缺口 | 文档位置 | 代码现状 |
|---|---|---|---|
| C1 | V3–V6：核对 `health_conditions`、`snoring_breathing`/`screen_osa`、STOP-Bang ≥3、自判 R1 后仍用睡眠限制 | `domain/plan_veto_rules.md:42-45` | `domain/vetoes.py:30-46` 的 `check_plan` 只读组件、禁忌、checked、可选年龄、危机级别、TIB，没有询问记录/OSA 结果/R1 预测的输入 |
| C2 | V9 / PV-12：有禁忌但缺就医建议组件 → 硬否决 | `plan_veto_rules.md:48,201`、`docs/review-queue.md:65` | 禁忌 `bipolar` + 仅 `sleep_hygiene` + TIB=330 返回 `[]` |
| C3 | F2–F6：保健品、酒精助眠、替就医做保证、保证效果、熬通宵 | `plan_veto_rules.md:80-106` | `domain/veto_rules.yaml` 只有一条 medication-advice 和 W1–W10；"建议补充镁""喝点红酒帮助入睡""不用去医院""保证有效""熬个通宵"均返回 `[]` |
| C4 | 候选硬规则 T3（降低卧床下限）、S1（跳过禁忌询问） | `plan_veto_rules.md` | 文本检查里没有 |

另有 10 项中、5 项低（F1 缺疑问句与咨询医生豁免、契约语义分歧、审核记录未同步等），见原始报告。

**处理方式**：这些应作为 `zhq/domain-vetoes-v2` 单独开 PR 实现（也列在 `pr6-safety-fixes.md` 的 S12）。V3–V6 需要先定输入接口（询问记录、OSA 筛查结果、最终 R1 预测怎么传给 `check_plan`）。

## B. PR #10（后端 Mock 接口）

验收通过：23 项测试全过；实际启动服务逐端点验证与文档一致；返回的 3 份报告和 3 份会谈通过契约校验；16 次路径穿越请求全部 404；CORS 默认关闭、不允许 `*`、`credentials=False`；没有碰 `contracts/`、`safety/`、`engine/`。

| 编号 | 严重度 | 问题 | 要求 |
|---|---|---|---|
| A1 | **高（和契约升级耦合）** | `mocks/fixtures.py:17` 把 `schema_version` 写死为 `0.1.0`；示例改为 `0.1.1` 时 `create_app()` 抛 `ValueError`，服务连健康检查都起不来（已复现）。另外三个报告文件名固定，缺一个就起不来（`:15–16`） | **契约升版本的那个 PR 必须同步改这里**（BACKLOG G1）。建议改成：读取契约 README/schema 里的版本常量，或接受一个允许集合 `{"0.1.0","0.2.0"}`，并在版本不识别时给出清楚的启动报错 |
| A2 | 中 | 任务和幂等记录没有数量上限、淘汰或 TTL：并发 128 个不同键后 `_runs=128, _keys=128, _tasks=128`，全部完成后仍是 `128,128,0`（`api/run_service.py:39-40,66-70,150-156`） | 加最大任务数与记录 TTL，超限返回 429；这是 Mock 阶段，演示前再补也行 |
| A3 | 中 | 运行时不做 JSON Schema 校验：把示例里 `metrics.isi_response_rate` 改成 2，服务照样 202/200 返回（`mocks/fixtures.py:16-27`、`api/routes.py:29-31`） | 启动时用 `contracts/validate.py` 的加载器校验一遍示例，不合格直接启动失败 |
| A4 | 低 | 测试硬编码 8 个来访、3 份 A 会谈、会谈全 completed、B 组无会谈（`api/tests/test_runs.py:78,203,222-226,240-242`）；契约 v0.1.1 补齐示例后会失效 | 改成从示例读取期望值 |
| A5 | 低 | `test_runs.py:87-90` 的"修改 GET 数据不污染快照"只改了客户端解码出的局部对象，检验不到服务端深拷贝 | 改成在服务端状态上断言 |
| A6 | 低 | `api/README.md:8-15` 只有 Windows PowerShell 命令；本机（macOS）需替换解释器与 venv 路径 | 补一份 POSIX 命令 |
| A7 | 低 | 失败/中断的 run 不产出 `run_report`，只覆盖成功运行（`MOCK_API.md` 已写明） | 无需修，登记即可 |
| A8 | 低 | 没有 visitor 与 evolution 查询接口；`session_ref` 24 条中 21 条文件不存在（契约 v0.1.1 分支会补齐） | 随契约升级补接口 |

## C. 与契约升级的关系

契约 v0.1.1（BACKLOG G 节）会让 `models.temperature`、`state_model` 变成必填、示例变多。**A1、A4 会直接被它打破**，升级 PR 要同步处理，否则 `make` 里的 API 测试会红。
