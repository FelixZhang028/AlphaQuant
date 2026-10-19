# Jev 使用文档

本版本在 AlphaQuant `main`（`c190fed`）基础上提供 Jev 增强与 bug 修复。Jev 提供结构化判断，不生成聊天文本。它可以独立用于股票数据判断和回测评估；文字解读、追问和自然语言策略生成使用另一套文本模型。

## 1. 配置与启动

### TypeSafe 官方服务

后端启动时自动读取 `dashboard/backend/.env`。首次配置可参考同目录 `.env.example`；已有 `.env` 时直接编辑，不要覆盖现有配置。

推荐将 Jev 密钥存放在项目目录的 `.env` 中，变量名为 `TYPESAFE_API_KEY`，无需设置 Windows 用户级或系统级永久环境变量。后端导入 `app` 时，通过 `python-dotenv` 将配置加载到后端进程自己的环境中，不修改 Windows 注册表或其他应用的环境。若启动后端前已经提供同名进程环境变量，则优先使用该值（`override=False`）。

```dotenv
TYPESAFE_API_KEY=填写你自己的_TypeSafe_密钥
# 留空使用官方默认值
FELLOWQUANT_JEV_MODEL=
FELLOWQUANT_JEV_URL=
# 普通账户每天的独立决策及回测评估次数，默认 10
FELLOWQUANT_AI_DAILY_REVIEWS=10
FELLOWQUANT_AI_DAILY_DECISIONS=10
```

密钥由 [TypeSafe 控制台](https://console.typesafe.ai/keys) 创建。默认调用 `https://api.typesafe.ai/v1/systemone`，模型为 `jev-latest`。不需要安装额外的 TypeSafe SDK。

本项目选择密钥和服务的顺序如下：

| 可用配置 | 默认服务 | 默认模型 |
| --- | --- | --- |
| `TYPESAFE_API_KEY` 非空 | TypeSafe 官方 | `jev-latest` |
| 前者为空，`JEV_API_KEY` 非空 | TypeSafe 官方 | `jev-latest` |
| 两者为空，`OPENROUTER_API_KEY` 非空 | OpenRouter Decisions | `typesafe/jev-1.13` |
| 都为空 | 决策功能不可用 | 无演示结果 |

`FELLOWQUANT_JEV_URL` 和 `FELLOWQUANT_JEV_MODEL` 可以覆盖默认值；URL 必须是完整的决策接口地址，密钥必须与提供商匹配。使用官方密钥时，应清除以前填入的 OpenRouter URL/模型覆盖。不会把官方密钥自动尝试发送给其他提供商，也不会自动跟随接口重定向。

密钥只保存在后端环境变量或 Git 忽略的 `.env`，不要放入前端 `VITE_*` 变量、请求示例、文档或 Git。仓库不提供真实密钥，需要在部署环境自行配置。

修改配置后停止原有服务，在项目根目录双击 `start.bat` 重新启动：

- 网页：`http://localhost:5273`
- 功能台：`http://localhost:5273/app.html`
- 后端：`http://127.0.0.1:8000`
- API 文档：`http://127.0.0.1:8000/docs`

如果旧服务占用端口且启动脚本无法确认其归属，需要从原启动窗口停止它；脚本不会仅凭 uvicorn/vite 进程名结束其他项目。

停止时需回到启动窗口按任意键。更新后的启动器把 Python、Vite 及其子进程纳入独立的 Windows 进程组，按键退出会整体清理；关闭启动窗口时也由 Windows 释放该进程组，防止父进程退出后遗留后台服务。前端直接启动 Vite，不再依赖 cmd/npm 中间进程。非交互输入重定向时使用 Enter 停止。

## 2. 在网页中使用

### 股票数据判断

1. 注册或登录账户，进入“AI研究员”。
2. 确认本地已有该股票的日线数据。输入完整股票代码或搜索名称选中股票；日期留空使用本地最近交易日。
3. 点击开始分析。系统先保存本地事实数据，再调用 Jev，根据这些数据判断“利好多 / 中性 / 风险多”（对当前数据的归纳，不是买卖建议）。
4. 在“Jev 分析报告”查看综合判断、三类倾向概率、模型置信度及五个分项：趋势与动能、成交配合、波动与回撤、估值位置、经营与财务。每项展示对应的保存数据，必要数据不足或模型无法判断时明确标为“数据不足”。
5. 在“以前的分析”重新打开同一次记录，可以查看当时的数据和判断；已有 Jev 结果直接复用，不会再次请求提供商。

只配置 `TYPESAFE_API_KEY` 就可以使用这条流程。若还配置了文本模型，系统会进一步生成文字解读并支持追问；两个模型判断不同会在页面提示。Jev 失败不会阻止本地数据显示。

报告还包含相对有利的线索、需留意的分项、基于已有波动/回撤的风险等级、数据缺口，以及下一步核查事项。说明文字由预先编写的模板整理模型的结构化答案，不冒充 Jev 的推理过程。展示的数据依据来自保存的本地事实，不是对综合结论的因果归因。

“可评估维度 2 / 5”表示本次只有两项获得可用判断，不是数据完整性或准确率的百分比。置信度展示标签按数值分为“较高”（≥0.7）、“一般”（≥0.5 且 <0.7）、“较低”（<0.5）；它不是未来涨跌幅或获利概率。缺少估值或财务时不会把缺项当成零风险。

旧记录显示“历史简版”，打开时直接复用原判断，不会自动重新计费。需要完整分项时点击“补全分项报告 · 使用 1 次评估”：对当时保存的数据重新评估并保存新版报告，综合概率可能变化；失败时保留原结果并退还本地额度。已经是新版报告时重复请求直接返回缓存。

### 回测评估

1. 用已注册的内置策略、结构化规则策略或因子组合完成一次回测。
2. 在回测结果页找到“AI 评估”并点击按钮。
3. 先看结论摘要及引擎给出的研究边界，再查看五档风险等级、模型置信度及过度拟合的可能性。“AI 看到的数据”展示发送的回测摘要。
4. 同一次回测已经保存评估时，重复打开或点击会复用保存结果。

这些判断只依据传入的本地数据和回测结果，不代表未来收益；引擎给出的有效性警告会保留。

### 手动结构化决策

打开[已登录功能台的决策辅助页面](http://localhost:5273/app.html?view=decision-center)。该页面保留在路由中，当前上游侧栏未单独列出。

先填写“决策上下文”，再选择：

| 类型 | 用途 | 输入与输出 |
| --- | --- | --- |
| 方案比较（Choice） | 从候选项中选择 | 至少 2 个不同非空选项，最多 255 个；返回选中项、各项概率和置信度 |
| 条件判断（Noul） | 判断条件是否成立 | 填写条件；返回 0–1 的成立概率 |
| 等级评分（Score） | 按有序等级评分 | 2–10 个不同非空等级，从低到高排列；返回 0 到“等级数减一”的分数、等级概率和置信度 |

上下文可以是文本、JSON 对象或数组。概率与置信度范围为 0–1；Score 是连续加权分数，不一定为整数。Noul 没有独立的置信度字段。

## 3. 调用项目 API

以下都是 AlphaQuant 后端接口。先登录，再使用返回的登录令牌；这里的 Bearer 令牌是项目登录令牌，**不是 TypeSafe API Key**。真正的 Jev 密钥由服务器读取。

| 方法与路径 | 用途 |
| --- | --- |
| `POST /api/v1/auth/login` | 获取项目登录令牌 |
| `GET /api/v1/jev/status` | 查看是否配置、模型和当天评估额度 |
| `POST /api/v1/jev/decide` | 手动 Choice / Noul / Score |
| `POST /api/v1/agent-lab/briefs` | 保存股票的本地事实数据 |
| `POST /api/v1/agent-lab/briefs/{id}/decision` | 对已保存事实做 Jev 判断；已有结果直接返回 |
| `POST /api/v1/agent-lab/briefs/{id}/decision?upgrade=true` | 用户主动补全旧报告；新版结果直接复用 |
| `GET /api/v1/agent-lab/briefs/{id}` | 读取分析与 `odds` 字段 |
| `GET /api/v1/backtests/{id}/ai-review` | 读取已保存的回测评估和额度 |
| `POST /api/v1/backtests/{id}/ai-review` | 创建或复用回测评估 |

### Python 示例

先设置 `ALPHAQUANT_EMAIL` 和 `ALPHAQUANT_PASSWORD` 为已注册账户的登录凭据。此示例消费一次评估额度。

```python
import os
import requests

base = "http://127.0.0.1:8000"
session = requests.Session()
login = session.post(f"{base}/api/v1/auth/login", json={
    "email": os.environ["ALPHAQUANT_EMAIL"],
    "password": os.environ["ALPHAQUANT_PASSWORD"],
}, timeout=10)
login.raise_for_status()
session.headers["Authorization"] = "Bearer " + login.json()["token"]

status = session.get(f"{base}/api/v1/jev/status", timeout=10)
status.raise_for_status()
print(status.json())

result = session.post(f"{base}/api/v1/jev/decide", json={
    "type": "noul",
    "condition": "摘要是否提到交易次数不足？",
    "state": {"摘要": "该策略只完成了三次完整买卖，样本有限。"},
}, timeout=45)
result.raise_for_status()
print(result.json())  # {"probability": 0 到 1 的数值}
```

Choice 请求体：

```json
{
  "type": "choice",
  "question": "哪些研究工作应优先进行？",
  "options": ["扩充历史数据", "继续参数优化"],
  "state": {"数据": "只有两个月行情，尚未做样本外验证"}
}
```

结果字段为 `selected`、`probabilities`、`confidence`。

Score 请求体：

```json
{
  "type": "score",
  "question": "这份研究材料的信息是否充分？",
  "levels": ["不充分", "一般", "充分"],
  "state": {"材料": "包含一年日线和成本说明，缺少样本外结果"}
}
```

结果字段为 `score`、`level_probabilities`、`confidence`、`levels`。三个等级时 `score` 范围是 0–2，页面换算为 0–100。

### 额度与账户隔离

- AI 研究员里的独立股票判断使用 `FELLOWQUANT_AI_DAILY_DECISIONS`；手动决策和回测评估共享 `FELLOWQUANT_AI_DAILY_REVIEWS`。两者默认普通账户每天各 10 次，互不占用，北京时间换日；管理员不设日限额。
- 每次成功的项目调用按一次计数；一次回测评估内的风险与过拟合问题合并发给 Jev。失败退还本地预留额度；这不表示项目可以决定提供商如何计费。
- 股票分项报告把综合倾向、可用维度和风险评级合并在一次请求中，最多 7 个结构化问题；仍使用一次本地个股判断额度，提供商费用按其计费规则计算。数据不足的维度不发送提问。
- 额度在发起网络请求前原子预留，并发请求不能越过最后一个剩余额度。
- 分析和评估按账户隔离。新建一次分析会产生新记录并可能触发新的调用；复用同一记录的已有结果不增加计数。
- 没有密钥或调用失败时不会生成演示概率。

## 4. 完整验证

在项目根目录运行：

```powershell
python scripts/verify_jev.py --live
```

该脚本使用后端 `.env`，向配置的真实服务发送示例问题、本地股票摘要和真实回测摘要，消耗约 5 次项目调用。它使用独立验证数据库，不覆盖已有账户和行情；报告和回测输出写入 Git 忽略的 `outputs/jev-smoke-时间戳/`。

验证内容包括：注册登录、Choice/Noul/Score、本地股票判断、真实动量回测后的风险与过拟合评估、重复访问不增加计数、未登录访问被拒绝，以及旧 Python 源码提交接口不可用。只有全部通过才写出 `passed: true` 的报告。不带 `--live` 不会执行外部调用。

无需计费的回归检查：

```powershell
cd dashboard/backend
python -m pytest -q
```

测试会隔离本地官方 Jev 凭据并使用模拟提供商响应，不会使用真实密钥做付费请求。

## 5. 常见问题

| 现象 | 检查方法 |
| --- | --- |
| 提示平台未配置决策模型 | 确认 `.env` 位于 `dashboard/backend/`，密钥非空，修改后已重启后端；检查 `/api/v1/jev/status` |
| Jev 可用但没有文字解读或追问 | Jev 是决策模型。文字能力需要另配 `OPENROUTER_API_KEY`，或 `FELLOWQUANT_AI_API_KEY` 加兼容服务地址和模型 |
| 没有本地股票数据 | 让管理员在数据管理中下载行情；分析日期不能超出已有数据。源码更新不会自动补齐全部行情 |
| 返回 401 | 项目登录令牌过期或无效，重新登录；若提示平台 AI 密钥无效，检查服务器端提供商密钥 |
| 返回 422 | 检查请求字段、选项/等级数量、日期及本地数据；未配置 Jev 也会返回 422 |
| 返回 429 | 当天项目额度已用完、计算任务正在进行或提供商限流；根据提示等任务完成或次日重试 |
| 返回 502、连接失败或超时 | 检查后端到 TypeSafe 的网络、密钥和权限；提供商失败退还本地额度，已有数据仍可查看 |
| 提示重定向或返回格式不对 | 检查是否误填聊天接口地址或错误模型；官方接口是 `/v1/systemone`，不是 `/chat/completions` |
| 重复分析仍扣次数 | 复用必须针对同一分析/回测记录；点击重新分析会新建记录 |

协议参考：[TypeSafe HTTP API](https://docs.typesafe.ai/api)、[官方模型说明](https://docs.typesafe.ai/models)。项目中的网页源码编辑与用户 Python 执行功能已停用，结构化规则和因子组合仍可使用。
