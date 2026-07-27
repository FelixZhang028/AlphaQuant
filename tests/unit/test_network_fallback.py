import os

from quant_platform.data.network import ProxyResilientAkShareClient


class ProxyError(Exception):
    pass


class ProxySensitiveClient:
    def __init__(self) -> None:
        self.calls = 0

    def fetch(self) -> str:
        self.calls += 1
        if os.environ.get("HTTPS_PROXY"):
            raise ProxyError("Unable to connect to proxy")
        return "direct result"


def test_proxy_failure_retries_directly_and_restores_environment(
    monkeypatch: object,
) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:19828")  # type: ignore[attr-defined]
    source = ProxySensitiveClient()
    client = ProxyResilientAkShareClient(source)

    assert client.fetch() == "direct result"
    assert client.direct_fallback_active is True
    assert os.environ["HTTPS_PROXY"] == "http://127.0.0.1:19828"
    assert source.calls == 2

    assert client.fetch() == "direct result"
    assert source.calls == 3
