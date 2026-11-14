# Windows 评委一键演示

`scripts/demo.ps1` 会把本地实验、只读 API 和网页串起来。默认使用 Mock，适合赛前彩排；只有显式指定 `-Mode real` 才会调用真实模型。脚本不会把密码、API key 或 `var/` 运行产物提交到 Git。
也可以直接双击仓库根目录的 `demo.bat`，它等价于运行默认的 Mock 彩排并自动打开浏览器；命令行调用时写 `.\demo.bat -Mode mock` 即可。
正式评委演示请在已经合入登录功能的最新 `main` 上运行；如果当前工作树还没有 `web/src/pages/auth/LoginPage.tsx`，脚本会提前停止，避免启动一个网页会收到 401 的旧前端。

## 第一次准备

在仓库根目录执行：

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\python.exe -m pip install -r api/requirements.txt
```

确认已安装 Node.js 18+。脚本第一次运行时会在 `web/node_modules` 不存在时执行 `npm ci`。

## 离线 Mock 彩排

```powershell
.\scripts\demo.ps1 -Mode mock -OpenBrowser
```

脚本会依次完成：

1. 构建 `web/dist`；
2. 重置独立 playbook 仓库到 v1；
3. 执行运行 1（A 组）；
4. 在 C 组验证候选并记录门禁结果；
5. 执行运行 2 与 v1 对照（B 组）；
6. 启动 `API_DATA_SOURCE=files` 的 FastAPI；
7. 等待 `/api/v1/health` 返回 `status=ok`；
8. 打开本地演示页面。

Mock 模式使用 3 个来访，主要用于验证链路，不代表最终量化成绩。网页登录默认开启。脚本会安全提示输入密码；也可以在当前 PowerShell 进程预先设置：

```powershell
$env:DEMO_PASSWORD = '<只存在于当前进程的演示密码>'
.\scripts\demo.ps1 -Mode mock -OpenBrowser
```

不要把这条命令写进脚本、提交记录或截图。若只需本机无登录检查，可临时使用 `-NoAuth`。

## 真实模型彩排

真实模式不会从缺少密钥时自动降级为 Mock。先在当前 PowerShell 进程配置：

```powershell
$env:DS_BASE_URL = 'https://<兼容 OpenAI API 的地址>'
$env:DS_API_KEY = '<只存在于当前进程的密钥>'
$env:DS_MODEL = '<模型名>'
.\scripts\demo.ps1 -Mode real -OpenBrowser
```

真实模式默认使用 `data/visitors/A`、`B`、`C` 的完整分组。现场演示前先确认服务商限流和预计耗时；不要在日志、截图或 PR 中暴露 `DS_API_KEY`。

## 评委现场流程

脚本完成后浏览器会打开本地地址（默认 `http://127.0.0.1:8000/`）：

1. 登录演示账号；
2. 先打开“进化看板”，展示运行 1、学习、运行 2、对照和安全线；
3. 打开“来访视角”，选择一个来访查看会谈详情；
4. 回到“控制台”展示运行报告和 playbook 版本链；
5. 说明 `crisis_missed=0`、C 组门禁和候选是否提交。

如果看板显示 `kept_previous`、运行 2 与对照都为 v1，应如实说明候选未通过门禁，系统保留上一代；不要把它描述成已经产生 v2 提升。

## 常见问题

- **端口被占用**：脚本不会覆盖已有服务，会提示 PID；先关闭旧的 uvicorn，或使用 `-Port 8010`。
- **网页显示 401**：登录页需要使用当前服务输出的演示账号；服务重启后旧 token 会失效。
- **真实模式缺少 DS_* **：这是保护措施，补齐环境变量后重新运行；不会静默使用 Mock。
- **需要脚本启动后立即返回**：使用 `-StopOnExit`；这适合自动化检查，服务会在脚本结束时停止。默认行为是保持服务运行，演示结束按 Enter 停止。
