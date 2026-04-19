# 개인 문서 검색 서버

400~500권의 ebook과 3GB+ 전자문서를 한 번의 검색으로 모두 검색할 수 있는 개인 문서 검색 서버.

## 기술 스택

- **검색엔진**: OpenSearch 2.x (nori 한국어 형태소 분석 + 사용자 사전 + 동의어)
- **백엔드**: Python 3.12 + FastAPI
- **프론트엔드**: Jinja2 + HTMX + Tailwind CSS
- **DB**: PostgreSQL 16 + SQLAlchemy 2.x
- **작업큐**: Celery + Redis (문서 파싱 / OCR / 인덱싱)
- **OCR**: Surya OCR (GPU 가속) + Tesseract 5.x fallback (한국어 + 영어)
- **컨테이너**: Docker Compose

## 서비스 구성

| 서비스 | 역할 | 포트 |
|---|---|---|
| api | FastAPI 웹 앱 | 8000 |
| worker | Celery worker (파싱 / OCR / 인덱싱) — **GPU 권장** | - |
| file-watcher | documents 볼륨 감시 → 자동 인덱싱 큐잉 | - |
| opensearch | 검색 인덱스 | 9200 |
| opensearch-dashboards | OpenSearch 관리 UI | 5601 |
| postgres | 메타데이터 / 사용자 / 권한 | 5432 |
| redis | Celery 브로커 + 결과 저장소 | 6379 |

## 시스템 요구사항

### GPU 가속 OCR (운영 권장)

- NVIDIA GPU (6GB+ VRAM, 예: RTX 4060)
- NVIDIA Driver 535 이상 (CUDA 12.6 runtime 호환)
- NVIDIA Container Toolkit
- Docker Compose v2

GPU가 없으면 worker가 자동으로 Tesseract 로 fallback 합니다. 한국어 OCR 정확도가 크게 떨어지므로 운영 환경에서는 GPU 환경을 권장.

### 최소 사양 (개발용, Tesseract)
- 8GB RAM, 20GB 디스크

## 빠른 시작

### 1. 환경 변수 설정

```bash
cp .env.example .env
# .env 파일을 편집하여 비밀번호 등을 변경
```

### 2. Docker Compose 실행

**운영 환경:**
```bash
docker compose up -d
```

**개발 환경 (메모리 축소 + 핫 리로드):**
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

### 3. 초기 설정

```bash
# DB 마이그레이션
docker compose exec api alembic upgrade head

# OpenSearch 인덱스 생성
docker compose exec api python -m scripts.init_opensearch

# Admin 계정 생성
docker compose exec api python -m scripts.create_admin
```

### 4. OCR 엔진 확인 (GPU 환경)

```bash
docker compose exec worker python -c "
from app.parsers.ocr_processor import get_ocr_engine, _is_surya_importable
print('surya importable:', _is_surya_importable())
print('engine:', get_ocr_engine().name)
"
```

`engine: surya` 가 정상. `tesseract` 면 GPU 설정 점검 필요.

### 5. 접속

- 웹 앱: http://localhost:8000
- OpenSearch Dashboards: http://localhost:5601

## 운영 작업

### 대량 초기 임포트
```bash
docker compose exec worker python scripts/bulk_import.py <디렉토리_경로>
```

### 인덱스 재구축 (파괴적)
매핑 / 동의어 / 사용자 사전을 변경한 뒤 실행. PostgreSQL 에서 재구축하므로 원본 파일·메타데이터는 안전.

```bash
docker compose restart opensearch    # nori 사전·동의어 파일 재로드
docker compose exec worker python scripts/rebuild_index.py
```

### OCR 벤치마크
`tests/fixtures/ocr_gt/` 에 ground truth 데이터셋 배치 후:
```bash
docker compose exec worker python -m scripts.ocr_benchmark --dataset tests/fixtures/ocr_gt
```

### 검색 품질 리포트
```bash
docker compose exec worker python scripts/quality_report.py
```

## 프로젝트 구조
app/                    FastAPI 메인 앱
├── api/                엔드포인트 라우터
├── models/             SQLAlchemy 모델
├── opensearch/         검색 쿼리 / 매핑
├── parsers/            PDF / EPUB / OCR (surya + tesseract)
├── schemas/            Pydantic 스키마
├── services/           비즈니스 로직
├── static/, templates/ 프론트엔드 자산
workers/                Celery 비동기 작업
├── tasks/              parse / ocr / index 태스크
├── celery_app.py       Celery 설정
└── file_watcher.py     documents 볼륨 감시
migrations/             Alembic DB 마이그레이션
scripts/                유틸리티 (init / rebuild / import / benchmark / quality)
docker/                 Dockerfile.worker / .api / opensearch/
opensearch-config/      nori 사용자 사전, 동의어 파일
requirements/           base / ocr / prod / dev / constraints
tests/                  API / 파서 / 검색 품질 테스트

자세한 설계 문서는 [CLAUDE.md](CLAUDE.md) 참조.
