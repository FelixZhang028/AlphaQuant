"""策略验伪（建设中）：用本地 PIT 数据对账外部回测主张。"""

from __future__ import annotations

import streamlit as st

from quant_platform.web.theme import inject_global_css

inject_global_css()

st.title("策略验伪")
st.caption("粘贴外部策略的成交记录或业绩主张，用本地数据对账核查——建设中，即将上线。")

st.info(
    "本页面将提供取证核查，每一条结论都附数据证据：\n\n"
    "1. **成交可行性**——声称某日买入的股票是否涨停/停牌；\n"
    "2. **时间线核查**——持仓中是否出现回测期后才上市的股票；\n"
    "3. **换手率矛盾**——声称低换手但成交记录算出的实际换手；\n"
    "4. **净值自洽性**——净值曲线与持仓、成本在数学上是否对得上。\n\n"
    "我们不运行你的代码，只重述你的逻辑并用严格引擎重跑——"
    "测量，而非意见。",
    icon=":material/construction:",
)
