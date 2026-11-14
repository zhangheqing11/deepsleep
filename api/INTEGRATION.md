# 离线引擎集成（开发验收用）

这个入口用于在没有真实模型调用、没有 API 费用的情况下，把固定版本的上游 engine、sim、scoring 和 safety 串起来验收。它不替代正式 A/B 评测，也不改变前端已经使用的 Mock API。

## 两个服务

| 地址 | 入口 | 用途 |
| --- | --- | --- |
| http://127.0.0.1:8000 | api.main:app | 前端第一轮 Mock 联调，路径为 /api/v1/runs |
| http://127.0.0.1:8001 | api.integration_app:create_integration_app --factory | 固定快照离线引擎集成，路径为 /api/v1/integration/runs |

两个入口可以同时运行。8000 的接口契约、X-Mock-Scenario、内存运行记录和前端代理约定保持不变。8001 使用 SQLite 保存运行、会谈和报告；它是单进程开发服务，不要使用多个 workers。

## 首次准备

在仓库根目录执行。脚本只从本地已经存在的 Git 对象导出固定提交，不会联网，也不会合并上游分支。

~~~powershell
./.venv/Scripts/python.exe -m pip install -r api/requirements-integration.txt
./.venv/Scripts/python.exe -m api.prepare_integration
~~~

快照写入被 .gitignore 忽略的 var/integration-deps/。启动时会校验文件 SHA-256、固定提交和模块来源；快照被改动或缺失时服务拒绝启动。

## 启动

~~~powershell
./.venv/Scripts/python.exe -m uvicorn api.integration_app:create_integration_app --factory --host 127.0.0.1 --port 8001
~~~

不要加载 .env，也不要设置真实模型的替换入口。这个入口会显式注入 Mock agent、Mock 路径分类器、Mock 访客和 Mock 安全判断器；报告中的 execution_mode 仍为 mock，并额外标记 execution_source=engine_offline。

## 手工验收

另开 PowerShell，先创建 1 个 sample 运行，然后查询状态、报告、会谈列表和 sample-001 详情：

~~~powershell
$key = [guid]::NewGuid().ToString()
$created = Invoke-RestMethod http://127.0.0.1:8001/api/v1/integration/runs -Method Post -Headers @{ 'Idempotency-Key' = $key } -ContentType application/json -Body '{"split":"sample","limit":1}'
$created
$runId = $created.run_id
Invoke-RestMethod http://127.0.0.1:8001/api/v1/integration/runs/$runId
Invoke-RestMethod http://127.0.0.1:8001/api/v1/integration/runs/$runId/report
Invoke-RestMethod http://127.0.0.1:8001/api/v1/integration/runs/$runId/sessions
Invoke-RestMethod http://127.0.0.1:8001/api/v1/integration/runs/$runId/sessions/sample-001
~~~

limit 可取 1 到 18。建议先跑 1 个确认流程，再跑 10 个检查批量结果。相同幂等键和相同请求会复用原运行；相同幂等键改请求会返回 409 IDEMPOTENCY_KEY_REUSED。

## 结果如何解释

成功运行的会谈和报告来自真实上游代码，但输入是 sample 来访，状态模型参数仍是占位参数，所有模型组件都是 Mock。每个会谈先通过 contracts 校验，任何会谈失败、超时或契约不兼容都会使整个运行进入 failed，不会生成部分汇总分数。

运行报告仍然照实执行评分和否决规则。当前 10/18 个样例的实测报告包含 2 例 crisis_missed，因此 veto.passed=false；这是上游安全验收未通过的真实结果，后端不会改写成成功。该集成链路通过不等于安全机制已经通过比赛门禁。

S2 模拟访客会跨两轮保留自己的透露/否认状态；当前 S2 接口不会消费第一轮状态模型的 round1_outcome，这个限制会记录在会谈 trace 中，待上游接口升级后再移除。

## 重启和持久化

默认数据库为 var/integration/runs.sqlite3，可通过 create_integration_app(database_path=...) 在测试中指定。服务关闭或重启不会自动重跑未完成任务，会把它们标为 RUN_INTERRUPTED。已经落盘的 completed / crisis_exit 会谈会在恢复时计入 completed；未确认的报告会被清除，避免把半成品当成成功结果。

## 测试

~~~powershell
./.venv/Scripts/python.exe -B -m unittest discover -s api/tests -v
~~~

测试覆盖原 Mock API、实际离线引擎 1/10/18 个样例、契约校验、无网络调用、并发、幂等、SQLite 重启恢复、快照完整性、报告和会谈查询。测试使用临时数据库；var/ 下的运行数据不会进入 Git。

## 当前边界

- 尚未接入真实 ds flash、Opus 或外部模型服务。
- 尚未接入 A/B/C 正式数据、40–50 并发的比赛规模、学习反思器和 playbook 版本演示。
- 8001 不是前端第一轮 Mock 联调的替代服务；前端继续使用 8000，除非双方另行约定集成接口。
