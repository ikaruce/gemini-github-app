from __future__ import annotations

import base64
import logging
from pathlib import Path

import httpx

from app.github.client import GITHUB_API_BASE, _github_request
from app.github.repo import get_branch_sha, get_file_sha, pr_exists_for_branch

logger = logging.getLogger(__name__)

WORKFLOW_BRANCH = "add-gemini-cli-workflows"
WORKFLOW_FILES = [
    "gemini-dispatch.yml",
    "gemini-review.yml",
    "gemini-triage.yml",
    "gemini-invoke.yml",
]
WORKFLOWS_PATH = ".github/workflows"


async def create_branch(
    owner: str,
    repo: str,
    branch: str,
    sha: str,
    token: str,
    api_url: str = GITHUB_API_BASE,
) -> None:
    """새 브랜치 생성.

    POST /repos/{owner}/{repo}/git/refs (복수 refs)
    422(브랜치 이미 존재) 시 무시.
    """
    try:
        await _github_request(
            "POST",
            f"/repos/{owner}/{repo}/git/refs",
            token=token,
            json={"ref": f"refs/heads/{branch}", "sha": sha},
            api_url=api_url,
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 422:
            logger.info("%s/%s: 브랜치 %s 이미 존재, 계속 진행", owner, repo, branch)
        else:
            raise


async def commit_file(
    owner: str,
    repo: str,
    branch: str,
    path: str,
    content: str,
    token: str,
    api_url: str = GITHUB_API_BASE,
) -> None:
    """파일 커밋 (신규 생성 또는 업데이트).

    PUT /repos/{owner}/{repo}/contents/{path}
    파일이 이미 존재하면 기존 SHA를 포함해 업데이트.
    """
    content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    body: dict = {
        "message": f"chore: add {path.split('/')[-1]}",
        "content": content_b64,
        "branch": branch,
    }

    existing_sha = await get_file_sha(owner, repo, path, branch, token, api_url=api_url)
    if existing_sha:
        body["sha"] = existing_sha

    await _github_request(
        "PUT",
        f"/repos/{owner}/{repo}/contents/{path}",
        token=token,
        json=body,
        api_url=api_url,
    )


async def create_pr(
    owner: str,
    repo: str,
    head: str,
    base: str,
    title: str,
    body: str,
    token: str,
    api_url: str = GITHUB_API_BASE,
) -> int:
    """Pull Request 생성.

    Returns:
        생성된 PR 번호
    """
    result = await _github_request(
        "POST",
        f"/repos/{owner}/{repo}/pulls",
        token=token,
        json={"title": title, "head": head, "base": base, "body": body},
        api_url=api_url,
    )
    return result["number"]


async def deploy_workflows_to_repo(
    owner: str,
    repo: str,
    default_branch: str,
    token: str,
    templates_dir: Path,
    api_url: str = GITHUB_API_BASE,
) -> None:
    """단일 리포에 Gemini CLI 워크플로우 배포.

    순서:
    1. 열린 PR 존재 → 스킵
    2. 브랜치 생성
    3. 워크플로우 파일 4개 커밋
    4. PR 생성
    """
    if await pr_exists_for_branch(owner, repo, WORKFLOW_BRANCH, token, api_url=api_url):
        logger.info("%s/%s: PR 이미 존재, 스킵", owner, repo)
        return

    sha = await get_branch_sha(owner, repo, default_branch, token, api_url=api_url)
    await create_branch(owner, repo, WORKFLOW_BRANCH, sha, token, api_url=api_url)

    pr_body = _load_pr_body(templates_dir)

    for filename in WORKFLOW_FILES:
        file_path = f"{WORKFLOWS_PATH}/{filename}"
        content = _load_template(templates_dir, filename)
        await commit_file(owner, repo, WORKFLOW_BRANCH, file_path, content, token, api_url=api_url)
        logger.info("%s/%s: %s 커밋 완료", owner, repo, filename)

    pr_number = await create_pr(
        owner=owner,
        repo=repo,
        head=WORKFLOW_BRANCH,
        base=default_branch,
        title="chore: Gemini CLI 워크플로우 추가",
        body=pr_body,
        token=token,
        api_url=api_url,
    )
    logger.info("%s/%s: PR #%d 생성 완료", owner, repo, pr_number)


def _load_template(templates_dir: Path, filename: str) -> str:
    """템플릿 파일 텍스트 로드."""
    return (templates_dir / filename).read_text(encoding="utf-8")


def _load_pr_body(templates_dir: Path) -> str:
    """PR 본문 템플릿 로드."""
    pr_body_path = templates_dir / "pr-body.md"
    if pr_body_path.exists():
        return pr_body_path.read_text(encoding="utf-8")
    return "Gemini CLI 워크플로우를 추가합니다."
