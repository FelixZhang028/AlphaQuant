from __future__ import annotations

import pandas as pd

from quant_platform.web.exports import dataframe_to_csv_bytes


def test_dataframe_to_csv_bytes_uses_bom_and_excludes_index() -> None:
    frame = pd.DataFrame({"股票代码": ["000001.SZ"], "股票名称": ["平安银行"]})

    content = dataframe_to_csv_bytes(frame)

    assert content.startswith(b"\xef\xbb\xbf")
    assert content.decode("utf-8-sig").splitlines() == [
        "股票代码,股票名称",
        "000001.SZ,平安银行",
    ]
