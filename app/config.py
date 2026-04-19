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

    # Chunking (파싱 청크 크기 규칙)
    chunk_min_size: int = 100
    chunk_max_size: int = 5000
    chunk_overlap_size: int = 200

    # PDF 내부 이미지 OCR (텍스트 기반 PDF 에 포함된 다이어그램/그래프 인식)
    # 초기 배포에서는 OFF. 이북 먼저 투입 후 필요 판단되면 활성화.
    pdf_embedded_image_ocr_enabled: bool = False
    pdf_embedded_image_min_width_px: int = 300   # 이 크기 미만은 로고/장식으로 간주하고 건너뜀
    pdf_embedded_image_min_height_px: int = 300


settings = Settings()
