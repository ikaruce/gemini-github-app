from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.audit import poller as poller_module
from app.audit.poller import (
    _mark_processed,
    _process_audit_entries,
    register_org,
    unregister_org,
)


@pytest.fixture(autouse=True)
def reset_poller_state():
    """각 테스트 후 모듈 수준 상태 리셋."""
    yield
    poller_module._processed_doc_ids.clear()
    poller_module._tracked_orgs.clear()


def test_register_org_adds_to_tracked():
    register_org("test-org", 42)
    assert poller_module._tracked_orgs["test-org"] == 42


def test_unregister_org_removes_from_tracked():
    register_org("test-org", 42)
    unregister_org("test-org")
    assert "test-org" not in poller_module._tracked_orgs


def test_unregister_nonexistent_org_is_safe():
    unregister_org("nonexistent-org")  # 예외 없어야 함


def test_mark_processed_adds_doc_id():
    _mark_processed("doc-123")
    assert "doc-123" in poller_module._processed_doc_ids


def test_mark_processed_trims_when_exceeds_max():
    """10,000개 초과 시 5,000개 정리 — 남은 항목 수는 TRIM_TARGET 부근이어야 함."""
    for i in range(10_001):
        poller_module._processed_doc_ids.add(f"doc-{i}")

    _mark_processed("trigger-trim")
    # 10001 + 1 = 10002 items → trim 5000 → 5002 remain
    assert len(poller_module._processed_doc_ids) <= poller_module._TRIM_TARGET + 2


@pytest.mark.asyncio
async def test_process_entries_skips_duplicate_doc_ids(mock_settings):
    """이미 처리된 document_id는 스킵."""
    poller_module._processed_doc_ids.add("doc-already-processed")

    entries = [
        {
            "_document_id": "doc-already-processed",
            "action": "org.update_secret",
            "data": {"name": "APP_ID"},
        }
    ]

    with patch.object(poller_module, "_handle_secret_change", new_callable=AsyncMock) as mock_handle:
        await _process_audit_entries("test-org", entries, 1, mock_settings)
        mock_handle.assert_not_called()


@pytest.mark.asyncio
async def test_process_entries_handles_app_id_change(mock_settings):
    """APP_ID 변경 감지 시 _handle_secret_change 호출."""
    entries = [
        {
            "_document_id": "doc-new",
            "action": "org.update_secret",
            "data": {"name": "APP_ID"},
        }
    ]

    with patch.object(poller_module, "_handle_secret_change", new_callable=AsyncMock) as mock_handle:
        await _process_audit_entries("test-org", entries, 1, mock_settings)
        mock_handle.assert_called_once_with("test-org", "APP_ID", 1, mock_settings)


@pytest.mark.asyncio
async def test_process_entries_handles_private_key_change(mock_settings):
    """APP_PRIVATE_KEY 변경 감지 시 _handle_secret_change 호출."""
    entries = [
        {
            "_document_id": "doc-pk-change",
            "action": "org.update_secret",
            "data": {"name": "APP_PRIVATE_KEY"},
        }
    ]

    with patch.object(poller_module, "_handle_secret_change", new_callable=AsyncMock) as mock_handle:
        await _process_audit_entries("test-org", entries, 1, mock_settings)
        mock_handle.assert_called_once_with("test-org", "APP_PRIVATE_KEY", 1, mock_settings)


@pytest.mark.asyncio
async def test_process_entries_ignores_unrelated_secrets(mock_settings):
    """관련 없는 Secret 변경은 무시."""
    entries = [
        {
            "_document_id": "doc-other",
            "action": "org.update_secret",
            "data": {"name": "SOME_OTHER_SECRET"},
        }
    ]

    with patch.object(poller_module, "_handle_secret_change", new_callable=AsyncMock) as mock_handle:
        await _process_audit_entries("test-org", entries, 1, mock_settings)
        mock_handle.assert_not_called()


@pytest.mark.asyncio
async def test_process_entries_marks_doc_id_as_processed(mock_settings):
    """처리 후 document_id가 processed set에 추가되어야 함."""
    entries = [
        {
            "_document_id": "doc-to-mark",
            "action": "org.update_secret",
            "data": {"name": "SOME_SECRET"},
        }
    ]

    with patch.object(poller_module, "_handle_secret_change", new_callable=AsyncMock):
        await _process_audit_entries("test-org", entries, 1, mock_settings)

    assert "doc-to-mark" in poller_module._processed_doc_ids
