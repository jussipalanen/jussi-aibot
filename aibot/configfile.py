"""
YAML config loading with `${VAR}` and `${VAR:-default}` environment substitution.
"""
import os
import re
from pathlib import Path
from typing import Any

import yaml

# Innermost-first match, so nested defaults like ${A:-${B:-c}} resolve correctly.
_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^${}]*))?\}")


def substitute_env(value: str) -> str:
    """Replace `${VAR}` and `${VAR:-default}` references with environment values."""
    def replace(match: re.Match) -> str:
        current = os.getenv(match.group(1), "").strip()
        return current or (match.group(2) or "")

    previous = None
    while previous != value:
        previous = value
        value = _ENV_PATTERN.sub(replace, value)
    return value


def substitute_tree(data: Any) -> Any:
    """Apply environment substitution to every string in a parsed YAML tree."""
    if isinstance(data, str):
        return substitute_env(data)
    if isinstance(data, list):
        return [substitute_tree(item) for item in data]
    if isinstance(data, dict):
        return {key: substitute_tree(value) for key, value in data.items()}
    return data


def load_yaml(path: Path) -> Any:
    """Load a YAML file and substitute environment references in its values."""
    with path.open(encoding="utf-8") as handle:
        return substitute_tree(yaml.safe_load(handle) or {})


def load_yaml_dir(directory: Path) -> list[tuple[Path, Any]]:
    """Load every `*.yaml` / `*.yml` file in a directory, sorted by name."""
    if not directory.is_dir():
        return []
    files = sorted([*directory.glob("*.yaml"), *directory.glob("*.yml")])
    return [(path, load_yaml(path)) for path in files]
