import pandas as pd

from quant_platform.data.price_limits import derive_cn_price_limits


def test_price_limit_rules_cover_main_st_growth_and_beijing_boards() -> None:
    source = pd.DataFrame(
        [
            {
                "symbol": "600519.SH",
                "trade_date": "2024-01-02",
                "pre_close": 10.05,
                "is_st": False,
                "list_date": "2001-08-27",
            },
            {
                "symbol": "600001.SH",
                "trade_date": "2024-01-02",
                "pre_close": 10.05,
                "is_st": True,
                "list_date": "2000-01-01",
            },
            {
                "symbol": "300001.SZ",
                "trade_date": "2024-01-02",
                "pre_close": 10.05,
                "is_st": True,
                "list_date": "2009-10-30",
            },
            {
                "symbol": "830001.BJ",
                "trade_date": "2024-01-02",
                "pre_close": 10.05,
                "is_st": False,
                "list_date": "2014-01-24",
            },
        ]
    )

    result = derive_cn_price_limits(source)

    assert list(result["up_limit"]) == [11.06, 10.55, 12.06, 13.07]
    assert list(result["down_limit"]) == [9.05, 9.55, 8.04, 7.04]
    assert result.iloc[1]["limit_rule_id"].endswith("MAIN_ST_5")
    assert result.iloc[2]["limit_rule_id"].endswith("CHINEXT_20")
    assert result.iloc[3]["limit_rule_id"].endswith("BEIJING_30")


def test_price_limit_rule_refuses_unverified_new_listing_window() -> None:
    source = pd.DataFrame(
        [
            {
                "symbol": "001234.SZ",
                "trade_date": "2024-01-05",
                "pre_close": 10.0,
                "is_st": False,
                "list_date": "2024-01-02",
            }
        ]
    )

    result = derive_cn_price_limits(source)

    assert pd.isna(result.iloc[0]["up_limit"])
    assert result.iloc[0]["limit_rule_id"] == "UNVERIFIED_NEW_LISTING_WINDOW"
    assert result.iloc[0]["price_limit_source"] == "unverified"
