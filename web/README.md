# web/ — deepsleep 前端

React 18 + TypeScript + Vite。一个项目、两套界面：

| 地址 | 界面 | 内容 |
|---|---|---|
| `#/console`（默认） | 开发者控制台 | 运行与报告（含最近运行、对比）、模拟来访、进化记录、调试 |
| `#/app/chat`、`#/app/settings` | 用户端交互演示 | 聊一聊、我的；**固定示例内容，未连接模型** |

旧链接 `#/runs/:run_id/sessions/:visitor_id` 仍可用。

## 启动

```bash
cd web
npm install
npm run dev          # http://localhost:5173
npm run dev:lan      # 同时监听局域网地址，供手机访问
npm run typecheck
npm run build
```

## 装到手机（PWA）

用户端可以“添加到主屏幕”，打开后全屏显示，进入“聊一聊”。

```bash
npm run build
npm run preview:lan   # 生产构建，终端里会显示局域网地址，如 http://172.20.10.2:4173
```

- 手机和电脑在同一网络（或电脑连着手机热点），用手机浏览器打开上面的地址：iPhone 用 Safari“分享 → 添加到主屏幕”；Android 用 Chrome 菜单“添加到主屏幕 / 安装应用”。
- 离线缓存（`public/sw.js`）只在 **https 或 localhost** 下生效。通过局域网 http 地址添加的图标能正常打开，但需要电脑上的服务在运行；部署到 https 后才能断网打开。
- 缓存规则：页面先走网络、失败才用缓存；`/api/` 请求一律不缓存，接口失败如实显示。发布不兼容的改动时把 `sw.js` 里的 `VERSION` 加一。
- 开发模式（`npm run dev`）不注册离线缓存，避免看到旧代码。

## 数据来源

在 `web/.env.local` 里配置（参考 `.env.example`）：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `VITE_API_ADAPTER` | `mock` | `mock`：前端本地模拟适配器，不需要后端；`http`：请求后端 |
| `VITE_API_BASE_URL` | `/api/v1` | 所有请求的基础地址，只在 `src/config.ts` 读取 |
| `VITE_DEV_PROXY_TARGET` | `http://127.0.0.1:8000` | 开发代理把 `/api` 转发到这里（后端地址待确认） |

- **mock 模式**：页面顶部固定显示“模拟数据”。报告和会谈直接取自 `contracts/examples/` 的正式示例（只读），进度、错误按接口草案模拟。模拟场景可在页面上切换：正常完成、任务失败、报告未准备好、网络不稳。
- 分组与版本的对应关系和后端 Mock 一致：`{split:A}` → 运行 1（A/v1）；`{split:B}` → 对照（B/v1）；`{split:B, playbook_version:v2}` → 运行 2（B/v2）。不填版本时固定 v1，其他组合返回 422。会谈记录只有 A-001 至 A-003，其余显示“无记录”。
- **http 模式 + 后端 Mock**：后端 `GET /health` 返回 `execution_mode=mock` 时，运行页出现“模拟场景 · 后端 Mock 调试”（normal / fail / report_delay），通过请求头 `X-Mock-Scenario` 传给后端，只在开发者控制台出现，用户端（`#/app`）不显示。每次点“开始运行”都生成新的 Idempotency-Key，所以换场景必然换 key；只有“重试提交”沿用原 key 和原场景。后端返回真实执行时不显示、不发送。前端本地模拟的场景（含“网络不稳”）只在 mock 模式出现，两者不混用。
- **联调启动**：后端按 `api/README.md` 在 `127.0.0.1:8000` 启动；**演示时不加 `--reload`、不用多个 workers、演示过程中不重启后端**（与后端约定）。后端运行记录只在内存里，重启后旧 run_id 返回 404，前端提示“找不到这个运行，请重新发起运行”。前端第一轮只对接 8000；后端的 8001 离线引擎入口是后端内部验收用，前端暂不接。前端在 `web/.env.local` 写 `VITE_API_ADAPTER=http` 与 `VITE_DEV_PROXY_TARGET=http://127.0.0.1:8000`，再 `npm run dev`。
- **http 模式**：真实请求失败时只显示错误，**不会**换成模拟数据。

## 目录

```
src/
├── config.ts              接口基础地址、适配器、轮询参数（唯一配置入口）
├── App.tsx                路由分发：控制台 / 用户端
├── api/
│   ├── contractTypes.ts   run_report / session / evolution 类型，手写自 contracts v0.1.0
│   ├── draftTypes.ts      ⚠ 接口草案类型（health、运行状态、错误结构、会谈列表项），未定稿
│   ├── client.ts          ApiClient 接口
│   ├── httpClient.ts      fetch 实现：统一错误结构、request_id、Idempotency-Key
│   ├── mockClient.ts      前端本地模拟适配器
│   ├── errors.ts          ApiError：network / http / invalid_response / aborted
│   ├── requestLog.ts      调试页用的请求记录（仅内存）
│   └── chatDemo.ts        ⚠ 用户端聊天演示剧本（固定回复，接口形状为前端占位草案）
├── hooks/
│   ├── useConsoleRun.ts   控制台“当前运行”状态，切换控制台页面时轮询不中断
│   ├── useChat.ts         演示聊天：发送中 / 失败重试（同一消息 ID）/ 反馈 / 建议 / 记忆确认
│   ├── useRunPoller.ts    1 秒串行轮询；终态停止；卸载 abort；网络失败退避
│   ├── useCreateRun.ts    幂等提交：网络失败后重试复用同一个 key
│   ├── useRunData.ts      health / 报告（409 重试）/ 会谈列表 / 单个会谈
│   └── useResource.ts     可取消的一次性请求
├── layouts/               ConsoleLayout（灰绿外框 + 左侧导航）、AppLayout（手机宽度 + 底部两项导航）
├── pages/console/         RunsPage、VisitorsPage、EvolutionPage（契约示例静态展示）、DebugPage
├── pages/app/             ChatPage、SettingsPage
├── components/            评测流程组件（RunLauncher、RunProgress、ReportView、SessionList、SessionView）与 console/ 子组件
├── lib/                   存储、格式化、中文文案；userDemoStore.ts 是用户端演示的本机偏好与记忆
├── styles.css             颜色变量（日间 / 夜间可手动切换）与基础组件
└── shell.css              控制台外壳与用户端样式
```

## 约定

- 正式指标、路径、转介全部来自后端，前端只做格式化（比例为 null 显示“暂无”，提升用 `path_acc_gain`）。
- 当前运行编号存 `localStorage`，刷新后继续查询；未确认的创建请求存 `sessionStorage`。
- 文案只用“建议”“干预路径”“建议就医”，不使用诊断式表述。
- 学习、playbook 版本、回滚接口未定：进化记录页只静态展示契约示例，没有任何操作按钮。
- 最近运行只记录本机发起的运行；对比页并排展示两份报告的数值、标出较好的一侧，不计算差值（是否由前端计算待团队确认）。
- 用户端演示只能选择预设消息，不开放自由输入：自由输入属于真实用户数据，且演示没有安全层，待团队决定并接入后端聊天接口后再开放。
- 用户端偏好和“我记住的事”只保存在本机浏览器；导出、删除数据等按钮标为“待接入”。
