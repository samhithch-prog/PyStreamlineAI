from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Callable


class AuthRepository:
    """Persistence operations for users, auth sessions, and login events."""

    def __init__(self, db_connect: Callable[[], Any], auth_session_ttl_days: int = 14) -> None:
        self._db_connect = db_connect
        self._auth_session_ttl_days = int(auth_session_ttl_days or 14)

    def authenticate_user(
        self,
        email: str,
        password: str,
        verify_password: Callable[[str, str], bool],
        is_modern_password_hash: Callable[[str], bool],
        hash_password: Callable[[str], str],
    ) -> dict[str, Any] | None:
        conn = self._db_connect()
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                """
                SELECT id, full_name, email, role, years_experience, created_at, password_hash, email_verified_at
                FROM users
                WHERE email = ?
                """,
                (str(email or "").strip().lower(),),
            ).fetchone()
            if row is None:
                return None

            stored_hash = str(row["password_hash"] or "")
            if not verify_password(str(password or ""), stored_hash):
                return None

            if not is_modern_password_hash(stored_hash):
                conn.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (hash_password(str(password or "")), int(row["id"])),
                )
                conn.commit()

            if not str(row["email_verified_at"] or "").strip():
                return {
                    "id": int(row["id"]),
                    "full_name": str(row["full_name"]),
                    "email": str(row["email"]),
                    "pending_verification": True,
                }

            return {
                "id": int(row["id"]),
                "full_name": str(row["full_name"]),
                "email": str(row["email"]),
                "role": str(row["role"] or ""),
                "years_experience": str(row["years_experience"] or ""),
                "created_at": str(row["created_at"]),
            }
        finally:
            conn.close()

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        cleaned_email = str(email or "").strip().lower()
        if not cleaned_email:
            return None
        conn = self._db_connect()
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                """
                SELECT id, full_name, email, role, years_experience, created_at, email_verified_at
                FROM users
                WHERE email = ?
                LIMIT 1
                """,
                (cleaned_email,),
            ).fetchone()
            if row is None:
                return None
            return {
                "id": int(row["id"]),
                "full_name": str(row["full_name"] or ""),
                "email": str(row["email"] or "").strip().lower(),
                "role": str(row["role"] or ""),
                "years_experience": str(row["years_experience"] or ""),
                "created_at": str(row["created_at"] or ""),
                "email_verified_at": str(row["email_verified_at"] or ""),
            }
        finally:
            conn.close()

    def update_password_and_revoke_sessions(self, user_id: int, password_hash: str) -> None:
        if int(user_id or 0) <= 0:
            return
        conn = self._db_connect()
        try:
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (str(password_hash or ""), int(user_id)),
            )
            conn.execute("DELETE FROM auth_sessions WHERE user_id = ?", (int(user_id),))
            conn.commit()
        finally:
            conn.close()

    def record_user_login_event(self, user_id: int, login_method: str, login_provider: str = "") -> None:
        if int(user_id or 0) <= 0:
            return
        method = str(login_method or "").strip().lower() or "password"
        provider = str(login_provider or "").strip().lower()
        now_iso = datetime.now(timezone.utc).isoformat()
        conn = self._db_connect()
        try:
            conn.execute(
                """
                INSERT INTO user_login_events (user_id, login_method, login_provider, login_at)
                VALUES (?, ?, ?, ?)
                """,
                (int(user_id), method, provider or None, now_iso),
            )
            conn.commit()
        finally:
            conn.close()

    def create_auth_session(self, user_id: int, ttl_days: int | None = None) -> str:
        if int(user_id or 0) <= 0:
            return ""
        ttl = int(ttl_days or self._auth_session_ttl_days or 1)
        raw_token = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        created_at = datetime.now(timezone.utc)
        expires_at = created_at + timedelta(days=max(1, ttl))
        created_iso = created_at.isoformat()
        expires_iso = expires_at.isoformat()
        conn = self._db_connect()
        try:
            conn.execute(
                """
                INSERT INTO auth_sessions (user_id, token_hash, created_at, expires_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (int(user_id), token_hash, created_iso, expires_iso, created_iso),
            )
            conn.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (created_iso,))
            conn.commit()
        finally:
            conn.close()
        return raw_token

    def revoke_auth_session(self, raw_token: str) -> None:
        cleaned = str(raw_token or "").strip()
        if not cleaned:
            return
        token_hash = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
        conn = self._db_connect()
        try:
            conn.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (token_hash,))
            conn.commit()
        finally:
            conn.close()

