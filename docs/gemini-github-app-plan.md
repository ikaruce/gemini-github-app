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
| `gemini-dispatch.yml` | 이벤트 감지 및 라우팅 (중앙 허브) |
| `gemini-review.yml` | PR 자동 코드 리뷰 |
| `gemini-triage.yml` | Issue 자동 트리아지 및 레이블 적용 |
| `gemini-invoke.yml` | `@gemini-cli` 자유 형식 명령 처리 |

### 기술 스택

- **언어**: Python
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
│   ├── main.py                  # FastAPI 서버 진입점
│   ├── config.py                # 환경변수 설정
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
│   ├── gemini-dispatch.yml      # ✅ 완료
│   ├── gemini-review.yml        # ✅ 완료
│   ├── gemini-triage.yml        # ✅ 완료
│   ├── gemini-invoke.yml        # ✅ 완료
│   └── pr-body.md               # ✅ 완료
├── .env.example
├── requirements.txt
└── README.md
```

---

## 구현 순서

### 1단계 — 기반 설정

**`requirements.txt`**
- fastapi, uvicorn
- PyJWT, cryptography
- PyNaCl (Secret 암호화)
- httpx
- apscheduler
- python-dotenv

**`config.py`**
- 환경변수 로드 및 유효성 검사
- 필수값 누락 시 서버 시작 실패 처리

---

### 2단계 — GitHub API 클라이언트 (`github/`)

**`client.py`** — 인증 토큰 관리
- GitHub App JWT 생성 (RS256, 10분 유효)
- Installation ID로 Access Token 발급
- Org명으로 Installation ID 조회

**`secret.py`** — Org Secret 관리
- Org Public Key 조회
- PyNaCl로 Secret 값 암호화 (libsodium sealed box)
- Org Secret 등록/업데이트 API 호출
- `APP_ID`, `APP_PRIVATE_KEY` 일괄 등록

**`repo.py`** — 리포지토리 정보
- Org 내 리포 목록 조회
- 브랜치 보호 여부 확인
- 이미 워크플로우 파일이 있는지 확인

**`workflow.py`** — 워크플로우 설치
- 새 브랜치 생성 (`add-gemini-cli-workflows`)
- 워크플로우 파일 4개 일괄 커밋
- PR 생성 (pr-body.md 내용 활용)
- 이미 PR이 열려 있으면 스킵

---

### 3단계 — Webhook 핸들러 (`webhook/`)

**`verify.py`** — 보안 검증
- `X-Hub-Signature-256` 헤더 HMAC 검증
- 검증 실패 시 403 반환

**`installation.py`** — installation 이벤트 처리

| action | 처리 내용 |
|--------|----------|
| `created` | Org Secret 등록 + 모든 리포에 워크플로우 PR 생성 |
| `added` | 새로 추가된 리포에만 워크플로우 PR 생성 |
| `deleted` | (선택) 알림 Issue 생성 |

**`handler.py`** — FastAPI 라우터
- `POST /webhook` 엔드포인트
- `X-GitHub-Event` 헤더로 이벤트 타입 분기
- 서명 검증 → 이벤트 핸들러 호출

---

### 4단계 — Audit Log 폴링 (`audit/`)

**`poller.py`** — Secret 변경 감지

```
APScheduler (5분마다)
      │
      ▼
등록된 Org 목록 순회
      │
      ▼
Audit Log API 호출
phrase: "action:org.update_secret"
      │
      ▼
APP_ID / APP_PRIVATE_KEY 변경 이벤트 확인
      │
      ├── 이미 처리한 이벤트 (document_id 기준) → 스킵
      │
      └── 신규 변경 감지
                │
                ├── Secret 자동 복구 시도
                │         ├── 성공 → 처리 완료 기록
                │         └── 실패 → notify/issue.py 호출
                │
                └── 처리 완료 기록 (메모리 or 파일)
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
- FastAPI 앱 초기화
- webhook 라우터 등록
- 서버 시작 시 APScheduler 시작
- 서버 종료 시 APScheduler 정리

**`.env.example`**
```dotenv
# GitHub App 설정
APP_ID=                          # GitHub App ID (숫자)
APP_PRIVATE_KEY=                 # GitHub App Private Key (PEM 전체 내용)
WEBHOOK_SECRET=                  # Webhook 서명 검증용 시크릿

# 알림 설정
NOTIFY_REPO=org/ops-repo         # 알림 Issue를 생성할 리포

# Audit Log 폴링 설정
AUDIT_POLL_INTERVAL_MINUTES=5    # 폴링 주기 (기본 5분)
```

**`README.md`**
- GitHub App 생성 방법
- 환경변수 설정 가이드
- 서버 실행 방법
- 워크플로우 파일 커스터마이징 방법

---

## 구현 시 주의사항

| 항목 | 내용 |
|------|------|
| **Secret 암호화** | GitHub API는 libsodium sealed box로 암호화된 값만 허용. PyNaCl 사용 필수 |
| **JWT 만료** | GitHub App JWT는 최대 10분 유효. 요청마다 새로 발급하거나 캐싱 필요 |
| **Webhook 서명 검증** | `X-Hub-Signature-256` 검증을 반드시 먼저 수행 |
| **중복 PR 방지** | 워크플로우 파일 또는 동일 브랜치가 이미 있으면 PR 생성 스킵 |
| **Audit Log 중복 처리** | `_document_id` 기준으로 처리 완료 여부 추적 |
| **Rate Limit** | Audit Log 폴링 주기가 너무 짧으면 API Rate Limit 초과 가능. 5분 권장 |
