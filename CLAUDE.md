# 개인 문서 검색 서버 — 설계 문서 v1.2

> 이 문서는 프로젝트의 전체 설계를 담고 있습니다.
> Claude Code 사용 시 프로젝트 루트에 `CLAUDE.md`로 배치하여 참조합니다.
> 
> 변경 이력:
> - v1.0 (2026-04-01): 초안 작성
> - v1.1 (2026-04-03): PostgreSQL 전환, 디스크 레이아웃, 보안 설정, 격리 환경 반영
> - v1.2 (2026-04-03): 다중 사용자 관리 추가, ARM/x86 호환성 명시, HTTPS 확장 계획

---

## 1. 프로젝트 개요

### 목적
400~500권의 ebook(epub, pdf)과 3GB+ 전자문서(docx, hwp, txt, pdf)를
한 번의 검색으로 모두 검색할 수 있는 개인 문서 검색 서버.

### 핵심 요구사항
- **검색 품질 98~99%**: 문서에 존재하는 단어는 반드시 검색되어야 함
- **한국어 + 영어 혼합 검색**: 형태소 분석 기반 (nori)
- **모바일 반응형 웹앱**: 어디서든 브라우저로 즉시 검색
- **문서 미리보기**: 검색 결과에서 해당 위치를 바로 확인 (텍스트 → 이미지 → 다운로드 3단계)
- **증분 인덱싱**: 새 문서 추가 시 자동 파싱/인덱싱
- **다중 사용자**: 가족/동료 계정 지원 (admin/editor/viewer 역할 분리)
- **향후 의미 검색 확장 가능**: 벡터 필드 예약 (현재 미구현)
- **향후 HTTPS 전환 가능**: 현재 HTTP, Tailscale MagicDNS로 전환 예정

### 기술 스택
| 구분 | 기술 | 버전 | 라이선스 |
|------|------|------|---------|
| 검색엔진 | OpenSearch | 2.x (최신 안정) | Apache 2.0 |
| 백엔드 | Python + FastAPI | Python 3.12, FastAPI 0.110+ | MIT |
| 프론트엔드 | Jinja2 + HTMX + Tailwind CSS | HTMX 2.x | BSD/MIT |
| DB | PostgreSQL | 16.x | PostgreSQL License |
| ORM | SQLAlchemy + Alembic | SQLAlchemy 2.x | MIT |
| 작업큐 | Celery + Redis | Celery 5.x, Redis 7.x | BSD |
| OCR | Tesseract | 5.x (한국어+영어) | Apache 2.0 |
| 컨테이너 | Docker Compose | v2 | Apache 2.0 |
| OS (서버) | Ubuntu 24.04 LTS Server | — | — |

모든 의존성은 상업적 이용이 가능한 라이선스만 사용합니다.

---

## 2. 인프라 구성

### 2-1. 장비 역할 배치

| 장비 | 역할 | Claude Code | 개인 데이터 |
|------|------|-------------|------------|
| M3 Max MacBook (128GB) | 대화형 AI + VS Code Remote-SSH | 설치 안 함 | 있음 (주력기) |
| M1 Max MacBook (64GB) | Claude Code 전용 개발/검증기 | 설치됨 (sandbox) | 없음 (격리) |
| VMware 데스크탑 서버 | 운영 서버 (24/7) | 해당 없음 | 없음 |

### 2-2. VMware 서버 사양

```
물리 하드웨어:
  CPU: 16 Core → 이 중 6 vCPU 할당함
  RAM: 128GB ECC non-REG → 이 중 24GB 할당함
  GPU: RTX 4060 (향후 LLM용, 현재 미사용)
  디스크:
    - datastore1: 1TB SSD (VMware OS)
    - 1TB SSD (기타/실습)
    - 4TB SSD (기타/실습) → 이 중 / partition 1disk 130GB 할당함 
    - 8TB SSD x2 → 이 중 /data partition 2disk 300GB, 300GB 할당 후 mdadm RAID1 적용함
```

### 2-3. search-server VM 사양

```
VM: search-server
  CPU:  6 vCPU
  RAM:  24 GB
  OS:   Ubuntu 24.04 LTS Server
```

### 2-4. 디스크 레이아웃

```
가상 디스크 1: OS + Docker (datastore1에서 할당)
  /boot         1 GB   ext4
  VG: vg_system (LVM)
  ├── lv_root   120 GB  ext4   /
  ├── lv_swap    24 GB  swap
  └── (미할당)        (향후 확장용)

가상 디스크 2: 데이터 (8TB x2 RAID 1 위에 할당, 씬 프로비전)
  소프트웨어 RAID 1 (mdadm, Ubuntu 설치 시 구성)
  VG: vg_data (LVM)
  └── lv_data   전체   ext4   /data
      ├── /data/documents/        원본 문서 파일
      ├── /data/postgresql/       PostgreSQL 데이터
      ├── /data/opensearch/       OpenSearch 인덱스 데이터
      ├── /data/preview-cache/    미리보기 이미지 캐시
      └── /data/redis/            Redis 영속 데이터
```

RAID 1으로 데이터 디스크를 보호하므로 별도 백업 크론은 불필요합니다.

### 2-5. 네트워크 보안 (OPNsense)

M1 맥북 앞단에 OPNsense 방화벽이 있으며, 아웃바운드 화이트리스트를 적용합니다. → 아웃바운드 화이트리스트는 아직 적용하지 않았습니다.(26-04-10 v1.2) → 직접 클로드에게 적용할 계획이라면 적용해주시고 명시적으로 제가 알 수 있도록 알려주세요.

```
M1 맥북 허용 도메인 (이외 차단):

# Claude Code 필수
api.anthropic.com
statsig.anthropic.com
sentry.io

# 개발 도구
github.com
*.githubusercontent.com
pypi.org
files.pythonhosted.org
registry.npmjs.org
download.docker.com
*.orbstack.dev

# OS 업데이트
*.apple.com
swscan.apple.com

# Docker 이미지
hub.docker.com
registry-1.docker.io
production.cloudflare.docker.com
artifacts.opensearch.org
```

Suricata IPS: ET POLICY + ET TROJAN 규칙셋 활성화.

---

## 3. 데이터 저장소 설계

### 3-1. 저장소 역할 분담

```
PostgreSQL (source of truth)       OpenSearch (검색 인덱스)
┌────────────────────────┐        ┌────────────────────────┐
│ files 테이블            │  ──→  │ documents 인덱스        │
│  - 파일 경로/크기/해시   │ 빌드   │  - 검색용 메타데이터    │
│  - 파싱 상태/품질점수    │        │                        │
│  - 파싱 이력 로그        │        │                        │
│                         │        │                        │
│ chunks 테이블           │  ──→  │ chunks 인덱스           │
│  - 페이지별 텍스트       │ 빌드   │  - 형태소 분석된 텍스트  │
│  - 메타데이터            │        │  - 하이라이트/검색용    │
│                         │        │                        │
│ job_log 테이블          │        │                        │
│  - 파싱/OCR/인덱싱 작업  │        │                        │
└────────────────────────┘        └────────────────────────┘

- OpenSearch 인덱스가 손상되면 → PostgreSQL + 원본 파일로 재구축
- PostgreSQL이 손상되면 → 원본 파일로 재파싱 (시간 소요)
- 원본 파일 손실 → 복구 불가 ← RAID 1로 보호
```

### 3-2. PostgreSQL 스키마

```sql
-- ============================================================
-- 파일 레지스트리: 모든 문서의 원천 정보
-- ============================================================
CREATE TABLE files (
    file_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_path       TEXT NOT NULL UNIQUE,
    file_name       TEXT NOT NULL,
    file_size       BIGINT NOT NULL,
    file_hash       VARCHAR(64) NOT NULL,     -- SHA-256 (변경 감지)

    format          VARCHAR(10) NOT NULL,     -- pdf, epub, docx, txt, hwp
    mime_type       VARCHAR(100),

    -- 파싱 상태
    parse_status    VARCHAR(20) DEFAULT 'pending'
                    CHECK (parse_status IN ('pending','parsing','success','partial','failed')),
    parse_quality   REAL DEFAULT 0.0,
    parse_error     TEXT,
    parsed_at       TIMESTAMPTZ,

    -- 메타데이터 (파싱 후 채워짐)
    title           TEXT,
    author          TEXT,
    language        VARCHAR(10),
    total_pages     INTEGER,
    total_chunks    INTEGER DEFAULT 0,
    has_ocr_pages   BOOLEAN DEFAULT FALSE,

    -- 인덱싱 상태
    indexed_at      TIMESTAMPTZ,
    index_version   INTEGER DEFAULT 0,        -- 스키마 변경 시 재인덱싱 추적

    -- 타임스탬프
    file_modified_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_files_format ON files(format);
CREATE INDEX idx_files_parse_status ON files(parse_status);
CREATE INDEX idx_files_hash ON files(file_hash);

-- ============================================================
-- 파싱된 텍스트 (청크 단위)
-- ============================================================
CREATE TABLE chunks (
    chunk_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id         UUID NOT NULL REFERENCES files(file_id) ON DELETE CASCADE,

    page_number     INTEGER,
    chapter         TEXT,
    section         TEXT,
    content         TEXT NOT NULL,
    content_type    VARCHAR(20) DEFAULT 'text'
                    CHECK (content_type IN ('text','code','table','image_ocr')),
    is_ocr          BOOLEAN DEFAULT FALSE,
    char_count      INTEGER,

    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_chunks_file_id ON chunks(file_id);
CREATE INDEX idx_chunks_file_page ON chunks(file_id, page_number);

-- ============================================================
-- 태그
-- ============================================================
CREATE TABLE tags (
    file_id         UUID NOT NULL REFERENCES files(file_id) ON DELETE CASCADE,
    tag             VARCHAR(100) NOT NULL,
    PRIMARY KEY (file_id, tag)
);

CREATE INDEX idx_tags_tag ON tags(tag);

-- ============================================================
-- 작업 이력
-- ============================================================
CREATE TABLE job_log (
    job_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id         UUID REFERENCES files(file_id) ON DELETE SET NULL,

    job_type        VARCHAR(20) NOT NULL
                    CHECK (job_type IN ('parse','ocr','index','reindex','delete')),
    status          VARCHAR(20) DEFAULT 'pending'
                    CHECK (status IN ('pending','running','success','failed','cancelled')),

    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    duration_ms     INTEGER,
    error_message   TEXT,
    details         JSONB,                    -- 추가 정보 (유연한 구조)

    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_job_log_file ON job_log(file_id);
CREATE INDEX idx_job_log_status ON job_log(status);
CREATE INDEX idx_job_log_type ON job_log(job_type);

-- ============================================================
-- 검색 히스토리 (향후 검색 분석용)
-- ============================================================
CREATE TABLE search_history (
    search_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(user_id) ON DELETE SET NULL,
    query           TEXT NOT NULL,
    result_count    INTEGER,
    took_ms         INTEGER,
    filters         JSONB,
    searched_at     TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- 사용자 관리 (admin/editor/viewer 역할)
-- ============================================================
CREATE TABLE users (
    user_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username        VARCHAR(50) NOT NULL UNIQUE,
    email           VARCHAR(255) UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    display_name    VARCHAR(100),
    role            VARCHAR(20) DEFAULT 'viewer'
                    CHECK (role IN ('admin','editor','viewer')),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),
    last_login_at   TIMESTAMPTZ
);

-- 역할 권한:
--   admin:  문서 업로드/삭제, 사용자 관리, 시스템 설정, 재인덱싱
--   editor: 문서 업로드, 태그 편집
--   viewer: 검색/열람만 가능

CREATE TRIGGER trg_users_updated
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- 북마크/즐겨찾기
-- ============================================================
CREATE TABLE bookmarks (
    user_id         UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    file_id         UUID NOT NULL REFERENCES files(file_id) ON DELETE CASCADE,
    note            TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, file_id)
);

-- ============================================================
-- updated_at 자동 갱신 트리거
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_files_updated
    BEFORE UPDATE ON files
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
```

### 3-3. PostgreSQL vs SQLite 선택 근거

| 기준 | PostgreSQL | SQLite |
|------|-----------|--------|
| 동시 쓰기 | 다중 Celery 워커 동시 쓰기 안전 | 잠금 충돌 가능 |
| 확장성 | 사용자 관리, 북마크 등 추가 용이 | 제한적 |
| JSON 지원 | JSONB 타입 + 인덱싱 | JSON 지원 제한적 |
| 학습 가치 | 업계 표준 RDBMS | SQLite 전용 지식 |
| 운영 부담 | Docker 컨테이너 1개 추가 | 파일 1개 |

→ PostgreSQL 선택. Docker Compose에 컨테이너 추가로 운영 부담 최소.

---

## 4. 프로젝트 구조

```
search-server/
├── CLAUDE.md                       # ← 이 파일
├── README.md
├── docker-compose.yml
├── docker-compose.dev.yml          # 개발 환경 오버라이드
├── .env.example
├── pyproject.toml
├── alembic.ini                     # DB 마이그레이션 설정
├── requirements/
│   ├── base.txt
│   ├── dev.txt
│   └── prod.txt
│
├── app/                            # FastAPI 메인 앱
│   ├── __init__.py
│   ├── main.py                     # FastAPI 엔트리포인트
│   ├── config.py                   # 설정 (pydantic-settings)
│   ├── database.py                 # SQLAlchemy 엔진/세션
│   │
│   ├── api/                        # API 라우터
│   │   ├── __init__.py
│   │   ├── router.py               # 라우터 통합
│   │   ├── auth.py                 # 로그인/로그아웃/회원가입
│   │   ├── users.py                # 사용자 관리 (admin)
│   │   ├── search.py               # GET /api/search
│   │   ├── documents.py            # 문서 CRUD
│   │   ├── preview.py              # 문서 미리보기
│   │   └── admin.py                # 시스템 관리
│   │
│   ├── services/                   # 비즈니스 로직
│   │   ├── __init__.py
│   │   ├── auth_service.py         # 인증/인가 (JWT, 비밀번호 해싱)
│   │   ├── user_service.py         # 사용자 CRUD
│   │   ├── search_service.py       # 검색 쿼리 구성 및 실행
│   │   ├── index_service.py        # 인덱싱 (OpenSearch CRUD)
│   │   ├── document_service.py     # 문서 메타데이터 관리
│   │   └── preview_service.py      # PDF 페이지 렌더링 등
│   │
│   ├── parsers/                    # 문서 텍스트 추출
│   │   ├── __init__.py
│   │   ├── base.py                 # BaseParser ABC
│   │   ├── pdf_parser.py           # PyMuPDF 기반
│   │   ├── epub_parser.py          # ebooklib + BeautifulSoup
│   │   ├── docx_parser.py          # python-docx
│   │   ├── txt_parser.py           # chardet 인코딩 감지
│   │   ├── hwp_parser.py           # stub (미지원 → 향후 구현)
│   │   ├── ocr_processor.py        # Tesseract OCR
│   │   └── quality_checker.py      # 파싱 품질 점수 계산
│   │
│   ├── models/                     # SQLAlchemy ORM 모델
│   │   ├── __init__.py
│   │   ├── user.py                 # User 모델
│   │   ├── file.py                 # File 모델
│   │   ├── chunk.py                # Chunk 모델
│   │   ├── tag.py                  # Tag 모델
│   │   ├── bookmark.py             # Bookmark 모델
│   │   └── job_log.py              # JobLog 모델
│   │
│   ├── schemas/                    # Pydantic 스키마 (API 입출력)
│   │   ├── __init__.py
│   │   ├── auth.py                 # LoginRequest, TokenResponse
│   │   ├── user.py                 # UserCreate, UserResponse
│   │   ├── document.py             # DocumentResponse, DocumentCreate
│   │   ├── chunk.py                # ChunkResponse
│   │   ├── search.py               # SearchRequest, SearchResponse
│   │   └── admin.py                # ParseStatus, SystemStats
│   │
│   ├── opensearch/                 # OpenSearch 클라이언트 및 설정
│   │   ├── __init__.py
│   │   ├── client.py               # OpenSearch 연결 관리
│   │   ├── index_manager.py        # 인덱스 생성/매핑 관리
│   │   └── query_builder.py        # 검색 쿼리 빌더
│   │
│   ├── templates/                  # Jinja2 HTML 템플릿
│   │   ├── base.html               # 레이아웃 (Tailwind CDN)
│   │   ├── login.html              # 로그인 페이지
│   │   ├── search.html             # 메인 검색 페이지
│   │   ├── results.html            # 검색 결과 (HTMX partial)
│   │   ├── document_detail.html    # 문서 상세
│   │   ├── preview.html            # 페이지 미리보기
│   │   ├── admin/
│   │   │   ├── dashboard.html
│   │   │   ├── parse_status.html
│   │   │   ├── reindex.html
│   │   │   └── users.html          # 사용자 관리
│   │   └── components/
│   │       ├── search_bar.html
│   │       ├── result_card.html
│   │       ├── nav_bar.html        # 상단 네비게이션 (로그인 사용자 표시)
│   │       └── pagination.html
│   │
│   └── static/
│       ├── css/custom.css
│       └── js/app.js               # 최소한의 JS (HTMX 보조)
│
├── workers/                        # Celery 비동기 작업
│   ├── __init__.py
│   ├── celery_app.py
│   ├── tasks/
│   │   ├── __init__.py
│   │   ├── parse_task.py
│   │   ├── index_task.py
│   │   └── ocr_task.py
│   └── file_watcher.py             # watchdog 기반 파일 감시
│
├── migrations/                     # Alembic 마이그레이션
│   ├── env.py
│   ├── versions/
│   └── script.py.mako
│
├── opensearch-config/
│   ├── index_settings.json
│   ├── synonyms_ko.txt
│   └── synonyms_en.txt
│
├── docker/
│   ├── Dockerfile.api
│   ├── Dockerfile.worker
│   └── opensearch/
│       └── Dockerfile              # nori 플러그인 포함
│
├── scripts/
│   ├── init_opensearch.py          # 인덱스 초기 생성
│   ├── create_admin.py             # 초기 admin 계정 생성
│   ├── bulk_import.py              # 기존 문서 대량 임포트
│   ├── quality_report.py           # 파싱 품질 리포트
│   └── rebuild_index.py            # PostgreSQL → OpenSearch 재구축
│
├── tests/
│   ├── conftest.py
│   ├── test_parsers/
│   │   ├── test_pdf_parser.py
│   │   ├── test_epub_parser.py
│   │   ├── test_docx_parser.py
│   │   └── test_ocr_processor.py
│   ├── test_api/
│   │   ├── test_search.py
│   │   └── test_documents.py
│   ├── test_search_quality/
│   │   ├── test_keyword_recall.py
│   │   └── ground_truth.json
│   └── fixtures/
│       ├── sample_text.pdf
│       ├── sample_scan.pdf
│       ├── sample.epub
│       ├── sample.docx
│       └── sample.txt
│
└── docs/
    ├── architecture.md
    ├── api_reference.md
    └── deployment_guide.md
```

### 모듈 의존성 방향 (단방향만 허용)

```
templates → api → services → parsers
                            → opensearch
                            → models / schemas
                            → database
workers/tasks → services
```

순환 의존 금지.

---

## 5. OpenSearch 인덱스 스키마

### 5-1. 인덱스 구조

| 인덱스 | 용도 | 비고 |
|--------|------|------|
| `documents` | 문서 메타데이터 검색 | 제목, 저자, 태그 |
| `chunks` | 전문 검색 대상 | 페이지/섹션 텍스트 |

### 5-2. documents 인덱스

```json
{
  "settings": {
    "number_of_shards": 1,
    "number_of_replicas": 0,
    "analysis": {
      "analyzer": {
        "korean_english": {
          "type": "custom",
          "tokenizer": "nori_tokenizer",
          "filter": ["lowercase", "nori_readingform"]
        }
      },
      "tokenizer": {
        "nori_tokenizer": {
          "type": "nori_tokenizer",
          "decompound_mode": "mixed"
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "doc_id":         { "type": "keyword" },
      "title":          {
        "type": "text",
        "analyzer": "korean_english",
        "fields": {
          "keyword": { "type": "keyword" },
          "english": { "type": "text", "analyzer": "english" }
        }
      },
      "author":         {
        "type": "text",
        "fields": { "keyword": { "type": "keyword" } }
      },
      "format":         { "type": "keyword" },
      "file_name":      { "type": "keyword" },
      "total_pages":    { "type": "integer" },
      "total_chunks":   { "type": "integer" },
      "parse_quality":  { "type": "float" },
      "has_ocr_pages":  { "type": "boolean" },
      "tags":           { "type": "keyword" },
      "language":       { "type": "keyword" },
      "indexed_at":     { "type": "date" }
    }
  }
}
```

### 5-3. chunks 인덱스

```json
{
  "settings": {
    "number_of_shards": 2,
    "number_of_replicas": 0,
    "analysis": {
      "analyzer": {
        "nori_mixed": {
          "type": "custom",
          "tokenizer": "nori_mixed_tokenizer",
          "filter": ["lowercase", "nori_readingform", "nori_number"]
        },
        "ngram_analyzer": {
          "type": "custom",
          "tokenizer": "ngram_tokenizer",
          "filter": ["lowercase"]
        }
      },
      "tokenizer": {
        "nori_mixed_tokenizer": {
          "type": "nori_tokenizer",
          "decompound_mode": "mixed"
        },
        "ngram_tokenizer": {
          "type": "ngram",
          "min_gram": 2,
          "max_gram": 4,
          "token_chars": ["letter", "digit"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "chunk_id":       { "type": "keyword" },
      "doc_id":         { "type": "keyword" },
      "page_number":    { "type": "integer" },
      "chapter":        {
        "type": "text",
        "analyzer": "nori_mixed",
        "fields": { "keyword": { "type": "keyword" } }
      },
      "section":        { "type": "keyword" },
      "content": {
        "type": "text",
        "analyzer": "nori_mixed",
        "fields": {
          "english":  { "type": "text", "analyzer": "english" },
          "standard": { "type": "text", "analyzer": "standard" },
          "ngram":    { "type": "text", "analyzer": "ngram_analyzer" }
        }
      },
      "content_type":   { "type": "keyword" },
      "is_ocr":         { "type": "boolean" },
      "char_count":     { "type": "integer" },
      "embedding": {
        "type": "knn_vector",
        "dimension": 768,
        "method": {
          "name": "hnsw",
          "space_type": "cosinesimil",
          "engine": "faiss"
        }
      }
    }
  }
}
```

**content 필드 4개 sub-field 설계 의도:**
- `nori_mixed` (기본): 한국어 형태소 분석 + 복합어 분해
- `english`: 영어 스테밍 (running → run)
- `standard`: 원형 보존 (코드, 변수명 정확 매칭)
- `ngram`: 부분 문자열 매칭 (오타 보완, 변수명)
- `embedding`: 벡터 검색 예약 (현재 데이터 넣지 않음)

---

## 6. API 엔드포인트 명세

### 6-1. 검색 API

```
GET /api/search
  Query Parameters:
    q          (str, required)   검색어
    page       (int, default=1)  페이지 번호
    size       (int, default=20) 페이지 크기 (max=100)
    format     (str, optional)   포맷 필터 (pdf,epub,docx,txt)
    sort       (str, default=_score) 정렬 (_score, date, title)
    highlight  (bool, default=true) 하이라이트 포함 여부

  Response 200:
    {
      "query": "python list",
      "total": 142,
      "page": 1,
      "size": 20,
      "took_ms": 35,
      "results": [
        {
          "doc_id": "uuid",
          "title": "파이썬 완벽 가이드",
          "author": "저자명",
          "format": "pdf",
          "page_number": 142,
          "chapter": "Chapter 5: 자료구조",
          "highlight": "...<mark>python</mark> <mark>list</mark> comprehension은...",
          "score": 15.7,
          "is_ocr": false
        }
      ]
    }
```

### 6-2. 인증 API

```
POST /api/auth/login                     # 로그인 → JWT 토큰 반환
POST /api/auth/logout                    # 로그아웃 (토큰 무효화)
POST /api/auth/register                  # 회원가입 (admin만 생성 가능, 또는 초대)
GET  /api/auth/me                        # 현재 로그인 사용자 정보
PUT  /api/auth/password                  # 비밀번호 변경
```

### 6-3. 사용자 관리 API (admin 전용)

```
GET    /api/users                        # 사용자 목록
GET    /api/users/{user_id}              # 사용자 상세
PUT    /api/users/{user_id}              # 사용자 정보 수정 (역할 변경 등)
DELETE /api/users/{user_id}              # 사용자 비활성화
```

### 6-4. 문서 관리 API

```
GET    /api/documents                    # 문서 목록 (페이지네이션, 필터)
GET    /api/documents/{doc_id}           # 문서 상세 메타데이터
DELETE /api/documents/{doc_id}           # 문서 삭제
POST   /api/documents/upload             # 파일 업로드 → 파싱 큐 등록
POST   /api/documents/reindex/{doc_id}   # 특정 문서 재인덱싱
```

### 6-5. 미리보기 API

```
GET /api/preview/{doc_id}/text/{page_num}
  # 해당 페이지 ± 1~2페이지 텍스트 반환

GET /api/preview/{doc_id}/image/{page_num}
  # PDF 페이지를 이미지(JPEG)로 렌더링
  Query: dpi (int, default=150)

GET /api/preview/{doc_id}/download
  # 원본 파일 다운로드
```

### 6-6. 관리 API

```
GET  /api/admin/stats                   # 시스템 통계
GET  /api/admin/parse-status            # 파싱 상태 목록
POST /api/admin/reindex-all             # 전체 재인덱싱
POST /api/admin/scan-folder             # 문서 폴더 스캔
```

### 6-7. 웹 페이지 (HTML)

```
GET /                    # 메인 검색 페이지 (로그인 필요)
GET /login               # 로그인 페이지
GET /search?q=...        # 검색 결과 페이지
GET /document/{doc_id}   # 문서 상세
GET /admin               # 관리 대시보드 (admin 전용)
GET /admin/users         # 사용자 관리 (admin 전용)
```

모든 페이지는 로그인 필수. 미인증 접근 시 /login으로 리다이렉트.

---

## 7. 파싱 파이프라인

### 7-1. 포맷별 처리

| 포맷 | 라이브러리 | 청킹 단위 | 오버랩 |
|------|----------|----------|--------|
| PDF (텍스트) | PyMuPDF | 페이지 | 없음 |
| PDF (스캔본) | PyMuPDF + Tesseract | 페이지 | 없음 |
| EPUB | ebooklib + BeautifulSoup | 챕터/섹션 | 200자 |
| DOCX | python-docx | Heading 기준 섹션 | 200자 |
| TXT | chardet + 직접 읽기 | 2000자 고정 | 200자 |
| HWP | stub (미지원) | — | — |

### 7-2. 스캔본 PDF 감지

```python
def is_scan_page(page_text: str, page_images: int) -> bool:
    """페이지 단위 판정: 텍스트 50자 미만 AND 이미지 1개 이상"""
    return len(page_text.strip()) < 50 and page_images >= 1
```

### 7-3. 품질 점수 (0.0 ~ 1.0)

- 텍스트 추출 성공률 (가중치 0.4)
- 평균 글자 수 적정성 (가중치 0.3)
- 비정상 문자 비율 역수 (가중치 0.2)
- 구조 정보 존재 여부 (가중치 0.1)

등급: 0.9+ = success, 0.7~0.9 = partial, <0.7 = failed

### 7-4. 청킹 규칙

- 최소 청크: 100자 (이하 → 이전 청크에 병합)
- 최대 청크: 5000자 (이상 → 분할)
- 오버랩: 이전 청크 마지막 200자 포함 (PDF 제외)

---

## 8. 검색 쿼리 설계

```json
{
  "query": {
    "bool": {
      "should": [
        {
          "multi_match": {
            "query": "사용자 검색어",
            "fields": [
              "content^3",
              "content.english^2",
              "content.standard^2",
              "content.ngram^1",
              "chapter^1.5"
            ],
            "type": "best_fields",
            "operator": "or",
            "minimum_should_match": "75%"
          }
        }
      ]
    }
  },
  "highlight": {
    "fields": {
      "content": {
        "fragment_size": 200,
        "number_of_fragments": 3,
        "pre_tags": ["<mark>"],
        "post_tags": ["</mark>"]
      }
    }
  },
  "collapse": {
    "field": "doc_id",
    "inner_hits": {
      "name": "pages",
      "size": 3,
      "sort": [{ "_score": "desc" }]
    }
  }
}
```

---

## 9. Docker Compose

```yaml
version: "3.8"

services:
  opensearch:
    build:
      context: ./docker/opensearch
    container_name: search-opensearch
    environment:
      - discovery.type=single-node
      - plugins.security.disabled=true
      - OPENSEARCH_JAVA_OPTS=-Xms2g -Xmx2g
      - DISABLE_INSTALL_DEMO_CONFIG=true
    ulimits:
      memlock: { soft: -1, hard: -1 }
      nofile: { soft: 65536, hard: 65536 }
    volumes:
      - opensearch-data:/usr/share/opensearch/data
      - ./opensearch-config/synonyms_ko.txt:/usr/share/opensearch/config/synonyms_ko.txt
      - ./opensearch-config/synonyms_en.txt:/usr/share/opensearch/config/synonyms_en.txt
    ports:
      - "9200:9200"
    mem_limit: 4g
    restart: unless-stopped

  opensearch-dashboards:
    image: opensearchproject/opensearch-dashboards:2
    container_name: search-dashboards
    environment:
      - OPENSEARCH_HOSTS=["http://opensearch:9200"]
      - DISABLE_SECURITY_DASHBOARDS_PLUGIN=true
    ports:
      - "5601:5601"
    mem_limit: 1g
    depends_on: [opensearch]
    restart: unless-stopped

  postgres:
    image: postgres:16-alpine
    container_name: search-postgres
    environment:
      - POSTGRES_DB=searchdb
      - POSTGRES_USER=search
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
    volumes:
      - postgres-data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    mem_limit: 1g
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    container_name: search-redis
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    mem_limit: 512m
    restart: unless-stopped

  api:
    build:
      context: .
      dockerfile: docker/Dockerfile.api
    container_name: search-api
    environment:
      - OPENSEARCH_URL=http://opensearch:9200
      - DATABASE_URL=postgresql+asyncpg://search:${POSTGRES_PASSWORD}@postgres:5432/searchdb
      - REDIS_URL=redis://redis:6379/0
      - DOCUMENT_ROOT=/data/documents
      - PREVIEW_CACHE=/data/preview-cache
    volumes:
      - documents:/data/documents
      - preview-cache:/data/preview-cache
    ports:
      - "8000:8000"
    mem_limit: 2g
    depends_on: [opensearch, postgres, redis]
    restart: unless-stopped

  worker:
    build:
      context: .
      dockerfile: docker/Dockerfile.worker
    container_name: search-worker
    environment:
      - OPENSEARCH_URL=http://opensearch:9200
      - DATABASE_URL=postgresql+asyncpg://search:${POSTGRES_PASSWORD}@postgres:5432/searchdb
      - REDIS_URL=redis://redis:6379/0
      - DOCUMENT_ROOT=/data/documents
      - PREVIEW_CACHE=/data/preview-cache
    volumes:
      - documents:/data/documents
      - preview-cache:/data/preview-cache
    mem_limit: 4g
    depends_on: [opensearch, postgres, redis]
    restart: unless-stopped

  file-watcher:
    build:
      context: .
      dockerfile: docker/Dockerfile.worker
    container_name: search-watcher
    command: python -m workers.file_watcher
    environment:
      - REDIS_URL=redis://redis:6379/0
      - WATCH_DIR=/data/documents
    volumes:
      - documents:/data/documents
    mem_limit: 256m
    depends_on: [redis]
    restart: unless-stopped

volumes:
  opensearch-data:
  postgres-data:
  redis-data:
  documents:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /srv/search/documents
  preview-cache:
```

---

## 10. 프론트엔드 설계

### HTMX 핵심 패턴

```html
<!-- 실시간 검색 -->
<input type="search" name="q"
       hx-get="/api/search"
       hx-trigger="keyup changed delay:300ms"
       hx-target="#results"
       hx-indicator="#spinner" />

<!-- 미리보기 인라인 로드 -->
<button hx-get="/api/preview/{doc_id}/text/{page}"
        hx-target="#preview-panel"
        hx-swap="innerHTML">미리보기</button>
```

### 모바일 최적화
- Tailwind 반응형: `sm:`, `md:`, `lg:`
- 터치 최적화: 버튼 최소 44x44px
- PWA manifest: 홈 화면 추가 가능

---

## 11. 보안 설계

### 인증/인가 (다중 사용자)

```
인증 방식: JWT (JSON Web Token)
- 로그인 시 access_token (30분) + refresh_token (7일) 발급
- 비밀번호: bcrypt 해싱 (passlib)
- 첫 실행 시 admin 계정 자동 생성 (환경변수에서 초기 비밀번호)
- admin만 새 사용자 생성 가능 (셀프 회원가입 비활성화)

역할 기반 접근 제어 (RBAC):
  admin:  모든 기능 + 사용자 관리 + 시스템 설정 + 재인덱싱
  editor: 검색 + 문서 업로드 + 태그 편집
  viewer: 검색 + 열람만

API 보호:
  /api/auth/*          → 인증 불필요 (로그인/토큰 갱신)
  /api/search          → viewer 이상
  /api/documents       → viewer(GET), editor(POST/PUT), admin(DELETE)
  /api/preview         → viewer 이상
  /api/users           → admin 전용
  /api/admin           → admin 전용
```

### 파일 접근
```python
def safe_file_path(doc_id: str) -> Path:
    doc = get_document(doc_id)
    path = Path(doc.file_path).resolve()
    assert path.is_relative_to(DOCUMENT_ROOT)
    return path
```

### 내부 서비스 보안
- OpenSearch/PostgreSQL: 내부망 전용, Docker 네트워크 내에서만 접근
- Redis: 내부망 전용, 비밀번호 설정 권장
- 서비스 간 통신은 Docker 내부 네트워크만 사용 (포트 외부 노출 최소화)

### 외부 접근
- Tailscale VPN으로 외부에서 안전하게 접속
- 향후 HTTPS 전환: Tailscale MagicDNS 자동 인증서 활용 예정

---

## 12. 아키텍처 호환성

### ARM (M1 개발) ↔ x86 (서버 운영)

개발 환경(M1 Max, ARM64)과 운영 환경(VMware Ubuntu, x86_64)의 CPU 아키텍처가 다름.
Docker multi-arch 이미지를 사용하므로 호환성 문제 없음.

```
호환 확인된 이미지:
  opensearchproject/opensearch:2   — multi-arch ✅
  postgres:16-alpine               — multi-arch ✅
  redis:7-alpine                   — multi-arch ✅
  python:3.12-slim                 — multi-arch ✅
```

주의사항:
- Dockerfile에서 특정 아키텍처를 하드코딩하지 않을 것
- `FROM --platform=linux/amd64` 같은 지정 사용 금지
- Python 패키지 중 C 확장이 있는 것은 양쪽에서 빌드 테스트 필요
  (PyMuPDF, Pillow 등은 양쪽 모두 wheel 제공 확인됨)

---

## 13. 검색 품질 검증

### Ground Truth

```json
{
  "test_cases": [
    {
      "id": "TC001",
      "query": "python list comprehension",
      "expected_results": [
        { "title_contains": "파이썬", "page_range": [140, 145], "must_exist": true }
      ]
    }
  ]
}
```

목표: Recall >= 0.98 (98%)

---

## 14. 향후 확장

| 기능 | 현재 | 확장 시 |
|------|------|--------|
| 의미 검색 | 스키마 예약만 | 임베딩 모델 + 파이프라인 |
| AI 요약 | — | 로컬 LLM (RTX 4060) |
| 자동 태깅 | — | 분류 모델 |
| HWP 파싱 | stub | pyhwp 또는 LibreOffice CLI |
| HTTPS | HTTP (내부망) | Tailscale MagicDNS 자동 인증서 |
| 셀프 회원가입 | admin만 생성 | 초대 링크 또는 승인 방식 |

---

## 15. 주요 Python 패키지

```
# requirements/base.txt

# 웹
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
jinja2>=3.1.0
python-multipart>=0.0.9

# DB
sqlalchemy[asyncio]>=2.0.0
asyncpg>=0.29.0
alembic>=1.13.0

# 검색
opensearch-py>=2.4.0

# 문서 파싱
PyMuPDF>=1.24.0
ebooklib>=0.18
python-docx>=1.1.0
beautifulsoup4>=4.12.0
chardet>=5.2.0
pytesseract>=0.3.10
Pillow>=10.0.0

# 작업큐
celery[redis]>=5.3.0
redis>=5.0.0

# 유틸리티
pydantic>=2.5.0
pydantic-settings>=2.1.0
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4
watchdog>=4.0.0
httpx>=0.27.0
```

```
# requirements/dev.txt
-r base.txt
pytest>=8.0.0
pytest-asyncio>=0.23.0
pytest-cov>=4.1.0
ruff>=0.3.0
```

---

## 16. Claude Code 사용 가이드

### 보안 설정 (.claude/settings.json)

M1 Max 격리 환경 전용 설정이 프로젝트 루트의 `.claude/settings.json`에 배치되어 있습니다.
sandbox는 `/sandbox` 명령으로 활성화합니다 (auto-allow 모드).

### 코드 생성 규칙

1. 이 CLAUDE.md의 프로젝트 구조와 모듈 의존성 방향을 준수할 것
2. 모든 코드에 타입 힌트 필수
3. 비즈니스 로직은 services/ 에 집중
4. API 라우터에는 로직을 넣지 않고 services를 호출만 할 것
5. 새 파일 생성 시 해당 디렉토리의 __init__.py도 함께 업데이트
6. 설정값은 하드코딩하지 말고 app/config.py의 Settings 클래스 사용
7. DB 스키마 변경 시 반드시 Alembic 마이그레이션 생성
8. 테스트 코드 동시 작성
