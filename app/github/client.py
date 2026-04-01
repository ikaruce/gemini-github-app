from __future__ import annotations

import time
from typing import Any

import httpx
import jwt


GITHUB_API_BASE = "https://api.github.com"
_GITHUB_API_VERSION = "2022-11-28"


def build_jwt(app_id: str, private_key_pem: str) -> str:
    """GitHub App RS256 JWT 생성 (유효기간 9분, 클럭 드리프트 60초 대응)."""
    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + 540,
        "iss": app_id,
    }
    return jwt.encode(payload, private_key_pem, algorithm="RS256")


async def get_installation_token(
    installation_id: int,
    app_id: str,
    private_key_pem: str,
    api_url: str = GITHUB_API_BASE,
) -> str:
    """Installation Access Token 발급.

    POST /app/installations/{installation_id}/access_tokens
    """
    app_jwt = build_jwt(app_id, private_key_pem)
    result = await _github_request(
        "POST",
        f"/app/installations/{installation_id}/access_tokens",
        token=app_jwt,
        token_type="Bearer",
        api_url=api_url,
    )
    return result["token"]


async def get_installation_id_for_org(
    org: str,
    app_id: str,
    private_key_pem: str,
    api_url: str = GITHUB_API_BASE,
) -> int | None:
    """Org 이름으로 Installation ID 조회 (페이지네이션 지원).

    GET /app/installations
    """
    app_jwt = build_jwt(app_id, private_key_pem)
    url = "/app/installations"
    params: dict[str, Any] = {"per_page": 100}

    while url:
        response = await _github_request_raw(
            "GET",
            url,
            token=app_jwt,
            token_type="Bearer",
            params=params,
            api_url=api_url,
        )
        installations = response.json()
        for inst in installations:
            account = inst.get("account", {})
            if (
                account.get("type") == "Organization"
                and account.get("login", "").lower() == org.lower()
            ):
                return inst["id"]

        url = _next_page_url(response)
        params = {}  # next URL에는 이미 파라미터 포함

    return None


async def _github_request(
    method: str,
    path: str,
    token: str,
    token_type: str = "token",
    json: dict | None = None,
    params: dict | None = None,
    api_url: str = GITHUB_API_BASE,
) -> dict:
    """GitHub API 요청 (JSON 응답 반환)."""
    response = await _github_request_raw(
        method, path, token, token_type, json=json, params=params, api_url=api_url
    )
    if response.status_code == 204:
        return {}
    return response.json()


async def _github_request_raw(
    method: str,
    path: str,
    token: str,
    token_type: str = "token",
    json: dict | None = None,
    params: dict | None = None,
    api_url: str = GITHUB_API_BASE,
) -> httpx.Response:
    """GitHub API 요청 (raw Response 반환 — 페이지네이션 Link 헤더 접근용)."""
    headers = {
        "Authorization": f"{token_type} {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": _GITHUB_API_VERSION,
    }
    # path가 절대 URL(Link 헤더 next)이면 api_url 무시
    if path.startswith("http"):
        base = ""
        url = path
    else:
        base = api_url
        url = path

    async with httpx.AsyncClient(base_url=base) as client:
        response = await client.request(
            method, url, headers=headers, json=json, params=params
        )
        response.raise_for_status()
        return response


def _next_page_url(response: httpx.Response) -> str | None:
    """Link 헤더에서 next 페이지 URL 추출."""
    link_header = response.headers.get("link", "")
    for part in link_header.split(","):
        part = part.strip()
        if 'rel="next"' in part:
            url_part = part.split(";")[0].strip()
            return url_part.strip("<>")
    return None
