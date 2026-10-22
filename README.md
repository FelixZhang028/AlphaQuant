<p align="center">
  <img src="landing/public/brand/prismind-icon-512.png" alt="镜思 Prismind logo" width="96" />
</p>

<h1 align="center">镜思 Prismind</h1>

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

![镜思 Prismind 首页](docs/images/homepage.png)

**功能台：精简导航与策略工作室**

![策略工作室](docs/images/workspace.png)

## 📖 项目介绍

镜思 Prismind（v4）是面向 A 股的数据研究工作台，基于 **Vue 3 + FastAPI** 构建。它把数据更新、策略创建、因子评估、回测验证和 AI 投研放进同一套工作流程，帮助研究者记录和检验投资想法。

v4 延续 AlphaQuant 的量化研究能力，并采用独立前后端架构。策略研究侧栏收敛为四个入口，详细操作在页内切换，减少寻找功能的成本。

| 工作区 | 功能 |
| --- | --- |
| AI 智能投研 | AI研究员：用本地数据整理一只股票的走势、估值、财报和风险，再由平台的 AI 模型只根据这些数据写解读；保存每次分析，并对照之后的实际涨跌。AI 问答（功能台右下角的悬浮窗）：可以跨股票提问（排序、比较、财报、自己的回测、因子说明、平台数据），模型先从固定的查询清单里选要查的本地数据，再只根据查到的数据回答，用到的数据可以展开看 |
| 我的策略 | 规则策略列表；新建规则策略可以从模板开始、用一句话描述或自己填表单，不用写代码 |
| 因子研究 | 因子库、单因子评估、组合研究；新建因子与高级合成评估保留页内入口 |
| 回测与验证 | 策略回测、参数优化、样本外验证；风险设置在配置区、审计附于结果、成交核查收入高级工具。优化与滚动验证目前为模拟预览 |
| 研究记录 | 历史研究结果与比较 |
| 数据管理 | 数据概览、数据更新、股票池管理；XTick 位于概览的「数据源与高级工具」 |
| 系统 | 个人中心、账户独立的服务配置 |

**能力边界：**回测与因子评估需要先下载行情数据。文本 AI 需要服务器配置 `OPENROUTER_API_KEY` 或其他兼容服务，Jev 决策可单独使用 `TYPESAFE_API_KEY`，没有配置时不显示相应 AI 结果；WeKnora 文档问答需要独立部署的服务。项目用于研究与模拟，不连接真实资金交易。

## 🚀 快速开始

准备 Python 3.11+、Node.js 18+ 和 Git。

```bash
git clone https://github.com/FelixZhang028/Prismind.git
cd Prismind
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

管理后台在 `admin/` 里运行 `npm ci` 和 `npm run dev`（端口 5175），用管理员账户登录；正式部署时在网站的 `/admin/` 下。

## ⚙️ 可选配置

将 `dashboard/backend/.env.example` 复制为同目录的 `.env`，填写需要的配置；后端启动时自动读取。模型密钥由服务器统一配置。AI 模型和密钥、AI 次数、每日更新、BaoStock 请求间隔、邮件服务和 WeKnora 也可以由管理员在管理后台的“系统设置”里改，保存后立刻生效，优先于 `.env`；改回用 `.env` 时清除后台的设置即可。`.env` 不进入 Git。

| 配置 | 用途 |
| --- | --- |
| `APP_SECRET` | 登录令牌签名；留空时自动生成并持久化本机随机密钥 |
| `FELLOWQUANT_ADMIN_EMAIL` / `FELLOWQUANT_ADMIN_PASSWORD` | 首次创建管理员，初始密码至少 12 位；不提供公共默认密码 |
| `OPENROUTER_API_KEY` | 平台统一提供的 AI 模型（AI研究员、用一句话生成规则），也用于 Jev 决策服务；用户不需要自己填写密钥 |
| `TYPESAFE_API_KEY` / `JEV_API_KEY` | TypeSafe 官方 Jev 密钥（前者优先）；配置后 Jev 独立于聊天模型，默认调用官方 `/v1/systemone`，未配置时使用 OpenRouter |
| `FELLOWQUANT_AI_MODEL` / `FELLOWQUANT_AI_BASE_URL` | 可选：换模型或换成其他 OpenAI 兼容服务（默认 OpenRouter 上的 `deepseek/deepseek-v4-pro`）；换服务时用 `FELLOWQUANT_AI_API_KEY` 填它的密钥 |
| `FELLOWQUANT_AI_DAILY_BRIEFS` / `_QUESTIONS` / `_STRATEGIES` / `_REVIEWS` / `_DECISIONS` / `_CHATS` | 可选：每人每天免费的 AI 分析、追问、生成规则、AI 评估（回测评估和决策辅助）、个股判断（AI 研究员里的 Jev）、AI 问答次数（默认 3 / 10 / 5 / 3 / 3 / 10），用完以后每次扣积分；管理员不限、不扣积分。AI 问答每问一次算一次（内部调用两次模型） |
| `FELLOWQUANT_POINTS_SIGNUP` / `_GIFT_DAYS` / `_CHECKIN` / `_CHECKIN_STEP` / `_CHECKIN_MAX` / `_CHECKIN_DAYS` / `_MAKEUP_EVERY` / `_MAKEUP_WINDOW` / `_DAILY_CAP` / `_COST_BRIEF` …… | 可选：积分。新用户送多少（默认 100，每个账户一次，以前注册的账户第一次打开时补上）、赠送的积分多少天有效（默认 30）、每日打卡（北京时间每天一次；连续第 1 天送 5，每多一天多送 2，最多 15，断了从头开始；打卡的积分 30 天有效；累计真正打卡 7 天送一张不过期的补签卡，可以补最近 7 天内漏打的一天，只接上连续天数、不送积分；第 1 天送 0 就关闭打卡）、每人每天最多用几次 AI（默认 200，免费的加积分的，0 不限）、免费次数用完以后每次多少积分（默认 AI 解读 3、追问 1、生成规则 2、AI 评估 2、个股判断 2、AI 问答 2）。模型没有回答时不扣积分；扣的时候先扣快到期的。积分来自注册赠送、每日打卡、兑换码和管理员发放，充值以后再开 |
| `FELLOWQUANT_JEV_MODEL` / `FELLOWQUANT_JEV_URL` | 可选：决策模型和完整接口地址；TypeSafe 默认 `jev-latest`，OpenRouter 默认 `typesafe/jev-1.13`。密钥必须与服务匹配 |
| `FELLOWQUANT_DAILY_UPDATE` / `FELLOWQUANT_DAILY_UPDATE_TIME` | 每个交易日收盘后自动更新全市场数据（默认开启，北京时间 18:30 以后）；填 `off` 关闭，管理员仍可在数据更新页手动运行 |
| `FELLOWQUANT_FUNDAMENTALS_UPDATE` | 财报季自动更新财务数据（默认开启）：1～4 月、7～8 月、10 月以及 5、9、11 月第一周的每个周六 10:00 以后，下载最近 5 个报告期里还没有的财报；填 `off` 关闭，管理员仍可以在管理后台手动更新 |
| `FELLOWQUANT_BAOSTOCK_INTERVAL` | 每两次 BaoStock 请求之间至少隔几秒（默认 0.1）。BaoStock 会把短时间内请求太多的服务器暂时拉黑（提示“黑名单用户”）；被拒绝时数据任务立刻停下、当天不再自动重试，页面上会写明原因。经常被拉黑时调大这个数 |
| `FELLOWQUANT_FACTOR_PROFILE` | AI 研究员的因子画像：后端每 10 分钟检查一次，把最新交易日的全市场因子值预先算好（约半分钟，存在 `data/runtime/factor_profiles`）；填 `off` 关闭预先计算，分析时仍会在后台现算 |
| `FELLOWQUANT_COMPUTE_SLOTS` / `_PER_USER` / `_TIMEOUT` / `_CACHE` | 耗时计算（回测、参数验证、因子评估与组合研究）的限制：全站同时最多几件（默认 CPU 核数的一半，2 到 4）、每人同时几件（默认 1）、一件最多多少秒（默认 600）、记住多少份因子研究结果（默认 64） |
| `FELLOWQUANT_AI_DAILY_TOTAL` | 全站每天最多调用多少次 AI（默认 500，管理员不计），防止费用失控；用完以后当天所有用户暂停 AI 功能 |
| `WEKNORA_BASE_URL` / `WEKNORA_API_KEY` | WeKnora 服务地址与空间 Key，也可由管理员在页面配置；没有配置时知识库问答不可用 |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_FROM` | 密码重置邮件服务，采用 STARTTLS；默认端口 587 |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | SMTP 登录凭据（邮件服务需要时填写） |
| `FELLOWQUANT_REGISTRATION` / `FELLOWQUANT_INVITE_CODES` | 注册方式和邀请码一般在管理后台的“注册与邀请码”里设置，改完立即生效。这两项只是默认值：在页面上选过注册方式以后以页面为准；`.env` 里的邀请码（`码:次数`，逗号分开，例如 `TRIAL2026:20,FRIEND`，不写次数就不限次数）和页面生成的一起有效；`FELLOWQUANT_REGISTRATION=closed` 会固定暂停注册，页面上也改不了 |
| `FELLOWQUANT_CLIENT_IP_HEADER` | 部署在 Cloudflare 或 Nginx 后面时，从哪个请求头读取用户的真实 IP（Cloudflare 填 `CF-Connecting-IP`），用于登录、注册的频率限制 |
| `FELLOWQUANT_CORS_ORIGINS` | 允许跨域访问的网页地址，逗号分开；默认只允许本机开发服务器。前后端同一个地址时不需要 |
| `FELLOWQUANT_STATIC_DIR` / `FELLOWQUANT_ADMIN_DIR` | 打包好的网页目录（`landing/dist`）和管理后台目录（`admin/dist`，在 `/admin/` 下），设置后后端直接提供网页，见下面的“正式部署” |
| `FELLOWQUANT_API_DOCS` | 填 `on` 打开接口文档 `/docs`（默认关闭；`scripts/start.ps1` 本机开发时自动打开） |
| `FELLOWQUANT_MAX_BODY_MB` | 一次请求最大多少 MB（默认 5），超过返回 413 |
| `FELLOWQUANT_BACKUP` / `_BACKUP_DIR` / `_BACKUP_KEEP` | 每天自动备份账户数据库、登录密钥和数据源、知识库设置（默认开启，放在 `data/backups`，保留 14 份）；备份目录最好设在另一块硬盘或同步盘；行情数据可以重新下载，不备份 |
| `FELLOWQUANT_PASSWORD_ITERATIONS` | 密码加密的计算轮数（默认 600000），一般不用改；旧账户登录时自动升级 |

行情数据所有用户共用一份。后端运行时，每个交易日收盘后自动更新全市场：行情（含估值与换手率）、新上市股票的全部历史、分红送转记录、指数行情、指数成分股、行业分类和历史股票池。当天行情还没发布或更新没完成时，30 分钟后再试，最晚到 23:30。白天手动运行时，如果当天的行情还没发布、但本地落后于最近一个交易日，会先把前几天补齐；管理后台和数据页会写明这次实际做了什么（例如“当天的行情还没有发布，先补到 10-19”），不只显示“完成”。被数据源拒绝（BaoStock 黑名单）时任务立刻停下，当天不再自动重试。下载数据、补历史数据、查看后台任务和配置 XTick 只有管理员可以操作；普通用户在数据更新页看到更新状态。数据文件先完整写好再整份替换，写到一半被中断（关闭程序、停电）也不会损坏原来的文件；后台数据任务不随启动窗口关闭，会继续运行到完成。

所有用户共用一台服务器，耗时的计算有三条限制：每人同一时间只算一件，全站同时算的数量有上限（满了提示稍后再试），一件计算超过时间限制就停下。同样的因子评估或组合研究在同一份数据上算过就直接返回，数据每天更新以后重新计算。

未配置 SMTP 时密码重置不可用；验证码只发送至注册邮箱，不返回到浏览器。重置密码、修改密码和退出登录后，这个账户的旧登录令牌全部失效。用户可以在个人中心修改密码和注销账户，注销会删除账户和全部研究数据；在设置页可以保存回测和 AI 研究员的默认值、查看今天剩余的免费 AI 次数（积分页面有余额、每一批的到期时间、价格、明细和兑换码），并把自己的全部数据导出成一个 JSON 文件（不含密码）。登录、注册和找回密码都有频率限制：同一 IP 15 分钟最多登录 30 次，同一邮箱连续输错 5 次密码要等 15 分钟，同一 IP 每小时最多注册 5 个账户。本机账户、行情、运行记录和密钥保存在后端 `data/` 中，不进入 Git。

WeKnora 需要预先部署、创建知识库，并为 Key 开通相应的读取、检索和聊天权限。AI研究员的文字解读和“用一句话生成规则”使用平台的聊天模型；没有配置时，生成规则改用离线规则识别。决策模型 Jev 按概率回答选择、是非、评分三类问题：AI研究员可只使用 Jev 给出利好多/中性/风险多的概率，无需文本模型；回测结果页用它评估风险等级和过度拟合的可能。材料由平台从本地数据自动整理，结果按账户保存，重复打开不再计费；独立判断计入每日评估额度。TypeSafe 的请求协议见[官方文档](https://docs.typesafe.ai/api)。

需要验证实际集成时，在项目根目录运行 `python scripts/verify_jev.py --live`。该命令会向配置的 Jev 服务发送本地行情和回测摘要，消耗 API 额度；使用独立账户数据库，报告保存在 Git 忽略的 `outputs/`，不会修改现有账户和行情。

完整的配置、网页操作、API 示例、额度说明和故障排查见 [Jev 使用文档](docs/JEV_USAGE.md)。

## 🌐 正式部署

正式部署时由后端直接提供打包好的网页，整个网站只有一个地址，不需要配置跨域：

```bash
cd dashboard/backend
python -m pip install -r requirements.txt -c requirements.lock
cd ../..
scripts/serve.sh            # Windows：powershell -File scripts\serve.ps1
```

脚本先打包 `landing/` 和 `admin/`，再在 `127.0.0.1:8000` 启动后端，只开一个进程（次数限制和后台任务记在这个进程里，不要开多个 worker）。前面用 Cloudflare Tunnel 或 Nginx 提供 https，不直接暴露端口。上线前在 `.env` 里至少确认：`APP_SECRET`、管理员账户、`OPENROUTER_API_KEY`、`FELLOWQUANT_AI_DAILY_TOTAL`、注册方式（试用阶段建议用邀请码）、`FELLOWQUANT_CLIENT_IP_HEADER`、SMTP 和备份目录。`requirements.lock` 是测试通过的固定版本。

**在自己的 Windows 电脑上公开（Cloudflare 临时 Tunnel）**：先安装 cloudflared（`winget install --id Cloudflare.cloudflared`），再运行

```powershell
powershell -ExecutionPolicy Bypass -File scripts\tunnel.ps1            # 打包网页、在 127.0.0.1:8100 启动后端、申请 https 网址
powershell -ExecutionPolicy Bypass -File scripts\tunnel.ps1 -Install   # 以后登录 Windows 自动在后台启动（-Uninstall 取消）
powershell -ExecutionPolicy Bypass -File scripts\tunnel.ps1 -Status    # 是否在运行、当前网址
powershell -ExecutionPolicy Bypass -File scripts\tunnel.ps1 -Stop      # 停止
```

网址形如 `https://xxx.trycloudflare.com`，不需要 Cloudflare 账号，但**每次 Tunnel 重新启动都会变**，当前网址在 `dashboard/backend/data/runtime/public-url.txt`；只适合试用，有了托管在 Cloudflare 的域名后再换成固定网址的正式 Tunnel。脚本自动设置 `FELLOWQUANT_CLIENT_IP_HEADER=CF-Connecting-IP`，后端或 Tunnel 意外退出时自动重启，日志在 `dashboard/backend/data/runtime/logs/public-*.log`。用 8100 端口，和本机开发（`start.bat`，8000）可以同时运行。电脑睡眠、关机或退出登录时网站就访问不到了，要在电源设置里关掉自动睡眠。更新代码后先 `-Stop` 再启动，网页会重新打包。

服务条款、隐私政策和风险提示在 `landing/src/legal/legalContent.js`，上线前要把【运营者名称】【联系邮箱】【生效日期】换成真实信息，并请律师看一遍。管理后台在 `https://你的域名/admin/`，只有管理员账户能登录：概览（注册人数、今天活跃、回测和 AI 用量、行情数据和备份）、用户（每个人今天和累计的 AI 次数、回测数，可以停用或恢复账户；停用后不能登录，已经登录的设备立即退出，数据不删除）、注册与邀请码（选择开放 / 邀请码 / 暂停，生成和停用邀请码）、积分与兑换码（用户手里还有效的积分、最近 30 天发出和用掉的积分；一次生成多个兑换码，设置积分、有效天数、几个账户能用和兑换期限；给某个用户加或扣积分，要写原因，用户在积分明细里能看到）、数据更新（服务器磁盘空间和数据占用，剩余不到 5 GB 或 10% 时提醒；每日更新每一步的结果，可以只重新运行没完成的部分；财务数据的自动更新和手动更新；选数据集和日期下载历史数据；后台任务的进度和日志；手动备份）、系统设置（AI 模型和密钥、各类 AI 每天的免费次数、积分规则、每日更新的开关和时间、BaoStock 请求间隔、找回密码用的邮件服务、知识库；保存后立刻生效，不用重启；密钥和邮箱密码用 `APP_SECRET` 派生的密钥加密后存进数据库，页面上只显示前后几位，保存要再输一次管理员密码；可以先“测试连接”或发一封测试邮件；没在后台设置的项照常用 `.env`）、操作记录（改设置、停用用户、注册方式、邀请码、积分和兑换码、数据任务、备份，不记录密钥本身）。概览页有最近 30 天每天各类 AI 的次数和文本模型的 token 用量。换了 `APP_SECRET` 以后，后台保存的密钥会解不开，需要重新填写。网页每次打开都会检查有没有新版本，发布更新以后不会用到旧页面。

## 🧩 项目结构

```text
.
├── landing/              # Vue 官网、登录、功能台、法律页面
├── admin/                # 管理后台（正式部署时在 /admin/）
├── dashboard/
│   └── backend/
│       ├── app/          # FastAPI 路由、认证、数据库
│       ├── quant_platform/  # 量化研究、WeKnora 与 Jev 适配器
│       ├── trading_agents/  # AI 投研流程
│       ├── configs/      # 数据源、策略、风险配置
│       └── tests/        # 回归测试
├── docs/images/          # 实际页面截图
├── scripts/start.ps1    # Windows 本机开发：启动前后端与清理
├── scripts/serve.ps1 / serve.sh  # 正式部署：打包网页，由后端一起提供
├── scripts/tunnel.ps1   # 在自己电脑上用 Cloudflare 临时 Tunnel 公开网站
└── start.bat
```

## 🧪 开发与验证

```bash
cd dashboard/backend
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m compileall -q app quant_platform trading_agents
```

在 `landing/`、`admin/` 各自执行 `npm ci`、`npm run build`。回归测试覆盖成交核查、外部服务协议、账户配置隔离、认证及密码重置；外部服务使用模拟响应，不产生模型费用。

## 🤝 参与贡献

欢迎通过 [Issue](https://github.com/FelixZhang028/Prismind/issues) 反馈问题、提出功能建议，或提交 Pull Request。反馈时请说明复现步骤、预期行为和实际行为。

感谢 AlphaQuant 的量化研究基础，以及 [WeKnora](https://github.com/Tencent/WeKnora) 和 [OpenRouter](https://openrouter.ai/) 提供的集成能力。

## 📄 许可证

项目采用 [GNU GPL v3](LICENSE)。
