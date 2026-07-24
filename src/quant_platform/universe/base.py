"""Universe interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

import pandas as pd


class Universe(ABC):
    """Select securities eligible at a point in time."""

    @abstractmethod
    def select(self, trade_date: date, history: pd.DataFrame) -> list[str]:
        """Return eligible symbols using only data available by ``trade_date``."""
