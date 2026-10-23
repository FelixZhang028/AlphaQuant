"""测一台机器连 BaoStock 顺不顺：连接延迟、登录、下载，并估算全市场每日更新要多久。

只依赖 baostock（pip install baostock），不需要项目的其他代码，可以直接在新服务器上运行：
    python scripts/check_baostock.py
    python scripts/check_baostock.py --json 结果.json     # 另外保存结果，方便和别的机器比较

只下载 20 只股票，每两次请求之间隔 0.5 秒（和大批量下载时的建议一样），不会被 BaoStock 列入黑名单。
不要在这台机器正在下载数据（数据更新页有任务在运行）时测：两边一起请求，结果不准，还可能被拒绝。
晚上 18:30 以后是每日更新的时间，也是网络高峰，最好在这个时间段再测一次。
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import json
import socket
import statistics
import time

import baostock as bs

HOST = "public-api.baostock.com"
PORT = 10030
INTERVAL = 0.5
# 沪深主板、创业板、科创板各取几只，覆盖不同交易所。
SYMBOLS = [
    "sh.600000", "sh.600036", "sh.600519", "sh.601318", "sh.601398", "sh.600276", "sh.601888",
    "sh.603288", "sh.688981", "sh.688111", "sz.000001", "sz.000002", "sz.000333", "sz.000651",
    "sz.000858", "sz.002415", "sz.002475", "sz.002594", "sz.300059", "sz.300750",
]
FIELDS = "date,code,open,high,low,close,volume,amount"
MARKET_SIZE = 5300          # 沪深在市股票大约这么多只
REQUESTS_PER_STOCK = 2      # 每日更新：不复权一次、前复权一次


def tcp_latency(address: str, attempts: int = 5) -> list[float]:
    times = []
    for _ in range(attempts):
        start = time.perf_counter()
        try:
            with socket.create_connection((address, PORT), timeout=10):
                times.append(time.perf_counter() - start)
        except OSError:
            pass
        time.sleep(0.2)
    return times


def ms(seconds: float) -> str:
    return f"{seconds * 1000:.0f} 毫秒"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", help="把结果另外保存成 JSON 文件")
    args = parser.parse_args()
    result: dict = {"time": datetime.now().astimezone().isoformat(timespec="seconds"), "host": socket.gethostname()}

    print(f"[1/4] 解析 {HOST} …")
    try:
        address = socket.gethostbyname(HOST)
    except OSError as error:
        print(f"  解析失败：{error}")
        return
    result["address"] = address
    print(f"  地址 {address}（198.18.x.x 是代理软件的假地址，说明流量经过了代理）")

    print(f"[2/4] 测 TCP 连接 {PORT} 端口（5 次）…")
    latency = tcp_latency(address)
    result["tcp_ms"] = [round(t * 1000) for t in latency]
    if not latency:
        print("  连不上，这台机器到 BaoStock 不通。")
        _save(args.json, result)
        return
    print(f"  成功 {len(latency)}/5 次，最快 {ms(min(latency))}，平均 {ms(statistics.mean(latency))}")
    if address.startswith("198.18."):
        print("  （经过代理时，这只是连到本机代理软件的时间，不代表到 BaoStock 的延迟；看后面的下载时间。）")

    print("[3/4] 登录 …")
    # 偶尔一次连接被断开不说明线路不通：最多试 3 次，每次隔 5 秒。
    for attempt in range(3):
        if attempt:
            time.sleep(5)
        start = time.perf_counter()
        login = bs.login()
        result["login_ms"] = round((time.perf_counter() - start) * 1000)
        result["login_attempts"] = attempt + 1
        if login.error_code == "0":
            break
    if login.error_code != "0":
        print(f"  登录失败：{login.error_code} {login.error_msg}")
        result["login_error"] = f"{login.error_code} {login.error_msg}"
        _save(args.json, result)
        return
    print(f"  成功（第 {result['login_attempts']} 次），用时 {ms(result['login_ms'] / 1000)}")

    print(f"[4/4] 下载 {len(SYMBOLS)} 只股票：一年不复权日线 + 最近 5 天前复权（每次间隔 {INTERVAL} 秒）…")
    today = date.today()
    ranges = [((today - timedelta(days=365)).isoformat(), "3"), ((today - timedelta(days=7)).isoformat(), "2")]
    times, rows, failures = [], 0, []
    try:
        for symbol in SYMBOLS:
            for start_date, adjust in ranges:
                time.sleep(INTERVAL)
                start = time.perf_counter()
                try:
                    reply = bs.query_history_k_data_plus(symbol, FIELDS, start_date=start_date,
                                                         end_date=today.isoformat(), frequency="d", adjustflag=adjust)
                    data = reply.get_data() if reply.error_code == "0" else None
                except Exception as error:  # 网络中断时 baostock 会直接抛错
                    reply, data = None, None
                    failures.append(f"{symbol} {type(error).__name__}: {error}")
                elapsed = time.perf_counter() - start
                if data is not None:
                    times.append(elapsed)
                    rows += len(data)
                elif reply is not None:
                    failures.append(f"{symbol} {reply.error_code} {reply.error_msg}")
    finally:
        bs.logout()

    total = len(SYMBOLS) * len(ranges)
    result.update(requests=total, ok=len(times), rows=rows, failures=failures[:10],
                  request_ms=[round(t * 1000) for t in times])
    if not times:
        print("  全部失败：", "；".join(failures[:3]))
        _save(args.json, result)
        return
    times.sort()
    p90 = times[int(len(times) * 0.9) - 1]
    print(f"  成功 {len(times)}/{total} 次，共 {rows} 行；每次请求：中位数 {ms(statistics.median(times))}，"
          f"90% 在 {ms(p90)} 以内，最慢 {ms(times[-1])}")
    for line in failures[:3]:
        print(f"  失败：{line}")

    per_request = statistics.mean(times)
    estimate = {}
    print(f"\n估算：全市场约 {MARKET_SIZE} 只股票，每只 {REQUESTS_PER_STOCK} 次请求的每日更新")
    for interval in (0.1, 0.5):
        minutes = MARKET_SIZE * REQUESTS_PER_STOCK * (per_request + interval) / 60
        estimate[str(interval)] = round(minutes)
        print(f"  请求间隔 {interval} 秒：大约 {minutes:.0f} 分钟")
    result.update(request_mean_ms=round(per_request * 1000), request_median_ms=round(statistics.median(times) * 1000),
                  estimate_minutes=estimate)
    print("  （只算网络时间，不含写文件和计算；失败重试会更久。和另一台机器的结果对比着看。）")
    _save(args.json, result)


def _save(path: str | None, result: dict) -> None:
    if path:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
        print(f"\n结果已保存到 {path}")


if __name__ == "__main__":
    main()
