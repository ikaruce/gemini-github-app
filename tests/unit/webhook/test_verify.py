from __future__ import annotations

import hashlib
import hmac

import pytest
from fastapi import HTTPException

from app.webhook.verify import verify_signature


def _make_sig(body: bytes, secret: str) -> str:
    mac = hmac.new(secret.encode("utf-8"), msg=body, digestmod=hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


def test_valid_signature_passes():
    body = b'{"action": "created"}'
    secret = "webhook-secret"
    sig = _make_sig(body, secret)
    verify_signature(body, secret, sig)  # 예외 없어야 함


def test_missing_signature_raises_403():
    with pytest.raises(HTTPException) as exc_info:
        verify_signature(b"body", "secret", None)
    assert exc_info.value.status_code == 403
    assert "Missing" in exc_info.value.detail


def test_invalid_signature_raises_403():
    with pytest.raises(HTTPException) as exc_info:
        verify_signature(b"body", "secret", "sha256=invalidhexvalue")
    assert exc_info.value.status_code == 403


def test_wrong_secret_raises_403():
    body = b'{"test": true}'
    sig = _make_sig(body, "correct-secret")
    with pytest.raises(HTTPException) as exc_info:
        verify_signature(body, "wrong-secret", sig)
    assert exc_info.value.status_code == 403


def test_empty_body_with_valid_sig_passes():
    body = b""
    secret = "secret"
    sig = _make_sig(body, secret)
    verify_signature(body, secret, sig)


def test_malformed_signature_format_raises_403():
    """sha256= 접두사 없는 서명도 거부."""
    body = b"body"
    secret = "secret"
    mac = hmac.new(secret.encode(), msg=body, digestmod=hashlib.sha256)
    # 접두사 없이 hex만 전달
    with pytest.raises(HTTPException) as exc_info:
        verify_signature(body, secret, mac.hexdigest())
    assert exc_info.value.status_code == 403
