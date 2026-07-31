# 回测指标说明

新回测会在 `summary.json` 中保存收益、风险、交易、成本和持仓指标，并在
`closed_trades.parquet` 中保存按 FIFO 匹配的完整买卖记录。旧回测结果仍可打开，
但旧文件中不存在的指标会在网页显示为 `—`。

## 收益与风险

- `cumulative_return`：期末权益相对初始资金的累计收益；
- `annual_return`：按 252 个交易日折算的复合年化收益；
- `annual_volatility`：日收益标准差乘以 `sqrt(252)`；
- `downside_volatility`：负超额日收益的下行波动率；
- `sharpe`：日均超额收益年化后除以年化波动率；
- `sortino`：日均超额收益年化后除以下行波动率；
- `calmar`：年化收益除以最大回撤绝对值；
- `max_drawdown`：净值相对历史峰值的最大跌幅；
- `max_drawdown_*_date`：最大回撤的峰值、谷底和恢复日期；
- `max_drawdown_duration_trading_days`：峰值到恢复或回测结束的交易日数量；
- `best_day_return`、`worst_day_return`：最佳和最差日收益；
- `positive_day_ratio`、`positive_month_ratio`：正收益日和正收益月比例。

Sharpe 和 Sortino 使用回测引擎的 `risk_free_rate`，默认值为 0。无法定义的比率
保存为 `null`，而不是人为填入无穷大。

## 交易与成本

- `order_fill_rate`：存在成交记录的订单数除以全部订单数；
- `trade_win_rate`：FIFO 已平仓记录中净盈亏为正的比例；
- `payoff_ratio`：平均盈利除以平均亏损绝对值；
- `profit_factor`：盈利交易净利润之和除以亏损交易净亏损绝对值；
- `average_holding_days`：FIFO 买卖配对的平均自然日持有时间；
- `portfolio_turnover`：成交金额除以两倍平均权益；
- `annualized_turnover`：根据回测交易日数量折算的年化换手率；
- `commission`、`stamp_tax`、`slippage_cost`：三类交易成本；
- `total_transaction_cost`：佣金、印花税和滑点成本合计。

滑点成本使用未加滑点的开盘价作为参考价。买卖成交价已经包含滑点，因此计算
完整交易净盈亏时不会重复扣除。

## 持仓

- `average_position_count`、`max_position_count`：平均和最大持仓数量；
- `average_exposure`、`max_exposure`：平均和最大股票仓位；
- `average_cash_ratio`、`minimum_cash_ratio`：平均和最低现金比例；
- `time_in_market_ratio`：股票仓位大于 0 的交易日比例；
- `max_single_position_weight`：单只股票达到过的最大权重；
- `average_concentration_hhi`、`max_concentration_hhi`：持仓权重平方和。

## 口径限制

- 完整交易使用 FIFO 匹配，未卖出的持仓不计入已实现交易胜率；
- 毛盈亏以参考开盘价计算，净盈亏扣除佣金、印花税和滑点；
- 当前指标均为绝对收益指标，基准数据完备后再增加超额收益和信息比率；
- 日频回测无法还原盘口排队、撮合延迟和真实市场冲击。
