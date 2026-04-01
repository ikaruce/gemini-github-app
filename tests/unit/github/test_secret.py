from __future__ import annotations

import base64

import pytest
from nacl.public import PrivateKey
from nacl import encoding

from app.github.secret import encrypt_secret


def _generate_test_keypair() -> tuple[str, PrivateKey]:
    """테스트용 키쌍 생성. (public_key_b64, private_key)"""
    private_key = PrivateKey.generate()
    pub_b64 = base64.b64encode(bytes(private_key.public_key)).decode("utf-8")
    return pub_b64, private_key


def test_encrypt_secret_returns_base64_string():
    pub_b64, _ = _generate_test_keypair()
    result = encrypt_secret(pub_b64, "my-secret-value")
    assert isinstance(result, str)
    # 유효한 base64인지 확인
    decoded = base64.b64decode(result)
    assert len(decoded) > 0


def test_encrypt_secret_produces_different_output_each_time():
    """SealedBox는 nonce를 사용하므로 같은 입력에도 결과가 달라야 함."""
    pub_b64, _ = _generate_test_keypair()
    result1 = encrypt_secret(pub_b64, "same-value")
    result2 = encrypt_secret(pub_b64, "same-value")
    assert result1 != result2


def test_encrypt_secret_can_be_decrypted():
    """암호화된 값을 비밀키로 복호화할 수 있어야 함."""
    from nacl.public import SealedBox

    pub_b64, private_key = _generate_test_keypair()
    secret_value = "super-secret-api-key"

    encrypted_b64 = encrypt_secret(pub_b64, secret_value)
    encrypted_bytes = base64.b64decode(encrypted_b64)

    box = SealedBox(private_key)
    decrypted = box.decrypt(encrypted_bytes).decode("utf-8")
    assert decrypted == secret_value


def test_encrypt_secret_handles_multiline_pem():
    """PEM 키처럼 개행이 포함된 값도 올바르게 암호화."""
    pub_b64, private_key = _generate_test_keypair()
    from nacl.public import SealedBox

    pem_value = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----"
    encrypted_b64 = encrypt_secret(pub_b64, pem_value)
    encrypted_bytes = base64.b64decode(encrypted_b64)

    box = SealedBox(private_key)
    decrypted = box.decrypt(encrypted_bytes).decode("utf-8")
    assert decrypted == pem_value
