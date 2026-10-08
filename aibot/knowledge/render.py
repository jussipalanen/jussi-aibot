"""
Turn JSON data into compact plain text a model can read.
"""
import re
from typing import Any


def _label(key: str) -> str:
    """`work_experiences` -> `Work experiences`, `pricePerMonth` -> `Price per month`."""
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", key).replace("_", " ").replace("-", " ").split()
    text = " ".join(words).lower()
    return text[:1].upper() + text[1:]


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def render_data(
    data: Any,
    *,
    fields: list[str] | None = None,
    exclude: list[str] | None = None,
    max_text_length: int = 0,
) -> str:
    """Render dicts and lists as indented `Label: value` lines.

    `fields` keeps only those top-level keys (in that order), `exclude` drops keys
    at any depth, and `max_text_length` shortens long strings (0 = no limit).
    """
    excluded = set(exclude or [])
    lines: list[str] = []

    def text(value: Any) -> str:
        result = _scalar(value)
        if max_text_length and len(result) > max_text_length:
            return result[:max_text_length].rstrip() + "…"
        return result

    def walk(value: Any, indent: int, keys: list[str] | None = None) -> None:
        pad = "  " * indent
        if isinstance(value, dict):
            for key in keys or list(value):
                if key in excluded or key not in value or _is_empty(value[key]):
                    continue
                item = value[key]
                if isinstance(item, dict):
                    lines.append(f"{pad}{_label(key)}:")
                    walk(item, indent + 1)
                elif isinstance(item, list) and all(not isinstance(v, (dict, list)) for v in item):
                    lines.append(f"{pad}{_label(key)}: {', '.join(text(v) for v in item if not _is_empty(v))}")
                elif isinstance(item, list):
                    lines.append(f"{pad}{_label(key)}:")
                    walk(item, indent + 1)
                else:
                    lines.append(f"{pad}{_label(key)}: {text(item)}")
        elif isinstance(value, list):
            for item in value:
                if _is_empty(item):
                    continue
                if isinstance(item, (dict, list)):
                    start = len(lines)
                    walk(item, indent + 1)
                    if len(lines) > start:
                        lines[start] = f"{pad}- {lines[start].lstrip()}"
                else:
                    lines.append(f"{pad}- {text(item)}")
        elif not _is_empty(value):
            lines.append(f"{pad}{text(value)}")

    walk(data, 0, fields if isinstance(data, dict) else None)
    return "\n".join(lines)


def resolve_asset_urls(data: Any, fields: list[str], base_url: str) -> Any:
    """Turn relative paths in the given fields (at any depth) into absolute URLs."""
    base = base_url.rstrip("/")
    targets = set(fields)
    if not base or not targets:
        return data

    def absolute(value: Any) -> Any:
        if isinstance(value, str) and value and not value.startswith(("http://", "https://")):
            return f"{base}/{value.lstrip('/')}"
        if isinstance(value, dict):
            return {k: absolute(v) for k, v in value.items()}
        if isinstance(value, list):
            return [absolute(v) for v in value]
        return value

    def walk(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: absolute(v) if k in targets else walk(v) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v) for v in value]
        return value

    return walk(data)
