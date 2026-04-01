from __future__ import annotations

import time

import pytest

from app.github.client import _next_page_url, build_jwt


def test_build_jwt_structure():
    """JWT가 올바른 구조로 생성되는지 확인 (RS256, iss, iat, exp)."""
    import jwt as pyjwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization

    # 테스트용 RSA 키쌍 생성
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    pub_key = private_key.public_key()

    token = build_jwt("123456", pem)

    decoded = pyjwt.decode(token, pub_key, algorithms=["RS256"])
    assert decoded["iss"] == "123456"
    assert "iat" in decoded
    assert "exp" in decoded


def test_build_jwt_expiry_within_10_minutes():
    """JWT exp가 현재로부터 10분 이내여야 함."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization
    import jwt as pyjwt

    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    token = build_jwt("app-id", pem)
    pub_key = private_key.public_key()
    decoded = pyjwt.decode(token, pub_key, algorithms=["RS256"])

    now = int(time.time())
    assert decoded["exp"] <= now + 600  # 10분 이내
    assert decoded["exp"] > now  # 이미 만료되지 않음


def test_next_page_url_extracts_url():
    mock_response = type("R", (), {
        "headers": {"link": '<https://api.github.com/repos?page=2>; rel="next", <https://api.github.com/repos?page=5>; rel="last"'}
    })()
    url = _next_page_url(mock_response)
    assert url == "https://api.github.com/repos?page=2"


def test_next_page_url_returns_none_when_no_next():
    mock_response = type("R", (), {
        "headers": {"link": '<https://api.github.com/repos?page=1>; rel="prev"'}
    })()
    assert _next_page_url(mock_response) is None


def test_next_page_url_returns_none_when_no_link_header():
    mock_response = type("R", (), {"headers": {}})()
    assert _next_page_url(mock_response) is None
