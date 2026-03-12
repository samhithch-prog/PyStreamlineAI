import hashlib
import base64
import hmac
import html
import io
import json
import os
import re
import secrets
import sqlite3
import smtplib
import time
import zipfile
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from functools import lru_cache
from typing import Any
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import pdfplumber
import streamlit as st
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from src.controller.app_controller import run_app_runtime
from src.dto.auth_dto import PasswordResetInputDTO
from src.dto.runtime_dto import AppRuntimeHandlersDTO, PageConfigDTO
from src.repository.auth_repository import AuthRepository
from src.service.auth_service import AuthService, AuthServiceDependencies
from src.ui.auth_view import render_password_policy_checklist
from src.ui.styles import render_app_styles as render_ui_styles

try:
    import psycopg
except Exception:
    psycopg = None

LOGO_IMAGE_PATH = os.path.join("assets", "logo.png")
BOT_WELCOME_MESSAGE = "I am ZoSwi. Ask me about your Resume and JD analysis."
BOT_LAUNCHER_ICON = "\U0001F916"
BOT_ASSISTANT_AVATAR = "\U0001F916"
USER_AVATAR = "\U0001F9D1"
AUTH_COOKIE_NAME = "pystreamline_auth"
AUTH_SESSION_TTL_DAYS = 14
PBKDF2_ITERATIONS = 210000
EMAIL_OTP_DIGITS = 6
EMAIL_CODE_NAME = "Secure Code"
EMAIL_OTP_TTL_MINUTES_DEFAULT = 10
EMAIL_OTP_RESEND_SECONDS_DEFAULT = 60
EMAIL_OTP_MAX_ATTEMPTS_DEFAULT = 5
PASSWORD_RESET_RESEND_SECONDS_DEFAULT = 30
SIGNUP_REQUEST_TTL_HOURS_DEFAULT = 24
DEFAULT_APP_TIMEZONE = "America/New_York"
MIN_JOB_DESCRIPTION_WORDS = 25
MIN_JOB_DESCRIPTION_CHARS = 120
CODING_STAGE_COUNT = 3
CODING_LANGUAGES = [
    "Python",
    "Java",
    "JavaScript",
    "TypeScript",
    "Go",
    "C++",
]
PUBLIC_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "yahoo.co.in",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "msn.com",
    "icloud.com",
    "aol.com",
    "protonmail.com",
    "pm.me",
    "mail.com",
    "gmx.com",
    "zoho.com",
    "yandex.com",
}


class DBCursor:
    def __init__(
        self,
        raw_cursor: Any,
        connection: "DBConnection",
        lastrowid: int | None = None,
        prefetched_row: Any = None,
    ) -> None:
        self._raw_cursor = raw_cursor
        self._connection = connection
        self._lastrowid = lastrowid
        self._prefetched_row = prefetched_row
        self._prefetched_used = False

    @property
    def rowcount(self) -> int:
        return int(getattr(self._raw_cursor, "rowcount", 0) or 0)

    @property
    def lastrowid(self) -> int | None:
        return self._lastrowid

    def _column_names(self) -> list[str]:
        desc = getattr(self._raw_cursor, "description", None) or []
        names: list[str] = []
        for col in desc:
            if isinstance(col, (tuple, list)):
                names.append(str(col[0]))
            else:
                names.append(str(getattr(col, "name", "")))
        return names

    def _convert_row(self, row: Any) -> Any:
        if row is None:
            return None
        if self._connection.row_factory == sqlite3.Row:
            names = self._column_names()
            if not names:
                return dict(row) if isinstance(row, dict) else row
            if isinstance(row, dict):
                return row
            return dict(zip(names, row))
        return row

    def fetchone(self) -> Any:
        if not self._prefetched_used and self._prefetched_row is not None:
            self._prefetched_used = True
            return self._convert_row(self._prefetched_row)
        row = self._raw_cursor.fetchone()
        return self._convert_row(row)

    def fetchall(self) -> list[Any]:
        rows = self._raw_cursor.fetchall()
        if self._connection.row_factory == sqlite3.Row:
            return [self._convert_row(row) for row in rows]
        return rows


class DBConnection:
    def __init__(self, raw_connection: Any, backend: str) -> None:
        self._raw_connection = raw_connection
        self.backend = backend
        self._row_factory: Any = None

    @property
    def row_factory(self) -> Any:
        return self._row_factory

    @row_factory.setter
    def row_factory(self, value: Any) -> None:
        self._row_factory = value
        if self.backend == "sqlite":
            self._raw_connection.row_factory = value

    def _convert_placeholders(self, sql: str) -> str:
        if self.backend == "sqlite":
            return sql
        return sql.replace("?", "%s")

    def _should_returning_id(self, sql: str) -> bool:
        if self.backend != "postgres":
            return False
        sql_upper = sql.strip().upper()
        return sql_upper.startswith("INSERT INTO") and " RETURNING " not in sql_upper

    def execute(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> DBCursor:
        clean_sql = self._convert_placeholders(sql)
        raw_cursor = self._raw_connection.cursor()
        param_values = tuple(params) if isinstance(params, list) else params
        if self._should_returning_id(clean_sql):
            insert_sql = clean_sql.rstrip().rstrip(";") + " RETURNING id"
            raw_cursor.execute(insert_sql, param_values)
            inserted = raw_cursor.fetchone()
            inserted_id = int(inserted[0]) if inserted and inserted[0] is not None else None
            return DBCursor(raw_cursor, self, lastrowid=inserted_id, prefetched_row=inserted)
        raw_cursor.execute(clean_sql, param_values)
        return DBCursor(raw_cursor, self, lastrowid=getattr(raw_cursor, "lastrowid", None))

    def commit(self) -> None:
        self._raw_connection.commit()

    def rollback(self) -> None:
        self._raw_connection.rollback()

    def close(self) -> None:
        self._raw_connection.close()


def get_database_url() -> str:
    env_url = str(os.getenv("DATABASE_URL", "")).strip()
    if env_url:
        return env_url
    try:
        db_cfg = st.secrets.get("database")
        if hasattr(db_cfg, "get"):
            return str(db_cfg.get("url", "")).strip()
    except Exception:
        pass
    return ""


def using_postgres() -> bool:
    db_url = get_database_url().lower()
    return db_url.startswith("postgres://") or db_url.startswith("postgresql://")


def get_config_value(
    env_key: str,
    secret_section: str = "",
    secret_key: str = "",
    default: str = "",
) -> str:
    env_value = str(os.getenv(env_key, "")).strip()
    if env_value:
        return env_value

    target_key = str(secret_key or env_key).strip()
    try:
        if secret_section:
            section = st.secrets.get(secret_section)
            if hasattr(section, "get"):
                section_value = section.get(target_key, "")
                return str(section_value or "").strip() or str(default or "").strip()
        sectionless_value = st.secrets.get(target_key, "")
        return str(sectionless_value or "").strip() or str(default or "").strip()
    except Exception:
        return str(default or "").strip()


def get_db_setting_value(setting_key: str) -> str:
    cleaned_key = str(setting_key or "").strip()
    if not cleaned_key:
        return ""
    conn = db_connect()
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT setting_value
            FROM app_settings
            WHERE setting_key = ?
            LIMIT 1
            """,
            (cleaned_key,),
        ).fetchone()
        if row is None:
            return ""
        if isinstance(row, dict):
            return str(row.get("setting_value", "") or "").strip()
        return str(row[0] or "").strip()
    except Exception:
        return ""
    finally:
        conn.close()


def parse_bool(raw_value: str, default: bool = False) -> bool:
    cleaned = str(raw_value or "").strip().lower()
    if not cleaned:
        return default
    return cleaned in {"1", "true", "yes", "on", "y"}


def parse_int(raw_value: str, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(str(raw_value or "").strip())
    except Exception:
        parsed = default
    return max(min_value, min(max_value, parsed))


@lru_cache(maxsize=8)
def resolve_timezone(tz_name: str) -> Any:
    cleaned_name = str(tz_name or "").strip()
    if not cleaned_name:
        return timezone.utc
    try:
        return ZoneInfo(cleaned_name)
    except Exception:
        return timezone.utc


def get_app_timezone() -> Any:
    configured_tz = get_config_value("APP_TIMEZONE", "app", "timezone", DEFAULT_APP_TIMEZONE)
    resolved = resolve_timezone(configured_tz)
    if resolved == timezone.utc and str(configured_tz or "").strip() not in {"UTC", "Etc/UTC", "Z"}:
        return resolve_timezone(DEFAULT_APP_TIMEZONE)
    return resolved


def db_connect() -> DBConnection:
    db_url = get_database_url()
    if not db_url:
        raise RuntimeError("DATABASE_URL is required. Configure PostgreSQL in env or Streamlit secrets.")
    if not using_postgres():
        raise RuntimeError("DATABASE_URL must use a PostgreSQL URL (postgresql:// or postgres://).")
    if psycopg is None:
        raise RuntimeError("PostgreSQL selected but psycopg is not installed.")
    raw_conn = psycopg.connect(db_url)
    return DBConnection(raw_conn, "postgres")


def get_table_columns(conn: DBConnection, table_name: str) -> set[str]:
    if conn.backend == "postgres":
        rows = conn.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = ?
            """,
            (table_name,),
        ).fetchall()
        names: set[str] = set()
        for row in rows:
            if isinstance(row, dict):
                names.add(str(row.get("column_name", "")).strip())
            elif isinstance(row, (tuple, list)) and row:
                names.add(str(row[0]).strip())
        return names
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]).strip() for row in rows}


def cleanup_expired_signup_verification_requests(max_rows: int = 200) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    limit_rows = max(1, int(max_rows or 1))
    conn = db_connect()
    try:
        conn.execute(
            """
            DELETE FROM signup_verification_requests
            WHERE id IN (
                SELECT id
                FROM signup_verification_requests
                WHERE expires_at <= ?
                ORDER BY id
                FOR UPDATE SKIP LOCKED
                LIMIT ?
            )
            """,
            (now_iso, limit_rows),
        )
        conn.commit()
    except Exception as ex:
        try:
            conn.rollback()
        except Exception:
            pass
        # Expired-request cleanup is best-effort; never fail app startup on lock contention.
        error_text = str(ex).lower()
        if "deadlock detected" in error_text or "could not obtain lock" in error_text:
            return
        raise
    finally:
        conn.close()


def is_unique_violation(exc: Exception) -> bool:
    if isinstance(exc, sqlite3.IntegrityError):
        return True
    msg = str(exc).lower()
    return "duplicate key value violates unique constraint" in msg or "unique constraint failed" in msg


def render_top_left_logo() -> None:
    if not os.path.exists(LOGO_IMAGE_PATH):
        return
    st.markdown(
        """
        <style>
        .st-key-top_logo {
            margin-top: -1.35rem;
            margin-left: -0.35rem;
            margin-bottom: 0.35rem;
        }
        .st-key-top_logo [data-testid="stImage"] {
            margin: 0 !important;
        }
        .st-key-top_logo img {
            max-width: 190px !important;
            height: auto !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    with st.container(key="top_logo"):
        st.image(LOGO_IMAGE_PATH, width=190)


@lru_cache(maxsize=1)
def get_logo_data_uri() -> str:
    if not os.path.exists(LOGO_IMAGE_PATH):
        return ""
    try:
        with open(LOGO_IMAGE_PATH, "rb") as image_file:
            raw_logo = image_file.read()
    except Exception:
        return ""
    if not raw_logo:
        return ""
    ext = os.path.splitext(LOGO_IMAGE_PATH)[1].strip().lower()
    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
    }
    mime_type = mime_map.get(ext, "image/png")
    encoded_logo = base64.b64encode(raw_logo).decode("ascii")
    return f"data:{mime_type};base64,{encoded_logo}"


def init_db() -> None:
    conn = db_connect()
    id_pk_sql = "BIGSERIAL PRIMARY KEY" if conn.backend == "postgres" else "INTEGER PRIMARY KEY AUTOINCREMENT"
    fk_type = "BIGINT" if conn.backend == "postgres" else "INTEGER"
    session_id_type = "BIGINT" if conn.backend == "postgres" else "INTEGER"

    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS users (
            id {id_pk_sql},
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT,
            years_experience TEXT,
            role_contact_email TEXT,
            profile_data TEXT,
            email_verified_at TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS analysis_history (
            id {id_pk_sql},
            user_id {fk_type} NOT NULL,
            score INTEGER NOT NULL,
            category TEXT NOT NULL,
            summary TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS chat_history (
            id {id_pk_sql},
            user_id {fk_type} NOT NULL,
            session_id {session_id_type},
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id {id_pk_sql},
            user_id {fk_type} NOT NULL,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS auth_sessions (
            id {id_pk_sql},
            user_id {fk_type} NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS user_login_events (
            id {id_pk_sql},
            user_id {fk_type} NOT NULL,
            login_method TEXT NOT NULL,
            login_provider TEXT,
            login_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS user_email_otp_events (
            id {id_pk_sql},
            user_id {fk_type} NOT NULL,
            email TEXT NOT NULL,
            code_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            consumed_at TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS signup_verification_requests (
            id {id_pk_sql},
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            years_experience TEXT,
            role_contact_email TEXT,
            profile_data TEXT,
            promo_code TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            otp_code_hash TEXT,
            otp_sent_at TEXT,
            otp_expires_at TEXT,
            otp_attempts INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS promo_codes (
            id {id_pk_sql},
            code TEXT NOT NULL UNIQUE,
            description TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            max_uses INTEGER,
            uses_count INTEGER NOT NULL DEFAULT 0,
            expires_at TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS promo_redemptions (
            id {id_pk_sql},
            code TEXT NOT NULL,
            email TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(code, email)
        )
        """
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS app_settings (
            id {id_pk_sql},
            setting_key TEXT NOT NULL UNIQUE,
            setting_value TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    user_cols = get_table_columns(conn, "users")
    added_email_verified_col = False
    if "role_contact_email" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN role_contact_email TEXT")
    if "profile_data" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN profile_data TEXT")
    if "email_verified_at" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN email_verified_at TEXT")
        added_email_verified_col = True
    if added_email_verified_col:
        conn.execute("UPDATE users SET email_verified_at = created_at WHERE email_verified_at IS NULL")

    chat_cols = get_table_columns(conn, "chat_history")
    if "session_id" not in chat_cols:
        conn.execute(f"ALTER TABLE chat_history ADD COLUMN session_id {session_id_type}")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_analysis_history_user_id ON analysis_history(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_history_user_id ON chat_history(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_history_session_id ON chat_history(session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id ON chat_sessions(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated_at ON chat_sessions(updated_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires_at ON auth_sessions(expires_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_login_events_user_id ON user_login_events(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_login_events_login_at ON user_login_events(login_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_email_otp_events_user_id ON user_email_otp_events(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_email_otp_events_email ON user_email_otp_events(email)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_email_otp_events_expires_at ON user_email_otp_events(expires_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_signup_verification_requests_email ON signup_verification_requests(email)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_signup_verification_requests_expires_at ON signup_verification_requests(expires_at)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_promo_codes_code ON promo_codes(code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_promo_redemptions_email ON promo_redemptions(email)")

    legacy_users = conn.execute(
        """
        SELECT DISTINCT user_id
        FROM chat_history
        WHERE session_id IS NULL
        """
    ).fetchall()
    for row in legacy_users:
        legacy_user_id = int(row[0] if not isinstance(row, dict) else row.get("user_id", 0) or 0)
        if legacy_user_id <= 0:
            continue
        now_iso = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            """
            INSERT INTO chat_sessions (user_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (legacy_user_id, "Imported Chat", now_iso, now_iso),
        )
        imported_session_id = int(cur.lastrowid or 0)
        if imported_session_id > 0:
            conn.execute(
                """
                UPDATE chat_history
                SET session_id = ?
                WHERE user_id = ? AND session_id IS NULL
                """,
                (imported_session_id, legacy_user_id),
            )
    conn.commit()
    conn.close()
    try:
        cleanup_expired_signup_verification_requests()
    except Exception:
        # Cleanup must not block app initialization.
        pass


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${derived.hex()}"


def is_modern_password_hash(password_hash: str) -> bool:
    return str(password_hash).startswith("pbkdf2_sha256$")


def verify_password(password: str, stored_hash: str) -> bool:
    cleaned_hash = str(stored_hash or "").strip()
    if cleaned_hash.startswith("pbkdf2_sha256$"):
        try:
            _, iterations_raw, salt_hex, digest_hex = cleaned_hash.split("$", 3)
            iterations = int(iterations_raw)
            salt = bytes.fromhex(salt_hex)
            expected_digest = bytes.fromhex(digest_hex)
            computed_digest = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt,
                iterations,
            )
            return hmac.compare_digest(computed_digest, expected_digest)
        except Exception:
            return False

    legacy_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return hmac.compare_digest(legacy_hash, cleaned_hash)


def get_email_otp_pepper() -> str:
    explicit = get_config_value("OTP_PEPPER", "email_otp", "pepper")
    if explicit:
        return explicit
    # Fallback to existing auth cookie secret so OTP can work without an extra mandatory key.
    return get_config_value("AUTH_COOKIE_SECRET", "auth", "cookie_secret")


def get_email_otp_ttl_minutes() -> int:
    return parse_int(
        get_config_value(
            "EMAIL_OTP_TTL_MINUTES",
            "email_otp",
            "ttl_minutes",
            str(EMAIL_OTP_TTL_MINUTES_DEFAULT),
        ),
        EMAIL_OTP_TTL_MINUTES_DEFAULT,
        1,
        30,
    )


def get_email_otp_resend_seconds() -> int:
    return parse_int(
        get_config_value(
            "EMAIL_OTP_RESEND_SECONDS",
            "email_otp",
            "resend_seconds",
            str(EMAIL_OTP_RESEND_SECONDS_DEFAULT),
        ),
        EMAIL_OTP_RESEND_SECONDS_DEFAULT,
        10,
        600,
    )


def get_password_reset_resend_seconds() -> int:
    return parse_int(
        get_config_value(
            "PASSWORD_RESET_OTP_RESEND_SECONDS",
            "email_otp",
            "password_reset_resend_seconds",
            str(PASSWORD_RESET_RESEND_SECONDS_DEFAULT),
        ),
        PASSWORD_RESET_RESEND_SECONDS_DEFAULT,
        10,
        600,
    )


def get_email_otp_max_attempts() -> int:
    return parse_int(
        get_config_value(
            "EMAIL_OTP_MAX_ATTEMPTS",
            "email_otp",
            "max_attempts",
            str(EMAIL_OTP_MAX_ATTEMPTS_DEFAULT),
        ),
        EMAIL_OTP_MAX_ATTEMPTS_DEFAULT,
        1,
        10,
    )


def get_signup_request_ttl_hours() -> int:
    return parse_int(
        get_config_value(
            "SIGNUP_REQUEST_TTL_HOURS",
            "email_otp",
            "signup_request_ttl_hours",
            str(SIGNUP_REQUEST_TTL_HOURS_DEFAULT),
        ),
        SIGNUP_REQUEST_TTL_HOURS_DEFAULT,
        1,
        72,
    )


def get_smtp_settings() -> dict[str, Any]:
    host = get_config_value("SMTP_HOST", "smtp", "host")
    port = parse_int(
        get_config_value("SMTP_PORT", "smtp", "port", "587"),
        587,
        1,
        65535,
    )
    username = get_config_value("SMTP_USERNAME", "smtp", "username")
    password = get_config_value("SMTP_PASSWORD", "smtp", "password")
    from_email = get_config_value("SMTP_FROM_EMAIL", "smtp", "from_email")
    use_tls = parse_bool(
        get_config_value("SMTP_USE_TLS", "smtp", "use_tls", "true"),
        default=True,
    )
    return {
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "from_email": from_email,
        "use_tls": use_tls,
    }


def can_send_email_otp() -> tuple[bool, str]:
    pepper = get_email_otp_pepper()
    if not pepper:
        return False, "Email verification is not configured: missing code secret."

    smtp_cfg = get_smtp_settings()
    if not smtp_cfg["host"] or not smtp_cfg["from_email"]:
        return False, "Email verification is not configured: missing SMTP host/from email."
    if bool(smtp_cfg["username"]) != bool(smtp_cfg["password"]):
        return False, "Email verification is not configured: SMTP username/password must both be set."
    return True, ""


def hash_email_otp(otp_code: str) -> str:
    pepper = get_email_otp_pepper()
    if not pepper:
        raise RuntimeError("Missing email verification secret configuration.")
    raw = f"{str(otp_code).strip()}:{pepper}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_email_otp_code() -> str:
    upper = 10**EMAIL_OTP_DIGITS
    return f"{secrets.randbelow(upper):0{EMAIL_OTP_DIGITS}d}"


def send_email_otp_message(recipient_email: str, otp_code: str, ttl_minutes: int) -> tuple[bool, str]:
    smtp_cfg = get_smtp_settings()
    if not smtp_cfg["host"] or not smtp_cfg["from_email"]:
        return False, "Email verification sender is not configured."

    message = EmailMessage()
    message["Subject"] = "Your PyStreamlineAI verification code"
    message["From"] = smtp_cfg["from_email"]
    message["To"] = recipient_email
    message.set_content(
        "\n".join(
            [
                "Use this one-time verification code for PyStreamlineAI:",
                "",
                otp_code,
                "",
                f"This code expires in {ttl_minutes} minutes.",
                "If you did not request this, ignore this email.",
            ]
        )
    )

    try:
        with smtplib.SMTP(str(smtp_cfg["host"]), int(smtp_cfg["port"]), timeout=20) as smtp:
            if bool(smtp_cfg["use_tls"]):
                smtp.starttls()
            if smtp_cfg["username"] and smtp_cfg["password"]:
                smtp.login(str(smtp_cfg["username"]), str(smtp_cfg["password"]))
            smtp.send_message(message)
        return True, "Verification code sent."
    except Exception:
        return False, "Unable to send verification email right now."


def get_user_identity_by_email(email: str) -> dict[str, Any] | None:
    cleaned_email = str(email or "").strip().lower()
    if not cleaned_email:
        return None
    conn = db_connect()
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
        return dict(row) if row is not None else None
    finally:
        conn.close()


def get_pending_signup_request_by_email(email: str) -> dict[str, Any] | None:
    cleaned_email = str(email or "").strip().lower()
    if not cleaned_email:
        return None
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = db_connect()
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT *
            FROM signup_verification_requests
            WHERE email = ? AND expires_at > ?
            LIMIT 1
            """,
            (cleaned_email, now_iso),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def get_pending_signup_request_by_id_email(request_id: int, email: str) -> dict[str, Any] | None:
    cleaned_email = str(email or "").strip().lower()
    if request_id <= 0 or not cleaned_email:
        return None
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = db_connect()
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT *
            FROM signup_verification_requests
            WHERE id = ? AND email = ? AND expires_at > ?
            LIMIT 1
            """,
            (request_id, cleaned_email, now_iso),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def create_or_update_signup_verification_request(
    full_name: str,
    email: str,
    password: str,
    role: str,
    years_experience: str,
    role_contact_email: str = "",
    profile_data: dict[str, Any] | None = None,
    promo_code: str = "",
) -> tuple[bool, str, int]:
    cleaned_email = str(email or "").strip().lower()
    cleaned_role_contact_email = str(role_contact_email or "").strip().lower()
    normalized_role = str(role or "").strip().title()
    cleaned_years = str(years_experience or "").strip()
    cleaned_profile = profile_data if isinstance(profile_data, dict) else {}
    profile_payload = json.dumps(cleaned_profile, separators=(",", ":")) if cleaned_profile else None
    normalized_promo = normalize_promo_code(promo_code)

    password_ok, password_msg = validate_password_strength(password)
    if not password_ok:
        return False, password_msg, 0

    if user_exists_for_signup(cleaned_email, cleaned_role_contact_email):
        return False, "User exists, please login.", 0

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    request_expires = (now + timedelta(hours=get_signup_request_ttl_hours())).isoformat()
    password_hash = hash_password(password)

    conn = db_connect()
    conn.row_factory = sqlite3.Row
    try:
        existing = conn.execute(
            """
            SELECT id
            FROM signup_verification_requests
            WHERE email = ?
            LIMIT 1
            """,
            (cleaned_email,),
        ).fetchone()

        if existing is None:
            cur = conn.execute(
                """
                INSERT INTO signup_verification_requests (
                    full_name, email, password_hash, role, years_experience, role_contact_email, profile_data,
                    promo_code, created_at, updated_at, expires_at, otp_code_hash, otp_sent_at, otp_expires_at, otp_attempts
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, 0)
                """,
                (
                    full_name.strip(),
                    cleaned_email,
                    password_hash,
                    normalized_role,
                    cleaned_years,
                    cleaned_role_contact_email or None,
                    profile_payload,
                    normalized_promo or None,
                    now_iso,
                    now_iso,
                    request_expires,
                ),
            )
            request_id = int(cur.lastrowid or 0)
        else:
            request_id = int(existing["id"] if isinstance(existing, dict) else existing[0])
            conn.execute(
                """
                UPDATE signup_verification_requests
                SET
                    full_name = ?,
                    password_hash = ?,
                    role = ?,
                    years_experience = ?,
                    role_contact_email = ?,
                    profile_data = ?,
                    promo_code = ?,
                    updated_at = ?,
                    expires_at = ?,
                    otp_code_hash = NULL,
                    otp_sent_at = NULL,
                    otp_expires_at = NULL,
                    otp_attempts = 0
                WHERE id = ?
                """,
                (
                    full_name.strip(),
                    password_hash,
                    normalized_role,
                    cleaned_years,
                    cleaned_role_contact_email or None,
                    profile_payload,
                    normalized_promo or None,
                    now_iso,
                    request_expires,
                    request_id,
                ),
            )
        conn.commit()
        if request_id <= 0:
            return False, "Unable to start verification right now. Please try again.", 0
        return True, "Verification started.", request_id
    finally:
        conn.close()


def send_signup_verification_otp(request_id: int, email: str) -> tuple[bool, str]:
    cleaned_email = str(email or "").strip().lower()
    if request_id <= 0 or not cleaned_email:
        return False, "Verification request is invalid."

    request = get_pending_signup_request_by_id_email(request_id, cleaned_email)
    if request is None:
        return False, "Verification request expired. Create account again."

    config_ok, config_msg = can_send_email_otp()
    if not config_ok:
        return False, config_msg

    now = datetime.now(timezone.utc)
    resend_seconds = get_email_otp_resend_seconds()
    otp_sent_at = str(request.get("otp_sent_at") or "").strip()
    if otp_sent_at:
        resend_after = (now - timedelta(seconds=resend_seconds)).isoformat()
        if otp_sent_at > resend_after:
            return False, f"Please wait {resend_seconds} seconds before requesting another code."

    ttl_minutes = get_email_otp_ttl_minutes()
    otp_code = generate_email_otp_code()
    sent, send_msg = send_email_otp_message(cleaned_email, otp_code, ttl_minutes)
    if not sent:
        return False, send_msg

    now_iso = now.isoformat()
    otp_hash = hash_email_otp(otp_code)
    otp_expires = (now + timedelta(minutes=ttl_minutes)).isoformat()
    conn = db_connect()
    try:
        conn.execute(
            """
            UPDATE signup_verification_requests
            SET otp_code_hash = ?, otp_sent_at = ?, otp_expires_at = ?, otp_attempts = 0, updated_at = ?
            WHERE id = ? AND email = ?
            """,
            (otp_hash, now_iso, otp_expires, now_iso, request_id, cleaned_email),
        )
        conn.commit()
        return True, "Verification code sent to your email."
    finally:
        conn.close()


def create_verified_user_from_signup_request(request: dict[str, Any]) -> tuple[bool, str]:
    email = str(request.get("email", "")).strip().lower()
    if not email:
        return False, "Signup request data is invalid."
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = db_connect()
    conn.row_factory = sqlite3.Row
    try:
        existing = conn.execute(
            """
            SELECT id
            FROM users
            WHERE email = ?
            LIMIT 1
            """,
            (email,),
        ).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO users (
                    full_name, email, password_hash, role, years_experience, role_contact_email, profile_data,
                    email_verified_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(request.get("full_name", "")).strip() or email.split("@")[0],
                    email,
                    str(request.get("password_hash", "")).strip(),
                    str(request.get("role", "")).strip(),
                    str(request.get("years_experience", "")).strip(),
                    str(request.get("role_contact_email", "")).strip() or None,
                    str(request.get("profile_data", "")).strip() or None,
                    now_iso,
                    str(request.get("created_at", "")).strip() or now_iso,
                ),
            )
        else:
            conn.execute(
                "UPDATE users SET email_verified_at = COALESCE(email_verified_at, ?) WHERE email = ?",
                (now_iso, email),
            )
        conn.commit()
    except Exception as ex:
        if not is_unique_violation(ex):
            return False, "Unable to finalize account creation right now."
    finally:
        conn.close()

    return True, "Email verified and account created. You can now log in."


def verify_signup_verification_otp(request_id: int, email: str, otp_code: str) -> tuple[bool, str]:
    cleaned_email = str(email or "").strip().lower()
    cleaned_code = re.sub(r"\D", "", str(otp_code or "").strip())
    if request_id <= 0 or not cleaned_email:
        return False, "Verification request is invalid."
    if len(cleaned_code) != EMAIL_OTP_DIGITS:
        return False, f"Enter the {EMAIL_OTP_DIGITS}-digit verification code."
    if not get_email_otp_pepper():
        return False, "Email verification is not configured: missing code secret."

    request = get_pending_signup_request_by_id_email(request_id, cleaned_email)
    if request is None:
        return False, "Verification request expired. Create account again."

    otp_hash = str(request.get("otp_code_hash", "")).strip()
    otp_expires = str(request.get("otp_expires_at", "")).strip()
    if not otp_hash or not otp_expires:
        return False, "No active verification code found. Request a new code."

    now_iso = datetime.now(timezone.utc).isoformat()
    if otp_expires <= now_iso:
        return False, "Verification code expired. Request a new code."

    max_attempts = get_email_otp_max_attempts()
    attempts = int(request.get("otp_attempts", 0) or 0)
    if attempts >= max_attempts:
        return False, "Too many attempts. Request a new code."

    expected_hash = hash_email_otp(cleaned_code)
    if not hmac.compare_digest(otp_hash, expected_hash):
        conn = db_connect()
        try:
            conn.execute(
                "UPDATE signup_verification_requests SET otp_attempts = otp_attempts + 1 WHERE id = ? AND email = ?",
                (request_id, cleaned_email),
            )
            conn.commit()
        finally:
            conn.close()
        remaining = max(0, max_attempts - (attempts + 1))
        if remaining <= 0:
            return False, "Invalid code. Too many attempts. Request a new code."
        return False, f"Invalid code. {remaining} attempts remaining."

    created_ok, created_msg = create_verified_user_from_signup_request(request)
    if not created_ok:
        return False, created_msg

    conn = db_connect()
    try:
        conn.execute(
            "DELETE FROM signup_verification_requests WHERE id = ? AND email = ?",
            (request_id, cleaned_email),
        )
        conn.commit()
    finally:
        conn.close()
    return True, created_msg


def promo_codes_enabled() -> bool:
    return parse_bool(
        get_config_value("PROMO_CODES_ENABLED", "promo", "enabled", "false"),
        default=False,
    )


def mark_pending_email_verification(ref_id: int, email: str, mode: str = "signup_request") -> None:
    st.session_state.email_verification_ref_id = int(ref_id or 0)
    st.session_state.email_verification_email = str(email or "").strip().lower()
    st.session_state.email_verification_mode = str(mode or "").strip().lower() or "signup_request"


def clear_pending_email_verification() -> None:
    st.session_state.email_verification_ref_id = 0
    st.session_state.email_verification_email = ""
    st.session_state.email_verification_mode = ""


def normalize_auth_view(raw_value: str) -> str:
    cleaned = str(raw_value or "").strip().lower()
    if cleaned in {"create account", "create_account", "signup", "sign up", "register"}:
        return "Create Account"
    return "Login"


def auth_view_to_query_value(auth_view: str) -> str:
    return "signup" if normalize_auth_view(auth_view) == "Create Account" else "login"


def read_auth_view_from_query_params() -> str:
    try:
        raw_value = st.query_params.get("auth", "")
        if isinstance(raw_value, (list, tuple)):
            raw_value = raw_value[0] if raw_value else ""
        return normalize_auth_view(str(raw_value or ""))
    except Exception:
        return "Login"


def sync_auth_view_query_param(auth_view: str) -> None:
    target = auth_view_to_query_value(auth_view)
    try:
        current = st.query_params.get("auth", "")
        if isinstance(current, (list, tuple)):
            current = current[0] if current else ""
        if str(current or "").strip().lower() != target:
            st.query_params["auth"] = target
    except Exception:
        pass


def read_password_reset_from_query_params() -> bool:
    try:
        raw_value = st.query_params.get("pwreset", "")
        if isinstance(raw_value, (list, tuple)):
            raw_value = raw_value[0] if raw_value else ""
        cleaned = str(raw_value or "").strip().lower()
        return cleaned in {"1", "true", "yes", "on"}
    except Exception:
        return False


def sync_password_reset_query_param(enabled: bool) -> None:
    try:
        if enabled:
            st.query_params["pwreset"] = "1"
            return
        if "pwreset" in st.query_params:
            del st.query_params["pwreset"]
    except Exception:
        pass


def send_email_verification_otp(
    user_id: int,
    email: str,
    resend_seconds_override: int | None = None,
) -> tuple[bool, str]:
    cleaned_email = str(email or "").strip().lower()
    if user_id <= 0 or not cleaned_email:
        return False, "Email verification target is invalid."

    config_ok, config_msg = can_send_email_otp()
    if not config_ok:
        return False, config_msg

    ttl_minutes = get_email_otp_ttl_minutes()
    resend_seconds = (
        parse_int(str(resend_seconds_override), get_email_otp_resend_seconds(), 10, 600)
        if resend_seconds_override is not None
        else get_email_otp_resend_seconds()
    )
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    wait_threshold = (now - timedelta(seconds=resend_seconds)).isoformat()

    conn = db_connect()
    conn.row_factory = sqlite3.Row
    try:
        recent = conn.execute(
            """
            SELECT created_at
            FROM user_email_otp_events
            WHERE user_id = ? AND email = ? AND created_at > ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user_id, cleaned_email, wait_threshold),
        ).fetchone()
    finally:
        conn.close()

    if recent is not None:
        return False, f"Please wait {resend_seconds} seconds before requesting another code."

    otp_code = generate_email_otp_code()
    sent, send_msg = send_email_otp_message(cleaned_email, otp_code, ttl_minutes)
    if not sent:
        return False, send_msg

    otp_hash = hash_email_otp(otp_code)
    expires_iso = (now + timedelta(minutes=ttl_minutes)).isoformat()
    conn = db_connect()
    try:
        conn.execute(
            """
            INSERT INTO user_email_otp_events (user_id, email, code_hash, created_at, expires_at, consumed_at, attempts)
            VALUES (?, ?, ?, ?, ?, NULL, 0)
            """,
            (user_id, cleaned_email, otp_hash, now_iso, expires_iso),
        )
        conn.commit()
        return True, "Verification code sent to your email."
    finally:
        conn.close()


def verify_email_verification_otp(user_id: int, email: str, otp_code: str) -> tuple[bool, str]:
    cleaned_email = str(email or "").strip().lower()
    cleaned_code = re.sub(r"\D", "", str(otp_code or "").strip())
    if user_id <= 0 or not cleaned_email:
        return False, "Email verification target is invalid."
    if len(cleaned_code) != EMAIL_OTP_DIGITS:
        return False, f"Enter the {EMAIL_OTP_DIGITS}-digit verification code."

    if not get_email_otp_pepper():
        return False, "Email verification is not configured: missing code secret."

    max_attempts = get_email_otp_max_attempts()
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = db_connect()
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT id, code_hash, attempts, expires_at
            FROM user_email_otp_events
            WHERE user_id = ? AND email = ? AND consumed_at IS NULL
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user_id, cleaned_email),
        ).fetchone()
        if row is None:
            return False, "No active verification code found. Request a new code."

        if str(row["expires_at"] or "") <= now_iso:
            return False, "Verification code expired. Request a new code."

        attempts = int(row["attempts"] or 0)
        if attempts >= max_attempts:
            return False, "Too many attempts. Request a new code."

        expected_hash = hash_email_otp(cleaned_code)
        if not hmac.compare_digest(str(row["code_hash"] or ""), expected_hash):
            conn.execute(
                "UPDATE user_email_otp_events SET attempts = attempts + 1 WHERE id = ?",
                (int(row["id"]),),
            )
            conn.commit()
            remaining = max(0, max_attempts - (attempts + 1))
            if remaining <= 0:
                return False, "Invalid code. Too many attempts. Request a new code."
            return False, f"Invalid code. {remaining} attempts remaining."

        conn.execute(
            "UPDATE user_email_otp_events SET consumed_at = ? WHERE id = ?",
            (now_iso, int(row["id"])),
        )
        conn.execute(
            "UPDATE users SET email_verified_at = COALESCE(email_verified_at, ?) WHERE id = ?",
            (now_iso, user_id),
        )
        conn.commit()
        return True, "Email verified successfully. You can now log in."
    finally:
        conn.close()


def normalize_promo_code(raw_code: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "", str(raw_code or "").strip().upper())
    return cleaned[:64]


def extract_email_domain(email: str) -> str:
    cleaned_email = str(email or "").strip().lower()
    if "@" not in cleaned_email:
        return ""
    local_part, domain_part = cleaned_email.split("@", 1)
    if not local_part or not domain_part:
        return ""
    return domain_part.strip()


def is_university_email_domain(domain: str) -> bool:
    cleaned_domain = str(domain or "").strip().lower()
    if not cleaned_domain:
        return False
    return (
        cleaned_domain.endswith(".edu")
        or ".edu." in cleaned_domain
        or ".ac." in cleaned_domain
    )


def is_valid_email_address(email: str) -> bool:
    domain = extract_email_domain(email)
    return bool(domain and "." in domain and not domain.startswith(".") and not domain.endswith("."))


def validate_signup_email_for_role(email: str, role: str) -> tuple[bool, str]:
    if not is_valid_email_address(email):
        return False, "Enter a valid email address."
    return True, ""


def validate_role_specific_email(role: str, role_email: str) -> tuple[bool, str]:
    normalized_role = str(role or "").strip().title()
    if normalized_role not in {"Recruiter", "Student"}:
        return True, ""

    cleaned_role_email = str(role_email or "").strip().lower()
    if not cleaned_role_email:
        if normalized_role == "Recruiter":
            return False, "Recruiter Email is required for recruiter accounts."
        return False, "University Email is required for student accounts."
    if not is_valid_email_address(cleaned_role_email):
        return False, "Enter a valid role-specific email address."

    domain = extract_email_domain(cleaned_role_email)
    if normalized_role == "Recruiter" and domain in PUBLIC_EMAIL_DOMAINS:
        return False, "Recruiter accounts require an organization email (not personal email domains)."
    if normalized_role == "Student" and not is_university_email_domain(domain):
        return False, "Student accounts require a university email domain (for example, .edu)."
    return True, ""


def normalize_profile_text(raw_value: Any, max_len: int = 160) -> str:
    return str(raw_value or "").strip()[:max_len]


def get_password_policy_status(password: str) -> dict[str, bool]:
    raw_password = str(password or "")
    return {
        "min_length": len(raw_password) >= 8,
        "has_upper": re.search(r"[A-Z]", raw_password) is not None,
        "has_special": re.search(r"[^\w\s]", raw_password) is not None,
    }


def validate_password_strength(password: str) -> tuple[bool, str]:
    policy = get_password_policy_status(password)
    if not policy["min_length"]:
        return False, "Password must be at least 8 characters long."
    if not policy["has_upper"]:
        return False, "Password must include at least one uppercase letter."
    if not policy["has_special"]:
        return False, "Password must include at least one special character (for example: @ or %)."
    return True, ""


def validate_role_profile_inputs(
    role: str,
    years_experience: str,
    profile_data: dict[str, Any] | None = None,
) -> tuple[bool, str, str, dict[str, str]]:
    normalized_role = str(role or "").strip().title()
    incoming_profile = profile_data if isinstance(profile_data, dict) else {}
    cleaned_years = str(years_experience or "").strip()

    if normalized_role == "Candidate":
        if not cleaned_years:
            return False, "Years of Experience is required for candidate accounts.", "", {}
        if not re.fullmatch(r"\d{1,2}(\.\d{1})?", cleaned_years):
            return (
                False,
                "Enter Years of Experience as a number (for example: 0, 2, or 5.5).",
                "",
                {},
            )
        if float(cleaned_years) > 50:
            return False, "Years of Experience must be between 0 and 50.", "", {}

        candidate_profile: dict[str, str] = {}
        target_role = normalize_profile_text(incoming_profile.get("target_role"), max_len=120)
        if target_role:
            candidate_profile["target_role"] = target_role
        return True, "", cleaned_years, candidate_profile

    if normalized_role == "Student":
        university_name = normalize_profile_text(incoming_profile.get("university_name"), max_len=120)
        graduation_year_raw = normalize_profile_text(incoming_profile.get("graduation_year"), max_len=4)
        degree_program = normalize_profile_text(incoming_profile.get("degree_program"), max_len=120)

        if not university_name:
            return False, "University Name is required for student accounts.", "", {}
        if not re.fullmatch(r"\d{4}", graduation_year_raw):
            return False, "Graduation Year must be a 4-digit year.", "", {}

        graduation_year = int(graduation_year_raw)
        current_year = datetime.now(timezone.utc).year
        if graduation_year < current_year - 10 or graduation_year > current_year + 10:
            return False, "Graduation Year is out of allowed range.", "", {}

        student_profile: dict[str, str] = {
            "university_name": university_name,
            "graduation_year": str(graduation_year),
        }
        if degree_program:
            student_profile["degree_program"] = degree_program
        return True, "", "", student_profile

    if normalized_role == "Recruiter":
        organization_name = normalize_profile_text(incoming_profile.get("organization_name"), max_len=120)
        recruiter_title = normalize_profile_text(incoming_profile.get("recruiter_title"), max_len=120)
        hiring_focus = normalize_profile_text(incoming_profile.get("hiring_focus"), max_len=160)

        if not organization_name:
            return False, "Organization Name is required for recruiter accounts.", "", {}

        recruiter_profile: dict[str, str] = {"organization_name": organization_name}
        if recruiter_title:
            recruiter_profile["recruiter_title"] = recruiter_title
        if hiring_focus:
            recruiter_profile["hiring_focus"] = hiring_focus
        return True, "", "", recruiter_profile

    return True, "", cleaned_years, {}


def user_exists_for_signup(email: str, role_contact_email: str = "") -> bool:
    cleaned_email = str(email or "").strip().lower()
    cleaned_role_contact_email = str(role_contact_email or "").strip().lower()
    emails_to_check = sorted(
        {
            candidate_email
            for candidate_email in [cleaned_email, cleaned_role_contact_email]
            if candidate_email
        }
    )
    if not emails_to_check:
        return False

    placeholders = ", ".join(["?"] * len(emails_to_check))
    conn = db_connect()
    try:
        existing_user = conn.execute(
            f"""
            SELECT id
            FROM users
            WHERE email IN ({placeholders})
               OR role_contact_email IN ({placeholders})
            LIMIT 1
            """,
            tuple(emails_to_check + emails_to_check),
        ).fetchone()
        return existing_user is not None
    finally:
        conn.close()


def sync_promo_codes_from_secrets() -> None:
    try:
        promo_cfg = st.secrets.get("promo")
    except Exception:
        return
    if not promo_cfg:
        return

    raw_codes = promo_cfg.get("valid_codes", [])
    if isinstance(raw_codes, str):
        raw_codes = [raw_codes]
    if not isinstance(raw_codes, (list, tuple, set)):
        return

    cleaned_codes = []
    for raw_code in raw_codes:
        normalized = normalize_promo_code(str(raw_code or ""))
        if normalized:
            cleaned_codes.append(normalized)
    if not cleaned_codes:
        return

    now_iso = datetime.now(timezone.utc).isoformat()
    conn = db_connect()
    try:
        for code in sorted(set(cleaned_codes)):
            conn.execute(
                """
                INSERT INTO promo_codes (code, description, is_active, created_at)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(code) DO UPDATE SET is_active = 1
                """,
                (code, "Configured from secrets", now_iso),
            )
        conn.commit()
    finally:
        conn.close()


def validate_promo_code(raw_code: str) -> tuple[bool, str, str]:
    normalized = normalize_promo_code(raw_code)
    if not normalized:
        return False, "Enter a promo code.", ""

    now_iso = datetime.now(timezone.utc).isoformat()
    conn = db_connect()
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT code, is_active, max_uses, uses_count, expires_at
            FROM promo_codes
            WHERE code = ?
            LIMIT 1
            """,
            (normalized,),
        ).fetchone()
        total_row = conn.execute("SELECT COUNT(1) AS total_count FROM promo_codes").fetchone()
        if isinstance(total_row, dict):
            total_codes = int(total_row.get("total_count", 0) or 0)
        else:
            total_codes = int((total_row or [0])[0] or 0)
    finally:
        conn.close()

    if row is None:
        if total_codes <= 0:
            return False, "No promo codes are configured yet.", normalized
        return False, "Promo code is invalid.", normalized
    if int(row["is_active"] or 0) != 1:
        return False, "Promo code is inactive.", normalized

    expires_at = str(row["expires_at"] or "").strip()
    if expires_at and expires_at <= now_iso:
        return False, "Promo code has expired.", normalized

    max_uses = row["max_uses"]
    if max_uses is not None:
        if int(row["uses_count"] or 0) >= int(max_uses):
            return False, "Promo code has reached its usage limit.", normalized

    return True, "Promo code applied.", normalized


def redeem_promo_code(raw_code: str, email: str) -> tuple[bool, str]:
    is_valid, message, normalized = validate_promo_code(raw_code)
    if not is_valid:
        return False, message

    cleaned_email = str(email or "").strip().lower()
    if not cleaned_email:
        return False, "Email is required to redeem promo code."

    now_iso = datetime.now(timezone.utc).isoformat()
    conn = db_connect()
    conn.row_factory = sqlite3.Row
    try:
        existing = conn.execute(
            """
            SELECT 1
            FROM promo_redemptions
            WHERE code = ? AND email = ?
            LIMIT 1
            """,
            (normalized, cleaned_email),
        ).fetchone()
        if existing is not None:
            return False, "This promo code was already used for this email."

        cur = conn.execute(
            """
            UPDATE promo_codes
            SET uses_count = uses_count + 1
            WHERE code = ?
              AND is_active = 1
              AND (expires_at IS NULL OR expires_at > ?)
              AND (max_uses IS NULL OR uses_count < max_uses)
            """,
            (normalized, now_iso),
        )
        if int(cur.rowcount or 0) <= 0:
            conn.rollback()
            return False, "Promo code is no longer available."

        conn.execute(
            """
            INSERT INTO promo_redemptions (code, email, created_at)
            VALUES (?, ?, ?)
            """,
            (normalized, cleaned_email, now_iso),
        )
        conn.commit()
        return True, "Promo code applied."
    finally:
        conn.close()


def create_user(
    full_name: str,
    email: str,
    password: str,
    role: str,
    years_experience: str,
    role_contact_email: str = "",
    confirm_password: str | None = None,
    profile_data: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    if confirm_password is not None and password != confirm_password:
        return False, "Passwords do not match."
    password_ok, password_msg = validate_password_strength(password)
    if not password_ok:
        return False, password_msg
    normalized_role = str(role or "").strip().title()
    if normalized_role not in {"Candidate", "Student", "Recruiter"}:
        return False, "Please choose Candidate, Student, or Recruiter."
    email_ok, email_msg = validate_signup_email_for_role(email, normalized_role)
    if not email_ok:
        return False, email_msg
    role_email_ok, role_email_msg = validate_role_specific_email(normalized_role, role_contact_email)
    if not role_email_ok:
        return False, role_email_msg
    profile_ok, profile_msg, cleaned_years_experience, cleaned_profile = validate_role_profile_inputs(
        normalized_role,
        years_experience,
        profile_data,
    )
    if not profile_ok:
        return False, profile_msg
    cleaned_email = str(email or "").strip().lower()
    cleaned_role_contact_email = str(role_contact_email or "").strip().lower()
    role_contact_value = cleaned_role_contact_email if cleaned_role_contact_email else None
    profile_payload = json.dumps(cleaned_profile, separators=(",", ":")) if cleaned_profile else None
    if user_exists_for_signup(cleaned_email, cleaned_role_contact_email):
        return False, "User exists, please login."

    conn = db_connect()
    try:
        conn.execute(
            """
            INSERT INTO users (
                full_name, email, password_hash, role, years_experience, role_contact_email, profile_data, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                full_name.strip(),
                cleaned_email,
                hash_password(password),
                normalized_role,
                cleaned_years_experience,
                role_contact_value,
                profile_payload,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        return True, "Account created successfully. Verify your email to continue."
    except Exception as ex:
        if is_unique_violation(ex):
            return False, "User exists, please login."
        return False, "Unable to create account right now. Please try again."
    finally:
        conn.close()


def get_auth_repository() -> AuthRepository:
    return AuthRepository(db_connect=db_connect, auth_session_ttl_days=AUTH_SESSION_TTL_DAYS)


def update_password_and_revoke_sessions(user_id: int, password_hash: str) -> None:
    repo = get_auth_repository()
    repo.update_password_and_revoke_sessions(user_id, password_hash)


def get_auth_service() -> AuthService:
    deps = AuthServiceDependencies(
        email_code_name=EMAIL_CODE_NAME,
        is_valid_email_address=is_valid_email_address,
        can_send_email_otp=can_send_email_otp,
        get_user_by_email=get_user_by_email,
        get_password_reset_resend_seconds=get_password_reset_resend_seconds,
        send_email_verification_otp=send_email_verification_otp,
        validate_password_strength=validate_password_strength,
        verify_email_verification_otp=verify_email_verification_otp,
        hash_password=hash_password,
        update_password_and_revoke_sessions=update_password_and_revoke_sessions,
    )
    return AuthService(deps)


def authenticate_user(email: str, password: str) -> dict[str, Any] | None:
    repo = get_auth_repository()
    return repo.authenticate_user(
        email=email,
        password=password,
        verify_password=verify_password,
        is_modern_password_hash=is_modern_password_hash,
        hash_password=hash_password,
    )


def get_user_by_email(email: str) -> dict[str, Any] | None:
    repo = get_auth_repository()
    return repo.get_user_by_email(email)


def parse_wait_seconds_from_message(message: str) -> int:
    message_text = str(message or "").strip().lower()
    match = re.search(r"wait\s+(\d+)\s+seconds", message_text)
    if match is None:
        return 0
    try:
        return max(0, int(match.group(1)))
    except Exception:
        return 0


def send_password_reset_otp(email: str) -> tuple[bool, str]:
    auth_service = get_auth_service()
    result = auth_service.send_password_reset_code(email)
    return result.ok, result.message


def reset_password_with_email_otp(
    email: str,
    otp_code: str,
    new_password: str,
    confirm_password: str,
) -> tuple[bool, str]:
    auth_service = get_auth_service()
    result = auth_service.reset_password_with_code(
        PasswordResetInputDTO(
            email=str(email or ""),
            otp_code=str(otp_code or ""),
            new_password=str(new_password or ""),
            confirm_password=str(confirm_password or ""),
        )
    )
    return result.ok, result.message


def record_user_login_event(user_id: int, login_method: str, login_provider: str = "") -> None:
    repo = get_auth_repository()
    repo.record_user_login_event(user_id, login_method, login_provider)


def get_user_login_stats(user_id: int) -> dict[str, Any]:
    if user_id <= 0:
        return {"login_count": 0, "last_login_at": ""}
    conn = db_connect()
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) AS login_count, MAX(login_at) AS last_login_at
            FROM user_login_events
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
        if row is None:
            return {"login_count": 0, "last_login_at": ""}
        if isinstance(row, dict):
            return {
                "login_count": int(row.get("login_count", 0) or 0),
                "last_login_at": str(row.get("last_login_at", "") or ""),
            }
        return {"login_count": int(row[0] or 0), "last_login_at": str(row[1] or "")}
    finally:
        conn.close()


def create_auth_session(user_id: int, ttl_days: int = AUTH_SESSION_TTL_DAYS) -> str:
    repo = get_auth_repository()
    return repo.create_auth_session(user_id, ttl_days)


def get_user_for_auth_session(raw_token: str) -> dict[str, Any] | None:
    cleaned = str(raw_token or "").strip()
    if not cleaned:
        return None
    token_hash = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = db_connect()
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT u.id, u.full_name, u.email, u.role, u.years_experience, u.created_at
            FROM auth_sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = ? AND s.expires_at > ? AND u.email_verified_at IS NOT NULL
            LIMIT 1
            """,
            (token_hash, now_iso),
        ).fetchone()
        if row is None:
            conn.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (token_hash,))
            conn.commit()
            return None

        conn.execute(
            "UPDATE auth_sessions SET last_seen_at = ? WHERE token_hash = ?",
            (now_iso, token_hash),
        )
        conn.commit()
        return dict(row)
    finally:
        conn.close()


def revoke_auth_session(raw_token: str) -> None:
    repo = get_auth_repository()
    repo.revoke_auth_session(raw_token)


def queue_set_auth_cookie(raw_token: str) -> None:
    st.session_state.auth_cookie_value = str(raw_token or "").strip() or None
    st.session_state.auth_cookie_clear = False


def queue_clear_auth_cookie() -> None:
    st.session_state.auth_cookie_value = None
    st.session_state.auth_cookie_clear = True


def render_auth_cookie_sync() -> None:
    cookie_value = st.session_state.get("auth_cookie_value")
    should_clear = bool(st.session_state.get("auth_cookie_clear"))
    if not cookie_value and not should_clear:
        return

    safe_name = json.dumps(AUTH_COOKIE_NAME)
    max_age = int(AUTH_SESSION_TTL_DAYS * 24 * 60 * 60)
    if should_clear:
        script = f"""
        <script>
        (function () {{
            const name = {safe_name};
            document.cookie = name + "=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax";
        }})();
        </script>
        """
    else:
        safe_value = json.dumps(str(cookie_value))
        script = f"""
        <script>
        (function () {{
            const name = {safe_name};
            const value = {safe_value};
            const securePart = window.location.protocol === "https:" ? "; Secure" : "";
            document.cookie =
                name + "=" + encodeURIComponent(value) + "; path=/; max-age={max_age}; SameSite=Lax" + securePart;
        }})();
        </script>
        """

    st.components.v1.html(script, height=0)
    st.session_state.auth_cookie_value = None
    st.session_state.auth_cookie_clear = False


def try_restore_user_from_cookie() -> None:
    if st.session_state.get("user") is not None:
        return
    if bool(st.session_state.get("auth_cookie_clear")):
        return
    cookie_value = str(st.context.cookies.get(AUTH_COOKIE_NAME, "")).strip()
    if not cookie_value:
        return
    restored = get_user_for_auth_session(cookie_value)
    if restored:
        st.session_state.user = restored
        st.session_state.auth_session_token = cookie_value
        st.session_state.bot_user_email = None
        return
    queue_clear_auth_cookie()


def get_streamlit_oauth_user_info() -> dict[str, Any]:
    try:
        info = st.user.to_dict()
        if isinstance(info, dict):
            return info
    except Exception:
        pass
    return {}


def get_oauth_redirect_uri() -> str:
    env_redirect = str(os.getenv("AUTH_REDIRECT_URI", "")).strip()
    if env_redirect:
        return env_redirect
    try:
        auth_cfg = st.secrets.get("auth")
        if hasattr(auth_cfg, "get"):
            return str(auth_cfg.get("redirect_uri", "")).strip()
    except Exception:
        pass
    return ""


def get_runtime_app_origin() -> str:
    try:
        headers = st.context.headers
    except Exception:
        headers = {}
    host = str(headers.get("x-forwarded-host") or headers.get("host") or "").strip()
    if not host:
        return ""
    proto_raw = str(headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    proto = proto_raw if proto_raw in {"http", "https"} else ""
    if not proto:
        proto = "http" if host.startswith("localhost") or host.startswith("127.0.0.1") else "https"
    return f"{proto}://{host}"


def get_expected_oauth_redirect_uri() -> str:
    origin = get_runtime_app_origin().rstrip("/")
    if not origin:
        return ""
    return f"{origin}/oauth2callback"


def oauth_redirect_uri_mismatch() -> tuple[bool, str, str]:
    configured = get_oauth_redirect_uri()
    expected = get_expected_oauth_redirect_uri()
    if not configured or not expected:
        return False, configured, expected
    try:
        configured_host = str(urlsplit(configured).netloc or "").strip().lower()
        expected_host = str(urlsplit(expected).netloc or "").strip().lower()
    except Exception:
        return False, configured, expected
    if not configured_host or not expected_host:
        return False, configured, expected
    localhost_hosts = {"localhost", "localhost:8501", "127.0.0.1", "127.0.0.1:8501"}
    if expected_host in localhost_hosts:
        return False, configured, expected
    if configured_host in localhost_hosts:
        return True, configured, expected
    if configured.rstrip("/") != expected.rstrip("/"):
        return True, configured, expected
    return False, configured, expected


def is_streamlit_oauth_logged_in() -> bool:
    info = get_streamlit_oauth_user_info()
    if "is_logged_in" in info:
        return bool(info.get("is_logged_in"))
    try:
        raw_state = getattr(st.user, "is_logged_in")
        if raw_state is not None:
            return bool(raw_state)
    except Exception:
        pass
    return bool(info.get("email") or info.get("sub"))


def is_streamlit_oauth_configured() -> bool:
    try:
        auth_cfg = st.secrets.get("auth")
        return bool(auth_cfg)
    except Exception:
        return False


def get_streamlit_oauth_provider_name(preferred_provider: str | None = None) -> str | None:
    try:
        auth_cfg = st.secrets.get("auth")
        if not auth_cfg:
            return None
        preferred = str(preferred_provider or "").strip().lower()
        required_keys = {"client_id", "client_secret", "server_metadata_url"}
        auth_keys = set(auth_cfg.keys())
        # If these keys are present at [auth], Streamlit default provider works.
        if required_keys.issubset(auth_keys):
            if preferred and preferred not in {"google", "default"}:
                return None
            return None
        shared_auth_keys = {
            "redirect_uri",
            "cookie_secret",
            "client_id",
            "client_secret",
            "server_metadata_url",
            "client_kwargs",
        }
        providers: list[str] = []
        for key in auth_keys:
            key_text = str(key)
            if key_text in shared_auth_keys:
                continue
            section = auth_cfg.get(key)
            if hasattr(section, "keys"):
                providers.append(key_text)
        if not providers:
            return None
        if preferred:
            for provider_name in providers:
                if provider_name.lower() == preferred:
                    return provider_name
            return None
        return sorted(providers)[0]
    except Exception:
        return None
    return None


def is_streamlit_oauth_provider_available(provider_name: str) -> bool:
    preferred = str(provider_name or "").strip().lower()
    if not preferred:
        return False
    try:
        auth_cfg = st.secrets.get("auth")
        if not auth_cfg:
            return False
        required_keys = {"client_id", "client_secret", "server_metadata_url"}
        auth_keys = set(auth_cfg.keys())
        if required_keys.issubset(auth_keys):
            return preferred in {"google", "default"}
        provider = get_streamlit_oauth_provider_name(preferred)
        return bool(provider)
    except Exception:
        return False


def detect_oauth_provider(identity: dict[str, Any]) -> str:
    provider = str(identity.get("provider", "")).strip().lower()
    if provider in {"google", "linkedin"}:
        return provider
    issuer = str(identity.get("iss", "")).strip().lower()
    if "google" in issuer:
        return "google"
    if "linkedin" in issuer:
        return "linkedin"
    return "oauth"


def get_or_create_user_from_oauth_identity(identity: dict[str, Any]) -> dict[str, Any] | None:
    email = str(identity.get("email", "")).strip().lower()
    if not email:
        return None

    full_name = str(identity.get("name", "")).strip()
    if not full_name:
        given = str(identity.get("given_name", "")).strip()
        family = str(identity.get("family_name", "")).strip()
        full_name = " ".join(part for part in [given, family] if part).strip()
    if not full_name:
        full_name = email.split("@")[0] or "OAuth User"

    conn = db_connect()
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT id, full_name, email, role, years_experience, created_at, email_verified_at
            FROM users
            WHERE email = ?
            LIMIT 1
            """,
            (email,),
        ).fetchone()
        if row is not None:
            if not str(row["email_verified_at"] or "").strip():
                now_iso = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    "UPDATE users SET email_verified_at = ? WHERE id = ?",
                    (now_iso, int(row["id"])),
                )
                conn.commit()
                row = conn.execute(
                    """
                    SELECT id, full_name, email, role, years_experience, created_at, email_verified_at
                    FROM users
                    WHERE id = ?
                    LIMIT 1
                    """,
                    (int(row["id"]),),
                ).fetchone()
            return dict(row)

        now_iso = datetime.now(timezone.utc).isoformat()
        random_password = secrets.token_urlsafe(24)
        cur = conn.execute(
            """
            INSERT INTO users (full_name, email, password_hash, role, years_experience, email_verified_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (full_name, email, hash_password(random_password), "", "", now_iso, now_iso),
        )
        user_id = int(cur.lastrowid or 0)
        conn.commit()
        if user_id <= 0:
            return None
        return {
            "id": user_id,
            "full_name": full_name,
            "email": email,
            "role": "",
            "years_experience": "",
            "created_at": now_iso,
        }
    finally:
        conn.close()


def sync_user_from_oauth_session() -> None:
    if not is_streamlit_oauth_logged_in():
        return
    identity = get_streamlit_oauth_user_info()
    user = get_or_create_user_from_oauth_identity(identity)
    if user is None:
        return

    current = st.session_state.get("user")
    current_email = str((current or {}).get("email", "")).strip().lower()
    if current_email == str(user.get("email", "")).strip().lower():
        return

    user_id = int(user.get("id") or 0)
    record_user_login_event(user_id, "oauth", detect_oauth_provider(identity))
    full_name = str(user.get("full_name", "")).strip()
    clear_pending_email_verification()
    st.session_state.user = user
    st.session_state.bot_user_email = None
    st.session_state.active_chat_id = None
    st.session_state.bot_open = True
    st.session_state.bot_messages = default_bot_messages(full_name)
    st.session_state.bot_pending_prompt = None
    st.session_state.zoswi_submit = False
    st.session_state.clear_zoswi_input = True
    st.session_state.full_chat_submit = False
    st.session_state.clear_full_chat_input = True
    st.session_state.dashboard_view = "home"
    st.session_state.user_menu_open = False
    st.session_state.auth_session_token = None


def save_analysis_history(user_id: int, result: dict[str, Any]) -> None:
    if user_id <= 0:
        return
    try:
        conn = db_connect()
        conn.execute(
            """
            INSERT INTO analysis_history (user_id, score, category, summary, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                user_id,
                int(result.get("score", 0)),
                str(result.get("category", "")).strip() or "Not Relevant",
                str(result.get("summary", "")).strip()[:3000],
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_recent_analysis_history(user_id: int, limit: int = 5) -> list[dict[str, Any]]:
    if user_id <= 0:
        return []
    conn = db_connect()
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT score, category, summary, created_at
            FROM analysis_history
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def create_chat_session(user_id: int, title: str = "New Chat") -> int:
    if user_id <= 0:
        return 0
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = db_connect()
    try:
        cur = conn.execute(
            """
            INSERT INTO chat_sessions (user_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, title.strip() or "New Chat", now_iso, now_iso),
        )
        conn.commit()
        return int(cur.lastrowid or 0)
    finally:
        conn.close()


def get_recent_chat_sessions(user_id: int, limit: int = 12) -> list[dict[str, Any]]:
    if user_id <= 0:
        return []
    conn = db_connect()
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM chat_sessions
            WHERE user_id = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def rename_chat_session(user_id: int, session_id: int, new_title: str) -> bool:
    cleaned = " ".join(str(new_title).strip().split())
    if user_id <= 0 or session_id <= 0 or not cleaned:
        return False
    conn = db_connect()
    try:
        cur = conn.execute(
            """
            UPDATE chat_sessions
            SET title = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (cleaned[:70], datetime.now(timezone.utc).isoformat(), session_id, user_id),
        )
        conn.commit()
        return int(cur.rowcount or 0) > 0
    finally:
        conn.close()


def delete_chat_session(user_id: int, session_id: int) -> bool:
    if user_id <= 0 or session_id <= 0:
        return False
    conn = db_connect()
    try:
        exists = conn.execute(
            "SELECT id FROM chat_sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        ).fetchone()
        if not exists:
            return False
        conn.execute(
            "DELETE FROM chat_history WHERE user_id = ? AND session_id = ?",
            (user_id, session_id),
        )
        conn.execute(
            "DELETE FROM chat_sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def get_chat_messages_for_session(user_id: int, session_id: int) -> list[dict[str, str]]:
    if user_id <= 0 or session_id <= 0:
        return []
    conn = db_connect()
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT ch.role, ch.content
            FROM chat_history ch
            JOIN chat_sessions cs ON cs.id = ch.session_id
            WHERE ch.user_id = ? AND ch.session_id = ? AND cs.user_id = ?
            ORDER BY ch.id ASC
            """,
            (user_id, session_id, user_id),
        ).fetchall()
        return [{"role": str(row["role"]), "content": str(row["content"])} for row in rows]
    finally:
        conn.close()


def load_chat_session_into_state(user_id: int, session_id: int, full_name: str) -> None:
    if user_id <= 0 or session_id <= 0:
        return
    loaded = get_chat_messages_for_session(user_id, session_id)
    st.session_state.active_chat_id = session_id
    st.session_state.bot_messages = loaded or default_bot_messages(full_name)
    st.session_state.bot_pending_prompt = None
    st.session_state.clear_zoswi_input = True
    st.session_state.clear_full_chat_input = True


def infer_chat_title_from_intent(source_text: str) -> str:
    cleaned = " ".join(source_text.strip().split())
    if not cleaned:
        return "Resume and JD Support"

    # Remove polite filler so title focuses on intent.
    cleaned = re.sub(
        r"^(please\s+|can you\s+|could you\s+|would you\s+|i need\s+|i want\s+|help me\s+|"
        r"share me\s+|show me\s+|tell me\s+|give me\s+|can u\s+)",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()

    tokens = re.findall(r"[a-zA-Z0-9+#.]+", cleaned.lower())
    stop_words = {
        "please",
        "can",
        "you",
        "me",
        "my",
        "the",
        "a",
        "an",
        "is",
        "are",
        "to",
        "for",
        "of",
        "and",
        "with",
        "help",
        "about",
        "on",
        "this",
        "that",
        "in",
        "it",
    }
    filtered = [tok for tok in tokens if tok not in stop_words]
    if "jd" in tokens and "analysis" in tokens:
        return "JD Analysis Summary"
    if "resume" in tokens and ("jd" in tokens or "job" in tokens or "description" in tokens):
        return "Resume JD Match Guidance"
    if "resume" in tokens and ("improve" in tokens or "update" in tokens or "rewrite" in tokens):
        return "Resume Improvement Guidance"
    if "ats" in tokens or "keyword" in tokens:
        return "ATS Keyword Suggestions"
    if "resume" in tokens:
        return "Resume Improvement Guidance"
    if "jd" in tokens or ("job" in tokens and "description" in tokens):
        return "Job Description Analysis"
    if "mulesoft" in tokens:
        return "MuleSoft Skill Highlights"
    if "interview" in tokens:
        return "Interview Preparation Guidance"
    if not filtered:
        return "Career Guidance Chat"
    return " ".join(word.title() for word in filtered[:6])


def backfill_default_chat_titles(user_id: int, max_sessions: int = 30) -> None:
    if user_id <= 0:
        return
    conn = db_connect()
    conn.row_factory = sqlite3.Row
    try:
        sessions = conn.execute(
            """
            SELECT id
            FROM chat_sessions
            WHERE user_id = ? AND (title = '' OR title = 'New Chat' OR title = 'Imported Chat')
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, max_sessions),
        ).fetchall()
        for row in sessions:
            session_id = int(row["id"])
            first_user = conn.execute(
                """
                SELECT content
                FROM chat_history
                WHERE user_id = ? AND session_id = ? AND role = 'user'
                ORDER BY id ASC
                LIMIT 1
                """,
                (user_id, session_id),
            ).fetchone()
            if not first_user or not str(first_user["content"]).strip():
                continue
            title = infer_chat_title_from_intent(str(first_user["content"]))[:70]
            conn.execute(
                "UPDATE chat_sessions SET title = ? WHERE id = ?",
                (title, session_id),
            )
        conn.commit()
    finally:
        conn.close()


def update_chat_session_title_if_default(session_id: int, source_text: str) -> None:
    cleaned = " ".join(source_text.strip().split())
    if session_id <= 0 or not cleaned:
        return
    conn = db_connect()
    conn.row_factory = sqlite3.Row
    try:
        existing_row = conn.execute(
            "SELECT title FROM chat_sessions WHERE id = ? LIMIT 1",
            (session_id,),
        ).fetchone()
        existing_title = str(existing_row["title"]).strip() if existing_row else ""
        if existing_title not in {"", "New Chat", "Imported Chat"}:
            return
        title = infer_chat_title_from_intent(cleaned)[:70]
        conn.execute(
            """
            UPDATE chat_sessions
            SET title = ?, updated_at = ?
            WHERE id = ? AND (title = 'New Chat' OR title = '')
            """,
            (title, datetime.now(timezone.utc).isoformat(), session_id),
        )
        conn.commit()
    finally:
        conn.close()


def save_chat_history(user_id: int, session_id: int, role: str, content: str) -> None:
    normalized_role = role.strip().lower()
    cleaned = content.strip()
    if (
        user_id <= 0
        or session_id <= 0
        or normalized_role not in {"user", "assistant"}
        or not cleaned
    ):
        return
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = db_connect()
    try:
        conn.execute(
            """
            INSERT INTO chat_history (user_id, session_id, role, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                user_id,
                session_id,
                normalized_role,
                cleaned[:6000],
                now_iso,
            ),
        )
        conn.execute(
            "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
            (now_iso, session_id),
        )
        conn.commit()
    finally:
        conn.close()


def format_history_time(raw_iso: str) -> str:
    try:
        parsed = datetime.fromisoformat(str(raw_iso))
        return parsed.strftime("%b %d, %I:%M %p")
    except Exception:
        return str(raw_iso)


def format_history_date_short(raw_iso: str) -> str:
    try:
        parsed = datetime.fromisoformat(str(raw_iso))
        return parsed.strftime("%m/%d")
    except Exception:
        return "--/--"


def extract_pdf_text(file_bytes: bytes) -> str:
    text_parts: list[str] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            text_parts.append(page_text)
    return "\n".join(text_parts).strip()


def extract_docx_text(file_bytes: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as docx_zip:
        xml_content = docx_zip.read("word/document.xml")
    root = ET.fromstring(xml_content)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    text_nodes = root.findall(".//w:t", namespace)
    return "\n".join(node.text for node in text_nodes if node.text).strip()


def extract_resume_text(uploaded_file) -> str:
    file_name = uploaded_file.name.lower()
    file_bytes = uploaded_file.getvalue()
    if file_name.endswith(".pdf"):
        return extract_pdf_text(file_bytes)
    if file_name.endswith(".docx"):
        return extract_docx_text(file_bytes)
    raise ValueError("Unsupported file type. Please upload a PDF or DOCX file.")


def build_missing_jd_points(analysis_result: dict[str, Any]) -> list[str]:
    points: list[str] = []
    if not isinstance(analysis_result, dict):
        return points
    for key in ("gaps", "recommendations"):
        raw_items = analysis_result.get(key, [])
        if not isinstance(raw_items, list):
            continue
        for item in raw_items:
            cleaned = str(item or "").strip()
            if cleaned:
                points.append(cleaned)
    deduped: list[str] = []
    seen: set[str] = set()
    for item in points:
        token = re.sub(r"\s+", " ", item).strip().lower()
        if token and token not in seen:
            seen.add(token)
            deduped.append(item)
    return deduped[:12]


def _looks_like_client_name(candidate: str, allow_lowercase_name: bool = False) -> bool:
    value = re.sub(r"\s+", " ", str(candidate or "")).strip(" \t-:|,;")
    if not value:
        return False
    low = value.lower()
    blocked_exact = {
        "client",
        "clients",
        "client name",
        "end client",
        "customer",
        "account",
        "n/a",
        "na",
        "none",
        "unknown",
        "confidential",
        "multiple clients",
        "various clients",
    }
    if low in blocked_exact:
        return False
    tokens = re.findall(r"[A-Za-z0-9&()./\-]+", value)
    if not tokens or len(tokens) > 7:
        return False
    descriptor_words = {
        "real",
        "time",
        "transaction",
        "processing",
        "customer",
        "facing",
        "application",
        "applications",
        "billing",
        "support",
        "development",
        "domain",
        "services",
        "platform",
        "project",
        "projects",
        "role",
        "responsibilities",
        "experience",
        "work",
    }
    descriptor_hits = sum(1 for token in tokens if token.lower() in descriptor_words)
    if descriptor_hits >= max(2, (len(tokens) // 2) + 1):
        return False
    connector_words = {"of", "and", "the", "&", "for"}
    org_hint_words = {
        "bank",
        "corp",
        "corporation",
        "company",
        "co",
        "inc",
        "llc",
        "ltd",
        "limited",
        "technologies",
        "technology",
        "tech",
        "systems",
        "solutions",
        "financial",
        "finance",
        "services",
        "group",
        "holdings",
        "software",
        "telecom",
        "communications",
        "industries",
        "global",
        "enterprise",
        "america",
    }
    has_org_like_token = False
    has_org_hint = False
    for token in tokens:
        low = token.lower()
        if low in connector_words:
            continue
        if low in org_hint_words:
            has_org_hint = True
        if token[0].isupper() or token.isupper() or any(ch.isdigit() for ch in token):
            has_org_like_token = True
            break
    if not has_org_like_token and len(tokens) > 1:
        if allow_lowercase_name and has_org_hint:
            return True
        return False
    return True


def _clean_client_name(raw_value: str, allow_lowercase_name: bool = False) -> str:
    value = re.sub(r"\s+", " ", str(raw_value or "")).strip(" \t-:|,;")
    if not value:
        return ""
    value = value.strip("'\"")
    value = re.split(
        r"\b(?:role|project|duration|location|technology|tech stack|environment|team|responsibilities)\b\s*[:\-]?",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip(" \t-:|,;")
    value = re.sub(r"\s{2,}", " ", value).strip(" \t-:|,;")
    if not _looks_like_client_name(value, allow_lowercase_name=allow_lowercase_name):
        return ""
    return value


def extract_client_names(resume_text: str, limit: int = 8) -> list[str]:
    lines = str(resume_text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    candidates: list[str] = []

    for raw in lines:
        line = re.sub(r"\s+", " ", str(raw or "")).strip()
        if not line:
            continue
        segments = [line]
        if "|" in line:
            segments.extend(part.strip() for part in line.split("|") if part.strip())

        for segment in segments:
            m = re.search(
                r"(?i)\b(?:end\s+client|client(?:\s*name)?)\b\s*[:\-]\s*(.+?)(?=\b(?:location|role|project|duration|environment|team)\b\s*[:\-]|$)",
                segment,
            )
            if m:
                cleaned = _clean_client_name(m.group(1), allow_lowercase_name=True)
                if cleaned:
                    candidates.append(cleaned)

            m_loc = re.search(
                r"(?i)\b([A-Z][A-Za-z0-9&()./\-]{1,}(?:\s+(?:[A-Z][A-Za-z0-9&()./\-]{1,}|of|and|the|&)){0,5})\s+\b(?:location|loc)\b\s*[:\-]",
                segment,
            )
            if m_loc:
                cleaned_loc = _clean_client_name(m_loc.group(1), allow_lowercase_name=True)
                if cleaned_loc:
                    candidates.append(cleaned_loc)

            m_for = re.search(
                r"(?i)\bfor\s+([A-Za-z][A-Za-z0-9&()./\-]{1,}(?:\s+[A-Za-z][A-Za-z0-9&()./\-]{1,}){0,4})\s+(?:client|account)\b",
                segment,
            )
            if m_for:
                cleaned_for = _clean_client_name(m_for.group(1), allow_lowercase_name=True)
                if cleaned_for:
                    candidates.append(cleaned_for)

            if re.search(r"(?i)\bclient\s+location\b", segment):
                m_table = re.search(
                    r"(?i)\bclient\s+location\b\s*[:\-]?\s*([A-Z][A-Za-z0-9&()./\-]{1,}(?:\s+[A-Z][A-Za-z0-9&()./\-]{1,}){0,4})",
                    segment,
                )
                if m_table:
                    cleaned_table = _clean_client_name(m_table.group(1), allow_lowercase_name=True)
                    if cleaned_table:
                        candidates.append(cleaned_table)

    deduped: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        token = item.lower()
        if token not in seen:
            seen.add(token)
            deduped.append(item)
    return deduped[: max(1, int(limit or 1))]


def infer_resume_context(resume_text: str) -> dict[str, list[str]]:
    resume_raw = str(resume_text or "")
    resume_lower = resume_raw.lower()
    domain_map: dict[str, list[str]] = {
        "banking_finance": ["bank", "banking", "fintech", "payment", "loan", "credit", "insurance", "trading"],
        "healthcare": ["healthcare", "health", "ehr", "hipaa", "clinical", "patient", "pharma"],
        "retail_ecommerce": ["retail", "ecommerce", "e-commerce", "inventory", "checkout", "catalog", "order"],
        "telecom": ["telecom", "telco", "network", "5g", "billing", "subscriber"],
        "manufacturing": ["manufacturing", "factory", "supply chain", "procurement", "warehouse"],
        "public_sector": ["government", "public sector", "federal", "state", "compliance"],
        "media": ["media", "streaming", "adtech", "content delivery", "cdn"],
    }
    detected_domains: list[str] = []
    for domain, keywords in domain_map.items():
        if any(keyword in resume_lower for keyword in keywords):
            detected_domains.append(domain)

    deduped_clients = extract_client_names(resume_raw, limit=8)
    return {
        "domains": detected_domains[:4],
        "clients": deduped_clients[:4],
    }


def build_targeted_resume_additions(
    resume_text: str,
    job_description: str,
    analysis_result: dict[str, Any],
) -> list[str]:
    base_points = build_missing_jd_points(analysis_result)
    if not base_points:
        return []
    context = infer_resume_context(resume_text)
    jd_tokens = set(re.findall(r"[a-zA-Z]{3,}", str(job_description or "").lower()))
    resume_tokens = set(re.findall(r"[a-zA-Z]{3,}", str(resume_text or "").lower()))
    dominant_tokens = jd_tokens.intersection(resume_tokens)
    domain_seed: set[str] = set()
    for domain in context.get("domains", []):
        domain_seed.update(re.findall(r"[a-zA-Z]{3,}", domain))

    def score_point(point: str) -> int:
        p_low = str(point or "").lower()
        p_tokens = set(re.findall(r"[a-zA-Z]{3,}", p_low))
        score = 0
        score += min(4, len(p_tokens.intersection(dominant_tokens)))
        score += min(3, len(p_tokens.intersection(jd_tokens)))
        score += min(2, len(p_tokens.intersection(domain_seed)))
        if any(tag in p_low for tag in ("client", "domain", "stakeholder", "business impact", "sla", "kpi")):
            score += 1
        return score

    ranked = sorted(base_points, key=score_point, reverse=True)
    selected = ranked[:6]
    deduped: list[str] = []
    seen: set[str] = set()
    for point in selected:
        cleaned = re.sub(r"\s+", " ", str(point or "")).strip()
        token = cleaned.lower()
        if cleaned and token not in seen:
            seen.add(token)
            deduped.append(cleaned)
    return deduped


def extract_experience_snippets(resume_text: str, limit: int = 20) -> list[str]:
    raw_lines = str(resume_text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    snippets: list[str] = []
    action_markers = (
        "develop",
        "built",
        "designed",
        "implemented",
        "led",
        "optimized",
        "migrat",
        "automated",
        "integrat",
        "deployed",
        "delivered",
        "improved",
        "reduced",
        "increased",
        "supported",
    )
    heading_markers = ("education", "skills", "certification", "summary", "objective")
    for raw in raw_lines:
        cleaned = re.sub(r"\s+", " ", str(raw or "")).strip(" \t-•*")
        if len(cleaned) < 24 or len(cleaned) > 260:
            continue
        lower = cleaned.lower()
        if any(marker in lower for marker in heading_markers):
            continue
        has_action = any(marker in lower for marker in action_markers)
        has_number = bool(re.search(r"\d", cleaned))
        has_client = "client" in lower
        if has_action or has_number or has_client:
            snippets.append(cleaned)
    deduped: list[str] = []
    seen: set[str] = set()
    for snippet in snippets:
        token = snippet.lower()
        if token not in seen:
            seen.add(token)
            deduped.append(snippet)
    return deduped[: max(1, int(limit or 1))]


def _tokenize_words(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z]{3,}", str(text or "").lower()))


def build_experience_backed_fallback_points(
    resume_text: str,
    job_description: str,
    analysis_result: dict[str, Any],
) -> list[str]:
    base_points = build_missing_jd_points(analysis_result)
    if not base_points:
        base_points = build_targeted_resume_additions(resume_text, job_description, analysis_result)
    return filter_points_missing_from_resume(base_points, resume_text)


def filter_points_missing_from_resume(
    points: list[str],
    resume_text: str,
) -> list[str]:
    resume_tokens = _tokenize_words(resume_text)
    resume_lines = [
        re.sub(r"\s+", " ", str(line or "")).strip()
        for line in str(resume_text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if str(line or "").strip()
    ]
    line_token_sets = [_tokenize_words(line) for line in resume_lines]
    accepted: list[str] = []
    seen: set[str] = set()
    for point in points:
        cleaned = re.sub(r"\s+", " ", str(point or "")).strip().strip("-•* ")
        if len(cleaned) < 12:
            continue
        token = cleaned.lower()
        if token in seen:
            continue
        p_tokens = _tokenize_words(cleaned)
        if not p_tokens:
            continue
        new_tokens = p_tokens.difference(resume_tokens)
        best_line_overlap_ratio = 0.0
        for line_tokens in line_token_sets:
            if not line_tokens:
                continue
            overlap = len(p_tokens.intersection(line_tokens))
            best_line_overlap_ratio = max(best_line_overlap_ratio, float(overlap) / float(max(1, len(p_tokens))))
        if len(new_tokens) >= 2 and best_line_overlap_ratio < 0.72:
            seen.add(token)
            accepted.append(cleaned)
    return accepted[:8]


def generate_realtime_experience_points(
    resume_text: str,
    job_description: str,
    analysis_result: dict[str, Any],
) -> list[str]:
    fallback_points = build_experience_backed_fallback_points(resume_text, job_description, analysis_result)
    snippets = extract_experience_snippets(resume_text, limit=18)
    if not snippets:
        return fallback_points

    key = get_openai_key()
    if not key:
        return fallback_points

    gaps = analysis_result.get("gaps", []) if isinstance(analysis_result, dict) else []
    recommendations = analysis_result.get("recommendations", []) if isinstance(analysis_result, dict) else []
    gaps_text = "\n".join(f"- {str(item).strip()}" for item in gaps if str(item).strip())
    rec_text = "\n".join(f"- {str(item).strip()}" for item in recommendations if str(item).strip())
    snippet_text = "\n".join(f"- {line}" for line in snippets)
    jd_excerpt = str(job_description or "").strip()
    jd_excerpt = jd_excerpt[:2800] + ("..." if len(jd_excerpt) > 2800 else "")

    prompt = f"""
You are a senior resume writer.
Generate high-impact resume points that are currently missing from the candidate's resume.

Return ONLY valid JSON:
{{
  "points": ["<point 1>", "<point 2>", "..."]
}}

Rules:
- Create 5 to 8 bullet points.
- Each point must be concise (max 28 words).
- Points must be JD-aligned and heavy-impact (ownership, scale, outcomes, reliability, stakeholder value).
- Every point must be plausible from candidate snippets; do not invent companies, clients, tools, years, or fake metrics.
- Do not repeat existing resume wording. Return only points that appear missing from current resume.
- Align to analysis gaps/recommendations and role requirements.

Candidate experience snippets:
{snippet_text}

JD:
{jd_excerpt}

Analysis gaps:
{gaps_text or "- None"}

Analysis recommendations:
{rec_text or "- None"}
    """.strip()

    try:
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2, api_key=key)
        raw = llm.invoke(prompt).content
        parsed = parse_json_response(str(raw))
        raw_points = parsed.get("points", []) if isinstance(parsed, dict) else []
        if not isinstance(raw_points, list):
            return fallback_points
        missing_points = filter_points_missing_from_resume(raw_points, resume_text)
        if missing_points:
            return missing_points[:8]
        return fallback_points
    except Exception:
        return fallback_points


def parse_resume_addition_points(raw_text: str) -> list[str]:
    lines = str(raw_text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    points: list[str] = []
    for line in lines:
        cleaned = re.sub(r"^\s*[-*•]+\s*", "", str(line or "")).strip()
        if len(cleaned) < 2:
            continue
        points.append(cleaned)
    deduped: list[str] = []
    seen: set[str] = set()
    for point in points:
        token = point.lower()
        if token not in seen:
            seen.add(token)
            deduped.append(point)
    return deduped[:12]


def build_append_only_export_text(resume_text: str, addition_points: list[str]) -> str:
    parts: list[str] = []
    parts.append(str(resume_text or "").strip())
    parts.append("")
    parts.append("JD-ALIGNED ADDITIONS (APPEND ONLY)")
    for point in addition_points:
        parts.append(f"- {point}")
    return "\n".join(parts).strip()


def append_points_to_existing_docx(
    source_docx_bytes: bytes,
    addition_points: list[str],
    section_title: str = "JD-Aligned Additions (Append Only)",
) -> bytes:
    if not source_docx_bytes:
        return b""
    points = [str(point or "").strip() for point in addition_points if str(point or "").strip()]
    if not points:
        return source_docx_bytes
    source = io.BytesIO(source_docx_bytes)
    with zipfile.ZipFile(source, mode="r") as zin:
        files = {name: zin.read(name) for name in zin.namelist()}
    document_key = "word/document.xml"
    if document_key not in files:
        return source_docx_bytes
    ns_uri = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    ns = {"w": ns_uri}
    xml_namespace = "http://www.w3.org/XML/1998/namespace"
    root = ET.fromstring(files[document_key])
    body = root.find("w:body", ns)
    if body is None:
        return source_docx_bytes

    sect_pr = body.find("w:sectPr", ns)
    insert_at = list(body).index(sect_pr) if sect_pr is not None else len(body)

    def make_paragraph(text: str, bold: bool = False) -> ET.Element:
        p = ET.Element(f"{{{ns_uri}}}p")
        r = ET.SubElement(p, f"{{{ns_uri}}}r")
        if bold:
            r_pr = ET.SubElement(r, f"{{{ns_uri}}}rPr")
            ET.SubElement(r_pr, f"{{{ns_uri}}}b")
        t = ET.SubElement(r, f"{{{ns_uri}}}t")
        t.set(f"{{{xml_namespace}}}space", "preserve")
        t.text = text
        return p

    additions: list[ET.Element] = [make_paragraph(""), make_paragraph(section_title, bold=True)]
    for point in points:
        additions.append(make_paragraph(f"• {point}"))
    for element in reversed(additions):
        body.insert(insert_at, element)

    files[document_key] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    out = io.BytesIO()
    with zipfile.ZipFile(out, mode="w", compression=zipfile.ZIP_DEFLATED) as zout:
        for name, payload in files.items():
            zout.writestr(name, payload)
    return out.getvalue()


def build_resume_editor_text(
    resume_text: str,
    analysis_result: dict[str, Any],
    job_description: str,
) -> str:
    base_resume = str(resume_text or "").strip()
    points = build_missing_jd_points(analysis_result)
    jd_snapshot = re.sub(r"\s+", " ", str(job_description or "").strip())
    jd_snapshot = jd_snapshot[:1300] + ("..." if len(jd_snapshot) > 1300 else "")
    parts: list[str] = []
    parts.append("RESUME (EDITABLE DRAFT)")
    parts.append("")
    parts.append(base_resume or "Add your resume content here.")
    parts.append("")
    parts.append("JD-ALIGNED POINTS TO CONSIDER ADDING (only if accurate)")
    if points:
        for point in points:
            parts.append(f"- {point}")
    else:
        parts.append("- No missing JD points were detected from current analysis.")
    parts.append("")
    parts.append("JOB DESCRIPTION SNAPSHOT")
    parts.append(jd_snapshot or "No job description snapshot available.")
    return "\n".join(parts).strip()


def build_docx_bytes_from_text(document_text: str) -> bytes:
    paragraphs = str(document_text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    paragraph_xml: list[str] = []
    for para in paragraphs:
        cleaned = str(para)
        if not cleaned.strip():
            paragraph_xml.append("<w:p/>")
            continue
        escaped = html.escape(cleaned, quote=False)
        paragraph_xml.append(
            f'<w:p><w:r><w:t xml:space="preserve">{escaped}</w:t></w:r></w:p>'
        )

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas" '
        'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
        'xmlns:o="urn:schemas-microsoft-com:office:office" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" '
        'xmlns:v="urn:schemas-microsoft-com:vml" '
        'xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
        'xmlns:w10="urn:schemas-microsoft-com:office:word" '
        'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" '
        'xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup" '
        'xmlns:wpi="http://schemas.microsoft.com/office/word/2010/wordprocessingInk" '
        'xmlns:wne="http://schemas.microsoft.com/office/word/2006/wordml" '
        'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" mc:Ignorable="w14 wp14">'
        f"<w:body>{''.join(paragraph_xml)}"
        '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" '
        'w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>'
        "</w:body></w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    package_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        "</Relationships>"
    )
    document_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>'
    )
    out = io.BytesIO()
    with zipfile.ZipFile(out, mode="w", compression=zipfile.ZIP_DEFLATED) as docx_zip:
        docx_zip.writestr("[Content_Types].xml", content_types)
        docx_zip.writestr("_rels/.rels", package_rels)
        docx_zip.writestr("word/document.xml", document_xml)
        docx_zip.writestr("word/_rels/document.xml.rels", document_rels)
    return out.getvalue()


def _wrap_line_for_pdf(text: str, max_chars: int = 92) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return [""]
    words = raw.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if len(word) > max_chars:
            if current:
                lines.append(current)
                current = ""
            for i in range(0, len(word), max_chars):
                lines.append(word[i : i + max_chars])
            continue
        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def build_pdf_bytes_from_text(document_text: str, title: str = "Resume Draft") -> bytes:
    title_line = str(title or "Resume Draft").strip()
    all_lines: list[str] = [title_line, ""]
    raw_lines = str(document_text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for raw in raw_lines:
        all_lines.extend(_wrap_line_for_pdf(raw, max_chars=92))

    lines_per_page = 46
    pages: list[list[str]] = []
    for idx in range(0, len(all_lines), lines_per_page):
        pages.append(all_lines[idx : idx + lines_per_page])
    if not pages:
        pages = [["Resume Draft"]]

    page_count = len(pages)
    font_obj = 3 + (page_count * 2)
    objects: dict[int, str] = {}
    objects[1] = "<< /Type /Catalog /Pages 2 0 R >>"
    kids = " ".join(f"{3 + (i * 2)} 0 R" for i in range(page_count))
    objects[2] = f"<< /Type /Pages /Count {page_count} /Kids [{kids}] >>"

    def escape_pdf_text(line: str) -> str:
        return (
            str(line or "")
            .replace("\\", "\\\\")
            .replace("(", "\\(")
            .replace(")", "\\)")
        )

    for i, page_lines in enumerate(pages):
        page_obj = 3 + (i * 2)
        content_obj = page_obj + 1
        operations = ["BT", "/F1 10 Tf", "50 780 Td", "14 TL"]
        for line in page_lines:
            operations.append(f"({escape_pdf_text(line)}) Tj")
            operations.append("T*")
        operations.append("ET")
        stream_data = "\n".join(operations)
        stream_len = len(stream_data.encode("latin-1", errors="replace"))
        objects[page_obj] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_obj} 0 R >> >> /Contents {content_obj} 0 R >>"
        )
        objects[content_obj] = f"<< /Length {stream_len} >>\nstream\n{stream_data}\nendstream"

    objects[font_obj] = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"

    max_obj = font_obj
    output = io.BytesIO()
    output.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0] * (max_obj + 1)

    for obj_num in range(1, max_obj + 1):
        offsets[obj_num] = output.tell()
        payload = objects.get(obj_num, "")
        output.write(f"{obj_num} 0 obj\n".encode("latin-1"))
        output.write(payload.encode("latin-1", errors="replace"))
        output.write(b"\nendobj\n")

    xref_start = output.tell()
    output.write(f"xref\n0 {max_obj + 1}\n".encode("latin-1"))
    output.write(b"0000000000 65535 f \n")
    for obj_num in range(1, max_obj + 1):
        output.write(f"{offsets[obj_num]:010d} 00000 n \n".encode("latin-1"))
    output.write(
        (
            f"trailer\n<< /Size {max_obj + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_start}\n%%EOF"
        ).encode("latin-1")
    )
    return output.getvalue()


def build_export_base_name(file_name: str) -> str:
    raw = str(file_name or "").strip() or "resume"
    no_ext = re.sub(r"\.[A-Za-z0-9]{1,6}$", "", raw)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", no_ext).strip("._-")
    return safe or "resume"


def render_resume_export_assistant(show_toggle_button: bool = True) -> None:
    analysis = st.session_state.get("analysis_result")
    if not isinstance(analysis, dict) or not analysis:
        return
    resume_text = str(st.session_state.get("latest_resume_text", "")).strip()
    job_description = str(st.session_state.get("latest_job_description", "")).strip()
    if not resume_text:
        return

    source_payload = json.dumps(analysis, ensure_ascii=True, sort_keys=True)
    source_sig = hashlib.sha256(
        f"{resume_text}\n##\n{job_description}\n##\n{source_payload}".encode("utf-8")
    ).hexdigest()
    targeted_points = generate_realtime_experience_points(resume_text, job_description, analysis)
    if st.session_state.get("resume_editor_source_sig") != source_sig:
        st.session_state.resume_editor_source_sig = source_sig
        st.session_state.resume_editor_draft_text = "\n".join(f"- {point}" for point in targeted_points)

    panel_open = bool(st.session_state.get("resume_export_panel_open"))
    if show_toggle_button:
        st.markdown(
            """
            <style>
            .st-key-resume_export_toggle_wrap button {
                border-radius: 999px !important;
                border: 1px solid #0f766e !important;
                background: linear-gradient(135deg, #14b8a6 0%, #0ea5e9 100%) !important;
                color: #ffffff !important;
                padding: 0.32rem 0.9rem !important;
                font-size: 0.80rem !important;
                font-weight: 700 !important;
                box-shadow: 0 8px 18px rgba(14, 165, 233, 0.24) !important;
            }
            .st-key-resume_export_toggle_wrap button:hover {
                border-color: #0f766e !important;
                filter: brightness(1.03) !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        button_label = "Resume Add Points" if not panel_open else "Hide Resume Add Points"
        with st.container(key="resume_export_toggle_wrap"):
            if st.button(button_label, key="resume_export_toggle_btn", use_container_width=False):
                st.session_state.resume_export_panel_open = not panel_open
                panel_open = bool(st.session_state.get("resume_export_panel_open"))
    if not panel_open:
        return

    st.markdown("### Resume Points To Add")
    st.info("These are high-impact JD-aligned points that are currently missing from your resume.")
    resume_context = infer_resume_context(resume_text)
    detected_domains = resume_context.get("domains", [])
    if detected_domains:
        st.caption(f"Detected domain context: {', '.join(str(item).replace('_', ' ').title() for item in detected_domains)}")

    points_to_show = targeted_points
    if not points_to_show:
        points_to_show = build_experience_backed_fallback_points(resume_text, job_description, analysis)
    if not points_to_show:
        st.caption("No additional JD recommendation points were detected.")
        return

    st.markdown("**Recommended Missing Points (heavy-lifting additions)**")
    for point in points_to_show:
        st.write(f"- {point}")
    copy_block = "\n".join(f"- {point}" for point in points_to_show)
    st.caption("Copy-ready format")
    st.code(copy_block, language="text")


def get_openai_key() -> str | None:
    key_from_db = get_db_setting_value("OPENAI_API_KEY")
    if key_from_db:
        return key_from_db
    key_from_env = str(os.getenv("OPENAI_API_KEY", "")).strip()
    return key_from_env or None


def time_based_greeting() -> str:
    hour = datetime.now(get_app_timezone()).hour
    if 5 <= hour < 12:
        return "Good morning"
    if 12 <= hour < 17:
        return "Good afternoon"
    if 17 <= hour < 22:
        return "Good evening"
    return "Hello"


def default_bot_messages(full_name: str | None = None) -> list[dict[str, str]]:
    if full_name and full_name.strip():
        first_name = full_name.strip().split()[0]
        greeting = (
            f"{time_based_greeting()}, {first_name}. "
            "I am ZoSwi and I am live to help with your Resume and JD analysis."
        )
        return [{"role": "assistant", "content": greeting}]
    return [{"role": "assistant", "content": BOT_WELCOME_MESSAGE}]


def sync_bot_for_logged_in_user() -> None:
    user = st.session_state.get("user") or {}
    email = str(user.get("email", "")).strip().lower()
    user_id = int(user.get("id") or 0)
    if not email:
        return

    if st.session_state.get("bot_user_email") != email:
        backfill_default_chat_titles(user_id)
        full_name = str(user.get("full_name", "")).strip()
        st.session_state.bot_user_email = email
        st.session_state.bot_open = True
        st.session_state.active_chat_id = None
        st.session_state.bot_messages = default_bot_messages(full_name)
        st.session_state.bot_pending_prompt = None
        st.session_state.zoswi_submit = False
        st.session_state.clear_zoswi_input = True
        st.session_state.full_chat_submit = False
        st.session_state.clear_full_chat_input = True
        if full_name:
            first_name = full_name.split()[0]
            st.toast(f"{time_based_greeting()}, {first_name}. ZoSwi is live.")


def normalize_category(score: int, model_category: str | None) -> str:
    valid = {"not relevant", "good", "excellent", "perfect match"}
    if model_category and model_category.strip().lower() in valid:
        cat = model_category.strip().lower()
        return cat.title() if cat != "perfect match" else "Perfect Match"

    if score < 40:
        return "Not Relevant"
    if score < 65:
        return "Good"
    if score < 85:
        return "Excellent"
    return "Perfect Match"


def parse_json_response(raw_text: str) -> dict[str, Any]:
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```json\s*|\s*```$", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    return json.loads(cleaned)


def validate_job_description_text(job_description: str) -> tuple[bool, str]:
    jd = str(job_description or "").strip()
    if not jd:
        return False, "Please enter a job description."

    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9+#./-]*", jd)
    word_count = len(words)
    if word_count < MIN_JOB_DESCRIPTION_WORDS or len(jd) < MIN_JOB_DESCRIPTION_CHARS:
        return (
            False,
            f"Please insert a proper job description (minimum {MIN_JOB_DESCRIPTION_WORDS} words). "
            "A short phrase is not enough for scoring.",
        )

    unique_words = len({w.lower() for w in words})
    if unique_words < 12:
        return False, "Job description looks incomplete. Please paste the full JD with responsibilities and requirements."

    jd_lower = jd.lower()
    jd_markers = ("responsibil", "requirement", "qualification", "experience", "skills", "role")
    if not any(marker in jd_lower for marker in jd_markers):
        return (
            False,
            "Please provide a proper JD that includes role responsibilities and required skills.",
        )

    return True, ""


def fallback_analysis(resume_text: str, job_description: str) -> dict[str, Any]:
    resume_tokens = set(re.findall(r"[a-zA-Z]{3,}", resume_text.lower()))
    jd_tokens = set(re.findall(r"[a-zA-Z]{3,}", job_description.lower()))
    if not jd_tokens:
        overlap_pct = 0
    else:
        overlap_pct = int((len(resume_tokens.intersection(jd_tokens)) / len(jd_tokens)) * 100)

    score = max(0, min(100, overlap_pct))
    category = normalize_category(score, None)
    return {
        "score": score,
        "category": category,
        "summary": "Heuristic fallback analysis was used because AI output was unavailable.",
        "strengths": ["Keyword overlap was checked between resume and job description."],
        "gaps": ["Enable OpenAI key for deeper semantic analysis and stronger recommendations."],
        "recommendations": [
            "Add measurable achievements tied to the target role.",
            "Mirror role-specific keywords from the job description naturally.",
        ],
    }


def analyze_resume_with_ai(resume_text: str, job_description: str) -> dict[str, Any]:
    jd_ok, jd_error = validate_job_description_text(job_description)
    if not jd_ok:
        raise ValueError(jd_error)

    key = get_openai_key()
    if not key:
        return fallback_analysis(resume_text, job_description)

    splitter = RecursiveCharacterTextSplitter(chunk_size=900, chunk_overlap=120)
    chunks = splitter.split_text(resume_text)
    documents = [Document(page_content=chunk) for chunk in chunks if chunk.strip()]
    if not documents:
        return fallback_analysis(resume_text, job_description)

    embeddings = OpenAIEmbeddings(model="text-embedding-3-small", api_key=key)
    vectorstore = FAISS.from_documents(documents, embeddings)
    top_docs = vectorstore.similarity_search(job_description, k=min(4, len(documents)))
    context = "\n\n".join(doc.page_content for doc in top_docs)

    prompt = f"""
You are a strict resume-job fit evaluator.
Evaluate how well the resume matches the job description.

Return ONLY valid JSON with this schema:
{{
  "score": <integer from 0 to 100>,
  "category": "<one of: Not Relevant, Good, Excellent, Perfect Match>",
  "summary": "<2-3 sentence summary>",
  "strengths": ["<bullet>", "<bullet>", "<bullet>"],
  "gaps": ["<bullet>", "<bullet>", "<bullet>"],
  "recommendations": ["<bullet>", "<bullet>", "<bullet>"]
}}

Resume context:
{context}

Job description:
{job_description}
    """.strip()

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2, api_key=key)
    result_text = llm.invoke(prompt).content

    try:
        parsed = parse_json_response(result_text)
        score = int(parsed.get("score", 0))
        score = max(0, min(100, score))
        category = normalize_category(score, parsed.get("category"))
        return {
            "score": score,
            "category": category,
            "summary": parsed.get("summary", ""),
            "strengths": parsed.get("strengths", []),
            "gaps": parsed.get("gaps", []),
            "recommendations": parsed.get("recommendations", []),
        }
    except Exception:
        return fallback_analysis(resume_text, job_description)


def build_recent_chat_context(limit: int = 6) -> str:
    chat = st.session_state.get("bot_messages", [])
    if not isinstance(chat, list):
        return ""

    lines: list[str] = []
    for msg in chat[-limit:]:
        role = str(msg.get("role", "")).strip().lower()
        content = re.sub(r"\s+", " ", str(msg.get("content", "")).strip())
        if role not in {"user", "assistant"} or not content:
            continue
        lines.append(f"{role}: {content[:240]}")
    return "\n".join(lines)


def build_assistant_prompt(message: str) -> str:
    analysis = st.session_state.get("analysis_result")
    user = st.session_state.get("user") or {}
    full_name = str(user.get("full_name", "")).strip() or "Candidate"

    if analysis:
        strengths = analysis.get("strengths", [])
        gaps = analysis.get("gaps", [])
        recommendations = analysis.get("recommendations", [])
        if not isinstance(strengths, list):
            strengths = []
        if not isinstance(gaps, list):
            gaps = []
        if not isinstance(recommendations, list):
            recommendations = []
        strengths_text = "; ".join(str(item).strip() for item in strengths[:3] if str(item).strip())
        gaps_text = "; ".join(str(item).strip() for item in gaps[:3] if str(item).strip())
        rec_text = "; ".join(str(item).strip() for item in recommendations[:3] if str(item).strip())
        analysis_summary = (
            f"Category: {analysis['category']}, Score: {analysis['score']}%, "
            f"Summary: {str(analysis.get('summary', '')).strip()[:220]}, "
            f"Top strengths: {strengths_text or 'n/a'}, "
            f"Top gaps: {gaps_text or 'n/a'}, "
            f"Top recommendations: {rec_text or 'n/a'}"
        )
    else:
        analysis_summary = "No resume-JD analysis has been run yet."

    cleaned_message = re.sub(r"^\s*[A-Za-z]\s*:\s*", "", message.strip())
    chat_context = build_recent_chat_context()

    return f"""
You are ZoSwi, an AI assistant with a conversational style similar to ChatGPT.

Conversation style:
- Be warm, lively, concise, and natural.
- If user says thanks or appreciation, respond naturally (for example: You're welcome) and offer next help.
- Keep replies focused on exactly what the user asked.

Scope and safety:
- Primary scope: resume review, JD analysis, ATS keywords, interview prep, and role-skill guidance in career context.
- If user asks unrelated topics, respond politely and steer back to resume/JD help.
- If request is harmful, illegal, or privacy-invasive, refuse politely and redirect to safe career guidance.
- Never request or expose sensitive data like passwords, API keys, bank/identity details.

Candidate context:
- Candidate name: {full_name}
- Latest analysis snapshot: {analysis_summary}

Recent chat:
{chat_context or "No prior chat context."}

User message:
{cleaned_message}
    """.strip()


def chunk_to_text(chunk: Any) -> str:
    content = getattr(chunk, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


def ask_assistant_bot_stream(message: str):
    key = get_openai_key()
    if not key:
        yield "OPENAI_API_KEY is required for ZoSwi responses. Please set it and retry."
        return

    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.4,
        max_tokens=220,
        max_retries=1,
        timeout=25,
        api_key=key,
    )
    prompt = build_assistant_prompt(message)
    try:
        for chunk in llm.stream(prompt):
            text = chunk_to_text(chunk)
            if text:
                yield text
    except Exception:
        yield "I hit a temporary issue generating a response. Please try again."


def ask_assistant_bot(message: str) -> str:
    key = get_openai_key()
    if not key:
        return "OPENAI_API_KEY is required for ZoSwi responses. Please set it and retry."

    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.4,
        max_tokens=220,
        max_retries=1,
        timeout=25,
        api_key=key,
    )
    prompt = build_assistant_prompt(message)

    try:
        return llm.invoke(prompt).content
    except Exception:
        return "I hit a temporary issue generating a response. Please try again."


def request_coding_room_submit() -> None:
    st.session_state.coding_room_submit = True


def _trim_block(text: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(cleaned) <= max(0, int(limit or 0)):
        return cleaned
    return cleaned[: max(0, int(limit or 0))].rstrip() + "..."


def _normalize_text_list(raw_items: Any, limit: int, fallback: list[str]) -> list[str]:
    values: list[str] = []
    if isinstance(raw_items, list):
        for item in raw_items:
            cleaned = re.sub(r"\s+", " ", str(item or "")).strip().strip("-•* ")
            if cleaned:
                values.append(cleaned)
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        token = value.lower()
        if token not in seen:
            seen.add(token)
            deduped.append(value)
    result = deduped[: max(1, int(limit or 1))]
    if result:
        return result
    return list(fallback[: max(1, int(limit or 1))])


def _normalize_language_token(language: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "_", str(language or "").strip().lower()).strip("_")
    return token or "code"


def build_stage_starter_code(stage: dict[str, Any], language: str) -> str:
    lang = _normalize_language_token(language)
    question = str(stage.get("question", "") or stage.get("challenge", "")).strip() or "Complete the TODO logic."
    steps = stage.get("completion_steps", [])
    if not isinstance(steps, list) or not steps:
        steps = stage.get("requirements", [])
    clean_steps = [str(item).strip() for item in steps if str(item).strip()]
    if not clean_steps:
        clean_steps = ["Parse input", "Complete core logic", "Return expected output"]
    hints = stage.get("hint_starters", [])
    clean_hints = [str(item).strip() for item in hints if str(item).strip()]
    sample_case = str(stage.get("sample_case", "")).strip()
    todo_comment_lines = [f"TODO {idx + 1}: {item}" for idx, item in enumerate(clean_steps[:3])]
    hint_comment = clean_hints[0] if clean_hints else "Use deterministic logic and handle edge cases."

    if lang == "python":
        body = "\n".join(f"    # {line}" for line in todo_comment_lines)
        return (
            f"# Question: {question}\n"
            f"# Hint: {hint_comment}\n"
            f"{('# Sample: ' + sample_case + '\\n') if sample_case else ''}"
            "def solve(records):\n"
            f"{body}\n"
            "    result = {}\n"
            "    return result\n\n"
            "if __name__ == \"__main__\":\n"
            "    sample_records = []\n"
            "    print(solve(sample_records))\n"
        )
    if lang == "java":
        body = "\n".join(f"        // {line}" for line in todo_comment_lines)
        return (
            f"// Question: {question}\n"
            f"// Hint: {hint_comment}\n"
            f"{('// Sample: ' + sample_case + '\\n') if sample_case else ''}"
            "import java.util.*;\n\n"
            "public class Solution {\n"
            "    public static Map<String, Object> solve(List<Map<String, Object>> records) {\n"
            f"{body}\n"
            "        Map<String, Object> result = new HashMap<>();\n"
            "        return result;\n"
            "    }\n\n"
            "    public static void main(String[] args) {\n"
            "        List<Map<String, Object>> sampleRecords = new ArrayList<>();\n"
            "        System.out.println(solve(sampleRecords));\n"
            "    }\n"
            "}\n"
        )
    if lang == "javascript":
        body = "\n".join(f"  // {line}" for line in todo_comment_lines)
        return (
            f"// Question: {question}\n"
            f"// Hint: {hint_comment}\n"
            f"{('// Sample: ' + sample_case + '\\n') if sample_case else ''}"
            "function solve(records) {\n"
            f"{body}\n"
            "  const result = {};\n"
            "  return result;\n"
            "}\n\n"
            "const sampleRecords = [];\n"
            "console.log(solve(sampleRecords));\n"
        )
    if lang == "typescript":
        body = "\n".join(f"  // {line}" for line in todo_comment_lines)
        return (
            f"// Question: {question}\n"
            f"// Hint: {hint_comment}\n"
            f"{('// Sample: ' + sample_case + '\\n') if sample_case else ''}"
            "type GenericRecord = Record<string, unknown>;\n\n"
            "function solve(records: GenericRecord[]): Record<string, unknown> {\n"
            f"{body}\n"
            "  const result: Record<string, unknown> = {};\n"
            "  return result;\n"
            "}\n\n"
            "const sampleRecords: GenericRecord[] = [];\n"
            "console.log(solve(sampleRecords));\n"
        )
    if lang == "go":
        body = "\n".join(f"\t// {line}" for line in todo_comment_lines)
        return (
            f"// Question: {question}\n"
            f"// Hint: {hint_comment}\n"
            f"{('// Sample: ' + sample_case + '\\n') if sample_case else ''}"
            "package main\n\n"
            "import \"fmt\"\n\n"
            "func solve(records []map[string]any) map[string]any {\n"
            f"{body}\n"
            "\tresult := map[string]any{}\n"
            "\treturn result\n"
            "}\n\n"
            "func main() {\n"
            "\tsampleRecords := []map[string]any{}\n"
            "\tfmt.Println(solve(sampleRecords))\n"
            "}\n"
        )
    if lang == "c":
        # Fallback plain template when token simplifies unexpectedly.
        lang = "cpp"
    if lang == "cpp":
        body = "\n".join(f"    // {line}" for line in todo_comment_lines)
        return (
            f"// Question: {question}\n"
            f"// Hint: {hint_comment}\n"
            f"{('// Sample: ' + sample_case + '\\n') if sample_case else ''}"
            "#include <bits/stdc++.h>\n"
            "using namespace std;\n\n"
            "map<string, string> solve(const vector<map<string, string>>& records) {\n"
            f"{body}\n"
            "    map<string, string> result;\n"
            "    return result;\n"
            "}\n\n"
            "int main() {\n"
            "    vector<map<string, string>> sampleRecords;\n"
            "    auto out = solve(sampleRecords);\n"
            "    cout << out.size() << endl;\n"
            "    return 0;\n"
            "}\n"
        )
    return (
        f"// Question: {question}\n"
        f"// Hint: {hint_comment}\n"
        "// TODO: complete the solve function.\n"
    )


def _normalize_code_for_compare(code: str, language: str) -> str:
    token = _normalize_language_token(language)
    lines = str(code or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    normalized_parts: list[str] = []
    in_block_comment = False
    for raw_line in lines:
        line = str(raw_line or "").rstrip()
        stripped = line.strip()
        if not stripped:
            continue

        if in_block_comment:
            if "*/" in stripped:
                in_block_comment = False
            continue

        if stripped.startswith("/*"):
            if "*/" not in stripped:
                in_block_comment = True
            continue

        if token == "python":
            if stripped.startswith("#"):
                continue
        else:
            if stripped.startswith("//"):
                continue

        compact = re.sub(r"\s+", "", stripped)
        if compact:
            normalized_parts.append(compact)
    return "".join(normalized_parts)


def _is_starter_code_unchanged(submitted_code: str, starter_code: str, language: str) -> bool:
    submitted_sig = _normalize_code_for_compare(submitted_code, language)
    starter_sig = _normalize_code_for_compare(starter_code, language)
    if not submitted_sig:
        return True
    if starter_sig and submitted_sig == starter_sig:
        return True
    return False


def extract_top_technical_skills(
    resume_text: str,
    job_description: str,
    limit: int = 6,
) -> list[str]:
    resume_lower = str(resume_text or "").lower()
    jd_lower = str(job_description or "").lower()
    if not resume_lower and not jd_lower:
        return []

    skill_aliases: dict[str, list[str]] = {
        "Python": ["python"],
        "Java": ["java", "spring boot"],
        "JavaScript": ["javascript", "node.js", "nodejs"],
        "TypeScript": ["typescript"],
        "SQL": ["sql", "postgresql", "mysql", "oracle"],
        "React": ["react"],
        "Angular": ["angular"],
        "Node.js": ["node.js", "nodejs", "express"],
        "AWS": ["aws", "amazon web services"],
        "Azure": ["azure"],
        "GCP": ["gcp", "google cloud"],
        "Docker": ["docker", "container"],
        "Kubernetes": ["kubernetes", "k8s"],
        "Microservices": ["microservice", "microservices"],
        "Kafka": ["kafka"],
        "Redis": ["redis"],
        "MuleSoft": ["mulesoft", "anypoint"],
        "REST APIs": ["rest api", "restful"],
        "GraphQL": ["graphql"],
        "Data Structures": ["data structure", "algorithms", "algorithm"],
        "System Design": ["system design", "architecture", "distributed"],
    }
    scored: list[tuple[int, str]] = []
    for skill_name, aliases in skill_aliases.items():
        in_resume = any(alias in resume_lower for alias in aliases)
        in_jd = any(alias in jd_lower for alias in aliases)
        if not in_resume and not in_jd:
            continue
        score = (2 if in_resume else 0) + (3 if in_jd else 0)
        scored.append((score, skill_name))
    scored.sort(key=lambda item: (-item[0], item[1].lower()))
    return [name for _, name in scored[: max(1, int(limit or 1))]]


def _fallback_coding_stage_payload(resume_text: str, job_description: str) -> dict[str, Any]:
    skills = extract_top_technical_skills(resume_text, job_description, limit=6)
    primary = skills[0] if skills else "Backend Engineering"
    secondary = skills[1] if len(skills) > 1 else "SQL"
    tertiary = skills[2] if len(skills) > 2 else "System Design"
    return {
        "interviewer_intro": (
            f"{time_based_greeting()}. I am ZoSwi, your live coding interviewer. "
            "We will complete 3 stages with increasing depth and practical tradeoffs."
        ),
        "detected_skills": skills,
        "stages": [
            {
                "title": f"Stage 1 - Completion Drill in {primary}",
                "skill_focus": primary,
                "scenario": "You are completing an unfinished function used in a production data pipeline.",
                "question": (
                    "Complete `solve(records)` to return a summary dictionary with `valid_count`, `invalid_count`, "
                    "and `duplicate_ids` from incoming transaction-like records."
                ),
                "challenge": (
                    "Complete `solve(records)` using the starter template and return the expected summary output."
                ),
                "completion_steps": [
                    "Validate each record has required fields (`id`, `amount`).",
                    "Count valid vs invalid records and track duplicate ids.",
                    "Return a deterministic summary object with required keys.",
                ],
                "requirements": [
                    "Do not rewrite the full file; complete TODO sections.",
                    "Handle edge cases safely without crashing.",
                    "Keep logic close to O(n) for n records.",
                ],
                "hint_starters": [
                    "Use a set to detect duplicates in one pass.",
                    "Keep counters separate from output formatting.",
                ],
                "sample_case": "Input ids [A1, A2, A1, bad] -> valid_count=3, invalid_count=1, duplicate_ids=['A1']",
                "evaluation_rubric": [
                    "Correctness on edge cases",
                    "Completion of required TODO logic",
                    "Readable and testable code",
                ],
                "time_limit_min": 18,
            },
            {
                "title": f"Stage 2 - Query Logic Completion with {secondary}",
                "skill_focus": secondary,
                "scenario": "You are filling missing reconciliation logic in an existing analytics module.",
                "question": (
                    "Complete `solve(records)` so it groups orders by customer and returns customers with mismatch "
                    "between total orders and total payments."
                ),
                "challenge": (
                    "Use the provided starter code and complete reconciliation TODO blocks for mismatch detection."
                ),
                "completion_steps": [
                    "Aggregate total order amount per customer.",
                    "Aggregate total payment amount per customer.",
                    "Return only customers where totals do not match.",
                ],
                "requirements": [
                    "Avoid nested loops when hash maps can be used.",
                    "Keep output deterministic and easy to verify.",
                    "Complete only the missing parts of scaffold code.",
                ],
                "hint_starters": [
                    "Build per-customer totals first, then compare.",
                    "Normalize customer key casing before grouping.",
                ],
                "sample_case": "Customer C1 order=120 payment=100 -> include C1 with gap=20",
                "evaluation_rubric": [
                    "Data correctness",
                    "Completion accuracy",
                    "Output quality and readability",
                ],
                "time_limit_min": 20,
            },
            {
                "title": f"Stage 3 - Reliability Helper Completion with {tertiary}",
                "skill_focus": tertiary,
                "scenario": "You are completing retry utility code used by an existing service layer.",
                "question": (
                    "Complete `solve(records)` to simulate retry attempts and return successful records with "
                    "attempt counts, while stopping after max retries."
                ),
                "challenge": (
                    "Finish retry/idempotency TODO logic in the scaffold so repeated records are handled safely."
                ),
                "completion_steps": [
                    "Track attempt count per record id.",
                    "Stop retrying after configured max attempts.",
                    "Return summary with success list and failed list.",
                ],
                "requirements": [
                    "Complete TODO sections without overbuilding architecture.",
                    "Keep behavior deterministic and test-friendly.",
                    "Use clear variable names for retries and outcomes.",
                ],
                "hint_starters": [
                    "Use maps for attempt tracking and deduplication.",
                    "Separate per-record processing from final summary assembly.",
                ],
                "sample_case": "Record R9 succeeds at attempt 2 -> include R9 in success with attempts=2",
                "evaluation_rubric": [
                    "Retry logic correctness",
                    "Completion of scaffolded sections",
                    "Code clarity under constraints",
                ],
                "time_limit_min": 22,
            },
        ],
    }


def build_coding_stage_payload(
    resume_text: str,
    job_description: str,
    analysis_result: dict[str, Any],
) -> dict[str, Any]:
    fallback = _fallback_coding_stage_payload(resume_text, job_description)
    key = get_openai_key()
    if not key:
        return fallback

    role_summary = _trim_block(job_description, 1400)
    resume_summary = _trim_block(resume_text, 1400)
    analysis_summary = _trim_block(
        json.dumps(
            {
                "score": analysis_result.get("score"),
                "category": analysis_result.get("category"),
                "gaps": analysis_result.get("gaps", []),
                "recommendations": analysis_result.get("recommendations", []),
            },
            ensure_ascii=True,
        ),
        1200,
    )
    try:
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.35, api_key=key)
        prompt = f"""
You are designing a realistic 3-stage live coding interview.
Return ONLY valid JSON in this schema:
{{
  "interviewer_intro": "<1-2 sentences>",
  "detected_skills": ["<skill>", "<skill>", "..."],
  "stages": [
    {{
      "title": "<stage title>",
      "skill_focus": "<single skill focus>",
      "scenario": "<real-world scenario>",
      "question": "<focused coding question>",
      "challenge": "<same as question or concise variant>",
      "completion_steps": ["<todo 1>", "<todo 2>", "<todo 3>"],
      "requirements": ["<req1>", "<req2>", "<req3>"],
      "hint_starters": ["<hint1>", "<hint2>"],
      "sample_case": "<one concise sample input-output case>",
      "evaluation_rubric": ["<criterion1>", "<criterion2>", "<criterion3>"],
      "time_limit_min": <integer 15-35>
    }}
  ]
}}

Constraints:
- Exactly 3 stages.
- Difficulty must increase stage by stage.
- Challenges must be original scenario-style prompts, not famous named problems.
- Keep each field concise and practical for a real interview.
- Do NOT ask candidate to build a full service or full app.
- Every stage must be a code-completion exercise with starter-code intent (candidate fills TODOs).

Candidate resume snapshot:
{resume_summary}

Job description snapshot:
{role_summary}

Current analysis summary:
{analysis_summary}
        """.strip()
        raw = llm.invoke(prompt).content
        parsed = parse_json_response(str(raw))
        if not isinstance(parsed, dict):
            return fallback
    except Exception:
        return fallback

    raw_stages = parsed.get("stages", [])
    if not isinstance(raw_stages, list) or len(raw_stages) < CODING_STAGE_COUNT:
        return fallback

    normalized_stages: list[dict[str, Any]] = []
    fallback_stages = fallback["stages"]
    for idx in range(CODING_STAGE_COUNT):
        stage_raw = raw_stages[idx] if idx < len(raw_stages) and isinstance(raw_stages[idx], dict) else {}
        backup = fallback_stages[idx]
        title = _trim_block(str(stage_raw.get("title", "")).strip() or backup["title"], 84)
        focus = _trim_block(str(stage_raw.get("skill_focus", "")).strip() or backup["skill_focus"], 50)
        scenario = _trim_block(str(stage_raw.get("scenario", "")).strip() or backup["scenario"], 260)
        question = _trim_block(
            str(stage_raw.get("question", "")).strip()
            or str(stage_raw.get("challenge", "")).strip()
            or backup.get("question", backup["challenge"]),
            460,
        )
        challenge = _trim_block(str(stage_raw.get("challenge", "")).strip() or question, 460)
        completion_steps = _normalize_text_list(
            stage_raw.get("completion_steps"),
            4,
            backup.get("completion_steps", backup["requirements"]),
        )
        requirements = _normalize_text_list(stage_raw.get("requirements"), 4, backup["requirements"])
        hints = _normalize_text_list(stage_raw.get("hint_starters"), 3, backup["hint_starters"])
        rubric = _normalize_text_list(stage_raw.get("evaluation_rubric"), 4, backup["evaluation_rubric"])
        sample_case = _trim_block(str(stage_raw.get("sample_case", "")).strip() or str(backup.get("sample_case", "")).strip(), 220)
        time_limit = stage_raw.get("time_limit_min", backup["time_limit_min"])
        try:
            time_limit_int = int(time_limit)
        except Exception:
            time_limit_int = int(backup["time_limit_min"])
        time_limit_int = max(15, min(35, time_limit_int))
        normalized_stages.append(
            {
                "title": title,
                "skill_focus": focus,
                "scenario": scenario,
                "question": question,
                "challenge": challenge,
                "completion_steps": completion_steps,
                "requirements": requirements,
                "hint_starters": hints,
                "sample_case": sample_case,
                "evaluation_rubric": rubric,
                "time_limit_min": time_limit_int,
            }
        )

    intro = _trim_block(
        str(parsed.get("interviewer_intro", "")).strip() or fallback["interviewer_intro"],
        220,
    )
    skills = _normalize_text_list(parsed.get("detected_skills"), 8, fallback.get("detected_skills", []))
    return {
        "interviewer_intro": intro,
        "detected_skills": skills,
        "stages": normalized_stages,
    }


def format_timer_label(seconds: int) -> str:
    safe_seconds = max(0, int(seconds or 0))
    mins, secs = divmod(safe_seconds, 60)
    return f"{mins:02d}:{secs:02d}"


def render_live_stage_timer_widget(remaining_seconds: int, timer_element_id: str, warning_key: str) -> None:
    safe_remaining = max(0, int(remaining_seconds or 0))
    safe_timer_id = re.sub(r"[^a-zA-Z0-9_-]", "_", str(timer_element_id or "coding_chip_timer"))
    safe_warning_key = re.sub(r"[^a-zA-Z0-9_-]", "_", str(warning_key or "stage_warn"))
    st.components.v1.html(
        f"""
        <script>
        (function () {{
            const win = window.parent;
            const parentDoc = win && win.document ? win.document : null;
            if (!parentDoc) {{
                return;
            }}
            const timerEl = parentDoc.getElementById("{safe_timer_id}");
            if (!timerEl) {{
                return;
            }}
            const intervalKey = "__zoswiCodingTimerInterval_{safe_timer_id}";
            if (win[intervalKey]) {{
                win.clearInterval(win[intervalKey]);
            }}
            let remaining = {safe_remaining};
            function fmt(totalSeconds) {{
                const safe = Math.max(0, totalSeconds);
                const mins = String(Math.floor(safe / 60)).padStart(2, "0");
                const secs = String(safe % 60).padStart(2, "0");
                return mins + ":" + secs;
            }}
            function ensureWarnPopup() {{
                const storageKey = "zoswi_timer_warn_{safe_warning_key}";
                if (win.sessionStorage.getItem(storageKey) === "1") {{
                    return;
                }}
                win.sessionStorage.setItem(storageKey, "1");
                const existing = parentDoc.getElementById("zoswi-timer-alert-popup");
                if (existing) {{
                    existing.remove();
                }}
                const popup = parentDoc.createElement("div");
                popup.id = "zoswi-timer-alert-popup";
                popup.style.position = "fixed";
                popup.style.top = "1rem";
                popup.style.right = "1rem";
                popup.style.zIndex = "999999";
                popup.style.padding = "0.72rem 0.86rem";
                popup.style.borderRadius = "12px";
                popup.style.border = "1px solid #fca5a5";
                popup.style.background = "#fff1f2";
                popup.style.color = "#9f1239";
                popup.style.fontFamily = "'Plus Jakarta Sans','Segoe UI',sans-serif";
                popup.style.fontSize = "0.8rem";
                popup.style.fontWeight = "700";
                popup.style.boxShadow = "0 12px 24px rgba(127, 29, 29, 0.16)";
                popup.textContent = "5 minutes remaining for this stage. Please finalize your solution.";
                parentDoc.body.appendChild(popup);
                win.setTimeout(function () {{
                    if (popup && popup.parentNode) {{
                        popup.parentNode.removeChild(popup);
                    }}
                }}, 5200);
            }}
            function paint() {{
                if (remaining <= 0) {{
                    timerEl.classList.remove("timer-safe");
                    timerEl.classList.add("timer-alert");
                    timerEl.textContent = "Expired";
                    return;
                }}
                timerEl.classList.remove("timer-alert");
                timerEl.classList.add("timer-safe");
                timerEl.textContent = fmt(remaining);
                if (remaining <= 300) {{
                    ensureWarnPopup();
                }}
            }}
            paint();
            win[intervalKey] = win.setInterval(function () {{
                remaining -= 1;
                if (remaining <= 0) {{
                    remaining = 0;
                    paint();
                    win.clearInterval(win[intervalKey]);
                    win[intervalKey] = null;
                    return;
                }}
                paint();
            }}, 1000);
        }})();
        </script>
        """,
        height=0,
    )


def render_solution_editor_security_guard() -> None:
    st.components.v1.html(
        """
        <script>
        (function () {
            const hostDoc = (window.parent && window.parent.document) ? window.parent.document : window.document;
            if (!hostDoc) {
                return;
            }
            const blockEvent = function (event) {
                event.preventDefault();
                event.stopPropagation();
                return false;
            };
            const editorWrap = hostDoc.querySelector(".st-key-coding_editor_shell");
            if (!editorWrap) {
                return;
            }
            hostDoc.querySelectorAll(".zoswi-code-line-gutter").forEach(function (node) {
                if (node && node.parentNode) {
                    node.parentNode.removeChild(node);
                }
            });
            hostDoc.querySelectorAll('[data-testid="stTextArea"].zoswi-code-editor-root').forEach(function (node) {
                node.classList.remove("zoswi-code-editor-root");
            });
            const editors = editorWrap.querySelectorAll("textarea");
            if (!editors || editors.length === 0) {
                return;
            }
            editors.forEach(function (editor) {
                if (!editor) {
                    return;
                }
                editor.style.paddingLeft = "";
                editor.style.tabSize = "";
                editor.style.whiteSpace = "";
                editor.style.overflowWrap = "";
                if (editor.dataset.leftPadApplied) {
                    delete editor.dataset.leftPadApplied;
                }
                if (editor.dataset.lineSyncApplied) {
                    delete editor.dataset.lineSyncApplied;
                }
                if (editor.dataset.secGuardAppliedV3 === "1") {
                    return;
                }
                editor.dataset.secGuardAppliedV3 = "1";
                ["copy", "cut", "paste", "contextmenu", "drop"].forEach(function (evt) {
                    editor.addEventListener(evt, blockEvent);
                });
                editor.addEventListener("keydown", function (event) {
                    const key = String(event.key || "").toLowerCase();
                    const ctrlMeta = Boolean(event.ctrlKey || event.metaKey);
                    if (ctrlMeta && (key === "c" || key === "v" || key === "x" || key === "insert")) {
                        blockEvent(event);
                    }
                    if (event.shiftKey && key === "insert") {
                        blockEvent(event);
                    }
                    if (key === "enter" && !event.shiftKey && !event.ctrlKey && !event.metaKey && !event.isComposing) {
                        event.preventDefault();
                        const start = Number(editor.selectionStart || 0);
                        const end = Number(editor.selectionEnd || 0);
                        const fullText = String(editor.value || "");
                        const currentLine = fullText.slice(0, start).split("\\n").pop() || "";
                        const indent = (currentLine.match(/^\\s+/) || [""])[0];
                        const extraIndent = /[\\{\\[\\(]\\s*$/.test(currentLine) ? "    " : "";
                        const insertText = "\\n" + indent + extraIndent;
                        editor.setRangeText(insertText, start, end, "end");
                        try {
                            const ownerWin = editor.ownerDocument && editor.ownerDocument.defaultView;
                            const DomEvent = ownerWin && ownerWin.Event ? ownerWin.Event : Event;
                            editor.dispatchEvent(new DomEvent("input", { bubbles: true }));
                        } catch (error) {
                            // Ignore dispatch failures.
                        }
                    }
                });
            });
        })();
        </script>
        """,
        height=0,
    )


def validate_stage_approach_text(approach_text: str) -> tuple[bool, str]:
    cleaned = re.sub(r"\s+", " ", str(approach_text or "")).strip()
    if len(cleaned) < 80:
        return False, "Approach is too short. Explain your logic in at least 80 characters."
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", cleaned)
    if len(words) < 18:
        return False, "Approach is too short. Provide at least 18 words."
    lowered = cleaned.lower()
    required_keywords = ("approach", "logic", "edge", "test", "complexity", "tradeoff", "data")
    if not any(keyword in lowered for keyword in required_keywords):
        return False, "Mention core reasoning (logic, edge cases, tests, or complexity) in your approach."
    return True, ""


def run_hidden_tests_for_submission(
    stage: dict[str, Any],
    code: str,
    language: str,
    resume_text: str,
    job_description: str,
) -> dict[str, Any]:
    cleaned_code = str(code or "").strip()
    starter = build_stage_starter_code(stage, language)
    if _is_starter_code_unchanged(cleaned_code, starter, language):
        return {
            "ran": True,
            "total": 5,
            "passed": 0,
            "failed_cases": [
                "core_logic_completion",
                "edge_case_guard",
                "output_shape_validation",
            ],
            "summary": "Hidden tests failed because starter TODO logic is still incomplete.",
            "ready_for_evaluation": False,
        }

    todo_left = bool(re.search(r"\bTODO\b", cleaned_code, flags=re.IGNORECASE))
    has_return = "return" in cleaned_code.lower()
    has_condition = bool(re.search(r"\b(if|elif|else|switch|case)\b", cleaned_code, flags=re.IGNORECASE))
    has_iteration = bool(re.search(r"\b(for|while|foreach)\b", cleaned_code, flags=re.IGNORECASE))
    has_structure = bool(re.search(r"\b(dict|map|set|list|object|array|hashmap)\b", cleaned_code, flags=re.IGNORECASE))

    fallback_passed = 1
    if has_return:
        fallback_passed += 1
    if has_condition:
        fallback_passed += 1
    if has_iteration:
        fallback_passed += 1
    if has_structure and not todo_left:
        fallback_passed += 1
    fallback_passed = max(0, min(5, fallback_passed))
    fallback_failed: list[str] = []
    if todo_left:
        fallback_failed.append("todo_completion")
    if not has_return:
        fallback_failed.append("return_shape")
    if not has_condition:
        fallback_failed.append("edge_case_branching")
    if not has_iteration:
        fallback_failed.append("record_iteration")
    if not has_structure:
        fallback_failed.append("data_structure_usage")
    fallback_ready = fallback_passed >= 3 and not todo_left
    fallback_summary = (
        f"Hidden checks passed {fallback_passed}/5. "
        + ("Submission looks ready for formal evaluation." if fallback_ready else "Complete missing logic before evaluation.")
    )
    fallback_result = {
        "ran": True,
        "total": 5,
        "passed": fallback_passed,
        "failed_cases": fallback_failed[:5],
        "summary": fallback_summary,
        "ready_for_evaluation": fallback_ready,
    }

    key = get_openai_key()
    if not key:
        return fallback_result

    prompt = f"""
You are an interview hidden-test evaluator.
Assess whether the candidate's code likely passes unseen tests for the given scaffold-completion task.
Return ONLY valid JSON:
{{
  "total": <integer 4-8>,
  "passed": <integer 0-total>,
  "failed_cases": ["<short_case_name>", "<short_case_name>"],
  "summary": "<one concise sentence>",
  "ready_for_evaluation": <true or false>
}}

Stage title: {stage.get("title", "")}
Question: {stage.get("question", stage.get("challenge", ""))}
Completion steps: {json.dumps(stage.get("completion_steps", []), ensure_ascii=True)}
Requirements: {json.dumps(stage.get("requirements", []), ensure_ascii=True)}
Language: {language}

Candidate code:
```{language.lower()}
{_trim_block(cleaned_code, 6000)}
```

Resume snapshot:
{_trim_block(resume_text, 450)}

JD snapshot:
{_trim_block(job_description, 450)}
    """.strip()
    try:
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.15, api_key=key)
        raw = llm.invoke(prompt).content
        parsed = parse_json_response(str(raw))
        total = int(parsed.get("total", fallback_result["total"]))
        total = max(4, min(8, total))
        passed = int(parsed.get("passed", fallback_result["passed"]))
        passed = max(0, min(total, passed))
        failed_cases = _normalize_text_list(parsed.get("failed_cases"), 5, fallback_result["failed_cases"])
        summary = _trim_block(str(parsed.get("summary", "")).strip() or fallback_result["summary"], 220)
        ready = bool(parsed.get("ready_for_evaluation", False))
        if todo_left:
            ready = False
        return {
            "ran": True,
            "total": total,
            "passed": passed,
            "failed_cases": failed_cases,
            "summary": summary,
            "ready_for_evaluation": ready,
        }
    except Exception:
        return fallback_result


def summarize_coding_stage_score(score: int) -> str:
    if score >= 85:
        return "Strong"
    if score >= 70:
        return "Solid"
    if score >= 55:
        return "Developing"
    return "Needs Improvement"


def evaluate_coding_submission(
    stage: dict[str, Any],
    code: str,
    language: str,
    resume_text: str,
    job_description: str,
) -> dict[str, Any]:
    cleaned_code = str(code or "").strip()
    starter_code = build_stage_starter_code(stage, language)
    if not cleaned_code:
        return {
            "score": 0,
            "verdict": "No submission",
            "strengths": [],
            "improvements": ["Add a solution before running stage evaluation."],
            "next_step": "Submit code for this stage and re-run evaluation.",
        }
    if _is_starter_code_unchanged(cleaned_code, starter_code, language):
        return {
            "score": 0,
            "verdict": "No submission",
            "strengths": [],
            "improvements": [
                "Starter template is unchanged. Complete the TODO sections before evaluating.",
            ],
            "next_step": "Implement at least the required TODO steps, then run evaluation.",
        }

    fallback_score = min(92, max(38, 32 + (len(cleaned_code) // 35)))
    fallback = {
        "score": fallback_score,
        "verdict": summarize_coding_stage_score(fallback_score),
        "strengths": [
            "Submission was structured and covered a meaningful portion of the task.",
            f"Language selection `{language}` aligns with interview flexibility.",
        ],
        "improvements": [
            "Clarify edge-case handling and failure paths.",
            "Tighten complexity and document tradeoffs in brief comments.",
        ],
        "next_step": "Refine the solution for edge cases, then move to the next stage.",
    }

    key = get_openai_key()
    if not key:
        return fallback

    prompt = f"""
You are a strict senior coding interviewer.
Evaluate the candidate submission and return ONLY valid JSON:
{{
  "score": <integer 0-100>,
  "verdict": "<short label>",
  "strengths": ["<point>", "<point>"],
  "improvements": ["<point>", "<point>"],
  "next_step": "<single sentence>"
}}

Stage title: {stage.get("title", "")}
Skill focus: {stage.get("skill_focus", "")}
Scenario: {stage.get("scenario", "")}
Question: {stage.get("question", stage.get("challenge", ""))}
Challenge: {stage.get("challenge", "")}
Completion steps: {json.dumps(stage.get("completion_steps", []), ensure_ascii=True)}
Requirements: {json.dumps(stage.get("requirements", []), ensure_ascii=True)}
Evaluation rubric: {json.dumps(stage.get("evaluation_rubric", []), ensure_ascii=True)}

Candidate language: {language}
Candidate code:
```{language.lower()}
{_trim_block(cleaned_code, 6000)}
```

Candidate resume snapshot:
{_trim_block(resume_text, 700)}

Job description snapshot:
{_trim_block(job_description, 700)}
    """.strip()
    try:
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2, api_key=key)
        raw = llm.invoke(prompt).content
        parsed = parse_json_response(str(raw))
        score = int(parsed.get("score", fallback_score))
        score = max(0, min(100, score))
        strengths = _normalize_text_list(parsed.get("strengths"), 3, fallback["strengths"])
        improvements = _normalize_text_list(parsed.get("improvements"), 3, fallback["improvements"])
        verdict = _trim_block(
            str(parsed.get("verdict", "")).strip() or summarize_coding_stage_score(score),
            60,
        )
        next_step = _trim_block(str(parsed.get("next_step", "")).strip() or fallback["next_step"], 220)
        return {
            "score": score,
            "verdict": verdict,
            "strengths": strengths,
            "improvements": improvements,
            "next_step": next_step,
        }
    except Exception:
        return fallback


def build_coding_chat_context(limit: int = 8) -> str:
    messages = st.session_state.get("coding_room_messages", [])
    if not isinstance(messages, list):
        return ""
    lines: list[str] = []
    for message in messages[-max(1, int(limit or 1)) :]:
        role = str(message.get("role", "")).strip().lower()
        content = str(message.get("content", "")).strip()
        if role not in {"assistant", "user"} or not content:
            continue
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def stream_coding_interviewer_reply(
    action: str,
    user_message: str,
    stage: dict[str, Any],
    stage_index: int,
    user_name: str,
) -> Any:
    cleaned_action = str(action or "message").strip().lower()
    cleaned_user_message = str(user_message or "").strip()
    fallback_map = {
        "ready": "Great. Read the question, then complete the TODO blocks step by step.",
        "hint": "Focus on one TODO at a time and verify output shape before moving to the next step.",
        "nudge": "I did not hear a complete response. Share your next step, then we will proceed.",
    }
    fallback_default = "Understood. Explain your approach in one minute, then submit the best working version."
    key = get_openai_key()
    if not key:
        yield fallback_map.get(cleaned_action, fallback_default)
        return

    stage_completion_steps = stage.get("completion_steps", [])
    if not isinstance(stage_completion_steps, list) or not stage_completion_steps:
        stage_completion_steps = stage.get("requirements", [])
    stage_requirements = ", ".join(stage_completion_steps)
    stage_rubric = ", ".join(stage.get("evaluation_rubric", []))
    chat_context = build_coding_chat_context(limit=10)
    prompt = f"""
You are ZoSwi, a live coding interviewer.
Keep responses concise (max 80 words), conversational, and interviewer-like.
If candidate response is weak or unclear, ask a focused follow-up question.
If action is "hint", provide one useful hint without revealing full solution.
Guide the candidate to complete TODO sections rather than building a full service.

Candidate name: {user_name}
Current stage number: {stage_index + 1} of {CODING_STAGE_COUNT}
Stage title: {stage.get("title", "")}
Skill focus: {stage.get("skill_focus", "")}
Challenge: {stage.get("challenge", "")}
Requirements: {stage_requirements}
Rubric: {stage_rubric}
Action: {cleaned_action}
Candidate message: {cleaned_user_message or "(none)"}

Recent coding chat:
{chat_context or "No previous chat context."}
    """.strip()
    try:
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.45, api_key=key)
        for chunk in llm.stream(prompt):
            text = chunk_to_text(chunk)
            if text:
                yield text
    except Exception:
        yield fallback_map.get(cleaned_action, fallback_default)


def append_coding_room_message(role: str, content: str) -> None:
    messages = st.session_state.get("coding_room_messages", [])
    if not isinstance(messages, list):
        messages = []
    cleaned_content = str(content or "").strip()
    if not cleaned_content:
        return
    messages.append(
        {
            "role": "assistant" if str(role).strip().lower() == "assistant" else "user",
            "content": cleaned_content,
        }
    )
    st.session_state.coding_room_messages = messages[-40:]
    st.session_state.coding_room_scroll_pending = True


def category_style(category: str) -> tuple[str, str]:
    if category == "Perfect Match":
        return "#1E8E3E", "#E8F5E9"
    if category == "Excellent":
        return "#0B5394", "#E7F1FF"
    if category == "Good":
        return "#A56600", "#FFF4E5"
    return "#9C2E2E", "#FDECEC"


def render_app_styles() -> None:
    render_ui_styles()


def render_analysis_card(result: dict[str, Any]) -> None:
    color, bg = category_style(result["category"])
    st.markdown(
        f"""
        <div style="
            border: 1px solid {color};
            background: {bg};
            border-radius: 12px;
            padding: 16px;
            margin: 10px 0 16px 0;
        ">
            <h3 style="margin: 0 0 8px 0;">Match Result: {result["category"]}</h3>
            <p style="margin: 0;"><strong>Score:</strong> {result["score"]}%</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.write(result.get("summary", ""))
    st.markdown("**Strengths**")
    for item in result.get("strengths", []):
        st.write(f"- {item}")
    st.markdown("**Gaps**")
    for item in result.get("gaps", []):
        st.write(f"- {item}")
    st.markdown("**Recommendations**")
    for item in result.get("recommendations", []):
        st.write(f"- {item}")


def request_zoswi_submit() -> None:
    st.session_state.zoswi_submit = True


def request_full_chat_submit() -> None:
    st.session_state.full_chat_submit = True


def render_zoswi_autoscroll() -> None:
    st.components.v1.html(
        """
        <script>
        (function () {
            const doc = window.parent.document;
            const anchor = doc.getElementById("zoswi-scroll-anchor");
            if (!anchor) {
                return;
            }

            function findScrollableParent(node) {
                let current = node.parentElement;
                while (current) {
                    const style = window.parent.getComputedStyle(current);
                    const canScroll =
                        (style.overflowY === "auto" || style.overflowY === "scroll") &&
                        current.scrollHeight > current.clientHeight;
                    if (canScroll) {
                        return current;
                    }
                    current = current.parentElement;
                }
                return null;
            }

            const scrollParent = findScrollableParent(anchor);
            const scrollToBottom = () => {
                if (scrollParent) {
                    scrollParent.scrollTop = scrollParent.scrollHeight;
                }
                anchor.scrollIntoView({ block: "end", behavior: "smooth" });
            };

            scrollToBottom();
            window.parent.requestAnimationFrame(scrollToBottom);
            window.parent.setTimeout(scrollToBottom, 60);
            window.parent.setTimeout(scrollToBottom, 180);

            if (scrollParent) {
                if (scrollParent.__zoswiObserver) {
                    scrollParent.__zoswiObserver.disconnect();
                }
                const observer = new window.parent.MutationObserver(() => {
                    window.parent.requestAnimationFrame(scrollToBottom);
                });
                observer.observe(scrollParent, {
                    childList: true,
                    subtree: true,
                    characterData: true
                });
                scrollParent.__zoswiObserver = observer;
            }
        })();
        </script>
        """,
        height=0,
    )


def render_zoswi_outside_minimize_listener(is_open: bool) -> None:
    is_open_js = "true" if is_open else "false"
    st.components.v1.html(
        f"""
        <script>
        (function () {{
            const root = window.parent;
            const doc = root.document;
            root.__zoswiOpen = {is_open_js};

            if (!root.__zoswiOutsideHandler) {{
                root.__zoswiOutsideHandler = function (event) {{
                    if (!root.__zoswiOpen) {{
                        return;
                    }}
                    const target = event.target;
                    if (target && target.closest && target.closest(".st-key-zoswi_widget")) {{
                        return;
                    }}
                    const minimizeBtn = doc.querySelector(".st-key-zoswi_minimize button");
                    if (minimizeBtn) {{
                        root.setTimeout(function () {{
                            minimizeBtn.click();
                        }}, 0);
                    }}
                }};
                doc.addEventListener("click", root.__zoswiOutsideHandler);
            }}
        }})();
        </script>
        """,
        height=0,
    )


def format_zoswi_message_html(role: str, content: str, user_name: str) -> str:
    safe_content = html.escape(str(content)).replace("\n", "<br>")
    safe_user = html.escape((user_name or "You").strip()) or "You"
    if role == "assistant":
        return (
            '<div class="zoswi-msg assistant">'
            '<div class="zoswi-msg-head"><span>ZoSwi:</span></div>'
            f'<div class="zoswi-msg-text">{safe_content}</div>'
            "</div>"
        )
    return (
        '<div class="zoswi-msg user">'
        f'<div class="zoswi-msg-head"><span>{safe_user}:</span></div>'
        f'<div class="zoswi-msg-text">{safe_content}</div>'
        "</div>"
    )


def render_zoswi_widget() -> None:
    user = st.session_state.get("user") or {}
    user_id = int(user.get("id") or 0)
    full_name = str(user.get("full_name", "")).strip()
    active_chat_id = int(st.session_state.get("active_chat_id") or 0)
    first_name = full_name.split()[0] if full_name else "there"
    user_name_label = full_name.split()[0] if full_name else "You"
    stale_status_messages = {
        "zoswi is thinking...",
        "zoswi is typing.",
        "zoswi is typing..",
        "zoswi is typing...",
    }
    st.session_state.bot_messages = [
        msg
        for msg in st.session_state.bot_messages
        if str(msg.get("content", "")).strip().lower() not in stale_status_messages
    ]
    if st.session_state.get("clear_zoswi_input"):
        st.session_state.zoswi_input = ""
        st.session_state.clear_zoswi_input = False

    with st.container(key="zoswi_widget"):
        if st.session_state.bot_open:
            with st.container(key="zoswi_panel"):
                top_cols = st.columns([8, 1, 1, 1])
                with top_cols[0]:
                    st.markdown("**ZoSwi AI Assistant**")
                    st.caption(f"{time_based_greeting()}, {first_name}")
                with top_cols[1]:
                    if st.button("\u2212", key="zoswi_minimize", help="Minimize"):
                        st.session_state.bot_open = False
                        st.rerun()
                with top_cols[2]:
                    if st.button("\u21ba", key="zoswi_reset", help="Reset"):
                        st.session_state.active_chat_id = None
                        st.session_state.bot_messages = default_bot_messages(full_name)
                        st.session_state.bot_pending_prompt = None
                        st.rerun()
                with top_cols[3]:
                    if st.button("\u00d7", key="zoswi_close", help="Close"):
                        st.session_state.bot_open = False
                        st.session_state.bot_messages = default_bot_messages(full_name)
                        st.rerun()

                with st.container(height=300):
                    chat_history_container = st.container()
                    live_reply_container = st.container()
                    with chat_history_container:
                        for msg in st.session_state.bot_messages:
                            st.markdown(
                                format_zoswi_message_html(
                                    msg.get("role", "assistant"),
                                    msg.get("content", ""),
                                    user_name_label,
                                ),
                                unsafe_allow_html=True,
                            )
                    st.markdown('<div id="zoswi-scroll-anchor"></div>', unsafe_allow_html=True)
                    render_zoswi_autoscroll()

                pending_prompt = st.session_state.get("bot_pending_prompt")
                is_waiting_for_reply = bool(pending_prompt)
                input_cols = st.columns([6, 1])
                with input_cols[0]:
                    message = st.text_input(
                        "Ask ZoSwi",
                        key="zoswi_input",
                        on_change=request_zoswi_submit,
                        label_visibility="collapsed",
                        disabled=is_waiting_for_reply,
                    )
                with input_cols[1]:
                    send = st.button(
                        "\u2191",
                        key="zoswi_send",
                        help="Send",
                        use_container_width=True,
                        disabled=is_waiting_for_reply,
                    )

                submit_requested = send or bool(st.session_state.get("zoswi_submit"))
                if submit_requested:
                    st.session_state.zoswi_submit = False

                if submit_requested and not is_waiting_for_reply and message.strip():
                    clean_message = message.strip()
                    if user_id > 0 and active_chat_id <= 0:
                        active_chat_id = create_chat_session(user_id, "New Chat")
                        st.session_state.active_chat_id = active_chat_id
                    st.session_state.bot_messages.append({"role": "user", "content": clean_message})
                    save_chat_history(user_id, active_chat_id, "user", clean_message)
                    update_chat_session_title_if_default(active_chat_id, clean_message)
                    st.session_state.bot_pending_prompt = clean_message
                    st.session_state.clear_zoswi_input = True
                    st.rerun()

                if pending_prompt:
                    with live_reply_container:
                        response_placeholder = st.empty()
                        response_placeholder.markdown(
                            format_zoswi_message_html("assistant", "...", user_name_label),
                            unsafe_allow_html=True,
                        )
                        response_text = ""

                        for chunk in ask_assistant_bot_stream(str(pending_prompt)):
                            response_text += chunk
                            response_placeholder.markdown(
                                format_zoswi_message_html(
                                    "assistant",
                                    response_text + " \u258c",
                                    user_name_label,
                                ),
                                unsafe_allow_html=True,
                            )

                        if not response_text.strip():
                            response_text = "I hit a temporary issue generating a response. Please try again."

                        response_placeholder.markdown(
                            format_zoswi_message_html("assistant", response_text, user_name_label),
                            unsafe_allow_html=True,
                        )

                    st.session_state.bot_messages.append({"role": "assistant", "content": response_text})
                    save_chat_history(user_id, active_chat_id, "assistant", response_text)
                    st.session_state.bot_pending_prompt = None
                    st.rerun()

        if st.button(BOT_LAUNCHER_ICON, key="zoswi_fab", help="ZoSwi AI Agent"):
            st.session_state.bot_open = not st.session_state.bot_open
            st.rerun()
    render_zoswi_outside_minimize_listener(bool(st.session_state.get("bot_open")))


def init_state() -> None:
    defaults = {
        "user": None,
        "analysis_result": None,
        "bot_open": False,
        "bot_messages": default_bot_messages(),
        "bot_user_email": None,
        "active_chat_id": None,
        "zoswi_input": "",
        "zoswi_submit": False,
        "clear_zoswi_input": False,
        "bot_pending_prompt": None,
        "chat_rename_target": None,
        "dashboard_view": "home",
        "full_chat_input": "",
        "full_chat_submit": False,
        "clear_full_chat_input": False,
        "user_menu_open": False,
        "auth_session_token": None,
        "auth_cookie_value": None,
        "auth_cookie_clear": False,
        "auth_promo_code": "",
        "auth_promo_valid": False,
        "auth_promo_status": "",
        "auth_promo_checked_code": "",
        "signup_success_message": "",
        "signup_warning_message": "",
        "signup_form_reset_pending": False,
        "auth_notice_message": "",
        "email_verification_ref_id": 0,
        "email_verification_email": "",
        "email_verification_mode": "",
        "password_reset_flow_open": False,
        "password_reset_otp_sent": False,
        "password_reset_last_email": "",
        "password_reset_resend_after_ts": 0.0,
        "password_reset_form_reset_pending": False,
        "latest_resume_text": "",
        "latest_job_description": "",
        "latest_resume_file_name": "",
        "resume_editor_draft_text": "",
        "resume_editor_source_sig": "",
        "resume_export_panel_open": False,
        "coding_room_payload": None,
        "coding_room_source_sig": "",
        "coding_room_stage_index": 0,
        "coding_room_stage_scores": {},
        "coding_room_messages": [],
        "coding_room_submit": False,
        "coding_room_clear_input": False,
        "coding_room_user_input": "",
        "coding_room_language": CODING_LANGUAGES[0],
        "coding_room_session_started": False,
        "coding_room_scroll_pending": False,
        "coding_room_stage_started_at": {},
        "coding_room_hidden_tests": {},
        "coding_room_stage_approaches": {},
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def get_signup_form_text_keys() -> list[str]:
    return [
        "signup_first_name",
        "signup_last_name",
        "signup_email",
        "signup_university_email",
        "signup_recruiter_email",
        "signup_password",
        "signup_confirm_password",
        "signup_years_experience",
        "signup_candidate_target_role",
        "signup_university_name",
        "signup_graduation_year",
        "signup_degree_program",
        "signup_org_name",
        "signup_recruiter_title",
        "signup_hiring_focus",
    ]


def clear_signup_form_state() -> None:
    # Reset after rerun to avoid mutating widget state after instantiation.
    st.session_state.signup_form_reset_pending = True


def apply_pending_signup_form_reset() -> None:
    if not bool(st.session_state.get("signup_form_reset_pending")):
        return
    for key in get_signup_form_text_keys():
        if key in st.session_state:
            st.session_state[key] = ""
    st.session_state.signup_role_selector = "Candidate"
    st.session_state.signup_form_reset_pending = False


def get_password_reset_form_text_keys() -> list[str]:
    return [
        "password_reset_email_input",
        "password_reset_otp_code",
        "password_reset_new_password",
        "password_reset_confirm_password",
    ]


def clear_password_reset_flow_state() -> None:
    # Reset after rerun to avoid mutating widget state after instantiation.
    st.session_state.password_reset_flow_open = False
    st.session_state.password_reset_otp_sent = False
    st.session_state.password_reset_last_email = ""
    st.session_state.password_reset_resend_after_ts = 0.0
    st.session_state.password_reset_form_reset_pending = True


def apply_pending_password_reset_form_reset() -> None:
    if not bool(st.session_state.get("password_reset_form_reset_pending")):
        return
    for key in get_password_reset_form_text_keys():
        if key in st.session_state:
            st.session_state[key] = ""
    st.session_state.password_reset_form_reset_pending = False


def render_password_reset_timer_and_resend_widget(remaining_seconds: int) -> bool:
    safe_remaining = max(0, int(remaining_seconds or 0))
    with st.container(key="password_reset_resend_proxy"):
        resend_proxy_clicked = st.button(
            "Resend Code",
            key="password_reset_resend_proxy_btn",
            use_container_width=False,
        )
    st.components.v1.html(
        f"""
        <style>
            html, body {{
                margin: 0;
                padding: 0;
                background: transparent !important;
                overflow: hidden;
            }}
            #pwreset-inline-wrap {{
                min-height: 34px;
                display: flex;
                align-items: center;
                justify-content: flex-end;
                font-family: "Plus Jakarta Sans", "Segoe UI", sans-serif;
            }}
            #pwreset-inline-timer {{
                display: inline-flex;
                align-items: center;
                justify-content: center;
                min-width: 84px;
                padding: 0.34rem 0.62rem;
                border-radius: 999px;
                border: 1px solid #7dd3fc;
                background: #f0f9ff;
                color: #0369a1;
                font-size: 0.73rem;
                font-weight: 700;
                line-height: 1;
                white-space: nowrap;
            }}
            #pwreset-inline-resend {{
                display: none;
                border: 1px solid #7dd3fc;
                background: #ffffff;
                color: #0369a1;
                border-radius: 999px;
                padding: 0.32rem 0.62rem;
                font-size: 0.73rem;
                font-weight: 700;
                line-height: 1;
                cursor: pointer;
                white-space: nowrap;
            }}
            #pwreset-inline-resend:hover {{
                border-color: #38bdf8;
                background: #f0f9ff;
            }}
        </style>
        <div id="pwreset-inline-wrap">
            <span id="pwreset-inline-timer"></span>
            <button id="pwreset-inline-resend" type="button">Resend</button>
        </div>
        <script>
        (function () {{
            const timerEl = document.getElementById("pwreset-inline-timer");
            const resendEl = document.getElementById("pwreset-inline-resend");
            if (!timerEl || !resendEl) {{
                return;
            }}
            let remaining = {safe_remaining};
            function paint() {{
                if (remaining > 0) {{
                    timerEl.style.display = "inline-flex";
                    timerEl.textContent = "Resend in " + remaining + "s";
                    resendEl.style.display = "none";
                    return;
                }}
                timerEl.style.display = "none";
                resendEl.style.display = "inline-flex";
            }}
            paint();
            if (remaining > 0) {{
                const interval = setInterval(function () {{
                    remaining -= 1;
                    if (remaining <= 0) {{
                        remaining = 0;
                        clearInterval(interval);
                    }}
                    paint();
                }}, 1000);
            }}
            resendEl.addEventListener("click", function () {{
                const parentDoc = window.parent && window.parent.document ? window.parent.document : null;
                if (!parentDoc) {{
                    return;
                }}
                const proxyBtn = parentDoc.querySelector("[class*='st-key-password_reset_resend_proxy'] button");
                if (proxyBtn) {{
                    resendEl.disabled = true;
                    proxyBtn.click();
                }}
            }});
        }})();
        </script>
        """,
        height=36,
    )
    return bool(resend_proxy_clicked)


def render_password_reset_panel() -> None:
    send_clicked = False
    close_clicked = False
    resend_proxy_clicked = False
    cooldown_seconds = get_password_reset_resend_seconds()
    reset_email = str(st.session_state.get("password_reset_email_input", "")).strip()
    cleaned_reset_email = str(reset_email).strip().lower()
    last_reset_email = str(st.session_state.get("password_reset_last_email", "")).strip().lower()
    resend_after_ts = float(st.session_state.get("password_reset_resend_after_ts") or 0.0)
    remaining_seconds = int(max(0.0, resend_after_ts - time.time()) + 0.999)

    with st.container(key="password_reset_email_wrap"):
        left_col, center_col, right_col = st.columns([1.25, 3.5, 1.25], gap="small")
        with center_col:
            email_col, timer_col = st.columns([4.1, 1.45], gap="small")
            with email_col:
                reset_email = st.text_input(
                    "Reset Email",
                    key="password_reset_email_input",
                    placeholder="Enter registered email",
                    label_visibility="collapsed",
                )
                cleaned_reset_email = str(reset_email or "").strip().lower()
            with timer_col:
                should_show_resend_timer = bool(st.session_state.get("password_reset_otp_sent")) and bool(
                    last_reset_email
                )
                if should_show_resend_timer:
                    resend_proxy_clicked = render_password_reset_timer_and_resend_widget(remaining_seconds)
                else:
                    st.markdown("<div style='height:2.1rem;'></div>", unsafe_allow_html=True)
            with st.container(key="password_reset_actions"):
                send_col, close_col, spacer_col = st.columns([1.24, 0.9, 1.96], gap="small")
                with send_col:
                    with st.container(key="password_reset_send_btn"):
                        send_clicked = st.button(
                            "Send Code",
                            key="password_reset_send_otp_btn",
                            use_container_width=True,
                            type="primary",
                        )
                with close_col:
                    with st.container(key="password_reset_close_btn"):
                        close_clicked = st.button(
                            "Close",
                            key="password_reset_close_action_btn",
                            use_container_width=True,
                            type="secondary",
                        )
                with spacer_col:
                    st.markdown("", unsafe_allow_html=True)
        with left_col:
            st.markdown("", unsafe_allow_html=True)
        with right_col:
            st.markdown("", unsafe_allow_html=True)

    if send_clicked:
        sent, send_msg = send_password_reset_otp(reset_email)
        if sent:
            st.session_state.password_reset_otp_sent = True
            st.session_state.password_reset_last_email = cleaned_reset_email
            st.session_state.password_reset_resend_after_ts = time.time() + cooldown_seconds
            st.success(send_msg)
        else:
            wait_seconds = parse_wait_seconds_from_message(send_msg)
            if wait_seconds > 0:
                st.session_state.password_reset_otp_sent = True
                st.session_state.password_reset_last_email = cleaned_reset_email
                st.session_state.password_reset_resend_after_ts = time.time() + wait_seconds
                st.warning(send_msg)
            else:
                st.error(send_msg)

    if resend_proxy_clicked:
        resend_email = cleaned_reset_email or last_reset_email
        resent, resend_msg = send_password_reset_otp(resend_email)
        if resent:
            st.session_state.password_reset_otp_sent = True
            st.session_state.password_reset_last_email = resend_email
            st.session_state.password_reset_resend_after_ts = time.time() + cooldown_seconds
            st.success(f"Reset {EMAIL_CODE_NAME} sent again to your email.")
        else:
            wait_seconds = parse_wait_seconds_from_message(resend_msg)
            if wait_seconds > 0:
                st.session_state.password_reset_otp_sent = True
                st.session_state.password_reset_last_email = resend_email
                st.session_state.password_reset_resend_after_ts = time.time() + wait_seconds
                st.warning(resend_msg)
            else:
                st.error(resend_msg)

    if close_clicked:
        clear_password_reset_flow_state()
        sync_password_reset_query_param(False)
        st.rerun()

    if not bool(st.session_state.get("password_reset_otp_sent")):
        return

    otp_code = ""
    new_password = ""
    confirm_password = ""
    submit_reset = False
    with st.container(key="password_reset_fields_wrap"):
        left_fields_col, center_fields_col, right_fields_col = st.columns([1.25, 3.5, 1.25], gap="small")
        with center_fields_col:
            otp_code = st.text_input(
                f"Reset {EMAIL_CODE_NAME}",
                key="password_reset_otp_code",
                placeholder=f"Enter {EMAIL_CODE_NAME.lower()}",
                max_chars=EMAIL_OTP_DIGITS,
                label_visibility="collapsed",
            )
            new_password = st.text_input(
                "New Password",
                type="password",
                key="password_reset_new_password",
                placeholder="New password",
                label_visibility="collapsed",
            )
            confirm_password = st.text_input(
                "Confirm New Password",
                type="password",
                key="password_reset_confirm_password",
                placeholder="Confirm new password",
                label_visibility="collapsed",
            )

            password_policy = get_password_policy_status(new_password)
            render_password_policy_checklist(password_policy, new_password, confirm_password)

            password_policy_ok = bool(
                password_policy["min_length"]
                and password_policy["has_upper"]
                and password_policy["has_special"]
            )
            passwords_match = bool(new_password) and bool(confirm_password) and new_password == confirm_password
            otp_ready = len(re.sub(r"\D", "", str(otp_code or "").strip())) == EMAIL_OTP_DIGITS
            submit_left_col, submit_center_col, submit_right_col = st.columns([1.1, 1.5, 1.1], gap="small")
            with submit_center_col:
                with st.container(key="password_reset_submit_btn"):
                    submit_reset = st.button(
                        "Reset Password",
                        key="password_reset_submit_action_btn",
                        use_container_width=True,
                        disabled=not (password_policy_ok and passwords_match and otp_ready),
                    )
        with left_fields_col:
            st.markdown("", unsafe_allow_html=True)
        with right_fields_col:
            st.markdown("", unsafe_allow_html=True)

    if submit_reset:
        reset_ok, reset_msg = reset_password_with_email_otp(reset_email, otp_code, new_password, confirm_password)
        if reset_ok:
            clear_password_reset_flow_state()
            sync_password_reset_query_param(False)
            st.session_state.auth_notice_message = reset_msg
            st.rerun()
        else:
            st.error(reset_msg)


def render_email_verification_panel() -> None:
    pending_ref_id = int(st.session_state.get("email_verification_ref_id") or 0)
    pending_email = str(st.session_state.get("email_verification_email", "")).strip().lower()
    verification_mode = str(st.session_state.get("email_verification_mode", "")).strip().lower()
    if pending_ref_id <= 0 or not pending_email:
        return

    st.markdown("---")
    st.caption(f"Verify your email to continue: {pending_email}")
    otp_code = ""
    verify_clicked = False
    resend_clicked = False
    cancel_clicked = False
    with st.container(key="email_verification_panel_wrap"):
        left_col, center_col, right_col = st.columns([1.25, 3.5, 1.25], gap="small")
        with center_col:
            otp_code = st.text_input(
                f"Email {EMAIL_CODE_NAME}",
                key="email_verification_otp_code",
                placeholder=f"Enter {EMAIL_OTP_DIGITS}-digit {EMAIL_CODE_NAME.lower()}",
                max_chars=EMAIL_OTP_DIGITS,
                label_visibility="collapsed",
            )
            with st.container(key="email_verification_actions"):
                verify_col, resend_col, cancel_col = st.columns([1.1, 1.1, 0.9], gap="small")
                with verify_col:
                    with st.container(key="email_verify_btn"):
                        verify_clicked = st.button("Verify Code", key="verify_email_otp_btn", use_container_width=True)
                with resend_col:
                    with st.container(key="email_resend_btn"):
                        resend_clicked = st.button("Resend Code", key="resend_email_otp_btn", use_container_width=True)
                with cancel_col:
                    with st.container(key="email_cancel_btn"):
                        cancel_clicked = st.button("Cancel", key="cancel_email_otp_btn", use_container_width=True)
        with left_col:
            st.markdown("", unsafe_allow_html=True)
        with right_col:
            st.markdown("", unsafe_allow_html=True)

    if verify_clicked:
        if verification_mode == "user_account":
            verified, verify_msg = verify_email_verification_otp(pending_ref_id, pending_email, otp_code)
        else:
            verified, verify_msg = verify_signup_verification_otp(pending_ref_id, pending_email, otp_code)
        if verified:
            clear_pending_email_verification()
            st.session_state.signup_success_message = ""
            st.session_state.signup_warning_message = ""
            st.session_state.auth_notice_message = verify_msg
            st.session_state.auth_view_selector = "Login"
            st.rerun()
        else:
            st.error(verify_msg)

    if resend_clicked:
        if verification_mode == "user_account":
            resent, resend_msg = send_email_verification_otp(pending_ref_id, pending_email)
        else:
            resent, resend_msg = send_signup_verification_otp(pending_ref_id, pending_email)
        if resent:
            st.success(resend_msg)
        else:
            st.error(resend_msg)

    if cancel_clicked:
        clear_pending_email_verification()
        st.info("Email verification canceled. You can restart it from login.")


def render_auth_motivation_quote_box(role_context: str = "login") -> None:
    rocket = chr(0x1F680)
    lightning = chr(0x26A1)
    target = chr(0x1F3AF)
    chart_up = chr(0x1F4C8)
    briefcase = chr(0x1F4BC)
    grad_cap = chr(0x1F393)
    seedling = chr(0x1F331)
    books = chr(0x1F4DA)
    handshake = chr(0x1F91D)
    puzzle = chr(0x1F9E9)
    sparkles = chr(0x2728)
    star = chr(0x1F31F)

    role_key = str(role_context or "login").strip().lower()
    quote_sets: dict[str, dict[str, Any]] = {
        "login": {
            "mode": f"Login Confidence {lightning}",
            "quotes": [
                f"Welcome back. One small upskill today can unlock bigger roles tomorrow {rocket}",
                f"Your pace is enough. Keep learning, keep applying, keep winning {briefcase}",
                f"Confidence grows from action. Start with one focused step today {star}",
                f"Zoswi is with you. Build skills, show impact, and move ahead {chart_up}",
            ],
        },
        "candidate": {
            "mode": f"Candidate Mode {target}",
            "quotes": [
                f"Every tailored application sharpens your interview edge {rocket}",
                f"Upskill one tool this week and raise your market value fast {chart_up}",
                f"Interviews reward preparation. You are closer than you think {sparkles}",
                f"Your outcomes matter. Lead with impact, not only tasks {briefcase}",
            ],
        },
        "student": {
            "mode": f"Student Mode {grad_cap}",
            "quotes": [
                f"Projects plus consistency can beat experience gaps {seedling}",
                f"Learn in public, build your portfolio, and opportunities follow {rocket}",
                f"One internship-ready project can open your first big door {chart_up}",
                f"You do not need to know everything. Start, iterate, improve {books}",
            ],
        },
        "recruiter": {
            "mode": f"Recruiter Mode {handshake}",
            "quotes": [
                f"Clear feedback attracts stronger candidates faster {chart_up}",
                f"Great hiring is a skill. Every interview makes your process sharper {sparkles}",
                f"Better role briefs create better matches and stronger teams {puzzle}",
                f"You shape careers daily. That impact is powerful {star}",
            ],
        },
    }
    chosen = quote_sets.get(role_key, quote_sets["login"])
    mode_label = html.escape(str(chosen.get("mode", "Login Confidence")))
    payload = json.dumps(chosen.get("quotes", []), ensure_ascii=True)
    st.components.v1.html(
        f"""
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;700&display=swap');
            html, body {{
                margin: 0;
                padding: 0;
                background: transparent !important;
            }}
            #auth-motivation-wrap {{
                margin: 0;
                background: transparent;
            }}
            #auth-motivation-card {{
                position: relative;
                overflow: hidden;
                background: linear-gradient(140deg, #06080d 0%, #10182b 60%, #122646 100%);
                border: 1px solid rgba(125, 211, 252, 0.36);
                border-radius: 14px;
                padding: 12px 12px 11px 12px;
                color: #f8fafc;
                box-shadow: none;
                min-height: 126px;
                font-family: "Plus Jakarta Sans", "Nunito Sans", "Trebuchet MS", sans-serif;
                opacity: 0;
                transform: translateY(20px) scale(0.98);
                animation: authCardPop 460ms cubic-bezier(0.2, 0.9, 0.2, 1) forwards;
            }}
            #auth-motivation-header-row {{
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 8px;
                position: relative;
                z-index: 1;
            }}
            #auth-motivation-header {{
                font-size: 0.78rem;
                font-weight: 700;
                letter-spacing: 0.05em;
                text-transform: uppercase;
                color: #a5f3fc;
            }}
            #auth-motivation-mode {{
                font-size: 0.66rem;
                font-weight: 700;
                letter-spacing: 0.02em;
                color: #0f172a;
                background: linear-gradient(120deg, #67e8f9, #bae6fd);
                border-radius: 999px;
                padding: 2px 8px;
                white-space: nowrap;
            }}
            #auth-motivation-quote-shell {{
                position: relative;
                z-index: 1;
                border: 1px solid rgba(148, 163, 184, 0.25);
                border-radius: 10px;
                background: rgba(15, 23, 42, 0.46);
                padding: 8px 9px;
                min-height: 70px;
                display: flex;
                gap: 6px;
                align-items: flex-start;
            }}
            #auth-motivation-quote-mark {{
                font-size: 1.06rem;
                line-height: 1;
                color: #67e8f9;
                margin-top: 2px;
            }}
            #auth-motivation-quote {{
                flex: 1;
                font-size: 0.84rem;
                line-height: 1.35;
                opacity: 1;
                transition: opacity 0.28s ease;
                color: #e5e7eb;
                overflow-wrap: anywhere;
            }}
            @keyframes authCardPop {{
                from {{ opacity: 0; transform: translateY(20px) scale(0.98); }}
                to {{ opacity: 1; transform: translateY(0px) scale(1); }}
            }}
        </style>
        <div id="auth-motivation-wrap">
            <div id="auth-motivation-card">
                <div id="auth-motivation-header-row">
                    <div id="auth-motivation-header">Zoswi Career Boost {rocket}</div>
                    <div id="auth-motivation-mode">{mode_label}</div>
                </div>
                <div id="auth-motivation-quote-shell">
                    <div id="auth-motivation-quote-mark">&#x201C;</div>
                    <div id="auth-motivation-quote"></div>
                </div>
            </div>
        </div>
        <script>
        (function () {{
            const quotes = {payload};
            if (!Array.isArray(quotes) || quotes.length === 0) {{
                return;
            }}
            const quoteEl = document.getElementById("auth-motivation-quote");
            if (!quoteEl) {{
                return;
            }}

            function pickNext(currentIndex) {{
                if (quotes.length <= 1) {{
                    return 0;
                }}
                let next = currentIndex;
                while (next === currentIndex) {{
                    next = Math.floor(Math.random() * quotes.length);
                }}
                return next;
            }}

            let activeIndex = Math.floor(Math.random() * quotes.length);
            function renderQuote() {{
                quoteEl.textContent = quotes[activeIndex];
            }}
            function switchQuote(nextIndex) {{
                quoteEl.style.opacity = "0";
                setTimeout(() => {{
                    activeIndex = nextIndex;
                    renderQuote();
                    quoteEl.style.opacity = "1";
                }}, 150);
            }}

            renderQuote();
            setInterval(() => {{
                const nextIndex = pickNext(activeIndex);
                switchQuote(nextIndex);
            }}, 40000);
        }})();
        </script>
        """,
        height=188,
    )


def render_auth_screen() -> None:
    render_app_styles()
    render_zoswi_outside_minimize_listener(False)
    render_top_left_logo()
    st.title("Resume AI Checker")
    apply_pending_signup_form_reset()
    apply_pending_password_reset_form_reset()
    if "auth_view_selector" not in st.session_state:
        st.session_state.auth_view_selector = read_auth_view_from_query_params()
    quote_role_context = "login"
    if normalize_auth_view(str(st.session_state.get("auth_view_selector", "Login"))) == "Create Account":
        quote_role_context = str(st.session_state.get("signup_role_selector", "Candidate")).strip().lower()

    oauth_col, account_col = st.columns(2, gap="large")

    with oauth_col:
        if is_streamlit_oauth_configured():
            redirect_mismatch, configured_redirect, expected_redirect = oauth_redirect_uri_mismatch()
            google_available = is_streamlit_oauth_provider_available("google")
            linkedin_available = is_streamlit_oauth_provider_available("linkedin")
            google_provider_name = get_streamlit_oauth_provider_name("google")
            linkedin_provider_name = get_streamlit_oauth_provider_name("linkedin")
            if redirect_mismatch:
                google_available = False
                linkedin_available = False

            st.markdown("<div style='height:2in;'></div>", unsafe_allow_html=True)
            with st.container(key="oauth_social_stack"):
                left_space, button_col, right_space = st.columns([1,2,1], gap="large")
                with button_col:
                    if redirect_mismatch:
                        st.error("OAuth redirect URI is set to localhost and cannot work on this deployed app.")
                        if expected_redirect:
                            st.caption(
                                f"Update `[auth].redirect_uri` to `{expected_redirect}` "
                                f"(current: `{configured_redirect or 'not set'}`), then redeploy."
                            )
                    promo_enabled = promo_codes_enabled()
                    google_btn_label = (
                        "![Google](https://www.gstatic.com/images/branding/product/1x/googleg_32dp.png) "
                        "Continue with Google"
                    )
                    linkedin_btn_label = (
                        "![LinkedIn](https://upload.wikimedia.org/wikipedia/commons/c/ca/LinkedIn_logo_initials.png) "
                        "Continue with LinkedIn"
                    )
                    if st.button(
                        google_btn_label,
                        key="oauth_login_btn",
                        use_container_width=True,
                        disabled=not google_available,
                    ):
                        try:
                            if is_streamlit_oauth_logged_in():
                                sync_user_from_oauth_session()
                                if st.session_state.get("user") is not None:
                                    st.rerun()
                            else:
                                if google_provider_name:
                                    st.login(google_provider_name)
                                else:
                                    st.login()
                        except Exception as ex:
                            st.error(f"OAuth login setup issue: {ex}")
                    if st.button(
                        linkedin_btn_label,
                        key="oauth_login_linkedin_btn",
                        use_container_width=True,
                        disabled=not linkedin_available,
                    ):
                        try:
                            if is_streamlit_oauth_logged_in():
                                sync_user_from_oauth_session()
                                if st.session_state.get("user") is not None:
                                    st.rerun()
                            elif linkedin_provider_name:
                                st.login(linkedin_provider_name)
                        except Exception as ex:
                            st.error(f"LinkedIn OAuth login setup issue: {ex}")
                    if not linkedin_available:
                        st.caption("LinkedIn OAuth is not configured yet.")
                    if promo_enabled:
                        with st.container(key="oauth_promo_code"):
                            promo_input_col, promo_send_col = st.columns([5, 1], gap="small")
                            with promo_input_col:
                                promo_code_text = st.text_input(
                                    "Have a promo code",
                                    key="auth_promo_code",
                                    placeholder="Have a promo code",
                                    label_visibility="collapsed",
                                )

                            normalized_current = normalize_promo_code(promo_code_text)
                            checked_code = normalize_promo_code(
                                str(st.session_state.get("auth_promo_checked_code", ""))
                            )
                            if normalized_current != checked_code:
                                st.session_state.auth_promo_valid = False
                                st.session_state.auth_promo_status = ""

                            with promo_send_col:
                                apply_promo = st.button(
                                    "\u2192",
                                    key="oauth_promo_send",
                                    help="Apply promo code",
                                    use_container_width=True,
                                )

                            if apply_promo:
                                ok_promo, promo_msg, normalized_code = validate_promo_code(promo_code_text)
                                st.session_state.auth_promo_valid = ok_promo
                                st.session_state.auth_promo_status = promo_msg
                                st.session_state.auth_promo_checked_code = normalized_code

                            promo_status_text = str(st.session_state.get("auth_promo_status", "")).strip()
                            if promo_status_text:
                                if bool(st.session_state.get("auth_promo_valid")):
                                    st.success(promo_status_text)
                                else:
                                    st.error(promo_status_text)
                    spacer_height = "3.2rem" if promo_enabled else "5.8rem"
                    st.markdown(f"<div style='height:{spacer_height};'></div>", unsafe_allow_html=True)
                    with st.container(key="oauth_motivation_popup"):
                        render_auth_motivation_quote_box(quote_role_context)
        else:
            st.info("Google OAuth is not configured yet. Use login or create account on the right.")

    with account_col:
        st.caption("Create an account or log in to start resume-job matching.")
        auth_notice_message = str(st.session_state.get("auth_notice_message", "")).strip()
        if auth_notice_message:
            st.success(auth_notice_message)
            st.session_state.auth_notice_message = ""
        auth_view = st.radio(
            "Auth View",
            options=["Login", "Create Account"],
            key="auth_view_selector",
            horizontal=True,
            label_visibility="collapsed",
        )
        sync_auth_view_query_param(auth_view)

        if auth_view == "Login":
            with st.container(key="login_form_shell"):
                with st.form("login_form"):
                    left_gap, center_col, right_gap = st.columns([1, 3, 1], gap="small")
                    with center_col:
                        with st.container(key="login_form_center"):
                            email = st.text_input("Email")
                            password = st.text_input("Password", type="password")
                            open_reset = False
                            with st.container(key="login_forgot_row"):
                                forgot_label_col, forgot_reset_col = st.columns([8, 2], gap="small")
                                with forgot_label_col:
                                    st.markdown(
                                        '<div class="auth-forgot-label">Don\'t remember your password?</div>',
                                        unsafe_allow_html=True,
                                    )
                                with forgot_reset_col:
                                    with st.container(key="login_forgot_reset_btn"):
                                        open_reset = st.form_submit_button(
                                            "reset",
                                            use_container_width=False,
                                        )
                            with st.container(key="login_actions"):
                                with st.container(key="login_submit_btn"):
                                    submit = st.form_submit_button("Login", use_container_width=False, type="primary")
            login_email_prefill = str(email or "").strip().lower()
            if open_reset:
                st.session_state.password_reset_flow_open = True
                sync_password_reset_query_param(False)
                st.rerun()
            if read_password_reset_from_query_params():
                st.session_state.password_reset_flow_open = True
            if bool(st.session_state.get("password_reset_flow_open")) and login_email_prefill:
                current_reset_email = str(st.session_state.get("password_reset_email_input", "")).strip()
                if not current_reset_email:
                    st.session_state.password_reset_email_input = login_email_prefill
            if submit:
                user = authenticate_user(email, password)
                if user:
                    if bool(user.get("pending_verification")):
                        pending_user_id = int(user.get("id") or 0)
                        pending_email = str(user.get("email") or email).strip().lower()
                        mark_pending_email_verification(
                            pending_user_id,
                            pending_email,
                            mode="user_account",
                        )
                        sent, otp_msg = send_email_verification_otp(pending_user_id, pending_email)
                        if sent:
                            st.warning("Email not verified. A verification code has been sent to your inbox.")
                        else:
                            st.warning(f"Email not verified. {otp_msg}")
                        st.rerun()
                    user_id = int(user.get("id") or 0)
                    auth_token = create_auth_session(user_id)
                    record_user_login_event(user_id, "password", "local")
                    clear_pending_email_verification()
                    st.session_state.user = user
                    full_name = str(user.get("full_name", "")).strip()
                    st.session_state.bot_user_email = None
                    st.session_state.active_chat_id = None
                    st.session_state.bot_open = True
                    st.session_state.bot_messages = default_bot_messages(full_name)
                    st.session_state.bot_pending_prompt = None
                    st.session_state.zoswi_submit = False
                    st.session_state.clear_zoswi_input = True
                    st.session_state.full_chat_submit = False
                    st.session_state.clear_full_chat_input = True
                    st.session_state.dashboard_view = "home"
                    st.session_state.user_menu_open = False
                    st.session_state.auth_session_token = auth_token or None
                    if auth_token:
                        queue_set_auth_cookie(auth_token)
                    st.success("Logged in successfully.")
                    st.rerun()
                else:
                    pending_signup = get_pending_signup_request_by_email(email)
                    if pending_signup is not None and verify_password(
                        str(password or ""),
                        str(pending_signup.get("password_hash", "")),
                    ):
                        pending_request_id = int(pending_signup.get("id") or 0)
                        pending_email = str(pending_signup.get("email", "")).strip().lower()
                        mark_pending_email_verification(
                            pending_request_id,
                            pending_email,
                            mode="signup_request",
                        )
                        sent, otp_msg = send_signup_verification_otp(pending_request_id, pending_email)
                        if sent:
                            st.warning("Account verification pending. We sent a verification code to your email.")
                        else:
                            st.warning(f"Account verification pending. {otp_msg}")
                        st.rerun()
                    st.error("Invalid email or password.")

            if bool(st.session_state.get("password_reset_flow_open")):
                render_password_reset_panel()

        else:
            signup_success_message = str(st.session_state.get("signup_success_message", "")).strip()
            signup_warning_message = str(st.session_state.get("signup_warning_message", "")).strip()
            if signup_success_message:
                st.success(signup_success_message)
                if signup_warning_message:
                    st.warning(signup_warning_message)
                if int(st.session_state.get("email_verification_ref_id") or 0) > 0:
                    st.info(f"Enter the {EMAIL_CODE_NAME.lower()} below to finish account creation.")
                else:
                    st.info("Use the Login tab to sign in.")
                if st.button("Create another account", key="signup_create_another_btn"):
                    st.session_state.signup_success_message = ""
                    st.session_state.signup_warning_message = ""
                    clear_pending_email_verification()
                    clear_signup_form_state()
                    st.rerun()
            else:
                role = st.radio(
                    "I am a",
                    options=["Candidate", "Student", "Recruiter"],
                    horizontal=True,
                    key="signup_role_selector",
                )
                first_name_col, last_name_col = st.columns(2, gap="small")
                with first_name_col:
                    first_name = st.text_input("First Name", key="signup_first_name")
                with last_name_col:
                    last_name = st.text_input("Last Name", key="signup_last_name")
                email_label = "Email"
                if role == "Student":
                    email_label = "Personal Email"
                elif role == "Recruiter":
                    email_label = "Login Email"
                email = st.text_input(email_label, key="signup_email")
                role_contact_email = ""
                years_experience = ""
                role_profile_data: dict[str, str] = {}
                if role == "Candidate":
                    years_experience = st.text_input(
                        "Years of Experience",
                        key="signup_years_experience",
                        placeholder="For example: 0, 2, or 5.5",
                    )
                    target_role = st.text_input(
                        "Target Role (optional)",
                        key="signup_candidate_target_role",
                        placeholder="For example: Data Analyst",
                    )
                    role_profile_data = {"target_role": target_role}
                elif role == "Student":
                    role_contact_email = st.text_input("University Email", key="signup_university_email")
                    university_name = st.text_input("University Name", key="signup_university_name")
                    graduation_year = st.text_input(
                        "Graduation Year",
                        key="signup_graduation_year",
                        placeholder=str(datetime.now(timezone.utc).year + 1),
                    )
                    degree_program = st.text_input(
                        "Program / Degree (optional)",
                        key="signup_degree_program",
                    )
                    role_profile_data = {
                        "university_name": university_name,
                        "graduation_year": graduation_year,
                        "degree_program": degree_program,
                    }
                elif role == "Recruiter":
                    role_contact_email = st.text_input(
                        "Recruiter / Organization Email",
                        key="signup_recruiter_email",
                    )
                    organization_name = st.text_input("Organization Name", key="signup_org_name")
                    recruiter_title = st.text_input(
                        "Your Title (optional)",
                        key="signup_recruiter_title",
                    )
                    hiring_focus = st.text_input(
                        "Hiring Focus (optional)",
                        key="signup_hiring_focus",
                    )
                    role_profile_data = {
                        "organization_name": organization_name,
                        "recruiter_title": recruiter_title,
                        "hiring_focus": hiring_focus,
                    }
                password_col, password_status_col = st.columns([4, 2], gap="small")
                with password_col:
                    password = st.text_input("Password", type="password", key="signup_password")
                    confirm_password = st.text_input(
                        "Re-enter Password",
                        type="password",
                        key="signup_confirm_password",
                    )
                with password_status_col:
                    st.markdown("<div style='height:1.9rem;'></div>", unsafe_allow_html=True)
                    password_policy = get_password_policy_status(password)
                    render_password_policy_checklist(password_policy, password, confirm_password)
                    if password and confirm_password and password != confirm_password:
                        st.markdown(
                            "<span style='color:#dc2626;font-size:0.86rem;font-weight:600;'>"
                            "The password entered is wrong."
                            "</span>",
                            unsafe_allow_html=True,
                        )
                password_policy_ok = bool(
                    password_policy["min_length"]
                    and password_policy["has_upper"]
                    and password_policy["has_special"]
                )
                passwords_match = bool(password) and bool(confirm_password) and password == confirm_password
                submit_signup = st.button(
                    "Create Account",
                    key="signup_submit_btn",
                    disabled=not (password_policy_ok and passwords_match),
                )
                if submit_signup:
                    cleaned_first_name = str(first_name or "").strip()
                    cleaned_last_name = str(last_name or "").strip()
                    cleaned_email = str(email or "").strip()
                    cleaned_password = str(password or "")
                    cleaned_confirm_password = str(confirm_password or "")
                    password_ok, password_msg = validate_password_strength(cleaned_password)
                    full_name = " ".join(
                        part for part in [cleaned_first_name, cleaned_last_name] if part
                    )

                    email_ok, email_msg = validate_signup_email_for_role(cleaned_email, role)
                    role_email_ok, role_email_msg = validate_role_specific_email(role, role_contact_email)
                    duplicate_exists = False
                    if cleaned_email and email_ok:
                        role_email_for_lookup = role_contact_email if role_email_ok else ""
                        duplicate_exists = user_exists_for_signup(cleaned_email, role_email_for_lookup)

                    missing_fields: list[str] = []
                    if not cleaned_first_name:
                        missing_fields.append("First Name")
                    if not cleaned_last_name:
                        missing_fields.append("Last Name")
                    if not cleaned_email:
                        missing_fields.append("Email")
                    if not cleaned_password:
                        missing_fields.append("Password")
                    if not cleaned_confirm_password:
                        missing_fields.append("Re-enter Password")

                    if duplicate_exists:
                        st.error("User exists, please login.")
                    elif missing_fields:
                        st.error(f"Required: {', '.join(missing_fields)}.")
                    elif cleaned_password != cleaned_confirm_password:
                        st.error("Passwords do not match.")
                    elif not password_ok:
                        st.error(password_msg)
                    elif not email_ok:
                        st.error(email_msg)
                    elif not role_email_ok:
                        st.error(role_email_msg)
                    else:
                        role_profile_ok, role_profile_msg, normalized_years, cleaned_profile_data = (
                            validate_role_profile_inputs(
                                role,
                                years_experience,
                                role_profile_data,
                            )
                        )
                        if not role_profile_ok:
                            st.error(role_profile_msg)
                        else:
                            request_ok, request_msg, request_id = create_or_update_signup_verification_request(
                                full_name,
                                cleaned_email,
                                cleaned_password,
                                role,
                                normalized_years,
                                role_contact_email=role_contact_email,
                                profile_data=cleaned_profile_data,
                                promo_code="",
                            )
                            if not request_ok:
                                st.error(request_msg)
                            else:
                                mark_pending_email_verification(
                                    request_id,
                                    cleaned_email,
                                    mode="signup_request",
                                )
                                sent, otp_msg = send_signup_verification_otp(request_id, cleaned_email)
                                st.session_state.signup_success_message = (
                                    f"Verification code sent. Enter {EMAIL_CODE_NAME.lower()} below to finish account creation."
                                )
                                st.session_state.signup_warning_message = ""
                                if not sent:
                                    st.session_state.signup_warning_message = otp_msg
                                clear_signup_form_state()
                                st.rerun()

        render_email_verification_panel()


def logout_current_user() -> None:
    oauth_logged_in = is_streamlit_oauth_logged_in()
    auth_token = str(st.session_state.get("auth_session_token") or "").strip()
    if auth_token:
        revoke_auth_session(auth_token)
    queue_clear_auth_cookie()
    st.session_state.user = None
    st.session_state.analysis_result = None
    st.session_state.bot_open = False
    st.session_state.bot_messages = default_bot_messages()
    st.session_state.bot_user_email = None
    st.session_state.active_chat_id = None
    st.session_state.zoswi_input = ""
    st.session_state.zoswi_submit = False
    st.session_state.clear_zoswi_input = False
    st.session_state.bot_pending_prompt = None
    st.session_state.chat_rename_target = None
    st.session_state.dashboard_view = "home"
    st.session_state.full_chat_input = ""
    st.session_state.full_chat_submit = False
    st.session_state.clear_full_chat_input = False
    st.session_state.user_menu_open = False
    st.session_state.auth_session_token = None
    st.session_state.latest_resume_text = ""
    st.session_state.latest_job_description = ""
    st.session_state.latest_resume_file_name = ""
    st.session_state.resume_editor_draft_text = ""
    st.session_state.resume_editor_source_sig = ""
    st.session_state.resume_export_panel_open = False
    st.session_state.coding_room_payload = None
    st.session_state.coding_room_source_sig = ""
    st.session_state.coding_room_stage_index = 0
    st.session_state.coding_room_stage_scores = {}
    st.session_state.coding_room_messages = []
    st.session_state.coding_room_submit = False
    st.session_state.coding_room_clear_input = False
    st.session_state.coding_room_user_input = ""
    st.session_state.coding_room_language = CODING_LANGUAGES[0]
    st.session_state.coding_room_session_started = False
    st.session_state.coding_room_scroll_pending = False
    st.session_state.coding_room_stage_started_at = {}
    st.session_state.coding_room_hidden_tests = {}
    st.session_state.coding_room_stage_approaches = {}
    clear_pending_email_verification()
    clear_password_reset_flow_state()
    if oauth_logged_in:
        try:
            st.logout()
        except Exception:
            pass


def render_candidate_sidebar(user: dict[str, Any]) -> None:
    user_id = int(user.get("id") or 0)
    backfill_default_chat_titles(user_id)
    user_menu_open = bool(st.session_state.get("user_menu_open", False))
    full_name_raw = str(user.get("full_name", "")).strip()
    first_name = full_name_raw.split()[0] if full_name_raw else "Candidate"
    menu_title = f"{first_name}'s Menu"
    signed_in_name = html.escape(first_name)

    with st.sidebar:
        with st.container(key="sidebar_menu_body"):
            with st.container(key="sidebar_signed_row"):
                signed_cols = st.columns([7, 3], gap="small")
                with signed_cols[0]:
                    st.markdown(
                        f'<div class="ai-sidebar-signed">Signed in as <strong>{signed_in_name}</strong></div>',
                        unsafe_allow_html=True,
                    )
                with signed_cols[1]:
                    with st.container(key="sidebar_header_logout"):
                        if st.button(
                            " ",
                            key="sidebar_header_logout_btn",
                            help="Sign out",
                            icon=":material/logout:",
                        ):
                            logout_current_user()
                            st.rerun()
            with st.container(key="sidebar_menu_toggle"):
                if st.button(f"\u2630 {menu_title}", key="sidebar_menu_toggle_btn", use_container_width=True):
                    st.session_state.user_menu_open = not user_menu_open
                    st.rerun()

            if user_menu_open:
                with st.container(key="sidebar_nav_menu"):
                    if st.button("Recent Chats", key="sidebar_nav_chats", use_container_width=True):
                        st.session_state.dashboard_view = "chats"
                        st.session_state.bot_open = False
                        st.rerun()
                    if st.button("Recent Scores", key="sidebar_nav_scores", use_container_width=True):
                        st.session_state.dashboard_view = "scores"
                        st.rerun()
                    has_analysis = bool(st.session_state.get("analysis_result"))
                    coding_button_label = "AI Coding Room" if has_analysis else "AI Coding Room (Locked)"
                    if st.button(
                        coding_button_label,
                        key="sidebar_nav_coding_room",
                        use_container_width=True,
                        disabled=not has_analysis,
                    ):
                        st.session_state.dashboard_view = "coding_room"
                        st.session_state.bot_open = False
                        st.rerun()
                    if st.button("Home", key="sidebar_nav_home", use_container_width=True):
                        st.session_state.dashboard_view = "home"
                        st.rerun()


def render_home_dashboard(user: dict[str, Any]) -> None:
    st.markdown(
        """
        <div class="ai-hero">
            <div class="ai-chip">Resume AI + JD Analysis</div>
            <h1>Evaluate Resume Fit Against Job Descriptions</h1>
            <p>Upload a resume, paste the JD, and get a strict fit score with strengths, gaps, and action-focused recommendations.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Input")
    st.caption("Use a clear JD and a text-readable resume for the best analysis quality.")
    st.markdown(
        """
        <style>
        .st-key-home_jd_analyze_btn button {
            border-radius: 999px !important;
            border: 1px solid #1d4ed8 !important;
            background: linear-gradient(135deg, #0ea5e9 0%, #2563eb 100%) !important;
            color: #ffffff !important;
            padding: 0.32rem 0.9rem !important;
            font-size: 0.82rem !important;
            font-weight: 700 !important;
            box-shadow: 0 8px 20px rgba(37, 99, 235, 0.26) !important;
        }
        .st-key-home_jd_analyze_btn button:hover {
            border-color: #1e40af !important;
            filter: brightness(1.03) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    analyze_clicked = False
    upload_col, jd_col = st.columns(2)
    with upload_col:
        uploaded_file = st.file_uploader("Upload Resume (PDF or DOCX)", type=["pdf", "docx"])
    with jd_col:
        job_description = st.text_area("Paste Job Description", height=280)
        st.caption(f"JD must include role details and at least {MIN_JOB_DESCRIPTION_WORDS} words.")
        with st.container(key="home_jd_analyze_btn"):
            analyze_clicked = st.button(
                "Run Resume-JD Analysis",
                key="home_run_resume_jd_analysis_btn",
                use_container_width=False,
            )

    if analyze_clicked:
        if not uploaded_file:
            st.error("Please upload a resume file.")
            return
        jd_ok, jd_error = validate_job_description_text(job_description)
        if not jd_ok:
            st.error(jd_error)
            return

        with st.spinner("Extracting and analyzing resume..."):
            try:
                resume_text = extract_resume_text(uploaded_file)
                if not resume_text.strip():
                    st.error("Could not extract text from file.")
                    return
                result = analyze_resume_with_ai(resume_text, job_description)
                st.session_state.analysis_result = result
                st.session_state.latest_resume_text = resume_text
                st.session_state.latest_job_description = str(job_description or "").strip()
                st.session_state.latest_resume_file_name = str(getattr(uploaded_file, "name", "resume")).strip()
                st.session_state.resume_export_panel_open = False
                st.session_state.coding_room_source_sig = ""
                st.session_state.coding_room_payload = None
                st.session_state.coding_room_stage_index = 0
                st.session_state.coding_room_stage_scores = {}
                st.session_state.coding_room_messages = []
                st.session_state.coding_room_session_started = False
                st.session_state.coding_room_scroll_pending = False
                st.session_state.coding_room_stage_started_at = {}
                st.session_state.coding_room_hidden_tests = {}
                st.session_state.coding_room_stage_approaches = {}
                save_analysis_history(int(user.get("id") or 0), result)
                st.session_state.bot_open = True
                st.session_state.dashboard_view = "home"
                st.rerun()
            except Exception as ex:
                st.error(f"Analysis failed: {ex}")
                return

    if st.session_state.analysis_result:
        st.markdown("### Analysis Result")
        render_analysis_card(st.session_state.analysis_result)
        st.markdown(
            """
            <style>
            .st-key-home_resume_add_points_btn button,
            .st-key-home_launch_coding_room_btn button {
                border-radius: 999px !important;
                border: 1px solid #0f766e !important;
                background: linear-gradient(120deg, #14b8a6 0%, #0ea5e9 100%) !important;
                color: #ffffff !important;
                font-weight: 700 !important;
                box-shadow: 0 10px 22px rgba(20, 184, 166, 0.24) !important;
                padding: 0.35rem 1rem !important;
            }
            .st-key-home_resume_add_points_btn button:hover,
            .st-key-home_launch_coding_room_btn button:hover {
                border-color: #0f766e !important;
                filter: brightness(1.04) !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        action_cols = st.columns(2, gap="small")
        with action_cols[0]:
            panel_open = bool(st.session_state.get("resume_export_panel_open"))
            toggle_label = "Resume Add Points" if not panel_open else "Hide Resume Add Points"
            with st.container(key="home_resume_add_points_btn"):
                if st.button(toggle_label, key="home_resume_add_points_toggle_btn", use_container_width=False):
                    st.session_state.resume_export_panel_open = not panel_open
        with action_cols[1]:
            with st.container(key="home_launch_coding_room_btn"):
                if st.button("Start 3-Stage AI Coding Room", key="home_open_coding_room_btn", use_container_width=False):
                    st.session_state.dashboard_view = "coding_room"
                    st.session_state.bot_open = False
                    st.rerun()
        render_resume_export_assistant(show_toggle_button=False)
        st.caption("ZoSwi is available in the round memoji button at the bottom-right.")


def render_recent_scores_view(user: dict[str, Any]) -> None:
    user_id = int(user.get("id") or 0)
    recent_scores = get_recent_analysis_history(user_id, limit=50)
    st.markdown(
        """
        <div class="ai-hero">
            <div class="ai-chip">Recent Match Scores</div>
            <h1>Score History</h1>
            <p>Review your latest resume and JD analysis outcomes.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if not recent_scores:
        st.info("No recent score history yet.")
        return

    rows: list[dict[str, str]] = []
    for item in recent_scores:
        rows.append(
            {
                "Date": format_history_time(str(item.get("created_at", ""))),
                "Score": f"{int(item.get('score', 0))}%",
                "Category": str(item.get("category", "")),
                "Summary": str(item.get("summary", "")).strip()[:140],
            }
        )
    with st.container(key="full_scores_table"):
        st.dataframe(rows, use_container_width=True, hide_index=True)


def render_recent_chats_view(user: dict[str, Any]) -> None:
    user_id = int(user.get("id") or 0)
    full_name = str(user.get("full_name", "")).strip()
    first_name = full_name.split()[0] if full_name else "Candidate"
    user_name_label = first_name if first_name else "You"
    active_chat_id = int(st.session_state.get("active_chat_id") or 0)
    recent_sessions = get_recent_chat_sessions(user_id, limit=40)

    if active_chat_id <= 0 and recent_sessions:
        initial_session_id = int(recent_sessions[0]["id"])
        load_chat_session_into_state(user_id, initial_session_id, full_name)
        active_chat_id = initial_session_id
    if not st.session_state.get("bot_messages"):
        st.session_state.bot_messages = default_bot_messages(full_name)
    if st.session_state.get("clear_full_chat_input"):
        st.session_state.full_chat_input = ""
        st.session_state.clear_full_chat_input = False

    st.markdown(
        f"""
        <div class="ai-hero">
            <div class="ai-chip">Recent Chats</div>
            <h1>ZoSwi Chat Workspace</h1>
            <p>{html.escape(first_name)}'s conversations in a full-screen chat view.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.container(key="full_chat_shell"):
        left_col, right_col = st.columns([1.05, 2.35], gap="small")
        with left_col:
            if st.button("+ New Chat", key="full_chat_new", use_container_width=True):
                new_session_id = create_chat_session(user_id, "New Chat")
                st.session_state.active_chat_id = new_session_id if new_session_id > 0 else None
                st.session_state.bot_messages = default_bot_messages(full_name)
                st.session_state.bot_pending_prompt = None
                st.session_state.clear_full_chat_input = True
                st.rerun()

            with st.container(key="full_recent_chats"):
                st.markdown("##### Recent Chats")
                if recent_sessions:
                    for session in recent_sessions:
                        session_id = int(session["id"])
                        title = str(session.get("title", "")).strip() or "Untitled Chat"
                        display_title = title[:24] + "..." if len(title) > 27 else title
                        date_label = format_history_date_short(str(session.get("updated_at", "")))
                        active_prefix = "\u2192 " if session_id == active_chat_id else ""
                        label = f"{active_prefix}{date_label} {display_title}"
                        if st.button(
                            label,
                            key=f"full_recent_chat_{session_id}",
                            use_container_width=True,
                        ):
                            load_chat_session_into_state(user_id, session_id, full_name)
                            st.rerun()
                else:
                    st.caption("No recent chats yet.")

        with right_col:
            with st.container(key="full_chat_panel"):
                st.markdown("#### ZoSwi Live Chat")
                st.caption(f"{time_based_greeting()}, {first_name}")

                with st.container(height=560):
                    chat_history_container = st.container()
                    live_reply_container = st.container()
                    with chat_history_container:
                        for msg in st.session_state.bot_messages:
                            st.markdown(
                                format_zoswi_message_html(
                                    msg.get("role", "assistant"),
                                    msg.get("content", ""),
                                    user_name_label,
                                ),
                                unsafe_allow_html=True,
                            )
                    st.markdown('<div id="zoswi-scroll-anchor"></div>', unsafe_allow_html=True)
                    render_zoswi_autoscroll()

                pending_prompt = st.session_state.get("bot_pending_prompt")
                is_waiting_for_reply = bool(pending_prompt)
                with st.container(key="full_chat_input_wrap"):
                    input_cols = st.columns([9, 1])
                    with input_cols[0]:
                        message = st.text_input(
                            "Message ZoSwi",
                            key="full_chat_input",
                            on_change=request_full_chat_submit,
                            label_visibility="collapsed",
                            placeholder="Message ZoSwi",
                            disabled=is_waiting_for_reply,
                        )
                    with input_cols[1]:
                        send = st.button(
                            "\u2191",
                            key="full_chat_send",
                            help="Send",
                            use_container_width=True,
                            disabled=is_waiting_for_reply,
                        )

                submit_requested = send or bool(st.session_state.get("full_chat_submit"))
                if submit_requested:
                    st.session_state.full_chat_submit = False

                if submit_requested and not is_waiting_for_reply and message.strip():
                    clean_message = message.strip()
                    if user_id > 0 and active_chat_id <= 0:
                        active_chat_id = create_chat_session(user_id, "New Chat")
                        st.session_state.active_chat_id = active_chat_id
                    st.session_state.bot_messages.append({"role": "user", "content": clean_message})
                    save_chat_history(user_id, active_chat_id, "user", clean_message)
                    update_chat_session_title_if_default(active_chat_id, clean_message)
                    st.session_state.bot_pending_prompt = clean_message
                    st.session_state.clear_full_chat_input = True
                    st.rerun()

                if pending_prompt:
                    with live_reply_container:
                        response_placeholder = st.empty()
                        response_placeholder.markdown(
                            format_zoswi_message_html("assistant", "...", user_name_label),
                            unsafe_allow_html=True,
                        )
                        response_text = ""
                        for chunk in ask_assistant_bot_stream(str(pending_prompt)):
                            response_text += chunk
                            response_placeholder.markdown(
                                format_zoswi_message_html(
                                    "assistant",
                                    response_text + " \u258c",
                                    user_name_label,
                                ),
                                unsafe_allow_html=True,
                            )
                        if not response_text.strip():
                            response_text = "I hit a temporary issue generating a response. Please try again."
                        response_placeholder.markdown(
                            format_zoswi_message_html("assistant", response_text, user_name_label),
                            unsafe_allow_html=True,
                        )
                    st.session_state.bot_messages.append({"role": "assistant", "content": response_text})
                    save_chat_history(user_id, active_chat_id, "assistant", response_text)
                    st.session_state.bot_pending_prompt = None
                    st.rerun()


def render_coding_room_view(user: dict[str, Any]) -> None:
    full_name = str(user.get("full_name", "")).strip()
    first_name = full_name.split()[0] if full_name else "Candidate"
    analysis = st.session_state.get("analysis_result") or {}
    resume_text = str(st.session_state.get("latest_resume_text", "")).strip()
    job_description = str(st.session_state.get("latest_job_description", "")).strip()
    logo_data_uri = get_logo_data_uri()
    if st.session_state.get("coding_room_clear_input"):
        st.session_state.coding_room_user_input = ""
        st.session_state.coding_room_clear_input = False

    st.markdown(
        """
        <style>
        .coding-room-shell {
            border: 1px solid #dbeafe;
            border-radius: 18px;
            padding: 1rem 1rem 0.8rem 1rem;
            background:
                radial-gradient(800px 280px at -8% -14%, rgba(14, 165, 233, 0.16) 0%, transparent 56%),
                radial-gradient(600px 240px at 100% 0%, rgba(20, 184, 166, 0.15) 0%, transparent 60%),
                #ffffff;
            box-shadow: 0 18px 36px rgba(15, 23, 42, 0.08);
        }
        .coding-room-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.8rem;
            margin-bottom: 0.75rem;
        }
        .coding-room-title h2 {
            margin: 0;
            color: #0f172a;
            font-size: 1.48rem;
            line-height: 1.15;
        }
        .coding-room-title p {
            margin: 0.22rem 0 0 0;
            color: #475569;
            font-size: 0.9rem;
        }
        .coding-live-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            border: 1px solid #99f6e4;
            background: #f0fdfa;
            color: #0f766e;
            border-radius: 999px;
            padding: 0.28rem 0.62rem;
            font-size: 0.76rem;
            font-weight: 700;
            white-space: nowrap;
        }
        .coding-live-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #14b8a6;
            box-shadow: 0 0 0 0 rgba(20, 184, 166, 0.55);
            animation: codingLivePulse 1.5s infinite;
        }
        @keyframes codingLivePulse {
            0% { box-shadow: 0 0 0 0 rgba(20, 184, 166, 0.52); }
            70% { box-shadow: 0 0 0 8px rgba(20, 184, 166, 0.0); }
            100% { box-shadow: 0 0 0 0 rgba(20, 184, 166, 0.0); }
        }
        .coding-video-shell {
            border: 1px solid #dbeafe;
            border-radius: 15px;
            overflow: hidden;
            background: linear-gradient(180deg, #f8fbff 0%, #eef7ff 100%);
            min-height: 468px;
        }
        .coding-video-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.65rem;
            padding: 0.58rem 0.72rem;
            border-bottom: 1px solid #e2e8f0;
            background: rgba(255, 255, 255, 0.86);
        }
        .coding-memoji {
            width: 34px;
            height: 34px;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(135deg, #34d399 0%, #22d3ee 100%);
            color: #ffffff;
            font-size: 1.05rem;
            box-shadow: 0 8px 18px rgba(45, 212, 191, 0.33);
        }
        .coding-video-name {
            margin: 0;
            color: #0f172a;
            font-size: 0.9rem;
            font-weight: 700;
            line-height: 1.1;
        }
        .coding-video-sub {
            margin: 0.12rem 0 0 0;
            color: #475569;
            font-size: 0.77rem;
            line-height: 1.1;
        }
        .coding-video-body {
            padding: 0.78rem 0.82rem 0.84rem 0.82rem;
        }
        .coding-question-stage {
            margin: 0;
            color: #0369a1;
            font-size: 0.73rem;
            font-weight: 800;
            letter-spacing: 0.02em;
            text-transform: uppercase;
        }
        .coding-question-title {
            margin: 0.24rem 0 0 0;
            color: #0f172a;
            font-size: 1rem;
            font-weight: 700;
            line-height: 1.3;
        }
        .coding-question-meta {
            margin: 0.26rem 0 0 0;
            color: #334155;
            font-size: 0.8rem;
            line-height: 1.32;
        }
        .coding-question-text {
            margin: 0.36rem 0 0 0;
            color: #1e293b;
            font-size: 0.81rem;
            line-height: 1.38;
        }
        .coding-question-subhead {
            margin: 0.5rem 0 0.2rem 0;
            color: #0f172a;
            font-size: 0.8rem;
            font-weight: 700;
            line-height: 1.2;
        }
        .coding-question-list {
            margin: 0;
            padding-left: 1.03rem;
            color: #334155;
            font-size: 0.79rem;
            line-height: 1.34;
        }
        .coding-question-list li {
            margin-bottom: 0.12rem;
        }
        .coding-stage-card {
            border: 1px solid #dbeafe;
            border-radius: 15px;
            background: linear-gradient(140deg, #ffffff 0%, #f3f8ff 100%);
            padding: 0.92rem;
            box-shadow: 0 12px 24px rgba(14, 116, 144, 0.08);
        }
        .coding-stage-title {
            margin: 0;
            color: #0f172a;
            font-size: 1.06rem;
            font-weight: 700;
            line-height: 1.25;
        }
        .coding-stage-meta {
            margin: 0.38rem 0 0.5rem 0;
            color: #334155;
            font-size: 0.82rem;
            line-height: 1.35;
        }
        .coding-room-shell ul {
            margin-top: 0.2rem;
        }
        .st-key-coding_action_ready button,
        .st-key-coding_action_hint button,
        .st-key-coding_action_nudge button {
            border-radius: 999px !important;
            border: 1px solid #bae6fd !important;
            background: #f0f9ff !important;
            color: #0c4a6e !important;
            font-weight: 700 !important;
            font-size: 0.77rem !important;
            min-height: 2rem !important;
            box-shadow: none !important;
        }
        .st-key-coding_action_ready button:hover,
        .st-key-coding_action_hint button:hover,
        .st-key-coding_action_nudge button:hover {
            border-color: #38bdf8 !important;
            background: #e0f2fe !important;
        }
        .st-key-coding_eval_btn button,
        .st-key-coding_next_stage_btn button,
        .st-key-coding_load_template_btn button,
        .st-key-coding_reset_session_btn button,
        .st-key-coding_back_home_btn button {
            border-radius: 12px !important;
            font-weight: 700 !important;
            min-height: 2.05rem !important;
        }
        .st-key-coding_eval_btn button {
            border: 1px solid #0f766e !important;
            background: linear-gradient(130deg, #14b8a6 0%, #0ea5e9 100%) !important;
            color: #ffffff !important;
            box-shadow: 0 10px 18px rgba(20, 184, 166, 0.26) !important;
        }
        .st-key-coding_next_stage_btn button {
            border: 1px solid #1d4ed8 !important;
            background: #dbeafe !important;
            color: #1e3a8a !important;
        }
        .st-key-coding_reset_session_btn button {
            border: 1px solid #fca5a5 !important;
            background: #fef2f2 !important;
            color: #b91c1c !important;
        }
        .st-key-coding_reset_session_btn button:hover {
            border-color: #ef4444 !important;
            background: #fee2e2 !important;
            color: #991b1b !important;
        }
        .st-key-coding_load_template_btn button {
            border: 1px solid #cbd5e1 !important;
            background: #ffffff !important;
            color: #334155 !important;
            min-height: 1.85rem !important;
            font-size: 0.74rem !important;
            margin: 0.35rem 0 0.42rem 0 !important;
        }
        .st-key-coding_stage_approach_wrap [data-testid="stTextArea"] > label {
            color: #334155 !important;
            font-size: 0.76rem !important;
            font-weight: 700 !important;
        }
        .st-key-coding_stage_approach_wrap textarea {
            min-height: 112px !important;
            border-radius: 10px !important;
            border: 1px solid #cbd5e1 !important;
            background: #ffffff !important;
            color: #0f172a !important;
            line-height: 1.4 !important;
            font-size: 0.82rem !important;
        }
        .coding-score-card {
            border: 1px solid #bfdbfe;
            border-radius: 12px;
            background: #f8fbff;
            padding: 0.7rem 0.78rem;
            margin-top: 0.45rem;
        }
        .coding-score-card h4 {
            margin: 0;
            color: #0f172a;
            font-size: 0.91rem;
            line-height: 1.25;
        }
        .coding-score-card p {
            margin: 0.24rem 0 0 0;
            color: #334155;
            font-size: 0.79rem;
            line-height: 1.34;
        }
        .coding-workspace-wrap {
            border: 1px solid #cbd5e1;
            border-radius: 13px;
            background:
                radial-gradient(900px 300px at -12% -30%, rgba(14, 165, 233, 0.12) 0%, transparent 56%),
                radial-gradient(700px 260px at 110% -28%, rgba(16, 185, 129, 0.1) 0%, transparent 58%),
                #f8fbff;
            padding: 0.75rem 0.8rem;
            box-shadow: 0 12px 24px rgba(15, 23, 42, 0.12);
            margin-bottom: 0.58rem;
        }
        .coding-workspace-top {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.5rem;
            margin-bottom: 0.56rem;
        }
        .coding-workspace-title {
            margin: 0;
            color: #0f172a;
            font-size: 0.94rem;
            font-weight: 700;
            line-height: 1.2;
        }
        .coding-workspace-sub {
            margin: 0.1rem 0 0 0;
            color: #475569;
            font-size: 0.74rem;
            line-height: 1.2;
        }
        .coding-workspace-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.28rem;
            border: 1px solid #7dd3fc;
            background: #e0f2fe;
            color: #0c4a6e;
            border-radius: 999px;
            padding: 0.18rem 0.54rem;
            font-size: 0.68rem;
            font-weight: 700;
            white-space: nowrap;
        }
        .coding-workspace-chips {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.43rem;
        }
        .coding-tech-chip {
            border: 1px solid #dbeafe;
            border-radius: 10px;
            background: #ffffff;
            padding: 0.34rem 0.42rem;
        }
        .coding-tech-key {
            margin: 0;
            color: #64748b;
            font-size: 0.62rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            line-height: 1.1;
        }
        .coding-tech-value {
            margin: 0.17rem 0 0 0;
            color: #0f172a;
            font-size: 0.76rem;
            font-weight: 700;
            line-height: 1.2;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .coding-tech-value.timer-live-display {
            font-family: "JetBrains Mono", "Consolas", "Courier New", monospace;
            font-size: 0.98rem;
            letter-spacing: 0.03em;
        }
        .coding-tech-value.timer-safe {
            color: #047857;
        }
        .coding-tech-value.timer-alert {
            color: #b91c1c;
        }
        .st-key-coding_language_wrap [data-baseweb="select"] > div {
            background: #ffffff !important;
            border: 1px solid #cbd5e1 !important;
            border-radius: 10px !important;
            color: #0f172a !important;
            box-shadow: none !important;
        }
        .st-key-coding_language_wrap [data-baseweb="select"] span,
        .st-key-coding_language_wrap [data-baseweb="select"] div {
            color: #0f172a !important;
        }
        .st-key-coding_language_wrap label {
            color: #475569 !important;
            font-size: 0.74rem !important;
            font-weight: 700 !important;
        }
        .coding-editor-shell {
            border: 1px solid #cbd5e1;
            border-radius: 12px;
            overflow: hidden;
            background: #f8fafc;
            box-shadow: 0 10px 20px rgba(15, 23, 42, 0.11);
        }
        .coding-editor-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.5rem;
            padding: 0.48rem 0.62rem;
            border-bottom: 1px solid #d1d5db;
            background: linear-gradient(180deg, #f1f5f9 0%, #e2e8f0 100%);
        }
        .coding-editor-tabs {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
        }
        .coding-editor-tab {
            border: 1px solid #334155;
            background: #0b1220;
            color: #cbd5e1;
            border-radius: 999px;
            padding: 0.16rem 0.54rem;
            font-size: 0.7rem;
            font-weight: 700;
            line-height: 1;
        }
        .coding-editor-tab.active {
            border-color: #0ea5e9;
            color: #e0f2fe;
            background: rgba(14, 165, 233, 0.2);
        }
        .coding-editor-status {
            color: #334155;
            font-size: 0.72rem;
            font-weight: 600;
            line-height: 1;
        }
        .coding-editor-head-left {
            display: inline-flex;
            align-items: center;
            gap: 0.34rem;
        }
        .coding-editor-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            display: inline-block;
        }
        .coding-editor-dot.red { background: #ef4444; }
        .coding-editor-dot.yellow { background: #eab308; }
        .coding-editor-dot.green { background: #22c55e; }
        .coding-editor-file {
            color: #0f172a;
            font-size: 0.71rem;
            font-weight: 700;
            margin-left: 0.32rem;
            letter-spacing: 0.01em;
        }
        .st-key-coding_editor_shell [data-testid="stTextArea"] > label {
            color: #334155 !important;
            font-weight: 600 !important;
            font-size: 0.77rem !important;
        }
        .st-key-coding_editor_shell .zoswi-code-line-gutter {
            display: none !important;
            visibility: hidden !important;
            width: 0 !important;
            height: 0 !important;
            overflow: hidden !important;
        }
        .st-key-coding_editor_shell [data-testid="stTextArea"].zoswi-code-editor-root {
            position: static !important;
        }
        .st-key-coding_editor_shell {
            border: 1px solid #bfdbfe;
            border-top: 0;
            border-radius: 0 0 12px 12px;
            background: linear-gradient(135deg, #ffffff 0%, #eff6ff 45%, #ecfeff 100%);
            box-shadow: 0 12px 24px rgba(30, 64, 175, 0.1);
            padding: 0.32rem 0.36rem 0.36rem 0.36rem;
            margin-top: -1px;
        }
        .st-key-coding_editor_shell [data-testid="stTextArea"] {
            border: 1px solid #dbeafe;
            border-radius: 10px;
            background: rgba(255, 255, 255, 0.96);
            padding: 0.12rem;
        }
        .st-key-coding_editor_shell [data-testid="stTextArea"] textarea {
            background: #ffffff !important;
            color: #0f172a !important;
            border: 1px solid #cbd5e1 !important;
            border-radius: 0 0 10px 10px !important;
            font-family: "JetBrains Mono", "Consolas", "Courier New", monospace !important;
            font-size: 0.86rem !important;
            line-height: 1.45 !important;
            caret-color: #0369a1 !important;
            min-height: 250px !important;
            background-image:
                url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='340' height='140' viewBox='0 0 340 140'%3E%3Ctext x='50%25' y='54%25' dominant-baseline='middle' text-anchor='middle' font-family='Segoe UI,Arial,sans-serif' font-size='52' font-weight='700' fill='%230284c7' fill-opacity='0.11'%3EZoSwi%3C/text%3E%3C/svg%3E"),
                linear-gradient(transparent 96%, rgba(148, 163, 184, 0.06) 96%),
                linear-gradient(90deg, rgba(148, 163, 184, 0.04) 1px, transparent 1px) !important;
            background-repeat: no-repeat, repeat, repeat !important;
            background-position: center center, 0 0, 0 0 !important;
            background-size: 220px auto, 100% 1.5rem, 1.5rem 100% !important;
        }
        .st-key-coding_editor_shell [data-testid="stTextArea"] textarea:focus {
            border-color: #0284c7 !important;
            box-shadow: 0 0 0 1px rgba(2, 132, 199, 0.32) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    if logo_data_uri:
        st.markdown(
            f"""
            <style>
            .st-key-coding_editor_shell [data-testid="stTextArea"] textarea {{
                background-image:
                    linear-gradient(rgba(255, 255, 255, 0.92), rgba(255, 255, 255, 0.92)),
                    url("{logo_data_uri}"),
                    linear-gradient(transparent 96%, rgba(148, 163, 184, 0.06) 96%),
                    linear-gradient(90deg, rgba(148, 163, 184, 0.04) 1px, transparent 1px) !important;
                background-repeat: no-repeat, no-repeat, repeat, repeat !important;
                background-position: center center, center center, 0 0, 0 0 !important;
                background-size: 100% 100%, 520px auto, 100% 1.5rem, 1.5rem 100% !important;
            }}
            </style>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        f"""
        <div class="coding-room-shell">
            <div class="coding-room-header">
                <div class="coding-room-title">
                    <h2>ZoSwi Live Coding Room</h2>
                    <p>One-on-one coding interview simulation for {html.escape(first_name)} using your latest resume and JD analysis.</p>
                </div>
                <div class="coding-live-pill"><span class="coding-live-dot"></span>LIVE INTERVIEW FLOW</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not resume_text or not job_description or not isinstance(analysis, dict):
        st.warning("Run Resume-JD Analysis first, then launch the coding room.")
        with st.container(key="coding_back_home_btn"):
            if st.button("Go To Home", key="coding_go_home_from_empty", use_container_width=False):
                st.session_state.dashboard_view = "home"
                st.rerun()
        return

    source_payload = json.dumps(analysis, sort_keys=True, ensure_ascii=True)
    source_sig = hashlib.sha256(f"{resume_text}\n##\n{job_description}\n##\n{source_payload}".encode("utf-8")).hexdigest()
    if st.session_state.get("coding_room_source_sig") != source_sig:
        with st.spinner("Preparing your 3-stage coding simulation..."):
            payload = build_coding_stage_payload(resume_text, job_description, analysis)
        st.session_state.coding_room_payload = payload
        st.session_state.coding_room_source_sig = source_sig
        st.session_state.coding_room_stage_index = 0
        st.session_state.coding_room_stage_scores = {}
        st.session_state.coding_room_messages = []
        st.session_state.coding_room_session_started = False
        st.session_state.coding_room_clear_input = True
        st.session_state.coding_room_scroll_pending = False
        st.session_state.coding_room_stage_started_at = {}
        st.session_state.coding_room_hidden_tests = {}
        st.session_state.coding_room_stage_approaches = {}

    payload = st.session_state.get("coding_room_payload")
    if not isinstance(payload, dict) or not isinstance(payload.get("stages"), list) or not payload.get("stages"):
        st.error("Coding room setup failed. Please click back and run analysis again.")
        return

    stages = payload["stages"]
    total_stages = min(CODING_STAGE_COUNT, len(stages))
    stage_index = int(st.session_state.get("coding_room_stage_index") or 0)
    stage_index = max(0, min(total_stages - 1, stage_index))
    st.session_state.coding_room_stage_index = stage_index
    stage = stages[stage_index]
    stage_scores = st.session_state.get("coding_room_stage_scores", {})
    if not isinstance(stage_scores, dict):
        stage_scores = {}
    stage_key = str(stage_index)
    stage_started_at = st.session_state.get("coding_room_stage_started_at", {})
    if not isinstance(stage_started_at, dict):
        stage_started_at = {}
    if stage_key not in stage_started_at:
        stage_started_at[stage_key] = float(time.time())
        st.session_state.coding_room_stage_started_at = stage_started_at
    elapsed_seconds = max(0, int(time.time() - float(stage_started_at.get(stage_key, time.time()))))
    stage_limit_seconds = max(60, int(stage.get("time_limit_min", 20)) * 60)
    remaining_seconds = max(0, stage_limit_seconds - elapsed_seconds)
    timer_expired = remaining_seconds <= 0
    timer_instance_token = f"{stage_key}_{int(float(stage_started_at.get(stage_key, time.time())))}"
    timer_dom_id = f"coding_chip_timer_{re.sub(r'[^a-zA-Z0-9_-]', '_', timer_instance_token)}"

    hidden_tests_map = st.session_state.get("coding_room_hidden_tests", {})
    if not isinstance(hidden_tests_map, dict):
        hidden_tests_map = {}
    approaches_map = st.session_state.get("coding_room_stage_approaches", {})
    if not isinstance(approaches_map, dict):
        approaches_map = {}

    completed_stages = len([key for key in stage_scores if str(key).isdigit()])
    progress_value = min(1.0, float(completed_stages) / float(max(1, total_stages)))

    if not st.session_state.get("coding_room_session_started"):
        intro = str(payload.get("interviewer_intro", "")).strip()
        if intro:
            append_coding_room_message("assistant", intro)
        stage_opening = (
            f"Stage {stage_index + 1}/{total_stages}: {stage.get('title', '')}. "
            "When ready, summarize your approach, then complete the TODO blocks in starter code."
        )
        append_coding_room_message("assistant", stage_opening)
        st.session_state.coding_room_session_started = True

    skills = payload.get("detected_skills", [])
    if isinstance(skills, list) and skills:
        st.caption(f"Skill alignment: {', '.join(str(skill) for skill in skills[:6])}")
    st.progress(progress_value, text=f"Stage progress: {completed_stages}/{total_stages} completed")

    stage_question_text = str(stage.get("question", "") or stage.get("challenge", "")).strip()
    stage_completion_steps = stage.get("completion_steps", [])
    if not isinstance(stage_completion_steps, list) or not stage_completion_steps:
        stage_completion_steps = stage.get("requirements", [])
    question_requirements_html = "".join(
        f"<li>{html.escape(str(req))}</li>" for req in stage_completion_steps[:4]
    )
    question_hints_html = "".join(
        f"<li>{html.escape(str(hint))}</li>" for hint in stage.get("hint_starters", [])[:3]
    )
    question_sample_case = str(stage.get("sample_case", "")).strip()

    left_col, right_col = st.columns([0.96, 1.34], gap="medium")
    with left_col:
        st.markdown(
            f"""
            <div class="coding-video-shell">
                <div class="coding-video-head">
                    <div style="display:flex;align-items:center;gap:0.52rem;">
                        <span class="coding-memoji">\U0001F916</span>
                        <div>
                            <p class="coding-video-name">ZoSwi Interview Bot</p>
                            <p class="coding-video-sub">Live stage {stage_index + 1} interviewer</p>
                        </div>
                    </div>
                    <div class="coding-live-pill"><span class="coding-live-dot"></span>ACTIVE</div>
                </div>
                <div class="coding-video-body">
                    <p class="coding-question-stage">Stage {stage_index + 1} Question</p>
                    <p class="coding-question-title">{html.escape(str(stage.get("title", "")))}</p>
                    <p class="coding-question-meta"><strong>Focus:</strong> {html.escape(str(stage.get("skill_focus", "")))} | <strong>Time:</strong> {int(stage.get("time_limit_min", 20))} min</p>
                    <p class="coding-question-text"><strong>Scenario:</strong> {html.escape(str(stage.get("scenario", "")))}</p>
                    <p class="coding-question-text"><strong>Question:</strong> {html.escape(stage_question_text)}</p>
                    {f'<p class="coding-question-text"><strong>Sample:</strong> {html.escape(question_sample_case)}</p>' if question_sample_case else ''}
                    <p class="coding-question-subhead">Complete These TODOs</p>
                    <ul class="coding-question-list">{question_requirements_html}</ul>
                    <p class="coding-question-subhead">Hint Starters</p>
                    <ul class="coding-question-list">{question_hints_html}</ul>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.container(height=320):
            chat_history_container = st.container()
            live_reply_container = st.container()
            with chat_history_container:
                for msg in st.session_state.get("coding_room_messages", []):
                    st.markdown(
                        format_zoswi_message_html(
                            msg.get("role", "assistant"),
                            msg.get("content", ""),
                            first_name,
                        ),
                        unsafe_allow_html=True,
                    )
            if bool(st.session_state.get("coding_room_scroll_pending", False)):
                st.markdown('<div id="zoswi-scroll-anchor"></div>', unsafe_allow_html=True)
                render_zoswi_autoscroll()
                st.session_state.coding_room_scroll_pending = False

        action_cols = st.columns(3, gap="small")
        with action_cols[0]:
            with st.container(key="coding_action_ready"):
                ready_clicked = st.button("\U0001F60A I am ready", key="coding_action_ready_btn", use_container_width=True)
        with action_cols[1]:
            with st.container(key="coding_action_hint"):
                hint_clicked = st.button("\U0001F914 Give hint", key="coding_action_hint_btn", use_container_width=True)
        with action_cols[2]:
            with st.container(key="coding_action_nudge"):
                nudge_clicked = st.button("\u23ED Move forward", key="coding_action_nudge_btn", use_container_width=True)

        pending_action = ""
        pending_user_message = ""
        if ready_clicked:
            pending_action = "ready"
            pending_user_message = "I am ready. Please continue."
        elif hint_clicked:
            pending_action = "hint"
            pending_user_message = "I need a hint for this stage."
        elif nudge_clicked:
            pending_action = "nudge"
            pending_user_message = "Move to the next interview follow-up question."
        if pending_action:
            append_coding_room_message("user", pending_user_message)

        with st.container(key="coding_room_input_wrap"):
            input_cols = st.columns([9, 1])
            with input_cols[0]:
                candidate_message = st.text_input(
                    "Message interviewer",
                    key="coding_room_user_input",
                    on_change=request_coding_room_submit,
                    label_visibility="collapsed",
                    placeholder="Tell your approach or ask clarifications...",
                )
            with input_cols[1]:
                send_message = st.button("\u2191", key="coding_room_send_btn", use_container_width=True, help="Send")

        submit_requested = bool(send_message) or bool(st.session_state.get("coding_room_submit"))
        if submit_requested:
            st.session_state.coding_room_submit = False
            clean_message = str(candidate_message or "").strip()
            if clean_message:
                pending_action = "message"
                pending_user_message = clean_message
                append_coding_room_message("user", clean_message)
                st.session_state.coding_room_clear_input = True

        if pending_action:
            with live_reply_container:
                response_placeholder = st.empty()
                response_placeholder.markdown(
                    format_zoswi_message_html("assistant", "...", first_name),
                    unsafe_allow_html=True,
                )
                response_text = ""
                for chunk in stream_coding_interviewer_reply(
                    pending_action,
                    pending_user_message,
                    stage,
                    stage_index,
                    first_name,
                ):
                    response_text += str(chunk)
                    response_placeholder.markdown(
                        format_zoswi_message_html("assistant", response_text + " \u258c", first_name),
                        unsafe_allow_html=True,
                    )
                if not response_text.strip():
                    response_text = "I did not get that fully. Share your approach in 2-3 steps and proceed with code."
                response_placeholder.markdown(
                    format_zoswi_message_html("assistant", response_text, first_name),
                    unsafe_allow_html=True,
                )
            append_coding_room_message("assistant", response_text)
            st.rerun()

    with right_col:
        difficulty_label = "Medium" if stage_index == 0 else ("Hard" if stage_index == 1 else "Expert")
        timer_value_label = "Expired" if timer_expired else format_timer_label(remaining_seconds)
        timer_value_class = "timer-alert" if timer_expired else "timer-safe"
        st.markdown(
            f"""
            <div class="coding-workspace-wrap">
                <div class="coding-workspace-top">
                    <div>
                        <p class="coding-workspace-title">Coding Workspace</p>
                        <p class="coding-workspace-sub">Focused implementation zone with stage-linked evaluation.</p>
                    </div>
                    <span class="coding-workspace-pill">\u2699 RUN PHASE</span>
                </div>
                <div class="coding-workspace-chips">
                    <div class="coding-tech-chip">
                        <p class="coding-tech-key">Stage</p>
                        <p class="coding-tech-value">{stage_index + 1}/{total_stages}</p>
                    </div>
                    <div class="coding-tech-chip">
                        <p class="coding-tech-key">Difficulty</p>
                        <p class="coding-tech-value">{difficulty_label}</p>
                    </div>
                    <div class="coding-tech-chip">
                        <p class="coding-tech-key">Focus</p>
                        <p class="coding-tech-value">{html.escape(str(stage.get("skill_focus", "")))}</p>
                    </div>
                    <div class="coding-tech-chip">
                        <p class="coding-tech-key">Timer</p>
                        <p id="{timer_dom_id}" class="coding-tech-value timer-live-display {timer_value_class}">{timer_value_label}</p>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if timer_expired:
            st.warning("Stage timer expired. Click Next Stage to auto-evaluate your current submission and continue.")
        render_live_stage_timer_widget(remaining_seconds, timer_dom_id, timer_instance_token)

        language_widget_key = f"coding_room_language_stage_{stage_index}"
        if language_widget_key not in st.session_state:
            st.session_state[language_widget_key] = st.session_state.get("coding_room_language", CODING_LANGUAGES[0])
        with st.container(key="coding_language_wrap"):
            selected_language = st.selectbox(
                "Runtime / Language",
                options=CODING_LANGUAGES,
                key=language_widget_key,
            )
        st.session_state.coding_room_language = selected_language
        language_token = _normalize_language_token(selected_language)
        language_ext_map = {
            "python": "py",
            "java": "java",
            "javascript": "js",
            "typescript": "ts",
            "go": "go",
            "c": "cpp",
            "c++": "cpp",
        }
        file_ext = language_ext_map.get(language_token, "txt")
        code_key = f"coding_room_code_stage_{stage_index}_{language_token}"
        if code_key not in st.session_state:
            st.session_state[code_key] = build_stage_starter_code(stage, selected_language)
        st.markdown(
            f"""
            <div class="coding-editor-shell">
                <div class="coding-editor-head">
                    <div class="coding-editor-tabs">
                        <div class="coding-editor-head-left">
                            <span class="coding-editor-dot red"></span>
                            <span class="coding-editor-dot yellow"></span>
                            <span class="coding-editor-dot green"></span>
                            <span class="coding-editor-file">stage_{stage_index + 1}_solution.{file_ext}</span>
                        </div>
                    </div>
                    <span class="coding-editor-status">{html.escape(selected_language)} | {int(stage.get("time_limit_min", 20))}m slot</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.container(key="coding_load_template_btn"):
            load_template_clicked = st.button(
                "Reload Starter Code",
                key=f"coding_load_template_{stage_index}_{language_token}",
                use_container_width=False,
            )
        if load_template_clicked:
            st.session_state[code_key] = build_stage_starter_code(stage, selected_language)
            st.rerun()
        with st.container(key="coding_editor_shell"):
            st.text_area(
                f"Stage {stage_index + 1} Solution",
                key=code_key,
                height=520,
                placeholder=f"Write your {selected_language} solution here...",
            )
        render_solution_editor_security_guard()
        st.caption("Copy/paste is disabled in the solution editor for assessment integrity.")

        stage_code_current = str(st.session_state.get(code_key, "")).strip()
        stage_code_hash = hashlib.sha256(stage_code_current.encode("utf-8")).hexdigest()
        raw_hidden_result = hidden_tests_map.get(stage_key, {})
        if not isinstance(raw_hidden_result, dict):
            raw_hidden_result = {}
        hidden_result = (
            raw_hidden_result
            if str(raw_hidden_result.get("code_hash", "")) == stage_code_hash
            else {}
        )
        hidden_ran = bool(hidden_result.get("ran", False))
        hidden_ready_for_eval = bool(hidden_result.get("ready_for_evaluation", False))

        if raw_hidden_result and not hidden_result:
            st.caption("Code changed after the last backend check. Click Evaluate Stage to run hidden tests again.")
        if hidden_result:
            total_tests = int(hidden_result.get("total", 0) or 0)
            passed_tests = int(hidden_result.get("passed", 0) or 0)
            failed_cases = hidden_result.get("failed_cases", [])
            if not isinstance(failed_cases, list):
                failed_cases = []
            status_label = "Ready for Evaluate Stage" if hidden_ready_for_eval else "Fix hidden test failures first"
            status_color = "green" if hidden_ready_for_eval else "orange"
            st.markdown(
                f"Hidden tests: **{passed_tests}/{max(1, total_tests)} passed** | :{status_color}[{status_label}]"
            )
            summary_text = str(hidden_result.get("summary", "")).strip()
            if summary_text:
                st.caption(summary_text)
            if failed_cases:
                st.caption(f"Failed cases: {', '.join(str(item) for item in failed_cases[:5])}")

        approach_key = f"coding_stage_approach_{stage_index}"
        if approach_key not in st.session_state:
            st.session_state[approach_key] = str(approaches_map.get(stage_key, "")).strip()
        with st.container(key="coding_stage_approach_wrap"):
            st.text_area(
                "Your Approach (required before Next Stage unless timer expires)",
                key=approach_key,
                height=120,
                placeholder="Explain your approach, edge cases, and complexity considerations...",
            )
        stage_approach_text = str(st.session_state.get(approach_key, "")).strip()
        approach_ok, approach_error = validate_stage_approach_text(stage_approach_text)
        if stage_approach_text and not approach_ok:
            st.warning(approach_error)
        if approach_ok:
            st.caption("Approach validation: ready")

        has_stage_score = stage_key in stage_scores
        can_go_next = timer_expired or (approach_ok and has_stage_score)
        action_row = st.columns(3, gap="small")
        with action_row[0]:
            with st.container(key="coding_eval_btn"):
                evaluate_clicked = st.button(
                    "Evaluate Stage",
                    key=f"coding_eval_stage_btn_{stage_index}",
                    use_container_width=True,
                    disabled=timer_expired,
                )
        with action_row[1]:
            with st.container(key="coding_next_stage_btn"):
                next_label = "Next Stage" if stage_index < total_stages - 1 else "Finish Evaluation"
                next_clicked = st.button(
                    next_label,
                    key=f"coding_next_stage_btn_{stage_index}",
                    use_container_width=True,
                    disabled=not can_go_next,
                )
        with action_row[2]:
            with st.container(key="coding_reset_session_btn"):
                reset_clicked = st.button(
                    "Reset Session",
                    key=f"coding_reset_session_main_btn_{stage_index}",
                    use_container_width=True,
                )
        if not timer_expired:
            st.caption("Evaluate Stage runs hidden tests automatically in the backend.")
        else:
            st.caption("Timer expired: Next Stage will auto-evaluate your current code in the backend before moving on.")

        if evaluate_clicked:
            stage_code = stage_code_current
            hidden_result_payload = run_hidden_tests_for_submission(
                stage=stage,
                code=stage_code,
                language=selected_language,
                resume_text=resume_text,
                job_description=job_description,
            )
            updated_hidden = dict(hidden_tests_map)
            hidden_result_payload["code_hash"] = stage_code_hash
            updated_hidden[stage_key] = hidden_result_payload
            st.session_state.coding_room_hidden_tests = updated_hidden
            append_coding_room_message(
                "assistant",
                (
                    f"Hidden tests auto-run for Stage {stage_index + 1}: "
                    f"{int(hidden_result_payload.get('passed', 0))}/{int(hidden_result_payload.get('total', 0))} passed."
                ),
            )
            if not bool(hidden_result_payload.get("ready_for_evaluation", False)):
                append_coding_room_message(
                    "assistant",
                    "Evaluation blocked because hidden tests are not passing yet. Update code and evaluate again.",
                )
                st.rerun()
            result = evaluate_coding_submission(
                stage=stage,
                code=stage_code,
                language=selected_language,
                resume_text=resume_text,
                job_description=job_description,
            )
            updated_scores = dict(stage_scores)
            updated_scores[str(stage_index)] = result
            st.session_state.coding_room_stage_scores = updated_scores
            append_coding_room_message(
                "assistant",
                (
                    f"Stage {stage_index + 1} evaluation complete: {result.get('score', 0)}% ({result.get('verdict', '')}). "
                    f"Next step: {result.get('next_step', '')}"
                ),
            )
            st.rerun()

        current_stage_result = stage_scores.get(str(stage_index), {})
        if isinstance(current_stage_result, dict) and current_stage_result:
            score = int(current_stage_result.get("score", 0))
            st.markdown(
                f"""
                <div class="coding-score-card">
                    <h4>Stage {stage_index + 1} Score: {score}% ({html.escape(str(current_stage_result.get("verdict", "")))})</h4>
                    <p><strong>Strengths:</strong> {html.escape('; '.join(current_stage_result.get("strengths", [])))}</p>
                    <p><strong>Improvements:</strong> {html.escape('; '.join(current_stage_result.get("improvements", [])))}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

        if next_clicked:
            if not timer_expired and not approach_ok:
                st.error(approach_error)
            else:
                updated_approaches = dict(approaches_map)
                if stage_approach_text:
                    updated_approaches[stage_key] = stage_approach_text
                st.session_state.coding_room_stage_approaches = updated_approaches

                updated_scores = dict(stage_scores)
                if stage_key not in updated_scores:
                    if timer_expired:
                        stage_code = stage_code_current
                        hidden_result_payload = run_hidden_tests_for_submission(
                            stage=stage,
                            code=stage_code,
                            language=selected_language,
                            resume_text=resume_text,
                            job_description=job_description,
                        )
                        latest_hidden_tests = st.session_state.get("coding_room_hidden_tests", {})
                        if not isinstance(latest_hidden_tests, dict):
                            latest_hidden_tests = {}
                        updated_hidden = dict(latest_hidden_tests)
                        hidden_result_payload["code_hash"] = stage_code_hash
                        updated_hidden[stage_key] = hidden_result_payload
                        st.session_state.coding_room_hidden_tests = updated_hidden
                        append_coding_room_message(
                            "assistant",
                            (
                                f"Timer expiry auto-check for Stage {stage_index + 1}: "
                                f"{int(hidden_result_payload.get('passed', 0))}/{int(hidden_result_payload.get('total', 0))} hidden tests passed."
                            ),
                        )

                        result = evaluate_coding_submission(
                            stage=stage,
                            code=stage_code,
                            language=selected_language,
                            resume_text=resume_text,
                            job_description=job_description,
                        )
                        if not bool(hidden_result_payload.get("ready_for_evaluation", False)):
                            existing_improvements = result.get("improvements", [])
                            if not isinstance(existing_improvements, list):
                                existing_improvements = [str(existing_improvements)]
                            result["improvements"] = [
                                "Timer-expiry auto-evaluation used the available code even though hidden tests were not fully passing.",
                                *[str(item) for item in existing_improvements if str(item).strip()],
                            ][:5]
                        result["next_step"] = "Stage timed out. Result captured from current submission and moved to next stage."
                        updated_scores[stage_key] = result
                        st.session_state.coding_room_stage_scores = updated_scores
                        append_coding_room_message(
                            "assistant",
                            (
                                f"Stage {stage_index + 1} auto-evaluated at timeout: "
                                f"{result.get('score', 0)}% ({result.get('verdict', '')})."
                            ),
                        )
                    else:
                        st.error("Run Evaluate Stage first (or wait for timer expiry) before moving ahead.")
                        updated_scores = {}

                if updated_scores:
                    if stage_index < total_stages - 1:
                        st.session_state.coding_room_stage_index = stage_index + 1
                        next_stage = stages[stage_index + 1]
                        append_coding_room_message(
                            "assistant",
                            (
                                f"Great. Moving to Stage {stage_index + 2}/{total_stages}: {next_stage.get('title', '')}. "
                                "Share approach first, then complete the starter code."
                            ),
                        )
                        st.rerun()
                    overall_scores = []
                    final_scores = st.session_state.get("coding_room_stage_scores", {})
                    if not isinstance(final_scores, dict):
                        final_scores = {}
                    for idx in range(total_stages):
                        result = final_scores.get(str(idx))
                        if isinstance(result, dict):
                            overall_scores.append(int(result.get("score", 0)))
                    overall_score = int(sum(overall_scores) / max(1, len(overall_scores)))
                    st.success(
                        f"Coding journey complete. Overall score: {overall_score}% ({summarize_coding_stage_score(overall_score)})."
                    )

        if reset_clicked:
            st.session_state.coding_room_source_sig = ""
            st.session_state.coding_room_payload = None
            st.session_state.coding_room_stage_index = 0
            st.session_state.coding_room_stage_scores = {}
            st.session_state.coding_room_messages = []
            st.session_state.coding_room_session_started = False
            st.session_state.coding_room_clear_input = True
            st.session_state.coding_room_scroll_pending = False
            st.session_state.coding_room_stage_started_at = {}
            st.session_state.coding_room_hidden_tests = {}
            st.session_state.coding_room_stage_approaches = {}
            st.rerun()

    if stage_scores:
        st.markdown("### Coding Evaluation Snapshot")
        approach_summary_map = st.session_state.get("coding_room_stage_approaches", {})
        if not isinstance(approach_summary_map, dict):
            approach_summary_map = {}
        summary_rows: list[dict[str, str]] = []
        for idx in range(total_stages):
            result = stage_scores.get(str(idx), {})
            approach_status = "Provided" if str(approach_summary_map.get(str(idx), "")).strip() else "Missing"
            if not isinstance(result, dict) or not result:
                summary_rows.append(
                    {
                        "Stage": f"Stage {idx + 1}",
                        "Title": str(stages[idx].get("title", "")),
                        "Score": "--",
                        "Verdict": "Pending",
                        "Approach": approach_status,
                    }
                )
                continue
            summary_rows.append(
                {
                    "Stage": f"Stage {idx + 1}",
                    "Title": str(stages[idx].get("title", "")),
                    "Score": f"{int(result.get('score', 0))}%",
                    "Verdict": str(result.get("verdict", "")),
                    "Approach": approach_status,
                }
            )
        st.dataframe(summary_rows, use_container_width=True, hide_index=True)


def render_main_screen() -> None:
    user = st.session_state.user
    render_app_styles()
    render_top_left_logo()
    sync_bot_for_logged_in_user()
    render_candidate_sidebar(user)

    view = str(st.session_state.get("dashboard_view", "home")).strip().lower()
    if view == "chats":
        st.session_state.bot_open = False
        render_recent_chats_view(user)
        render_zoswi_outside_minimize_listener(False)
        return
    if view == "scores":
        render_recent_scores_view(user)
        render_zoswi_widget()
        return
    if view == "coding_room":
        st.session_state.bot_open = False
        render_coding_room_view(user)
        render_zoswi_outside_minimize_listener(False)
        return

    render_home_dashboard(user)
    render_zoswi_widget()


def get_current_session_user() -> Any:
    return st.session_state.get("user")


def main() -> None:
    config = PageConfigDTO(page_title="Resume AI Checker", layout="wide", initial_sidebar_state="expanded")
    handlers = AppRuntimeHandlersDTO(
        init_db=init_db,
        init_state=init_state,
        sync_promo_codes_from_secrets=sync_promo_codes_from_secrets,
        try_restore_user_from_cookie=try_restore_user_from_cookie,
        render_auth_cookie_sync=render_auth_cookie_sync,
        render_auth_screen=render_auth_screen,
        render_main_screen=render_main_screen,
        get_current_user=get_current_session_user,
    )
    run_app_runtime(config, handlers)


if __name__ == "__main__":
    main()
