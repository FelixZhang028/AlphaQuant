"""WeKnora API adapter with SSE answer aggregation and source references."""
from __future__ import annotations
import json
from urllib.parse import quote
import requests
from .mock import MOCK_KNOWLEDGE_BASES, mock_chat

DEFAULT_TIMEOUT = 60.0

class WeKnoraClient:
    def __init__(self, base_url=None, api_key=None, timeout=DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip("/") if base_url else None
        if self.base_url and not self.base_url.endswith("/api/v1"):
            self.base_url += "/api/v1"
        self.api_key, self.timeout = api_key, timeout

    @property
    def configured(self):
        return bool(self.base_url)

    def _headers(self):
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    @staticmethod
    def _unwrap(data):
        if isinstance(data, dict):
            if data.get("success") is False:
                raise ValueError("WeKnora returned an error")
            return data.get("data", data)
        return data

    def _request(self, method, path, payload=None):
        with requests.request(method, f"{self.base_url}{path}", json=payload,
                              headers=self._headers(), timeout=self.timeout) as resp:
            resp.raise_for_status()
            return self._unwrap(resp.json())

    def list_knowledge_bases(self):
        if not self.configured:
            return [dict(item) for item in MOCK_KNOWLEDGE_BASES]
        data = self._request("GET", "/knowledge-bases")
        if isinstance(data, dict):
            data = data.get("items", [])
        if not isinstance(data, list):
            raise ValueError("Invalid knowledge base list")
        return data  # An empty real library is not a demo library.

    @staticmethod
    def _reference(item):
        return {**item, "title": item.get("knowledge_title") or item.get("title") or item.get("file_name") or "文档片段",
                "snippet": item.get("content") or item.get("snippet") or "",
                "page": item.get("page") or item.get("page_number")}

    def query(self, query, knowledge_base_id=None, top_k=5):
        if not self.configured:
            return mock_chat(query).get("references", [])[:top_k]
        if not knowledge_base_id:
            raise ValueError("请选择知识库")
        data = self._request("POST", "/knowledge-search", {"query": query, "knowledge_base_id": knowledge_base_id})
        if isinstance(data, dict):
            data = data.get("results", data.get("items", []))
        if not isinstance(data, list):
            raise ValueError("Invalid search response")
        return [self._reference(item) for item in data[:top_k]]

    @staticmethod
    def _events(lines):
        parts = []
        for line in lines:
            if not line:
                if parts:
                    yield json.loads("\n".join(parts)); parts = []
            elif line.startswith("data:"):
                parts.append(line[5:].lstrip())
        if parts:
            yield json.loads("\n".join(parts))

    def chat(self, question, knowledge_base_id=None):
        if not self.configured:
            return mock_chat(question)
        if not knowledge_base_id:
            raise ValueError("请选择知识库")
        session = self._request("POST", "/sessions", {"title": question[:80]})
        session_id = session["id"]
        payload = {"query": question, "knowledge_base_ids": [knowledge_base_id]}
        answer, refs, complete = [], [], False
        with requests.post(f"{self.base_url}/knowledge-chat/{quote(str(session_id), safe='')}",
                           json=payload, headers=self._headers(), timeout=self.timeout, stream=True) as resp:
            resp.raise_for_status()
            resp.encoding = "utf-8"
            for event in self._events(resp.iter_lines(decode_unicode=True)):
                kind = event.get("response_type")
                if kind == "error":
                    raise ValueError("WeKnora answer failed")
                if kind == "answer":
                    answer.append(event.get("content") or "")
                elif kind == "references":
                    refs.extend(event.get("knowledge_references") or [])
                elif kind == "complete":
                    complete = True
                    break
        if not complete:
            raise ValueError("WeKnora answer stream interrupted")
        return {"answer": "".join(answer), "references": [self._reference(item) for item in refs],
                "mock": False, "session_id": session_id}
