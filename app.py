import hashlib
import hmac
import html
import io
import json
import os
import re
import secrets
import sqlite3
import smtplib
import zipfile
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any
from xml.etree import ElementTree as ET

import pdfplumber
import streamlit as st
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

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
EMAIL_OTP_TTL_MINUTES_DEFAULT = 10
EMAIL_OTP_RESEND_SECONDS_DEFAULT = 60
EMAIL_OTP_MAX_ATTEMPTS_DEFAULT = 5
SIGNUP_REQUEST_TTL_HOURS_DEFAULT = 24
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

    now_iso = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "DELETE FROM signup_verification_requests WHERE expires_at <= ?",
        (now_iso,),
    )

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
        return False, "Email OTP is not configured: missing OTP secret."

    smtp_cfg = get_smtp_settings()
    if not smtp_cfg["host"] or not smtp_cfg["from_email"]:
        return False, "Email OTP is not configured: missing SMTP host/from email."
    if bool(smtp_cfg["username"]) != bool(smtp_cfg["password"]):
        return False, "Email OTP is not configured: SMTP username/password must both be set."
    return True, ""


def hash_email_otp(otp_code: str) -> str:
    pepper = get_email_otp_pepper()
    if not pepper:
        raise RuntimeError("Missing OTP secret configuration.")
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
        return False, "Email OTP is not configured: missing OTP secret."

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


def send_email_verification_otp(user_id: int, email: str) -> tuple[bool, str]:
    cleaned_email = str(email or "").strip().lower()
    if user_id <= 0 or not cleaned_email:
        return False, "Email verification target is invalid."

    config_ok, config_msg = can_send_email_otp()
    if not config_ok:
        return False, config_msg

    ttl_minutes = get_email_otp_ttl_minutes()
    resend_seconds = get_email_otp_resend_seconds()
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
        return False, "Email OTP is not configured: missing OTP secret."

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


def authenticate_user(email: str, password: str) -> dict[str, Any] | None:
    conn = db_connect()
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT id, full_name, email, role, years_experience, created_at, password_hash, email_verified_at
            FROM users
            WHERE email = ?
            """,
            (email.strip().lower(),),
        ).fetchone()
        if row is None:
            return None

        stored_hash = str(row["password_hash"] or "")
        if not verify_password(password, stored_hash):
            return None

        if not is_modern_password_hash(stored_hash):
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (hash_password(password), int(row["id"])),
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


def record_user_login_event(user_id: int, login_method: str, login_provider: str = "") -> None:
    if user_id <= 0:
        return
    method = str(login_method or "").strip().lower()
    provider = str(login_provider or "").strip().lower()
    if not method:
        method = "password"
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = db_connect()
    try:
        conn.execute(
            """
            INSERT INTO user_login_events (user_id, login_method, login_provider, login_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, method, provider or None, now_iso),
        )
        conn.commit()
    finally:
        conn.close()


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
    if user_id <= 0:
        return ""
    raw_token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    created_at = datetime.now(timezone.utc)
    expires_at = created_at + timedelta(days=max(1, ttl_days))
    created_iso = created_at.isoformat()
    expires_iso = expires_at.isoformat()
    conn = db_connect()
    try:
        conn.execute(
            """
            INSERT INTO auth_sessions (user_id, token_hash, created_at, expires_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, token_hash, created_iso, expires_iso, created_iso),
        )
        conn.execute(
            "DELETE FROM auth_sessions WHERE expires_at <= ?",
            (created_iso,),
        )
        conn.commit()
    finally:
        conn.close()
    return raw_token


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
    cleaned = str(raw_token or "").strip()
    if not cleaned:
        return
    token_hash = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
    conn = db_connect()
    try:
        conn.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (token_hash,))
        conn.commit()
    finally:
        conn.close()


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
            ORDER BY datetime(updated_at) DESC, id DESC
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

    key = get_openai_key()
    if key:
        try:
            llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2, api_key=key)
            prompt = f"""
Create a short chat title based on intent, not verbatim copy.
Rules:
- 3 to 7 words
- professional and clear
- no quotes, no emojis, no trailing punctuation
- focus on resume/JD/career context

User request:
{cleaned}
            """.strip()
            raw_title = str(llm.invoke(prompt).content).strip()
            raw_title = re.sub(r"[\r\n]+", " ", raw_title).strip(" .,:;!?-")
            if raw_title:
                words = raw_title.split()
                if len(words) > 8:
                    raw_title = " ".join(words[:8])
                return raw_title
        except Exception:
            pass

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
    title = infer_chat_title_from_intent(cleaned)[:70]
    conn = db_connect()
    try:
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


def get_openai_key() -> str | None:
    try:
        if st.secrets.get("OPENAI_API_KEY"):
            return st.secrets["OPENAI_API_KEY"]
    except Exception:
        pass
    return os.getenv("OPENAI_API_KEY")


def time_based_greeting() -> str:
    hour = datetime.now().hour
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


def build_recent_chat_context(limit: int = 8) -> str:
    chat = st.session_state.get("bot_messages", [])
    if not isinstance(chat, list):
        return ""

    lines: list[str] = []
    for msg in chat[-limit:]:
        role = str(msg.get("role", "")).strip().lower()
        content = str(msg.get("content", "")).strip()
        if role not in {"user", "assistant"} or not content:
            continue
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def build_assistant_prompt(message: str) -> str:
    analysis = st.session_state.get("analysis_result")
    user = st.session_state.get("user") or {}
    full_name = str(user.get("full_name", "")).strip() or "Candidate"

    if analysis:
        analysis_summary = (
            f"Category: {analysis['category']}, Score: {analysis['score']}%, "
            f"Summary: {analysis.get('summary', '')}, "
            f"Strengths: {', '.join(analysis.get('strengths', []))}, "
            f"Gaps: {', '.join(analysis.get('gaps', []))}, "
            f"Recommendations: {', '.join(analysis.get('recommendations', []))}"
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

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.5, api_key=key)
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

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.5, api_key=key)
    prompt = build_assistant_prompt(message)

    try:
        return llm.invoke(prompt).content
    except Exception:
        return "I hit a temporary issue generating a response. Please try again."


def category_style(category: str) -> tuple[str, str]:
    if category == "Perfect Match":
        return "#1E8E3E", "#E8F5E9"
    if category == "Excellent":
        return "#0B5394", "#E7F1FF"
    if category == "Good":
        return "#A56600", "#FFF4E5"
    return "#9C2E2E", "#FDECEC"


def render_app_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,500,0,0');
        @import url('https://fonts.googleapis.com/icon?family=Material+Icons+Outlined');
        :root {
            --ai-ink: #102a43;
            --ai-muted: #486581;
            --ai-accent-soft: #e6fffa;
            --ai-card: #ffffff;
            --ai-line: #d9e2ec;
        }
        .stApp {
            background:
                radial-gradient(1200px 500px at 15% -10%, #e8f2ff 0%, transparent 55%),
                radial-gradient(900px 450px at 100% 0%, #fff4d8 0%, transparent 60%),
                #f8fafc;
        }
        .ai-hero {
            border: 1px solid var(--ai-line);
            background: linear-gradient(115deg, #ffffff 0%, #f0fdfa 100%);
            border-radius: 16px;
            padding: 20px 22px;
            margin-bottom: 14px;
            box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
        }
        .ai-hero h1 {
            margin: 0 0 8px 0;
            color: var(--ai-ink);
            font-size: 1.7rem;
            line-height: 1.2;
        }
        .ai-hero p {
            margin: 0;
            color: var(--ai-muted);
            font-size: 0.98rem;
        }
        .ai-card {
            border: 1px solid var(--ai-line);
            background: var(--ai-card);
            border-radius: 14px;
            padding: 14px 16px;
            margin-bottom: 10px;
        }
        .ai-card-title {
            margin: 0 0 6px 0;
            color: var(--ai-ink);
            font-size: 1rem;
            font-weight: 700;
        }
        .ai-chip {
            display: inline-block;
            border: 1px solid #a7f3d0;
            background: var(--ai-accent-soft);
            color: #065f46;
            border-radius: 999px;
            padding: 2px 10px;
            font-size: 0.76rem;
            margin-bottom: 8px;
        }
        .ai-muted {
            color: var(--ai-muted);
            font-size: 0.92rem;
            margin: 0 0 4px 0;
        }
        .st-key-oauth_social_stack {
            margin-top: 0;
        }
        .st-key-oauth_social_stack [data-testid="stVerticalBlock"] {
            gap: 0.6rem;
        }
        .st-key-oauth_login_btn button,
        .st-key-oauth_login_btn [data-testid="baseButton-secondary"],
        .st-key-oauth_login_linkedin_btn button,
        .st-key-oauth_login_linkedin_btn [data-testid="baseButton-secondary"] {
            border: 1px solid #d1d5db !important;
            background: #ffffff !important;
            color: #0f172a !important;
            border-radius: 12px !important;
            font-weight: 700 !important;
            box-shadow: 0 6px 16px rgba(15, 23, 42, 0.08) !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            gap: 8px !important;
            overflow: visible !important;
        }
        .st-key-oauth_login_btn button:hover,
        .st-key-oauth_login_btn [data-testid="baseButton-secondary"]:hover,
        .st-key-oauth_login_linkedin_btn button:hover,
        .st-key-oauth_login_linkedin_btn [data-testid="baseButton-secondary"]:hover {
            border: 1px solid #9ca3af !important;
            background: #f8fafc !important;
            transform: translateY(-1px);
        }
        .st-key-oauth_login_btn button::before,
        .st-key-oauth_login_btn [data-testid="baseButton-secondary"]::before {
            content: "";
            width: 14px;
            height: 14px;
            flex: 0 0 14px;
            display: inline-block;
            background-repeat: no-repeat;
            background-size: 14px 14px;
            background-image: url("data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 viewBox=%270 0 48 48%27%3E%3Cpath fill=%27%23FFC107%27 d=%27M43.611,20.083H42V20H24v8h11.303C33.655,32.657,29.263,36,24,36c-6.627,0-12-5.373-12-12s5.373-12,12-12c3.059,0,5.842,1.154,7.961,3.039l5.657-5.657C34.046,6.053,29.268,4,24,4C12.955,4,4,12.955,4,24s8.955,20,20,20s20-8.955,20-20C44,22.659,43.862,21.35,43.611,20.083z%27/%3E%3Cpath fill=%27%23FF3D00%27 d=%27M6.306,14.691l6.571,4.819C14.655,15.108,18.961,12,24,12c3.059,0,5.842,1.154,7.961,3.039l5.657-5.657C34.046,6.053,29.268,4,24,4C16.318,4,9.656,8.337,6.306,14.691z%27/%3E%3Cpath fill=%27%234CAF50%27 d=%27M24,44c5.166,0,9.86-1.977,13.409-5.192l-6.19-5.238C29.143,35.091,26.715,36,24,36c-5.237,0-9.615-3.325-11.283-7.946l-6.522,5.025C9.505,39.556,16.227,44,24,44z%27/%3E%3Cpath fill=%27%231976D2%27 d=%27M43.611,20.083H42V20H24v8h11.303c-1.11,3.059-3.275,5.483-6.084,7.571c0.001-0.001,0.002-0.001,0.003-0.002l6.19,5.238C35.971,40.399,44,34,44,24C44,22.659,43.862,21.35,43.611,20.083z%27/%3E%3C/svg%3E");
        }
        .st-key-oauth_login_linkedin_btn button::before,
        .st-key-oauth_login_linkedin_btn [data-testid="baseButton-secondary"]::before {
            content: "in";
            width: 14px;
            height: 14px;
            flex: 0 0 14px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 2px;
            background: #0a66c2;
            color: #ffffff;
            font-size: 10px;
            font-weight: 800;
            line-height: 1;
            font-family: Arial, sans-serif;
            text-transform: lowercase;
        }
        .st-key-oauth_login_btn button p,
        .st-key-oauth_login_btn button span,
        .st-key-oauth_login_linkedin_btn button p,
        .st-key-oauth_login_linkedin_btn button span {
            margin: 0 !important;
        }
        .st-key-oauth_promo_code [data-testid="stTextInputRootElement"] > div {
            background: transparent !important;
        }
        .st-key-oauth_promo_code [data-testid="stTextInputRootElement"] input {
            background: #ffffff !important;
            border: 1px solid #ffffff !important;
            border-radius: 12px !important;
            color: #0f172a !important;
            box-shadow: 0 6px 16px rgba(15, 23, 42, 0.08) !important;
            text-align: center !important;
        }
        .st-key-oauth_promo_code [data-testid="stTextInputRootElement"] input::placeholder {
            color: #64748b !important;
            opacity: 1 !important;
        }
        .st-key-oauth_promo_code [data-testid="stTextInputRootElement"] input:focus,
        .st-key-oauth_promo_code [data-testid="stTextInputRootElement"] input:focus-visible {
            border: 1px solid #d1d5db !important;
            outline: none !important;
        }
        .st-key-oauth_promo_send button,
        .st-key-oauth_promo_send [data-testid="baseButton-secondary"] {
            border: 1px solid #ffffff !important;
            background: #ffffff !important;
            color: #0f172a !important;
            border-radius: 12px !important;
            min-height: 2.45rem !important;
            font-weight: 800 !important;
            box-shadow: 0 6px 16px rgba(15, 23, 42, 0.08) !important;
        }
        .st-key-oauth_promo_send button:hover,
        .st-key-oauth_promo_send [data-testid="baseButton-secondary"]:hover {
            border: 1px solid #d1d5db !important;
            background: #f8fafc !important;
            transform: translateY(-1px);
        }
        .st-key-oauth_promo_send button p {
            margin: 0 !important;
            font-size: 1rem !important;
        }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #f8fbff 0%, #eefbf7 100%);
            border-right: 1px solid #d9e2ec;
        }
        [data-testid="stSidebarHeader"] {
            display: none !important;
        }
        [data-testid="stSidebarCollapseButton"] {
            display: none !important;
        }
        [data-testid="stSidebarCollapsedControl"] {
            display: none !important;
        }
        [data-testid="stSidebar"] [data-testid="stSidebarContent"] {
            padding-bottom: 0;
            height: 100vh;
            overflow: hidden !important;
        }
        [data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
            min-height: 100%;
            height: 100%;
            display: flex;
            flex-direction: column;
            overflow: hidden !important;
        }
        .st-key-sidebar_menu_body {
            flex: 1 1 auto;
            overflow: hidden;
        }
        .ai-sidebar-signed {
            margin: 0 0 6px 0;
            color: #0f172a;
            font-size: 0.82rem;
            font-weight: 600;
        }
        .ai-sidebar-signed strong {
            color: #0b3b6f;
            font-weight: 800;
        }
        .st-key-sidebar_signed_row [data-testid="stHorizontalBlock"] {
            align-items: center;
        }
        .st-key-sidebar_header_logout .stButton,
        .st-key-sidebar_header_logout [data-testid="stButton"] {
            margin: 0 !important;
            display: flex !important;
            justify-content: flex-end !important;
        }
        .st-key-sidebar_header_logout .stButton > button,
        .st-key-sidebar_header_logout [data-testid="baseButton-secondary"] {
            border: none !important;
            background: transparent !important;
            background-color: transparent !important;
            background-image: none !important;
            box-shadow: none !important;
            border-radius: 0 !important;
            min-height: 0 !important;
            min-width: 0 !important;
            padding: 0 !important;
            margin: 0 !important;
            color: #be123c !important;
            font-size: 0.78rem !important;
            line-height: 1 !important;
            font-weight: 800 !important;
            width: auto !important;
            height: auto !important;
            display: inline-block !important;
            appearance: none !important;
            -webkit-appearance: none !important;
            text-transform: none !important;
            letter-spacing: 0.015em;
            white-space: nowrap !important;
            writing-mode: horizontal-tb !important;
            text-shadow: 0 0 5px rgba(225, 29, 72, 0.22);
            animation: ai-logout-float 2.8s ease-in-out infinite, ai-logout-glow 3s ease-in-out infinite;
            transition: color 140ms ease, filter 140ms ease, letter-spacing 140ms ease !important;
        }
        .st-key-sidebar_header_logout .stButton > button p,
        .st-key-sidebar_header_logout .stButton > button span {
            margin: 0 !important;
            font-size: 0.78rem !important;
            line-height: 1 !important;
            color: #be123c !important;
            font-weight: 800 !important;
            letter-spacing: 0.015em;
            white-space: nowrap !important;
            writing-mode: horizontal-tb !important;
            text-shadow: 0 0 5px rgba(225, 29, 72, 0.22);
        }
        .st-key-sidebar_header_logout .stButton > button:focus,
        .st-key-sidebar_header_logout .stButton > button:focus-visible,
        .st-key-sidebar_header_logout .stButton > button:active,
        .st-key-sidebar_header_logout [data-testid="baseButton-secondary"]:focus,
        .st-key-sidebar_header_logout [data-testid="baseButton-secondary"]:focus-visible,
        .st-key-sidebar_header_logout [data-testid="baseButton-secondary"]:active {
            border: none !important;
            background: transparent !important;
            background-color: transparent !important;
            background-image: none !important;
            box-shadow: none !important;
            outline: none !important;
        }
        .st-key-sidebar_header_logout .stButton > button:hover,
        .st-key-sidebar_header_logout [data-testid="baseButton-secondary"]:hover {
            border: none !important;
            background: transparent !important;
            background-color: transparent !important;
            background-image: none !important;
            color: #e11d48 !important;
            box-shadow: none !important;
            filter: none !important;
            transform: none !important;
            text-decoration: none;
            letter-spacing: 0.02em;
            filter: drop-shadow(0 0 8px rgba(225, 29, 72, 0.45)) !important;
        }
        .st-key-sidebar_menu_toggle .stButton > button {
            border: none !important;
            background: linear-gradient(120deg, #0284c7 0%, #0ea5e9 55%, #22d3ee 100%) !important;
            color: #ffffff !important;
            border-radius: 999px !important;
            padding: 0.4rem 0.72rem !important;
            min-height: 0 !important;
            font-weight: 800 !important;
            font-size: 0.9rem !important;
            box-shadow: 0 8px 18px rgba(2, 132, 199, 0.35) !important;
            justify-content: flex-start !important;
            text-align: left !important;
            transition: transform 150ms ease, filter 150ms ease, box-shadow 150ms ease !important;
        }
        .st-key-sidebar_menu_toggle .stButton > button p {
            margin: 0 !important;
        }
        .st-key-sidebar_menu_toggle .stButton > button:hover {
            border: none !important;
            background: linear-gradient(120deg, #0284c7 0%, #06b6d4 60%, #22d3ee 100%) !important;
            transform: translateY(-1px) scale(1.01);
            filter: brightness(1.05);
            box-shadow: 0 10px 24px rgba(14, 165, 233, 0.42) !important;
        }
        .st-key-sidebar_nav_menu {
            margin-top: 4px;
            margin-bottom: 2px;
        }
        .st-key-sidebar_nav_menu [data-testid="stVerticalBlock"] {
            gap: 0.06rem !important;
        }
        .st-key-sidebar_nav_menu [data-testid="stElementContainer"] {
            margin-bottom: 0 !important;
        }
        .st-key-sidebar_nav_menu .stButton {
            margin: 0 !important;
        }
        .st-key-sidebar_nav_menu .stButton > button {
            border: none !important;
            background: transparent !important;
            color: #0c4a6e !important;
            border-radius: 0 !important;
            padding: 0.12rem 0 !important;
            min-height: 0 !important;
            font-weight: 700 !important;
            font-size: 0.84rem !important;
            box-shadow: none !important;
            justify-content: flex-start !important;
            text-align: left !important;
            transition: transform 140ms ease, color 140ms ease, filter 140ms ease !important;
        }
        .st-key-sidebar_nav_menu .stButton > button p {
            margin: 0 !important;
        }
        .st-key-sidebar_nav_menu .stButton > button:hover {
            border: none !important;
            background: transparent !important;
            color: #0284c7 !important;
            transform: translateX(3px);
            filter: drop-shadow(0 0 5px rgba(14, 165, 233, 0.32));
        }
        .st-key-full_chat_shell {
            border: 1px solid #dbeafe;
            border-radius: 18px;
            background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
            padding: 10px;
            box-shadow: 0 14px 30px rgba(30, 64, 175, 0.08);
        }
        .st-key-full_recent_chats {
            border: 1px solid #dbeafe;
            border-radius: 14px;
            background: #ffffff;
            padding: 8px 10px;
            min-height: 72vh;
        }
        .st-key-full_recent_chats .stButton > button {
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
            justify-content: flex-start !important;
            text-align: left !important;
            padding: 0.3rem 0 !important;
            min-height: 0 !important;
            color: #1e3a8a !important;
            border-radius: 0 !important;
            font-size: 0.84rem !important;
        }
        .st-key-full_recent_chats .stButton > button p {
            margin: 0 !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
        }
        .st-key-full_recent_chats .stButton > button:hover {
            color: #0f172a !important;
            transform: translateX(2px);
        }
        .st-key-full_chat_panel {
            border: 1px solid #dbeafe;
            border-radius: 14px;
            background: #ffffff;
            padding: 10px 12px;
            min-height: 72vh;
        }
        .st-key-full_chat_input_wrap .stButton > button {
            border-radius: 12px !important;
        }
        .st-key-full_scores_table {
            border: 1px solid #dbeafe;
            border-radius: 14px;
            background: #ffffff;
            padding: 8px;
        }
        .st-key-sidebar_recent_chats .stButton > button {
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
            justify-content: flex-start !important;
            text-align: left !important;
            padding: 0.22rem 0 !important;
            min-height: 0 !important;
            color: #1e3a8a !important;
            font-weight: 600 !important;
            border-radius: 0 !important;
        }
        .st-key-sidebar_recent_chats .stButton > button > div {
            width: 100%;
            overflow: hidden;
        }
        .st-key-sidebar_recent_chats .stButton > button p {
            margin: 0 !important;
            width: 100%;
            font-size: 0.82rem !important;
            line-height: 1.2 !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
        }
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_edit_"] button,
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_delete_"] button,
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_save_"] button,
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_cancel_"] button {
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
            border-radius: 0 !important;
            justify-content: center !important;
            text-align: center !important;
            padding: 0.2rem 0 !important;
            min-height: 0 !important;
            font-size: 0.95rem !important;
            font-weight: 700 !important;
            transition: transform 140ms ease, color 140ms ease, filter 140ms ease !important;
        }
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_edit_"] button,
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_save_"] button {
            color: #0f766e !important;
        }
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_delete_"] button,
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_cancel_"] button {
            color: #be123c !important;
        }
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_edit_"] button p,
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_delete_"] button p,
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_save_"] button p,
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_cancel_"] button p {
            font-size: 1rem !important;
            text-overflow: clip !important;
        }
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_edit_"] button:hover,
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_delete_"] button:hover,
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_save_"] button:hover,
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_cancel_"] button:hover {
            background: transparent !important;
            border: none !important;
            transform: translateY(-1px) scale(1.12) !important;
            filter: drop-shadow(0 0 6px rgba(15, 118, 110, 0.25));
        }
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_delete_"] button:hover,
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_cancel_"] button:hover {
            filter: drop-shadow(0 0 6px rgba(190, 24, 93, 0.3));
        }
        .st-key-sidebar_recent_chats .stButton > button:hover {
            color: #0f172a !important;
            transform: translateX(2px);
        }
        .st-key-zoswi_minimize button,
        .st-key-zoswi_reset button,
        .st-key-zoswi_close button {
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
            border-radius: 0 !important;
            padding: 0.08rem 0.22rem !important;
            min-height: 0 !important;
            color: #0b3b6f !important;
            font-weight: 700 !important;
            transition: transform 140ms ease, color 140ms ease, filter 140ms ease !important;
        }
        .st-key-zoswi_minimize button:hover,
        .st-key-zoswi_reset button:hover,
        .st-key-zoswi_close button:hover {
            background: transparent !important;
            border: none !important;
            color: #0284c7 !important;
            transform: translateY(-1px) scale(1.12) !important;
            filter: drop-shadow(0 0 6px rgba(2, 132, 199, 0.28));
        }
        .ai-sidebar-title {
            font-size: 1rem;
            font-weight: 800;
            color: #0b3b6f;
            margin: 4px 0 10px 0;
        }
        .ai-side-card {
            border: 1px solid #c7d2fe;
            background: #ffffff;
            border-radius: 14px;
            padding: 12px 12px 10px 12px;
            box-shadow: 0 8px 20px rgba(15, 23, 42, 0.06);
            margin-top: 6px;
        }
        .ai-side-card p {
            margin: 0 0 5px 0;
            color: #334e68;
            font-size: 0.9rem;
        }
        .ai-side-card .title {
            margin: 0 0 8px 0;
            color: #102a43;
            font-size: 0.98rem;
            font-weight: 700;
        }
        .st-key-sidebar_logout button {
            margin-top: 0;
            width: auto !important;
            height: auto !important;
            min-height: 0 !important;
            border-radius: 0 !important;
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
            color: #9f1239 !important;
            font-size: 1.6rem !important;
            font-weight: 700 !important;
            padding: 0 !important;
            line-height: 1 !important;
            transition: transform 150ms ease, color 150ms ease;
            filter: drop-shadow(0 0 4px rgba(190, 24, 93, 0.26));
            animation: ai-logout-float 2.8s ease-in-out infinite, ai-logout-glow 3s ease-in-out infinite;
        }
        .st-key-sidebar_logout button,
        .st-key-sidebar_logout button p {
            font-family: "Material Symbols Outlined", "Segoe UI Symbol", sans-serif !important;
            font-feature-settings: "liga";
            font-variation-settings: "FILL" 0, "wght" 500, "GRAD" 0, "opsz" 24;
            letter-spacing: normal !important;
            text-transform: none !important;
        }
        .st-key-sidebar_logout button:hover {
            border: none !important;
            background: transparent !important;
            color: #be123c !important;
            transform: translateX(2px) scale(1.1);
        }
        .st-key-sidebar_fixed_actions {
            position: relative;
            bottom: 0;
            width: 100%;
            z-index: 10;
            margin-top: auto;
            padding: 8px 0 8px 0;
            background: linear-gradient(
                180deg,
                rgba(248, 251, 255, 0) 0%,
                rgba(248, 251, 255, 0.96) 28%,
                rgba(238, 251, 247, 0.99) 100%
            );
            backdrop-filter: blur(4px);
            border-top: 1px solid rgba(148, 163, 184, 0.22);
        }
        .st-key-sidebar_fixed_actions [data-testid="stHorizontalBlock"] {
            gap: 10px;
        }
        .st-key-zoswi_widget {
            position: fixed;
            right: 14px;
            bottom: 14px;
            z-index: 1000;
            width: min(380px, calc(100vw - 24px));
            display: flex;
            flex-direction: column;
            align-items: flex-end;
        }
        .st-key-zoswi_panel {
            border: 1px solid #bfdbfe;
            background: linear-gradient(135deg, #ffffff 0%, #eff6ff 45%, #ecfeff 100%);
            background-size: 180% 180%;
            border-radius: 30px;
            padding: 10px 12px;
            box-shadow: 0 16px 34px rgba(30, 64, 175, 0.2);
            margin-bottom: 10px;
            position: relative;
            overflow: visible;
            backdrop-filter: blur(6px);
            transform-origin: bottom right;
            animation: zoswi-think-pop 420ms cubic-bezier(0.2, 0.8, 0.2, 1),
                       zoswi-think-breathe 3.8s ease-in-out infinite 420ms,
                       zoswi-panel-gradient 8s ease-in-out infinite 420ms;
        }
        .st-key-zoswi_panel::before,
        .st-key-zoswi_panel::after {
            content: "";
            position: absolute;
            border-radius: 50%;
            background: radial-gradient(circle at 35% 35%, #ffffff 0%, #eff6ff 100%);
            border: 1px solid #bfdbfe;
            box-shadow: 0 4px 12px rgba(30, 64, 175, 0.14);
            pointer-events: none;
            animation: zoswi-tail-bob 2.2s ease-in-out infinite;
        }
        .st-key-zoswi_panel::before {
            width: 14px;
            height: 14px;
            right: 46px;
            bottom: -12px;
            animation-delay: 0.1s;
        }
        .st-key-zoswi_panel::after {
            width: 9px;
            height: 9px;
            right: 30px;
            bottom: -23px;
            animation-delay: 0.35s;
        }
        .st-key-zoswi_panel .stButton > button {
            border-radius: 10px;
        }
        .st-key-zoswi_panel [data-testid="stVerticalBlockBorderWrapper"] {
            scroll-behavior: smooth;
        }
        .st-key-zoswi_panel .zoswi-msg {
            margin: 0.24rem 0 0.52rem 0;
        }
        .st-key-zoswi_panel .zoswi-msg.assistant {
            text-align: left;
        }
        .st-key-zoswi_panel .zoswi-msg.user {
            text-align: right;
        }
        .st-key-zoswi_panel .zoswi-msg-head {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 0.82rem;
            font-weight: 700;
            color: #1e3a8a;
            letter-spacing: 0.01em;
            margin-bottom: 2px;
        }
        .st-key-zoswi_panel .zoswi-msg.user .zoswi-msg-head {
            justify-content: flex-end;
            color: #0f766e;
        }
        .st-key-zoswi_panel .zoswi-msg-text {
            display: inline-block;
            max-width: 92%;
            color: #0f172a;
            font-size: 0.94rem;
            line-height: 1.4;
            white-space: pre-wrap;
            word-break: break-word;
        }
        .st-key-zoswi_panel .zoswi-msg.user .zoswi-msg-text {
            text-align: left;
        }
        .st-key-zoswi_minimize button,
        .st-key-zoswi_reset button,
        .st-key-zoswi_close button {
            width: auto;
            height: auto;
            min-height: 0;
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
            color: #0b3b6f;
            font-weight: 800;
            font-size: 1.05rem;
            line-height: 1;
            border-radius: 0 !important;
            padding: 0.08rem 0.22rem !important;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-left: auto;
            transition: transform 140ms ease, color 140ms ease, filter 140ms ease;
        }
        .st-key-zoswi_minimize button:hover,
        .st-key-zoswi_reset button:hover,
        .st-key-zoswi_close button:hover {
            background: transparent !important;
            border: none !important;
            color: #0284c7 !important;
            transform: translateY(-1px) scale(1.12);
            filter: drop-shadow(0 0 6px rgba(2, 132, 199, 0.28));
        }
        @keyframes zoswi-pulse {
            0% {
                transform: translateY(0) scale(1);
                filter: saturate(1.2) brightness(1.06);
            }
            50% {
                transform: translateY(-4px) scale(1.13);
                filter: saturate(1.55) brightness(1.2);
            }
            100% {
                transform: translateY(0) scale(1);
                filter: saturate(1.2) brightness(1.06);
            }
        }
        .st-key-zoswi_fab {
            position: relative;
            overflow: visible;
        }
        .st-key-zoswi_fab::before {
            content: "";
            position: absolute;
            right: 10px;
            bottom: 8px;
            width: 56px;
            height: 56px;
            border-radius: 50%;
            background: radial-gradient(circle, rgba(56, 189, 248, 0.55) 0%, rgba(14, 116, 144, 0) 72%);
            filter: blur(6px);
            pointer-events: none;
            animation: zoswi-fab-halo 2.4s ease-in-out infinite;
        }
        .st-key-zoswi_fab::after {
            content: "✦";
            position: absolute;
            right: 2px;
            bottom: 52px;
            font-size: 0.95rem;
            color: #0ea5e9;
            text-shadow: 0 0 10px rgba(14, 165, 233, 0.65);
            pointer-events: none;
            animation: zoswi-spark 2.8s ease-in-out infinite;
        }
        .st-key-zoswi_fab button {
            width: 76px;
            height: 76px;
            border-radius: 50%;
            border: none !important;
            background: transparent !important;
            color: #0f172a;
            font-size: 4.1rem !important;
            line-height: 1;
            padding: 0 !important;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: none !important;
            text-shadow: 0 10px 18px rgba(59, 130, 246, 0.5);
            animation: zoswi-pulse 1.65s ease-in-out infinite, zoswi-wiggle 5.6s ease-in-out infinite;
        }
        .st-key-zoswi_fab button p {
            margin: 0 !important;
            font-size: 4.1rem !important;
            line-height: 1 !important;
        }
        .st-key-zoswi_fab button:hover {
            filter: saturate(1.6) brightness(1.2);
        }
        .zoswi-think-symbol {
            font-size: 1.05rem;
            line-height: 1;
            margin-top: -2px;
            margin-bottom: 2px;
            display: inline-block;
            color: #7c3aed;
            filter: drop-shadow(0 0 6px rgba(168, 85, 247, 0.42));
            animation: zoswi-think-symbol 1.35s ease-in-out infinite;
        }
        @keyframes zoswi-think-pop {
            0% {
                opacity: 0;
                transform: translateY(22px) scale(0.88);
                filter: blur(8px);
            }
            70% {
                opacity: 1;
                transform: translateY(-2px) scale(1.03);
                filter: blur(0);
            }
            100% {
                opacity: 1;
                transform: translateY(0) scale(1);
                filter: blur(0);
            }
        }
        @keyframes zoswi-think-breathe {
            0%, 100% { box-shadow: 0 16px 34px rgba(30, 64, 175, 0.2); }
            50% { box-shadow: 0 18px 40px rgba(124, 58, 237, 0.24); }
        }
        @keyframes zoswi-panel-gradient {
            0%, 100% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
        }
        @keyframes zoswi-tail-bob {
            0%, 100% { transform: translateY(0) scale(1); opacity: 0.95; }
            50% { transform: translateY(-2px) scale(1.05); opacity: 1; }
        }
        @keyframes zoswi-fab-halo {
            0%, 100% { transform: scale(0.9); opacity: 0.58; }
            50% { transform: scale(1.16); opacity: 0.9; }
        }
        @keyframes zoswi-wiggle {
            0%, 80%, 100% { transform: rotate(0deg); }
            84% { transform: rotate(-6deg); }
            88% { transform: rotate(6deg); }
            92% { transform: rotate(-4deg); }
            96% { transform: rotate(3deg); }
        }
        @keyframes zoswi-spark {
            0%, 100% { opacity: 0.3; transform: translateY(1px) scale(0.85) rotate(-8deg); }
            50% { opacity: 1; transform: translateY(-4px) scale(1.14) rotate(8deg); }
        }
        @keyframes zoswi-think-symbol {
            0%, 100% { transform: translateY(0) scale(1); opacity: 0.76; }
            50% { transform: translateY(-3px) scale(1.14); opacity: 1; }
        }
        @keyframes ai-logout-float {
            0%, 100% { transform: translateY(0) scale(1); }
            50% { transform: translateY(-2px) scale(1.05); }
        }
        @keyframes ai-logout-glow {
            0%, 100% { filter: drop-shadow(0 0 4px rgba(190, 24, 93, 0.24)); }
            50% { filter: drop-shadow(0 0 10px rgba(225, 29, 72, 0.55)); }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


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


def render_email_verification_panel() -> None:
    pending_ref_id = int(st.session_state.get("email_verification_ref_id") or 0)
    pending_email = str(st.session_state.get("email_verification_email", "")).strip().lower()
    verification_mode = str(st.session_state.get("email_verification_mode", "")).strip().lower()
    if pending_ref_id <= 0 or not pending_email:
        return

    st.markdown("---")
    st.caption(f"Verify your email to continue: {pending_email}")
    otp_code = st.text_input(
        "Email OTP",
        key="email_verification_otp_code",
        placeholder="Enter 6-digit code",
        max_chars=EMAIL_OTP_DIGITS,
    )
    verify_col, resend_col, cancel_col = st.columns(3, gap="small")

    with verify_col:
        verify_clicked = st.button("Verify OTP", key="verify_email_otp_btn", use_container_width=True)
    with resend_col:
        resend_clicked = st.button("Resend OTP", key="resend_email_otp_btn", use_container_width=True)
    with cancel_col:
        cancel_clicked = st.button("Cancel", key="cancel_email_otp_btn", use_container_width=True)

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


def render_auth_screen() -> None:
    render_zoswi_outside_minimize_listener(False)
    render_top_left_logo()
    st.title("Resume AI Checker")
    apply_pending_signup_form_reset()

    oauth_col, account_col = st.columns(2, gap="large")

    with oauth_col:
        if is_streamlit_oauth_configured():
            google_available = is_streamlit_oauth_provider_available("google")
            linkedin_available = is_streamlit_oauth_provider_available("linkedin")
            google_provider_name = get_streamlit_oauth_provider_name("google")
            linkedin_provider_name = get_streamlit_oauth_provider_name("linkedin")

            st.markdown("<div style='height:2in;'></div>", unsafe_allow_html=True)
            with st.container(key="oauth_social_stack"):
                left_space, button_col, right_space = st.columns([1,2,1], gap="large")
                with button_col:
                    if st.button(
                        "Continue with Google",
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
                        "Continue with LinkedIn",
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
                    if promo_codes_enabled():
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
        else:
            st.info("Google OAuth is not configured yet. Use login or create account on the right.")

    with account_col:
        st.caption("Create an account or log in to start resume-job matching.")
        auth_notice_message = str(st.session_state.get("auth_notice_message", "")).strip()
        if auth_notice_message:
            st.success(auth_notice_message)
            st.session_state.auth_notice_message = ""
        tab_login, tab_signup = st.tabs(["Login", "Create Account"])

        with tab_login:
            with st.form("login_form"):
                email = st.text_input("Email")
                password = st.text_input("Password", type="password")
                submit = st.form_submit_button("Login")
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

        with tab_signup:
            signup_success_message = str(st.session_state.get("signup_success_message", "")).strip()
            signup_warning_message = str(st.session_state.get("signup_warning_message", "")).strip()
            if signup_success_message:
                st.success(signup_success_message)
                if signup_warning_message:
                    st.warning(signup_warning_message)
                if int(st.session_state.get("email_verification_ref_id") or 0) > 0:
                    st.info("Enter the OTP code below to finish account creation.")
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
                with password_status_col:
                    st.markdown("<div style='height:1.9rem;'></div>", unsafe_allow_html=True)
                    st.markdown(
                        "<div style='font-size:0.82rem;color:#334155;font-weight:700;'>we care about you</div>",
                        unsafe_allow_html=True,
                    )
                    password_policy = get_password_policy_status(password)
                    for is_ok, label in [
                        (password_policy["min_length"], "8+ characters"),
                        (password_policy["has_upper"], "1 uppercase letter"),
                        (password_policy["has_special"], "1 special character"),
                    ]:
                        icon = "&#10003;" if is_ok else "&#10007;"
                        color = "#16a34a" if is_ok else "#dc2626"
                        st.markdown(
                            f"<div style='font-size:0.82rem;color:{color};font-weight:600;'>{icon} {label}</div>",
                            unsafe_allow_html=True,
                        )
                confirm_col, confirm_status_col = st.columns([4, 2], gap="small")
                with confirm_col:
                    confirm_password = st.text_input(
                        "Re-enter Password",
                        type="password",
                        key="signup_confirm_password",
                    )
                with confirm_status_col:
                    st.markdown("<div style='height:1.9rem;'></div>", unsafe_allow_html=True)
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
                                    "Verification code sent. Enter OTP below to finish account creation."
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
    clear_pending_email_verification()
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
                        if st.button("Logout", key="sidebar_header_logout_btn", help="Logout"):
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
    upload_col, jd_col = st.columns(2)
    with upload_col:
        uploaded_file = st.file_uploader("Upload Resume (PDF or DOCX)", type=["pdf", "docx"])
    with jd_col:
        job_description = st.text_area("Paste Job Description", height=280)

    analyze_clicked = st.button("Run Resume-JD Analysis", type="primary", use_container_width=True)
    if analyze_clicked:
        if not uploaded_file:
            st.error("Please upload a resume file.")
            return
        if not job_description.strip():
            st.error("Please enter a job description.")
            return

        with st.spinner("Extracting and analyzing resume..."):
            try:
                resume_text = extract_resume_text(uploaded_file)
                if not resume_text.strip():
                    st.error("Could not extract text from file.")
                    return
                result = analyze_resume_with_ai(resume_text, job_description)
                st.session_state.analysis_result = result
                save_analysis_history(int(user.get("id") or 0), result)
                st.session_state.bot_open = True
                st.session_state.dashboard_view = "home"
                st.rerun()
            except Exception as ex:
                st.error(f"Analysis failed: {ex}")
                return

    if uploaded_file:
        with st.expander("Preview extracted resume text"):
            try:
                preview_text = extract_resume_text(uploaded_file)
                trimmed = preview_text[:2200]
                st.text(trimmed + ("..." if len(preview_text) > 2200 else ""))
            except Exception as ex:
                st.warning(f"Preview unavailable: {ex}")

    if st.session_state.analysis_result:
        st.markdown("### Analysis Result")
        render_analysis_card(st.session_state.analysis_result)
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

    render_home_dashboard(user)
    render_zoswi_widget()


def main() -> None:
    st.set_page_config(page_title="Resume AI Checker", layout="wide", initial_sidebar_state="expanded")
    init_db()
    init_state()
    sync_promo_codes_from_secrets()
    try_restore_user_from_cookie()
    render_auth_cookie_sync()

    if st.session_state.user is None:
        render_auth_screen()
        return
    render_main_screen()


if __name__ == "__main__":
    main()
