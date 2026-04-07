from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings

_BASE = dict(
    app_id="1",
    app_private_key="key",
    webhook_secret="secret",
    notify_repo="org/repo",
    workflows_repo="org/gemini-workflows",
    bot_name="gemini-cli",
)


def test_default_github_api_url():
    """github_api_url 미설정 시 GitHub.com 기본값 사용."""
    s = Settings(**_BASE)
    assert s.github_api_url == "https://api.github.com"


def test_ghes_api_url_override():
    """GHES URL 설정이 올바르게 저장되는지 확인."""
    s = Settings(**_BASE, github_api_url="https://github.example.com/api/v3")
    assert s.github_api_url == "https://github.example.com/api/v3"


def test_private_key_newline_normalization():
    """.env에서 \\n 리터럴로 저장된 PEM을 실제 개행으로 변환."""
    s = Settings(
        **{**_BASE, "app_private_key": "-----BEGIN RSA PRIVATE KEY-----\\nMIIE\\n-----END RSA PRIVATE KEY-----"},
    )
    assert "\n" in s.app_private_key
    assert "\\n" not in s.app_private_key


def test_invalid_notify_repo_format():
    """notify_repo가 'org/repo' 형식이 아니면 ValidationError."""
    with pytest.raises(ValidationError):
        Settings(**{**_BASE, "notify_repo": "invalid-no-slash"})


def test_invalid_workflows_repo_format():
    """workflows_repo가 'org/repo' 형식이 아니면 ValidationError."""
    with pytest.raises(ValidationError):
        Settings(**{**_BASE, "workflows_repo": "invalid-no-slash"})


def test_audit_poll_interval_bounds():
    """audit_poll_interval_minutes는 1~60 범위여야 함."""
    with pytest.raises(ValidationError):
        Settings(**_BASE, audit_poll_interval_minutes=0)
    with pytest.raises(ValidationError):
        Settings(**_BASE, audit_poll_interval_minutes=61)
