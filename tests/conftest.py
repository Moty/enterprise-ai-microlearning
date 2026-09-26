"""Global pytest test configuration and isolation fixtures."""

import os
import pytest
from src.core.config import settings


@pytest.fixture(autouse=True)
def isolate_test_environment(monkeypatch):
    """Ensures tests run in local hermetic mode without external cloud side effects."""
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    monkeypatch.setenv("STORAGE_BACKEND", "local")
