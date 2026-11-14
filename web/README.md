# web/ — deepsleep 前端

React 18 + TypeScript + Vite。第一轮只做最小流程：**开始运行 → 显示进度 → 展示报告 → 查看会谈**。

## 启动

```bash
cd web
npm install
npm run dev          # http://localhost:5173
npm run dev:lan      # 同时监听局域网地址，供手机访问
npm run typecheck
npm run build
```

## 数据来源

在 `web/.env.local` 里配置（参考 `.env.example`）：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `VITE_API_ADAPTER` | `mock` | `mock`：前端本地模拟适配器，不需要后端；`http`：请求后端 |
| `VITE_API_BASE_URL` | `/api/v1` | 所有请求的基础地址，只在 `src/config.ts` 读取 |
| `VITE_DEV_PROXY_TARGET` | `http://127.0.0.1:8000` | 开发代理把 `/api` 转发到这里（后端地址待确认） |

- **mock 模式**：页面顶部固定显示“模拟数据”。报告和会谈直接取自 `contracts/examples/` 的正式示例（只读），进度、错误按接口草案模拟。模拟场景可在页面上切换：正常完成、任务失败、报告未准备好、网络不稳。
- 分组与版本的对应关系和后端 Mock 一致：`{split:A}` → 运行 1（A/v1）；`{split:B}` → 对照（B/v1）；`{split:B, playbook_version:v2}` → 运行 2（B/v2）。不填版本时固定 v1，其他组合返回 422。会谈记录只有 A-001 至 A-003，其余显示“无记录”。
- **http 模式**：真实请求失败时只显示错误，**不会**换成模拟数据。

## 目录

```
src/
├── config.ts              接口基础地址、适配器、轮询参数（唯一配置入口）
├── api/
│   ├── contractTypes.ts   run_report / session 类型，手写自 contracts v0.1.0
│   ├── draftTypes.ts      ⚠ 接口草案类型（health、运行状态、错误结构、会谈列表项），未定稿
│   ├── client.ts          ApiClient 接口
│   ├── httpClient.ts      fetch 实现：统一错误结构、request_id、Idempotency-Key
│   ├── mockClient.ts      前端本地模拟适配器
│   └── errors.ts          ApiError：network / http / invalid_response / aborted
├── hooks/
│   ├── useRunPoller.ts    1 秒串行轮询；终态停止；卸载 abort；网络失败退避
│   ├── useCreateRun.ts    幂等提交：网络失败后重试复用同一个 key
│   ├── useRunData.ts      health / 报告（409 重试）/ 会谈列表 / 单个会谈
│   └── useResource.ts     可取消的一次性请求
├── lib/                   存储、格式化、中文文案
└── components/            页面组件
```

## 约定

- 正式指标、路径、转介全部来自后端，前端只做格式化（比例为 null 显示“暂无”，提升用 `path_acc_gain`）。
- 当前运行编号存 `localStorage`，刷新后继续查询；未确认的创建请求存 `sessionStorage`。
- 文案只用“建议”“干预路径”“建议就医”，不使用诊断式表述。
- 学习、playbook 版本、回滚接口未定，本轮未实现。
