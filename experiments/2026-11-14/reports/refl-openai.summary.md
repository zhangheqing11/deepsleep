# OpenAI 主反思器实现与验收

日期：2026-11-14。工作目录 `/Users/zhangheqing/bohack/ds-refl`，分支 `zhq/evolve-openai-reflector`，基线 `bfce076`。实现留在工作区，未 commit、push 或修改工作树 Git 元数据；未执行 fetch/rebase。现有完整测试会使用 pytest 临时目录中的独立测试 git 库。

## 交付

- `engine/evolve/llm.py`：新增 OpenAI SDK Responses 客户端，默认 `gpt-6-astra`、`reasoning={"effort": "xhigh"}`。保留 Anthropic 客户端；默认链为所选主提供方 → ds flash。拒答、未完成响应、空输出、SDK 错误、超时与不可用 JSON 均进入已有降级路径。
- `engine/evolve/config.yaml`：默认 provider=openai、model=gpt-6-astra、effort=xhigh、主超时 300 秒。`REFLECTOR_PROVIDER`、`REFLECTOR_MODEL`、`REFLECTOR_REASONING_EFFORT`、`REFLECTOR_TIMEOUT_S` 可覆盖配置，空值使用默认值。Anthropic 的默认模型 / effort 单独保留为 claude-opus-5-5 / high。
- `engine/evolve/reflector.py`：每次主 / 备用调用记录提供方、实际返回模型、effort、耗时、reasoning token、成功状态与错误原因；原有候选提取 / 归一化 / 结构检查继续使用。两边均失败仍返回三份空候选。
- `engine/evolve/pipeline.py`：契约 JSON 保持原有 `reflector.model/fell_back/fallback_reason`；额外元数据写入 `insights.reflector`（含 `attempts`），已验证实际落盘和返回值。
- `.env.example`：增加 OpenAI key、provider、model、effort、timeout 变量，值均留空。
- `engine/evolve/README.md`：配置、切换、日志字段、失败行为和 API 依据已更新。
- `tests/test_evolve_openai.py`：新增 21 项测试，mock SDK 外部边界、使用真实反思解析 / 降级 / 报告代码。

未修改 `contracts/`、`safety/`、`sim/`、会谈引擎、playbook v0 或 prompt；未新增依赖，现有 openai SDK 版本为 3.51.0。三个反思客户端均关闭 SDK 隐式重试（max_retries=0），每次反思至多主请求一次、备用请求一次。ds flash 要求自己的 DS_API_KEY，避免缺失时误用 OPENAI_API_KEY。

API 依据：https://developers.openai.com/api/reference/resources/responses/methods/create

## 本地检查

指定解释器：`/Users/zhangheqing/bohack/ds-safety/.venv/bin/python`。

1. 首批新增回归测试先运行失败（12 failed），确认当时没有 OpenAI 分流、调用记录与新配置行为；完成实现后通过。
2. 最终 `/Users/zhangheqing/bohack/ds-safety/.venv/bin/python -m pytest -q --ignore=api`：**808 passed in 11.32s**，无跳过。
3. `make -o .venv/.requirements-installed contracts`：**10 个契约示例全部 OK**。临时将本工作树 `.venv` 链接到指定解释器所在 venv，并用 `-o` 跳过 Makefile 重建 / pip 安装依赖步骤；运行的是原有 contracts 目标。该临时链接已移除，未改 Makefile 或重建共享 venv。
4. `git diff --check` 通过。改动范围为 `.env.example`、`engine/evolve/` 和新增测试文件。

新增测试覆盖：OpenAI 成功及 reasoning usage、超时（SDK / 外层时限）、API 错误、非法 JSON、空输出、拒答、incomplete、无可用候选；OpenAI / Anthropic 配置切换及 Anthropic 成功；环境变量 / YAML 覆盖；缺 key、无客户端；实际模型 / effort 返回值；usage 不跨调用残留；evolution 契约兼容及 insights 落盘；错误诊断不保存 SDK 响应正文。

## 真实冒烟：累计 3 次调用，已停止调用

密钥仅从 `/Users/zhangheqing/bohack/ds-safety/.env` 读入进程内存，未打印、复制到输出文件或修改源文件。

输入：

- `contracts/examples/run_report.run1.json`
- `engine/fixtures/sessions/A-001.json` 至 `A-003.json`
- `engine/fixtures/trace/A-001.json` 至 `A-003.json`
- 对应 3 份契约 visitor 示例及 `engine/playbook_v0.md`

| 请求 | 提供方 / 模型 / effort | 耗时 | 结果 |
|---|---|---:|---|
| 1 | OpenAI / gpt-6-astra / xhigh，初版带 `text.format=json_object` | 1.737 秒 | HTTP 400，按代码自动降级 |
| 2 | DeepSeek / deepseek-flash / 未设置 | 23.487 秒 | 成功，reasoning tokens=2601；3 份候选，各 3 条改动，结构校验均通过 |
| 3 | OpenAI / gpt-6-astra / xhigh，最终请求不设置 `text.format` | 200.552 秒 | **成功，未降级，reasoning tokens=7768；3 份候选，各 3 条改动，结构校验均通过；无丢弃改动** |

第一轮总耗时 25.227 秒，第二轮总耗时 200.553 秒。第三次为遵守总预算，只注入主客户端（未接入备用）；生产代码仍保留主 → ds flash 链。未发生隐式重试。

初版 HTTP 400 当时仅保存了类型与 HTTP 状态，没有保存响应正文，因此不能断言服务端具体原因。最终移除额外 JSON mode 参数，沿用现有 prompt 请求 JSON，再由既有解析与校验路径检查，已通过真实调用。错误记录现增加安全的 SDK `code/param`，以后可定位参数错误而不保存原始异常正文。

结构校验方式：使用现有 evolution schema 的候选 `id/summary/changes` 子结构，保留本地 `$ref` 解析，按正式 pipeline 约定将 `dimension` 从契约 changes 中剥离后校验；另要求三份候选非空。未伪造 C 验证指标或门禁结果，也未把结构通过当作效果验证。

结果文件（均不提交团队仓库）：

- 最终记录：`/Users/zhangheqing/bohack/ds-refl/var/evolve/openai-smoke/summary.json`
- 最终候选及反思证据：`/Users/zhangheqing/bohack/ds-refl/var/evolve/openai-smoke/reflection.json`
- 初次降级记录与候选：同目录 `attempt-1/summary.json`、`attempt-1/reflection.json`
- 冒烟脚本：`/Users/zhangheqing/bohack/research/codex-tasks/refl-openai.smoke.py`（最终主客户端单次版本；重跑将产生新 API 调用，不属于本次已用完的 3 次预算）

## 使用与验收边界

- 配置由启动进程环境提供，本模块不自动加载 `.env`。切回 Anthropic 时，设置 `REFLECTOR_PROVIDER=anthropic`，同时清空 OpenAI 的 model / effort 覆盖值，或显式设置 `REFLECTOR_MODEL=claude-opus-5-5`、`REFLECTOR_REASONING_EFFORT=high`。
- 本次实际完整反思需要约 **3 分 21 秒**，在 300 秒默认时限内，但明显超过约 1 分钟。短连接测试的约 4 秒不能代表完整失败案例 + S3 证据 + 3 份候选生成的耗时；演示调度需按这个观测值预留时间。
- 没有执行真实 C 集门禁或效果评估，不能据此声称 ISI 等指标提升；真实冒烟未初始化 playbook git 库、未提交任何新版本。
- 本地测试和一次主提供方真实生成已验收；没有远端 CI、合并或部署。
