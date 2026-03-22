"""
Security tests for origin-based access control logic.
"""
from urllib.parse import urlparse
import pytest


def _is_origin_allowed(origin: str, allowed_origins: set[str]) -> bool:
    """Mirror the matching logic from routes.py:verify_api_key."""
    origin_normalized = origin.rstrip("/").split("?")[0]
    if not origin_normalized:
        return False
    for allowed in allowed_origins:
        allowed_normalized = allowed.rstrip("/")
        if origin_normalized == allowed_normalized or origin_normalized.startswith(allowed_normalized + "/"):
            return True
    return False


def _parse_referer_to_origin(referer: str) -> str:
    """Mirror the referer parsing from routes.py."""
    normalized = referer.rstrip("/").split("?")[0]
    parsed = urlparse(normalized)
    return f"{parsed.scheme}://{parsed.netloc}"


# ── Origin matching ────────────────────────────────────────────────────────

@pytest.mark.parametrize("origin,allowed,expected", [
    # Exact match
    ("http://localhost:3000", {"http://localhost:3000"}, True),
    # Trailing slash normalised
    ("http://localhost:3000/", {"http://localhost:3000"}, True),
    # Path under allowed origin
    ("http://localhost:3000/some/path", {"http://localhost:3000"}, True),
    # Different port — must block
    ("http://localhost:3001", {"http://localhost:3000"}, False),
    # Subdomain — must block
    ("https://app.example.com", {"https://example.com"}, False),
    # Prefix attack — must block
    ("http://localhost:3000.evil.com", {"http://localhost:3000"}, False),
    # Suffix attack — must block
    ("http://localhost:3000-evil.com", {"http://localhost:3000"}, False),
    # Protocol mismatch — must block
    ("https://localhost:3000", {"http://localhost:3000"}, False),
    # Empty origin — must block
    ("", {"http://localhost:3000"}, False),
    # Multiple allowed — matches first
    ("http://localhost:3000", {"http://localhost:3000", "https://app.example.com"}, True),
    # Multiple allowed — matches second
    ("https://app.example.com", {"http://localhost:3000", "https://app.example.com"}, True),
    # Multiple allowed — no match
    ("https://evil.com", {"http://localhost:3000", "https://app.example.com"}, False),
])
def test_origin_matching(origin: str, allowed: set[str], expected: bool) -> None:
    assert _is_origin_allowed(origin, allowed) == expected


# ── Referer parsing ────────────────────────────────────────────────────────

@pytest.mark.parametrize("referer,expected_origin", [
    ("http://localhost:3000/some/path", "http://localhost:3000"),
    ("https://example.com/page?query=value", "https://example.com"),
    ("https://app.example.com:8080/dashboard", "https://app.example.com:8080"),
])
def test_referer_parsing(referer: str, expected_origin: str) -> None:
    assert _parse_referer_to_origin(referer) == expected_origin
