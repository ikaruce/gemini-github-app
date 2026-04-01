# Gemini GitHub App — 구현 플랜

## 프로젝트 개요

### 목적

GitHub 조직(Org)에 Gemini CLI GitHub App을 설치하면, 해당 Org 내 모든 리포지토리에 Gemini CLI 워크플로우를 자동으로 배포하고 운영하는 백엔드 서버입니다.

### 핵심 기능

| 기능 | 설명 |
|------|------|
| **워크플로우 자동 배포** | App 설치 시 각 리포에 PR을 자동 생성하여 워크플로우 설치 유도 |
| **Org Secret 자동 등록** | App 설치 시 `APP_ID`, `APP_PRIVATE_KEY`를 Org Secret에 자동 등록 |
| **Secret 변경 감지** | Audit Log 폴링으로 Secret 변경을 감지하고 자동 복구 |
| **GitHub Issue 알림** | 이상 상황 발생 시 지정 리포에 GitHub Issue로 알림 |

### 동작 흐름

```
Org에 App 설치
      │
      ▼
installation webhook 수신
      ├── Org Secret 자동 등록 (APP_ID, APP_PRIVATE_KEY)
      └── 각 리포에 워크플로우 PR 자동 생성
                │
                ▼
         관리자가 PR 검토 후 머지
                │
                ▼
         Gemini CLI 즉시 사용 가능
                │
    ┌───────────┴───────────┐
    │                       │
    ▼                       ▼
PR 오픈 시 자동 리뷰    댓글로 수동 호출
                        @gemini-cli /review
                        @gemini-cli 설명해줘
```

```
[백그라운드 — 5분마다]
Audit Log 폴링
      │
      ▼
APP_ID / APP_PRIVATE_KEY 변경 감지
      │
      ├── 자동 복구 시도
      │         │
      │    성공 → 정상 운영 재개
      │    실패 → GitHub Issue 생성 (수동 확인 요청)
      │
      └── GitHub Issue 알림 발송
```

### 배포되는 워크플로우 파일

| 파일 | 역할 |
|------|------|
| `gemini-dispatch.yml` | 이벤트 감지 및 라우팅 (중앙 허브, 재사용 워크플로우 호출) |
| `gemini-review.yml` | PR 자동 코드 리뷰 (`workflow_call` 지원) |
| `gemini-triage.yml` | Issue 자동 트리아지 및 레이블 적용 (`workflow_call` 지원) |
| `gemini-invoke.yml` | `@gemini-cli` 자유 형식 명령 처리 (`workflow_call` 지원) |

### 기술 스택

- **언어**: Python 3.11+
- **패키지 매니저**: uv (`pyproject.toml` + `uv.lock`)
- **웹 프레임워크**: FastAPI
- **스케줄러**: APScheduler (Audit Log 폴링)
- **GitHub 인증**: PyJWT (GitHub App JWT 생성)
- **Secret 암호화**: PyNaCl (libsodium 기반)
- **HTTP 클라이언트**: httpx

---

## 프로젝트 구조

```
gemini-github-app/
├── app/
│   ├── main.py                  # FastAPI 서버 진입점 + APScheduler 생명주기
│   ├── config.py                # 환경변수 설정 (pydantic-settings)
│   ├── logging_config.py        # 로그 설정 (콘솔 + 파일 핸들러, 로테이션)
│   ├── webhook/
│   │   ├── __init__.py
│   │   ├── handler.py           # webhook 라우터
│   │   ├── installation.py      # installation 이벤트 처리
│   │   └── verify.py            # webhook 서명 검증
│   ├── github/
│   │   ├── __init__.py
│   │   ├── client.py            # GitHub App JWT 생성 + Installation Access Token 발급
│   │   ├── secret.py            # Org Secret 등록/복구
│   │   ├── workflow.py          # 브랜치 생성 + 파일 커밋 + PR 생성
│   │   └── repo.py              # 리포 정보 조회 (브랜치 보호 확인 등)
│   ├── audit/
│   │   ├── __init__.py
│   │   └── poller.py            # Audit Log 폴링 + Secret 변경 감지 + 복구
│   └── notify/
│       ├── __init__.py
│       └── issue.py             # GitHub Issue 생성으로 알림
├── templates/
│   ├── gemini-dispatch.yml      # ✅ 완료 (재사용 워크플로우 호출 방식)
│   ├── gemini-review.yml        # ✅ 완료 (workflow_call 지원)
│   ├── gemini-triage.yml        # ✅ 완료 (workflow_call 지원)
│   ├── gemini-invoke.yml        # ✅ 완료 (workflow_call 지원)
│   └── pr-body.md               # ✅ 완료
├── tests/
│   └── unit/
│       ├── conftest.py
│       ├── test_config.py
│       ├── test_logging_config.py
│       ├── audit/
│       ├── github/
│       ├── notify/
│       └── webhook/
├── logs/                        # 로그 파일 출력 디렉터리 (Docker 볼륨 마운트)
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml               # uv 패키지 설정 (requirements.txt 대체)
├── .env.example
└── README.md
```

---

## 구현 순서

### 1단계 — 기반 설정

**`pyproject.toml`** (uv 기반, requirements.txt 미사용)
```toml
[project]
name = "gemini-github-app"
requires-python = ">=3.11"
dependencies = [
    "fastapi", "uvicorn[standard]", "pydantic-settings",
    "PyJWT", "cryptography", "PyNaCl",
    "httpx", "apscheduler", "python-dotenv",
]

[dependency-groups]
dev = ["pytest", "pytest-asyncio"]
```

**`config.py`**
- 환경변수 로드 및 유효성 검사 (pydantic-settings)
- 필수값 누락 시 서버 시작 실패 처리

| 환경변수 | 필수 | 기본값 | 설명 |
|----------|:----:|--------|------|
| `APP_ID` | ✅ | — | GitHub App ID |
| `APP_PRIVATE_KEY` | ✅ | — | RSA 비밀키 (PEM) |
| `WEBHOOK_SECRET` | ✅ | — | Webhook HMAC 시크릿 |
| `NOTIFY_REPO` | ✅ | — | 알림 Issue 생성 리포 (`org/repo`) |
| `GITHUB_API_URL` | — | `https://api.github.com` | GHES 사용 시 `https://{hostname}/api/v3` |
| `LOG_FILE_NAME` | — | `None` | 로그 파일명. 미설정 시 콘솔만 출력 |
| `LOG_ROTATION_WHEN` | — | `midnight` | 로테이션 주기 (`midnight`, `h`, `d`, `w0`~`w6`) |
| `LOG_ROTATION_BACKUP_COUNT` | — | `30` | 보관할 로테이션 파일 수 |
| `AUDIT_POLL_INTERVAL_MINUTES` | — | `5` | Audit Log 폴링 주기 (분) |

**`logging_config.py`**
- `setup_logging(settings)`: 루트 로거에 핸들러 구성
- 콘솔 핸들러 (항상 추가)
- `LOG_FILE_NAME` 설정 시 `logs/{LOG_FILE_NAME}`에 `TimedRotatingFileHandler` 추가
- 핸들러 중복 추가 방지 (uvicorn reload 대응)

---

### 2단계 — GitHub API 클라이언트 (`github/`)

**`client.py`** — 인증 토큰 관리
- GitHub App JWT 생성 (RS256, `iat=now-60`, `exp=now+540`)
- Installation ID로 Access Token 발급
- Org명으로 Installation ID 조회
- 모든 함수에 `api_url` 파라미터 추가 (GHES 지원)

**`secret.py`** — Org Secret 관리
- Org Public Key 조회
- PyNaCl로 Secret 값 암호화 (libsodium sealed box)
- Org Secret 등록/업데이트 API 호출 (`visibility: "all"` 필수)
- `APP_ID`, `APP_PRIVATE_KEY` 일괄 등록

**`repo.py`** — 리포지토리 정보
- Org 내 리포 목록 조회 (archived, fork 제외)
- 브랜치 SHA 조회 (`GET .../ref/heads/` 단수 주의)
- 파일/PR 존재 여부 확인

**`workflow.py`** — 워크플로우 설치
- 새 브랜치 생성 (`add-gemini-cli-workflows`, `POST .../refs/` 복수)
- 422 (브랜치 이미 존재) 시 무시하고 계속 진행
- 워크플로우 파일 4개 일괄 커밋
- PR 생성 (pr-body.md 내용 활용)
- 이미 PR이 열려 있으면 스킵

> **GHES 지원**: 모든 `github/` 모듈 함수는 `api_url: str` 파라미터를 가지며,
> 상위 모듈(`installation.py`, `poller.py` 등)에서 `settings.github_api_url`을 전달한다.

---

### 3단계 — Webhook 핸들러 (`webhook/`)

**`verify.py`** — 보안 검증
- `X-Hub-Signature-256` 헤더 HMAC 검증
- `await request.body()` raw bytes 먼저 읽기 → `json.loads()` 순서 필수
- 검증 실패 시 403 반환

**`installation.py`** — installation 이벤트 처리

| action | 처리 내용 |
|--------|----------|
| `created` | Org Secret 등록 + 모든 리포에 워크플로우 PR 생성 |
| `added` | 새로 추가된 리포에만 워크플로우 PR 생성 |
| `deleted` | 알림 Issue 생성 |

- 대규모 Org 대응: `asyncio.gather` + `Semaphore(10)` 병렬 배포

**`handler.py`** — FastAPI 라우터
- `POST /webhook` 엔드포인트
- `X-GitHub-Event` 헤더로 이벤트 타입 분기

---

### 4단계 — Audit Log 폴링 (`audit/`)

**`poller.py`** — Secret 변경 감지

```
APScheduler (5분마다, AsyncIOScheduler)
      │  max_instances=1, coalesce=True
      ▼
등록된 Org 목록 순회
      │
      ▼
GET /orgs/{org}/audit-log?phrase=action:org.update_secret
      │ (403 → GHEC 미지원 Org, 경고 로그 후 스킵)
      ▼
APP_ID / APP_PRIVATE_KEY 변경 이벤트 확인
      │
      ├── 이미 처리한 이벤트 (_document_id 기준) → 스킵
      │     (_processed_doc_ids 집합, 10,000 초과 시 5,000개 정리)
      └── 신규 변경 감지
                │
                ├── Secret 자동 복구 시도
                │         ├── 성공 → 처리 완료 기록
                │         └── 실패 → notify/issue.py 호출
                │
                └── 처리 완료 기록
```

---

### 5단계 — 알림 (`notify/`)

**`issue.py`** — GitHub Issue 생성

| 상황 | Issue 제목 예시 |
|------|----------------|
| Secret 변경 감지 | `⚠️ [Org-A] APP_ID Secret이 변경되었습니다` |
| 자동 복구 실패 | `🚨 [Org-A] Secret 복구 실패 — 수동 확인 필요` |
| App 제거 감지 | `ℹ️ [Org-A] Gemini CLI App이 제거되었습니다` |

---

### 6단계 — 진입점 및 설정

**`main.py`**
- `setup_logging(settings)` 호출 (lifespan 시작 시)
- FastAPI `@asynccontextmanager lifespan` 패턴
- `AsyncIOScheduler` 시작/종료
- webhook 라우터, `/health` 엔드포인트 등록

**`.env.example`**
```dotenv
# GitHub App 설정 (필수)
APP_ID=123456
APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----"
WEBHOOK_SECRET=your_webhook_secret_here

# 알림 설정
NOTIFY_REPO=your-org/ops-repo

# GHES 사용 시 주석 해제 (기본값: https://api.github.com)
# GITHUB_API_URL=https://github.example.com/api/v3

# 로그 설정
# LOG_FILE_NAME=app.log
# LOG_ROTATION_WHEN=midnight
# LOG_ROTATION_BACKUP_COUNT=30

# Audit Log 폴링 주기 (분, 기본 5)
AUDIT_POLL_INTERVAL_MINUTES=5
```

**`docker-compose.yml`**
```yaml
services:
  app:
    image: gemini-github-app:${TAG:-latest}
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./app:/app/app:ro
      - ./templates:/app/templates:ro
      - ./logs:/app/logs          # 로그 파일 영속화
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "..."]
      interval: 30s
```

- `TAG` 환경변수로 이미지 태그 지정 (`TAG=v1.2.3 docker compose up`)
- `./logs:/app/logs` 볼륨으로 로그 파일 호스트에 영속화

---

### 7단계 — 워크플로우 템플릿 (`templates/`)

**호출 방식: 재사용 워크플로우 (`workflow_call`)**

`gemini-dispatch.yml`은 `actions/github-script` API 호출 방식 대신
job 레벨 `uses:` 키워드로 재사용 워크플로우를 직접 호출한다.

```yaml
# gemini-dispatch.yml
jobs:
  call-review:
    if: github.event_name == 'pull_request'
    uses: ./.github/workflows/gemini-review.yml
    with:
      pr_number: ${{ github.event.pull_request.number }}
    secrets: inherit

  call-triage:
    if: github.event_name == 'issues'
    uses: ./.github/workflows/gemini-triage.yml
    with:
      issue_number: ${{ github.event.issue.number }}
    secrets: inherit

  call-invoke:
    if: |
      github.event_name == 'issue_comment' &&
      contains(github.event.comment.body, '@gemini-cli')
    uses: ./.github/workflows/gemini-invoke.yml
    with:
      comment_id: ${{ github.event.comment.id }}
      comment_body: ${{ github.event.comment.body }}
    secrets: inherit
```

각 워크플로우는 `workflow_call` 트리거를 추가하여 dispatch에서 직접 호출 가능하면서,
`pull_request` / `issues` / `issue_comment` 직접 트리거도 그대로 유지한다.

| 파일 | `workflow_call` 입력 | 직접 트리거 유지 |
|------|----------------------|----------------|
| `gemini-review.yml` | `pr_number: number` | `pull_request`, `workflow_dispatch` |
| `gemini-triage.yml` | `issue_number: number` | `issues`, `workflow_dispatch` |
| `gemini-invoke.yml` | `comment_id: number`, `comment_body: string` | `issue_comment`, `pull_request_review_comment`, `workflow_dispatch` |

**이전 방식 대비 장점**

| 항목 | 이전 (github-script API 호출) | 이후 (workflow_call) |
|------|-------------------------------|----------------------|
| GitHub API 호출 | 워크플로우 트리거마다 REST API 1회 | 없음 |
| 실행 연속성 | 별도 워크플로우 실행 (컨텍스트 단절) | dispatch job의 자식으로 실행 |
| 로그 확인 | 트리거된 워크플로우 별도 확인 | dispatch run에서 통합 확인 |
| `secrets` 전달 | 명시적 전달 필요 | `secrets: inherit` 자동 상속 |

---

## 구현 시 주의사항

| 항목 | 내용 |
|------|------|
| **Secret 암호화** | GitHub API는 libsodium sealed box로 암호화된 값만 허용. PyNaCl 사용 필수 |
| **JWT 만료** | GitHub App JWT는 최대 10분 유효. `iat=now-60`, `exp=now+540`으로 설정 |
| **Webhook 서명 검증** | `await request.body()` → `json.loads()` 순서. `request.json()` 재호출 불가 |
| **중복 PR 방지** | 동일 브랜치 PR이 이미 열려 있으면 스킵 |
| **Audit Log 중복 처리** | `_document_id` 기준으로 처리 완료 여부 추적 |
| **Rate Limit** | Audit Log 폴링 주기가 너무 짧으면 API Rate Limit 초과. 5분 권장 |
| **GHES 지원** | `GITHUB_API_URL` 환경변수로 엔드포인트 지정. 미설정 시 `https://api.github.com` |
| **Audit Log 권한** | GHEC 전용 API. 403 응답 시 경고 로그 후 해당 Org 스킵 |
| **PEM 개행** | `.env`의 `\\n` 리터럴을 `field_validator`에서 실제 개행(`\n`)으로 변환 필수 |
| **ref vs refs** | `GET .../git/ref/heads/{branch}` (단수) vs `POST .../git/refs` (복수) |
| **APScheduler** | `AsyncIOScheduler` 사용. `max_instances=1`, `coalesce=True` 필수 |
| **로그 파일** | `LOG_FILE_NAME` 미설정 시 콘솔만. 설정 시 `logs/` 디렉터리 자동 생성 |
