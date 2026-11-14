# web/ — deepsleep 前端

React 18 + TypeScript + Vite。一个项目、四套界面（后端开启登录时，都先过登录页）：

| 地址 | 界面 | 内容 |
|---|---|---|
| `#/`（默认，未知地址也回到这里） | 进化看板 | 给评委看的一屏：阶段、主指标对比、学到了什么、怎么回退、安全线；只读，随实验自动更新 |
| `#/console` | 开发者控制台 | 运行与报告（含最近运行、对比）、模拟来访、进化记录、调试 |
| `#/app`、`#/app/v/:visitor_id` | 用户端：来访视角 | 以一位模拟来访的身份看同一句心事的两次回应（学习前 / 学习后）：逐句回放会谈、两场对比、来访自评；**只读实验数据，没有输入框** |
| `#/me`、`#/me/chat`、`#/me/profile`（可带 `/v/:visitor_id`） | 用户视角 | 一位来访自己打开应用会看到的页面：今晚的安排、和教练的对话、我的自评与账号；数据是一位模拟来访与最新一版教练的会谈，**没有输入框** |

旧链接 `#/runs/:run_id/sessions/:visitor_id` 仍可用；旧的 `#/app/chat`、`#/app/settings` 回到用户端首页。

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

用户端可以“添加到主屏幕”，打开后全屏显示，进入用户视角（`#/me`）。

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
| `VITE_API_ADAPTER` | `http` | `mock`：前端本地模拟适配器，不需要后端；`http`：请求后端 |
| `VITE_API_BASE_URL` | `/api/v1` | 所有请求的基础地址，只在 `src/config.ts` 读取 |
| `VITE_DEV_PROXY_TARGET` | `http://127.0.0.1:8000` | 开发代理把 `/api` 转发到这里（后端地址待确认） |

- **mock 模式**：页面顶部固定显示“模拟数据”。报告和会谈直接取自 `contracts/examples/` 的正式示例（只读），进度、错误按接口草案模拟。模拟场景可在页面上切换：正常完成、任务失败、报告未准备好、网络不稳。
- 分组与版本的对应关系和后端 Mock 一致：`{split:A}` → 运行 1（A/v1）；`{split:B}` → 对照（B/v1）；`{split:B, playbook_version:v2}` → 运行 2（B/v2）。不填版本时固定 v1，其他组合返回 422。会谈记录只有 A-001 至 A-003，其余显示“无记录”。
- **http 模式 + 后端 Mock**：后端 `GET /health` 返回 `execution_mode=mock` 时，运行页出现“模拟场景 · 后端 Mock 调试”（normal / fail / report_delay），通过请求头 `X-Mock-Scenario` 传给后端，只在开发者控制台出现，用户端（`#/app`）不显示。每次点“开始运行”都生成新的 Idempotency-Key，所以换场景必然换 key；只有“重试提交”沿用原 key 和原场景。后端返回真实执行时不显示、不发送。前端本地模拟的场景（含“网络不稳”）只在 mock 模式出现，两者不混用。
- **联调启动**：后端按 `api/README.md` 在 `127.0.0.1:8000` 启动；**演示时不加 `--reload`、不用多个 workers、演示过程中不重启后端**（与后端约定）。后端 `API_DATA_SOURCE=files` 时读取运行产物；`mock` 模式的内存运行重启后可能返回 404。前端第一轮只对接 8000；后端的 8001 离线引擎入口是后端内部验收用，前端暂不接。前端在 `web/.env.local` 写 `VITE_API_ADAPTER=http` 与 `VITE_DEV_PROXY_TARGET=http://127.0.0.1:8000`，再 `npm run dev`。
- **http 模式**：真实请求失败时只显示错误，**不会**换成模拟数据。

## 目录

```
src/
├── config.ts              接口基础地址、适配器、轮询参数（唯一配置入口）
├── App.tsx                路由分发：看板 / 控制台 / 用户端
├── api/
│   ├── contractTypes.ts   run_report / session / evolution 类型，手写自 contracts v0.1.0
│   ├── extensionTypes.ts  后端扩展，非契约（运行列表、实验、进化状态、版本等）
│   ├── draftTypes.ts      ⚠ 接口草案类型（health、运行状态、错误结构、会谈列表项），未定稿
│   ├── client.ts          ApiClient 接口
│   ├── httpClient.ts      fetch 实现：统一错误结构、request_id、Idempotency-Key
│   ├── mockClient.ts      前端本地模拟适配器
│   ├── errors.ts          ApiError：network / http / invalid_response / aborted
│   ├── requestLog.ts      调试页用的请求记录（仅内存）
│   └── auth.ts            登录状态：/auth/me、/auth/login、/auth/logout；令牌只放 sessionStorage，不进请求记录
├── hooks/
│   ├── useConsoleRun.ts   控制台“当前运行”状态，切换控制台页面时轮询不中断
│   ├── useRunPoller.ts    1 秒串行轮询；终态停止；卸载 abort；网络失败退避
│   ├── useCreateRun.ts    幂等提交：网络失败后重试复用同一个 key
│   ├── useRunData.ts      health / 报告（409 重试）/ 会谈列表 / 单个会谈
│   ├── useBoard.ts        看板读取循环：任何失败都不停止，失败期间保留上一份数据
│   ├── useReplay.ts       用户端读取循环（实验在跑时跟着刷新）与会谈缓存
│   └── useResource.ts     可取消的一次性请求
├── layouts/               ConsoleLayout（外框 + 左侧导航）
├── pages/board/           BoardPage（进化看板外壳：顶栏、数据来源与连接状态）
├── pages/console/         RunsPage、VisitorsPage、EvolutionPage（后端只读数据）、DebugPage
├── pages/app/             UserApp（来访列表、来访页：会谈 / 对比 / 自评）
├── pages/me/              MeApp（用户视角：今晚 / 对话 / 我的）
├── pages/auth/            LoginPage
├── components/            评测流程组件（RunLauncher、RunProgress、ReportView、SessionList、SessionView）与 console/ 子组件
├── components/board/      看板的纯展示组件：只吃一份 BoardData，不发请求
├── components/app/        用户端的纯展示组件：会谈记录、收尾、两场对比、自评
├── lib/                   存储、格式化、中文文案；board.ts 是看板的数据聚合与结论推导；replay.ts 是用户端的会谈配对与逐步回放；scales.ts 是量表说明与题目；appearance.ts 是本机外观偏好
├── styles.css             颜色变量（日间 / 夜间可手动切换）、内置字体与基础组件
├── shell.css              控制台外壳样式
├── board.css              进化看板样式
├── app.css                来访视角样式（会谈、计划、自评的样式也被用户视角复用）
├── me.css                 用户视角样式
└── login.css              登录页样式
```

## 约定

- 正式指标、路径、转介全部来自后端；前端只格式化指标并计算三方对比的显示差值（比例为 null 显示“暂无”，轮内提升用 `path_acc_gain`）。
- 当前运行编号存 `localStorage`，刷新后继续查询；未确认的创建请求存 `sessionStorage`。
- 文案只用“建议”“干预路径”“建议就医”，不使用诊断式表述。
- 进化记录从后端读取，默认最新一条；进行中轮询状态，审核倒计时使用 `review.deadline`。版本历史、任意两版差异与正文只读展示，不发起学习或回滚。
- 最近运行优先读取 `GET /runs?limit=50`；读取失败时明确提示并显示本机最近 20 条缓存。当前实验每秒串行轮询，done/failed 停止；重新查询可读取新实验。
- 实验完成后一键按“运行 1 / 对照 / 运行 2”对比。差值为运行 2 减对照，比例用百分点；任一值为 null 显示“暂无”。不同分组或相同 run_id 会提示，不把较好数值当作学习效果结论。
- 用户端没有输入框，也不生成任何教练的话：页面上的人只是替模拟来访把会谈记录里的下一句“说出来”，教练、来访、安全层的每一句都原样来自 `GET /runs/{id}/sessions/{visitor}`。开放自由输入仍需团队决定并接入后端聊天接口与安全层。
- 学习前取对照、学习后取运行 2（同一批来访）；对照没跑完时退到运行 1。两侧手册版本相同时称“对照 / 运行 2”，并说明差别不是学习的结果。
- 会谈记录里没有“哪一句出自哪条规则”，用户端只并列展示新规则与两场会谈的差别，不做逐句归因。
- 自评页只展示模拟来访的作答。PHQ-9、GAD-7 用通行中文版题目；ISI、STOP-Bang 有版权，只概括每题看什么。题目与说明待按 BACKLOG B3 审定。
- 外观偏好（深浅色）只保存在本机浏览器。
- **登录**：进入页面时先问 `GET /auth/me`。后端没开登录（`API_AUTH_MODE=none`，默认）时不出现登录页；开启（`demo`）后三套界面都先登录，令牌放 `sessionStorage`，随每个请求以 `Authorization: Bearer` 发出；任何接口返回 `AUTH_REQUIRED` / `INVALID_TOKEN` / `TOKEN_EXPIRED` 都会清掉令牌回到登录页（后端重启后令牌失效属于这种情况）。账号由启动后端的人用环境变量设置，前端没有注册入口，账号密码不落盘、不进调试页的请求记录。前端本地模拟（mock 适配器）没有登录。
- 用户视角与来访视角读的是同一份会谈：默认进入第一位没有触发安全线、和最新一版教练谈过的来访，页面顶部始终标明这是哪位模拟来访的数据。

## 进化后台入口

控制台侧栏底部有一个“进化后台”入口。进化后台是独立的只读应用（`devconsole/`），用来给评委看实时指标和学习过程。点击入口会用普通链接在**新标签页**打开它（`target="_blank" rel="noopener noreferrer"`），原控制台当前的页面和运行不受影响。本次没有做 iframe 副屏和拖拽分栏。

- 地址只在一处配置：`VITE_DEVCONSOLE_URL`（`src/config.ts` 读取）。可以填 `http(s)://` 开头的完整地址，也可以填以 `/` 开头的同源路径。开发期可以指向同机的 devconsole 服务，例如 `http://localhost:5174/devconsole/`；部署时用后端确认的挂载地址，例如 `/devconsole/`。双机演示时不要写 localhost。
- 不填时显示“尚未配置”；填了非法值时显示“地址配置有误”。这两种情况都不会给出链接。
- 入口会读取目标地址下的 `devconsole-meta.json` 标识文件。只有确认目标是进化后台时才显示可点击的链接。如果拿到的是 HTML（例如被 SPA 回退到旧控制台首页）或 404，就显示“待部署”。如果网络不通，链接仍然保留，并提示“未能确认是否已启动”，因为跨域被拦下时也会走到这里。
- 在 Git Bash 里用命令行设置 `VITE_DEVCONSOLE_URL=/devconsole/` 时，路径会被自动改写成 Windows 路径。请写进 `.env.local`，或者在命令前加 `MSYS_NO_PATHCONV=1`。
- 测试：`npm run test:link`。同源托管时，根作用域 Service Worker 与 `/devconsole/` 的共存情况已经实测：`sw.js` 只接管自己的入口导航，断网刷新 `/devconsole/` 时显示浏览器自己的离线错误页，不会显示旧控制台首页。缓存策略没有改动。

## Service Worker 缓存范围与回归测试

- 缓存名由 `deepsleep-web:`、完整注册 scope 和版本号组成，只清理同应用、同 scope 的旧版本。其他应用和其他部署路径的缓存不会被读取或清理。
- 只在安装时预缓存固定的 `index.html`、manifest 与图标；运行时仅缓存本 scope 白名单静态资源和 Vite 带哈希的 JS/CSS。API、未知 GET、查询参数、Authorization、Range 和 no-store 请求均不接管。
- 导航响应从不写入离线缓存。HTTP 错误直接返回；只有入口导航发生网络异常，才使用安装时验证过的静态首页。离线外壳不可用时返回 503。
- 仅缓存 200、未重定向、MIME 匹配且非 private/no-store 的响应。缓存配额满或读取失败时，正常网络响应仍可使用。
- 旧版 `deepsleep-v1` 未记录 scope，无法可靠判定归属，因此不自动删除，也不再读取。每次发布前需更新 `public/sw.js` 中 VERSION；离线 JS/CSS 仍需先成功加载一次。

运行 `npm run test:sw`（Node 20+，无需新依赖）。26 项 Node 回归测试执行实际 `public/sw.js`，用内存 CacheStorage 与受控网络验证隔离、白名单、错误响应、离线回退与缓存故障。它们不替代浏览器安装/升级和真机 PWA 验收。

## 进化看板

- 评委页，站着在一两米外读：字号随视口放大（同时受宽和高约束），1440×900 与 16:9 全屏下主要内容在一屏内。
- 视觉约定：低饱和、不抢眼。唯一的色相家族 `--hue`（偏灰的深青绿）只用在运行 2（进化后的版本）的数据和“变好”上，对照用灰；砖红只表示变差与安全线失守。板块靠各自的低饱和底色分开（`--panel-*`），页面底色比所有板块深一档。
- 主对比是对照与运行 2（同一批 B 组来访）；运行 1 是另一批来访，缩小放在一旁，只作背景。
- 来访点阵把对照与运行 2 按 `visitor_id` 逐个配对；两份报告的来访不一致时不配对，只比较占比。
- 未生成的指标写“尚未生成”或“—”，不画成 0；总人数未知（`progress.total` 为 null）时只报已处理数，不画比例条。
- “保留上一代”按正常结果呈现；反思器降级、模拟数据始终有可见标注（模拟来源取自每次运行的 `execution_mode`，不只看 health）。
- 后端断开时保留最后一份数据并标注时间，恢复后自动接上；看板的轮询不会因 4xx 停止。
- 字体随包内置（Geist，OFL-1.1，只打包拉丁子集），不请求外网；中文使用系统字体。
- 回退命令只展示，不提供按钮：看板不做任何写操作。
- 图表全部手写（`components/board/charts.tsx`，SVG / HTML，无图表库），只画后端给的数据：
  - 副指标对比条：每个指标一行，对照与运行 2 各一个点，越靠右越好；运行 1 是短竖线。缺失的值不画点。
  - 门禁条：每份候选一条，上一代基线是贯穿的竖线；没跑验证的候选不画长度。
  - 4 周 ISI 轨迹（第二屏）：每位来访相对第 0 周的变化是细线，平均是粗线，−7 分是有效线。
  - 问诊证据曲线（第二屏）：读 `GET /runs/{id}/evidence` 的 `summary.by_step`。该接口不在契约里，字段未冻结，结构不符或 `available:false` 时显示“尚未生成”，不画假曲线。
- 数据到达时的过渡只在元素首次出现时播放一次，轮询刷新不重播；系统开启“减少动态效果”时直接显示结果。
- 第一屏是结论、主对比、学到了什么、回退与安全线；轨迹与证据在往下滚动的第二屏。

```bash
npm run test:board   # 聚合缓存、结论推导、图表与各阶段静态渲染；无浏览器或模型调用
npm run test:app     # 用户端：会谈配对、逐步回放、对比与自评的静态渲染；措辞边界
npm run test:auth    # 登录状态机（假 fetch）、令牌存放、登录页与用户视角的静态渲染
```

交叉评审的其他待修项与给 Claude 的分批任务见 [reviews/CROSS_REVIEW_FIXES.md](reviews/CROSS_REVIEW_FIXES.md)。


## 只读数据接口 v1

- HTTP 路径和字段对照集成规格 `read-api-spec.md`，没有改动 `contracts/`。
- 默认 `VITE_API_ADAPTER=http`；离线开发显式设置 `VITE_API_ADAPTER=mock`。health 失败显示“后端不可用”，不切换适配器。
- files 模式的 `POST /runs` 返回 `501 RUNS_VIA_CLI` 时显示后端终端命令，清除未确认提交，不按暂时故障重试。
- 本地 mock 的实验是固定占位；报告、进化来自契约示例。版本元数据是占位，正文只包含契约 diff 的片段；无 path_probs / insights 示例时返回 `{available:false}`。
- 状态扩展对照 `engine/evolve/status.py`（验证和审核可能并行）；`insights` 内部字段未冻结，暂以原始 JSON 类型接收。
- 版本接口没有父提交关系，版本树按 v1/v2/... 排列为版本历史，不推断分支关系。

```bash
npm run test:read-api  # 使用已有 Vite + Node test；适配器、轮询、静态渲染回归，无浏览器或模型调用
npm run typecheck && npm run build && npm run test:sw && npm run test:board && npm run test:app && npm run test:auth
```
