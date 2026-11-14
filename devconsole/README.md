# deepsleep 进化后台（devconsole）

独立的只读展示应用，给评委看三件事：**比什么指标、学到了什么、怎么回退**。原 `web/` 控制台继续负责操作和调试，只在侧栏加一个跳转入口（单独的 PR）。

- 技术栈与 `web/` 相同（React 18.3.1、TypeScript 5.6.3、Vite 5.4.11），有自己的 `package.json` 和锁文件，锁文件的依赖版本和 `web/` 一致。不做 monorepo，也不做共享包。
- 只读：没有发起运行、触发学习、回滚、审批等写操作，所有请求都是 GET。
- 不注册 Service Worker：断网时应该明确显示断连，而不是显示缓存页面。
- 需求来源：统筹会话的《交接：进化后台》修订 2。本轮只做独立应用和新标签页跳转；iframe 副屏、拖拽分栏和嵌入模式留到后续。

## 运行

```bash
cd devconsole
npm ci
npm run dev          # http://localhost:5174/devconsole/
npm test             # 纯前端单元测试（node --test，不新增依赖）
npm run typecheck
npm run build        # 产物在 dist/，资源路径以 /devconsole/ 开头
```

如果 5174 端口被占用，可以用 `npx vite --port <其他端口>` 临时换一个。

## 数据模式（`VITE_DATA_MODE`）

| 值 | 状态 | 数据 | 页面标识 |
|---|---|---|---|
| `mock`（默认） | 可用 | 报告和进化记录读 `contracts/examples` 的正式示例；实验清单、运行进度和学习状态读 `src/fixtures/devSamples.ts` 里手写的**开发样例** | 顶栏显示“数据来源：模拟数据”，页面顶部有黄色横幅 |
| `http` | 可用，但依赖的后端接口**尚未实现** | 读后端只读接口（见下表） | “数据来源：实时后端”，另有连接状态和执行模式 |
| `snapshot` | **未实现** | 回放包，要等后端导出格式（B4）确定 | 页面直接说明不可用，不显示数据 |

填了不认识的值会显示配置错误，**不会悄悄退回 mock**。HTTP 请求失败时也不会改用 mock。

mock 模式可以用 URL 参数切换开发样例，用来检查各种状态下的界面，例如 `/devconsole/?fixture=learning#/overview`：

| `fixture` | 内容 |
|---|---|
| `complete`（默认） | 实验已完成，三份报告和进化记录都是正式示例 |
| `running` | 运行 2 与对照进行中（进度是手写样例），只能读到运行 1 的报告 |
| `learning` | 学习中：候选验证 + 审核窗口 |
| `kept_previous` | 所有候选都没通过，保留上一代（正式示例缺少这个状态，按 BACKLOG G4 手写） |
| `failed` | 学习失败 |
| `none` | 还没有实验 |

开发样例只补正式示例里没有的结构，**不写任何指标数字**，运行 ID 和进化 ID 沿用正式示例里的值。所有 mock 数据都是静态的，不会用定时器制造进度增长。

其他配置见 `.env.example`：`VITE_API_BASE_URL`、`VITE_DEV_PROXY_TARGET`、`VITE_EXPERIMENT_POLL_MS`、`VITE_RUN_POLL_MS`、`VITE_REQUEST_TIMEOUT_MS`。

## 轮询

- 串行：上一个请求结束后才安排下一个，不会堆积；每次请求有单次超时；页面切换或卸载时取消在途请求。
- 当前实验（`/demo/experiment`）**一直轮询**，另一台电脑开始新实验时展示页会自动切换；不依赖本机存储，也不需要手动输入 run_id。
- 运行进度和学习状态到终态后停止轮询；报告在运行完成后再读，遇到 409 `REPORT_NOT_READY` 时稍后重试。
- 失败按 2 / 4 / 8 秒退避。连续失败 3 次后，页面标为“断连 · 数据过期”，保留最后一次成功读到的数据，并继续自动重试。

## 需要的后端接口（只读，待崔秀净确认，**目前 api/ 都还没有实现**）

前缀 `/api/v1`，错误结构和 `X-Request-ID` 沿用现有约定。

| 接口 | 前端怎么用 | 前端能接受的格式 |
|---|---|---|
| `GET /demo/experiment` | 发现当前实验 | `engine/demo.py` 写出的 `var/demo/experiment.json` 原样返回；没有实验时返回 `{"available": false}`（200）。接口不存在（404）会显示成错误，不会当成“没有实验” |
| `GET /runs/{run_id}` | 进度、执行模式 | 现有 Mock 的字段；`progress.completed` 和草案里的 `progress.done` 都能读。`execution_mode` 缺失时显示“后端未提供”。只有后端真的提供 `partial_metrics` 时才显示阶段统计 |
| `GET /runs/{run_id}/report` | 最终指标 | 契约 `run_report`；未就绪时返回 409 `REPORT_NOT_READY` |
| `GET /evolutions/{id}/status` | 学习进度 | `engine/evolve/status.py` 的 `status.json` 原样返回 |
| `GET /evolutions/{id}` | 学到了什么 | 契约 `evolution`；学习进行中返回 404 `NOT_READY`，用来和“不存在”区分 |

需要后端确认的问题：

1. `engine/demo.py` 生成的真实运行 ID（`<experiment>-run1` 等）能不能用 `/runs/{id}` 查到？现在的 Mock `/runs/{id}` 只认自己创建的运行。如果清单里有 ID、详情却返回 404，页面会显示“未找到该运行”。
2. `progress` 字段约定：沿用 Mock 的 `completed / failed / total`，还是草案的 `done`？前端两种都能读，但需要定一个。
3. `partial_metrics` 实际有没有？没有的话，前端只显示进度，最终指标等报告生成后再显示。
4. `review.deadline` 的格式：`status.py` 用的是 `astimezone().isoformat()`，带时区偏移，前端按这个解析，请确认不会改成不带时区的格式。
5. `/devconsole/` 怎么托管：同源（后端用 `StaticFiles` 挂 `devconsole/dist`），还是单独端口？双机演示时，另一台电脑要访问的地址是什么（不能是 localhost）？
6. 如果 `cxj/api-auth-demo` 的 Bearer 鉴权合入，并且这些只读接口也需要鉴权，进化后台要怎么拿令牌？现在前端**不带任何令牌**，也不做登录。

错误样例（前端已有测试覆盖）：404 无错误结构，表示接口未部署；404 `RUN_NOT_FOUND` / `EVOLUTION_NOT_FOUND`；404 `NOT_READY`；409 `REPORT_NOT_READY`；没有错误结构的 502/503，按网络问题处理；200 但不是 JSON（例如 SPA 回退页），显示数据格式错误。

## 原控制台入口的识别文件

`public/devconsole-meta.json` 只包含应用标识。原控制台的“进化后台”入口会读取它，确认目标地址部署的确实是进化后台，而不是被 SPA 回退到别的页面。

## 目录

```
src/config.ts            唯一配置入口
src/lib/settings.ts      配置解析（纯函数）
src/lib/poller.ts        串行轮询
src/lib/shape.ts         结构校验工具
src/api/                 数据接口：client（接口）、httpClient、mockClient、validate、contractTypes（复制自 web）、extensionTypes（后端扩展，非契约）
src/fixtures/            mock 模式的开发样例（手写占位）
tests/                   node --test；tests/support/load.mjs 用 Vite 自带的 esbuild 打包真实源码
```
