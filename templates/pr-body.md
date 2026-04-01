## Gemini CLI 워크플로우 추가

이 PR은 리포지토리에 Gemini CLI 자동화 워크플로우를 추가합니다.

### 추가되는 파일

| 파일 | 역할 |
|------|------|
| `gemini-dispatch.yml` | 이벤트 감지 및 라우팅 (중앙 허브) |
| `gemini-review.yml` | PR 자동 코드 리뷰 |
| `gemini-triage.yml` | Issue 자동 트리아지 및 레이블 적용 |
| `gemini-invoke.yml` | `@gemini-cli` 자유 형식 명령 처리 |

### 사전 조건

다음 Org 시크릿이 자동으로 등록되어 있습니다:
- `APP_ID` — Gemini GitHub App 식별자
- `APP_PRIVATE_KEY` — Gemini GitHub App 비밀키

### 사용 방법

이 PR을 머지하면 즉시 사용 가능합니다:

- **PR 자동 리뷰**: PR을 열거나 업데이트하면 자동으로 코드 리뷰 코멘트가 달립니다
- **Issue 자동 트리아지**: 새 Issue 생성 시 자동으로 레이블이 적용됩니다
- **자유 형식 명령**: PR 또는 Issue 댓글에 `@gemini-cli <질문이나 명령>` 입력

### 커스터마이징

워크플로우 동작을 변경하려면 `.github/workflows/` 디렉토리의 파일을 수정하세요.
