"""Guided research correctness and recoverable UI workflow."""

import json
from datetime import date
from pathlib import Path
from shutil import copytree

import pandas as pd
import pytest
import yaml
from streamlit.testing.v1 import AppTest

from quant_platform.application.backtest_service import BacktestService
from quant_platform.application.guided_research import idea_request, inspect_request
from quant_platform.sample_data import generate_sample_market_data

ROOT = Path(__file__).parents[2]


@pytest.fixture
def research(tmp_path, monkeypatch):
    copytree(ROOT / "configs", tmp_path / "configs")
    path = tmp_path / "configs/app.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    config["data"]["repository"] = "runtime/market"
    config["backtest"]["start_date"] = "2023-01-03"
    config["backtest"]["end_date"] = "2023-12-29"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    symbols = yaml.safe_load((tmp_path / config["universe"]["config"]).read_text(encoding="utf-8"))[
        "universe"
    ]["symbols"]
    monkeypatch.chdir(tmp_path)
    repo = generate_sample_market_data(
        "runtime/market", symbols, date(2022, 1, 3), date(2023, 12, 29)
    )
    benchmark = repo.get_daily_bars([symbols[0]])[["symbol", "trade_date", "raw_close"]].copy()
    benchmark["symbol"] = "000300.SH"
    repo.save_table("benchmark_bars", benchmark)
    return BacktestService(), repo


def test_intent_maps_to_real_factor_and_missing_data_blocks(research):
    service, repo = research
    req = idea_request(service, "低波动", date(2023, 1, 3), date(2023, 12, 29), 1e6, 5, "weekly")
    assert json.loads(req.strategy_parameters["factors_json"])[0]["name"] == "volatility_20"
    checks = inspect_request(service, req)
    assert checks["状态"].eq("通过").all(), checks.to_dict("records")
    bars = repo.get_daily_bars()
    # Remove a real trading-day observation without modifying the calendar.
    missing = bars[(bars.trade_date == pd.Timestamp("2023-03-01"))].iloc[0]
    monkey = pytest.MonkeyPatch()
    original = repo.get_daily_bars
    engine, snapshot = service.build_engine(req)
    with monkey.context() as m:
        m.setattr(
            engine.repository,
            "get_daily_bars",
            lambda *a, **k: original(*a, **k).loc[
                lambda f: ~((f.symbol == missing.symbol) & (f.trade_date == missing.trade_date))
            ],
        )
        m.setattr(service, "build_engine", lambda _: (engine, snapshot))
        checks = inspect_request(service, req)
    assert checks.set_index("检查项目").loc["区间行情", "状态"] == "需处理"


def test_guided_ui_runs_and_keeps_draft(research):
    service, repo = research
    app = AppTest.from_file(str(ROOT / "src/quant_platform/web/app.py"), default_timeout=30)
    app.session_state["aq_authenticated_user"] = "test-user"
    app.run().switch_page("app_pages/0_strategy_hub.py").run()
    assert not app.exception
    app.radio(key="_guided_idea").set_value("低波动").run()
    app.button(key="guided_check").click().run()
    assert not app.exception
    assert app.session_state["guided_draft"]["checks"]["状态"].eq("通过").all()
    assert app.button(key="guided_run").disabled
    next(c for c in app.checkbox if c.key.startswith("guided_confirm_")).check().run()
    app.button(key="guided_run").click().run()
    assert not app.exception
    assert app.session_state["guided_draft"].get("run_id"), [e.value for e in app.error]
    app.number_input(key="_guided_top_n").set_value(3).run()
    assert app.button(key="guided_run").disabled
    assert "run_id" not in app.session_state["guided_draft"]
    app.switch_page("home.py").run().switch_page("app_pages/0_strategy_hub.py").run()
    assert app.number_input(key="_guided_top_n").value == 3


def test_failed_update_preserves_inputs_and_can_retry(research, monkeypatch):
    service, repo = research
    # Pretend the data is absent until the second update attempt succeeds.
    from quant_platform.application import guided_research as implementation

    actual = implementation.inspect_request
    attempts = []

    def update(*args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise ConnectionError("https://example.test?token=private-test-secret")
        return []

    def inspect(s, r):
        if len(attempts) < 2:
            return pd.DataFrame([{"检查项目": "比较基准", "状态": "需处理", "说明": "缺少行情"}])
        return actual(s, r)

    monkeypatch.setattr("quant_platform.web.guided_research.inspect_request", inspect)
    monkeypatch.setattr("quant_platform.web.guided_research.DataCenterService.update_all", update)
    app = AppTest.from_file(str(ROOT / "src/quant_platform/web/app.py"), default_timeout=30)
    app.session_state["aq_authenticated_user"] = "test-user"
    app.run().switch_page("app_pages/0_strategy_hub.py").run()
    app.radio(key="_guided_idea").set_value("短期超跌").run()
    app.number_input(key="_guided_top_n").set_value(3).run()
    app.button(key="guided_check").click().run()
    app.button(key="guided_update").click().run()
    assert not app.exception
    assert app.error
    assert all("private-test-secret" not in e.value for e in app.error)
    assert app.number_input(key="_guided_top_n").value == 3
    assert app.radio(key="_guided_idea").value == "短期超跌"
    app.button(key="guided_update").click().run()
    assert not app.exception
    assert app.session_state["guided_draft"]["checks"]["状态"].eq("通过").all()
