"""Convenience wrapper for the data-center update command."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from quant_platform.cli import main  # noqa: E402


def _command_arguments(arguments: list[str]) -> list[str]:
    """Keep the global config option before the injected subcommand."""

    remaining = list(arguments)
    global_arguments: list[str] = []
    if "--config" in remaining:
        index = remaining.index("--config")
        if index + 1 >= len(remaining):
            return ["update", *remaining]
        global_arguments = remaining[index : index + 2]
        del remaining[index : index + 2]
    return [*global_arguments, "update", *remaining]


if __name__ == "__main__":
    main(_command_arguments(sys.argv[1:]))
