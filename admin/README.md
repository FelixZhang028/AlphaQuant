# 智投引擎 · 管理后台（独立项目）

后台管理界面，与官网（landing）解耦的独立 Vite + Vue 3 + Tailwind 项目。

## 与官网的关系
- 官网 `landing` 只负责品牌展示 + 注册/登录。
- 用户登录后进入功能台（`landing/app.html`）。
- **本管理后台是独立项目**，面向运营/管理员，不集成在官网内。

## 启动
```bash
cd D:\code\github_proj\FellowQuant_v4\admin
pnpm install   # 或 npm install
pnpm run dev
```
访问 http://127.0.0.1:5175

> 需先启动后端 `dashboard/backend`（`uvicorn app.main:app --reload`，端口 8000）。

## 管理员登录
- 默认账户：`admin@zhitou.io` / `Admin12345`（后端 `app/database.py` 种子，可修改）
- 登录走 `/api/v1/auth/login`，前端校验 `is_admin`；非管理员会被拒绝。
- 令牌存 localStorage，刷新后 `/api/v1/auth/me` 校验。

## 对接真实数据
- KPI（活跃策略/运行实例/数据链路/今日成交）、实时性能（处理速率/吞吐/延迟/挂起订单）来自 `/api/v1/admin/stats`（复用后端 simulator）。
- 「注册用户」表来自 `/api/v1/admin/users`。
- 全球成交/策略来源/成交额趋势/系统动态/近期订单当前为演示数据，可继续对接真实接口。

## 结构
- 侧边栏导航：概览 / 策略管理 / 用户管理 / 订单管理 / 风控中心 / 数据源 / 系统设置
- KPI + 实时性能 + 注册用户表 + 全球成交地图 + 策略来源圆环 + 成交额趋势柱状图（30/90/12月）+ 系统动态时间线 + 近期订单表

> 当前部分数据为演示数据。后续可对接 `dashboard/backend` 的 REST / WebSocket 接口替换为真实数据。
