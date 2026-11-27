from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # project root (where .env lives)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "mandi_user"
    db_password: str = ""
    db_name: str = "mandi_dashboard"
    # Optional full override (used by tests, e.g. sqlite+pysqlite:///:memory:)
    database_url: str | None = None

    mandi_api_url: str = "https://api.dharun.dev/v1/mandi"
    api_timeout_seconds: int = 30
    api_page_limit: int = 100
    # 1 = exactly what your working fatch_mandi_data.py does (one request per commodity).
    # Raise only after confirming the API supports `offset` (see README, Stage 2 notes).
    api_max_pages: int = 1
    api_retries: int = 3

    refresh_interval_hours: int = 3
    target_state: str = "Rajasthan"
    cors_origins: str = "http://localhost:8000"

    # Stage 5 (production)
    app_env: str = "development"          # "production" enables long-lived static caching
    docs_enabled: bool = True             # set DOCS_ENABLED=false to hide /docs and /redoc
    manual_refresh_cooldown_seconds: int = 60  # protects the upstream API from button spam

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        pwd = quote_plus(self.db_password)
        return (
            f"mysql+pymysql://{self.db_user}:{pwd}@{self.db_host}:{self.db_port}"
            f"/{self.db_name}?charset=utf8mb4"
        )

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
