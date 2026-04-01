from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from app.audit.poller import poll_all_orgs
from app.config import get_settings
from app.logging_config import setup_logging
from app.webhook.handler import router as webhook_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """APScheduler 시작/종료 생명주기 관리."""
    settings = get_settings()
    setup_logging(settings)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        poll_all_orgs,
        trigger="interval",
        minutes=settings.audit_poll_interval_minutes,
        args=[settings],
        max_instances=1,   # 이전 실행이 완료되기 전 중복 실행 방지
        coalesce=True,     # 서버 다운 중 missed 실행은 재시작 후 1회만 실행
        id="audit_poller",
    )
    scheduler.start()
    logger.info(
        "APScheduler 시작: 폴링 주기=%d분",
        settings.audit_poll_interval_minutes,
    )

    yield

    scheduler.shutdown(wait=False)
    logger.info("APScheduler 종료")


app = FastAPI(
    title="gemini-github-app",
    description="GitHub Org에 Gemini CLI 워크플로우를 자동 배포하는 백엔드 서버",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(webhook_router)


@app.get("/health")
async def health() -> dict:
    """서버 상태 확인."""
    return {"status": "ok"}
