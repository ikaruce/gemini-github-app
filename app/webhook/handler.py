from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Header, Request

from app.config import get_settings
from app.webhook.installation import (
    handle_installation_added,
    handle_installation_created,
    handle_installation_deleted,
)
from app.webhook.verify import verify_signature

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/webhook")
async def webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(None),
    x_github_event: str | None = Header(None),
) -> dict:
    """GitHub Webhook 수신 엔드포인트.

    1. raw body 읽기 (스트림 소비 전 서명 검증에 사용)
    2. HMAC 서명 검증
    3. 이벤트 타입별 핸들러 호출
    """
    body = await request.body()
    settings = get_settings()

    verify_signature(body, settings.webhook_secret, x_hub_signature_256)

    payload = json.loads(body)
    logger.info("webhook 수신: event=%s", x_github_event)

    if x_github_event == "installation":
        action = payload.get("action")
        if action == "created":
            await handle_installation_created(payload, settings)
        elif action == "added":
            await handle_installation_added(payload, settings)
        elif action == "deleted":
            await handle_installation_deleted(payload, settings)
        else:
            logger.debug("처리하지 않는 installation action: %s", action)
    else:
        logger.debug("처리하지 않는 GitHub event: %s", x_github_event)

    return {"status": "ok"}
