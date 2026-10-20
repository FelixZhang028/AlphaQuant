"""The update a trading day needs, run once after the close for the whole market.

Steps, each on its own: one that fails is reported and the next still runs.

1. Is today a trading day, and are today's bars published yet? If not, and the local data is behind
   the last trading day that is published, the run catches up to that day instead (``caught_up``);
   otherwise nothing is downloaded.
2. The security list (new listings, delistings).
3. Daily bars of every listed Shanghai and Shenzhen stock, ``BATCH`` at a time, through the same path as a manual
   update: each request starts at the stock's last stored bar and the new adjustment factors
   are put on the stored basis. Valuation and turnover come with the bars. A stock with no
   bars at all yet (a new listing) gets its whole history.
4. Dividend records for adjustment-factor changes that have none.
5. Benchmark index levels, index members and the industry classification.
6. The listing-period universe and delisting settlements (computed locally).

Steps and stocks already updated today are skipped when a run resumes, so a run that was
stopped or killed picks up where it was. A stock that fails is retried on its own, so it
does not hold back the rest of its batch. When the data source refuses the server (BaoStock's
blacklist) the whole run stops at once: every further request would only prolong the block.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from quant_platform.core.diagnostics import redact_text
from quant_platform.core.exceptions import DataSourceBlocked
from quant_platform.core.files import write_json_atomic

BATCH = 200
# 判断今天的行情是否已经发布：几只几乎不停牌的大盘股，有一只有今天的日线就算发布了。
READY_PROBES = ("600519.SH", "000001.SZ", "601318.SH")
# 新上市股票补全历史时最早从这一天开始（和全市场下载一致）。
HISTORY_START = date(2015, 1, 5)
# 只更新沪深两市：BaoStock 没有北交所的行情，本地也没有（一批里混进一只，整批都会失败）。
MARKETS = (".SH", ".SZ")
# 连续几批失败就停下：多半是网络断了，等下次续传。
BATCH_FAILURE_LIMIT = 3
STEPS = ("security_master", "daily_bars", "corporate_actions", "benchmarks", "index_constituents", "industry", "derived")
# 补齐前几天：本地有这一天行情的股票少于在市股票的这个比例，就认为还没更新到这一天。
CAUGHT_UP_SHARE = 0.95
CALENDAR_LOOKBACK_DAYS = 20


def _read(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write(path: Path, value: dict[str, Any]) -> None:
    write_json_atomic(path, value)


def _error(exc: BaseException) -> str:
    return redact_text(f"{type(exc).__name__}: {exc}")[:300]


class DailyUpdate:
    """One day's update. ``service`` is a ``DataCenterService``; ``heartbeat`` is called often
    (the job kills and resumes the run when it stops being called); ``progress(stage, done, total)``."""

    def __init__(
        self,
        service: Any,
        state_path: Path,
        *,
        heartbeat: Callable[[], None] = lambda: None,
        progress: Callable[[str, int, int], None] | None = None,
        lock: Callable[[], Any] | None = None,
    ) -> None:
        self.service = service
        self.state_path = Path(state_path)
        self.heartbeat = heartbeat
        self._progress = progress
        # 下载日线时持有的锁：和手动更新互斥（不传就不加锁，测试用）。
        self.lock = lock

    def progress(self, stage: str, done: int, total: int) -> None:
        self.heartbeat()
        if self._progress is not None:
            self._progress(stage, done, total)

    def run(self, today: date) -> dict[str, Any]:
        """``{trade_date, market, steps, errors}``; ``market`` is ``closed``, ``not_ready`` or ``updated``.

        When today's bars are not out (or today is closed) but the local data is behind the last
        published trading day, ``caught_up`` names that day and the steps run for it; ``trade_date``
        is then that day."""

        result: dict[str, Any] = {"trade_date": today.isoformat(), "steps": {}, "errors": {}}
        self.progress("market_open", 0, 1)
        result["market"] = self._market(today)
        day = today
        if result["market"] != "updated":
            previous = self._previous_trading_day(today)
            if previous is None or not self._behind(previous):
                result["up_to_date"] = previous is not None   # 本地已经有最近一个交易日的行情
                return result
            day = previous
            result["caught_up"] = previous.isoformat()
            result["trade_date"] = previous.isoformat()
        state = _read(self.state_path)
        if state.get("date") != day.isoformat():
            state = {"date": day.isoformat(), "done": [], "results": {}, "symbols_done": []}
        for name in STEPS:
            if name in state["done"]:
                result["steps"][name] = state["results"].get(name)
                continue
            self.progress(name, 0, 1)
            try:
                outcome = getattr(self, f"_{name}")(day, state)
            except DataSourceBlocked as exc:
                # 数据源拒绝了这台服务器：后面的步骤也都要用它，全部停下，等解除后再运行。
                result["errors"][name] = _error(exc)
                result["blocked"] = True
                break
            except Exception as exc:  # noqa: BLE001 - 一步失败不影响后面的步骤
                result["errors"][name] = _error(exc)
                continue
            result["steps"][name] = outcome
            if isinstance(outcome, dict) and outcome.get("errors"):
                messages = outcome["errors"]
                shown = messages if len(messages) <= 3 else [*messages[:2], f"……共 {len(messages)} 条", messages[-1]]
                result["errors"][name] = "；".join(shown)
                continue
            state["done"].append(name)
            state["results"][name] = outcome
            _write(self.state_path, state)
        return result

    # ----------------------------------------------------------------------- #

    def _market(self, today: date) -> str:
        provider = self.service.sources.baostock_provider()
        try:
            calendar = provider.get_trade_calendar(today, today)
            self.heartbeat()
            open_ = not calendar.empty and calendar.get("is_trading_day", pd.Series(dtype=str)).astype(str).eq("1").any()
            if not open_:
                return "closed"
            for symbol in READY_PROBES:
                bars = provider.get_history_range(symbol, today, today, adjustflag="3")
                self.heartbeat()
                if not bars.empty:
                    return "updated"
            return "not_ready"
        finally:
            provider.close()

    def _previous_trading_day(self, today: date) -> date | None:
        """The last trading day before ``today`` (its bars are out by now)."""

        provider = self.service.sources.baostock_provider()
        try:
            calendar = provider.get_trade_calendar(today - timedelta(days=CALENDAR_LOOKBACK_DAYS), today - timedelta(days=1))
            self.heartbeat()
        finally:
            provider.close()
        if calendar.empty or "calendar_date" not in calendar.columns:
            return None
        open_days = calendar[calendar.get("is_trading_day", pd.Series(dtype=str)).astype(str).eq("1")]
        if open_days.empty:
            return None
        return pd.Timestamp(open_days["calendar_date"].max()).date()

    def _behind(self, day: date) -> bool:
        """Whether fewer than ``CAUGHT_UP_SHARE`` of the listed stocks have bars on ``day``."""

        listed = set(self._listed(day))
        summary = self.service.repository.daily_bar_summary()
        if not listed or summary.empty:
            return True
        ends = summary.loc[summary.index.astype(str).isin(listed), "end"]
        if ends.empty:
            return True
        return float((pd.to_datetime(ends) >= pd.Timestamp(day)).mean()) < CAUGHT_UP_SHARE

    def _security_master(self, today: date, state: dict[str, Any]) -> dict[str, Any]:
        master = self.service.full_market_backfill().refresh_security_master()
        return {"rows": int(len(master))}

    def _listed(self, today: date) -> list[str]:
        master = self.service.repository.read_table("security_master")
        if master.empty:
            return []
        listed = pd.to_datetime(master["list_date"], errors="coerce")
        delisted = pd.to_datetime(master["delist_date"], errors="coerce")
        trading = (listed.isna() | (listed <= pd.Timestamp(today))) & (delisted.isna() | (delisted >= pd.Timestamp(today)))
        symbols = master.loc[trading, "symbol"].astype(str)
        return sorted(symbols[symbols.str.endswith(MARKETS)].unique())

    def _daily_bars(self, today: date, state: dict[str, Any]) -> dict[str, Any]:
        symbols = self._listed(today)
        summary = self.service.repository.daily_bar_summary()
        stored = set(summary.index.astype(str)) if not summary.empty else set()
        new = [symbol for symbol in symbols if symbol not in stored]
        # 断点记的是已经更新的股票（不是第几批）：同一天股票列表变了也不会漏掉或重复。
        finished = set(state.get("symbols_done", []))
        pending_new = [symbol for symbol in new if symbol not in finished]
        pending = [symbol for symbol in symbols if symbol in stored and symbol not in finished]
        # 新股要从上市开始的全部历史；其余股票从各自最后一根已存的 K 线接着下载。
        batches = [(HISTORY_START, pending_new[i:i + BATCH]) for i in range(0, len(pending_new), BATCH)]
        batches += [(today, pending[i:i + BATCH]) for i in range(0, len(pending), BATCH)]
        notes: list[str] = []
        errors: list[str] = []
        failures_in_a_row = 0
        done = len(finished & set(symbols))
        self.progress("daily_bars", done, len(symbols))
        for number, (start, batch) in enumerate(batches, start=1):
            failed: dict[str, str] = {}
            try:
                updates = [self._fetch(start, today, batch)]
            except DataSourceBlocked:
                raise
            except Exception as exc:  # noqa: BLE001 - 一只股票出错不能拖累整批：拆开逐只重试
                updates = []
                for symbol in batch:
                    try:
                        updates.append(self._fetch(start, today, [symbol]))
                    except DataSourceBlocked:
                        raise
                    except Exception as single:  # noqa: BLE001
                        failed[symbol] = _error(single)
                if len(failed) == len(batch):
                    errors.append(f"第 {number} 批：{_error(exc)}")
                    failures_in_a_row += 1
                    if failures_in_a_row >= BATCH_FAILURE_LIMIT:
                        errors.append("连续几批失败，已停下，下次运行时从这里继续")
                        break
                    continue
            failures_in_a_row = 0
            notes += [update.message.split("；", 1)[-1] for update in updates if "未更新" in update.message]
            if failed:
                names = "、".join(list(failed)[:5]) + (" 等" if len(failed) > 5 else "")
                errors.append(f"{len(failed)} 只股票没有更新（{names}）：{next(iter(failed.values()))}")
            state.setdefault("symbols_done", []).extend(symbol for symbol in batch if symbol not in failed)
            _write(self.state_path, state)
            done += len(batch) - len(failed)
            self.progress("daily_bars", done, len(symbols))
        return {"symbols": len(symbols), "new_listings": len(new), "batches": len(batches), "notes": notes[:5], "errors": errors}

    def _fetch(self, start: date, today: date, batch: list[str]) -> Any:
        """Only BaoStock: a stock whose history came from BaoStock is never continued from another source,
        so trying the fallbacks would download a whole batch only to refuse it."""

        def fetch():
            return self.service.update_market_data(start, today, batch, source_order=["baostock"], allow_fallback=False,
                                                   on_symbol=lambda _symbol: self.heartbeat())

        if self.lock is None:
            return fetch()
        with self.lock():
            return fetch()

    def _corporate_actions(self, today: date, state: dict[str, Any]) -> dict[str, Any]:
        outcome = self.service.backfill_corporate_action_gaps(progress=self.progress)
        return {key: value for key, value in outcome.items() if isinstance(value, (int, float, str))}

    def _benchmarks(self, today: date, state: dict[str, Any]) -> dict[str, Any]:
        # 先查一遍已存的指数行情：不可能的点位（例如下载时把同代码的股票当成了指数）删掉重新下载。
        repaired = self.service.repair_benchmarks()
        self.heartbeat()
        stored = self.service.repository.read_table("benchmark_bars")
        symbols = sorted(stored["symbol"].astype(str).unique()) if not stored.empty else ["000300.SH"]
        errors: list[str] = list(repaired["errors"])
        for symbol in symbols:
            self.heartbeat()
            try:
                self.service.update_benchmark(today - timedelta(days=30), today, symbol)
            except Exception as exc:  # noqa: BLE001 - 一个指数失败不影响别的指数
                errors.append(f"{symbol}：{_error(exc)}")
        return {"symbols": len(symbols), "errors": errors, "repaired": repaired["detail"]}

    def _index_constituents(self, today: date, state: dict[str, Any]) -> dict[str, Any]:
        outcome = self.service.backfill_index_constituents(HISTORY_START, today, progress=self.progress)
        return {key: value for key, value in outcome.items() if isinstance(value, (int, float, str))}

    def _industry(self, today: date, state: dict[str, Any]) -> dict[str, Any]:
        outcome = self.service.backfill_industry(HISTORY_START, today, progress=self.progress)
        return {key: value for key, value in outcome.items() if isinstance(value, (int, float, str))}

    def _derived(self, today: date, state: dict[str, Any]) -> dict[str, Any]:
        backfill = self.service.full_market_backfill()
        membership = backfill.build_universe_membership()
        self.heartbeat()
        settlements = backfill.build_delisting_settlements()
        return {"universe_rows": int(len(membership)), "settlement_rows": int(len(settlements))}
