# 镜思 Prismind · 后端（FastAPI）

官网、功能台和管理后台共用的后端：账户与登录、行情数据、策略与回测、因子研究、AI 研究员和管理后台的统计。

## 运行

```bash
cd dashboard/backend
python -m venv .venv
# Windows (PowerShell): .\.venv\Scripts\Activate.ps1
# Linux/macOS:          source .venv/bin/activate
pip install -r requirements.txt -c requirements.lock
uvicorn app.main:app --reload
```

- 健康检查：http://localhost:8000/api/health
- 接口文档：设置 `FELLOWQUANT_API_DOCS=on` 后在 http://localhost:8000/docs（`scripts/start.ps1` 本机开发时自动打开）
- 配置写在同目录的 `.env` 里，参考 `.env.example`；全部配置的说明见项目根目录的 README

## 目录结构

```
app/
├── main.py        # 入口：安全设置、跨域、路由，正式部署时也提供打包好的网页
├── database.py    # SQLite 账户数据库（data/app.db）
├── security.py    # 密码加密与登录令牌
├── routes/        # 接口：auth 登录注册、workspace 数据与研究、backtests 回测、agent_lab AI 研究员、admin 管理后台
└── quant/         # 限速、邀请码、AI 次数、每日更新、备份等
quant_platform/    # 量化研究：数据、回测、因子、WeKnora 与 Jev 适配器
trading_agents/    # 多智能体 AI 投研流程
tests/             # 回归测试：python -m pytest -q
```
