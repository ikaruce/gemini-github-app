from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

import pytest

from app.config import Settings
from app.logging_config import setup_logging


def _make_settings(**kwargs) -> Settings:
    defaults = dict(
        app_id="1",
        app_private_key="key",
        webhook_secret="secret",
        notify_repo="org/repo",
    )
    defaults.update(kwargs)
    return Settings(**defaults)


@pytest.fixture(autouse=True)
def reset_root_logger():
    """각 테스트 후 루트 로거 핸들러 초기화."""
    yield
    root = logging.getLogger()
    for h in root.handlers[:]:
        h.close()
        root.removeHandler(h)


def test_console_only_when_no_log_file_name():
    """log_file_name 미설정 시 StreamHandler만 추가된다."""
    settings = _make_settings()
    setup_logging(settings)

    root = logging.getLogger()
    handler_types = [type(h) for h in root.handlers]
    assert logging.StreamHandler in handler_types
    assert logging.handlers.TimedRotatingFileHandler not in handler_types


def test_file_handler_added_when_log_file_name_set(tmp_path, monkeypatch):
    """log_file_name 설정 시 TimedRotatingFileHandler가 추가된다."""
    monkeypatch.chdir(tmp_path)
    settings = _make_settings(log_file_name="app.log")
    setup_logging(settings)

    root = logging.getLogger()
    handler_types = [type(h) for h in root.handlers]
    assert logging.StreamHandler in handler_types
    assert logging.handlers.TimedRotatingFileHandler in handler_types


def test_log_file_created_in_logs_dir(tmp_path, monkeypatch):
    """로그 파일이 logs/ 디렉터리에 생성된다."""
    monkeypatch.chdir(tmp_path)
    settings = _make_settings(log_file_name="app.log")
    setup_logging(settings)

    assert (tmp_path / "logs" / "app.log").exists()


def test_file_handler_rotation_settings(tmp_path, monkeypatch):
    """TimedRotatingFileHandler의 when, backupCount가 설정값과 일치한다."""
    monkeypatch.chdir(tmp_path)
    settings = _make_settings(
        log_file_name="app.log",
        log_rotation_when="h",
        log_rotation_backup_count=7,
    )
    setup_logging(settings)

    root = logging.getLogger()
    file_handler = next(
        h for h in root.handlers
        if isinstance(h, logging.handlers.TimedRotatingFileHandler)
    )
    assert file_handler.when == "H"  # TimedRotatingFileHandler는 대문자로 정규화
    assert file_handler.backupCount == 7


def test_invalid_rotation_when_raises():
    """유효하지 않은 log_rotation_when 값은 ValueError를 발생시킨다."""
    settings = _make_settings(log_file_name="app.log", log_rotation_when="invalid")
    with pytest.raises(ValueError, match="log_rotation_when"):
        setup_logging(settings)


def test_duplicate_handlers_not_added(tmp_path, monkeypatch):
    """setup_logging을 두 번 호출해도 핸들러가 중복 추가되지 않는다."""
    monkeypatch.chdir(tmp_path)
    settings = _make_settings(log_file_name="app.log")
    setup_logging(settings)
    setup_logging(settings)

    root = logging.getLogger()
    stream_count = sum(
        1 for h in root.handlers if type(h) is logging.StreamHandler
    )
    file_count = sum(
        1 for h in root.handlers
        if isinstance(h, logging.handlers.TimedRotatingFileHandler)
    )
    assert stream_count == 1
    assert file_count == 1


def test_both_handlers_write_output(tmp_path, monkeypatch, capsys):
    """콘솔과 파일에 동시에 로그가 기록된다."""
    monkeypatch.chdir(tmp_path)
    settings = _make_settings(log_file_name="app.log")
    setup_logging(settings)

    logging.getLogger("test.both").info("hello from test")

    # 파일에 기록됐는지 확인
    log_content = (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")
    assert "hello from test" in log_content

    # 콘솔에 기록됐는지 확인
    captured = capsys.readouterr()
    assert "hello from test" in captured.err
