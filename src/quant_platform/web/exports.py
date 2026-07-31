"""Helpers for exporting data from the web interface."""

from __future__ import annotations

import pandas as pd


def dataframe_to_csv_bytes(frame: pd.DataFrame) -> bytes:
    """Serialize a dataframe as an Excel-friendly UTF-8 CSV file."""

    return frame.to_csv(index=False).encode("utf-8-sig")
