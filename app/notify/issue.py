from __future__ import annotations

import logging

from app.github.client import GITHUB_API_BASE, _github_request

logger = logging.getLogger(__name__)


async def create_issue(
    repo: str,
    title: str,
    body: str,
    token: str,
    labels: list[str] | None = None,
    api_url: str = GITHUB_API_BASE,
) -> int:
    """GitHub Issue 생성.

    Args:
        repo: "org/repo-name" 형식
        title: Issue 제목
        body: Issue 본문 (Markdown)
        token: Installation Access Token
        labels: 적용할 레이블 목록 (없으면 생략)
        api_url: GitHub API 엔드포인트 (GHES 지원)

    Returns:
        생성된 Issue 번호
    """
    owner, repo_name = repo.split("/", 1)

    payload: dict = {"title": title, "body": body}
    if labels:
        payload["labels"] = labels

    result = await _github_request(
        "POST",
        f"/repos/{owner}/{repo_name}/issues",
        token=token,
        json=payload,
        api_url=api_url,
    )
    issue_number: int = result["number"]
    logger.info("Issue #%d 생성: %s/%s", issue_number, owner, repo_name)
    return issue_number
