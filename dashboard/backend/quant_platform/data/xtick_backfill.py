"""XTick historical daily-bar downloader and local publisher."""
from datetime import date
import os
import pandas as pd
from quant_platform.core.exceptions import DataUnavailableError
from quant_platform.data.normalizers import canonical_symbol
from quant_platform.data.quality import inspect_daily_bars

class XTickRangeBackfill:
    def __init__(self, raw_repository, market_repository, base_url="http://api.xtick.top", token=None, requester=None):
        self.raw_repository, self.market_repository = raw_repository, market_repository
        self.base_url, self.token = base_url, token or os.getenv("XTICK_TOKEN")
        self.requester = requester
    def backfill(self, symbols, start_date: date, end_date: date):
        if not self.token: raise DataUnavailableError("XTICK_TOKEN 未配置")
        import requests, zipfile, io, json
        rows=[]
        for symbol in symbols:
            p={"type":"1","code":symbol.split(".")[0],"fq":"1","period":"1d","startDate":start_date.isoformat(),"endDate":end_date.isoformat()}
            r=(self.requester or requests.get)(f"{self.base_url.rstrip('/')}/kline/market", params={"token":self.token, **p}, timeout=30)
            r.raise_for_status(); content=r.content
            data=json.loads(zipfile.ZipFile(io.BytesIO(content)).read("data.json")) if content[:2]==b"PK" else r.json()
            if isinstance(data, dict): data=data.get("data", data)
            for x in data if isinstance(data,list) else []:
                rows.append({"symbol":canonical_symbol(str(x.get("code",symbol))),"trade_date":x.get("date",x.get("tradeDate")),"open":x.get("open"),"high":x.get("high"),"low":x.get("low"),"close":x.get("close"),"volume":x.get("volume",x.get("vol")),"amount":x.get("amount",x.get("money")),"source":"xtick"})
        frame=pd.DataFrame(rows)
        if frame.empty: raise DataUnavailableError("XTick returned no daily bars")
        frame["trade_date"]=pd.to_datetime(frame["trade_date"]); frame=frame.sort_values(["trade_date","symbol"])
        self.market_repository.save_table("daily_bars", frame)
        self.market_repository.save_table("trade_calendar", pd.DataFrame({"cal_date":frame.trade_date.dt.date.unique(),"is_open":1,"exchange":"CN","source":"xtick"}))
        return inspect_daily_bars(frame)

    def benchmark(self, symbol, start_date: date, end_date: date):
        import requests, zipfile, io, json
        if not self.token: raise DataUnavailableError("XTICK_TOKEN 未配置")
        p={"type":"2","code":symbol.split('.')[0],"fq":"1","period":"1d","startDate":start_date.isoformat(),"endDate":end_date.isoformat()}
        r=requests.get(f"{self.base_url.rstrip('/')}/kline/market",params={"token":self.token,**p},timeout=30); r.raise_for_status()
        c=r.content; data=json.loads(zipfile.ZipFile(io.BytesIO(c)).read('data.json')) if c[:2]==b'PK' else r.json(); data=data.get('data',data) if isinstance(data,dict) else data
        rows=[{"symbol":symbol,"trade_date":x.get('date',x.get('tradeDate')),"raw_close":x.get('close'),"close":x.get('close'),"open":x.get('open'),"high":x.get('high'),"low":x.get('low'),"volume":x.get('volume',x.get('vol')),"amount":x.get('amount')} for x in data]
        frame=pd.DataFrame(rows)
        if frame.empty: raise DataUnavailableError(f"XTick returned no benchmark bars: {symbol}")
        frame['trade_date']=pd.to_datetime(frame['trade_date']).dt.normalize(); return frame
