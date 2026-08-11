"""Chinese labels for user-facing dataframes and platform states."""

from __future__ import annotations

from typing import Any

import pandas as pd

COLUMN_LABELS: dict[str, str] = {
    "run_id": "运行编号",
    "run_label": "回测名称",
    "run_kind": "运行类型",
    "parent_experiment_id": "所属实验",
    "baseline_run_id": "基准回测",
    "version_id": "版本号",
    "dataset": "数据集",
    "source": "数据来源",
    "provider": "数据来源",
    "display_name": "名称",
    "role": "用途",
    "readiness": "配置状态",
    "detail": "说明",
    "provider_route": "调用路径",
    "fallback_used": "发生回退",
    "requested_route": "请求来源顺序",
    "fallback_enabled": "允许自动回退",
    "status": "状态",
    "decision": "风控结果",
    "event_type": "检查类型",
    "action": "风控动作",
    "reason": "原因",
    "error": "错误说明",
    "message": "结果说明",
    "created_at": "创建时间",
    "updated_at": "更新时间",
    "started_at": "开始时间",
    "completed_at": "完成时间",
    "ingested_at": "入库时间",
    "symbol": "股票代码",
    "name": "股票名称",
    "exchange": "交易所",
    "list_status": "上市状态",
    "list_date": "上市日期",
    "delist_date": "退市日期",
    "trade_date": "交易日期",
    "signal_date": "信号日期",
    "execution_date": "执行日期",
    "buy_date": "买入日期",
    "sell_date": "卖出日期",
    "start_date": "开始日期",
    "end_date": "结束日期",
    "min_date": "最早日期",
    "max_date": "最晚日期",
    "raw_open": "未复权开盘价",
    "raw_high": "未复权最高价",
    "raw_low": "未复权最低价",
    "raw_close": "未复权收盘价",
    "pre_close": "前收盘价",
    "adjusted_close": "前复权收盘价",
    "adj_factor": "复权因子",
    "close": "估值收盘价",
    "volume": "成交量（股）",
    "amount": "成交额（元）",
    "up_limit": "涨停价",
    "down_limit": "跌停价",
    "is_suspended": "是否停牌",
    "is_st": "是否ST",
    "is_listed": "是否上市",
    "quality_status": "数据质量状态",
    "rows": "实际记录数",
    "row_count": "记录数",
    "symbol_count": "股票数量",
    "expected_rows": "预计记录数",
    "missing_rows": "缺失记录数",
    "coverage_ratio": "覆盖率",
    "duplicate_rows": "重复记录数",
    "unknown_status_rows": "状态未知记录数",
    "local_rows": "本地行情记录数",
    "local_start_date": "本地开始日期",
    "local_end_date": "本地结束日期",
    "has_local_data": "已有本地行情",
    "missing_price_rows": "价格缺失记录数",
    "strategy": "策略",
    "strategy_id": "策略实例编号",
    "parameters": "策略参数",
    "optimization_id": "参数优化编号",
    "train_run_id": "训练期回测编号",
    "test_run_id": "样本外回测编号",
    "objective_value": "优化指标值",
    "train_objective_value": "训练期优化指标值",
    "eligible": "是否满足约束",
    "rank": "排名",
    "order_id": "委托编号",
    "fill_id": "成交编号",
    "buy_order_id": "买入委托编号",
    "sell_order_id": "卖出委托编号",
    "side": "买卖方向",
    "quantity": "数量（股）",
    "filled_quantity": "已成交数量（股）",
    "remaining_quantity": "未成交数量（股）",
    "price": "成交价格",
    "reference_price": "参考价格",
    "commission": "佣金",
    "stamp_tax": "印花税",
    "slippage_cost": "滑点成本",
    "filled_at": "成交时间",
    "reject_reason": "拒绝原因",
    "available_quantity": "可卖数量（股）",
    "average_cost": "平均持仓成本",
    "market_value": "持仓市值",
    "target_weight": "目标权重",
    "score": "策略评分",
    "target_count": "目标股票数",
    "total_weight": "目标总仓位",
    "max_weight": "最大单股权重",
    "current_drawdown": "当前回撤",
    "current_total_weight": "当前总仓位",
    "current_max_weight": "当前最大单股权重",
    "buy_price": "买入成交价",
    "sell_price": "卖出成交价",
    "buy_reference_price": "买入参考价",
    "sell_reference_price": "卖出参考价",
    "gross_pnl": "毛盈亏",
    "direct_cost": "直接交易费用",
    "net_pnl": "净盈亏",
    "return_rate": "交易收益率",
    "holding_days": "持仓天数",
    "cumulative_return": "累计收益",
    "annual_return": "年化收益",
    "annual_volatility": "年化波动率",
    "downside_volatility": "下行波动率",
    "risk_free_rate": "无风险利率",
    "best_day_return": "最佳单日收益",
    "worst_day_return": "最差单日收益",
    "positive_day_ratio": "正收益交易日比例",
    "positive_month_ratio": "正收益月份比例",
    "return_observations": "收益率观测数",
    "sharpe": "夏普比率",
    "sortino": "索提诺比率",
    "calmar": "卡玛比率",
    "max_drawdown": "最大回撤",
    "max_drawdown_start_date": "最大回撤开始日期",
    "max_drawdown_trough_date": "最大回撤谷底日期",
    "max_drawdown_recovery_date": "最大回撤恢复日期",
    "max_drawdown_duration_trading_days": "最大回撤持续交易日",
    "total_transaction_cost": "总交易成本",
    "orders": "委托数",
    "fills": "成交数",
    "filled_orders": "已成交委托数",
    "rejected_orders": "已拒绝委托数",
    "failed_orders": "失败委托数",
    "order_fill_rate": "委托成交率",
    "buy_fills": "买入成交数",
    "sell_fills": "卖出成交数",
    "closed_trades": "已平仓交易数",
    "winning_trades": "盈利交易数",
    "losing_trades": "亏损交易数",
    "trade_win_rate": "交易胜率",
    "average_trade_pnl": "平均每笔净盈亏",
    "average_win": "平均盈利",
    "average_loss": "平均亏损",
    "payoff_ratio": "盈亏比",
    "profit_factor": "利润因子",
    "max_trade_profit": "单笔最大盈利",
    "max_trade_loss": "单笔最大亏损",
    "average_holding_days": "平均持仓天数",
    "max_holding_days": "最长持仓天数",
    "realized_gross_pnl": "已实现毛盈亏",
    "realized_net_pnl": "已实现净盈亏",
    "transaction_cost_to_initial_cash": "交易成本占初始资金比例",
    "traded_notional": "累计成交金额",
    "portfolio_turnover": "组合换手率",
    "annualized_turnover": "年化换手率",
    "average_position_count": "平均持仓数量",
    "max_position_count": "最大持仓数量",
    "average_exposure": "平均仓位",
    "max_exposure": "最大仓位",
    "average_cash_ratio": "平均现金比例",
    "minimum_cash_ratio": "最低现金比例",
    "time_in_market_ratio": "在场时间比例",
    "max_single_position_weight": "最大单只股票权重",
    "average_concentration_hhi": "平均持仓集中度",
    "max_concentration_hhi": "最大持仓集中度",
    "initial_cash": "初始资金",
    "final_equity": "期末权益",
    "risk_checks": "风控检查次数",
    "risk_rejections": "风控拒绝数",
    "risk_adjustments": "风控自动调整数",
    "validity_status": "结果可信度",
    "metrics_reliable": "绩效指标可用",
    "legacy_unverified": "旧版未验证",
    "validity_audit_version": "审计版本",
    "evaluation_mode": "评价方式",
    "unknown_market_rows": "未知市场状态记录数",
    "unknown_market_symbols": "未知市场状态股票数",
    "unknown_status_orders": "未知状态拒单数",
    "window": "滚动窗口",
    "train_start": "训练开始日期",
    "train_end": "训练结束日期",
    "test_start": "样本外开始日期",
    "test_end": "样本外结束日期",
    "selected_parameters": "入选参数",
}


VALUE_LABELS: dict[str, dict[str, str]] = {
    "run_kind": {
        "single": "单次回测",
        "optimization": "参数优化",
        "walk_forward_oos": "样本外验证",
    },
    "source": {
        "ifind": "iFinD",
        "akshare": "AkShare",
        "ifind -> akshare": "iFinD → AkShare",
    },
    "provider": {"ifind": "iFinD", "akshare": "AkShare"},
    "role": {"PRIMARY": "首选", "FALLBACK": "备用"},
    "readiness": {"READY": "已配置", "NOT_READY": "未就绪"},
    "provider_route": {
        "ifind:success": "iFinD 成功",
        "akshare:success": "AkShare 成功",
        "ifind:failed -> akshare:success": "iFinD 失败 → AkShare 成功",
    },
    "requested_route": {
        "ifind -> akshare": "iFinD → AkShare",
        "akshare -> ifind": "AkShare → iFinD",
        "ifind": "仅 iFinD",
        "akshare": "仅 AkShare",
    },
    "status": {
        "CREATED": "已创建",
        "READY": "已就绪",
        "RUNNING": "运行中",
        "ACTIVE": "运行正常",
        "SUCCESS": "成功",
        "FAILED": "失败",
        "SUBMITTED": "已提交",
        "ACCEPTED": "已受理",
        "PARTIALLY_FILLED": "部分成交",
        "FILLED": "全部成交",
        "CANCEL_PENDING": "撤单处理中",
        "CANCELLED": "已撤单",
        "REJECTED": "已拒绝",
    },
    "状态": {
        "CREATED": "已创建",
        "READY": "已就绪",
        "RUNNING": "运行中",
        "ACTIVE": "运行正常",
        "SUCCESS": "成功",
        "FAILED": "失败",
        "SUBMITTED": "已提交",
        "ACCEPTED": "已受理",
        "PARTIALLY_FILLED": "部分成交",
        "FILLED": "全部成交",
        "CANCEL_PENDING": "撤单处理中",
        "CANCELLED": "已撤单",
        "REJECTED": "已拒绝",
    },
    "decision": {"PASS": "通过", "ADJUST": "调整", "REJECT": "拒绝"},
    "action": {
        "NONE": "无",
        "STOP_NEW": "停止新开仓",
        "REBALANCE": "持仓纠偏",
        "REDUCE": "降低仓位",
        "LIQUIDATE": "清仓",
    },
    "validity_status": {"VALID": "有效", "WARNING": "有警告", "INVALID": "无效"},
    "side": {"BUY": "买入", "SELL": "卖出"},
    "quality_status": {
        "OK": "正常",
        "UNKNOWN_STATUS": "交易状态未知",
        "MISSING_PRICE": "价格缺失",
        "MISSING_ADJ_FACTOR": "复权因子缺失",
    },
    "reject_reason": {
        "MISSING_EXECUTION_BAR": "执行日缺少行情",
        "SUSPENDED": "证券停牌",
        "UNKNOWN_SUSPENSION_STATUS": "停牌状态未知",
        "UNKNOWN_MARKET_STATUS": "交易状态未知",
        "MARKET_DATA_NOT_TRADABLE": "行情数据不可用于成交",
        "UNKNOWN_PRICE_LIMIT": "涨跌停价格未知",
        "OPEN_AT_UPPER_LIMIT": "涨停开盘，买入被拒绝",
        "OPEN_AT_LOWER_LIMIT": "跌停开盘，卖出被拒绝",
        "INSUFFICIENT_CASH_OR_QUANTITY": "资金或可用数量不足",
    },
    "list_status": {"L": "上市", "D": "退市", "P": "暂停上市"},
    "dataset": {
        "security_master": "证券主表",
        "daily_bars": "股票日线行情",
        "benchmark_bars": "基准指数行情",
        "trade_calendar": "交易日历",
    },
    "数据集": {
        "security_master": "证券主表",
        "daily_bars": "股票日线行情",
        "benchmark_bars": "基准指数行情",
        "trade_calendar": "交易日历",
    },
}


GENERAL_VALUE_LABELS: dict[str, str] = {
    "daily": "每日",
    "weekly": "每周",
    "monthly": "每月",
    "in_sample": "普通历史回测",
    "training": "训练期",
    "out_of_sample": "样本外测试",
    "DAILY_POSITION": "每日实际持仓",
    "TARGET_PORTFOLIO": "策略目标仓位",
    "True": "是",
    "False": "否",
}


def localize_value(value: Any, *, column: str | None = None) -> Any:
    """Translate a known state while preserving numbers and missing values."""

    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return value
    text = str(value)
    if column and column in VALUE_LABELS:
        return VALUE_LABELS[column].get(text, value)
    return GENERAL_VALUE_LABELS.get(text, value)


def localize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a display-only copy with Chinese columns and enum values."""

    result = frame.copy()
    for column in result.columns:
        if column in VALUE_LABELS:
            result[column] = result[column].map(
                lambda value, source=column: localize_value(value, column=source)
            )
        elif result[column].dtype == bool:
            result[column] = result[column].map({True: "是", False: "否"})
        else:
            result[column] = result[column].map(localize_value)
    labels = {column: localized_column_label(str(column)) for column in result.columns}
    return result.rename(columns=labels)


def localized_column_label(column: str) -> str:
    """Return a Chinese display label, including walk-forward metric prefixes."""

    if column in COLUMN_LABELS:
        return COLUMN_LABELS[column]
    if column.startswith("test_"):
        base_label = COLUMN_LABELS.get(column.removeprefix("test_"))
        if base_label is not None:
            return f"样本外{base_label}"
    return column


def rebalance_label(value: str) -> str:
    """Return the Chinese label for a rebalance frequency."""

    return str(GENERAL_VALUE_LABELS.get(value, value))


def status_label(value: str) -> str:
    """Return the Chinese label for a lifecycle or order status."""

    return str(VALUE_LABELS["status"].get(value, value))
