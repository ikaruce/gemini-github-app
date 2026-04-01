from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from app.config import Settings

_LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# TimedRotatingFileHandler when 파라미터 허용값
_VALID_WHEN = {"s", "m", "h", "d", "midnight", "w0", "w1", "w2", "w3", "w4", "w5", "w6"}


def setup_logging(settings: Settings) -> None:
    """루트 로거에 콘솔 핸들러와 (설정 시) 파일 핸들러를 구성한다.

    - LOG_FILE_NAME 미설정: 콘솔 출력만
    - LOG_FILE_NAME 설정: 콘솔 + logs/{log_file_name} 파일 동시 출력
    - 파일은 LOG_ROTATION_WHEN 주기마다 로테이션, LOG_ROTATION_BACKUP_COUNT개 보관
    """
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # 중복 핸들러 방지 (uvicorn --reload 등에서 setup_logging이 재호출될 수 있음)
    if root.handlers:
        root.handlers.clear()

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # 콘솔 핸들러 (항상 추가)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    # 파일 핸들러 (LOG_FILE_NAME 설정 시)
    if settings.log_file_name:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)

        when = settings.log_rotation_when.lower()
        if when not in _VALID_WHEN:
            raise ValueError(
                f"log_rotation_when 값이 잘못되었습니다: '{when}'. "
                f"허용값: {sorted(_VALID_WHEN)}"
            )

        file_handler = logging.handlers.TimedRotatingFileHandler(
            filename=log_dir / settings.log_file_name,
            when=when,
            backupCount=settings.log_rotation_backup_count,
            encoding="utf-8",
            utc=True,  # UTC 기준 로테이션 (서버 시간대에 무관하게 일관성 유지)
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

        logging.getLogger(__name__).info(
            "파일 로깅 활성화: path=logs/%s, rotation=%s, backup=%d",
            settings.log_file_name,
            settings.log_rotation_when,
            settings.log_rotation_backup_count,
        )
