# deepsleep 后端：第一轮 Mock 联调

本阶段提供健康检查、Mock 运行创建、进度、契约报告及已有会谈查询。
接口与前端确认的 v0 约定对齐，业务报告和会谈直接读取 contracts/examples/ 的 v0.1.0 示例。
不调用 LLM，不需要 API key，不产生模型费用。execution_mode=mock 表示开发联调，不能作为真实评测或改善证据。
完整接口约定、版本映射、测试场景和手工验收见 [MOCK_API.md](MOCK_API.md)。学习与真实引擎尚未接入。

## 安装和启动（PowerShell）

要求 Python 3.11+。以下命令均在仓库根目录执行：

~~~powershell
python -m venv .venv
& './.venv/Scripts/python.exe' -m pip install -r api/requirements-dev.txt
& './.venv/Scripts/python.exe' -m uvicorn api.main:app --host 127.0.0.1 --port 8000
~~~

已经存在 .venv 时跳过创建步骤。无需激活虚拟环境，也无需调整 PowerShell 执行策略。
仅运行服务时可安装 api/requirements.txt；开发测试额外需要 httpx 和根目录已声明的 jsonschema。
依赖清单自动读取 api/constraints.txt，固定本次验证的依赖版本；升级时需重新测试并更新约束。
开发时可在启动命令末尾增加 --reload；演示时关闭自动重载，避免任务被重启中断。
此前启动的旧服务需要在原终端按 Ctrl+C 后重启，才能加载新接口。
本轮任务和幂等记录均存内存，只支持单进程，不要设置多个 workers。刷新浏览器可继续查询；服务重启或重载后记录清空。

- 健康检查：http://127.0.0.1:8000/api/v1/health
- 接口文档：http://127.0.0.1:8000/docs
- OpenAPI：http://127.0.0.1:8000/openapi.json
- 停止服务：在启动终端按 Ctrl+C。

~~~json
{
  "status": "ok",
  "execution_mode": "mock"
}
~~~

健康检查只证明 HTTP 服务能响应，不检查引擎、模型、评分和版本库是否就绪。

## 配置

配置在服务创建时读取系统环境变量，修改后需要重启。本骨架不会自动加载 .env 文件。

| 变量 | 默认值 | 说明 |
|---|---|---|
| API_EXECUTION_MODE | mock | 当前只支持 mock；设置 real 或其他值会启动失败，避免误报真实模块已接入 |
| API_CORS_ORIGINS | 空 | 允许访问的前端来源，英文逗号分隔；默认不授予跨域权限 |
| API_MOCK_STEP_DELAY_S | 0.5 | 每步模拟间隔，允许 0.01～5 秒 |
| API_MOCK_REPORT_DELAY_S | 3 | report_delay 场景的额外等待，允许 0.01～10 秒 |

前端已确认 http://localhost:5173，通过 Vite 代理请求 /api/v1，不需要 CORS。后端地址确认 http://127.0.0.1:8000。
前后端运行在同一台电脑时适用以上地址；另一台电脑的 127.0.0.1 指向它自己，跨电脑联调需另定可达地址。
如前端需要直连后端，在启动服务的同一个终端设置：

~~~powershell
$env:API_CORS_ORIGINS = "http://localhost:5173"
& './.venv/Scripts/python.exe' -m uvicorn api.main:app --host 127.0.0.1 --port 8000
~~~

来源须包含协议和端口（如有），不含路径。
当前允许 GET/POST 跨域业务请求，允许 Content-Type、Idempotency-Key、X-Mock-Scenario 请求头，暴露 X-Request-ID 响应头，不启用跨域 Cookie。
CORS 不是身份认证。本阶段面向本地开发，尚未设计外网部署和身份认证。

## 错误与请求编号

应用响应携带服务端生成的 X-Request-ID。路由错误、参数校验错误和未处理异常返回：

~~~json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "接口或资源不存在。",
    "request_id": "req_example"
  }
}
~~~

| HTTP 状态 | 错误码 | 含义 |
|---|---|---|
| 404 | RUN_NOT_FOUND / SESSION_NOT_FOUND / NOT_FOUND | 不存在的运行、会谈或接口 |
| 405 | METHOD_NOT_ALLOWED | 不支持该请求方法 |
| 409 | IDEMPOTENCY_KEY_REUSED / REPORT_NOT_READY | 幂等键冲突或报告尚不可读 |
| 422 | VALIDATION_ERROR | 请求参数不符合类型要求 |
| 500 | INTERNAL_ERROR | 未处理的内部异常 |

未处理异常日志仅记异常类型和请求编号，不输出请求正文或异常中的敏感内容。
跨域预检由中间件直接处理，响应格式和请求编号不适用上述业务错误约定。
Idempotency-Key 已实现并发去重；具体请求比较方式见 MOCK_API.md。

## 测试

~~~powershell
& './.venv/Scripts/python.exe' -m unittest discover -s api/tests -v
& './.venv/Scripts/python.exe' contracts/validate.py
& './.venv/Scripts/python.exe' -m pip check
~~~

测试覆盖健康检查、统一错误、跨域、顺序与并发幂等、进度、失败、报告延迟、契约报告、会谈与缺失记录、关闭任务等。
测试内临时增加的验证及失败路由不会出现在实际服务中。
仓库现有 make smoke 仅调用契约校验，尚未包含 10 来访的引擎端到端运行。Windows 可直接运行上述契约校验命令。

2026-11-14：Windows / Python 3.14.3 下 23 项测试通过，包括 Mock 返回数据的 Schema 与适用语义校验。
正式契约示例校验和 pip check 通过；实际启动 Uvicorn 后，A/v1、B/v1、B/v2 的创建、进度、
报告与会谈查询，以及幂等冲突、模拟失败、报告延迟、422 和 404 场景均通过 HTTP 验证。
验证用临时服务已关闭，原有 8000 端口服务未重启；使用新接口前请手动重启原服务。
其他 Python 版本尚未实测。当前 Starlette TestClient 会提示 httpx 使用方式弃用，
但本次测试均通过；后续升级测试依赖时处理，暂不扩展本阶段依赖范围。

## 后续

与前端实测“创建运行 → 查询进度 → 查看 Mock 报告”，确认页面展示和异常反馈。
之后再接入真实引擎、评分、持久化与学习版本管理，不提前复制引擎或评分逻辑。
