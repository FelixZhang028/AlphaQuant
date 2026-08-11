"""Command-line entry points for data, backtest, and sample workflows."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from quant_platform.application.backtest_service import BacktestService, parse_date
from quant_platform.application.data_service import DataCenterService
from quant_platform.backtest.engine import BacktestEngine
from quant_platform.core.config import require_mapping
from quant_platform.core.logging import configure_logging
from quant_platform.sample_data import generate_sample_market_data


def _load_component_configs(app_path: str | Path) -> dict[str, Any]:
    """Compatibility wrapper for callers that inspect effective configuration."""

    return BacktestService(app_path).configs


def build_engine(app_path: str | Path) -> tuple[BacktestEngine, dict[str, Any]]:
    """Build an engine through the same application service used by the web UI."""

    return BacktestService(app_path).build_engine()


def command_sample_data(args: argparse.Namespace) -> None:
    configs = _load_component_configs(args.config)
    universe = require_mapping(configs["universe"], "universe")
    repository = require_mapping(configs["app"], "data")["repository"]
    generate_sample_market_data(
        repository,
        [str(symbol) for symbol in universe["symbols"]],
        parse_date(args.start_date),
        parse_date(args.end_date),
        args.seed,
    )
    print(f"Sample market data written to {Path(repository).resolve()}")


def command_backtest(args: argparse.Namespace) -> None:
    service = BacktestService(args.config)
    request = service.default_request()
    request = replace(
        request,
        start_date=parse_date(args.start_date) if args.start_date else request.start_date,
        end_date=parse_date(args.end_date) if args.end_date else request.end_date,
        initial_cash=(
            float(args.initial_cash) if args.initial_cash is not None else request.initial_cash
        ),
    )
    run = service.run(request)
    print(json.dumps(run.result.summary, ensure_ascii=False, indent=2))
    print(f"Run artifacts: {run.output_dir.resolve()}")


def command_data_backfill(args: argparse.Namespace) -> None:
    """Backfill configured symbols using the configured provider route."""

    result = DataCenterService(args.config).update_market_data(
        parse_date(args.start_date),
        parse_date(args.end_date),
    )
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2, default=str))


def command_strategies(args: argparse.Namespace) -> None:
    """List strategies found without manual registration."""

    for metadata in BacktestService(args.config).available_strategies():
        print(f"{metadata.plugin_name}\t{metadata.display_name}")


def _add_config_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", default=argparse.SUPPRESS)


def make_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""

    parser = argparse.ArgumentParser(description="A-share quant platform")
    parser.set_defaults(config="configs/app.yaml")
    parser.add_argument("--config", default="configs/app.yaml")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sample = subparsers.add_parser("sample-data", help="generate deterministic local demo data")
    _add_config_argument(sample)
    sample.add_argument("--start-date", default="20220103")
    sample.add_argument("--end-date", default="20241231")
    sample.add_argument("--seed", type=int, default=42)
    sample.set_defaults(func=command_sample_data)

    backtest = subparsers.add_parser("backtest", help="run a configured backtest")
    _add_config_argument(backtest)
    backtest.add_argument("--start-date")
    backtest.add_argument("--end-date")
    backtest.add_argument("--initial-cash", type=float)
    backtest.set_defaults(func=command_backtest)

    backfill = subparsers.add_parser("data-backfill", help="download and standardize provider data")
    _add_config_argument(backfill)
    backfill.add_argument("--start-date", required=True)
    backfill.add_argument("--end-date", required=True)
    backfill.set_defaults(func=command_data_backfill)

    strategies = subparsers.add_parser(
        "strategies", help="list automatically discovered strategies"
    )
    _add_config_argument(strategies)
    strategies.set_defaults(func=command_strategies)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Run the command-line application."""

    args = make_parser().parse_args(argv)
    configure_logging()
    args.func(args)


if __name__ == "__main__":
    main()
