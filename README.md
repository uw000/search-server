# 개인 문서 검색 서버

400~500권의 ebook과 3GB+ 전자문서를 한 번의 검색으로 모두 검색할 수 있는 개인 문서 검색 서버.

## 기술 스택

- **검색엔진**: OpenSearch 2.x (nori 한국어 형태소 분석)
- **백엔드**: Python 3.12 + FastAPI
- **프론트엔드**: Jinja2 + HTMX + Tailwind CSS
- **DB**: PostgreSQL 16 + SQLAlchemy 2.x
- **작업큐**: Celery + Redis
- **OCR**: Tesseract 5.x (한국어 + 영어)
- **컨테이너**: Docker Compose

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

### 4. 접속

- 웹 앱: http://localhost:8000
- OpenSearch Dashboards: http://localhost:5601

## 프로젝트 구조

```
app/           # FastAPI 메인 앱
workers/       # Celery 비동기 작업
migrations/    # Alembic DB 마이그레이션
scripts/       # 유틸리티 스크립트
tests/         # 테스트
docker/        # Dockerfile 모음
```

자세한 설계 문서는 [CLAUDE.md](CLAUDE.md)를 참조하세요.
