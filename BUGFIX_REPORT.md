# FellowQuant v3 · Bug 修复报告

> 修复日期：2026-08-30 ｜ 基线：AlphaQuant_v2 → FellowQuant_v3
> 验证方式：全量测试 205 passed；15 个页面 AppTest 无头渲染通过；Playwright 实机截图验收

## Bug 修复清单

| # | Bug 名 | Bug 位置 | Bug 修复方案 | 预期的效果 |
|---|--------|----------|--------------|------------|
| 1 | 回测执行时 NoneType 崩溃（下单执行价非法） | `src/quant_platform/execution/next_open.py`（`_rejection_reason`）；关联 `execution/models.py`、`backtest/validity.py` | 原代码直接 `float(row["raw_open"])`，当回测区间内某股票无行情数据（raw_open 为 None/NaN/≤0）时抛 TypeError 使整轮回测崩溃。修复：在转 float 前先校验 raw_open 为有限正数，否则拒单并记录新拒单原因 `INVALID_EXECUTION_PRICE`（已同步注册进 OrderRejectReason 与 UNKNOWN_STATUS_REJECTION_REASONS 白名单） | 回测区间内无数据的股票不再导致崩溃，而是被明确拒单并在订单明细中给出可读原因，回测正常跑完 |
| 2 | 无数据股票估值被静默按 0 处理 | `src/quant_platform/backtest/engine.py`（新增 `_seed_closing_prices`） | 股票在回测区间内无行情时，`last_closing_prices` 从未初始化，持仓估值取不到价格会退化为 0 或触发 None 路径。修复：回测启动时用起点之前最近一个收盘价为所有持仓种子化 `last_closing_prices` | 区间内停牌/无数据的持仓按最后已知价格估值，组合净值与收益率曲线不再出现虚假归零或 NoneType 异常 |
| 3 | 左侧导航栏只能一直隐藏或一直显示 | `src/quant_platform/web/theme.py`（新增 `render_sidebar_toggle`）、`web/app.py`、`web/home.py` | 原开关只写在 home 页内部，离开该页即失效，且状态不全局持久。修复：把开关提升为全局组件，在 app 入口统一渲染，session 状态跨页面持久（键 `fq_sidebar_open`，兼容旧键），Welcome 页自动隐藏开关 | 用户在任意功能页都能一键展开/收起左侧导航，选择跨页面记忆 |
| 4 | 改名导致老用户认证库失效风险 | `src/quant_platform/web/auth.py` | 改名后默认认证库路径变化会丢弃已有账号。修复：默认库改为 `data/fellowquant_auth.sqlite3`，启动时自动检测并迁移旧 `alphaquant_auth.sqlite3` | 老用户账号无缝保留，新装用户使用新库，无数据丢失 |

## UI / 品牌修复（非逻辑 bug）

| # | 问题 | 位置 | 方案 | 效果 |
|---|------|------|------|------|
| 5 | 登录/注册卡片 UI 与首页主题不搭 | `src/quant_platform/web/welcome.py` | 认证卡片整体重制：深海军蓝玻璃拟态卡片 + 品牌渐变主按钮（`#7ec8ff → #2563eb`）+ 胶囊式登录/注册分段切换 | 卡片与首页深海洋蓝主题完全统一，视觉一体化 |

## 新增回归测试

- `tests/unit/test_missing_market_data.py`：3 个用例覆盖上述 bug 1/2 的边界场景（raw_open 为 None、停牌股票估值、播种价格正确性）。
