from __future__ import annotations

import os

import pytest

from app.config import Settings, reset_settings


@pytest.fixture(autouse=True)
def reset_settings_between_tests():
    """각 테스트 후 설정 싱글톤 리셋."""
    yield
    reset_settings()


@pytest.fixture
def mock_settings() -> Settings:
    return Settings(
        app_id="123456",
        app_private_key="-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA\n-----END RSA PRIVATE KEY-----",
        webhook_secret="test-webhook-secret",
        notify_repo="test-org/ops-repo",
        audit_poll_interval_minutes=5,
    )
