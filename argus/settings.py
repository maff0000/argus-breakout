"""Typed settings, read from the environment only (PID 8.2)."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigError(RuntimeError):
    """Raised when required configuration is missing."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    argus_store_dir: Path = Path("store")
    argus_out_dir: Path = Path("out")
    argus_config_dir: Path = Path("config")
    argus_log_level: str = "INFO"
    polygon_api_key: SecretStr | None = None
    fmp_api_key: SecretStr | None = None
    fmp_daily_call_budget: int = 200
    ib_host: str = "127.0.0.1"
    ib_port: int | None = None
    ib_client_id: int = 11
    ib_client_id_write: int = 12
    llm_base_url: str | None = None
    llm_api_key: SecretStr | None = None
    llm_model_brief: str | None = None
    llm_model_review: str | None = None
    llm_model_fast: str | None = None
    llm_model_embed: str | None = None

    def require(self, *names: str) -> None:
        """Raise ConfigError listing every named field that is None/empty."""
        missing = []
        for name in names:
            value = getattr(self, name)
            if isinstance(value, SecretStr):
                value = value.get_secret_value()
            if value is None or value == "":
                missing.append(name)
        if missing:
            raise ConfigError(", ".join(missing))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
