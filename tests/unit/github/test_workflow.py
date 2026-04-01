from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.github.workflow import (
    WORKFLOW_BRANCH,
    deploy_workflows_to_repo,
)


@pytest.mark.asyncio
async def test_deploy_skips_when_pr_exists(tmp_path):
    """열린 PR이 이미 있으면 브랜치 생성 없이 스킵."""
    # 빈 템플릿 파일 생성
    for f in ["gemini-dispatch.yml", "gemini-review.yml", "gemini-triage.yml", "gemini-invoke.yml", "pr-body.md"]:
        (tmp_path / f).write_text("placeholder")

    with patch("app.github.workflow.pr_exists_for_branch", new_callable=AsyncMock, return_value=True):
        with patch("app.github.workflow.create_branch", new_callable=AsyncMock) as mock_branch:
            await deploy_workflows_to_repo("org", "repo", "main", "token", tmp_path)
            mock_branch.assert_not_called()


@pytest.mark.asyncio
async def test_deploy_creates_branch_and_pr(tmp_path):
    """PR 없을 때 브랜치 생성 → 파일 커밋 → PR 생성."""
    for f in ["gemini-dispatch.yml", "gemini-review.yml", "gemini-triage.yml", "gemini-invoke.yml", "pr-body.md"]:
        (tmp_path / f).write_text(f"content of {f}")

    with patch("app.github.workflow.pr_exists_for_branch", new_callable=AsyncMock, return_value=False):
        with patch("app.github.workflow.get_branch_sha", new_callable=AsyncMock, return_value="abc123"):
            with patch("app.github.workflow.create_branch", new_callable=AsyncMock) as mock_branch:
                with patch("app.github.workflow.commit_file", new_callable=AsyncMock) as mock_commit:
                    with patch("app.github.workflow.create_pr", new_callable=AsyncMock, return_value=42) as mock_pr:
                        await deploy_workflows_to_repo("org", "repo", "main", "token", tmp_path)

                        mock_branch.assert_called_once_with("org", "repo", WORKFLOW_BRANCH, "abc123", "token")
                        assert mock_commit.call_count == 4  # 워크플로우 파일 4개
                        mock_pr.assert_called_once()


@pytest.mark.asyncio
async def test_deploy_continues_when_branch_already_exists(tmp_path):
    """브랜치 이미 존재(422) 시에도 파일 커밋과 PR 생성은 계속 진행.

    create_branch 내부에서 422를 처리하므로 _github_request 레벨에서 모킹.
    """
    import httpx

    for f in ["gemini-dispatch.yml", "gemini-review.yml", "gemini-triage.yml", "gemini-invoke.yml", "pr-body.md"]:
        (tmp_path / f).write_text("content")

    mock_422_response = MagicMock(status_code=422)
    mock_422 = httpx.HTTPStatusError("422", request=MagicMock(), response=mock_422_response)

    with patch("app.github.workflow.pr_exists_for_branch", new_callable=AsyncMock, return_value=False):
        with patch("app.github.workflow.get_branch_sha", new_callable=AsyncMock, return_value="abc123"):
            # _github_request를 패치해서 create_branch 내부 422 처리 로직이 실제로 실행되도록 함
            with patch("app.github.workflow._github_request", new_callable=AsyncMock, side_effect=mock_422):
                with patch("app.github.workflow.commit_file", new_callable=AsyncMock) as mock_commit:
                    with patch("app.github.workflow.create_pr", new_callable=AsyncMock, return_value=1):
                        await deploy_workflows_to_repo("org", "repo", "main", "token", tmp_path)
                        assert mock_commit.call_count == 4
