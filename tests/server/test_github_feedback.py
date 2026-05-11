from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx

from src.server.github_feedback import GithubFeedbackPoller
from src.server.postgres.models import GithubPullRequestFeedbackStatus
from src.server.postgres.repositories import (
    GithubPullRequestFeedbackRepository,
    TaskRepository,
)


class FakeDatabase:
    @asynccontextmanager
    async def session(self):
        yield object()


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


def _make_settings():
    return SimpleNamespace(
        github_tokens={"sophie": "test-token"},
        github_feedback_poll_interval_seconds=60,
        github_feedback_poll_task_limit=20,
        github_feedback_http_timeout_seconds=10.0,
    )


def test_poll_once_discovers_feedback_and_reuses_existing_task(monkeypatch):
    task = SimpleNamespace(
        id=uuid.uuid4(),
        repo="owner/repo",
        external_pull_request_url="https://github.com/owner/repo/pull/12",
        agent=SimpleNamespace(value="sophie"),
        updated_at=datetime.fromisoformat("2024-01-01T00:00:00+00:00"),
    )
    captured_statuses = []
    runner = SimpleNamespace(dispatch_github_feedback=AsyncMock(return_value=True))

    async def fake_list_candidates(session, *, limit):
        assert limit == 20
        return [task]

    async def fake_upsert(session, **kwargs):
        captured_statuses.append(
            {
                "kind": kwargs["kind"].value,
                "status": kwargs["status"],
                "author": kwargs["author"],
            }
        )
        return SimpleNamespace(id=uuid.uuid4()), True

    async def fake_has_pending_newer_than(session, task_id, *, cutoff):
        assert task_id == task.id
        assert cutoff == task.updated_at
        return False

    async def fake_get(self, url, headers=None, params=None):
        page = 1 if params is None else params.get("page", 1)
        if url.endswith("/user"):
            return FakeResponse({"login": "nexus-bot"})
        if url.endswith("/pulls/12"):
            return FakeResponse({"state": "open", "merged_at": None})
        if url.endswith("/issues/12/comments"):
            if page > 1:
                return FakeResponse([])
            return FakeResponse(
                [
                    {
                        "id": 101,
                        "user": {"login": "nexus-bot"},
                        "body": "I already replied here.",
                        "created_at": "2024-01-01T00:00:00Z",
                        "updated_at": "2024-01-01T00:00:00Z",
                        "html_url": "https://github.com/owner/repo/pull/12#issuecomment-101",
                    }
                ]
            )
        if url.endswith("/pulls/12/reviews"):
            if page > 1:
                return FakeResponse([])
            return FakeResponse(
                [
                    {
                        "id": 201,
                        "user": {"login": "reviewer"},
                        "state": "CHANGES_REQUESTED",
                        "body": "Please add a regression test.",
                        "submitted_at": "2024-01-02T00:00:00Z",
                        "html_url": "https://github.com/owner/repo/pull/12#pullrequestreview-201",
                    }
                ]
            )
        if url.endswith("/pulls/12/comments"):
            if page > 1:
                return FakeResponse([])
            return FakeResponse(
                [
                    {
                        "id": 301,
                        "user": {"login": "reviewer"},
                        "body": "Rename this variable.",
                        "path": "src/main.py",
                        "line": 42,
                        "original_line": 42,
                        "commit_id": "abc123",
                        "created_at": "2024-01-03T00:00:00Z",
                        "updated_at": "2024-01-03T00:00:00Z",
                        "html_url": "https://github.com/owner/repo/pull/12#discussion_r301",
                    }
                ]
            )
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(TaskRepository, "list_external_pull_request_candidates", fake_list_candidates)
    monkeypatch.setattr(GithubPullRequestFeedbackRepository, "upsert_discovered", fake_upsert)
    monkeypatch.setattr(
        GithubPullRequestFeedbackRepository,
        "has_pending_newer_than",
        fake_has_pending_newer_than,
    )
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    poller = GithubFeedbackPoller(
        settings=_make_settings(),
        database=FakeDatabase(),
        runner=runner,
    )
    discovered = asyncio.run(poller.poll_once())

    assert discovered == 2
    runner.dispatch_github_feedback.assert_awaited_once_with(task.id)
    assert captured_statuses == [
        {
            "kind": "pr_comment",
            "status": GithubPullRequestFeedbackStatus.ignored,
            "author": "nexus-bot",
        },
        {
            "kind": "pr_review",
            "status": GithubPullRequestFeedbackStatus.pending,
            "author": "reviewer",
        },
        {
            "kind": "pr_review_comment",
            "status": GithubPullRequestFeedbackStatus.pending,
            "author": "reviewer",
        },
    ]


def test_poll_once_does_not_redispatch_stale_pending_feedback(monkeypatch):
    task = SimpleNamespace(
        id=uuid.uuid4(),
        repo="owner/repo",
        external_pull_request_url="https://github.com/owner/repo/pull/12",
        agent=SimpleNamespace(value="sophie"),
        updated_at=datetime.fromisoformat("2024-01-10T00:00:00+00:00"),
    )
    runner = SimpleNamespace(dispatch_github_feedback=AsyncMock(return_value=True))

    async def fake_list_candidates(session, *, limit):
        return [task]

    async def fake_upsert(session, **kwargs):
        return SimpleNamespace(id=uuid.uuid4()), False

    async def fake_has_pending_newer_than(session, task_id, *, cutoff):
        assert task_id == task.id
        assert cutoff == task.updated_at
        return False

    async def fake_get(self, url, headers=None, params=None):
        page = 1 if params is None else params.get("page", 1)
        if url.endswith("/user"):
            return FakeResponse({"login": "nexus-bot"})
        if url.endswith("/pulls/12"):
            return FakeResponse({"state": "open", "merged_at": None})
        if page > 1:
            return FakeResponse([])
        if url.endswith("/issues/12/comments"):
            return FakeResponse(
                [
                    {
                        "id": 101,
                        "user": {"login": "reviewer"},
                        "body": "Already handled feedback.",
                        "created_at": "2024-01-01T00:00:00Z",
                        "updated_at": "2024-01-01T00:00:00Z",
                        "html_url": "https://github.com/owner/repo/pull/12#issuecomment-101",
                    }
                ]
            )
        if url.endswith("/pulls/12/reviews") or url.endswith("/pulls/12/comments"):
            return FakeResponse([])
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(TaskRepository, "list_external_pull_request_candidates", fake_list_candidates)
    monkeypatch.setattr(GithubPullRequestFeedbackRepository, "upsert_discovered", fake_upsert)
    monkeypatch.setattr(
        GithubPullRequestFeedbackRepository,
        "has_pending_newer_than",
        fake_has_pending_newer_than,
    )
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    poller = GithubFeedbackPoller(
        settings=_make_settings(),
        database=FakeDatabase(),
        runner=runner,
    )
    discovered = asyncio.run(poller.poll_once())

    assert discovered == 0
    runner.dispatch_github_feedback.assert_not_awaited()
