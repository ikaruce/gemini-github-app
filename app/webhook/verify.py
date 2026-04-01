from __future__ import annotations

import hashlib
import hmac

from fastapi import HTTPException


def verify_signature(
    payload_body: bytes,
    secret: str,
    signature_header: str | None,
) -> None:
    """X-Hub-Signature-256 헤더 HMAC 검증.

    Args:
        payload_body: raw request body bytes (JSON 파싱 전)
        secret: webhook secret
        signature_header: X-Hub-Signature-256 헤더 값

    Raises:
        HTTPException(403): 서명 누락 또는 불일치
    """
    if not signature_header:
        raise HTTPException(
            status_code=403,
            detail="Missing X-Hub-Signature-256 header",
        )

    mac = hmac.new(
        secret.encode("utf-8"),
        msg=payload_body,
        digestmod=hashlib.sha256,
    )
    expected = f"sha256={mac.hexdigest()}"

    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(
            status_code=403,
            detail="Request signature mismatch",
        )
