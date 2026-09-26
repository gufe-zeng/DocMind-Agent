from app.core.config import Settings


def test_default_app_name() -> None:
    settings = Settings(_env_file=None)
    assert settings.app_name == "DocMind-Agent"
