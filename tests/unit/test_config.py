from pathlib import Path

import pytest

from quant_platform.core.config import load_yaml
from quant_platform.core.exceptions import ConfigurationError


def test_load_yaml_expands_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TEST_TOKEN", "secret")
    path = tmp_path / "config.yaml"
    path.write_text("provider:\n  token: ${TEST_TOKEN}\n", encoding="utf-8")

    assert load_yaml(path)["provider"]["token"] == "secret"


def test_load_yaml_rejects_non_mapping(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("- item\n", encoding="utf-8")

    with pytest.raises(ConfigurationError):
        load_yaml(path)
