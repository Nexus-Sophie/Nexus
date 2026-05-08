"""Authentication API routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from src.server.api.auth import (
    build_github_login_url,
    create_access_token,
    exchange_code_for_token,
    fetch_github_user,
    get_agent_price,
    get_current_user,
)
from src.server.postgres.database import Database
from src.server.postgres.models import AgentName, UserRecord
from src.server.postgres.repositories import (
    UserAgentSubscriptionRepository,
    UserRepository,
)
from src.server.schemas import (
    AuthTokenResponse,
    BuyAgentRequest,
    RechargeRequest,
    UserAgentSubscriptionResponse,
    UserResponse,
)

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.get("/github/login")
async def github_login(state: str = Query(default="")) -> dict[str, str]:
    """Return the GitHub OAuth authorization URL."""
    try:
        url = build_github_login_url(state)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"authorization_url": url}


@router.get("/github/callback", response_model=AuthTokenResponse)
async def github_callback(request: Request, code: str = Query(...)) -> AuthTokenResponse:
    """Exchange GitHub OAuth code for an access token and return a JWT."""
    access_token = await exchange_code_for_token(code)
    if access_token is None:
        raise HTTPException(status_code=400, detail="Failed to exchange code for token")

    github_user = await fetch_github_user(access_token)
    if github_user is None:
        raise HTTPException(status_code=400, detail="Failed to fetch GitHub user")

    github_id = str(github_user.get("id", ""))
    github_login = github_user.get("login", "")
    email = github_user.get("email") or None

    if not github_id or not github_login:
        raise HTTPException(status_code=400, detail="Invalid GitHub user data")

    database: Database = request.app.state.database
    async with database.session() as session:
        user = await UserRepository.get_by_github_id(session, github_id)
        if user is None:
            user = await UserRepository.create(
                session,
                github_id=github_id,
                github_login=github_login,
                email=email,
            )

    token = create_access_token(user.id)
    return AuthTokenResponse(access_token=token)


@router.post("/logout")
async def logout() -> dict[str, str]:
    """Logout endpoint. Clients should discard their token."""
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
async def me(current_user: UserRecord = Depends(get_current_user)) -> UserResponse:
    """Return the current authenticated user's information."""
    return UserResponse.from_record(current_user)


@router.post("/recharge", response_model=UserResponse)
async def recharge(
    request: Request,
    payload: RechargeRequest,
    current_user: UserRecord = Depends(get_current_user),
) -> UserResponse:
    """Recharge the current user's balance."""
    amount = Decimal(payload.amount)
    database: Database = request.app.state.database
    async with database.session() as session:
        user = await UserRepository.add_balance(session, current_user.id, amount)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
    return UserResponse.from_record(user)


@router.post("/buy-agent", response_model=UserAgentSubscriptionResponse)
async def buy_agent(
    request: Request,
    payload: BuyAgentRequest,
    current_user: UserRecord = Depends(get_current_user),
) -> UserAgentSubscriptionResponse:
    """Purchase an agent subscription for the current user."""
    try:
        price = get_agent_price(payload.agent.value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    total_price = price * Decimal(payload.months)

    database: Database = request.app.state.database
    async with database.session() as session:
        user = await UserRepository.deduct_balance(session, current_user.id, total_price)
        if user is None:
            raise HTTPException(status_code=400, detail="Insufficient balance")

        now = datetime.now(timezone.utc)
        started_at = now
        expires_at = now + timedelta(days=30 * payload.months)

        subscription = await UserAgentSubscriptionRepository.create(
            session,
            user_id=user.id,
            agent=AgentName(payload.agent.value),
            started_at=started_at,
            expires_at=expires_at,
            commit=False,
        )
        if hasattr(session, "commit"):
            await session.commit()
        if hasattr(session, "refresh"):
            await session.refresh(subscription)

    return UserAgentSubscriptionResponse.from_record(subscription)
