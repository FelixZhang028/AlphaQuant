"""Strategy signal domain models."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime


@dataclass(frozen=True)
class Signal:
    """A scored strategy opinion; it is not an order."""

    strategy_id: str
    trade_date: date
    symbol: str
    signal_type: str
    score: float
    target_direction: str = "LONG"
    target_weight: float | None = None
    model_version: str | None = None
    generated_at: datetime = datetime.min.replace(tzinfo=UTC)

    def to_dict(self) -> dict[str, object]:
        """Convert this immutable signal to a serialization mapping."""

        result = asdict(self)
        if self.generated_at == datetime.min.replace(tzinfo=UTC):
            result["generated_at"] = datetime.now(UTC)
        return result
