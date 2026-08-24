import pandas as pd

from quant_platform.backtest.analytics import analyze_backtest
from quant_platform.backtest.diagnosis import generate_diagnosis
from quant_platform.backtest.result import BacktestResult


def _make_result(
    *,
    with_benchmark: bool = False,
    empty_fills: bool = False,
) -> BacktestResult:
    nav = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(
                ["2024-01-02", "2024-01-31", "2024-02-29", "2024-03-29"]
            ),
            "equity": [100_000.0, 105_000.0, 98_000.0, 103_000.0],
        }
    )
    if with_benchmark:
        nav["benchmark_equity"] = [1.0, 1.02, 1.01, 1.03]
    fills = pd.DataFrame(
        [
            {
                "order_id": "buy-win",
                "symbol": "000001.SZ",
                "side": "BUY",
                "quantity": 100,
                "price": 10.0,
                "reference_price": 10.0,
                "commission": 5.0,
                "stamp_tax": 0.0,
                "slippage_cost": 5.0,
                "trade_date": "2024-01-02",
            },
            {
                "order_id": "sell-win",
                "symbol": "000001.SZ",
                "side": "SELL",
                "quantity": 100,
                "price": 15.0,
                "reference_price": 15.0,
                "commission": 5.0,
                "stamp_tax": 7.5,
                "slippage_cost": 5.0,
                "trade_date": "2024-01-31",
            },
            {
                "order_id": "buy-lose",
                "symbol": "600000.SH",
                "side": "BUY",
                "quantity": 100,
                "price": 20.0,
                "reference_price": 20.0,
                "commission": 5.0,
                "stamp_tax": 0.0,
                "slippage_cost": 5.0,
                "trade_date": "2024-02-01",
            },
            {
                "order_id": "sell-lose",
                "symbol": "600000.SH",
                "side": "SELL",
                "quantity": 100,
                "price": 12.0,
                "reference_price": 12.0,
                "commission": 5.0,
                "stamp_tax": 6.0,
                "slippage_cost": 5.0,
                "trade_date": "2024-02-29",
            },
        ]
    )
    orders = pd.DataFrame(
        {
            "order_id": ["buy-win", "sell-win", "buy-lose", "sell-lose"],
            "status": ["FILLED", "FILLED", "FILLED", "FILLED"],
        }
    )
    positions = pd.DataFrame(
        {
            "trade_date": ["2024-01-02"],
            "symbol": ["000001.SZ"],
            "market_value": [1_000.0],
        }
    )
    analytics = analyze_backtest(nav, orders, fills, positions, initial_cash=100_000.0)
    trades = analytics.trades
    if empty_fills:
        fills = fills.iloc[0:0]
        trades = pd.DataFrame()
    return BacktestResult(
        run_id="test-run",
        nav=nav,
        signals=pd.DataFrame(),
        targets=pd.DataFrame(),
        orders=orders,
        fills=fills,
        trades=trades,
        positions=positions,
        risk_events=pd.DataFrame(),
        summary=analytics.summary,
        validity={},
    )


def _section_titles(report) -> list[str]:
    return [section.title for section in report.sections]


def test_diagnosis_covers_all_sections_without_benchmark() -> None:
    report = generate_diagnosis(_make_result())

    assert _section_titles(report) == [
        "为什么盈利/亏损",
        "哪些时期影响最大",
        "胜率与盈亏结构",
        "交易成本损失",
        "与沪深300对比",
        "可优先调整的参数建议",
    ]


def test_pnl_source_lists_top_winner_and_loser() -> None:
    report = generate_diagnosis(_make_result())
    pnl_section = report.sections[0]
    joined = "\n".join(pnl_section.bullets)

    assert "000001.SZ" in joined
    assert "赚钱最多" in joined
    assert "600000.SH" in joined
    assert "亏钱最多" in joined


def test_periods_and_cost_sections_have_plain_content() -> None:
    report = generate_diagnosis(_make_result())
    period_section = report.sections[1]
    cost_section = report.sections[3]

    assert any("2024-02" in bullet and "最差" in bullet for bullet in period_section.bullets)
    assert any("交易成本" in bullet and "佣金" in bullet for bullet in cost_section.bullets)
    assert any("初始资金" in bullet for bullet in cost_section.bullets)


def test_win_rate_structure_mentions_win_rate() -> None:
    report = generate_diagnosis(_make_result())
    win_section = report.sections[2]

    assert any("胜率" in bullet for bullet in win_section.bullets)
    assert any("平均每笔" in bullet for bullet in win_section.bullets)


def test_no_benchmark_gives_friendly_hint() -> None:
    report = generate_diagnosis(_make_result())
    benchmark_section = report.sections[4]

    assert any("未配置" in bullet for bullet in benchmark_section.bullets)


def test_benchmark_equity_column_enables_comparison() -> None:
    report = generate_diagnosis(_make_result(with_benchmark=True))
    benchmark_section = report.sections[4]

    assert any("沪深300" in bullet and "基准收益" in bullet for bullet in benchmark_section.bullets)
    assert any("跑赢" in bullet or "跑输" in bullet for bullet in benchmark_section.bullets)


def test_empty_fills_degrades_gracefully() -> None:
    report = generate_diagnosis(_make_result(empty_fills=True))

    assert _section_titles(report) == [
        "为什么盈利/亏损",
        "哪些时期影响最大",
        "胜率与盈亏结构",
        "交易成本损失",
        "与沪深300对比",
        "可优先调整的参数建议",
    ]
    assert any("无法拆解" in bullet for bullet in report.sections[0].bullets)
    assert all(section.bullets for section in report.sections)


def test_suggestions_prefixed_with_advice() -> None:
    report = generate_diagnosis(_make_result())
    suggestion_section = report.sections[5]

    assert 1 <= len(suggestion_section.bullets) <= 4
    assert all(bullet.startswith("建议") for bullet in suggestion_section.bullets)
