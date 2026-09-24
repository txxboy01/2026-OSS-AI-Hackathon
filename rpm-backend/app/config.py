from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="forbid", hide_input_in_errors=True
    )
    app_env: Literal["development", "test", "production"] = "development"
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = ""
    cors_allow_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    ai_timeout_seconds: float = Field(default=12, gt=0, le=12)
    analyze_deadline_seconds: float = Field(default=15, gt=0, le=15)
    gemini_max_output_tokens: int = Field(default=4096, gt=0, le=16384)
    max_message_codepoints: int = 5000
    max_request_bytes: int = 32768
    max_ai_output_bytes: int = 32768
    max_evidence_items: int = 12
    max_quote_codepoints: int = 500
    max_spans_per_quote: int = 20
    max_concurrent_analyses: int = Field(default=4, ge=1, le=100)
    analyze_per_ip_per_minute: int = Field(default=5, ge=1)
    guidance_per_ip_per_minute: int = Field(default=30, ge=1)
    analyze_global_per_minute: int = Field(default=60, ge=1)
    log_level: Literal["INFO", "WARNING", "ERROR"] = "INFO"
    enable_docs: bool | None = None

    @model_validator(mode="after")
    def valid_settings(self):
        if self.app_env != "test" and (
            not self.gemini_api_key.get_secret_value().strip() or not self.gemini_model.strip()
        ):
            raise ValueError("GEMINI_API_KEY and GEMINI_MODEL are required")
        if self.gemini_model and (
            not self.gemini_model.startswith("gemini-")
            or not all(c.isalnum() or c in ".-_" for c in self.gemini_model)
        ):
            raise ValueError("invalid GEMINI_MODEL identifier")
        fixed = {
            "max_message_codepoints": 5000,
            "max_request_bytes": 32768,
            "max_ai_output_bytes": 32768,
            "max_evidence_items": 12,
            "max_quote_codepoints": 500,
            "max_spans_per_quote": 20,
        }
        if any(getattr(self, k) != v for k, v in fixed.items()):
            raise ValueError("v1 contract limits cannot change without updating the contract")
        if self.ai_timeout_seconds > self.analyze_deadline_seconds:
            raise ValueError("AI timeout must not exceed request deadline")
        if self.app_env == "production" and (
            "cors_allow_origins" not in self.model_fields_set or not self.cors_allow_origins
        ):
            raise ValueError("explicit production CORS_ALLOW_ORIGINS required")
        for origin in self.cors_allow_origins:
            p = urlsplit(origin)
            if (
                not p.hostname
                or p.username
                or p.password
                or p.path
                or p.query
                or p.fragment
                or p.scheme not in {"http", "https"}
            ):
                raise ValueError("invalid CORS origin")
            if self.app_env == "production" and p.scheme != "https":
                raise ValueError("production origins must use HTTPS")
        if self.enable_docs is None:
            self.enable_docs = self.app_env != "production"
        return self
