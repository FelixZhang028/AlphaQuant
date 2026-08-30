# XTick API

## 行情数据接口

- 股票列表：按照股票池获取股票代码，包括沪深京A股、港股、沪深指数、ETF、可转债几类数据。
    - API: http://api.xtick.top/doc/stockinfo?symbol=all&token=448f197d69e049b38051edca063f1487
    - 输入参数名：
        - symbol: (String) all-全部股票，sz-深交所股票，sh-上交所股票，bj-北交所股票，hk-港交所股票，index-指数，bond-可转债，cyb-创业板股票，kcb-科创板股票，etf-全部ETF，st-st股票，ts-退市股票
        - token: 账户登录可取得token
    - 返回参数名：
        - type: (int)      标的类别
        - code: (String)   股票代码
- 