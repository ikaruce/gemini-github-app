from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.config import Settings
from app.github.client import get_installation_id_for_org, get_installation_token
from app.github.repo import list_org_repos
from app.github.secret import register_app_secrets
from app.github.workflow import deploy_workflows_to_repo

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"
_DEPLOY_CONCURRENCY = 10  # 동시 배포 리포 수 제한


async def handle_installation_created(
    payload: dict,
    settings: Settings,
) -> None:
    """installation.created 이벤트 처리.

    1. Org Secret 등록 (APP_ID, APP_PRIVATE_KEY)
    2. 모든 리포에 워크플로우 PR 생성
    """
    installation_id: int = payload["installation"]["id"]
    org: str = payload["installation"]["account"]["login"]
    api_url = settings.github_api_url

    logger.info("installation.created: org=%s installation_id=%d", org, installation_id)

    token = await get_installation_token(
        installation_id, settings.app_id, settings.app_private_key, api_url=api_url
    )

    await register_app_secrets(org, settings.app_id, settings.app_private_key, token, api_url=api_url)
    logger.info("Org secret 등록 완료: org=%s", org)

    repos = await list_org_repos(org, token, api_url=api_url)
    logger.info("%d개 리포에 워크플로우 배포 시작: org=%s", len(repos), org)

    await _deploy_to_repos(org, repos, token, settings)


async def handle_installation_added(
    payload: dict,
    settings: Settings,
) -> None:
    """installation.added 이벤트 처리 (리포 추가).

    payload의 repositories 배열에 있는 리포만 배포.
    """
    installation_id: int = payload["installation"]["id"]
    org: str = payload["installation"]["account"]["login"]
    repositories: list[dict] = payload.get("repositories", [])
    api_url = settings.github_api_url

    logger.info(
        "installation.added: org=%s repos=%d",
        org,
        len(repositories),
    )

    token = await get_installation_token(
        installation_id, settings.app_id, settings.app_private_key, api_url=api_url
    )

    # webhook payload의 repositories는 full_name만 포함 → default_branch 조회 필요
    # list_org_repos로 전체 메타데이터 가져오기
    all_repos = await list_org_repos(org, token, api_url=api_url)
    added_names = {r["name"].lower() for r in repositories}
    target_repos = [r for r in all_repos if r["name"].lower() in added_names]

    await _deploy_to_repos(org, target_repos, token, settings)


async def handle_installation_deleted(
    payload: dict,
    settings: Settings,
) -> None:
    """installation.deleted 이벤트 처리.

    NOTIFY_REPO에 알림 Issue 생성.
    """
    from app.notify.issue import create_issue

    org: str = payload["installation"]["account"]["login"]
    api_url = settings.github_api_url
    logger.info("installation.deleted: org=%s", org)

    # notify_repo의 installation token 발급
    notify_org = settings.notify_repo.split("/")[0]
    notify_installation_id = await get_installation_id_for_org(
        notify_org, settings.app_id, settings.app_private_key, api_url=api_url
    )
    if notify_installation_id is None:
        logger.error("notify_org %s의 installation을 찾을 수 없음", notify_org)
        return

    notify_token = await get_installation_token(
        notify_installation_id, settings.app_id, settings.app_private_key, api_url=api_url
    )

    await create_issue(
        repo=settings.notify_repo,
        title=f"[{org}] Gemini CLI App이 제거되었습니다",
        body=f"Org **{org}** 에서 Gemini CLI GitHub App이 제거되었습니다.\n\n재설치가 필요하면 App을 다시 설치해 주세요.",
        token=notify_token,
        labels=["gemini-cli", "app-removed"],
        api_url=api_url,
    )


async def _deploy_to_repos(
    org: str,
    repos: list[dict],
    token: str,
    settings: Settings,
) -> None:
    """여러 리포에 동시 워크플로우 배포 (Semaphore로 동시성 제한)."""
    semaphore = asyncio.Semaphore(_DEPLOY_CONCURRENCY)
    api_url = settings.github_api_url

    async def deploy_one(repo: dict) -> None:
        async with semaphore:
            try:
                await deploy_workflows_to_repo(
                    owner=org,
                    repo=repo["name"],
                    default_branch=repo.get("default_branch", "main"),
                    token=token,
                    templates_dir=TEMPLATES_DIR,
                    workflows_repo=settings.workflows_repo,
                    bot_name=settings.bot_name,
                    api_url=api_url,
                )
            except Exception:
                logger.exception("워크플로우 배포 실패: %s/%s", org, repo["name"])

    tasks = [deploy_one(repo) for repo in repos]
    await asyncio.gather(*tasks, return_exceptions=True)
