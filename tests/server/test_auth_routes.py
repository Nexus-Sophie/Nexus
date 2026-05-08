"""Tests for auth routes and logic."""

from __future__ import annotations

import asyncio
import sys
import types
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

import src.server.api.auth as auth_module
import src.server.api.routes.auth as auth_routes
from src.server.api.auth import (
    build_github_login_url,
    create_access_token,
    get_agent_price,
    verify_access_token,
)
from src.server.api.routes.auth import router as auth_router
from src.server.postgres.models import AgentName
from src.server.postgres.repositories import (
    UserAgentSubscriptionRepository,
    UserRepository,
)


class FakeDatabase:
    def __init__(self, session_obj: object | None = None) -> None:
        self._session_obj = session_obj if session_obj is not None else object()

    @asynccontextmanager
    async def session(self):
        yield self._session_obj


def _build_app(session_obj: object | None = None) -> FastAPI:
    app = FastAPI()
    app.state.database = FakeDatabase(session_obj)
    app.include_router(auth_router)
    return app


def _make_settings(
    *,
    jwt_secret: str = "test-secret",
    jwt_algorithm: str = "HS256",
    jwt_expiration_hours: int = 168,
    github_oauth_client_id: str = "test-client-id",
    github_oauth_client_secret: str = "test-client-secret",
) -> Any:
    return SimpleNamespace(
        jwt_secret=jwt_secret,
        jwt_algorithm=jwt_algorithm,
        jwt_expiration_hours=jwt_expiration_hours,
        github_oauth_client_id=github_oauth_client_id,
        github_oauth_client_secret=github_oauth_client_secret,
    )


def _make_user(
    *,
    user_id: uuid.UUID | None = None,
    github_id: str = "123456",
    github_login: str = "testuser",
    email: str | None = "test@example.com",
    balance: Decimal = Decimal("100.0000"),
) -> Any:
    return SimpleNamespace(
        id=user_id or uuid.uuid4(),
        github_id=github_id,
        github_login=github_login,
        email=email,
        balance=balance,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


# --- Auth logic tests ---


def test_create_and_verify_access_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_module, "get_settings", _make_settings)
    user_id = uuid.uuid4()
    token = create_access_token(user_id)
    assert isinstance(token, str)
    assert verify_access_token(token) == user_id


def test_verify_access_token_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_module, "get_settings", _make_settings)
    assert verify_access_token("not-a-valid-token") is None


def test_verify_access_token_without_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        auth_module, "get_settings", lambda: _make_settings(jwt_secret="")
    )
    assert verify_access_token("any-token") is None


def test_build_github_login_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_module, "get_settings", _make_settings)
    url = build_github_login_url("random-state")
    assert url.startswith("https://github.com/login/oauth/authorize")
    assert "client_id=test-client-id" in url
    assert "state=random-state" in url
    assert "scope=read:user user:email" in url


def test_build_github_login_url_missing_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        auth_module, "get_settings", lambda: _make_settings(github_oauth_client_id="")
    )
    with pytest.raises(RuntimeError, match="NEXUS_GITHUB_OAUTH_CLIENT_ID"):
        build_github_login_url("state")


def test_get_agent_price_known() -> None:
    assert get_agent_price("tela") == "5500"
    assert get_agent_price("sophie") == "6000"


def test_get_agent_price_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown agent"):
        get_agent_price("unknown")


# --- Route tests ---


def test_github_login_returns_authorization_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_module, "get_settings", _make_settings)

    async def run_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=_build_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get("/v1/auth/github/login", params={"state": "xyz"})

    response = asyncio.run(run_request())
    assert response.status_code == 200
    assert "authorization_url" in response.json()


def test_github_login_returns_503_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        auth_module, "get_settings", lambda: _make_settings(github_oauth_client_id="")
    )

    async def run_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=_build_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get("/v1/auth/github/login")

    response = asyncio.run(run_request())
    assert response.status_code == 503


def test_github_callback_creates_new_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_module, "get_settings", _make_settings)
    user = _make_user()
    created = False

    async def fake_exchange(code: str) -> str | None:
        return "gh-access-token"

    async def fake_fetch(token: str) -> dict[str, Any] | None:
        return {"id": 123456, "login": "testuser", "email": "test@example.com"}

    async def fake_get_by_github_id(session, github_id: str) -> Any | None:
        return None

    async def fake_create(session, **kwargs) -> Any:
        nonlocal created
        created = True
        user.github_id = kwargs["github_id"]
        user.github_login = kwargs["github_login"]
        user.email = kwargs["email"]
        return user

    monkeypatch.setattr(auth_routes, "exchange_code_for_token", fake_exchange)
    monkeypatch.setattr(auth_routes, "fetch_github_user", fake_fetch)
    monkeypatch.setattr(UserRepository, "get_by_github_id", fake_get_by_github_id)
    monkeypatch.setattr(UserRepository, "create", fake_create)

    async def run_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=_build_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get("/v1/auth/github/callback", params={"code": "abc123"})

    response = asyncio.run(run_request())
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert created is True


def test_github_callback_looks_up_existing_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_module, "get_settings", _make_settings)
    user = _make_user()
    created = False

    async def fake_exchange(code: str) -> str | None:
        return "gh-access-token"

    async def fake_fetch(token: str) -> dict[str, Any] | None:
        return {"id": 123456, "login": "testuser", "email": "test@example.com"}

    async def fake_get_by_github_id(session, github_id: str) -> Any | None:
        return user

    async def fake_create(session, **kwargs) -> Any:
        nonlocal created
        created = True
        return user

    monkeypatch.setattr(auth_routes, "exchange_code_for_token", fake_exchange)
    monkeypatch.setattr(auth_routes, "fetch_github_user", fake_fetch)
    monkeypatch.setattr(UserRepository, "get_by_github_id", fake_get_by_github_id)
    monkeypatch.setattr(UserRepository, "create", fake_create)

    async def run_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=_build_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get("/v1/auth/github/callback", params={"code": "abc123"})

    response = asyncio.run(run_request())
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert created is False


def test_github_callback_fails_token_exchange(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_module, "get_settings", _make_settings)

    async def fake_exchange(code: str) -> str | None:
        return None

    monkeypatch.setattr(auth_routes, "exchange_code_for_token", fake_exchange)

    async def run_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=_build_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get("/v1/auth/github/callback", params={"code": "bad-code"})

    response = asyncio.run(run_request())
    assert response.status_code == 400
    assert response.json()["detail"] == "Failed to exchange code for token"


def test_github_callback_fails_user_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_module, "get_settings", _make_settings)

    async def fake_exchange(code: str) -> str | None:
        return "gh-access-token"

    async def fake_fetch(token: str) -> dict[str, Any] | None:
        return None

    monkeypatch.setattr(auth_routes, "exchange_code_for_token", fake_exchange)
    monkeypatch.setattr(auth_routes, "fetch_github_user", fake_fetch)

    async def run_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=_build_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get("/v1/auth/github/callback", params={"code": "abc123"})

    response = asyncio.run(run_request())
    assert response.status_code == 400
    assert response.json()["detail"] == "Failed to fetch GitHub user"


def test_logout_returns_success() -> None:
    async def run_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=_build_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post("/v1/auth/logout")

    response = asyncio.run(run_request())
    assert response.status_code == 200
    assert response.json()["message"] == "Logged out successfully"


def test_me_returns_current_user(monkeypatch: pytest.MonkeyPatch) -> None:
    user = _make_user()

    def fake_verify(token: str) -> uuid.UUID | None:
        return user.id

    async def fake_get_by_id(session, user_id: uuid.UUID) -> Any | None:
        return user

    monkeypatch.setattr(auth_module, "verify_access_token", fake_verify)
    monkeypatch.setattr(UserRepository, "get_by_id", fake_get_by_id)

    async def run_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=_build_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get("/v1/auth/me", headers={"Authorization": "Bearer valid-token"})

    response = asyncio.run(run_request())
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(user.id)
    assert payload["github_login"] == user.github_login
    assert payload["balance"] == str(user.balance)


def test_me_returns_401_without_header() -> None:
    async def run_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=_build_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get("/v1/auth/me")

    response = asyncio.run(run_request())
    assert response.status_code == 401
    assert "authorization header" in response.json()["detail"].lower()


def test_me_returns_401_with_invalid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_verify(token: str) -> uuid.UUID | None:
        return None

    monkeypatch.setattr(auth_module, "verify_access_token", fake_verify)

    async def run_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=_build_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get("/v1/auth/me", headers={"Authorization": "Bearer invalid"})

    response = asyncio.run(run_request())
    assert response.status_code == 401
    assert "invalid or expired token" in response.json()["detail"].lower()


def test_me_returns_401_when_user_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_verify(token: str) -> uuid.UUID | None:
        return uuid.uuid4()

    async def fake_get_by_id(session, user_id: uuid.UUID) -> Any | None:
        return None

    monkeypatch.setattr(auth_module, "verify_access_token", fake_verify)
    monkeypatch.setattr(UserRepository, "get_by_id", fake_get_by_id)

    async def run_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=_build_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get("/v1/auth/me", headers={"Authorization": "Bearer valid-token"})

    response = asyncio.run(run_request())
    assert response.status_code == 401
    assert "user not found" in response.json()["detail"].lower()


def test_recharge_increases_balance(monkeypatch: pytest.MonkeyPatch) -> None:
    user = _make_user(balance=Decimal("50.0000"))
    updated_user = _make_user(user_id=user.id, balance=Decimal("150.0000"))

    def fake_verify(token: str) -> uuid.UUID | None:
        return user.id

    async def fake_get_by_id(session, user_id: uuid.UUID) -> Any | None:
        return user

    async def fake_add_balance(session, user_id: uuid.UUID, amount: Any) -> Any | None:
        return updated_user

    monkeypatch.setattr(auth_module, "verify_access_token", fake_verify)
    monkeypatch.setattr(UserRepository, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(UserRepository, "add_balance", fake_add_balance)

    async def run_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=_build_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/v1/auth/recharge",
                headers={"Authorization": "Bearer valid-token"},
                json={"amount": "100"},
            )

    response = asyncio.run(run_request())
    assert response.status_code == 200
    assert response.json()["balance"] == "150.0000"


def test_recharge_returns_401_without_auth() -> None:
    async def run_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=_build_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post("/v1/auth/recharge", json={"amount": "100"})

    response = asyncio.run(run_request())
    assert response.status_code == 401


def test_buy_agent_creates_subscription(monkeypatch: pytest.MonkeyPatch) -> None:
    user = _make_user(balance=Decimal("10000.0000"))
    subscription = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user.id,
        agent=AgentName.tela,
        started_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        created_at=datetime.now(timezone.utc),
    )

    def fake_verify(token: str) -> uuid.UUID | None:
        return user.id

    async def fake_get_by_id(session, user_id: uuid.UUID) -> Any | None:
        return user

    async def fake_deduct_balance(session, user_id: uuid.UUID, amount: Any) -> Any | None:
        return user

    async def fake_create_sub(session, **kwargs) -> Any:
        return subscription

    monkeypatch.setattr(auth_module, "verify_access_token", fake_verify)
    monkeypatch.setattr(UserRepository, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(UserRepository, "deduct_balance", fake_deduct_balance)
    monkeypatch.setattr(UserAgentSubscriptionRepository, "create", fake_create_sub)

    async def run_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=_build_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/v1/auth/buy-agent",
                headers={"Authorization": "Bearer valid-token"},
                json={"agent": "tela", "months": 1},
            )

    response = asyncio.run(run_request())
    assert response.status_code == 200
    payload = response.json()
    assert payload["user_id"] == str(user.id)
    assert payload["agent"] == "tela"


def test_buy_agent_returns_400_for_insufficient_balance(monkeypatch: pytest.MonkeyPatch) -> None:
    user = _make_user(balance=Decimal("0.0000"))

    def fake_verify(token: str) -> uuid.UUID | None:
        return user.id

    async def fake_get_by_id(session, user_id: uuid.UUID) -> Any | None:
        return user

    async def fake_deduct_balance(session, user_id: uuid.UUID, amount: Any) -> Any | None:
        return None

    monkeypatch.setattr(auth_module, "verify_access_token", fake_verify)
    monkeypatch.setattr(UserRepository, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(UserRepository, "deduct_balance", fake_deduct_balance)

    async def run_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=_build_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/v1/auth/buy-agent",
                headers={"Authorization": "Bearer valid-token"},
                json={"agent": "sophie", "months": 1},
            )

    response = asyncio.run(run_request())
    assert response.status_code == 400
    assert "insufficient balance" in response.json()["detail"].lower()


def test_buy_agent_returns_401_without_auth() -> None:
    async def run_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=_build_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post("/v1/auth/buy-agent", json={"agent": "tela", "months": 1})

    response = asyncio.run(run_request())
    assert response.status_code == 401



