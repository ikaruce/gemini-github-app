from __future__ import annotations

import httpx

from app.github.client import GITHUB_API_BASE, _github_request, _github_request_raw, _next_page_url


async def list_org_repos(
    org: str,
    token: str,
    api_url: str = GITHUB_API_BASE,
) -> list[dict]:
    """Org 내 모든 리포 목록 조회 (archived, fork 제외).

    GET /orgs/{org}/repos?type=all&per_page=100
    """
    repos: list[dict] = []
    url = f"/orgs/{org}/repos"
    params: dict = {"type": "all", "per_page": 100}

    while url:
        response = await _github_request_raw(
            "GET", url, token=token, params=params, api_url=api_url
        )
        for repo in response.json():
            if not repo.get("archived") and not repo.get("fork"):
                repos.append(repo)
        url = _next_page_url(response)
        params = {}

    return repos


async def get_branch_sha(
    owner: str,
    repo: str,
    branch: str,
    token: str,
    api_url: str = GITHUB_API_BASE,
) -> str:
    """브랜치의 최신 커밋 SHA 조회.

    GET /repos/{owner}/{repo}/git/ref/heads/{branch}
    주의: GET은 단수 ref/, POST는 복수 refs/
    """
    result = await _github_request(
        "GET",
        f"/repos/{owner}/{repo}/git/ref/heads/{branch}",
        token=token,
        api_url=api_url,
    )
    return result["object"]["sha"]


async def file_exists(
    owner: str,
    repo: str,
    path: str,
    branch: str,
    token: str,
    api_url: str = GITHUB_API_BASE,
) -> bool:
    """특정 브랜치에 파일 존재 여부 확인.

    HEAD /repos/{owner}/{repo}/contents/{path}?ref={branch}
    """
    try:
        await _github_request_raw(
            "HEAD",
            f"/repos/{owner}/{repo}/contents/{path}",
            token=token,
            params={"ref": branch},
            api_url=api_url,
        )
        return True
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return False
        raise


async def get_file_sha(
    owner: str,
    repo: str,
    path: str,
    branch: str,
    token: str,
    api_url: str = GITHUB_API_BASE,
) -> str | None:
    """파일의 blob SHA 조회 (파일 업데이트 시 필요).

    GET /repos/{owner}/{repo}/contents/{path}?ref={branch}
    파일 없으면 None 반환.
    """
    try:
        result = await _github_request(
            "GET",
            f"/repos/{owner}/{repo}/contents/{path}",
            token=token,
            params={"ref": branch},
            api_url=api_url,
        )
        return result.get("sha")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return None
        raise


async def pr_exists_for_branch(
    owner: str,
    repo: str,
    head_branch: str,
    token: str,
    api_url: str = GITHUB_API_BASE,
) -> bool:
    """특정 헤드 브랜치에 대한 열린 PR 존재 여부 확인.

    GET /repos/{owner}/{repo}/pulls?head={owner}:{head_branch}&state=open
    """
    result = await _github_request(
        "GET",
        f"/repos/{owner}/{repo}/pulls",
        token=token,
        params={"head": f"{owner}:{head_branch}", "state": "open"},
        api_url=api_url,
    )
    return len(result) > 0
