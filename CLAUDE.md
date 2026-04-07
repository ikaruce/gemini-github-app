# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Gemini GitHub App** is a FastAPI server that automatically manages Gemini CLI GitHub App installations across GitHub Organizations. On installation, it registers org secrets, deploys workflow files to all repos via PRs, and monitors audit logs to detect/recover from secret changes.

## Commands

```bash
# Install dependencies
uv sync

# Run locally
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
pytest

# Run a single test file
pytest tests/unit/test_config.py

# Run with coverage
pytest --cov=app --cov-report=term-missing

# Build Docker image
docker build -t gemini-github-app:latest .

# Run via Docker Compose (requires .env)
cp .env.example .env
docker compose up
```

## Architecture

### Request Flow

```
GitHub Webhook → /webhook (handler.py)
  → verify.py       HMAC-SHA256 signature check
  → installation.py Route by event (created/added/deleted)
    → github/client.py    Issue installation token (JWT → Token)
    → github/secret.py    Encrypt + register org secrets (PyNaCl SealedBox)
    → github/repo.py      List repos, check existing branches/PRs
    → github/workflow.py  Create branch, commit 4 workflow files, open PR
    → audit/poller.py     Register org for ongoing monitoring

Background Job (APScheduler, every 5 min):
  → audit/poller.py   Poll org audit logs for secret changes
    → github/secret.py   Auto-recover changed secrets
    → notify/issue.py    Create GitHub Issue alert on failure
```

### Key Modules

| Module | Responsibility |
|--------|---------------|
| `app/main.py` | FastAPI app, lifespan (APScheduler start/stop), `/webhook` + `/health` endpoints |
| `app/config.py` | Pydantic Settings, lazy singleton `get_settings()`, PEM normalization |
| `app/webhook/installation.py` | Core orchestration: secret registration + workflow deployment on install |
| `app/github/client.py` | JWT (RS256, iat-60/exp+540), installation tokens, paginated API requests |
| `app/github/secret.py` | Fetch org public key, PyNaCl SealedBox encrypt, PUT to GitHub Secrets API |
| `app/audit/poller.py` | APScheduler job, `_tracked_orgs` dict, dedup via `_processed_ids` set |
| `app/logging_config.py` | Root logger, optional `TimedRotatingFileHandler` |

### Workflow Templates

Four files deployed to `.github/workflows/` in every repo on install:
- `gemini-dispatch.yml` — Hub: listens to PR/issue events, routes via `workflow_call`
- `gemini-review.yml` — PR code review
- `gemini-triage.yml` — Issue auto-labeling
- `gemini-invoke.yml` — Freeform `@gemini-cli` commands

### Configuration (`.env`)

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `APP_ID` | Yes | — | GitHub App ID |
| `APP_PRIVATE_KEY` | Yes | — | RSA PEM (newlines auto-normalized) |
| `WEBHOOK_SECRET` | Yes | — | For HMAC verification |
| `NOTIFY_REPO` | Yes | — | `org/repo` format for alert issues |
| `GITHUB_API_URL` | No | `https://api.github.com` | Override for GHES |
| `AUDIT_POLL_INTERVAL_MINUTES` | No | `5` | Range: 1–60 |
| `LOG_FILE_NAME` | No | — | Enables file logging if set |
| `TAG` | No | `latest` | Docker image tag |

### Design Patterns

- **Lazy singleton settings**: `get_settings()` avoids import-time init; tests reset via `get_settings.cache_clear()`
- **GHES support**: All GitHub API functions accept `api_url` parameter; defaults to `https://api.github.com`
- **Concurrency**: `asyncio.Semaphore(10)` limits concurrent repo deployments in `installation.py`
- **Audit dedup**: In-memory `_processed_ids` set, trimmed to 10K entries to prevent unbounded growth
- **Clock drift tolerance**: JWT issued with `iat = now - 60s` to handle server clock skew
