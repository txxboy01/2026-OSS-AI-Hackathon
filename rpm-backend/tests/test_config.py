import pytest
from conftest import FakeExtractor
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app


@pytest.mark.parametrize(
    "fields",
    [
        {"app_env": "production"},
        {"app_env": "development"},
        {"app_env": "test", "max_message_codepoints": 5001},
        {"app_env": "test", "ai_timeout_seconds": 13},
        {"app_env": "test", "ai_timeout_seconds": 5, "analyze_deadline_seconds": 4},
        {"app_env": "test", "cors_allow_origins": ["*"]},
        {"app_env": "test", "cors_allow_origins": ["https://a.invalid/path"]},
        {"app_env": "test", "gemini_model": "../private-model"},
    ],
)
def test_invalid_configuration(fields):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **fields)


def test_production_requires_https_origins_and_rejects_test_injection():
    fields = {
        "_env_file": None,
        "app_env": "production",
        "gemini_api_key": "synthetic-unused-key",
        "gemini_model": "gemini-test",
    }
    with pytest.raises(ValidationError):
        Settings(**fields)
    with pytest.raises(ValidationError):
        Settings(**fields, cors_allow_origins=["http://localhost:3000"])
    settings = Settings(**fields, cors_allow_origins=["https://rpm.example.invalid"])
    assert settings.enable_docs is False
    with pytest.raises(ValueError, match="test environment"):
        create_app(settings, FakeExtractor())
    app = create_app(settings)
    assert app.docs_url is None and app.openapi_url is None


def test_no_implicit_test_stub():
    with pytest.raises(ValueError, match="explicit test extractor"):
        create_app(Settings(_env_file=None, app_env="test"))
