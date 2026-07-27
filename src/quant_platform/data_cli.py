"""Command-line interface dedicated to local data-center operations."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import datetime

from quant_platform.application.data_service import DataCenterService


def _parse_date(value: str):  # type: ignore[no-untyped-def]
    return datetime.strptime(value.replace("-", ""), "%Y%m%d").date()


def _status(args: argparse.Namespace) -> None:
    overview = DataCenterService(args.config).overview()
    print(json.dumps(overview.to_dict(), ensure_ascii=False, indent=2, default=str))


def _update(args: argparse.Namespace) -> None:
    service = DataCenterService(args.config)
    results = service.update_all(
        _parse_date(args.start_date),
        _parse_date(args.end_date),
        include_security_master=not args.skip_security_master,
        include_market=not args.skip_market,
        include_benchmark=not args.skip_benchmark,
    )
    print(
        json.dumps(
            [asdict(result) for result in results],
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


def make_parser() -> argparse.ArgumentParser:
    """Create the data-center command parser."""

    parser = argparse.ArgumentParser(description="A-share local data center")
    parser.add_argument("--config", default="configs/app.yaml")
    subparsers = parser.add_subparsers(dest="command", required=True)
    status = subparsers.add_parser("status", help="show local coverage and versions")
    status.set_defaults(func=_status)
    update = subparsers.add_parser("update", help="update selected AkShare datasets")
    update.add_argument("--start-date", required=True)
    update.add_argument("--end-date", required=True)
    update.add_argument("--skip-security-master", action="store_true")
    update.add_argument("--skip-market", action="store_true")
    update.add_argument("--skip-benchmark", action="store_true")
    update.set_defaults(func=_update)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Run a data-center command."""

    args = make_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
