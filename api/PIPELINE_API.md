# 全链路演示接口（控制台"一键全链路"用）

> 非契约扩展（不在 `contracts/` 里）。前缀 `/api/v1`，鉴权、错误结构、`X-Request-ID` 与 `READ_API.md` 一致。
> 只在 `API_DATA_SOURCE=files` 下有真实数据；`mock` 数据源下 `GET /demo/pipeline` 返回 `{"available": false, "launcher": {"enabled": false, ...}}`，两个 POST 返回 501。

全链路 = 运行 1（v1，A 组）→ 学习 N 代（反思 → 验证集 C 门禁 → 采纳或保留上一代 →（多代时）用新版本重跑 A 组练习）→ 运行 2（学习后的版本，B 组）与对照（v1，B 组）并行。

HTTP 服务本身不调用模型：`POST /demo/launch` 只是在仓库根目录启动一个子进程 `python -m engine.demo all --reset ...`，进度全部从 `var/` 下的文件读。从终端执行 `make demo-run1` 启动的实验同样能被 `GET /demo/pipeline` 读到。

## 进度文件（`engine.demo` 写）

`var/demo/<experiment_id>/progress.json`，每次有批次开始或结束、每代开始或结束时原子重写：

```json
{
  "schema": "demo-progress/1",
  "experiment_id": "exp-20261115-093000-ab12cd34",
  "started_at": "2026-11-15T09:30:00+08:00",
  "commands": ["run1", "learn", "run2"],
  "generations_planned": 3,
  "mock": false,
  "batches": [
    {"run_id": "exp-...-run1", "role": "run1", "version": "v1", "split": "A", "total": 45,
     "state": "done", "started_at": "...", "finished_at": "...",
     "generation": null, "candidate": null, "replicate": 1}
  ],
  "generations": [
    {"index": 1, "evolution_id": "exp-...-learn-g1", "from_version": "v1", "state": "done",
     "started_at": "...", "finished_at": "...", "outcome": "committed", "to_version": "v2"}
  ]
}
```

- `batches[].role`：`run1` | `validation` | `practice` | `run2` | `control`。
- `batches[].state`：`running` | `done` | `failed`。`total` 是该批来访数。
- `validation` 批次带 `generation`（第几代，从 1 起）、`candidate`（`null` 表示基线，否则 `c1`/`c2`/`c3`）、`replicate`（第几次重复，从 1 起）。`practice` 批次的 `generation` 是它之后那一代要用它来反思的上一代序号（即刚被采纳的那一代）。
- `generations[].state`：`running` | `done` | `failed`；`outcome`：`committed` | `kept_previous` | `null`。
- `validation` 批次的 `version` 是去掉重复后缀的门禁标签（`v1`、`v1+c2`），`replicate` 从标签的 `#rN` 解析。
- 另有顶层 `updated_at`（每次重写时更新）。时间戳精确到毫秒。
- 分步执行（`run1` → `learn` → `run2` 分开跑）时续写同一个文件，`commands` 累加。
- 实验失败时，仍处于 `running` 的批次和代被标为 `failed`。

没有这个文件的旧实验，`GET /demo/pipeline` 只按清单（`experiment.json`）给出粗粒度步骤。

## `GET /api/v1/demo/pipeline`

```json
{
  "available": true,
  "experiment_id": "exp-...",
  "mode": "real",
  "state": "running",
  "error": null,
  "started_at": "...", "updated_at": "...", "finished_at": null,
  "elapsed_s": 212.4,
  "eta_s": 180,
  "generations_planned": 1,
  "playbook": {"from_version": "v1", "current_version": "v1"},
  "steps": [],
  "result": {"run1": null, "control": null, "run2": null, "delta_pp": null},
  "launcher": {}
}
```

- `available=false` 时只有 `available` 和 `launcher`。
- 附加字段：`stage`（清单原样的 `stage`）、`progress_available`（`false` = 旧实验，只有粗粒度步骤，没有验证批次）。
- `mode`：`real` | `mock`。`state`：`running` | `done` | `failed`。实验结束（`done`/`failed`）后，还没开始的步骤报 `skipped`，仍在 `running` 的步骤与批次报 `failed`。
- 子进程由本服务启动、已退出而清单未到终态时报 `failed`；这个判断只在同一个服务进程内有效（重启服务后，被强杀的旧实验会一直显示 `running`，直到下一次启动覆盖它）。
- `elapsed_s`：从 `started_at` 到现在（已结束则到 `finished_at`）。`eta_s`：剩余时间估计（秒），结束、失败或无法估计时为 `null`。
- `result.run1` / `control` / `run2`：对应运行的报告生成后为 `{"isi_response_rate", "referral_recall", "referral_precision", "n", "playbook_version"}`，否则 `null`。`delta_pp` = (运行 2 − 对照) 的 ISI 有效率百分点差，任一缺失为 `null`。

### `steps[]`（按执行顺序；未开始的步骤也列出，`state` 为 `pending`）

```json
{
  "key": "gen1",
  "kind": "generation",
  "label": "学习 · 第 1 代",
  "detail": "反思运行结果，提出 3 份候选，在验证集 C 上过门禁",
  "state": "running",
  "started_at": "...", "finished_at": null,
  "elapsed_s": 95.0, "expected_s": 200, "eta_s": 105,
  "batches": [],
  "generation": {}
}
```

- `key`/`kind`：`run1`/`run`；`gen<i>`/`generation`；`practice<i>`/`practice`（只在计划代数 > 1 时出现，位于第 i 代之后、且只到第 N−1 代——最后一代之后不练习；第 i 代未采纳、学习已结束或下一代已开始而没有练习批次时 `state` 为 `skipped`）；`final`/`final`（运行 2 与对照）。
- `state`：`pending` | `running` | `done` | `failed` | `skipped`。
- `expected_s`：该步骤预计总时长；`eta_s`：该步骤剩余时间（非 running 时为 `null`）。估计方法：同一实验里已完成的同类步骤的实际时长优先（`practice`/`final` 没有同类样本时借用运行 1 的时长），否则用启动预设里的默认值（本服务启动的实验用其预设；其他实验按计划代数选：1 代 = `live`，否则 `full`；`mock` 实验用很小的默认值）。运行类步骤在已有会谈完成时改用会谈完成速度外推。顶层 `eta_s` = running 步骤的 `eta_s` 之和 + pending 步骤的 `expected_s` 之和。
- `batches[]`：属于该步骤的批次，见下。
- `generation`（仅 `kind=generation`，尚未开始时为 `null`）：

```json
{
  "index": 1, "evolution_id": "exp-...-learn-g1", "from_version": "v1",
  "phase": "validating",
  "reflector": {"state": "done", "model": "gpt-6-astra", "fell_back": false},
  "baseline_isi": 0.522,
  "candidates": [
    {"id": "c1", "state": "running", "isi": null, "passed": null},
    {"id": "c2", "state": "pending", "isi": null, "passed": null},
    {"id": "c3", "state": "pending", "isi": null, "passed": null}
  ],
  "outcome": null, "to_version": null, "chosen": null
}
```

  - `phase` 原样取自 `var/evolve/<evolution_id>/status.json`：`reflecting` | `validating` | `committing` | `done` | `failed`。`reflector` 同样原样取自 status。
  - `baseline_isi` / `candidates[].isi`：该代已完成的基线 / 该候选各次重复的 ISI 有效率均值，一次都没完成时为 `null`。
  - `candidates[].state`：`pending` | `running` | `done`。`passed`：该代结束后取自 `evolution.json`（门禁是否通过），之前为 `null`。附加 `candidates[].status`：status.json 里的原始状态（`blocked` / `empty` / `error` 都归为 `state=done`，靠它区分）。候选列表来自 status；反思尚未完成时默认列出 `c1`–`c3`。
  - 附加 `baseline_state`：status 里的基线状态（`skipped` = 沿用上一代被采纳候选的评估，此时 `baseline_isi` 取上一代被采纳候选的 ISI；该代结束后若批次里没有基线则取 `evolution.json` 的 `baseline_val_metrics`）。
  - `outcome` / `to_version` / `chosen`：该代结束后取自 status。

### `batches[]`

```json
{"run_id": "exp-...-learn-v1_c1", "role": "validation", "label": "候选 1 · 第 1 次",
 "version": "v1+c1", "split": "C", "total": 30, "completed": 12, "failed": 0,
 "state": "running", "started_at": "...", "finished_at": null, "duration_s": null,
 "isi_response_rate": null}
```

- `completed` / `failed`：`var/runs/<run_id>/sessions/*.json` 里已写出的会谈数（`status == "error"` 计入 `failed`）。
- `label`：`运行 1`、`基线 · 第 n 次`、`候选 k · 第 n 次`、`练习（vN）`、`运行 2`、`对照`。
- `isi_response_rate`：该批的 `run_report.json` 生成后取 `metrics.isi_response_rate`，否则 `null`。
- 附加 `generation` / `candidate` / `replicate`（同进度文件）。旧实验的批次 `total` 取报告的 `n_visitors`，`started_at`/`finished_at` 为 `null`，`duration_s` 取报告的 `duration_s`。

### `launcher`

```json
{"enabled": true, "state": "running", "pid": 12345, "preset": "live",
 "started_at": "...", "exit_code": null,
 "presets": [
   {"key": "live", "label": "现场模式", "generations": 1, "description": "运行 1 → 学习 1 代 → 运行 2 与对照", "expected_s": 400},
   {"key": "full", "label": "完整模式", "generations": 3, "description": "运行 1 → 学习 3 代（含自我练习）→ 运行 2 与对照", "expected_s": 1500}
 ],
 "log_tail": ["experiment_id=exp-..."]}
```

- `enabled`：服务端设置了 `API_DEMO_LAUNCH=1` 才为 `true`。为 `false` 时控制台只读地显示进度，启动按钮禁用并提示"在终端执行 make demo-run1"。
- `state`：`idle`（本服务进程没有启动过子进程）| `running` | `exited`（保持到下一次启动）。
- 附加 `mock`（上次启动是否 mock）、`stopped`（是否经 `POST /demo/stop` 停止）。预设的 `expected_s` 由服务端默认步骤时长算出（当前 `live` 400、`full` 1480）。
- `log_tail`：子进程标准输出与标准错误合并后的最后 20 行（来自 `var/demo/launcher.log`），不含任何密钥（名字含 KEY/TOKEN/SECRET/PASSWORD 的环境变量值会被替换为 `***`）。`enabled=false` 时为空。

## `POST /api/v1/demo/launch`

请求体：`{"preset": "live", "mock": false}`。`preset` 必填，取 `launcher.presets[].key`；`mock` 默认 `false`，为 `true` 时子进程加 `--mock`（不调用任何模型，用于检查流程和界面）。

预设写死在服务端代码里（赛规：现场不能改参数）：

| preset | 代数 | 反思器档位（子进程环境变量 `REFLECTOR_REASONING_EFFORT`） |
|---|---|---|
| `live` | 1 | `low` |
| `full` | 3 | `high` |

子进程命令：`<当前 Python> -m engine.demo all --reset --generations <N> --visitor-renderer template [--mock]`，工作目录为仓库根，输出重定向到 `var/demo/launcher.log`（每次启动覆盖）。子进程继承服务环境（另设 `PYTHONUNBUFFERED=1`、`PYTHONUTF8=1`），在独立进程组（Windows `CREATE_NEW_PROCESS_GROUP`）/ 会话（POSIX `start_new_session`）中运行。`launcher.log` 与 `.lock` 位于 `API_DATA_ROOT` 下；子进程总是写仓库根的 `var/`，所以一键启动只在 `API_DATA_ROOT` 为仓库根（默认）时有意义。

- 202：`{"pid": 12345, "preset": "live", "mock": false}`。实验编号由子进程生成，前端随后从 `GET /demo/pipeline` 读到。
- 403 `LAUNCH_DISABLED`：没有设置 `API_DEMO_LAUNCH=1`。
- 409 `ALREADY_RUNNING`：本服务启动的子进程还在运行，或 `var/demo/.lock` 被另一个 demo 命令占用。
- 422 `VALIDATION_ERROR`：未知预设、缺少 `preset` 或请求体有多余字段。
- 检查顺序：501 → 403 → 422 → 409。
- 501 `RUNS_VIA_CLI`：`mock` 数据源。

## `POST /api/v1/demo/stop`

终止本服务启动的子进程（及其子进程树：Windows `taskkill /PID <pid> /T /F`；POSIX 先 `killpg(SIGTERM)`，5 秒未退出再 `SIGKILL`）。200：`{"stopped": true}`；409 `NOT_RUNNING`：没有在运行的子进程；403 `LAUNCH_DISABLED`。停止后清单里的 `stage` 可能仍是运行中状态，`GET /demo/pipeline` 在"子进程已退出但清单未到终态"时把 `state` 报为 `failed`，`error` 为"已手动停止"或子进程退出码说明。
