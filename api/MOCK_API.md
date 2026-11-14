# 第一轮 Mock 联调说明（2026-11-14）

启动时显式设置 `API_DATA_SOURCE=mock`（默认已改为 files）。健康检查额外返回 `data_source: "mock"`。
新增只读示例接口见 [READ_API.md](READ_API.md)；下述创建、进度、失败与幂等行为保持不变。

本轮实现前端确认的接口草案 v0。运行报告与会谈使用正式 contracts v0.1.0。
后端地址：http://127.0.0.1:8000。前缀：/api/v1。
前端 localhost:5173 的 Vite 代理将 /api 转到后端，保留完整前缀，无需跨域配置。
以上 127.0.0.1 适用于前后端在同一台电脑运行；跨电脑不能用该地址访问对方服务。

## 已实现接口

| 方法及路径（不含前缀） | 响应 |
|---|---|
| GET /health | 200，status=ok、execution_mode=mock |
| POST /runs | 202，run_id、status=queued、execution_mode=mock |
| GET /runs/{run_id} | 200，状态、分组、版本、progress、elapsed_ms、report_available、error |
| GET /runs/{run_id}/report | 200，原样契约报告，仅替换顶层 run_id |
| GET /runs/{run_id}/sessions | 200，items 列表 |
| GET /runs/{run_id}/sessions/{visitor_id} | 200，契约会谈，同步替换 run_id 和 session_id |

成功直接返回资源，不包 code/data。所有应用错误包括 422 使用统一结构：

~~~json
{"error":{"code":"RUN_NOT_FOUND","message":"未找到该运行记录，服务重启后请创建新运行。","request_id":"req_example"}}
~~~

正文 request_id 与响应头 X-Request-ID 一致。
未知运行的状态、报告、会谈接口均为 404 RUN_NOT_FOUND；会谈不存在为 404 SESSION_NOT_FOUND；
报告未就绪为 409 REPORT_NOT_READY；请求体或请求头校验失败为 422 VALIDATION_ERROR。

## 创建与幂等

~~~json
{"split":"A"}
~~~

split 只接受 A/B。playbook_version 可选，省略或 null 使用当前 Mock 版本 v1。不接受额外字段。
必须带 Idempotency-Key，建议 UUID；允许 1～128 个 ASCII 字母、数字及 . _ : -。
run_id 是不透明字符串，不含斜线。

- 同 key、相同校验后字段值、相同场景：复用同一 run_id，不重置进度或计时。
- JSON 字段顺序无影响；省略版本与 null 等价；省略版本与显式 v1 视为不同请求。
- 同 key、不同 split / 显式版本 / 场景：409 IDEMPOTENCY_KEY_REUSED。
- 重试仍返回最初的 202 受理响应（status=queued）；实时状态请读取 GET /runs/{run_id}。
- 任务和幂等记录只保存在当前进程内。浏览器刷新可继续查；服务重启后记录清空。

## 版本映射：一个固定的当前版本

| 请求 | 报告示例 |
|---|---|
| A，省略版本或指定 v1 | run_report.run1.json |
| B，省略版本或指定 v1 | run_report.control.json |
| B，显式指定 v2 | run_report.run2.json |

不支持的组合（如 A/v2）返回 422 VALIDATION_ERROR。
这是为了落实“不传版本用当前版本”：当前固定 v1，不能把 B/v2 分数改名为 v1。
若前端希望展示运行 2 示例，请发送 {"split":"B","playbook_version":"v2"}。
Mock 没有真实学习或版本库，不会在执行 B 组时自动切换版本。

## 进度和报告

默认先 queued，再 running，约 4.5 秒后 succeeded，实际时长受调度影响。
任务在后台自行推进，不依赖轮询次数。这是模拟进度，不是实际调用来访或模型。

- 示例为 8 个来访，progress.total=8；completed 不含 failed。
- 正常成功时报告与 succeeded 同时可用。
- elapsed_ms 是本次模拟经过的毫秒数，终态后固定。
- error 为 null 或 {code,message}；fail 场景状态为 failed，无成功报告。
- 建议约 1 秒轮询；failed 停止等待；succeeded 且 report_available=true 后读取报告。

报告只改顶层 run_id。schema_version、created_at、duration_s（秒）、models、指标、
session_ref 均保留正式示例，不代表本次执行时间、模型调用或真实改善。
使用正式字段 metrics.crisis_missed、metrics.path_acc_gain、n_visitors，
不添加 execution_mode、request_id 等额外业务字段；页面根据任务元数据标记 Mock。

## 会谈示例的限制

列表按报告的 8 个 visitor_id 返回；A-001、A-002、A-003 有会谈，A-004～A-008 及全部 B 组暂无会谈。
缺失记录返回 session_available=false、session_status=null；任务技术 status 可为 succeeded。
有记录的来访处理完成后返回 session_available=true，并保留契约会谈状态。

会谈详情保留原文与安全层发言，仅改 run_id、session_id。session_id 为运行 ID / 来访 ID。
不存在或尚不可读的详情返回 404 SESSION_NOT_FOUND。
session_ref 是示例文件路径，不是 HTTP URL；前端应使用会谈查询接口。
不补造缺失会谈，也不修改 contracts/ 的已知引用缺口。

## 可选场景开关

创建时增加 X-Mock-Scenario 请求头，不改请求体。支持：

| 值 | 行为 |
|---|---|
| normal（默认） | 正常结束并立即提供报告 |
| fail | 模拟整体失败，未完成来访全部记 failed；error.code=MOCK_RUN_FAILED；无报告 |
| report_delay | 先 succeeded、report_available=false；默认再等 3 秒提供报告 |

延迟期间报告接口返回 409 REPORT_NOT_READY。失败运行也无报告，应根据 failed 停止等待。
延迟可用 API_MOCK_REPORT_DELAY_S 配置（0.01～10 秒），默认低于前端 30 次轮询等待上限。
同一幂等 key 不能更换场景；换场景请用新 key。直连 CORS 已允许此请求头。

## 手工验收（PowerShell）

在原服务终端 Ctrl+C 后重启服务。以下命令在另一个 PowerShell 执行：

~~~powershell
$apiBase = 'http://127.0.0.1:8000/api/v1'
$runHeaders = @{ 'Idempotency-Key' = [guid]::NewGuid().ToString() }
$mockRun = Invoke-RestMethod -Method Post -Uri "$apiBase/runs" -Headers $runHeaders -ContentType 'application/json' -Body '{"split":"A"}'
$mockRun
Invoke-RestMethod -Uri "$apiBase/runs/$($mockRun.run_id)"
Start-Sleep -Seconds 5
Invoke-RestMethod -Uri "$apiBase/runs/$($mockRun.run_id)"
Invoke-RestMethod -Uri "$apiBase/runs/$($mockRun.run_id)/report"
Invoke-RestMethod -Uri "$apiBase/runs/$($mockRun.run_id)/sessions"
~~~

重复 POST 使用相同 runHeaders 和请求体应返回相同 run_id；修改 split 而不换 key 应返回 409。
5 秒后若仍在运行，继续按实际状态查询，不把固定等待当作成功判据。
也可以打开 /docs，用 Try it out 填入请求体和请求头进行验证。

## 范围

仅限单进程 Mock 联调，不支持多 workers、持久化或真实引擎并发评测。
运行记录与报告不会写入团队仓库。契约、前端、引擎、安全层和评分模块均未修改。

## 本地演示登录（可选）

默认 API_AUTH_MODE=none，保持匿名 Mock 联调兼容。启用 demo 后，/runs、报告、会谈和只读看板接口都要求 Authorization: Bearer <access_token>。GET /health 和登录接口公开；token 只存在后端进程内，重启服务后失效。

POST /api/v1/auth/login
{"username":"demo","password":"demo-pass"}

成功返回 access_token、token_type、expires_in 和 user；前端应将 token 放入 sessionStorage，收到 401 时清除并返回登录页。
