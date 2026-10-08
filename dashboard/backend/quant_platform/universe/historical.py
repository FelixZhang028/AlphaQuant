"""Dated universe membership; never substitute today's constituents."""

import pandas as pd

from quant_platform.universe.a_share import AShareUniverse, AShareUniverseConfig


class HistoricalUniverse(AShareUniverse):
    def __init__(
        self, config: AShareUniverseConfig, membership: pd.DataFrame, master: pd.DataFrame
    ) -> None:
        super().__init__(config)
        required = {"symbol", "effective_from", "effective_to", "known_at"}
        if not required.issubset(membership.columns) or membership.empty:
            raise ValueError("历史股票池需要 universe_membership：" + ", ".join(sorted(required)))
        self.membership = membership.copy()
        for col in ("effective_from", "effective_to", "known_at"):
            self.membership[col] = pd.to_datetime(self.membership[col])
        if self.membership[["effective_from", "known_at"]].isna().any().any():
            raise ValueError("历史成分生效日期与可知日期不能为空")
        if (self.membership.effective_to < self.membership.effective_from).any():
            raise ValueError("历史成分退出日期早于生效日期")
        if not {"symbol", "list_date", "delist_date"}.issubset(master.columns):
            raise ValueError("历史股票池需要含 list_date/delist_date 的证券主表")
        self.master = master.drop_duplicates("symbol").set_index("symbol")
        if not set(self.symbols).issubset(self.master.index):
            raise ValueError("历史成分缺少证券主表记录（含已退市证券）")
        if self.master.loc[list(self.symbols), "list_date"].isna().any():
            raise ValueError("历史成分上市日期缺失")

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(sorted(self.membership.symbol.unique()))

    def period_symbols(self, start, end):
        frame = self.membership
        frame = frame[
            (frame.effective_from <= pd.Timestamp(end))
            & (frame.known_at <= pd.Timestamp(end))
            & (frame.effective_to.isna() | (frame.effective_to > pd.Timestamp(start)))
        ]
        return tuple(sorted(frame.symbol.unique()))

    def select(self, trade_date, history):
        day = pd.Timestamp(trade_date)
        members = self.membership
        valid = members[
            (members.effective_from <= day)
            & (members.known_at <= day)
            & (members.effective_to.isna() | (members.effective_to > day))
        ]
        eligible = set(super().select(trade_date, history))
        result = []
        for symbol in valid.symbol.unique():
            row = self.master.loc[symbol]
            listed, delisted = pd.Timestamp(row.list_date), pd.Timestamp(row.delist_date)
            if symbol in eligible and listed <= day and (pd.isna(delisted) or day <= delisted):
                result.append(symbol)
        return sorted(result)
