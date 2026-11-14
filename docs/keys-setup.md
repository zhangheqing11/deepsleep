# API Key 申请与连通性检查

核查日期：2026-11-14。以下入口来自官方站点；未实际注册账户，也未从中国大陆网络逐家实测。网络可达性与账户／地区资格是两件事，VPN 本身不代表满足服务地区要求。无法核实的条件标为“待确认”。

背景参考：`~/bohack/research/1114/1-jev.md`、`5-gemini-decision.md`、`6-yuandian.md`；关键配置和申请入口已再次查阅下列官方来源。所有检测仅发送固定模拟文本，不使用真实来访数据。

## 1. DeepSeek（ds flash）

- **申请官网**：[DeepSeek 开放平台](https://platform.deepseek.com/)。[登录页](https://platform.deepseek.com/sign_in)提供手机号／邮箱入口；完成账户注册与页面要求的验证。当前是否额外要求实名认证、哪些地区的号码可注册：待确认。
- **海外网络／VPN**：国内服务，通常无需海外网络；本次未做大陆直连实测，现场可达性待确认。
- **免费额度**：本次未确认面向所有新账户的固定赠送额度或长期免费 API 层，待确认；不要把网页聊天免费等同于 API 免费。以账户余额和[官方价格页](https://api-docs.deepseek.com/quick_start/pricing)为准。
- **生成位置**：开放平台的 [API keys](https://platform.deepseek.com/api_keys) 页面创建密钥。
- **填写变量**：密钥填入 `DS_API_KEY`；同时填写下列两个配置。当前[官方首次调用文档](https://api-docs.deepseek.com/)明确给出 OpenAI 兼容地址与 `deepseek-flash` 模型名；它目前由 DeepSeek-V4.1-Flash-1017 提供服务。旧 Flash 名称仍被接受，但对应旧模型已经退役。

```dotenv
DS_BASE_URL=https://api.deepseek.com
DS_MODEL=deepseek-flash
```

检测脚本复用 `DsFlashJudge.classify`；三项均填好才请求一次。没有另行换模型或回退到 Mock。

## 2. TypeSafe / Jev

- **申请官网**：[TypeSafe](https://typesafe.ai/)，进入 [Console](https://console.typesafe.ai/)。登录页支持 Google 或邮箱；按提示完成邮箱验证。[账户帮助](https://help.typesafe.ai/articles/4519713419-how-do-i-create-or-activate-my-account-after-an-invitation-or-waitlist-approval)明确注册已开放，无需候补批准。
- **海外网络／VPN**：是否必须使用海外网络待确认，未取得中国大陆直连保证，也未实测。可按团队现有网络条件检查，不应把超时直接解释为 key 错误。
- **免费额度**：[官方费用说明](https://help.typesafe.ai/articles/5187202169-how-much-does-jev-cost)明确不提供免费或试用额度；先在 Settings → Billing 预付充值。余额用完可能返回 402。当前价格为每百万输入 token 0.042 美元，输出免费。
- **生成位置**：[Console → Settings → Keys](https://console.typesafe.ai/settings/keys)，创建 API key；[官方快速开始](https://docs.typesafe.ai/introduction/quickstart)也指向该控制台。
- **填写变量**：`TYPESAFE_API_KEY`。检测使用 `JevJudge.classify`；需 `typesafe-sdk`，安装要求见仓库 `requirements-optional.txt`。

## 3. Google AI Studio（Gemini Decision 1）

- **申请官网**：[Google AI Studio](https://aistudio.google.com/)，使用 Google 账户登录；接受相关条款，选择或创建有权限的 Google Cloud 项目。年龄、账号验证及组织管理员限制以当前页面为准；未完成注册实测，账户是否需要额外验证待确认。[官方 key 指南](https://ai.google.dev/gemini-api/docs/api-key)
- **海外网络／VPN**：需能够访问 Google 服务并满足[官方支持地区要求](https://ai.google.dev/gemini-api/docs/available-regions)。中国大陆未列入该页面支持地区；大陆网络通常需要海外网络才能访问，但这不等于取得服务资格。具体账户与网络可用性待确认。
- **免费额度**：[官方发布公告](https://blog.google/innovation-and-ai/technology/developers-tools/gemini-decisions-api/)确认 Decision 1 有免费层；具体 RPM、TPM、RPD 以[速率限制](https://aistudio.google.com/docs/rate-limits#gemini-decision)及账户显示为准，本指南不承诺固定日额度。付费价为每百万输入 token 0.10 美元，输出免费；详见[模型价格](https://aistudio.google.com/docs/pricing#gemini-decision)。
- **生成位置**：[AI Studio → API keys](https://aistudio.google.com/apikey)，创建 key 并关联项目，流程见[官方 key 指南](https://ai.google.dev/gemini-api/docs/api-key)。
- **填写变量**：`GEMINI_API_KEY`。仓库 `GeminiDecisionJudge` 已固定使用 `gemini-decision-1`；需 `google-genai>=3.2.0`，见 `requirements-optional.txt`。不必另加模型变量。

## 4. 原点星辉 StartLux（Bamboo 托管）

- **申请官网**：[StartLux Decision](https://decision.startlux.com/)；模型托管申请入口为 [Bamboo Relay](https://bamboonode.dev/)。[登录页](https://bamboonode.dev/login)显示 GitHub、Google、用户名／密码和注册入口；注册所需邮箱验证、手机号或实名条件待确认，未实际注册。
- **海外网络／VPN**：`bamboonode.dev` 是否需海外网络待确认；不能仅凭模型由国内团队开发就认定托管 API 可从大陆直连。
- **免费额度**：[Bamboo 模型指南](https://bamboonode.dev/docs/ai-model/decisions/startlux)说明当前测试阶段免费，新账户／零余额账户无需充值，需可访问 **default group** 的 key。测试结束日期、后续价格与具体配额待确认，不是永久免费承诺。
- **生成位置**：从 [Bamboo 文档首页](https://bamboonode.dev/docs)的 **API Keys** 链接进入控制台，创建可访问 **default group** 的 key。
- **填写变量**：Bamboo key 填到本仓库 `STARTLUX_API_KEY`（不是另加 `BAMBOO_API_KEY`）。`STARTLUX_BASE_URL`、`STARTLUX_MODEL` 可留空，Judge 默认如下；这是原生 Decisions 接口，脚本会复用 `StartLuxJudge.classify`。

```dotenv
STARTLUX_BASE_URL=https://api.bamboonode.dev
STARTLUX_MODEL=startlux-decision-27b-autothink
```

## 5. Anthropic

- **申请官网**：[Claude 开发者平台](https://platform.claude.com/)。创建／登录账户，按提示创建组织或工作区，并完成验证及计费设置。注册是否要求手机、身份验证、特定付款方式：待确认，以账户流程为准。[官方 API 入门](https://platform.claude.com/docs/en/api/overview)
- **海外网络／VPN**：需海外服务可达性，同时必须满足[官方支持地区政策](https://www.anthropic.com/legal/supported-regions)；中国大陆不在支持列表内。VPN 不能替代地区资格，账户能否申请与调用需按官方政策确认。
- **免费额度**：面向该账户的新用户赠送、试用金额或订阅附带 API 额度待确认；以控制台 Billing 显示为准，不假定注册即有免费余额。参见[官方账户开始使用说明](https://support.claude.com/en/articles/8114531-i-created-a-claude-console-organization-how-do-i-start-using-the-claude-api)。
- **生成位置**：[Console → Settings → API keys](https://platform.claude.com/settings/keys)，点击 Create key；参见[官方生成 key 指南](https://platform.claude.com/docs/en/get-api-key)。
- **填写变量**：`ANTHROPIC_API_KEY`。检测模型读取 `REFLECTOR_MODEL`，为空时使用项目约定的 `claude-opus-5-5`；该账户是否获准调用此模型待确认。检测只发一次 `max_tokens=5` 请求，不自动改模型。
- **SDK**：使用 `anthropic` Python SDK。当前仓库没有将其列为必装依赖；未安装时检测显示 `sdk_missing`，按需运行 `.venv/bin/python -m pip install anthropic`。脚本不会自动安装 SDK。

## 检查结果怎么看

`scripts/check_keys.py` 优先使用 python-dotenv，未安装则解析常用的单行 `KEY=value`、引号、`export` 与行尾注释；手动解析不支持多行值或变量插值。无需新增必装依赖。

- 按 `.env.example` 的变量名逐项输出“已填／空”，不显示任何值。只读取仓库根 `.env`，不把 shell 中已有 key 当作填写结果，也不使用模板值补齐报告；所以没有 `.env` 时全部显示空。
- 已填且满足所需配置的 provider 各检测一次，固定输入为“最近睡不好，躺下脑子停不下来”。四家 Judge 复用原有 `classify`；Anthropic 使用 SDK。每项进程级超时 15 秒（含加载 SDK），无脚本级重试。
- 输出 `provider | status | 延迟 ms | 错误类型`。延迟包含启动子进程和加载 SDK；不会显示 key、模型响应、异常正文或 SDK 日志。
- `ok` 表示此次调用及 Judge 响应校验成功；不代表分类效果达标。`error` 可能包括认证、余额、网络或响应格式问题；只展示错误类名。`timeout` 表示超时；`sdk_missing` 提示安装可选 SDK；`skipped / MissingConfiguration` 表示未配置齐全、没有发出请求。
- 全部未配置时正常退出（退出码 0）；任何已尝试的检测失败则退出码 1。`.env` 不存在时不创建文件、不发请求。

在仓库根目录执行 `cp .env.example .env` 后填写，然后 `make check-keys`。
