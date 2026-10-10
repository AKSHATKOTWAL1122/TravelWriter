import os

from storymaker.config import Settings, get_settings


def test_defaults_when_nothing_is_set():
    settings = get_settings()

    assert settings.model == "gemini-2.5-flash"
    assert settings.gemini_api_key == ""


def test_environment_variable_changes_a_setting(monkeypatch):
    monkeypatch.setenv("STORYMAKER_MODEL", "from-env")

    assert Settings().model == "from-env"


def test_gemini_key_uses_its_standard_name(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")

    assert Settings().gemini_api_key == "fake-key-for-test"


def test_dotenv_file_is_used_when_no_variable_is_set(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("STORYMAKER_MODEL=from-file\n")

    assert Settings(_env_file=env_file).model == "from-file"


def test_environment_variable_wins_over_dotenv_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("STORYMAKER_MODEL=from-file\n")
    monkeypatch.setenv("STORYMAKER_MODEL", "from-env")

    assert Settings(_env_file=env_file).model == "from-env"


def test_tests_never_see_the_real_gemini_key():
    assert "GEMINI_API_KEY" not in os.environ
    assert get_settings().gemini_api_key == ""
