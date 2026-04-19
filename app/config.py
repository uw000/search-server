from pathlib import Path
from typing import Literal

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
    documents_originals_root: Path = Path("/data/documents/originals")
    preview_cache: Path = Path("/data/preview-cache")

    # Chunking (파싱 청크 크기 규칙)
    chunk_min_size: int = 100
    chunk_max_size: int = 5000
    chunk_overlap_size: int = 200

    # PDF 전처리 (고DPI 스캔본 자동 다운스케일)
    auto_downscale_enabled: bool = True
    max_dpi: int = 300           # 300 DPI 초과 시 다운스케일
    dpi_sample_pages: int = 3    # DPI 감지 시 샘플링할 페이지 수
    downscale_jpeg_quality: int = 85

    # PDF 내부 이미지 OCR (텍스트 기반 PDF 에 포함된 다이어그램/그래프 인식)
    # 초기 배포에서는 OFF. 이북 먼저 투입 후 필요 판단되면 활성화.
    pdf_embedded_image_ocr_enabled: bool = False
    pdf_embedded_image_min_width_px: int = 300   # 이 크기 미만은 로고/장식으로 간주하고 건너뜀
    pdf_embedded_image_min_height_px: int = 300

    # OCR 엔진 선택
    #   auto      — Surya 설치·사용 가능하면 Surya, 아니면 Tesseract
    #   surya     — 강제로 Surya 사용 (설치 안 되어 있으면 런타임 에러)
    #   tesseract — 강제로 Tesseract
    ocr_engine: Literal["auto", "surya", "tesseract"] = "auto"
    # Surya 실행 디바이스 (auto 는 CUDA → MPS → CPU 순으로 탐지)
    surya_device: Literal["auto", "cuda", "mps", "cpu"] = "auto"
    # Surya 언어 hint (Tesseract 의 kor+eng 를 Surya 의 ["ko","en"] 로 매핑)
    surya_langs: list[str] = ["ko", "en"]


settings = Settings()
