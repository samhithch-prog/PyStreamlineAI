import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_auth_context
from app.core.auth import AuthContext, UserRole, decode_streamlit_launch_token, mint_access_token, mint_ws_token
from app.core.redis_client import get_redis_client
from app.schemas.auth import (
    AccessTokenResponse,
    StreamlitLaunchTokenRequest,
    WebSocketTokenRequest,
    WebSocketTokenResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])
_local_launch_jti_store: dict[str, int] = {}


def _safe_claim_str(claims: dict[str, Any], key: str) -> str:
    return str(claims.get(key, "")).strip()


def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


async def _consume_streamlit_launch_jti(jti: str, ttl_seconds: int) -> bool:
    cleaned_jti = str(jti or "").strip()
    if not cleaned_jti:
        return False
    ttl = max(15, int(ttl_seconds or 15))
    redis = get_redis_client()
    if redis is not None:
        created = await redis.set(f"auth:streamlit-launch:jti:{cleaned_jti}", "1", ex=ttl, nx=True)
        return bool(created)

    now_ts = _now_ts()
    expired = [key for key, exp in _local_launch_jti_store.items() if int(exp) <= now_ts]
    for key in expired:
        _local_launch_jti_store.pop(key, None)
    if cleaned_jti in _local_launch_jti_store:
        return False
    _local_launch_jti_store[cleaned_jti] = now_ts + ttl
    return True


def _normalize_role(value: str) -> UserRole:
    cleaned = str(value or "").strip().lower()
    if cleaned == UserRole.admin.value:
        return UserRole.admin
    if cleaned == UserRole.recruiter.value:
        return UserRole.recruiter
    return UserRole.candidate


@router.post("/streamlit-launch", response_model=AccessTokenResponse)
async def exchange_streamlit_launch_token(payload: StreamlitLaunchTokenRequest) -> AccessTokenResponse:
    claims = decode_streamlit_launch_token(payload.launch_token)
    jti = _safe_claim_str(claims, "jti")
    exp_ts = int(claims.get("exp", 0) or 0)
    ttl = max(1, exp_ts - _now_ts())
    consumed = await _consume_streamlit_launch_jti(jti, ttl)
    if not consumed:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Launch token is invalid or already used.",
        )

    user_id = _safe_claim_str(claims, "sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Launch token missing subject.")
    role = _normalize_role(_safe_claim_str(claims, "role"))
    org_id = _safe_claim_str(claims, "org_id") or None
    email = _safe_claim_str(claims, "email") or None
    access_token, expires_in = mint_access_token(
        user_id=user_id,
        role=role,
        org_id=org_id,
        email=email,
    )
    return AccessTokenResponse(
        access_token=access_token,
        expires_in=expires_in,
    )


@router.post("/ws-token", response_model=WebSocketTokenResponse)
async def create_websocket_token(
    payload: WebSocketTokenRequest,
    auth_ctx: AuthContext = Depends(get_current_auth_context),
) -> WebSocketTokenResponse:
    session_id = uuid.UUID(str(payload.session_id))
    token, expires_in = mint_ws_token(access_ctx=auth_ctx, session_id=session_id)
    return WebSocketTokenResponse(
        ws_token=token,
        expires_in=expires_in,
        session_id=session_id,
    )
