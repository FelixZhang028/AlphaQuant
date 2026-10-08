"""全市场数据闭环：主表（含退市股）、日线、分红送配、历史成分与退市结算。

数据闭环的目标是消除幸存者偏差：回测股票池必须覆盖历史时点真实
可交易的全部证券（含此后退市的），行情与公司行为也要覆盖全市场。
BaoStock 免费提供含退市股的全量列表与日线，是本闭环的主力来源；
历史成分暂以规则近似（上市即入池、退市即出池），指数成分历史后续
再接入。所有外网步骤分批落库并记录断点，长任务中断后可续传。
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import date, datetime, UTC
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from quant_platform.core.exceptions import DataUnavailableError
from quant_platform.data.akshare_catalog import AkShareCatalogIngestor
from quant_platform.data.baostock_backfill import (
    BaoStockRangeBackfill,
    normalize_baostock_master,
)
from quant_platform.data.normalizers import canonical_symbol
from quant_platform.data.quality import inspect_daily_bars
from quant_platform.data.repositories.parquet_repository import (
    ParquetMarketDataRepository,
)
from quant_platform.data.repositories.raw_repository import RawDataRepository
from quant_platform.data.versioning import DataManifest, save_manifest

logger = logging.getLogger(__name__)

# 连续失败熔断阈值：疑似网络中断时尽快停下，保留断点等待续传。
CONSECUTIVE_FAILURE_LIMIT = 30
# 整批公司行为抓取连续失败的熔断阈值（AkShare 网络层故障）。
BATCH_FAILURE_LIMIT = 3
# 看门狗强杀进程的退出码：外层守护脚本据此识别并重启续传。
WATCHDOG_EXIT_CODE = 86

ProgressCallback = Callable[[str, int, int], None]


class _ProgressWatchdog:
    """外网请求心跳看门狗，防数据源挂死后进程永久空转。

    实测教训：baostock 连接中断后其内部循环可能既不返回也不抛异常，
    进程以单核 100% 空转十几个小时零进度。本看门狗由守护线程周期
    检查心跳，超时即 ``os._exit`` 强杀进程，交由外层重启循环从断点
    续传；本地落库窗口用 ``pause``/``resume`` 暂停监控，避免写
    Parquet 中途被杀损坏数据文件。
    """

    def __init__(self, timeout_seconds: float) -> None:
        if timeout_seconds <= 0:
            raise ValueError("watchdog timeout must be positive")
        self._timeout = float(timeout_seconds)
        self._deadline: float | None = None
        self._paused = False
        self._lock = threading.Lock()

    def start(self) -> None:
        """武装看门狗并启动守护线程。"""

        self._arm()
        threading.Thread(
            target=self._run, name="backfill-watchdog", daemon=True
        ).start()

    def _arm(self) -> None:
        with self._lock:
            self._deadline = time.monotonic() + self._timeout

    def feed(self) -> None:
        """喂狗：每次外网请求或落库进展前调用。"""

        with self._lock:
            if self._deadline is not None and not self._paused:
                self._deadline = time.monotonic() + self._timeout

    def pause(self) -> None:
        """暂停监控（本地落库窗口内不判超时）。"""

        with self._lock:
            self._paused = True

    def resume(self) -> None:
        """恢复监控并顺带喂狗。"""

        with self._lock:
            self._paused = False
            if self._deadline is not None:
                self._deadline = time.monotonic() + self._timeout

    def expired(self) -> bool:
        with self._lock:
            return (
                self._deadline is not None
                and not self._paused
                and time.monotonic() > self._deadline
            )

    def _run(self) -> None:
        interval = min(self._timeout / 10.0, 5.0)
        while True:
            time.sleep(interval)
            if not self.expired():
                continue
            message = (
                f"看门狗超时：{self._timeout:.0f} 秒无心跳，疑似数据源挂死，"
                f"强制退出进程（exit={WATCHDOG_EXIT_CODE}）等待外层重启续传"
            )
            logger.critical(message)
            print(message, flush=True)
            os._exit(WATCHDOG_EXIT_CODE)


def _range_key(start_date: date, end_date: date) -> str:
    """断点归属键：同一数据集的回填区间变化即视为新任务。"""

    return f"{start_date.isoformat()}..{end_date.isoformat()}"


class ClosedLoopState:
    """断点续传状态：按数据集记录已完成与失败的证券代码。"""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.datasets: dict[str, dict[str, Any]] = {}
        if path is not None and path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self.datasets = {
                        str(key): value
                        for key, value in raw.items()
                        if isinstance(value, dict)
                    }
            except (OSError, json.JSONDecodeError):
                logger.warning("闭环断点文件损坏，忽略并重建：%s", path)

    def progress(self, dataset: str, range_key: str) -> tuple[list[str], dict[str, str]]:
        """读取某数据集断点；区间变化时自动作废旧进度。"""

        record = self.datasets.get(dataset, {})
        if record.get("range") != range_key:
            return [], {}
        done = [str(item) for item in record.get("done", [])]
        failed_raw = record.get("failed", {})
        failed = (
            {str(key): str(value) for key, value in failed_raw.items()}
            if isinstance(failed_raw, dict)
            else {}
        )
        return done, failed

    def record(
        self,
        dataset: str,
        range_key: str,
        done: list[str],
        failed: dict[str, str],
    ) -> None:
        """覆盖式记录某数据集断点并原子落盘。"""

        self.datasets[dataset] = {
            "range": range_key,
            "done": list(done),
            "failed": failed,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self.datasets, ensure_ascii=False), encoding="utf-8"
        )
        os.replace(temporary, self.path)

    def snapshot(self) -> dict[str, Any]:
        """返回可直接展示的断点摘要。"""

        summary: dict[str, Any] = {}
        for dataset, record in self.datasets.items():
            failed = record.get("failed", {})
            summary[dataset] = {
                "range": record.get("range", ""),
                "done": len(record.get("done", [])),
                "failed": len(failed) if isinstance(failed, dict) else 0,
                "updated_at": record.get("updated_at", ""),
            }
        return summary


class FullMarketBackfill:
    """全市场（含退市股）数据闭环回填器。"""

    def __init__(
        self,
        raw_repository: RawDataRepository,
        market_repository: ParquetMarketDataRepository,
        provider: Any | None = None,
        *,
        akshare_client: Any | None = None,
        state_path: str | Path | None = None,
    ) -> None:
        self.raw_repository = raw_repository
        self.market_repository = market_repository
        self._provider = provider
        self.akshare_client = akshare_client
        self.state = ClosedLoopState(Path(state_path) if state_path else None)
        self._range_backfill: BaoStockRangeBackfill | None = None

    # ── 步骤 1：全量主表（BaoStock，含退市股） ─────────────────────────

    def refresh_security_master(self) -> pd.DataFrame:
        """刷新全量 A 股主表：退市股保留 delist_date 与 D 状态。"""

        provider = self._ensure_provider()
        raw = provider.get_security_master()
        if raw.empty:
            raise DataUnavailableError("BaoStock 未返回全量证券列表")
        self.raw_repository.save(
            "baostock", "security_master_full", date.today(), raw, {"universe": "全市场"}
        )
        stocks = raw[raw["type"].astype(str).eq("1")].copy()
        if "code" in stocks.columns:
            stocks["symbol"] = stocks["code"].astype(str).map(canonical_symbol)
        master = normalize_baostock_master(stocks, [])
        if master.empty:
            raise DataUnavailableError("BaoStock 全量列表中没有 A 股股票")
        self.market_repository.save_table("security_master", master)
        provider.close()
        return master

    # ── 步骤 2：全市场日线（分批落库 + 断点续传） ───────────────────────

    def backfill_daily_bars(
        self,
        start_date: date,
        end_date: date,
        *,
        batch_size: int = 50,
        resume: bool = True,
        limit: int = 0,
        progress: ProgressCallback | None = None,
        watchdog: _ProgressWatchdog | None = None,
    ) -> dict[str, Any]:
        """逐只回填全市场日线；单只失败可容忍，连续失败熔断。"""

        provider = self._ensure_provider()
        master = self._require_master()
        symbols = self._overlapping_symbols(master, start_date, end_date)
        if limit > 0:
            symbols = symbols[:limit]
        key = _range_key(start_date, end_date)
        done, failed = self.state.progress("daily_bars", key) if resume else ([], {})
        # Resume retries failures, skipping only successfully persisted symbols.
        done = [symbol for symbol in done if symbol not in failed]
        failed = {}
        done_set = set(done)
        pending = [
            symbol for symbol in symbols if symbol not in done_set and symbol not in failed
        ]
        total = len(symbols)
        rows_this_run = 0
        status_counts: dict[str, int] = {}
        consecutive_failures = 0
        frames: list[pd.DataFrame] = []

        if progress:
            progress("daily_bars", len(done), total)
        provider.login()
        if watchdog is not None:
            watchdog.feed()
        try:
            for symbol in pending:
                if watchdog is not None:
                    watchdog.feed()
                try:
                    frame = self._range().fetch_symbol(symbol, start_date, end_date, master)
                    consecutive_failures = 0
                    if not frame.empty:
                        frames.append(frame)
                    done.append(symbol)
                except Exception as exc:  # noqa: BLE001 - 单只失败不断阻断全市场任务
                    consecutive_failures += 1
                    failed[symbol] = f"{type(exc).__name__}: {exc}"[:300]
                    logger.warning("全市场日线回填失败：%s（%s）", symbol, exc)
                    if consecutive_failures >= CONSECUTIVE_FAILURE_LIMIT:
                        raise
                if len(frames) >= batch_size:
                    rows_this_run += self._flush_bars_checkpoint(
                        frames, status_counts, done, failed, key, watchdog
                    )
                    frames = []
                    if progress:
                        progress("daily_bars", len(done) + len(failed), total)
            if frames:
                rows_this_run += self._flush_bars_checkpoint(
                    frames, status_counts, done, failed, key, watchdog
                )
        finally:
            if watchdog is not None:
                watchdog.pause()
            try:
                self.state.record("daily_bars", key, done, failed)
            finally:
                if watchdog is not None:
                    watchdog.resume()
            provider.close()
        if progress:
            progress("daily_bars", len(done) + len(failed), total)
        return {
            "total": total,
            "done": len(done),
            "failed": failed,
            "rows_this_run": rows_this_run,
            "status_counts": status_counts,
        }

    # ── 步骤 3：全市场分红送配（AkShare 分批 + 断点续传） ───────────────

    def backfill_corporate_actions(
        self,
        start_date: date,
        end_date: date,
        *,
        batch_size: int = 200,
        resume: bool = True,
        limit: int = 0,
        progress: ProgressCallback | None = None,
        watchdog: _ProgressWatchdog | None = None,
    ) -> dict[str, Any]:
        """逐批刷新全市场分红送配；复权因子变化的持仓必须有明细可结算。"""

        master = self._require_master()
        symbols = self._overlapping_symbols(master, start_date, end_date)
        if limit > 0:
            symbols = symbols[:limit]
        key = _range_key(start_date, end_date)
        done, failed = self.state.progress("corporate_actions", key) if resume else ([], {})
        done = [symbol for symbol in done if symbol not in failed]
        failed = {}
        done_set = set(done)
        pending = [
            symbol for symbol in symbols if symbol not in done_set and symbol not in failed
        ]
        total = len(symbols)
        if progress:
            progress("corporate_actions", len(done), total)
        catalog = AkShareCatalogIngestor(
            self.raw_repository,
            self.market_repository,
            client=self._akshare_client(),
        )
        batch_failures = 0
        heartbeat: Callable[[str], None] | None = (
            (lambda _symbol: watchdog.feed()) if watchdog is not None else None
        )
        for index in range(0, len(pending), batch_size):
            chunk = pending[index : index + batch_size]
            if watchdog is not None:
                watchdog.feed()
            try:
                _, chunk_failures = catalog.update_corporate_actions(
                    chunk, heartbeat=heartbeat
                )
                done.extend(symbol for symbol in chunk if symbol not in chunk_failures)
                for symbol in chunk_failures:
                    failed[symbol] = "akshare stock_fhps_detail_em 获取失败"
                batch_failures = 0
            except Exception as exc:  # noqa: BLE001 - 整批失败先记录，连续熔断
                batch_failures += 1
                for symbol in chunk:
                    failed[symbol] = f"{type(exc).__name__}: {exc}"[:300]
                logger.warning("分红送配批次失败（%s 只）：%s", len(chunk), exc)
                if batch_failures >= BATCH_FAILURE_LIMIT:
                    self.state.record("corporate_actions", key, done, failed)
                    raise
            self.state.record("corporate_actions", key, done, failed)
            if progress:
                progress("corporate_actions", len(done) + len(failed), total)
        return {"total": total, "done": len(done), "failed": failed}

    # ── 步骤 4：历史成分表（规则近似） ─────────────────────────────────

    def build_universe_membership(
        self, *, inactive_tolerance_days: int = 365
    ) -> pd.DataFrame:
        """生成规则近似的 universe_membership：上市即入池、退市即出池。

        - effective_from = max(上市日, 本地首根行情日)：没有行情的证券
          无法回测，也不进入成分表；
        - effective_to = 退市日（若本地数据更早截止则取最后行情日）；
          仍在市且近期有行情的证券留空（长期有效）；
        - 长期停牌等导致数据提前截断的在市证券，成分止于最后行情日，
          避免回测引擎因"成分缺少行情"而中断；
        - known_at = effective_from（上市信息在上市时即公开可知）。
        """

        master = self._require_master()
        bars = self.market_repository.read_table("daily_bars")
        if bars.empty:
            raise DataUnavailableError("缺少日线数据，请先完成全市场日线回填")
        bars = bars.copy()
        bars["trade_date"] = pd.to_datetime(bars["trade_date"]).dt.normalize()
        coverage = (
            bars.groupby("symbol")["trade_date"]
            .agg(first_bar="min", last_bar="max")
            .to_dict("index")
        )
        data_end = bars["trade_date"].max()
        stale_cutoff = data_end - pd.Timedelta(days=inactive_tolerance_days)
        rows: list[dict[str, Any]] = []
        for record in master.drop_duplicates("symbol").itertuples(index=False):
            span = coverage.get(str(record.symbol))
            if span is None:
                continue
            listed = (
                pd.Timestamp(record.list_date)
                if pd.notna(record.list_date)
                else pd.NaT
            )
            effective_from = (
                max(listed, span["first_bar"])
                if pd.notna(listed)
                else span["first_bar"]
            )
            delisted = (
                pd.Timestamp(record.delist_date)
                if pd.notna(record.delist_date)
                else pd.NaT
            )
            if pd.notna(delisted):
                effective_to: pd.Timestamp | pd.NaT = min(delisted, span["last_bar"])
            elif span["last_bar"] >= stale_cutoff:
                effective_to = pd.NaT
            else:
                effective_to = span["last_bar"]
            if pd.notna(effective_to) and effective_to < effective_from:
                continue
            rows.append(
                {
                    "symbol": str(record.symbol),
                    "effective_from": effective_from,
                    "effective_to": effective_to,
                    "known_at": effective_from,
                    "source": "rule:listing_period",
                }
            )
        membership = pd.DataFrame(rows)
        if membership.empty:
            raise DataUnavailableError("规则近似未生成任何历史成分，请检查主表与行情")
        for column in ("effective_from", "effective_to", "known_at"):
            membership[column] = pd.to_datetime(membership[column])
        # 按证券替换旧成分行：effective_from 变化时不残留陈旧区间。
        existing = self.market_repository.read_table("universe_membership")
        if not existing.empty:
            existing = existing[~existing["symbol"].isin(set(membership["symbol"]))]
            membership = pd.concat([existing, membership], ignore_index=True)
        self.market_repository.save_table("universe_membership", membership)
        return membership

    # ── 步骤 5：退市结算表（最后收盘价近似） ───────────────────────────

    def build_delisting_settlements(self) -> pd.DataFrame:
        """退市结算：以退市日前最后一根收盘价近似结算价。

        引擎在退市日后的首个交易日按 cash_per_share 把持仓折算为现金；
        缺少结算记录会触发 BacktestValidityError，因此闭环必须补齐。
        """

        master = self._require_master()
        delisted = master[master["delist_date"].notna()]
        if delisted.empty:
            return pd.DataFrame(columns=["symbol", "settlement_date", "cash_per_share"])
        bars = self.market_repository.read_table("daily_bars")
        if bars.empty:
            raise DataUnavailableError("缺少日线数据，请先完成全市场日线回填")
        bars = bars.copy()
        bars["trade_date"] = pd.to_datetime(bars["trade_date"]).dt.normalize()
        scope = bars[bars["symbol"].isin(set(delisted["symbol"]))]
        if scope.empty:
            return pd.DataFrame(columns=["symbol", "settlement_date", "cash_per_share"])
        delist_map = dict(
            zip(delisted["symbol"], pd.to_datetime(delisted["delist_date"]), strict=True)
        )
        scope = scope[scope["trade_date"] <= scope["symbol"].map(delist_map)]
        last = (
            scope.sort_values(["symbol", "trade_date"])
            .groupby("symbol", sort=False)
            .tail(1)[["symbol", "trade_date", "raw_close"]]
        )
        settlements = last.rename(
            columns={"trade_date": "settlement_date", "raw_close": "cash_per_share"}
        ).reset_index(drop=True)
        settlements["cash_per_share"] = pd.to_numeric(
            settlements["cash_per_share"], errors="coerce"
        )
        settlements = settlements[settlements["cash_per_share"].notna()]
        settlements["source"] = "derived:last_close"
        # 按证券替换旧结算行，保持幂等。
        existing = self.market_repository.read_table("delisting_settlements")
        if not existing.empty:
            existing = existing[~existing["symbol"].isin(set(settlements["symbol"]))]
            settlements = pd.concat([existing, settlements], ignore_index=True)
        self.market_repository.save_table("delisting_settlements", settlements)
        return settlements

    # ── 编排：一键闭环 + 数据版本记录 ─────────────────────────────────

    def run_closed_loop(
        self,
        start_date: date,
        end_date: date,
        *,
        batch_size: int = 50,
        actions_batch_size: int = 200,
        limit: int = 0,
        resume: bool = True,
        skip_bars: bool = False,
        skip_actions: bool = False,
        skip_derived: bool = False,
        progress: ProgressCallback | None = None,
        watchdog_timeout: float | None = None,
    ) -> dict[str, Any]:
        """执行全量主表 → 日线 → 分红送配 → 历史成分/退市结算的完整闭环。

        ``watchdog_timeout`` 启用心跳看门狗：单次外网请求超过该秒数
        无进展即强杀进程（退出码 86），供外层守护脚本重启续传；默认
        关闭以保持库调用可测。
        """

        results: dict[str, Any] = {}
        watchdog = (
            _ProgressWatchdog(watchdog_timeout) if watchdog_timeout is not None else None
        )
        if watchdog is not None:
            watchdog.start()
            watchdog.feed()
        master_manifest = DataManifest.start(
            "security_master", "baostock", {"closed_loop": True}
        )
        try:
            master = self.refresh_security_master()
            delisted = int(master["delist_date"].notna().sum())
            results["security_master"] = {"rows": len(master), "delisted": delisted}
            save_manifest(
                self.market_repository,
                master_manifest.succeed(
                    row_count=len(master),
                    symbol_count=int(master["symbol"].nunique()),
                    quality={"delisted": delisted, "scope": "全市场含退市股"},
                ),
            )
        except Exception as exc:
            save_manifest(self.market_repository, master_manifest.fail(exc))
            raise

        if progress:
            progress("security_master", 1, 1)

        if not skip_bars:
            bars_manifest = DataManifest.start(
                "daily_bars",
                "baostock",
                {
                    "closed_loop": True,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "limit": limit,
                },
            )
            try:
                stats = self.backfill_daily_bars(
                    start_date,
                    end_date,
                    batch_size=batch_size,
                    resume=resume,
                    limit=limit,
                    progress=progress,
                    watchdog=watchdog,
                )
                results["daily_bars"] = stats
                save_manifest(
                    self.market_repository,
                    bars_manifest.succeed(
                        row_count=int(stats["rows_this_run"]),
                        symbol_count=int(stats["done"]),
                        min_date=start_date,
                        max_date=end_date,
                        quality={
                            "status_counts": stats["status_counts"],
                            "failed_symbols": len(stats["failed"]),
                            "scope": "全市场含退市股",
                        },
                    ),
                )
            except Exception as exc:
                save_manifest(self.market_repository, bars_manifest.fail(exc))
                raise

        if not skip_actions:
            actions_manifest = DataManifest.start(
                "corporate_actions",
                "akshare",
                {
                    "closed_loop": True,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "limit": limit,
                },
            )
            try:
                stats = self.backfill_corporate_actions(
                    start_date,
                    end_date,
                    batch_size=actions_batch_size,
                    resume=resume,
                    limit=limit,
                    progress=progress,
                    watchdog=watchdog,
                )
                results["corporate_actions"] = stats
                save_manifest(
                    self.market_repository,
                    actions_manifest.succeed(
                        row_count=0,
                        symbol_count=int(stats["done"]),
                        quality={
                            "failed_symbols": len(stats["failed"]),
                            "scope": "全市场含退市股",
                        },
                    ),
                )
            except Exception as exc:
                save_manifest(self.market_repository, actions_manifest.fail(exc))
                raise

        if not skip_derived:
            if progress:
                progress("universe_membership", 0, 1)
            membership_manifest = DataManifest.start(
                "universe_membership", "derived", {"closed_loop": True, "method": "规则近似"}
            )
            try:
                if watchdog is not None:
                    watchdog.feed()
                membership = self.build_universe_membership()
                results["universe_membership"] = {
                    "rows": len(membership),
                    "symbols": int(membership["symbol"].nunique()),
                }
                save_manifest(
                    self.market_repository,
                    membership_manifest.succeed(
                        row_count=len(membership),
                        symbol_count=int(membership["symbol"].nunique()),
                        quality={"method": "rule:listing_period"},
                    ),
                )
            except Exception as exc:
                save_manifest(self.market_repository, membership_manifest.fail(exc))
                raise
            if progress:
                progress("delisting_settlements", 0, 1)
            settlements_manifest = DataManifest.start(
                "delisting_settlements", "derived", {"closed_loop": True}
            )
            try:
                if watchdog is not None:
                    watchdog.feed()
                settlements = self.build_delisting_settlements()
                results["delisting_settlements"] = {"rows": len(settlements)}
                save_manifest(
                    self.market_repository,
                    settlements_manifest.succeed(
                        row_count=len(settlements),
                        symbol_count=int(settlements["symbol"].nunique()),
                    ),
                )
            except Exception as exc:
                save_manifest(self.market_repository, settlements_manifest.fail(exc))
                raise
        if progress and not skip_derived:
            progress("delisting_settlements", 1, 1)
        results["checkpoint"] = self.state.snapshot()
        return results

    # ── 内部工具 ───────────────────────────────────────────────────────

    def _ensure_provider(self) -> Any:
        if self._provider is None:
            from quant_platform.data.providers.baostock_provider import BaoStockDataProvider

            self._provider = BaoStockDataProvider()
        return self._provider

    def _range(self) -> BaoStockRangeBackfill:
        if self._range_backfill is None:
            self._range_backfill = BaoStockRangeBackfill(
                self.raw_repository, self.market_repository, self._ensure_provider()
            )
        return self._range_backfill

    def _akshare_client(self) -> Any:
        if self.akshare_client is None:
            from quant_platform.data.network import ProxyResilientAkShareClient

            import akshare as ak

            self.akshare_client = ProxyResilientAkShareClient(ak, direct_fallback=True)
        return self.akshare_client

    def _require_master(self) -> pd.DataFrame:
        master = self.market_repository.read_table("security_master")
        if master.empty:
            master = self.refresh_security_master()
        return master

    @staticmethod
    def _overlapping_symbols(
        master: pd.DataFrame, start_date: date, end_date: date
    ) -> list[str]:
        """上市期与回填区间有交集的全部股票（含已退市）。"""

        listed = pd.to_datetime(master.get("list_date"), errors="coerce")
        delisted = pd.to_datetime(master.get("delist_date"), errors="coerce")
        overlap = (listed.isna() | (listed <= pd.Timestamp(end_date))) & (
            delisted.isna() | (delisted >= pd.Timestamp(start_date))
        )
        return sorted(master.loc[overlap, "symbol"].astype(str).unique())

    def _flush_bars_checkpoint(
        self,
        frames: list[pd.DataFrame],
        status_counts: dict[str, int],
        done: list[str],
        failed: dict[str, str],
        range_key: str,
        watchdog: _ProgressWatchdog | None,
    ) -> int:
        """落库一批日线并记断点；写文件期间暂停看门狗防误杀。"""

        if watchdog is not None:
            watchdog.pause()
        try:
            rows = self._flush_bars(frames, status_counts)
            self.state.record("daily_bars", range_key, done, failed)
            return rows
        finally:
            if watchdog is not None:
                watchdog.resume()

    def _flush_bars(self, frames: list[pd.DataFrame], status_counts: dict[str, int]) -> int:
        """把一批日线落库（含交易日历增量）并累计质量分布。"""

        if not frames:
            return 0
        daily = pd.concat(frames, ignore_index=True).sort_values(["trade_date", "symbol"])
        report = inspect_daily_bars(daily)
        for key, value in report.status_counts.items():
            status_counts[key] = status_counts.get(key, 0) + int(value)
        calendar = pd.DataFrame(
            {
                "cal_date": sorted(daily["trade_date"].dropna().unique()),
                "is_open": 1,
                "exchange": "CN",
                "source": "baostock_bar_union",
            }
        )
        self.market_repository.save_table("trade_calendar", calendar)
        self.market_repository.save_table("daily_bars", daily)
        return len(daily)
