# 只读产物 API

实现依据：团队共享 `read-api-spec.md` v1。HTTP 服务只读 CLI 产物，不执行模型、反思、门禁或 Git 提交。

## 启动

在仓库根目录，使用已安装依赖的 Python（本机为 `/Users/zhangheqing/bohack/.venv-api/bin/python`）：

```bash
API_DATA_SOURCE=files python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

单进程，不使用 `--reload`，放行系统防火墙 TCP 8000。同一局域网通过服务电脑的局域网 IP 访问。
`API_DATA_ROOT` 指向写入 `var/` 的仓库根；省略时为当前 API 代码仓库根，不受启动 cwd 影响。
设置 `API_SERVE_WEB=1` 且当前代码仓库 `web/dist` 存在时，`/` 静态托管前端（hash 路由、无回退、无 `X-Frame-Options`）。API 和 `/docs` 优先于静态挂载。

离线前端开发：

```bash
API_DATA_SOURCE=mock python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

## 实现细节与未指定项的处理

- files 返回的 run_report、session、evolution 原样保留，并经过当前 `contracts/validate.py` 的结构与语义校验。不往契约文档注入来源、请求编号等字段。
- `/runs` 列表 `status=completed`；单项 RunState 沿用旧接口 `status=succeeded`。两者无报告时均为 `running`。
- RunState 的 `progress.completed/failed` 按可读会谈文件统计，`crisis_exit` 计入 completed。总人数优先使用 experiment 对应运行项的可选 `n_visitors`，其次 `summary.attempted`，最后报告 `n_visitors`；均未知时为 null。规范最小 experiment 本身不含人数，因此不能保证进行中有 total。
- 无报告的运行从清单获取 label/role/split/version；没有来源时相关字段为 null，version 可回退到已有会谈。无报告 created_at 使用清单 created_at 或目录修改时间；无 duration_s 时 elapsed_ms=0，不推测运行时长。完成报告的执行来源按 `models.agent` 是否以 mock 开头判断；无报告时参考已有会谈，尚无会谈时按 files 数据源为 real。
- 列表按 ISO 时间对应的时间点倒序，不按带时区字符串直接排序。运行/进化列表跳过单个不可读产物；直接查询该产物返回 404。空数据根返回空列表；缺实验清单返回 `{"available":false}`，不自动造数据。
- 只读 evidence 通过 `run_evidence()` 从报告标签、会谈和 trace 计算，不透传 trace 的调用记录。没有报告或有效 path_probs 返回 `{"available":false}`。数据源未包含 visitor 卡，因此 key_clue_known=false、相关线索指标为 null，不伪造线索证据。
- 只有 status 的进化项，列表 outcome=null；最终 evolution 查询返回 404 NOT_READY。status 和 insights 均原样返回，缺文件为 404 NOT_FOUND。
- Playbook 只读取现有独立 Git 库的 vN tag；不初始化、checkout、reset 或 commit。is_head 依据 tag 对应 SHA 是否等于 HEAD。没有版本库为 404；不存在 tag 为 404。diff 返回 unified diff；同一版本对比为空字符串。
- 文件不存在为 404 NOT_FOUND，进行中报告为 404 NOT_READY；损坏 JSON、非对象/非有限数字、契约不合法或读取/Git 失败为 404 DATA_UNAVAILABLE。错误内容不包含底层异常或文件路径。输入 ID 不合法为 422 VALIDATION_ERROR（路由不能匹配时为 404）。额外拒绝 `.`、`..` 与产物路径中的符号链接；API 不接受磁盘路径参数。
- mock 新接口使用 contracts/examples 的三份报告、已有会谈与 evolution.v1-v2.json。列表中的运行 ID 可由原 GET 接口读取；原 POST 创建的动态运行继续沿用原内存流程。新运行列表用于固定离线示例，不收录动态 Mock 任务。
- contracts/examples 没有独立 experiment/status/insights/playbook 文件，这些 mock 响应由示例字段派生。playbook 文本明确标为 diff 片段，v1 未提供 SHA 时返回 null；不冒充真实完整版本库。evidence 无权重示例时 available=false。
- 不新增 review_request 路由；不暴露 calls.json、预算账本、.env 或其他任意文件。旧 integration_app 保留，见 INTEGRATION.md。

## 验证

```bash
python -m pytest -q api/tests
PYTHONPATH=. python -m pytest -q tests
```

`api/tests/test_read_api.py` 在临时目录构造契约产物、进化 status 和 PlaybookRepo v1→v2，并验证路由、契约、只读性、缺文件、路径越界和静态托管。

---

# 只读数据接口规格 v1（集成用；web/ 与 devconsole/ 共用）

前缀 `/api/v1`，沿用现有错误结构 `{"error":{code,message,request_id}}` 与 `X-Request-ID`。全部 GET，除了已有的 `POST /runs`。

## 数据源
环境变量 `API_DATA_SOURCE=files|mock`（默认 `files`）。`API_DATA_ROOT` 默认仓库根。
- `files`：只读 `FileStore`，读编排器 `python -m engine.demo` 与 `engine.run` 写的产物：
  - `var/runs/<run_id>/{run_report.json, summary.json, sessions/<vid>.json, trace/<vid>.json}`
  - `var/evolve/<evolution_id>/{evolution.json, insights.json, status.json, review_request.json}`
  - `var/playbook-repo/`（独立 git 库，tag v1/v2/…；用 `engine.evolve.repo.PlaybookRepo` 读）
  - `var/demo/experiment.json`（格式见下）
- `mock`：现有 Mock 行为不变；新增路由用 `contracts/examples/` 返回示例（evolution 用 `evolution.v1-v2.json`），供前端离线开发。

## 路由
| 路由 | 返回 |
|---|---|
| `GET /health` | `{status:"ok", data_source:"files"|"mock", execution_mode:"real"|"mock"}`（files 模式为 real） |
| `GET /demo/experiment` | experiment.json 原样；文件不存在 `{"available": false}` |
| `GET /runs?limit=50` | `{items:[{run_id,label,role,playbook_version,split,n_visitors,created_at,duration_s,execution_mode,status,metrics}]}`，created_at 倒序。`execution_mode`：report.models.agent 以 `mock` 开头为 mock，否则 real；`status`：有 run_report=completed，只有 sessions 无报告=running |
| `GET /runs/{id}` | 现有 RunState 结构；files 模式下 progress 由 sessions 计数 / 清单里的计划人数推出，拿不到总数时 total=null |
| `GET /runs/{id}/report` / `/sessions` / `/sessions/{vid}` | 现有结构，files 模式读文件 |
| `GET /runs/{id}/evidence` | `engine.evolve.evidence.run_evidence()` 的 `{summary, visitors}` + `"contract": false`；无 path_probs 时 `{"available": false}` |
| `GET /evolutions?limit=20` | `{items:[{evolution_id,created_at,from_version,to_version,outcome,source_run_id,chosen,phase}]}`；只有 status.json 的进行中项也列出（outcome=null） |
| `GET /evolutions/{id}` | evolution.json 原样；进行中 404 `NOT_READY`；不存在 404 `NOT_FOUND` |
| `GET /evolutions/{id}/status` | status.json 原样 |
| `GET /evolutions/{id}/insights` | insights.json 原样，缺失 404 |
| `GET /playbook/versions` | `{items:[{version,sha,author,message,committed_at,is_head}]}` |
| `GET /playbook/{version}` | `{version, text}` |
| `GET /playbook/diff?from=v1&to=v2` | `{from,to,diff}`（unified diff 文本） |
| `POST /runs`（files 模式） | 501 `RUNS_VIA_CLI`，message 写明「真实运行请在操作员终端执行 make demo-run1 / make demo-run2」 |

## experiment.json（编排器写）
```json
{"experiment_id":"exp-…","updated_at":"ISO+tz","stage":"run1|learning|run2|control|done|failed",
 "run1":{"run_id":"…","playbook_version":"v1","split":"A","state":"pending|running|done|failed"},
 "evolution":{"evolution_id":"…","state":"…"},
 "run2":{"run_id":"…","playbook_version":"v2","split":"B","state":"…"},
 "control":{"run_id":"…","playbook_version":"v1","split":"B","state":"…"},
 "error":null}
```

## 约束
- id 白名单：run_id / evolution_id `^[A-Za-z0-9._-]{1,80}$`，version `^v\d{1,4}$`，visitor_id `^[A-Za-z0-9._-]{1,64}$`；禁止路径穿越，不接受任何路径参数。
- 不透传 `calls.json`、预算账本、`.env`。
- 文件读取失败 → 404/对应错误码，绝不 500 泄露堆栈。
