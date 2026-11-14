# deepsleep PR #10 后端 Mock 联调接口验收审查

审查日期：2026-11-14。对象：[PR #10](https://github.com/zhangheqing11/deepsleep/pull/10)，作者 Cuixiujing；head `e657c64621fd876fa9733f4183696443953d8e3e`，base `163213604c953ab020dbc2e22c61dbdfbc80abd4`。

本报告记录事实、复现条件及证据，不给出是否合并的结论。审查目标是供前端王译旋对着 contracts 示例 JSON 开发的本地 Mock 接口；真实引擎与临床安全层效果不属于本次实测范围。

已阅读 AGENTS.md（含第 2、3、6 节）、docs/BACKLOG.md、contracts/README.md、api/README.md、api/MOCK_API.md，以及本 PR 源码、测试和现有校验器。使用了直接相关的 code-review-and-quality 审查技能。旧记忆仅用于定位项目背景，以下项目状态均以本次文件、远端 PR 与运行证据为准。

环境：macOS / Darwin arm64，Python 3.14.5；新建项目内 `.venv`，按 `api/requirements-dev.txt` 及其递归引用的 `api/requirements.txt`、根目录 `requirements.txt`、`api/constraints.txt` 安装。根目录没有 constraints.txt，实际约束文件在 api/ 内。全部临时脚本、日志、隔离示例均放在 `evidence/`。运行时设置 `PYTHONDONTWRITEBYTECODE=1`，避免在源码目录生成缓存。

## 1. 发现与边界

以下每条按“[高/中/低] 一句话 + 证据”记录；“低”中有明确的范围限制或核查事实，不全部代表代码缺陷。

- [高] **当示例的 schema_version 升为 0.1.1 时，当前服务会在应用创建阶段抛错，连健康检查都无法提供。** 证据：`mocks/fixtures.py:17` 严格要求 `0.1.0`，`api/main.py:43` 在创建应用时构造目录，`api/main.py:117` 导入即调用 create_app；隔离复制全部示例、仅改 schema_version 后，`create_app()` 抛 `ValueError: Mock 需要 contracts v0.1.0 示例，请先核对契约升级。`（附录 D `version-0.1.1`）。这是已复现的升级阻断条件；当前 v0.1.0 启动正常。
- [中] **不同幂等键可持续创建后台任务，运行记录和幂等记录没有数量限制、淘汰或 TTL。** 证据：`api/run_service.py:39`、`:40` 创建永久字典，`:66`～`:70` 无上限地存储和 create_task，`:150`～`:156` 只取消/清理任务集合；隔离服务并发接受 128 个不同键后 `_runs=128, _keys=128, _tasks=128`，全部成功后变为 `128,128,0`，close 后仍为 `128,128,0`（附录 D）。本次未跑到内存耗尽，未声称 128 个任务就会崩溃；风险是连续创建时积累。
- [中] **运行时没有执行 JSON Schema 校验，结构错误的本地示例可能被当作成功报告原样返回。** 证据：`mocks/fixtures.py:16`～`:27` 仅做版本、报告人数/ID 唯一性检查；`api/routes.py:29`～`:31` 报告只声明返回 dict；在隔离副本中将 `metrics.isi_response_rate` 改为 2，仍得到 POST 202、report 200，独立 Draft202012Validator 报 `2 is greater than the maximum of 1`（附录 D `invalid-contract`）。这是对错误/升级示例的防护缺口，**不是当前正式示例返回了无效报告**；原有测试会校验其当时读取的示例。
- [低] **测试对 8 个来访、3 份 A 会谈、全部会谈 completed 和 B 组无会谈有硬编码，补全/调整示例会使这些断言失效。** 证据：`api/tests/test_runs.py:78`、`:203`、`:222`～`:226`、`:240`～`:242`；隔离副本改为 9 个唯一来访且同步 n_visitors 后，服务实际返回 `progress={total:9,completed:9,failed:0}`；将 A-001 会谈改为 error 后，列表真实保留 `session_status=error`（附录 D）。服务人数来自明细，并未固定为 8；当前断言随示例变化需同步。
- [低] **“调用方修改 GET 数据不能污染服务快照”的这段测试不能检验内部深拷贝是否存在。** 证据：`api/tests/test_runs.py:87`～`:90` 只修改 `report.json()` 在客户端解码出的局部对象，再发一次 GET；修改局部对象没有调用能改变服务状态的代码。该断言不能证明内部 deepcopy 的必要性或正确性；整项测试还有真实的状态、原文件不变、契约校验等有效断言，未发现 `assertTrue(True)` 一类纯占位整项测试。
- [低] **失败或中断的 run 不产出 run_report，因此“任何一次运行产出契约 JSON”在本 Mock 中仅覆盖成功运行。** 证据：`api/run_service.py:81`～`:83`、`:100`～`:107` 明确把 report 设为 None；实测 fail 场景 `failed/0 completed/8 failed/report_available=false`，report 接口 409；`api/MOCK_API.md:66`、`:92`～`:95` 已明确文档化。这是当前范围与 AGENTS.md 第 9 节字面要求的差异，不是文档未告知的行为。
- [低] **本 PR 没有 visitor 或 evolution 查询接口，且报告引用的 24 份会谈中只有 3 份实际示例存在。** 证据：`api/routes.py:16`～`:41`、OpenAPI 只有文档列出的六种接口；对 `/api/v1/visitors/A-001` 和 `/api/v1/evolutions` 实测 404；3 个报告共 24 条 session_ref，按示例目录解析存在 3 条、缺失 21 条；A-001～A-003 详情 200，其余 A 及全部 B 详情 404。`api/MOCK_API.md:74`～`:83` 已声明此限制，缺失引用来自现有契约示例，本 PR 未补造数据。
- [低] **README 提供的是 Windows PowerShell 命令，在本机需替换解释器与虚拟环境路径才能执行。** 证据：`api/README.md:8`～`:15`；本机 `command -v python: None`、`command -v pwsh: None`、`.venv/Scripts/python.exe exists: False`。使用 `python3` 与 `.venv/bin/python` 的等价步骤后安装、启动、测试全部成功（附录 A/B）。这属于已标注平台的操作限制，未验证 Windows 原命令。

## 2. 环境、README 步骤与全部测试

- [低] **依赖按清单可安装且本次所有已安装业务/测试包都受精确版本约束。** 证据：`api/requirements-dev.txt:1`～`:4` 递归引入运行和根目录依赖；`api/requirements.txt:2` 引入同目录 constraints；`api/constraints.txt` 使用 `==` 固定 22 个包，本次安装与 freeze 对应，pip check 退出码 0。requirements 本身是范围，实际安装时 constraints 生效；未做包哈希锁定或漏洞数据库审计。完整安装输出：[setup.log](evidence/setup.log)，完整版本：[freeze.log](evidence/freeze.log)。
- [低] **API 全部 23 项测试通过，契约校验器对 10 份现有示例均返回 OK。** 证据：附录 A 原始标准输出/错误合并日志与退出码；测试用时 3.526 秒。出现 Starlette 关于 httpx 的弃用警告，不影响本次退出码。
- [低] **README 的等价 POSIX 操作能从全新环境完成，服务在 127.0.0.1:8000 启动并正常退出。** 证据：附录 B。逐端点 HTTP 检查使用同一源码的独立 Uvicorn 进程，默认配置端口 51292，指定 CORS 配置端口 51371；两进程均退出码 0。没有重启或终止别人的服务。

执行顺序：创建 `.venv` → `pip install -r api/requirements-dev.txt` → `unittest discover -s api/tests -v` → `contracts/validate.py` → `pip check` → 启动服务并发送 HTTP 请求 → SIGINT 正常关闭。安装仅附加了 `--no-cache-dir --disable-pip-version-check`，避免写用户缓存；没有调整依赖版本。未执行会重新建环境的 Makefile 目标；`Makefile:12`～`:14` 显示 smoke 目前只是 contracts，不代表引擎端到端测试。

## 3. 文档端点逐项验收

前缀均为 `/api/v1`。原始请求、请求体、状态码、响应头和完整响应正文保存在 [http-transcript.json](evidence/http-transcript.json)；脚本见 [http_review.py](evidence/http_review.py)。这轮记录 141 次 httpx 请求及 16 次 curl 路径探测，另有未逐条落盘的就绪/状态轮询；311 个检查点均通过，**不是新增了 311 项项目测试**。成功响应全文样本在附录 C。

| 文档端点 | 实际结果 | 与 MOCK_API.md 一致性 |
|---|---|---|
| GET /health | 200，`{"status":"ok","execution_mode":"mock"}` | 一致 |
| POST /runs | 202，返回不含斜线的 run_id、queued、mock | 一致；缺少幂等键、额外字段、非法 split、A/v2 均 422 |
| GET /runs/{run_id} | 200，初始 queued，终态 succeeded；含 split、version、progress、elapsed_ms、report_available、error、mock | 一致；正常默认耗时实测 4505～4513 ms |
| GET /runs/{run_id}/report | 正常终态 200；与对应示例深度比较，唯独顶层 run_id 替换 | 一致；未就绪和失败运行 409 REPORT_NOT_READY |
| GET /runs/{run_id}/sessions | 200，items 共 8 项；A 有 3 项 available，B 全部 unavailable | 一致；技术 status=succeeded 与 session_available 可分别为 true/false |
| GET /runs/{run_id}/sessions/{visitor_id} | A-001、A-002、A-003 200，仅 run_id/session_id 替换；其余 404 SESSION_NOT_FOUND | 一致；未完成时详情也 404 |

| 请求/场景 | 实际报告或行为 |
|---|---|
| A 省略版本、A 显式 v1 | run_report.run1.json，v1 |
| B 省略版本、B 显式 v1 | run_report.control.json，v1 |
| B 显式 v2 | run_report.run2.json，v2 |
| 同键重试相同请求 | 返回相同 run_id，仍 202/queued；实际终态需查 GET |
| 省略版本与 null | 同键复用同一 run_id |
| 省略版本改成显式 v1、改 split、改 scenario | 同键返回 409 IDEMPOTENCY_KEY_REUSED |
| fail | 约 1000 ms 后 failed，completed=0/failed=8，不提供报告 |
| report_delay | 约 4505 ms 后 succeeded 且 report_available=false，约 3 秒后 true；elapsed_ms 仍 4505 |
| 未知 run 的状态/报告/列表/详情 | 全部 404 RUN_NOT_FOUND |
| 错误 envelope | error={code,message,request_id}；业务错误正文 ID 与 X-Request-ID 一致 |

附录 C 的正常状态、报告和会谈是**实际响应**，包括固定示例时间及模型名；它们不能作为本次调用真实模型的证据。

## 4. 契约符合性、字段与示例加载

- [低] **实际返回的 3 种报告与 3 种现有会谈均通过当前 Draft202012Validator 与现有适用语义检查，没有新增或改名业务字段。** 证据：独立 HTTP 脚本调用 `contracts.validate.load_validators()` 和 `validate_document()`；该加载器在 `contracts/validate.py:57`～`:69` 用 Draft202012Validator、referencing.Registry、Resource 和 FormatChecker 本地解析 `$ref`。报告严格等于对应示例改顶层 run_id，会谈严格等于对应示例改 run_id/session_id。重复正常场景及延迟场景也分别校验通过，结果见 [http-checks.json](evidence/http-checks.json)。
- [低] **visitor 和 evolution 的通过结果只对应磁盘示例，不是接口返回验证。** 证据：附录 A 中 3 份 visitor 与 1 份 evolution 全 OK；当前没有对应返回接口，不能把本地文件通过写成 HTTP 支持。
- [低] **execution_mode、progress、report_available 等是单独的 API 任务元数据，不被塞进正式 run_report/session 对象。** 证据：`api/run_models.py:17`～`:54` 定义受理、进度、列表模型；报告/会谈的 schema 为严格业务对象，实际响应检查未发现额外字段；`api/MOCK_API.md:69`～`:72` 明确区分。任务元数据本身没有在 contracts/ 下新增 schema，属于本 PR 文档化的 API 层结构，不应拿它当 run_report 校验。
- [低] **FixtureCatalog 的路径相对源码文件定位，不依赖启动时当前目录。** 证据：`mocks/fixtures.py:7` 使用 `Path(__file__).resolve().parents[1] / "contracts" / "examples"`；把进程 CWD 改为 `/private/tmp`、用 PYTHONPATH 指向项目后仍加载到 reports=3、sessions=3，退出码 0（附录 D）。正常 `uvicorn api.main:app` 的模块发现仍需从项目根目录或显式设置导入路径，和示例路径定位是两件事。

读取文件明细：固定读取 `run_report.run1.json`、`run_report.run2.json`、`run_report.control.json`；再 glob `session.*.json`，当前得到 `session.A-001.json`、`session.A-002.json`、`session.A-003.json`。不加载 visitor.* 或 evolution.*；不按 HTTP 传入的文件名读取。所有文件在服务创建时加载到内存，运行时 snapshot 深拷贝，不会自动重读修改过的示例。

## 5. 安全与资源边界

- [低] **本次构造的路径穿越没有读取到 examples 以外的文件。** 证据：使用 `curl --path-as-is` 避免客户端归一化，分别将下表 8 种 payload 放进 run_id 与 visitor_id，共 16 请求全部 404；响应只含统一错误，未含 AGENTS.md 内容或本机绝对路径。单/双重 URL 编码、反斜线、绝对路径、NUL 均包含在测试内。`api/run_service.py:109`～`:113`、`:144`～`:148` 只查内存字典；不存在将这些参数拼成文件路径的代码。

| payload | run_id 路径结果 | visitor_id 路径结果 |
|---|---|---|
| `../AGENTS.md` | 404 NOT_FOUND | 404 NOT_FOUND |
| `../../AGENTS.md` | 404 NOT_FOUND | 404 NOT_FOUND |
| `%2e%2e%2fAGENTS.md` | 404 NOT_FOUND | 404 NOT_FOUND |
| `%2e%2e%2f%2e%2e%2fAGENTS.md` | 404 NOT_FOUND | 404 NOT_FOUND |
| `%252e%252e%252fAGENTS.md` | 404 RUN_NOT_FOUND | 404 SESSION_NOT_FOUND |
| `..%5c..%5cAGENTS.md` | 404 RUN_NOT_FOUND | 404 SESSION_NOT_FOUND |
| `%2fetc%2fpasswd` | 404 NOT_FOUND | 404 NOT_FOUND |
| `%00AGENTS.md` | 404 RUN_NOT_FOUND | 404 SESSION_NOT_FOUND |

- [低] **没有可控制文件名的业务参数，也没有写/删文件端点。** 证据：OpenAPI 只列六种接口，唯一 POST 为创建内存 run；DELETE/PUT/PATCH `/runs/{id}` 实测 405。向创建请求附加 `filename=../../AGENTS.md` 返回 422；向 report 添加 filename/file/path/session_ref 查询参数，响应与原报告完全相同（这些未知查询参数被忽略）；`playbook_version=../AGENTS.md` 返回 422。`mocks/fixtures.py` 只使用 read_text，api 与 mocks 没有运行输出落盘实现。
- [低] **CORS 默认关闭来源授权，显式来源可用，禁止星号，credentials=False。** 证据：`api/config.py:13`、`:26`～`:41`，`api/main.py:106`～`:112`；默认预检 400、无 Allow-Origin/Allow-Credentials；显式 `http://localhost:5173` 时预检 200 且只返回该来源，未配置来源 400；带 Origin 的 404 业务错误也带正确 CORS 头。设置 `API_CORS_ORIGINS=*` 时 Settings 抛 ValueError（附录 D）。预检正文是中间件纯文本，没有 X-Request-ID，符合 README 的预检例外。
- [低] **HTTP 错误未回显本机路径，进程启动错误仍可能在本地控制台出现路径。** 证据：所有路径探测/422/404/409 响应无绝对路径；在仅测试实例上添加抛 FileNotFoundError(绝对路径) 的路由，返回 500 INTERNAL_ERROR，`path_leaked=false`，日志只有异常类型和 request_id。隔离重命名示例导致构造器 FileNotFoundError，其异常字符串含隔离副本路径（附录 D）；它发生在应用创建阶段，服务未就绪，不是远端 HTTP 信息泄露。
- [低] **常规未处理异常会转为可观察错误状态，而不是静默返回成功。** 证据：`api/main.py:68`～`:77` 记录类型/请求号并返回 500；`api/run_service.py:95`～`:97` 记录类型/run_id 并标 failed；取消任务在 `:92`～`:94` 标 RUN_INTERRUPTED 后重新抛出。`:155` 的 gather(return_exceptions=True) 用于关闭时收拢已取消任务；`:57` 则会将 snapshot 内的 KeyError 统一映射为 422，可能降低排查错误示例的精度，但当前有效示例没有触发错误映射。

资源限制：配置给单步延时设置 0.01～5 秒、额外报告延时 0.01～10 秒，并拒绝 nan/越界值；8 条明细时预计正常 `(8+1)*0.5=4.5` 秒，最大配置延迟 `(8+1)*5+10=55` 秒，不含事件循环调度开销。**没有全局任务数量上限、排队容量、请求频率限制、记录清理、通用任务 deadline，也没有 API 层请求体大小限制。** 本次 128 个任务是隔离服务对象的有限资源探测，不是网络压测或长期容量结论；单进程限制及重启丢失已写入 README。

`config.py` 只读取以下四个环境变量，不读 DS_*、ANTHROPIC_API_KEY，不自动载入 .env，也没有默认密钥：

| 环境变量 | 默认值 | 实际约束 |
|---|---|---|
| API_EXECUTION_MODE | mock | 只能 mock；real 启动失败 |
| API_CORS_ORIGINS | 空 | HTTP(S) 来源；不允许通配符、路径、认证信息；去重并去尾斜杠 |
| API_MOCK_STEP_DELAY_S | 0.5 | 有限浮点数，0.01～5 |
| API_MOCK_REPORT_DELAY_S | 3 | 有限浮点数，0.01～10 |

证据：`api/config.py:43`～`:59`，附录 D 配置输入探测。没有模型调用客户端，故未产生模型 API 费用。

## 6. 与锁定决定及职责范围的关系

- [低] **接口明确表明 Mock，只有脱离任务元数据单独展示报告时才会丢失该标识。** 证据：health、POST 受理、GET run 状态均含 execution_mode=mock；OpenAPI 描述明确“不调用真实模型”；`api/MOCK_API.md:69`～`:72` 要求页面根据任务元数据标记。报告与会谈保留示例 models/created_at/duration_s，不能代表本次执行；本审查没有真实前端，未确认 UI 最终是否展示标记。
- [低] **成功 run 提供当前有效的报告，但真实 40～50 来访并发、评分、学习、门禁、playbook 版本库与回滚尚未实现。** 证据：`api/run_service.py:76`～`:91` 逐条 sleep 后复制模板，FixtureCatalog 直接读取已有结果；接口不连接 engine/safety/scoring，`api/MOCK_API.md:119`～`:122` 明确限定 Mock。本次未把示例分数的高低或危机指标当作实际学习/安全成绩。
- [低] **远端 PR 的变更范围仅为 api/ 与 mocks/，没有碰 contracts/、safety/、engine/。** 证据：GitHub 文件清单为 16 个新增文件、1125 行新增、0 删除；远端 patch 重建内容与本地 16 个文件逐一一致（[pr-export-match.json](evidence/pr-export-match.json)）。导出本身无 .git，故通过远端 PR 元数据与 patch 核对，而非相信 README 自述。远端证据：[pr-remote.json](evidence/pr-remote.json)。

## 7. v0.1.1 兼容性与示例耦合

| 耦合点 | 代码证据 | 实测/影响 |
|---|---|---|
| schema_version 严格等于 0.1.0 | mocks/fixtures.py:17 | 改成 0.1.1 即应用创建失败（已复现） |
| 固定三个报告文件名，全部必须存在 | mocks/fixtures.py:15～:16 | 重命名 run_report.run1.json 即 FileNotFoundError（已复现），即使只想查看 B 也无法创建应用 |
| 默认 playbook v1 | mocks/fixtures.py:11；api/run_service.py:54 | 如果新版示例不再提供 v1，省略版本的请求无法找到映射；这是代码推导，未假称真实 v0.1.1 已改版本 |
| 报告关键字段硬读取 | mocks/fixtures.py:17～:22；api/run_service.py:60～:65 | 依赖 schema_version、per_visitor[].visitor_id、n_visitors、split、playbook_version、run_id 保持结构；人数只要求非空且 ID 唯一/数量一致 |
| 会谈连接键 | mocks/fixtures.py:24～:35 | glob 文件名后按原始 run_id、visitor_id、playbook_version 连接；连接不上就显示 unavailable，不读取 session_ref 指向的文件 |
| 新增 models.temperature、state_model | mocks/fixtures.py:29～:36；api/run_service.py:87、:91、:131、:148 | 深拷贝整个 dict，不枚举/裁剪字段；隔离保留旧 schema_version、仅添加示意字段时，report/session 200 且字段保留 |
| 新会谈状态 | api/run_models.py:50；api/run_service.py:140 | completed/crisis_exit/error 均被模型允许；隔离 error 示例可呈现，但现有测试断言全部 completed |
| 示例数量与可用性 | api/tests/test_runs.py:78、:222～:242 | 服务支持 9 条的探测通过；测试和文档仍写 8、3、B 无详情 |
| 新的跨文件校验规则 | contracts/validate.py；api/run_service.py:60～:63 | 动态 run_id/session_id 与保留的磁盘 session_ref/模板元数据如何被新校验器关联，尚待真实 v0.1.1 联测 |

新增字段探测只用于证明“不会裁剪未知新增字段”，使用了 `temperature={agent:0,visitor:0}` 与 `state_model={version:"probe-only",params_digest:"probe-only"}` 的隔离示意值；**没有把它当作已定稿的新契约，也没有声称通过真实 v0.1.1 Schema**。仅加字段不改版本的探测不绕过生产服务中的实际版本拒绝：真实版本号一旦升为 0.1.1，前述高项仍会触发。

## 8. 原文件完整性

- [低] **本次审查未修改、删除导出目录内任何既有文件，也未在 .venv 之外新增文件。** 证据：执行前后 SHA-256 清单对比共 45 个原文件，`changed=[]`、`deleted=[]`、`added_outside_venv=[]`（[readonly-check.json](evidence/readonly-check.json)）。新增 `.venv` 属用户允许范围；报告和复现材料在导出目录之外。所有本次启动的 Uvicorn 进程已关闭。

## 我没能验证的事项

- Windows / PowerShell 原始命令、Python 3.11/3.12/3.13、Windows 路径和网络行为：本次仅在 macOS/Python 3.14.5 实测。README 已记录作者的 Windows 结果，本报告没有将其当作独立复验。
- 前端真实页面、Vite 代理、浏览器跨域执行，以及页面是否持续显示 Mock 标识；本次完成的是后端 HTTP 与 CORS 头验证。
- 真正的 v0.1.1 schema、示例全集和新校验器联调；本次只有版本号与新增字段/数量/状态的隔离兼容性探测。
- 真实模型、40～50 个来访的真实会谈并发、冻结规则状态模型、危机 0 漏报、转介门禁、学习收益、候选选择、playbook git 回滚：本 PR 没有对应实现，未做相关效果判断。
- 长时间压力、内存耗尽点、网络级吞吐量、多 worker、持久化、外网部署与认证；本次 128 个任务探测不能替代容量测试。
- 完整依赖漏洞、供应链与跨平台安装矩阵；本次核验了约束生效、安装、pip check 和实际测试。

报告只陈述上述证据，不作是否合并的结论。
