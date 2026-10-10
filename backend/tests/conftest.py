import os

import pytest
from fastapi.testclient import TestClient

from storymaker.config import Settings, get_settings
from storymaker.main import app


def _settings_env_names() -> set[str]:
    """Environment variable names that Settings reads, so new settings are covered automatically."""
    prefix = Settings.model_config["env_prefix"]
    names = set()
    for field_name, field in Settings.model_fields.items():
        alias = field.validation_alias if isinstance(field.validation_alias, str) else None
        names.add((alias or f"{prefix}{field_name}").upper())
    return names


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    """Keep every test away from the developer's real shell variables and backend/.env."""
    names = _settings_env_names()
    prefix = Settings.model_config["env_prefix"]
    for name in list(os.environ):
        if name.upper() in names or name.upper().startswith(prefix):
            monkeypatch.delenv(name)
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
