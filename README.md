<p align="center">
  <img src="landing/public/fellowquant-logo.png" alt="FellowQuant logo" width="88" />
</p>

<h1 align="center">FellowQuant · 智投引擎</h1>

<p align="center">从投资想法，到可验证的量化研究。</p>

<p align="center">
  <a href="README.md"><strong>简体中文</strong></a> · <a href="README.en.md">English</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/Vue-3-4FC08D?logo=vuedotjs&logoColor=white" alt="Vue 3" />
  <img src="https://img.shields.io/badge/FastAPI-backend-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-GPL--3.0-blue" alt="GPL 3.0" /></a>
</p>

## 🖥️ 实际界面

以下截图来自本项目运行页面，使用隔离的演示账户；未配置外部服务的结果会标明演示模式。

**品牌首页**

![FellowQuant 首页](docs/images/homepage.png)

**功能台：精简导航与策略工作室**

![策略工作室](docs/images/workspace.png)

**Jev 结构化决策**

![Jev 决策中心](docs/images/decision-center.png)

## 📖 项目介绍

FellowQuant v4 是面向 A 股的量化研究工作台，基于 **Vue 3 + FastAPI** 构建。它把数据更新、策略创建、因子评估、回测验证和 AI 投研放进同一套工作流程，帮助研究者记录和检验投资想法。

v4 延续 AlphaQuant 的量化研究能力，并采用独立前后端架构。策略研究侧栏收敛为四个入口，详细操作在页内切换，减少寻找功能的成本。

| 工作区 | 功能 |
| --- | --- |
| AI 智能投研 | AI研究员、账户先验知识库、WeKnora 文档检索与问答、Jev 决策中心 |
| 策略工作室 | 策略管理、模板与积木、自然语言、Python 自定义策略 |
| 因子实验室 | 内置因子、自定义因子、评估与组合研究 |
| 回测与验证 | 单次回测、参数优化、滚动样本外验证、可信度审计、成交核查 |
| 研究记录 | 历史研究结果与比较 |
| 数据管理 | 数据资产、行情更新、XTick、股票池与风险配置 |
| 系统 | 个人中心、账户独立的服务配置 |

**能力边界：**回测与因子评估需要先下载行情数据；监控大屏使用模拟指标。WeKnora 和 Jev 需要独立服务或有效 API Key，未配置时提供明确标记的演示结果，配置后的服务错误会直接提示。项目用于研究与模拟，不连接真实资金交易。

## 🚀 快速开始

准备 Python 3.11+、Node.js 18+ 和 Git。

```bash
git clone --branch fellowquant_v4 https://github.com/FelixZhang028/AlphaQuant.git
cd AlphaQuant
```

**Windows**：在项目根目录运行 `start.bat`。首次运行会检查并安装必要依赖，启动后访问 `http://127.0.0.1:5273`。按任意键停止由脚本启动的服务。

**手动启动 / macOS / Linux**：

```bash
# 终端一：后端
cd dashboard/backend
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell 使用：.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```bash
# 终端二：从项目根目录进入官网/功能台
cd landing
npm ci
npm run dev -- --host 127.0.0.1
```

注册并登录后，先进入「数据管理 → 数据更新」，再创建策略、运行回测。接口文档位于 `http://127.0.0.1:8000/docs`。

独立管理后台与监控大屏可分别从 `admin/`、`dashboard/frontend/` 运行 `npm ci` 和 `npm run dev`，默认端口为 5175、5174。

## ⚙️ 可选配置

将 `dashboard/backend/.env.example` 复制为同目录的 `.env`，填写需要的配置；后端启动时自动读取。用户在页面保存的模型和 WeKnora 配置优先于相应环境变量。

| 配置 | 用途 |
| --- | --- |
| `APP_SECRET` | 登录令牌签名；留空时自动生成并持久化本机随机密钥 |
| `FELLOWQUANT_ADMIN_EMAIL` / `FELLOWQUANT_ADMIN_PASSWORD` | 首次创建管理员，初始密码至少 12 位；不提供公共默认密码 |
| `OPENROUTER_API_KEY` | Jev 决策服务，也可在「系统 → 设置」填写 |
| `WEKNORA_BASE_URL` / `WEKNORA_API_KEY` | WeKnora 服务地址与空间 Key，也可在页面配置 |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_FROM` | 密码重置邮件服务，采用 STARTTLS；默认端口 587 |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | SMTP 登录凭据（邮件服务需要时填写） |

未配置 SMTP 时密码重置不可用；验证码只发送至注册邮箱，不返回到浏览器。重置密码后旧登录令牌失效。本机账户、行情、运行记录和密钥保存在后端 `data/` 中，不进入 Git。

WeKnora 需要预先部署、创建知识库，并为 Key 开通相应的读取、检索和聊天权限。Jev 提供 Choice、Noul、Score 三种决策，可输入文本或 JSON 上下文；真实调用可能消耗服务额度。自然语言策略和 AI研究员使用聊天模型，Jev 在独立决策中心使用。

## 🧩 项目结构

```text
.
├── landing/              # Vue 官网、登录、功能台与社区页面
├── admin/                # 独立管理后台
├── dashboard/
│   ├── frontend/         # 实时监控大屏
│   └── backend/
│       ├── app/          # FastAPI 路由、认证、数据库
│       ├── quant_platform/  # 量化研究、WeKnora 与 Jev 适配器
│       ├── trading_agents/  # AI 投研流程
│       ├── configs/      # 数据源、策略、风险配置
│       └── tests/        # 回归测试
├── docs/images/          # 实际页面截图
├── scripts/start.ps1    # Windows 服务启动与清理
└── start.bat
```

## 🧪 开发与验证

```bash
cd dashboard/backend
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m compileall -q app quant_platform trading_agents
```

在 `landing/`、`admin/`、`dashboard/frontend/` 各自执行 `npm ci`、`npm run build`。回归测试覆盖成交核查、外部服务协议、账户配置隔离、认证及密码重置；外部服务使用模拟响应，不产生模型费用。

## 🤝 参与贡献

欢迎通过 [Issue](https://github.com/FelixZhang028/AlphaQuant/issues) 反馈问题、提出功能建议，或提交 Pull Request。反馈时请说明复现步骤、预期行为和实际行为。

感谢 AlphaQuant 的量化研究基础，以及 [WeKnora](https://github.com/Tencent/WeKnora) 和 [OpenRouter](https://openrouter.ai/) 提供的集成能力。

## 📄 许可证

项目采用 [GNU GPL v3](LICENSE)。
