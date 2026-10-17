"""WeKnora mock 数据，用于未配置或服务不可达时演示。"""
from __future__ import annotations

MOCK_KNOWLEDGE_BASES = [
    {
        "id": "kb-quant-research",
        "name": "量化策略研究",
        "description": "多因子模型、回测方法论、策略设计模式",
        "document_count": 128,
    },
    {
        "id": "kb-risk-management",
        "name": "风控与仓位管理",
        "description": "风险度量、止损止盈、仓位优化",
        "document_count": 64,
    },
    {
        "id": "kb-data-sources",
        "name": "数据源与数据质量",
        "description": "行情数据、复权处理、数据清洗",
        "document_count": 42,
    },
]

_MOCK_QA = {
    "动量": {
        "answer": "动量策略通过捕捉价格延续趋势获利。常见实现包括横截面动量（相对强弱排序）和时序动量（自身历史收益）。关键参数包括回看周期（通常 3-12 个月）和调仓频率。需注意换手率和交易成本的影响，以及动量崩溃风险。",
        "references": [
            {"title": "动量因子研究综述", "page": 12, "snippet": "横截面动量在 A 股市场存在显著溢价..."},
            {"title": "回测方法论", "page": 45, "snippet": "动量策略的换手率通常在 50%-150% 之间..."},
        ],
    },
    "回撤": {
        "answer": "最大回撤衡量策略从峰值到谷底的最大跌幅，是评估风险的核心指标。控制回撤的方法包括：分散化持仓、动态仓位调整、止损规则、波动率目标等。实践中建议结合最大回撤和回撤持续期综合评估。",
        "references": [
            {"title": "风险度量指南", "page": 8, "snippet": "最大回撤是投资者最关心的下行风险指标..."},
        ],
    },
    "默认": {
        "answer": "这是一个演示回答。配置 WeKnora 服务地址后，将返回真实知识库的检索与问答结果。当前为 mock 模式，可在设置页面配置 WeKnora base_url 后启用真实问答。",
        "references": [
            {"title": "演示文档", "page": 1, "snippet": "这是 mock 模式下的示例引用..."},
        ],
    },
}


def mock_chat(question: str) -> dict:
    """根据问题关键词返回 mock 问答结果。"""
    key = "默认"
    for k in _MOCK_QA:
        if k in question:
            key = k
            break
    result = dict(_MOCK_QA[key])
    result["mock"] = True
    return result
