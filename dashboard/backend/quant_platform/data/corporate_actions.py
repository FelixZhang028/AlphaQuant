"""Read explicit, auditable cash and share entitlements from the local repository."""

from datetime import date

import pandas as pd

from quant_platform.accounts.models import CorporateAction


def load_corporate_actions(repository, start: date, end: date, symbols) -> list[CorporateAction]:
    frame = repository.read_table("corporate_actions")
    if frame.empty:
        return []
    required = {"symbol", "ex_date", "cash_per_share", "share_multiplier"}
    if not required.issubset(frame.columns):
        raise ValueError(
            f"corporate_actions missing fields: {sorted(required - set(frame.columns))}"
        )
    frame = frame.copy()
    frame["ex_date"] = pd.to_datetime(frame["ex_date"], errors="raise").dt.date
    if frame["ex_date"].isna().any():
        raise ValueError("corporate_actions contains missing ex_date")
    frame = frame[frame["ex_date"].between(start, end)]
    if symbols:
        frame = frame[frame["symbol"].isin(symbols)]
    if frame.duplicated(["symbol", "ex_date"]).any():
        raise ValueError(
            "Combine cash/share entitlements into one corporate action per symbol/date"
        )
    actions = []
    for row in frame.sort_values(["ex_date", "symbol"]).to_dict("records"):
        dates = {}
        for key in ("pay_date", "share_listing_date"):
            value = row.get(key)
            dates[key] = pd.Timestamp(value).date() if pd.notna(value) else None
        actions.append(
            CorporateAction(
                symbol=str(row["symbol"]),
                ex_date=row["ex_date"],
                cash_per_share=float(row["cash_per_share"]),
                share_multiplier=float(row["share_multiplier"]),
                **dates,
            )
        )
    return actions
