"""
Shared fixtures and environment setup.
Env vars must be set before importing the app since routes.py reads them at module level.
"""
import os
import pytest

# Set safe defaults before any app import
os.environ.setdefault("DEFAULT_PROVIDER", "puter_ai")
os.environ.setdefault("DISABLE_LOCAL_MODEL", "true")

from fastapi.testclient import TestClient
from main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)
