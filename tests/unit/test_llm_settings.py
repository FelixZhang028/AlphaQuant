"""Tests for the local LLM settings store and provider catalog."""

from __future__ import annotations

import json
from pathlib import Path

from quant_platform.agents_bridge.llm_settings import (
    PROVIDER_CATALOG,
    LLMSettingsStore,
)


def test_catalog_lists_requested_models() -> None:
    assert "deepseek-v4-pro" in PROVIDER_CATALOG["deepseek"].models
    assert "kimi-k2.6" in PROVIDER_CATALOG["kimi"].models
    assert PROVIDER_CATALOG["deepseek"].default_model == "deepseek-v4-pro"
    assert PROVIDER_CATALOG["kimi"].default_model == "kimi-k2.6"


def test_resolve_returns_provider_defaults(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    store = LLMSettingsStore(tmp_path / "llm_settings.json")

    resolved = store.resolve("deepseek")

    assert resolved["base_url"] == "https://api.deepseek.com/v1"
    assert resolved["model"] == "deepseek-v4-pro"
    assert resolved["api_key"] == ""


def test_store_saves_and_resolves_locally(tmp_path: Path) -> None:
    store = LLMSettingsStore(tmp_path / "llm_settings.json")

    store.save(
        "kimi", base_url="https://api.kimi.com/v1", api_key="sk-test", model="kimi-k2.6"
    )
    resolved = store.resolve("kimi")

    assert resolved["base_url"] == "https://api.kimi.com/v1"
    assert resolved["api_key"] == "sk-test"
    assert resolved["model"] == "kimi-k2.6"
    raw = json.loads((tmp_path / "llm_settings.json").read_text(encoding="utf-8"))
    assert raw["providers"]["kimi"]["api_key"] == "sk-test"


def test_resolve_prefers_local_api_key_over_env(tmp_path: Path, monkeypatch) -> None:
    store = LLMSettingsStore(tmp_path / "llm_settings.json")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")

    store.save("deepseek", base_url="", api_key="local-key", model="deepseek-v4-pro")

    assert store.resolve("deepseek")["api_key"] == "local-key"


def test_env_fallback_when_no_local_key(tmp_path: Path, monkeypatch) -> None:
    store = LLMSettingsStore(tmp_path / "llm_settings.json")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")

    assert store.resolve("deepseek")["api_key"] == "env-key"


def test_corrupt_settings_file_is_tolerated(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    path = tmp_path / "llm_settings.json"
    path.write_text("{not valid json", encoding="utf-8")

    store = LLMSettingsStore(path)

    assert store.resolve("deepseek")["model"] == "deepseek-v4-pro"


def test_default_provider_is_persisted(tmp_path: Path) -> None:
    store = LLMSettingsStore(tmp_path / "llm_settings.json")

    assert store.get_default_provider() == "mock"
    store.save_default_provider("deepseek")

    assert store.get_default_provider() == "deepseek"
