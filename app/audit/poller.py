from __future__ import annotations

import logging

from app.config import Settings
from app.github.client import (
    _github_request_raw,
    _next_page_url,
    get_installation_id_for_org,
    get_installation_token,
)
from app.github.secret import register_app_secrets
from app.notify.issue import create_issue

logger = logging.getLogger(__name__)

# 처리 완료된 audit log document_id 집합 (메모리 내 중복 방지)
_processed_doc_ids: set[str] = set()
_MAX_DOC_IDS = 10_000
_TRIM_TARGET = 5_000

# 추적 중인 Org → installation_id 매핑
_tracked_orgs: dict[str, int] = {}


def register_org(org: str, installation_id: int) -> None:
    """Audit Log 폴링 대상 Org 등록 (installation.created 시 호출)."""
    _tracked_orgs[org] = installation_id
    logger.info("Audit Log 폴링 등록: org=%s", org)


def unregister_org(org: str) -> None:
    """Org 폴링 해제 (installation.deleted 시 호출)."""
    _tracked_orgs.pop(org, None)
    logger.info("Audit Log 폴링 해제: org=%s", org)


async def poll_all_orgs(settings: Settings) -> None:
    """등록된 모든 Org의 Audit Log를 폴링 (APScheduler에서 주기적 호출)."""
    if not _tracked_orgs:
        logger.debug("폴링할 Org 없음")
        return

    for org, installation_id in list(_tracked_orgs.items()):
        try:
            await poll_org_audit_log(org, installation_id, settings)
        except Exception:
            logger.exception("Audit Log 폴링 실패: org=%s", org)


async def poll_org_audit_log(
    org: str,
    installation_id: int,
    settings: Settings,
) -> None:
    """단일 Org Audit Log 폴링 및 Secret 변경 감지.

    GET /orgs/{org}/audit-log?phrase=action:org.update_secret&include=all
    403 응답(비 GHEC Org) 시 경고 로그 후 스킵.
    """
    api_url = settings.github_api_url
    token = await get_installation_token(
        installation_id, settings.app_id, settings.app_private_key, api_url=api_url
    )

    url = f"/orgs/{org}/audit-log"
    params: dict = {
        "phrase": "action:org.update_secret",
        "include": "all",
        "per_page": 100,
        "order": "desc",
    }

    entries: list[dict] = []
    current_url: str | None = url

    while current_url:
        try:
            response = await _github_request_raw(
                "GET",
                current_url,
                token=token,
                params=params if current_url == url else {},
                api_url=api_url,
            )
        except Exception as e:
            # 403 = GHEC 미사용 Org (Audit Log API 미지원)
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status == 403:
                logger.warning("Audit Log API 미지원 Org (GHEC 필요): org=%s", org)
                return
            raise

        entries.extend(response.json())
        current_url = _next_page_url(response)

    await _process_audit_entries(org, entries, installation_id, settings)


async def _process_audit_entries(
    org: str,
    entries: list[dict],
    installation_id: int,
    settings: Settings,
) -> None:
    """Audit Log 항목에서 APP_ID/APP_PRIVATE_KEY 변경 감지 및 처리."""
    for entry in entries:
        doc_id = entry.get("_document_id")
        if not doc_id or doc_id in _processed_doc_ids:
            continue

        secret_name = (
            entry.get("data", {}).get("name")
            or entry.get("name", "")
        )

        if secret_name in ("APP_ID", "APP_PRIVATE_KEY"):
            logger.warning(
                "Secret 변경 감지: org=%s secret=%s doc_id=%s",
                org, secret_name, doc_id,
            )
            await _handle_secret_change(org, secret_name, installation_id, settings)

        _mark_processed(doc_id)


async def _handle_secret_change(
    org: str,
    secret_name: str,
    installation_id: int,
    settings: Settings,
) -> None:
    """Secret 변경 감지 후 자동 복구 시도. 실패 시 Issue 알림."""
    api_url = settings.github_api_url
    try:
        token = await get_installation_token(
            installation_id, settings.app_id, settings.app_private_key, api_url=api_url
        )
        await register_app_secrets(
            org, settings.app_id, settings.app_private_key, token, api_url=api_url
        )
        logger.info("Secret 자동 복구 성공: org=%s secret=%s", org, secret_name)
    except Exception as recovery_error:
        logger.error(
            "Secret 자동 복구 실패: org=%s secret=%s error=%s",
            org, secret_name, recovery_error,
        )
        await _notify_recovery_failure(org, secret_name, recovery_error, settings)


async def _notify_recovery_failure(
    org: str,
    secret_name: str,
    error: Exception,
    settings: Settings,
) -> None:
    """복구 실패 시 NOTIFY_REPO에 Issue 생성."""
    api_url = settings.github_api_url
    try:
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
            title=f"[{org}] Secret 복구 실패 — 수동 확인 필요: {secret_name}",
            body=(
                f"Org **{org}** 의 `{secret_name}` Secret 자동 복구에 실패했습니다.\n\n"
                f"**오류:**\n```\n{error}\n```\n\n"
                "수동으로 Secret을 재등록해 주세요."
            ),
            token=notify_token,
            labels=["gemini-cli", "secret-recovery-failed"],
            api_url=api_url,
        )
    except Exception:
        logger.exception("복구 실패 알림 Issue 생성 실패: org=%s", org)


def _mark_processed(doc_id: str) -> None:
    """처리된 document_id 기록. 집합이 과도하게 커지면 절반 정리."""
    _processed_doc_ids.add(doc_id)
    if len(_processed_doc_ids) > _MAX_DOC_IDS:
        # 오래된 항목 정리 (set이므로 임의 항목 제거)
        to_remove = list(_processed_doc_ids)[:_TRIM_TARGET]
        for item in to_remove:
            _processed_doc_ids.discard(item)
