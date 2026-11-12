from pathlib import Path

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WREN_", extra="ignore", hide_input_in_errors=True)

    service_token: SecretStr
    registry_path: Path = Path("models/registry.json")
    plan_timeout_seconds: float = Field(default=15, ge=0.1, le=300)
    startup_timeout_seconds: float = Field(default=60, ge=1, le=300)
    max_concurrent_plans: int = Field(default=3, ge=1, le=32)
    # Bound on waiting for a worker slot before a caller gets 503 (0 disables queueing).
    queue_timeout_seconds: float = Field(default=5, ge=0, le=30)
    max_request_bytes: int = Field(default=65_536, ge=1024, le=1_048_576)
    max_manifest_bytes: int = Field(default=4_194_304, ge=1024, le=16_777_216)
    execution_sources_path: Path | None = None
    execution_timeout_seconds: float = Field(default=15, ge=0.1, le=300)
    max_concurrent_executions: int = Field(default=3, ge=1, le=32)
    execution_max_result_bytes: int = Field(default=4_194_304, ge=4096, le=16_777_216)
    studio_enabled: bool = False
    studio_password: SecretStr | None = None
    studio_data_dir: Path = Path(".state/studio")
    studio_cookie_secure: bool = False
    studio_max_request_bytes: int = Field(default=1_048_576, ge=1024, le=4_194_304)

    @model_validator(mode="after")
    def validate_studio(self):
        if self.studio_enabled:
            password = self.studio_password.get_secret_value() if self.studio_password else ""
            if len(password) < 12 or password == self.service_token.get_secret_value():
                raise ValueError("Studio requires its own password, at least 12 characters")
        return self

    @field_validator("service_token")
    @classmethod
    def require_strong_token(cls, value: SecretStr) -> SecretStr:
        token = value.get_secret_value()
        if len(token) < 32 or token.strip() != token:
            raise ValueError("WREN_SERVICE_TOKEN must contain at least 32 non-padding characters")
        return value
