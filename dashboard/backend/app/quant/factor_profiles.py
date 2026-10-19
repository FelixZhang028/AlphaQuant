"""每天预先算好全市场的因子值，AI 研究员的因子画像打开就有。

内置因子对全市场算一遍要半分钟左右，同一天对所有股票、所有用户都一样，所以：
- 算好的结果存在 ``data/runtime/factor_profiles``，重启后不用重算；
- 后台每 10 分钟检查一次本地最新的交易日，还没算过就算一遍（每日更新完成后很快就会算好）；
- 分析更早的日期时，在后台现算，算好后再打开那次分析就能看到；
- ``FELLOWQUANT_FACTOR_PROFILE=off`` 关闭预先计算（分析时仍会在后台现算）。
"""

from __future__ import annotations

import logging
import os
import threading

from quant_platform.ai_research import report

from .runtime import RUNTIME_ROOT, market_repository

logger = logging.getLogger("uvicorn.error")
CHECK_SECONDS = 600
STORE = RUNTIME_ROOT / "factor_profiles"

report.configure(STORE)


def enabled() -> bool:
    return os.getenv("FELLOWQUANT_FACTOR_PROFILE", "on").strip().lower() not in ("0", "off", "false", "no")


class FactorProfileWarmer:
    """Daemon thread: keeps the newest trading day's factor values computed."""

    def __init__(self) -> None:
        self._stop = threading.Event()

    def tick(self) -> bool:
        if not enabled():
            return False
        repository = market_repository()
        bounds = repository.daily_bar_bounds()
        if bounds is None:
            return False
        newest = bounds[1]
        import pandas as pd

        if report.known_cross_section(repository, pd.Timestamp(newest), exact=True) is not None:
            return False
        logger.info("预先计算 %s 的全市场因子值", newest)
        return report.ensure_cross_section(repository, pd.Timestamp(newest), background=False, exact=True) is not None

    def _loop(self) -> None:
        while not self._stop.wait(CHECK_SECONDS):
            try:
                self.tick()
            except Exception:  # noqa: BLE001 - 检查失败不能让线程退出
                logger.exception("预先计算因子值失败")

    def start(self) -> None:
        threading.Thread(target=self._loop, name="factor-profile-warmer", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
