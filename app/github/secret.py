from __future__ import annotations

import base64

from nacl import encoding, public

from app.github.client import GITHUB_API_BASE, _github_request


async def get_org_public_key(
    org: str,
    token: str,
    api_url: str = GITHUB_API_BASE,
) -> tuple[str, str]:
    """Org Actions Public Key 조회.

    Returns:
        (key_id, key_b64) 튜플
    """
    result = await _github_request(
        "GET",
        f"/orgs/{org}/actions/secrets/public-key",
        token=token,
        api_url=api_url,
    )
    return result["key_id"], result["key"]


def encrypt_secret(public_key_b64: str, secret_value: str) -> str:
    """PyNaCl SealedBox(libsodium sealed box)로 시크릿 암호화.

    Args:
        public_key_b64: GitHub API에서 받은 base64 인코딩된 공개키
        secret_value: 암호화할 시크릿 값

    Returns:
        base64 인코딩된 암호화 값
    """
    pk = public.PublicKey(
        public_key_b64.encode("utf-8"),
        encoding.Base64Encoder(),
    )
    box = public.SealedBox(pk)
    encrypted = box.encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")


async def register_org_secret(
    org: str,
    secret_name: str,
    secret_value: str,
    token: str,
    api_url: str = GITHUB_API_BASE,
) -> None:
    """Org Actions Secret 등록/업데이트.

    PUT /orgs/{org}/actions/secrets/{secret_name}
    """
    key_id, key_b64 = await get_org_public_key(org, token, api_url=api_url)
    encrypted_value = encrypt_secret(key_b64, secret_value)

    await _github_request(
        "PUT",
        f"/orgs/{org}/actions/secrets/{secret_name}",
        token=token,
        json={
            "encrypted_value": encrypted_value,
            "key_id": key_id,
            "visibility": "all",
        },
        api_url=api_url,
    )


async def register_app_secrets(
    org: str,
    app_id: str,
    private_key_pem: str,
    token: str,
    api_url: str = GITHUB_API_BASE,
) -> None:
    """APP_ID와 APP_PRIVATE_KEY를 Org Secret으로 일괄 등록."""
    await register_org_secret(org, "APP_ID", app_id, token, api_url=api_url)
    await register_org_secret(org, "APP_PRIVATE_KEY", private_key_pem, token, api_url=api_url)
