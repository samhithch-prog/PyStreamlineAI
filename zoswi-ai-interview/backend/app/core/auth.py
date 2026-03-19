from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any

import jwt
from fastapi import HTTPException, status

from app.core.config import get_settings

settings = get_settings()
PERSONAL_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "icloud.com",
    "aol.com",
    "protonmail.com",
    "pm.me",
    "mail.com",
    "gmx.com",
    "zoho.com",
    "yandex.com",
}


class UserRole(StrEnum):
    candidate = "candidate"
    recruiter = "recruiter"
    admin = "admin"


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    role: UserRole
    org_id: str | None
    token_type: str
    raw_claims: dict[str, Any]


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.") from exc


def _normalize_role(value: Any) -> UserRole:
    cleaned = str(value or "").strip().lower()
    if cleaned not in {role.value for role in UserRole}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid role claim.")
    return UserRole(cleaned)


def _extract_email_domain(email: str) -> str:
    cleaned = str(email or "").strip().lower()
    if "@" not in cleaned:
        return ""
    _local, domain = cleaned.split("@", 1)
    return domain.strip()


def _is_university_email_domain(domain: str) -> bool:
    cleaned = str(domain or "").strip().lower()
    if not cleaned:
        return False
    return cleaned.endswith(".edu") or ".edu." in cleaned or ".ac." in cleaned


def _extract_claim_email(claims: dict[str, Any]) -> str:
    for key in ("email", "user_email", "preferred_username", "upn"):
        value = str(claims.get(key, "")).strip().lower()
        if "@" in value:
            return value
    return ""


def _derive_effective_role(raw_role: Any, claims: dict[str, Any]) -> UserRole:
    role = _normalize_role(raw_role)
    if role != UserRole.recruiter:
        return role
    email = _extract_claim_email(claims)
    if not email:
        return role
    domain = _extract_email_domain(email)
    if domain in PERSONAL_EMAIL_DOMAINS or _is_university_email_domain(domain):
        return UserRole.candidate
    return role


def decode_access_token(token: str) -> AuthContext:
    claims = _decode_token(token)
    token_type = str(claims.get("typ", "access")).strip().lower()
    if token_type != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Expected access token.")
    return AuthContext(
        user_id=str(claims.get("sub", "")).strip(),
        role=_derive_effective_role(claims.get("role"), claims),
        org_id=str(claims.get("org_id", "")).strip() or None,
        token_type=token_type,
        raw_claims=claims,
    )


def decode_ws_token(token: str, expected_session_id: uuid.UUID | None = None) -> AuthContext:
    claims = _decode_token(token)
    token_type = str(claims.get("typ", "")).strip().lower()
    if token_type != "ws":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Expected websocket token.")
    session_id_raw = str(claims.get("session_id", "")).strip()
    if not session_id_raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Websocket token missing session binding.")
    if expected_session_id and session_id_raw != str(expected_session_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Session mismatch for websocket token.")
    return AuthContext(
        user_id=str(claims.get("sub", "")).strip(),
        role=_derive_effective_role(claims.get("role"), claims),
        org_id=str(claims.get("org_id", "")).strip() or None,
        token_type=token_type,
        raw_claims=claims,
    )


def decode_streamlit_launch_token(token: str) -> dict[str, Any]:
    launch_secret = str(settings.streamlit_launch_secret or "").strip()
    if not launch_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Streamlit launch auth is not configured.",
        )
    try:
        claims = jwt.decode(
            token,
            launch_secret,
            algorithms=[settings.jwt_algorithm],
            audience=settings.streamlit_launch_audience,
            issuer=settings.streamlit_launch_issuer,
            options={"require": ["exp", "iat", "sub", "iss", "aud", "jti"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Launch token expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid launch token.") from exc
    token_type = str(claims.get("typ", "")).strip().lower()
    if token_type != "streamlit_launch":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid launch token type.")
    return claims


def mint_access_token(
    *,
    user_id: str,
    role: UserRole,
    org_id: str | None = None,
    email: str | None = None,
    ttl_seconds: int | None = None,
) -> tuple[str, int]:
    cleaned_user_id = str(user_id or "").strip()
    if not cleaned_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing user id.")
    expires_in = max(60, int(ttl_seconds or settings.access_token_ttl_seconds))
    now = _now_utc()
    payload: dict[str, Any] = {
        "sub": cleaned_user_id,
        "role": role.value,
        "org_id": str(org_id or "").strip() or None,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
        "typ": "access",
        "jti": secrets.token_hex(16),
    }
    cleaned_email = str(email or "").strip().lower()
    if cleaned_email:
        payload["email"] = cleaned_email
    encoded = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded, expires_in


def mint_ws_token(access_ctx: AuthContext, session_id: uuid.UUID, ttl_seconds: int | None = None) -> tuple[str, int]:
    expires_in = max(1, int(ttl_seconds or settings.ws_token_ttl_seconds))
    now = _now_utc()
    payload = {
        "sub": access_ctx.user_id,
        "role": access_ctx.role.value,
        "org_id": access_ctx.org_id,
        "session_id": str(session_id),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
        "typ": "ws",
        "jti": secrets.token_hex(16),
    }
    encoded = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded, expires_in
