from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    app_id: str = Field(..., description="GitHub App ID (숫자 문자열)")
    app_private_key: str = Field(..., description="GitHub App RSA 비밀키 (PEM 형식)")
    webhook_secret: str = Field(..., description="Webhook 서명 검증 시크릿")
    notify_repo: str = Field(..., description="알림 Issue를 생성할 리포 (org/repo)")
    github_api_url: str = Field(
        default="https://api.github.com",
        description="GitHub API 엔드포인트. GHES는 'https://{hostname}/api/v3' 형식",
    )
    log_file_name: str | None = Field(
        default=None,
        description="로그 파일명. 설정 시 logs/{log_file_name}에 저장. 미설정 시 콘솔만 출력",
    )
    log_rotation_when: str = Field(
        default="midnight",
        description="로그 로테이션 주기 (midnight, h, d, w0~w6). TimedRotatingFileHandler 기준",
    )
    log_rotation_backup_count: int = Field(
        default=30,
        ge=1,
        description="보관할 로테이션 파일 수",
    )
    audit_poll_interval_minutes: int = Field(
        default=5,
        ge=1,
        le=60,
        description="Audit Log 폴링 주기 (분)",
    )

    @field_validator("app_private_key")
    @classmethod
    def normalize_private_key(cls, v: str) -> str:
        """환경변수 파일에서 \n 리터럴로 저장된 PEM을 실제 개행으로 변환."""
        return v.replace("\\n", "\n")

    @field_validator("notify_repo")
    @classmethod
    def validate_notify_repo(cls, v: str) -> str:
        if "/" not in v or v.count("/") != 1:
            raise ValueError("notify_repo는 'org/repo' 형식이어야 합니다.")
        return v


_settings: Settings | None = None


def get_settings() -> Settings:
    """lazy singleton — import time에 평가하지 않아 테스트 격리 가능."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """테스트에서 설정을 리셋할 때 사용."""
    global _settings
    _settings = None
