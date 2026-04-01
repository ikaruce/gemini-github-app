# 1. Base image 설정 (Python 3.12 slim 버전 사용)
FROM python:3.12-slim-bookworm

# 2. 작업 디렉토리 설정
WORKDIR /app

# 3. 환경 변수 설정
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_PROJECT_ENVIRONMENT=/app/.venv

# 4. uv 설치
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 5. 의존성 파일 복사 및 설치
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 6. 소스 코드 및 템플릿 복사
COPY app/ ./app/
COPY templates/ ./templates/

# 7. PATH 설정
ENV PATH="/app/.venv/bin:$PATH"

# 8. 포트 노출
EXPOSE 8000

# 9. 실행 명령
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
