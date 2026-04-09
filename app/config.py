from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # PostgreSQL
    database_url: str = "postgresql+asyncpg://search:password@localhost:5432/searchdb"

    # OpenSearch
    opensearch_url: str = "http://localhost:9200"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_secret_key: str = "change_me_to_random_secret_key"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # Initial Admin
    initial_admin_username: str = "admin"
    initial_admin_password: str = "admin"
    initial_admin_email: str = "admin@localhost"

    # Documents
    document_root: Path = Path("/data/documents")
    preview_cache: Path = Path("/data/preview-cache")


settings = Settings()
