"""Deterministic import of CSV and tab-separated clipboard trade records."""

import csv
import io
import re
from dataclasses import dataclass

import pandas as pd

LABELS = {
    "date": "日期",
    "symbol": "股票代码",
    "side": "买卖方向",
    "quantity": "成交数量",
    "price": "成交价",
}
ALIASES = {
    "date": {"日期", "成交日期", "交易日期", "成交时间", "date", "trade_date", "datetime"},
    "symbol": {"代码", "股票代码", "证券代码", "symbol", "code", "ticker"},
    "side": {"方向", "买卖方向", "买卖标志", "操作", "业务名称", "side", "买卖"},
    "quantity": {
        "数量",
        "成交数量",
        "成交数量股",
        "数量股",
        "成交数量手",
        "数量手",
        "quantity",
        "volume",
        "qty",
    },
    "price": {"价格", "成交价", "成交价格", "成交价未复权", "未复权成交价", "price"},
}


def header(value: str) -> str:
    return re.sub(r"[\s（）()\[\]]", "", str(value)).lower().lstrip("\ufeff")


def read_material(content: bytes | str) -> pd.DataFrame:
    if isinstance(content, bytes):
        if len(content) > 5_000_000:
            raise ValueError("文件超过5 MB，请按日期拆分后检查。")
        for encoding in ("utf-8-sig", "gb18030"):
            try:
                content = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValueError("无法识别编码，请另存为 UTF-8 CSV。")
    if len(content) > 5_000_000:
        raise ValueError("内容过长，请按日期拆分后检查。")
    try:
        delimiter = "\t" if "\t" in content.splitlines()[0] else ","
        rows = list(csv.reader(io.StringIO(content), delimiter=delimiter, strict=True))
    except (csv.Error, IndexError) as exc:
        raise ValueError("请粘贴带表头的成交表格，或上传 CSV。") from exc
    if len(rows) < 2 or len(rows[0]) < 2:
        raise ValueError("未识别到成交表，请包含表头和至少一条记录。")
    columns = [c.strip().lstrip("\ufeff") for c in rows[0]]
    if len(set(map(header, columns))) != len(columns) or any(not c for c in columns):
        raise ValueError("表头有重复或空列名，请修正后导入。")
    records, numbers = [], []
    for number, row in enumerate(rows[1:], 2):
        if not any(c.strip() for c in row):
            continue
        if len(row) != len(columns):
            raise ValueError(f"第{number}条表格记录的列数与表头不一致。")
        records.append(row)
        numbers.append(number)
    if not records or len(records) > 20000:
        raise ValueError("请提供1～20000条成交记录。")
    return pd.DataFrame(records, columns=columns, index=numbers)


def detect_columns(frame: pd.DataFrame) -> dict[str, str]:
    mapping = {}
    for field, aliases in ALIASES.items():
        matches = [c for c in frame if header(c) in aliases]
        if len(matches) == 1:
            mapping[field] = matches[0]
    return mapping


def normalize_symbol(value: str) -> str:
    value = value.strip().upper().replace(" ", "")
    match = re.fullmatch(r"(?:(SH|SZ|BJ)[.:-]?)?(\d{1,6})(?:[.:-]?(SH|SZ|BJ))?", value)
    if not match:
        raise ValueError("代码应为六位数字或带 SH/SZ/BJ 前后缀")
    prefix, code, suffix = match.groups()
    if prefix and suffix and prefix != suffix:
        raise ValueError("交易所前后缀冲突")
    code = code.zfill(6)
    exchange = prefix or suffix
    if not exchange:
        exchange = (
            "SH"
            if code.startswith("6")
            else (
                "SZ"
                if code.startswith(("0", "3"))
                else ("BJ" if code.startswith(("4", "8", "92")) else None)
            )
        )
    if not exchange:
        raise ValueError("无法确定交易所，请补充 SH/SZ/BJ 后缀")
    return f"{code}.{exchange}"


@dataclass
class ParsedTrades:
    trades: pd.DataFrame
    errors: pd.DataFrame


def parse_trades(frame: pd.DataFrame, mapping: dict[str, str], unit: str) -> ParsedTrades:
    if set(mapping) != set(LABELS) or len(set(mapping.values())) != len(LABELS):
        raise ValueError("请为五个字段分别指定不同的列。")
    if unit not in ("股", "手"):
        raise ValueError("请确认数量单位。")
    records, errors = [], []
    for number, row in frame.iterrows():
        record = {"row": number}
        for field, column in mapping.items():
            value = str(row[column]).strip()
            try:
                if field == "symbol":
                    parsed = normalize_symbol(value)
                elif field == "date":
                    if not re.fullmatch(r"\d{8}|\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:[ T].*)?", value):
                        raise ValueError("请使用 YYYY-MM-DD 或 YYYYMMDD 日期")
                    parsed = pd.Timestamp(pd.to_datetime(value)).normalize()
                    if pd.isna(parsed) or parsed.tzinfo is not None:
                        raise ValueError("日期无效或含时区，请转为交易所本地日期")
                elif field == "side":
                    parsed = {
                        "买入": "BUY",
                        "证券买入": "BUY",
                        "买": "BUY",
                        "BUY": "BUY",
                        "卖出": "SELL",
                        "证券卖出": "SELL",
                        "卖": "SELL",
                        "SELL": "SELL",
                    }.get(value.upper())
                    if parsed is None:
                        raise ValueError("仅支持买入/卖出，委托、撤单及其他业务暂不支持")
                else:
                    parsed = float(value.replace(",", ""))
                    if not 0 < parsed < float("inf"):
                        raise ValueError("必须是大于0的有限数值")
                    if field == "quantity":
                        parsed *= 100 if unit == "手" else 1
                        if not parsed.is_integer():
                            raise ValueError("转换后股数必须为整数")
                record[field] = parsed
            except (ValueError, TypeError, OverflowError) as exc:
                errors.append(
                    {"表格行": number, "字段": LABELS[field], "原值": value, "问题": str(exc)}
                )
        records.append(record)
    return ParsedTrades(pd.DataFrame(records), pd.DataFrame(errors))
