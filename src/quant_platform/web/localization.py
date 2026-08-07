"""Chinese labels for user-facing dataframes and platform states."""

from __future__ import annotations

from typing import Any

import pandas as pd

COLUMN_LABELS: dict[str, str] = {
    "run_id": "运行编号",
    "version_id": "版本号",
    "dataset": "数据集",
    "source": "数据来源",
    "provider": "数据来源",
    "role": "用途",
    "readiness": "配置状态",
    "detail": "说明",
    "provider_route": "调用路径",
    "fallback_used": "发生回退",
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
    "objective_value": "优化指标值",
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
    "sharpe": "夏普比率",
    "sortino": "索提诺比率",
    "calmar": "卡玛比率",
    "max_drawdown": "最大回撤",
    "total_transaction_cost": "总交易成本",
    "orders": "委托数",
    "fills": "成交数",
    "risk_rejections": "风控拒绝数",
    "risk_adjustments": "风控自动调整数",
    "validity_status": "结果可信度",
    "evaluation_mode": "评价方式",
    "window": "滚动窗口",
    "train_start": "训练开始日期",
    "train_end": "训练结束日期",
    "test_start": "样本外开始日期",
    "test_end": "样本外结束日期",
    "selected_parameters": "入选参数",
}


VALUE_LABELS: dict[str, dict[str, str]] = {
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
    return result.rename(columns=COLUMN_LABELS)


def rebalance_label(value: str) -> str:
    """Return the Chinese label for a rebalance frequency."""

    return str(GENERAL_VALUE_LABELS.get(value, value))


def status_label(value: str) -> str:
    """Return the Chinese label for a lifecycle or order status."""

    return str(VALUE_LABELS["status"].get(value, value))
