"""WeKnora REST API 客户端。

支持知识库列表查询、文档检索、问答。无配置或服务不可达时回退到 mock。
"""
from .client import WeKnoraClient

__all__ = ["WeKnoraClient"]
