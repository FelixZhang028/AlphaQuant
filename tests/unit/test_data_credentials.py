"""Tests for locally stored market-data credentials."""

from __future__ import annotations

import os
from pathlib import Path

from quant_platform.agents_bridge.data_credentials import DataCredentialStore


def test_local_credentials_take_priority(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XTICK_TOKEN", "environment-token")
    store = DataCredentialStore(tmp_path / "data_credentials.json")
    store.save("xtick", token="local-token", base_url="http://example.test")

    assert store.resolve("xtick", "token", "XTICK_TOKEN") == "local-token"
    assert store.get("xtick")["base_url"] == "http://example.test"


def test_saved_credentials_can_feed_existing_providers(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("IFIND_USERNAME", "old-user")
    monkeypatch.delenv("IFIND_PASSWORD", raising=False)
    store = DataCredentialStore(tmp_path / "data_credentials.json")
    store.save("ifind", username="researcher", password="secret")

    store.load_into_environment()

    assert os.environ["IFIND_USERNAME"] == "researcher"
    assert os.environ["IFIND_PASSWORD"] == "secret"
    assert store.resolve("ifind", "username", "IFIND_USERNAME") == "researcher"
    assert store.resolve("ifind", "password", "IFIND_PASSWORD") == "secret"
