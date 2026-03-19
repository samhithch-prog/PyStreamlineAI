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
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from functools import lru_cache
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import pdfplumber
import streamlit as st
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI as ZoSwiAIChat, OpenAIEmbeddings as ZoSwiAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from openai import OpenAI as ZoSwiAIClient
from src.controller.app_controller import run_app_runtime
from src.dto.auth_dto import PasswordResetInputDTO
from src.dto.runtime_dto import AppRuntimeHandlersDTO, PageConfigDTO
from src.repository.auth_repository import AuthRepository
from src.service.auth_service import AuthService, AuthServiceDependencies
from src.ui.auth_view import render_password_policy_checklist
from src.ui.styles import render_app_styles as render_ui_styles

try:
    import jwt as pyjwt
except Exception:
    pyjwt = None

try:
    import psycopg
except Exception:
    psycopg = None

try:
    from psycopg_pool import ConnectionPool as PsycopgConnectionPool
except Exception:
    PsycopgConnectionPool = None

LOGO_IMAGE_PATH = os.path.join("assets", "logo.png")
BROWSER_ICON_PATH = os.path.join("assets", "logo_icon.png")
BOT_WELCOME_MESSAGE = "I am ZoSwi. Ask me about your Resume and JD analysis."
BOT_LAUNCHER_ICON = "\U0001F916"
BOT_ASSISTANT_AVATAR = "\U0001F916"
USER_AVATAR = "\U0001F9D1"
ZOSWI_ASSISTANT_SCOPE_ONLY_MESSAGE = (
    "I can only help with resume, JD, ATS, and interview-prep guidance. "
    "Share your resume/JD question."
)
ZOSWI_ASSISTANT_NO_CODE_MESSAGE = (
    "I cannot provide code, scripts, or non-career content. "
    "I can help with resume, JD, ATS, and interview-prep guidance."
)
ZOSWI_ASSISTANT_EMERGENCY_MESSAGE = (
    "This sounds like a health or safety emergency. Contact emergency services now "
    "(call 911 in the U.S.) or your local emergency number immediately."
)
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
RUNTIME_BOOTSTRAP_VERSION = 2
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
AI_WORKSPACE_FILE_TYPES = [
    "txt",
    "md",
    "pdf",
    "docx",
    "png",
    "jpg",
    "jpeg",
    "webp",
    "bmp",
    "tiff",
    "py",
    "js",
    "ts",
    "java",
    "go",
    "cpp",
    "c",
    "cs",
    "json",
    "yaml",
    "yml",
    "xml",
    "html",
    "css",
    "sql",
    "sh",
    "bat",
    "ps1",
    "csv",
    "log",
]
AI_WORKSPACE_FILE_MAX_CHARS = 12000
IMAGE_TOOL_UPLOAD_TYPES = ["png", "jpg", "jpeg", "webp", "bmp", "tiff"]
IMAGE_TOOL_TARGET_FORMATS = ["PNG", "JPEG", "WEBP"]
IMAGE_TOOL_GENERATE_SIZES = ["1024x1024", "1536x1024", "1024x1536"]
IMAGE_TOOL_STYLE_NOTES = {
    "Professional": "clean professional composition with natural lighting",
    "Photorealistic": "highly detailed photorealistic render",
    "Illustration": "modern digital illustration with clean edges",
    "Minimal": "minimal style with clear negative space and balanced layout",
}
AI_WORKSPACE_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}
AI_WORKSPACE_ADULT_BLOCK_MESSAGE = (
    "I can’t help with 18+ or explicit sexual content. "
    "I can help with career, coding, interview prep, and professional tasks."
)
ZOSWI_LIVE_WORKSPACE_NAME = "ZoSwi Live Workspace"
ZOSWI_INTERVIEW_APP_URL_DEFAULT = "http://127.0.0.1:3000/interview"
ZOSWI_BLOCKED_APP_NAME_PATTERN = re.compile(
    r"(?i)\b(?:"
    r"chat\s*gpt|chatgpt|claude|perplexity|"
    r"github\s+copilot|microsoft\s+copilot|copilot|"
    r"gemini|bard|deepseek|llama|mistral|grok|cursor"
    r")\b"
)
ZOSWI_BLOCKED_EXTERNAL_APP_PATTERN = re.compile(
    r"(?i)\b(?:"
    r"photoshop|adobe\s+photoshop|gimp|picsart|canva|figma|"
    r"midjourney|stable\s+diffusion|dall[\s\-]?e|"
    r"lightroom|premiere(?:\s+pro)?|after\s+effects|capcut|krita"
    r")\b"
)
ZOSWI_STREAM_SANITIZE_TAIL_CHARS = 96
ZOSWI_BUILDER_NAME_KEY = "ZOSWI_BUILDER_NAME"
ZOSWI_SUCCESS_MOTIVATION_QUOTES = [
    "The future depends on what you do today. - Mahatma Gandhi",
    "Success is not final, failure is not fatal: it is the courage to continue that counts. - Winston Churchill",
    "Do the best you can until you know better. Then when you know better, do better. - Maya Angelou",
    "If you are not willing to risk the usual, you will have to settle for the ordinary. - Jim Rohn",
    "The way to get started is to quit talking and begin doing. - Walt Disney",
    "It always seems impossible until it is done. - Nelson Mandela",
    "Do not watch the clock; do what it does. Keep going. - Sam Levenson",
    "The only way to do great work is to love what you do. - Steve Jobs",
    "Believe you can and you are halfway there. - Theodore Roosevelt",
    "Opportunities do not happen. You create them. - Chris Grosser",
    "I have not failed. I have just found 10000 ways that will not work. - Thomas Edison",
    "Dream big and dare to fail. - Norman Vaughan",
    "You miss 100 percent of the shots you do not take. - Wayne Gretzky",
    "Whether you think you can or you think you cannot, you are right. - Henry Ford",
    "Try not to become a person of success, but rather a person of value. - Albert Einstein",
    "The successful warrior is the average person with laser-like focus. - Bruce Lee",
    "A person who never made a mistake never tried anything new. - Albert Einstein",
    "Hardships often prepare ordinary people for an extraordinary destiny. - C.S. Lewis",
    "Act as if what you do makes a difference. It does. - William James",
    "Quality means doing it right when no one is looking. - Henry Ford",
    "The secret of getting ahead is getting started. - Mark Twain",
    "Small deeds done are better than great deeds planned. - Peter Marshall",
    "What you do today can improve all your tomorrows. - Ralph Marston",
    "Success usually comes to those who are too busy to be looking for it. - Henry David Thoreau",
    "There are no shortcuts to any place worth going. - Beverly Sills",
    "The only limit to our realization of tomorrow is our doubts of today. - Franklin D. Roosevelt",
    "Do one thing every day that scares you. - Eleanor Roosevelt",
    "The harder I work, the luckier I get. - Samuel Goldwyn",
    "Do not wait to strike till the iron is hot; make it hot by striking. - William Butler Yeats",
    "Discipline is choosing between what you want now and what you want most. - Abraham Lincoln",
    "Perseverance is not a long race; it is many short races one after another. - Walter Elliot",
    "You are never too old to set another goal or to dream a new dream. - C.S. Lewis",
    "Success is the sum of small efforts, repeated day in and day out. - Robert Collier",
    "Keep your face always toward the sunshine and shadows will fall behind you. - Walt Whitman",
    "If you can dream it, you can do it. - Walt Disney",
    "Go as far as you can see; when you get there, you will be able to see further. - Thomas Carlyle",
    "Motivation gets you going, but discipline keeps you growing. - John C. Maxwell",
    "Without hustle, talent will only carry you so far. - Gary Vaynerchuk",
    "Success is liking yourself, liking what you do, and liking how you do it. - Maya Angelou",
    "The best way to predict the future is to create it. - Peter Drucker",
    "If opportunity does not knock, build a door. - Milton Berle",
    "Either you run the day or the day runs you. - Jim Rohn",
    "Great things are done by a series of small things brought together. - Vincent van Gogh",
    "The difference between ordinary and extraordinary is that little extra. - Jimmy Johnson",
    "Success is where preparation and opportunity meet. - Bobby Unser",
    "Do not be pushed by your problems. Be led by your dreams. - Ralph Waldo Emerson",
    "Do what you can, with what you have, where you are. - Theodore Roosevelt",
    "Courage is grace under pressure. - Ernest Hemingway",
    "When something is important enough, you do it even if the odds are not in your favor. - Elon Musk",
    "The man who moves a mountain begins by carrying away small stones. - Confucius",
    "Ambition is the path to success. Persistence is the vehicle you arrive in. - Bill Bradley",
    "The best revenge is massive success. - Frank Sinatra",
    "Fall seven times, stand up eight. - Japanese Proverb",
    "Do not let what you cannot do interfere with what you can do. - John Wooden",
    "Energy and persistence conquer all things. - Benjamin Franklin",
    "Well done is better than well said. - Benjamin Franklin",
    "Success is not in what you have, but who you are. - Bo Bennett",
    "It does not matter how slowly you go as long as you do not stop. - Confucius",
    "Everything you have ever wanted is on the other side of fear. - George Addair",
    "You become what you believe. - Oprah Winfrey",
    "Never bend your head. Hold it high. Look the world straight in the eye. - Helen Keller",
    "The journey of a thousand miles begins with one step. - Lao Tzu",
    "Do what you feel in your heart to be right, for you will be criticized anyway. - Eleanor Roosevelt",
    "Start where you are. Use what you have. Do what you can. - Arthur Ashe",
    "Your time is limited, so do not waste it living someone else's life. - Steve Jobs",
    "Today a reader, tomorrow a leader. - Margaret Fuller",
    "The expert in anything was once a beginner. - Helen Hayes",
    "The only place where success comes before work is in the dictionary. - Vidal Sassoon",
    "A goal properly set is halfway reached. - Zig Ziglar",
    "You do not have to be great to start, but you have to start to be great. - Zig Ziglar",
    "What lies behind us and what lies before us are tiny matters compared to what lies within us. - Ralph Waldo Emerson",
    "Action is the foundational key to all success. - Pablo Picasso",
    "Build your own dreams, or someone else will hire you to build theirs. - Farrah Gray",
    "I never dreamed about success. I worked for it. - Estee Lauder",
    "Be so good they cannot ignore you. - Steve Martin",
    "Do not count the days, make the days count. - Muhammad Ali",
    "It is never too late to be what you might have been. - George Eliot",
    "Success is walking from failure to failure with no loss of enthusiasm. - Winston Churchill",
    "Everything should be made as simple as possible, but not simpler. - Albert Einstein",
    "You cannot cross the sea merely by standing and staring at the water. - Rabindranath Tagore",
    "If people are doubting how far you can go, go so far that you cannot hear them anymore. - Michele Ruiz",
    "The best preparation for tomorrow is doing your best today. - H. Jackson Brown Jr.",
    "A winner is a dreamer who never gives up. - Nelson Mandela",
    "The only impossible journey is the one you never begin. - Tony Robbins",
    "Do not limit your challenges. Challenge your limits. - Jerry Dunn",
    "If you want to achieve greatness stop asking for permission. - Eddie Colla",
    "Failure is simply the opportunity to begin again, this time more intelligently. - Henry Ford",
    "Success is not for the lazy. - Sofia Vergara",
    "Success does not come from what you do occasionally. It comes from what you do consistently. - Marie Forleo",
    "Keep your eyes on the stars, and your feet on the ground. - Theodore Roosevelt",
    "A river cuts through rock not because of its power but because of its persistence. - James N. Watkins",
    "Learning never exhausts the mind. - Leonardo da Vinci",
    "Do not let yesterday take up too much of today. - Will Rogers",
    "Work hard in silence, let success make the noise. - Frank Ocean",
    "Where focus goes, energy flows. - Tony Robbins",
    "Progress, not perfection. - Marie Forleo",
    "The pain you feel today will be the strength you feel tomorrow. - Arnold Schwarzenegger",
    "If you get tired, learn to rest, not to quit. - Banksy",
    "Success is a journey, not a destination. - Arthur Ashe",
    "Turn your wounds into wisdom. - Oprah Winfrey",
]
ZOSWI_GLOBAL_MUSIC_TRACKS = [
    {"name": "Focus Flow", "url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3"},
    {"name": "Deep Work", "url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3"},
    {"name": "Calm Build", "url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3"},
    {"name": "Night Sprint", "url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-4.mp3"},
]
ZOSWI_MUSIC_SEARCH_TIMEOUT_SECONDS = 8
ZOSWI_AUDIUS_BASE_URL = "https://api.audius.co"
ZOSWI_AUDIUS_APP_NAME = "ZoSwi"
ZOSWI_MUSIC_FEATURE_FLAG_KEY = "ZOSWI_MUSIC_BAR_ENABLED"
ZOSWI_FEATURE_CAREERS_ENABLED_KEY = "ZOSWI_FEATURE_CAREERS_ENABLED"
ZOSWI_FEATURE_LIVE_WORKSPACE_ENABLED_KEY = "ZOSWI_FEATURE_LIVE_WORKSPACE_ENABLED"
ZOSWI_FEATURE_IMMIGRATION_UPDATES_ENABLED_KEY = "ZOSWI_FEATURE_IMMIGRATION_UPDATES_ENABLED"
ZOSWI_FEATURE_AI_CODING_ROOM_ENABLED_KEY = "ZOSWI_FEATURE_AI_CODING_ROOM_ENABLED"
ZOSWI_FEATURE_LIVE_AI_INTERVIEW_ENABLED_KEY = "ZOSWI_FEATURE_LIVE_AI_INTERVIEW_ENABLED"
ZOSWI_DASHBOARD_FEATURE_FLAGS: dict[str, tuple[str, str]] = {
    "careers": (ZOSWI_FEATURE_CAREERS_ENABLED_KEY, "careers_enabled"),
    "ai_workspace": (ZOSWI_FEATURE_LIVE_WORKSPACE_ENABLED_KEY, "live_workspace_enabled"),
    "immigration_updates": (ZOSWI_FEATURE_IMMIGRATION_UPDATES_ENABLED_KEY, "immigration_updates_enabled"),
    "coding_room": (ZOSWI_FEATURE_AI_CODING_ROOM_ENABLED_KEY, "ai_coding_room_enabled"),
    "live_interview": (ZOSWI_FEATURE_LIVE_AI_INTERVIEW_ENABLED_KEY, "live_ai_interview_enabled"),
}
ZOSWI_PROD_FULL_ACCESS_ENTITLEMENT_KEY = "ZOSWI_PROD_FULL_ACCESS_ENTITLEMENT"
ZOSWI_PROD_FULL_ACCESS_ENTITLEMENT_DEFAULT = "Zoswi Entitlement"
ZOSWI_PRODUCTION_ENV_NAMES = {"prod", "production", "prd", "live"}
JOB_SEARCH_MAX_RESULTS_DEFAULT = 5
JOB_SEARCH_MAX_RESULTS_LIMIT = 15
JOB_SEARCH_FETCH_CACHE_TTL_SECONDS = 300
JOB_SEARCH_API_TIMEOUT_SECONDS = 12
JOB_SEARCH_SCORING_MAX_WORKERS = 4
JOB_SEARCH_MAX_AI_EVALUATIONS = 8
JOB_SEARCH_MIN_RESUME_MATCH_STRICT = 48
JOB_SEARCH_MIN_ROLE_RELEVANCE_STRICT = 45
JOB_SEARCH_MIN_RESUME_MATCH_RELAXED = 38
JOB_SEARCH_MIN_ROLE_RELEVANCE_RELAXED = 30
JOB_SEARCH_POSTED_WITHIN_OPTIONS: list[tuple[str, int]] = [
    ("Anytime", 0),
    ("Past 24 hours", 1),
    ("Past 3 days", 3),
    ("Past 7 days", 7),
    ("Past 14 days", 14),
    ("Past 30 days", 30),
]
JOB_SEARCH_PROVIDER_OPTIONS = [
    "Adzuna",
    "Remotive",
    "Jooble",
    "USAJobs",
]
JOB_SEARCH_VISA_STATUSES = [
    "US Citizen / Green Card",
    "H-1B",
    "F-1 OPT / CPT",
    "L-1",
    "TN",
    "Other visa status",
]
JOB_POSITION_FILTER_OPTIONS = [
    "Full-Time",
    "Contract",
    "W2",
    "C2C",
    "Part-Time",
]
AGENTIVE_JOB_ACTION_TOKENS = (
    "find",
    "search",
    "show",
    "match",
    "recommend",
    "shortlist",
    "apply",
    "check",
    "list",
)
AGENTIVE_JOB_OBJECT_TOKENS = (
    "job",
    "jobs",
    "role",
    "roles",
    "opening",
    "openings",
    "position",
    "positions",
)
AGENTIVE_WORK_AUTH_TOKENS = (
    "sponsorship",
    "visa",
    "h1b",
    "h-1b",
    "opt",
    "cpt",
    "w2",
    "c2c",
    "full-time",
    "full time",
    "contract",
)
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
    def __init__(self, raw_connection: Any, backend: str, release_callback: Any = None) -> None:
        self._raw_connection = raw_connection
        self.backend = backend
        self._row_factory: Any = None
        self._release_callback = release_callback
        self._closed = False

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
        if self._closed:
            return
        self._closed = True
        if callable(self._release_callback):
            try:
                self._release_callback(self._raw_connection)
                return
            except Exception:
                pass
        self._raw_connection.close()


def _normalize_database_url(raw_url: str) -> str:
    cleaned = str(raw_url or "").strip()
    if not cleaned:
        return ""
    parsed = urlsplit(cleaned)
    if parsed.scheme not in {"postgres", "postgresql"}:
        return cleaned
    hostname = str(parsed.hostname or "").strip().lower()
    if "supabase.com" not in hostname:
        return cleaned
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    has_sslmode = any(str(key or "").strip().lower() == "sslmode" for key, _ in query_pairs)
    if has_sslmode:
        return cleaned
    query_pairs.append(("sslmode", "require"))
    normalized_query = urlencode(query_pairs, doseq=True)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, normalized_query, parsed.fragment))


def get_database_url() -> str:
    env_url = _normalize_database_url(os.getenv("DATABASE_URL", ""))
    if env_url:
        return env_url
    try:
        db_cfg = st.secrets.get("database")
        if hasattr(db_cfg, "get"):
            return _normalize_database_url(str(db_cfg.get("url", "")))
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


def get_zoswi_builder_name() -> str:
    configured_value = get_config_value(
        ZOSWI_BUILDER_NAME_KEY,
        "branding",
        "builder_name",
        "",
    )
    if not configured_value:
        configured_value = get_db_setting_value(ZOSWI_BUILDER_NAME_KEY)
    cleaned = re.sub(r"\s+", " ", str(configured_value or "").strip())
    return cleaned[:120]


def normalize_interview_requirement_type(raw_value: str) -> str:
    cleaned = str(raw_value or "").strip().lower().replace(" ", "_").replace("-", "_")
    mapping = {
        "mixed": "mixed",
        "hybrid": "mixed",
        "technical": "technical",
        "tech": "technical",
        "behavioral": "behavioral",
        "behavioural": "behavioral",
        "behavior": "behavioral",
    }
    return mapping.get(cleaned, "mixed")


def normalize_interview_auth_role(raw_value: str) -> str:
    cleaned = str(raw_value or "").strip().lower()
    if cleaned in {"admin", "administrator"}:
        return "admin"
    if cleaned in {"recruiter", "hiring_manager", "hiring manager"}:
        return "recruiter"
    return "candidate"


def get_interview_launch_secret() -> str:
    candidates = [
        ("STREAMLIT_LAUNCH_SECRET", "", "", ""),
        ("ZOSWI_INTERVIEW_LAUNCH_SECRET", "", "", ""),
        ("STREAMLIT_LAUNCH_SECRET", "interview", "launch_secret", ""),
        ("ZOSWI_INTERVIEW_LAUNCH_SECRET", "interview", "launch_secret", ""),
    ]
    for env_key, section, secret_key, default in candidates:
        value = get_config_value(env_key, section, secret_key, default).strip()
        if value:
            return value
    return ""


def get_interview_launch_issuer() -> str:
    candidates = [
        ("STREAMLIT_LAUNCH_ISSUER", "", "", ""),
        ("ZOSWI_INTERVIEW_LAUNCH_ISSUER", "", "", ""),
        ("STREAMLIT_LAUNCH_ISSUER", "interview", "launch_issuer", ""),
        ("ZOSWI_INTERVIEW_LAUNCH_ISSUER", "interview", "launch_issuer", ""),
    ]
    for env_key, section, secret_key, default in candidates:
        value = get_config_value(env_key, section, secret_key, default).strip()
        if value:
            return value
    return "zoswi-streamlit"


def get_interview_launch_audience() -> str:
    candidates = [
        ("STREAMLIT_LAUNCH_AUDIENCE", "", "", ""),
        ("ZOSWI_INTERVIEW_LAUNCH_AUDIENCE", "", "", ""),
        ("STREAMLIT_LAUNCH_AUDIENCE", "interview", "launch_audience", ""),
        ("ZOSWI_INTERVIEW_LAUNCH_AUDIENCE", "interview", "launch_audience", ""),
    ]
    for env_key, section, secret_key, default in candidates:
        value = get_config_value(env_key, section, secret_key, default).strip()
        if value:
            return value
    return "zoswi-interview-launch"


def get_interview_jwt_algorithm() -> str:
    return (get_config_value("JWT_ALGORITHM", "interview", "jwt_algorithm", "HS256") or "HS256").strip()


def get_interview_launch_ttl_seconds() -> int:
    configured = ""
    candidates = [
        ("STREAMLIT_LAUNCH_TOKEN_TTL_SECONDS", "", "", ""),
        ("ZOSWI_INTERVIEW_LAUNCH_TOKEN_TTL_SECONDS", "", "", ""),
        ("STREAMLIT_LAUNCH_TOKEN_TTL_SECONDS", "interview", "launch_token_ttl_seconds", ""),
        ("ZOSWI_INTERVIEW_LAUNCH_TOKEN_TTL_SECONDS", "interview", "launch_token_ttl_seconds", ""),
    ]
    for env_key, section, secret_key, default in candidates:
        value = get_config_value(env_key, section, secret_key, default).strip()
        if value:
            configured = value
            break
    if not configured:
        configured = "60"
    return parse_int(
        configured,
        60,
        15,
        300,
    )


def build_streamlit_interview_launch_token(user: dict[str, Any]) -> str:
    if pyjwt is None:
        return ""
    launch_secret = get_interview_launch_secret()
    if not launch_secret:
        return ""
    user_id = str(user.get("id", "")).strip()
    user_email = str(user.get("email", "")).strip().lower()
    subject = user_id or user_email
    if not subject:
        return ""
    now = datetime.now(timezone.utc)
    exp = now + timedelta(seconds=get_interview_launch_ttl_seconds())
    payload = {
        "sub": subject,
        "email": user_email,
        "role": normalize_interview_auth_role(str(user.get("role", "")).strip()),
        "org_id": str(user.get("org_id", "")).strip() or None,
        "iss": get_interview_launch_issuer(),
        "aud": get_interview_launch_audience(),
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "typ": "streamlit_launch",
        "jti": secrets.token_hex(16),
        "source": "streamlit",
    }
    try:
        encoded = pyjwt.encode(payload, launch_secret, algorithm=get_interview_jwt_algorithm())
    except Exception:
        return ""
    return str(encoded or "").strip()


def get_zoswi_live_interview_base_url() -> str:
    configured = get_config_value(
        "ZOSWI_INTERVIEW_APP_URL",
        "interview",
        "app_url",
        "",
    )
    if not configured:
        runtime_origin = str(get_runtime_app_origin() or "").lower()
        is_local_runtime = runtime_origin.startswith("http://localhost") or runtime_origin.startswith(
            "http://127.0.0.1"
        )
        if is_local_runtime:
            configured = ZOSWI_INTERVIEW_APP_URL_DEFAULT
    parsed = urlsplit(configured)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    path = str(parsed.path or "").strip()
    if not path:
        path = "/"
    # Streamlit should land on frontend home first; keep explicit custom paths.
    if path.rstrip("/") == "/interview":
        path = "/"
    base = f"{parsed.scheme}://{parsed.netloc}{path}"
    if parsed.query:
        base = f"{base}?{parsed.query}"
    return base


def build_zoswi_live_interview_launch_url(
    candidate_name: str,
    role: str,
    requirement_type: str,
    user: dict[str, Any] | None = None,
) -> str:
    base_url = get_zoswi_live_interview_base_url()
    if not base_url:
        return ""
    cleaned_name = str(candidate_name or "").strip()[:160]
    cleaned_role = str(role or "").strip()[:160]
    if not cleaned_name or not cleaned_role:
        return ""
    normalized_type = normalize_interview_requirement_type(requirement_type)
    query_params = {
        "candidate": cleaned_name,
        "role": cleaned_role,
        "type": normalized_type,
        "source": "streamlit",
    }
    launch_token = build_streamlit_interview_launch_token(user or {})
    if launch_token:
        query_params["launch_token"] = launch_token
    query = urlencode(query_params)
    joiner = "&" if "?" in base_url else "?"
    return f"{base_url}{joiner}{query}"


def get_db_setting_value(setting_key: str) -> str:
    cleaned_key = str(setting_key or "").strip()
    if not cleaned_key:
        return ""
    cached_settings = _cached_app_settings_map()
    if cleaned_key in cached_settings:
        return str(cached_settings.get(cleaned_key, "") or "").strip()
    if cached_settings:
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


@st.cache_data(ttl=20, show_spinner=False)
def _cached_app_settings_map() -> dict[str, str]:
    conn = db_connect()
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT setting_key, setting_value
            FROM app_settings
            """
        ).fetchall()
    except Exception:
        return {}
    finally:
        conn.close()

    settings: dict[str, str] = {}
    for row in rows:
        if isinstance(row, dict):
            key = str(row.get("setting_key", "") or "").strip()
            value = str(row.get("setting_value", "") or "").strip()
        else:
            key = str(row[0] if row and len(row) > 0 else "").strip()
            value = str(row[1] if row and len(row) > 1 else "").strip()
        if key:
            settings[key] = value
    return settings


def clear_cached_app_settings() -> None:
    try:
        _cached_app_settings_map.clear()
    except Exception:
        pass


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


@lru_cache(maxsize=1)
def get_postgres_pool() -> Any:
    if PsycopgConnectionPool is None or psycopg is None:
        return None
    db_url = get_database_url()
    if not db_url:
        return None
    try:
        return PsycopgConnectionPool(conninfo=db_url, min_size=1, max_size=8, timeout=12)
    except Exception:
        return None


def db_connect() -> DBConnection:
    db_url = get_database_url()
    if not db_url:
        raise RuntimeError("DATABASE_URL is required. Configure PostgreSQL in env or Streamlit secrets.")
    if not using_postgres():
        raise RuntimeError("DATABASE_URL must use a PostgreSQL URL (postgresql:// or postgres://).")
    if psycopg is None:
        raise RuntimeError("PostgreSQL selected but psycopg is not installed.")
    pool = get_postgres_pool()
    if pool is not None:
        try:
            raw_conn = pool.getconn()
            return DBConnection(raw_conn, "postgres", release_callback=pool.putconn)
        except Exception:
            pass
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
    current_view = str(st.session_state.get("dashboard_view", "home")).strip().lower()
    show_product_of = current_view == "ai_workspace"
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
        .st-key-top_logo .top-logo-product-of {
            color: #9ca3af;
            font-size: 0.62rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            margin: 0 0 0.16rem 0.16rem;
            animation: topLogoProductBlink 1.2s ease-in-out infinite;
        }
        @keyframes topLogoProductBlink {
            0% { opacity: 0.38; }
            50% { opacity: 1; }
            100% { opacity: 0.38; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    with st.container(key="top_logo"):
        if show_product_of:
            st.markdown('<div class="top-logo-product-of">Product of</div>', unsafe_allow_html=True)
        st.image(LOGO_IMAGE_PATH, width=190)


def is_global_music_enabled() -> bool:
    db_value = get_db_setting_value(ZOSWI_MUSIC_FEATURE_FLAG_KEY)
    if db_value:
        return parse_bool(db_value, default=False)
    config_value = get_config_value(
        ZOSWI_MUSIC_FEATURE_FLAG_KEY,
        "music",
        "enabled",
        "false",
    )
    return parse_bool(config_value, default=False)


def normalize_entitlement_token(raw_value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", str(raw_value or "").strip().lower())
    return cleaned.strip("_")


def normalize_runtime_environment(raw_value: str) -> str:
    cleaned = normalize_entitlement_token(raw_value)
    mapping = {
        "production": "prod",
        "prd": "prod",
        "live": "prod",
        "development": "dev",
        "local": "dev",
        "stage": "staging",
    }
    return mapping.get(cleaned, cleaned)


def get_runtime_environment() -> str:
    configured = get_config_value("APP_ENV", "app", "environment", "")
    if not configured:
        configured = str(os.getenv("ENVIRONMENT", "") or os.getenv("STAGE", "") or os.getenv("DEPLOY_ENV", "")).strip()
    return normalize_runtime_environment(configured)


def is_production_environment() -> bool:
    env_name = normalize_runtime_environment(get_runtime_environment())
    return env_name in ZOSWI_PRODUCTION_ENV_NAMES


def is_local_or_dev_environment() -> bool:
    runtime_env = normalize_runtime_environment(get_runtime_environment())
    return runtime_env in {"", "dev"}


def get_prod_full_access_entitlement_token() -> str:
    configured = get_config_value(
        ZOSWI_PROD_FULL_ACCESS_ENTITLEMENT_KEY,
        "entitlements",
        "prod_full_access_entitlement",
        ZOSWI_PROD_FULL_ACCESS_ENTITLEMENT_DEFAULT,
    )
    normalized = normalize_entitlement_token(configured)
    if normalized:
        return normalized
    return normalize_entitlement_token(ZOSWI_PROD_FULL_ACCESS_ENTITLEMENT_DEFAULT)


def entitlement_environment_matches_runtime(raw_environment: str, runtime_environment: str) -> bool:
    normalized = normalize_runtime_environment(raw_environment)
    if normalized in {"", "all", "global", "any", "*"}:
        return True
    if not runtime_environment:
        return False
    return normalized == runtime_environment


def get_user_entitlement_tokens(user_id: int) -> set[str]:
    safe_user_id = int(user_id or 0)
    if safe_user_id <= 0:
        return set()
    runtime_environment = get_runtime_environment()
    conn = db_connect()
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT entitlement_name, environment
            FROM user_entitlements
            WHERE user_id = ? AND is_active = 1
            """,
            (safe_user_id,),
        ).fetchall()
    except Exception:
        return set()
    finally:
        conn.close()

    tokens: set[str] = set()
    for row in rows:
        if isinstance(row, dict):
            raw_name = str(row.get("entitlement_name", "") or "")
            raw_env = str(row.get("environment", "") or "")
        else:
            raw_name = str(row[0] if row and len(row) > 0 else "")
            raw_env = str(row[1] if row and len(row) > 1 else "")
        if not entitlement_environment_matches_runtime(raw_env, runtime_environment):
            continue
        normalized = normalize_entitlement_token(raw_name)
        if normalized:
            tokens.add(normalized)
    return tokens


def get_user_entitlement_tokens_from_user(user: dict[str, Any] | None) -> set[str]:
    if not isinstance(user, dict):
        return set()

    tokens: set[str] = set()
    has_embedded_entitlements = "entitlements" in user
    raw_entitlements = user.get("entitlements", [])
    if isinstance(raw_entitlements, str):
        raw_entitlements = [raw_entitlements]
    if isinstance(raw_entitlements, (list, tuple, set)):
        for item in raw_entitlements:
            normalized = normalize_entitlement_token(str(item or ""))
            if normalized:
                tokens.add(normalized)
    if has_embedded_entitlements:
        return tokens

    return get_user_entitlement_tokens(int(user.get("id") or 0))


def enrich_user_with_entitlements(user: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(user, dict):
        return user
    enriched = dict(user)
    cleaned_email = str(enriched.get("email", "")).strip().lower()
    if cleaned_email:
        enriched["email"] = cleaned_email
    enriched["role"] = normalize_user_role_for_login_email(
        str(enriched.get("role", "")),
        cleaned_email,
        assign_default=True,
    )
    enriched["entitlements"] = sorted(get_user_entitlement_tokens(int(enriched.get("id") or 0)))
    return enriched


def has_prod_full_access_entitlement(user: dict[str, Any] | None = None) -> bool:
    if not is_production_environment():
        return False
    required = get_prod_full_access_entitlement_token()
    if not required:
        return False
    candidate = user if isinstance(user, dict) else st.session_state.get("user")
    return required in get_user_entitlement_tokens_from_user(candidate if isinstance(candidate, dict) else None)


@st.cache_data(ttl=20, show_spinner=False)
def get_dashboard_feature_flags() -> dict[str, bool]:
    flags: dict[str, bool] = {}
    for view_name, (setting_key, secret_key) in ZOSWI_DASHBOARD_FEATURE_FLAGS.items():
        db_value = get_db_setting_value(setting_key)
        if db_value:
            flags[view_name] = parse_bool(db_value, default=False)
            continue
        config_value = get_config_value(
            setting_key,
            "features",
            secret_key,
            "false",
        )
        flags[view_name] = parse_bool(config_value, default=False)
    return flags


def get_effective_dashboard_feature_flags(user: dict[str, Any] | None = None) -> dict[str, bool]:
    effective = dict(get_dashboard_feature_flags())
    if has_prod_full_access_entitlement(user):
        for view_name in ZOSWI_DASHBOARD_FEATURE_FLAGS:
            effective[view_name] = True
    return effective


def is_dashboard_module_enabled(view_name: str) -> bool:
    normalized = normalize_dashboard_view(view_name)
    if not normalized:
        normalized = str(view_name or "").strip().lower().replace(" ", "_").replace("-", "_")
    if normalized in {"home", "chats", "scores"}:
        return True
    return bool(get_effective_dashboard_feature_flags().get(normalized, True))


def build_dashboard_module_status_summary() -> str:
    flags = get_effective_dashboard_feature_flags(st.session_state.get("user"))
    labels = (
        ("Careers", "careers"),
        ("Live Workspace", "ai_workspace"),
        ("Immigration Updates", "immigration_updates"),
        ("AI Coding Room", "coding_room"),
        ("Live AI Interview", "live_interview"),
    )
    return ", ".join(
        f"{label}: {'enabled' if flags.get(key, False) else 'disabled'}"
        for label, key in labels
    )


def get_audius_request_headers() -> dict[str, str]:
    headers = {
        "User-Agent": "ZoSwi/1.0",
        "Accept": "application/json",
    }
    api_key = get_config_value("AUDIUS_API_KEY", "music", "audius_api_key")
    if api_key:
        headers["x-api-key"] = api_key
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


@lru_cache(maxsize=120)
def search_audius_full_tracks(query: str, limit: int = 8) -> tuple[tuple[str, str], ...]:
    cleaned_query = re.sub(r"\s+", " ", str(query or "").strip())
    if len(cleaned_query) < 2:
        return tuple()
    safe_limit = max(3, min(15, int(limit or 8)))
    params = urlencode(
        {
            "query": cleaned_query,
            "limit": safe_limit,
            "app_name": ZOSWI_AUDIUS_APP_NAME,
        }
    )
    request_url = f"{ZOSWI_AUDIUS_BASE_URL}/v1/tracks/search?{params}"
    request = Request(request_url, headers=get_audius_request_headers())
    try:
        with urlopen(request, timeout=ZOSWI_MUSIC_SEARCH_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8", errors="ignore")
    except Exception:
        return tuple()
    try:
        payload = json.loads(raw)
    except Exception:
        return tuple()
    entries = payload.get("data", []) if isinstance(payload, dict) else []
    if not isinstance(entries, list):
        return tuple()

    seen: set[str] = set()
    results: list[tuple[str, str]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        track_id = str(item.get("id", "")).strip()
        title = str(item.get("title", "")).strip()
        streamable = item.get("streamable")
        if streamable is False or not track_id or not title:
            continue
        user_obj = item.get("user", {})
        artist_name = ""
        if isinstance(user_obj, dict):
            artist_name = str(user_obj.get("name", "")).strip()
        title_lower = title.lower()
        artist_lower = artist_name.lower()
        label = title if artist_lower and artist_lower in title_lower else f"{title} - {artist_name}" if artist_name else title
        label = re.sub(r"\s+", " ", label).strip()
        if not label:
            continue
        stream_url = f"{ZOSWI_AUDIUS_BASE_URL}/v1/tracks/{track_id}/stream?app_name={ZOSWI_AUDIUS_APP_NAME}"
        dedupe_key = f"{label}|{track_id}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        results.append((label[:120], stream_url))
        if len(results) >= safe_limit:
            break
    return tuple(results)


@lru_cache(maxsize=120)
def search_itunes_song_previews(query: str, limit: int = 8) -> tuple[tuple[str, str], ...]:
    cleaned_query = re.sub(r"\s+", " ", str(query or "").strip())
    if len(cleaned_query) < 2:
        return tuple()
    safe_limit = max(3, min(15, int(limit or 8)))
    params = urlencode(
        {
            "term": cleaned_query,
            "media": "music",
            "entity": "song",
            "limit": safe_limit,
        }
    )
    request_url = f"https://itunes.apple.com/search?{params}"
    request = Request(
        request_url,
        headers={
            "User-Agent": "ZoSwi/1.0",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=ZOSWI_MUSIC_SEARCH_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8", errors="ignore")
    except Exception:
        return tuple()
    try:
        payload = json.loads(raw)
    except Exception:
        return tuple()
    entries = payload.get("results", []) if isinstance(payload, dict) else []
    if not isinstance(entries, list):
        return tuple()

    seen: set[str] = set()
    results: list[tuple[str, str]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        preview_url = str(item.get("previewUrl", "")).strip()
        track_name = str(item.get("trackName", "")).strip()
        artist_name = str(item.get("artistName", "")).strip()
        if not preview_url or not track_name:
            continue
        label = f"{track_name} - {artist_name}" if artist_name else track_name
        label = re.sub(r"\s+", " ", label).strip()
        if not label:
            continue
        dedupe_key = f"{label}|{preview_url}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        results.append((label[:120], preview_url))
        if len(results) >= safe_limit:
            break
    return tuple(results)


def render_global_music_bar() -> None:
    if not is_global_music_enabled():
        return
    if is_mobile_browser():
        return
    tracks = [item for item in ZOSWI_GLOBAL_MUSIC_TRACKS if isinstance(item, dict)]
    if not tracks:
        return
    labels = [str(item.get("name", "")).strip() for item in tracks if str(item.get("name", "")).strip()]
    if not labels:
        return
    track_map = {
        str(item.get("name", "")).strip(): str(item.get("url", "")).strip()
        for item in tracks
        if str(item.get("name", "")).strip() and str(item.get("url", "")).strip()
    }
    if not track_map:
        return

    default_track = labels[0]
    selected_track = str(st.session_state.get("global_music_track", default_track)).strip()
    if selected_track not in track_map:
        selected_track = default_track
    st.session_state.global_music_track = selected_track
    if "global_music_search_results" not in st.session_state:
        st.session_state.global_music_search_results = []
    if "global_music_search_status" not in st.session_state:
        st.session_state.global_music_search_status = ""

    with st.container(key="global_music_bar"):
        st.markdown('<div class="zoswi-music-title">ZoSwi Music</div>', unsafe_allow_html=True)
        with st.container(key="global_music_search_row"):
            query_col, search_col = st.columns([4.5, 1.5], gap="small")
            with query_col:
                with st.container(key="global_music_search_input"):
                    search_query = st.text_input(
                        "Search songs",
                        key="global_music_query",
                        placeholder="Search songs...",
                        label_visibility="collapsed",
                    )
            with search_col:
                with st.container(key="global_music_search_btn_wrap"):
                    search_clicked = st.button(
                        "Search",
                        key="global_music_search_btn",
                        use_container_width=True,
                    )

        if search_clicked:
            clean_query = re.sub(r"\s+", " ", str(search_query or "").strip())
            if len(clean_query) < 2:
                st.session_state.global_music_search_status = "Enter at least 2 characters to search."
                st.session_state.global_music_search_results = []
            else:
                audius_pairs = list(search_audius_full_tracks(clean_query, limit=10))
                if audius_pairs:
                    search_results = [{"name": f"{name} - Full", "url": url} for name, url in audius_pairs]
                    st.session_state.global_music_search_results = search_results
                    st.session_state.global_music_track = str(search_results[0]["name"])
                    st.session_state.global_music_search_status = f"Found {len(search_results)} full tracks."
                else:
                    preview_pairs = list(search_itunes_song_previews(clean_query, limit=10))
                    search_results = [{"name": f"{name} - Preview", "url": url} for name, url in preview_pairs]
                    st.session_state.global_music_search_results = search_results
                    if search_results:
                        st.session_state.global_music_track = str(search_results[0]["name"])
                        st.session_state.global_music_search_status = (
                            f"No free full tracks found. Showing {len(search_results)} preview tracks."
                        )
                    else:
                        st.session_state.global_music_search_status = "No tracks found for that search."

        search_results_state = st.session_state.get("global_music_search_results", [])
        search_tracks = (
            [item for item in search_results_state if isinstance(item, dict)]
            if isinstance(search_results_state, list)
            else []
        )
        active_tracks = search_tracks if search_tracks else tracks
        active_map = {
            str(item.get("name", "")).strip(): str(item.get("url", "")).strip()
            for item in active_tracks
            if str(item.get("name", "")).strip() and str(item.get("url", "")).strip()
        }
        if not active_map:
            active_map = track_map
        active_labels = list(active_map.keys())
        selected_active = str(st.session_state.get("global_music_track", active_labels[0])).strip()
        if selected_active not in active_map:
            selected_active = active_labels[0]
            st.session_state.global_music_track = selected_active

        chosen_track = st.selectbox(
            "Choose music",
            options=active_labels,
            key="global_music_track",
            label_visibility="collapsed",
        )
        status_text = str(st.session_state.get("global_music_search_status", "")).strip()
        if status_text:
            st.caption(status_text)

        chosen_url = active_map.get(str(chosen_track).strip(), active_map[active_labels[0]])
        st.audio(chosen_url, format="audio/mp3")
    st.components.v1.html(
        """
        <script>
        (function () {
            const hostDoc = (window.parent && window.parent.document) ? window.parent.document : window.document;
            if (!hostDoc) {
                return;
            }
            function alignMusicBarWithLogo() {
                const musicWrap = hostDoc.querySelector(".st-key-global_music_bar");
                if (!musicWrap) {
                    return;
                }
                const logoImg = hostDoc.querySelector(".st-key-top_logo img");
                const logoWrap = hostDoc.querySelector(".st-key-top_logo");
                const refRect = logoImg ? logoImg.getBoundingClientRect() : (logoWrap ? logoWrap.getBoundingClientRect() : null);
                if (!refRect) {
                    return;
                }
                const targetTop = Math.max(8, Math.round(refRect.top + 2));
                musicWrap.style.top = targetTop + "px";
            }
            let ticks = 0;
            const timer = setInterval(function () {
                alignMusicBarWithLogo();
                ticks += 1;
                if (ticks >= 20) {
                    clearInterval(timer);
                }
            }, 120);
            alignMusicBarWithLogo();
        })();
        </script>
        """,
        height=0,
    )


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


@st.cache_resource(show_spinner=False)
def _bootstrap_runtime_once(bootstrap_version: int) -> bool:
    _ = bootstrap_version
    init_db()
    sync_promo_codes_from_secrets()
    clear_cached_app_settings()
    return True


def bootstrap_runtime() -> None:
    _bootstrap_runtime_once(RUNTIME_BOOTSTRAP_VERSION)


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
            account_status TEXT NOT NULL DEFAULT 'active',
            auth_provider TEXT,
            auth_provider_user_id TEXT,
            timezone TEXT,
            locale TEXT,
            email_verified_at TEXT,
            last_login_at TEXT,
            onboarding_completed_at TEXT,
            terms_accepted_at TEXT,
            privacy_accepted_at TEXT,
            updated_at TEXT NOT NULL,
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
        CREATE TABLE IF NOT EXISTS job_search_history (
            id {id_pk_sql},
            user_id {fk_type} NOT NULL,
            source_profile TEXT NOT NULL DEFAULT 'Adzuna',
            role_query TEXT NOT NULL,
            preferred_location TEXT,
            visa_status TEXT,
            sponsorship_required INTEGER NOT NULL DEFAULT 0,
            result_count INTEGER NOT NULL DEFAULT 0,
            results_json TEXT,
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
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS user_entitlements (
            id {id_pk_sql},
            user_id {fk_type} NOT NULL,
            entitlement_name TEXT NOT NULL,
            environment TEXT NOT NULL DEFAULT 'all',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, entitlement_name, environment),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS immigration_updates (
            id {id_pk_sql},
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            source TEXT NOT NULL,
            link TEXT NOT NULL UNIQUE,
            visa_category TEXT NOT NULL,
            published_date TEXT NOT NULL,
            tags TEXT,
            original_text TEXT,
            content_hash TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    music_setting_now_iso = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO app_settings (setting_key, setting_value, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(setting_key) DO NOTHING
        """,
        (ZOSWI_MUSIC_FEATURE_FLAG_KEY, "false", music_setting_now_iso, music_setting_now_iso),
    )
    conn.execute(
        """
        INSERT INTO app_settings (setting_key, setting_value, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(setting_key) DO NOTHING
        """,
        ("IMMIGRATION_UPDATES_LAST_FETCH_AT", "", music_setting_now_iso, music_setting_now_iso),
    )
    for setting_key, _secret_key in ZOSWI_DASHBOARD_FEATURE_FLAGS.values():
        conn.execute(
            """
            INSERT INTO app_settings (setting_key, setting_value, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(setting_key) DO NOTHING
            """,
            (setting_key, "false", music_setting_now_iso, music_setting_now_iso),
        )
    if is_local_or_dev_environment():
        for setting_key, _secret_key in ZOSWI_DASHBOARD_FEATURE_FLAGS.values():
            conn.execute(
                """
                INSERT INTO app_settings (setting_key, setting_value, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(setting_key) DO UPDATE SET
                    setting_value = EXCLUDED.setting_value,
                    updated_at = EXCLUDED.updated_at
                """,
                (setting_key, "true", music_setting_now_iso, music_setting_now_iso),
            )
        conn.execute(
            """
            INSERT INTO app_settings (setting_key, setting_value, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(setting_key) DO UPDATE SET
                setting_value = EXCLUDED.setting_value,
                updated_at = EXCLUDED.updated_at
            """,
            (ZOSWI_MUSIC_FEATURE_FLAG_KEY, "false", music_setting_now_iso, music_setting_now_iso),
        )

    user_cols = get_table_columns(conn, "users")
    added_email_verified_col = False
    if "role_contact_email" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN role_contact_email TEXT")
    if "profile_data" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN profile_data TEXT")
    if "account_status" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN account_status TEXT")
        conn.execute("UPDATE users SET account_status = 'active' WHERE account_status IS NULL OR account_status = ''")
    if "auth_provider" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN auth_provider TEXT")
    if "auth_provider_user_id" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN auth_provider_user_id TEXT")
    if "timezone" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN timezone TEXT")
    if "locale" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN locale TEXT")
    if "email_verified_at" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN email_verified_at TEXT")
        added_email_verified_col = True
    if "last_login_at" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN last_login_at TEXT")
    if "onboarding_completed_at" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN onboarding_completed_at TEXT")
    if "terms_accepted_at" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN terms_accepted_at TEXT")
    if "privacy_accepted_at" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN privacy_accepted_at TEXT")
    if "updated_at" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN updated_at TEXT")
        conn.execute("UPDATE users SET updated_at = created_at WHERE updated_at IS NULL OR updated_at = ''")
    if added_email_verified_col:
        conn.execute("UPDATE users SET email_verified_at = created_at WHERE email_verified_at IS NULL")

    entitlement_cols = get_table_columns(conn, "user_entitlements")
    if "environment" not in entitlement_cols:
        conn.execute("ALTER TABLE user_entitlements ADD COLUMN environment TEXT")
        conn.execute(
            "UPDATE user_entitlements SET environment = 'all' WHERE environment IS NULL OR environment = ''"
        )
    if "is_active" not in entitlement_cols:
        conn.execute("ALTER TABLE user_entitlements ADD COLUMN is_active INTEGER")
        conn.execute("UPDATE user_entitlements SET is_active = 1 WHERE is_active IS NULL")
    if "created_at" not in entitlement_cols:
        conn.execute("ALTER TABLE user_entitlements ADD COLUMN created_at TEXT")
        conn.execute(
            "UPDATE user_entitlements SET created_at = ? WHERE created_at IS NULL OR created_at = ''",
            (music_setting_now_iso,),
        )
    if "updated_at" not in entitlement_cols:
        conn.execute("ALTER TABLE user_entitlements ADD COLUMN updated_at TEXT")
        conn.execute(
            "UPDATE user_entitlements SET updated_at = ? WHERE updated_at IS NULL OR updated_at = ''",
            (music_setting_now_iso,),
        )

    chat_cols = get_table_columns(conn, "chat_history")
    if "session_id" not in chat_cols:
        conn.execute(f"ALTER TABLE chat_history ADD COLUMN session_id {session_id_type}")
    job_search_cols = get_table_columns(conn, "job_search_history")
    if "source_profile" not in job_search_cols:
        conn.execute("ALTER TABLE job_search_history ADD COLUMN source_profile TEXT")
        conn.execute("UPDATE job_search_history SET source_profile = 'Adzuna' WHERE source_profile IS NULL")
    immigration_cols = get_table_columns(conn, "immigration_updates")
    if "summary" not in immigration_cols:
        conn.execute("ALTER TABLE immigration_updates ADD COLUMN summary TEXT")
        conn.execute("UPDATE immigration_updates SET summary = '' WHERE summary IS NULL")
    if "source" not in immigration_cols:
        conn.execute("ALTER TABLE immigration_updates ADD COLUMN source TEXT")
        conn.execute("UPDATE immigration_updates SET source = 'Unknown Source' WHERE source IS NULL")
    if "visa_category" not in immigration_cols:
        conn.execute("ALTER TABLE immigration_updates ADD COLUMN visa_category TEXT")
        conn.execute("UPDATE immigration_updates SET visa_category = 'General' WHERE visa_category IS NULL")
    if "published_date" not in immigration_cols:
        conn.execute("ALTER TABLE immigration_updates ADD COLUMN published_date TEXT")
        conn.execute("UPDATE immigration_updates SET published_date = created_at WHERE published_date IS NULL")
    if "tags" not in immigration_cols:
        conn.execute("ALTER TABLE immigration_updates ADD COLUMN tags TEXT")
    if "original_text" not in immigration_cols:
        conn.execute("ALTER TABLE immigration_updates ADD COLUMN original_text TEXT")
    if "content_hash" not in immigration_cols:
        conn.execute("ALTER TABLE immigration_updates ADD COLUMN content_hash TEXT")
    if "updated_at" not in immigration_cols:
        conn.execute("ALTER TABLE immigration_updates ADD COLUMN updated_at TEXT")
        conn.execute("UPDATE immigration_updates SET updated_at = created_at WHERE updated_at IS NULL OR updated_at = ''")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_analysis_history_user_id ON analysis_history(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_job_search_history_user_id ON job_search_history(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_job_search_history_created_at ON job_search_history(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_history_user_id ON chat_history(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_history_session_id ON chat_history(session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id ON chat_sessions(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated_at ON chat_sessions(updated_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires_at ON auth_sessions(expires_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_login_events_user_id ON user_login_events(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_login_events_login_at ON user_login_events(login_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_account_status ON users(account_status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_auth_provider_user_id ON users(auth_provider, auth_provider_user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_entitlements_user_id ON user_entitlements(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_entitlements_environment ON user_entitlements(environment)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_entitlements_name ON user_entitlements(entitlement_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_email_otp_events_user_id ON user_email_otp_events(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_email_otp_events_email ON user_email_otp_events(email)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_email_otp_events_expires_at ON user_email_otp_events(expires_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_signup_verification_requests_email ON signup_verification_requests(email)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_signup_verification_requests_expires_at ON signup_verification_requests(expires_at)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_immigration_updates_published_date ON immigration_updates(published_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_immigration_updates_visa_category ON immigration_updates(visa_category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_immigration_updates_source ON immigration_updates(source)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_immigration_updates_link ON immigration_updates(link)")
    if conn.backend == "postgres":
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_immigration_updates_fts
            ON immigration_updates
            USING GIN (to_tsvector('english', coalesce(title,'') || ' ' || coalesce(summary,'') || ' ' || coalesce(tags,'')))
            """
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
    clear_cached_app_settings()
    try:
        get_dashboard_feature_flags.clear()
    except Exception:
        pass
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


def get_support_inbox_email() -> str:
    explicit = get_config_value("SUPPORT_INBOX_EMAIL", "support", "inbox_email")
    if explicit:
        return str(explicit).strip().lower()
    fallback = get_config_value("SUPPORT_EMAIL_TO", "support", "email_to")
    if fallback:
        return str(fallback).strip().lower()
    smtp_cfg = get_smtp_settings()
    return str(smtp_cfg.get("from_email", "") or "").strip().lower()


def send_support_verification_code_message(
    recipient_email: str,
    otp_code: str,
    ttl_minutes: int,
) -> tuple[bool, str]:
    smtp_cfg = get_smtp_settings()
    if not smtp_cfg["host"] or not smtp_cfg["from_email"]:
        return False, "Support verification sender is not configured."

    message = EmailMessage()
    message["Subject"] = "Your ZoSwi support verification code"
    message["From"] = smtp_cfg["from_email"]
    message["To"] = str(recipient_email or "").strip().lower()
    message.set_content(
        "\n".join(
            [
                "Use this one-time code to verify your ZoSwi support request:",
                "",
                str(otp_code or "").strip(),
                "",
                f"This code expires in {ttl_minutes} minutes.",
                "If you did not request support, ignore this email.",
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
        return False, "Unable to send support verification email right now."


def send_support_contact_message(
    first_name: str,
    last_name: str,
    sender_email: str,
    subject: str,
    body: str,
) -> tuple[bool, str]:
    smtp_cfg = get_smtp_settings()
    if not smtp_cfg["host"] or not smtp_cfg["from_email"]:
        return False, "Support email sender is not configured."
    inbox_email = get_support_inbox_email()
    if not inbox_email:
        return False, "Support inbox email is not configured."

    cleaned_subject = str(subject or "").strip()
    cleaned_body = str(body or "").strip()
    cleaned_email = str(sender_email or "").strip().lower()
    sender_full_name = " ".join(
        part for part in [str(first_name or "").strip(), str(last_name or "").strip()] if part
    ).strip()
    if not sender_full_name:
        sender_full_name = "ZoSwi User"

    message = EmailMessage()
    message["Subject"] = f"ZoSwi Support: {cleaned_subject[:120]}"
    message["From"] = smtp_cfg["from_email"]
    message["To"] = inbox_email
    message["Reply-To"] = cleaned_email
    message.set_content(
        "\n".join(
            [
                "ZoSwi Privacy Center support request",
                "",
                f"From: {sender_full_name}",
                f"Email: {cleaned_email}",
                f"Submitted (UTC): {datetime.now(timezone.utc).isoformat()}",
                "",
                "Message:",
                cleaned_body,
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
        return True, "Support request sent successfully."
    except Exception:
        return False, "Unable to send support request right now."


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
        if row is None:
            return None
        payload = dict(row)
        payload["role"] = normalize_user_role_for_login_email(
            str(payload.get("role", "")),
            cleaned_email,
            assign_default=True,
        )
        return payload
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
    normalized_role = normalize_user_role_for_login_email(str(role or "").strip().title(), cleaned_email)
    if normalized_role != "Recruiter":
        cleaned_role_contact_email = ""
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
    normalized_role = normalize_user_role_for_login_email(
        str(request.get("role", "")).strip(),
        email,
    )
    normalized_role_contact_email = str(request.get("role_contact_email", "")).strip().lower()
    if normalized_role != "Recruiter":
        normalized_role_contact_email = ""
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
                    account_status, email_verified_at, updated_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(request.get("full_name", "")).strip() or email.split("@")[0],
                    email,
                    str(request.get("password_hash", "")).strip(),
                    normalized_role,
                    str(request.get("years_experience", "")).strip(),
                    normalized_role_contact_email or None,
                    str(request.get("profile_data", "")).strip() or None,
                    "active",
                    now_iso,
                    now_iso,
                    str(request.get("created_at", "")).strip() or now_iso,
                ),
            )
        else:
            conn.execute(
                "UPDATE users SET email_verified_at = COALESCE(email_verified_at, ?), updated_at = ? WHERE email = ?",
                (now_iso, now_iso, email),
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


def normalize_dashboard_view(raw_value: str) -> str:
    cleaned = str(raw_value or "").strip().lower().replace(" ", "_").replace("-", "_")
    mapping = {
        "home": "home",
        "chats": "chats",
        "chat": "chats",
        "scores": "scores",
        "score": "scores",
        "ai_workspace": "ai_workspace",
        "workspace": "ai_workspace",
        "careers": "careers",
        "career": "careers",
        "coding_room": "coding_room",
        "coding": "coding_room",
        "codingroom": "coding_room",
        "live_interview": "live_interview",
        "interview": "live_interview",
        "ai_interview": "live_interview",
        "immigration_updates": "immigration_updates",
        "immigration": "immigration_updates",
        "visa_updates": "immigration_updates",
    }
    return mapping.get(cleaned, "")


def pop_dashboard_view_from_query_params() -> str:
    raw_value = ""
    try:
        for key in ("nav", "view"):
            value = st.query_params.get(key, "")
            if isinstance(value, (list, tuple)):
                value = value[0] if value else ""
            if str(value or "").strip():
                raw_value = str(value or "")
            if key in st.query_params:
                del st.query_params[key]
            if raw_value:
                break
    except Exception:
        return ""
    return normalize_dashboard_view(raw_value)


def sync_password_reset_query_param(enabled: bool) -> None:
    try:
        if enabled:
            st.query_params["pwreset"] = "1"
            return
        if "pwreset" in st.query_params:
            del st.query_params["pwreset"]
    except Exception:
        pass


def is_mobile_browser() -> bool:
    override_raw = ""
    try:
        override_raw = str(st.query_params.get("mobile", "") or "").strip().lower()
    except Exception:
        override_raw = ""
    if override_raw in {"1", "true", "yes", "on"}:
        st.session_state._ui_is_mobile = True
        return True
    if override_raw in {"0", "false", "no", "off"}:
        st.session_state._ui_is_mobile = False
        return False

    cached = st.session_state.get("_ui_is_mobile")
    if isinstance(cached, bool):
        return cached

    user_agent = ""
    try:
        headers = getattr(st.context, "headers", {})
        user_agent = str(headers.get("user-agent", "") or "").strip().lower()
    except Exception:
        user_agent = ""

    mobile_markers = [
        "android",
        "iphone",
        "ipad",
        "ipod",
        "mobile",
        "blackberry",
        "opera mini",
        "iemobile",
        "windows phone",
    ]
    is_mobile = any(marker in user_agent for marker in mobile_markers)
    st.session_state._ui_is_mobile = bool(is_mobile)
    return bool(is_mobile)


def should_auto_open_bot_after_auth() -> bool:
    return not is_mobile_browser()


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
            "UPDATE users SET email_verified_at = COALESCE(email_verified_at, ?), updated_at = ? WHERE id = ?",
            (now_iso, now_iso, user_id),
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


def infer_non_recruiter_role_from_email(email: str) -> str:
    domain = extract_email_domain(email)
    if is_university_email_domain(domain):
        return "Student"
    return "Candidate"


def normalize_user_role_for_login_email(role: str, email: str, assign_default: bool = False) -> str:
    normalized_role = str(role or "").strip().title()
    if normalized_role == "Recruiter":
        domain = extract_email_domain(email)
        if is_university_email_domain(domain):
            return "Student"
        if domain in PUBLIC_EMAIL_DOMAINS:
            return "Candidate"
        return "Recruiter"
    if normalized_role in {"Candidate", "Student"}:
        return normalized_role
    if assign_default and not normalized_role:
        return infer_non_recruiter_role_from_email(email)
    return normalized_role


def get_recruiter_role_restriction_reason(email: str) -> str:
    domain = extract_email_domain(email)
    if not domain:
        return ""
    if is_university_email_domain(domain):
        return (
            "Recruiter access is restricted to organization emails. "
            "University domains are treated as Student accounts."
        )
    if domain in PUBLIC_EMAIL_DOMAINS:
        return (
            "Recruiter access is restricted to organization emails. "
            "Personal domains are treated as Candidate accounts."
        )
    return ""


def is_valid_email_address(email: str) -> bool:
    domain = extract_email_domain(email)
    return bool(domain and "." in domain and not domain.startswith(".") and not domain.endswith("."))


def validate_signup_email_for_role(email: str, role: str) -> tuple[bool, str]:
    if not is_valid_email_address(email):
        return False, "Enter a valid email address."
    normalized_role = str(role or "").strip().title()
    if normalized_role == "Recruiter":
        restriction_reason = get_recruiter_role_restriction_reason(email)
        if restriction_reason:
            return False, f"{restriction_reason} Sign up as Candidate or Student."
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
    if normalized_role == "Recruiter" and is_university_email_domain(domain):
        return False, "Recruiter accounts require an organization email (university domains are not allowed)."
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
    cleaned_email = str(email or "").strip().lower()
    if not cleaned_email:
        return False, "Email is required to redeem promo code."

    is_valid, message, normalized = validate_promo_code(raw_code)
    if not is_valid:
        return False, message

    now_iso = datetime.now(timezone.utc).isoformat()
    conn = db_connect()
    conn.row_factory = sqlite3.Row
    try:
        existing_email = conn.execute(
            """
            SELECT 1
            FROM promo_redemptions
            WHERE email = ?
            LIMIT 1
            """,
            (cleaned_email,),
        ).fetchone()
        if existing_email is not None:
            return False, "Promo code was already used for this account."

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


def has_promo_redemption(email: str) -> bool:
    cleaned_email = str(email or "").strip().lower()
    if not cleaned_email:
        return False

    conn = db_connect()
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT 1
            FROM promo_redemptions
            WHERE email = ?
            LIMIT 1
            """,
            (cleaned_email,),
        ).fetchone()
        return row is not None
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
                full_name, email, password_hash, role, years_experience, role_contact_email, profile_data, account_status, updated_at, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                full_name.strip(),
                cleaned_email,
                hash_password(password),
                normalized_role,
                cleaned_years_experience,
                role_contact_value,
                profile_payload,
                "active",
                datetime.now(timezone.utc).isoformat(),
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
    user = repo.authenticate_user(
        email=email,
        password=password,
        verify_password=verify_password,
        is_modern_password_hash=is_modern_password_hash,
        hash_password=hash_password,
    )
    return enrich_user_with_entitlements(user)


def get_user_by_email(email: str) -> dict[str, Any] | None:
    repo = get_auth_repository()
    user = repo.get_user_by_email(email)
    return enrich_user_with_entitlements(user)


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
        return enrich_user_with_entitlements(dict(row))
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

    oauth_provider = detect_oauth_provider(identity)
    provider_user_id = str(
        identity.get("sub")
        or identity.get("id")
        or identity.get("user_id")
        or identity.get("uid")
        or ""
    ).strip() or None

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
            existing_role = str(row["role"] or "")
            normalized_role = normalize_user_role_for_login_email(
                existing_role,
                email,
                assign_default=True,
            )
            now_iso = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                UPDATE users
                SET
                    role = ?,
                    email_verified_at = COALESCE(email_verified_at, ?),
                    auth_provider = COALESCE(auth_provider, ?),
                    auth_provider_user_id = COALESCE(auth_provider_user_id, ?),
                    updated_at = ?
                WHERE id = ?
                """,
                (normalized_role, now_iso, oauth_provider or None, provider_user_id, now_iso, int(row["id"])),
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
            return enrich_user_with_entitlements(dict(row))

        now_iso = datetime.now(timezone.utc).isoformat()
        random_password = secrets.token_urlsafe(24)
        normalized_role = normalize_user_role_for_login_email("", email, assign_default=True)
        cur = conn.execute(
            """
            INSERT INTO users (
                full_name, email, password_hash, role, years_experience,
                account_status, auth_provider, auth_provider_user_id, email_verified_at, updated_at, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                full_name,
                email,
                hash_password(random_password),
                normalized_role,
                "",
                "active",
                oauth_provider or None,
                provider_user_id,
                now_iso,
                now_iso,
                now_iso,
            ),
        )
        user_id = int(cur.lastrowid or 0)
        conn.commit()
        if user_id <= 0:
            return None
        return enrich_user_with_entitlements(
            {
            "id": user_id,
            "full_name": full_name,
            "email": email,
            "role": normalized_role,
            "years_experience": "",
            "created_at": now_iso,
            }
        )
    finally:
        conn.close()


def sync_user_from_oauth_session() -> None:
    if not is_streamlit_oauth_logged_in():
        return
    try:
        identity = get_streamlit_oauth_user_info()
        user = get_or_create_user_from_oauth_identity(identity)
    except Exception:
        # OAuth identity may be present even when DB/config is temporarily unavailable.
        # Keep auth screen responsive instead of failing the whole render cycle.
        return
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
    st.session_state.bot_open = should_auto_open_bot_after_auth()
    st.session_state.bot_messages = default_bot_messages(full_name)
    st.session_state.bot_pending_prompt = None
    st.session_state.zoswi_submit = False
    st.session_state.clear_zoswi_input = True
    st.session_state.full_chat_submit = False
    st.session_state.clear_full_chat_input = True
    st.session_state.ai_workspace_media_bytes = b""
    st.session_state.ai_workspace_media_mime = ""
    st.session_state.ai_workspace_media_file_name = ""
    st.session_state.ai_workspace_media_label = ""
    st.session_state.dashboard_view = "home"
    st.session_state.user_menu_open = False
    st.session_state.auth_session_token = None
    st.session_state.job_search_results = []
    st.session_state.job_search_last_error = ""
    st.session_state.job_search_role_query = ""
    st.session_state.job_search_preferred_location = ""
    st.session_state.job_search_visa_status = JOB_SEARCH_VISA_STATUSES[0]
    st.session_state.job_search_sponsorship_required = False
    st.session_state.job_search_position_types = []
    st.session_state.job_search_max_results = JOB_SEARCH_MAX_RESULTS_DEFAULT
    st.session_state.job_search_posted_within_days = 0
    st.session_state.careers_use_custom_profile = False
    st.session_state.careers_input_mode = "Resume + JD"
    st.session_state.careers_resume_text = ""
    st.session_state.careers_resume_file_name = ""
    st.session_state.careers_target_job_description = ""
    st.session_state.careers_target_job_description_input = ""
    st.session_state.careers_profile_status = ""


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


def save_job_search_history(
    user_id: int,
    source_profile: str,
    role_query: str,
    preferred_location: str,
    visa_status: str,
    sponsorship_required: bool,
    results: list[dict[str, Any]],
) -> None:
    if user_id <= 0:
        return
    safe_results: list[dict[str, Any]] = []
    for item in (results or [])[:JOB_SEARCH_MAX_RESULTS_LIMIT]:
        raw_position_tags = item.get("position_tags", [])
        if not isinstance(raw_position_tags, list):
            raw_position_tags = []
        safe_results.append(
            {
                "title": str(item.get("title", "")).strip()[:180],
                "company": str(item.get("company", "")).strip()[:180],
                "location": str(item.get("location", "")).strip()[:180],
                "source": str(item.get("source", "")).strip()[:40],
                "overall_score": int(item.get("overall_score", 0) or 0),
                "sponsorship_status": str(item.get("sponsorship_status", "")).strip()[:80],
                "position_tags": [str(tag).strip()[:20] for tag in raw_position_tags[:5]],
                "apply_url": str(item.get("apply_url", "")).strip()[:1200],
            }
        )
    payload = json.dumps(safe_results, ensure_ascii=True)
    conn = db_connect()
    try:
        conn.execute(
            """
            INSERT INTO job_search_history (
                user_id,
                source_profile,
                role_query,
                preferred_location,
                visa_status,
                sponsorship_required,
                result_count,
                results_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(user_id),
                str(source_profile or "").strip()[:40] or "Adzuna",
                str(role_query or "").strip()[:220],
                str(preferred_location or "").strip()[:220],
                str(visa_status or "").strip()[:80],
                1 if sponsorship_required else 0,
                len(safe_results),
                payload[:120000],
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_recent_job_search_history(user_id: int, limit: int = 8) -> list[dict[str, Any]]:
    if user_id <= 0:
        return []
    conn = db_connect()
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT source_profile, role_query, preferred_location, visa_status, sponsorship_required, result_count, created_at
            FROM job_search_history
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, max(1, int(limit or 1))),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def fetch_adzuna_jobs(
    role_query: str,
    preferred_location: str,
    max_results: int = JOB_SEARCH_MAX_RESULTS_DEFAULT,
) -> tuple[list[dict[str, Any]], str]:
    app_id = get_config_value("ADZUNA_APP_ID", "jobs", "adzuna_app_id", "")
    app_key = get_config_value("ADZUNA_APP_KEY", "jobs", "adzuna_app_key", "")
    country = get_config_value("ADZUNA_COUNTRY", "jobs", "adzuna_country", "us").strip().lower() or "us"
    if not app_id or not app_key:
        return (
            [],
            "Set ADZUNA_APP_ID and ADZUNA_APP_KEY in environment/secrets to fetch live jobs.",
        )

    safe_role = " ".join(str(role_query or "").split())
    if not safe_role:
        return [], "Enter a target role before searching jobs."
    safe_where = " ".join(str(preferred_location or "").split())

    limit = max(1, min(JOB_SEARCH_MAX_RESULTS_LIMIT, int(max_results or JOB_SEARCH_MAX_RESULTS_DEFAULT)))
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": str(limit),
        "what": safe_role,
        "sort_by": "date",
        "content-type": "application/json",
    }
    if safe_where:
        params["where"] = safe_where

    request_url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1?{urlencode(params)}"
    request = Request(
        request_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "PyStreamlineAI/1.0",
        },
    )
    try:
        with urlopen(request, timeout=JOB_SEARCH_API_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except HTTPError as ex:
        return [], f"Job API error ({int(ex.code)}). Check Adzuna credentials/country and retry."
    except URLError:
        return [], "Job API connection failed. Check network access and retry."
    except Exception:
        return [], "Could not parse the job API response."

    items = payload.get("results", [])
    if not isinstance(items, list):
        items = []

    jobs: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        company_obj = item.get("company", {}) or {}
        location_obj = item.get("location", {}) or {}
        location_parts = location_obj.get("display_name")
        location_text = str(location_parts or "").strip()
        if not location_text:
            area_values = location_obj.get("area")
            if isinstance(area_values, list):
                location_text = ", ".join(str(part).strip() for part in area_values if str(part).strip())
        title = str(item.get("title", "")).strip()
        description = str(item.get("description", "")).strip()
        if not title:
            continue
        jobs.append(
            {
                "title": title,
                "company": str(company_obj.get("display_name", "")).strip() or "Unknown company",
                "location": location_text or "Location not listed",
                "description": description,
                "apply_url": str(item.get("redirect_url", "")).strip(),
                "source": "Adzuna",
                "employment_type": str(item.get("contract_time", "")).strip(),
                "contract_type": str(item.get("contract_type", "")).strip(),
                "posted_at": normalize_posted_at(item.get("created")),
            }
        )
    if not jobs:
        return [], "No jobs matched the current role/location filter."
    return jobs, ""


def strip_html_tags(raw_text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", str(raw_text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text


def get_posted_within_label(days: int) -> str:
    for label, value in JOB_SEARCH_POSTED_WITHIN_OPTIONS:
        if int(value) == int(days or 0):
            return label
    return "Anytime"


def parse_job_posted_datetime(raw_value: Any) -> datetime | None:
    text = str(raw_value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(text)
    except Exception:
        parsed = None
    if parsed is None:
        known_formats = (
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%d %H:%M:%S%z",
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
        )
        for fmt in known_formats:
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except Exception:
                continue
    if parsed is None:
        try:
            parsed = parsedate_to_datetime(text)
        except Exception:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_posted_at(raw_value: Any) -> str:
    parsed = parse_job_posted_datetime(raw_value)
    if parsed is None:
        return ""
    return parsed.isoformat()


def is_posted_within_days(posted_at: str, max_days: int) -> bool:
    days = max(0, int(max_days or 0))
    if days <= 0:
        return True
    parsed = parse_job_posted_datetime(posted_at)
    if parsed is None:
        return False
    age = datetime.now(timezone.utc) - parsed
    return timedelta(0) <= age <= timedelta(days=days)


def format_posted_age(posted_at: str) -> str:
    parsed = parse_job_posted_datetime(posted_at)
    if parsed is None:
        return "Posted date not listed"
    age = datetime.now(timezone.utc) - parsed
    if age < timedelta(0):
        return "Recently posted"
    if age < timedelta(hours=1):
        mins = max(1, int(age.total_seconds() // 60))
        return f"Posted {mins} min ago"
    if age < timedelta(days=1):
        hours = max(1, int(age.total_seconds() // 3600))
        return f"Posted {hours} hour ago" if hours == 1 else f"Posted {hours} hours ago"
    days = age.days
    return f"Posted {days} day ago" if days == 1 else f"Posted {days} days ago"


def fetch_remotive_jobs(
    role_query: str,
    preferred_location: str,
    max_results: int = JOB_SEARCH_MAX_RESULTS_DEFAULT,
) -> tuple[list[dict[str, Any]], str]:
    safe_role = " ".join(str(role_query or "").split())
    if not safe_role:
        return [], "Enter a target role before searching jobs."

    limit = max(1, min(JOB_SEARCH_MAX_RESULTS_LIMIT, int(max_results or JOB_SEARCH_MAX_RESULTS_DEFAULT)))
    params = {
        "search": safe_role,
        "limit": str(limit),
    }
    request_url = f"https://remotive.com/api/remote-jobs?{urlencode(params)}"
    request = Request(
        request_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "PyStreamlineAI/1.0",
        },
    )
    try:
        with urlopen(request, timeout=JOB_SEARCH_API_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except HTTPError as ex:
        return [], f"Remotive API error ({int(ex.code)})."
    except URLError:
        return [], "Remotive API connection failed. Check network access and retry."
    except Exception:
        return [], "Could not parse Remotive API response."

    items = payload.get("jobs", [])
    if not isinstance(items, list):
        items = []

    preferred = str(preferred_location or "").strip().lower()
    jobs: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        location = str(item.get("candidate_required_location", "")).strip() or "Remote"
        if preferred and preferred not in location.lower() and "remote" not in location.lower():
            continue
        description = strip_html_tags(str(item.get("description", "")))
        jobs.append(
            {
                "title": title,
                "company": str(item.get("company_name", "")).strip() or "Unknown company",
                "location": location,
                "description": description,
                "apply_url": str(item.get("url", "")).strip(),
                "source": "Remotive",
                "employment_type": str(item.get("job_type", "")).strip(),
                "contract_type": str(item.get("job_type", "")).strip(),
                "posted_at": normalize_posted_at(item.get("publication_date")),
            }
        )
        if len(jobs) >= limit:
            break
    if not jobs:
        return [], "No Remotive jobs matched the current role/location filter."
    return jobs, ""


def fetch_usajobs_jobs(
    role_query: str,
    preferred_location: str,
    max_results: int = JOB_SEARCH_MAX_RESULTS_DEFAULT,
) -> tuple[list[dict[str, Any]], str]:
    auth_key = get_config_value("USAJOBS_AUTH_KEY", "jobs", "usajobs_auth_key", "")
    user_agent = get_config_value("USAJOBS_USER_AGENT", "jobs", "usajobs_user_agent", "")
    if not auth_key or not user_agent:
        return (
            [],
            "Set USAJOBS_AUTH_KEY and USAJOBS_USER_AGENT in env/secrets to use USAJobs source.",
        )

    safe_role = " ".join(str(role_query or "").split())
    if not safe_role:
        return [], "Enter a target role before searching jobs."
    limit = max(1, min(JOB_SEARCH_MAX_RESULTS_LIMIT, int(max_results or JOB_SEARCH_MAX_RESULTS_DEFAULT)))

    params = {
        "Keyword": safe_role,
        "ResultsPerPage": str(limit),
    }
    safe_where = " ".join(str(preferred_location or "").split())
    if safe_where:
        params["LocationName"] = safe_where

    request_url = f"https://data.usajobs.gov/api/Search?{urlencode(params)}"
    request = Request(
        request_url,
        headers={
            "Accept": "application/json",
            "Authorization-Key": auth_key,
            "Host": "data.usajobs.gov",
            "User-Agent": user_agent,
        },
    )
    try:
        with urlopen(request, timeout=JOB_SEARCH_API_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except HTTPError as ex:
        return [], f"USAJobs API error ({int(ex.code)}). Check credentials and header values."
    except URLError:
        return [], "USAJobs API connection failed. Check network access and retry."
    except Exception:
        return [], "Could not parse USAJobs API response."

    search_result = payload.get("SearchResult", {}) if isinstance(payload, dict) else {}
    raw_items = search_result.get("SearchResultItems", []) if isinstance(search_result, dict) else []
    if not isinstance(raw_items, list):
        raw_items = []

    jobs: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        descriptor = item.get("MatchedObjectDescriptor", {}) or {}
        title = str(descriptor.get("PositionTitle", "")).strip()
        if not title:
            continue
        positions = descriptor.get("PositionLocation", [])
        location = "Location not listed"
        if isinstance(positions, list) and positions:
            first_loc = positions[0]
            if isinstance(first_loc, dict):
                location = str(first_loc.get("LocationName", "")).strip() or location
        job_summary = ""
        details: dict[str, Any] = {}
        user_area = descriptor.get("UserArea", {}) or {}
        if isinstance(user_area, dict):
            details = user_area.get("Details", {}) or {}
            if isinstance(details, dict):
                job_summary = str(details.get("JobSummary", "")).strip()
        apply_url = ""
        apply_list = descriptor.get("ApplyURI", [])
        if isinstance(apply_list, list) and apply_list:
            apply_url = str(apply_list[0]).strip()
        posted_at = ""
        for candidate in (
            descriptor.get("PublicationStartDate"),
            descriptor.get("PositionStartDate"),
            descriptor.get("PositionEndDate"),
            details.get("PublicationStartDate") if isinstance(details, dict) else "",
            details.get("PositionStartDate") if isinstance(details, dict) else "",
            details.get("PositionEndDate") if isinstance(details, dict) else "",
        ):
            normalized_candidate = normalize_posted_at(candidate)
            if normalized_candidate:
                posted_at = normalized_candidate
                break

        jobs.append(
            {
                "title": title,
                "company": str(descriptor.get("OrganizationName", "")).strip() or "US Government",
                "location": location,
                "description": strip_html_tags(job_summary),
                "apply_url": apply_url,
                "source": "USAJobs",
                "employment_type": strip_html_tags(json.dumps(descriptor.get("PositionSchedule", []))),
                "contract_type": strip_html_tags(json.dumps(descriptor.get("PositionOfferingType", []))),
                "posted_at": posted_at,
            }
        )
    if not jobs:
        return [], "No USAJobs roles matched the current role/location filter."
    return jobs, ""


def fetch_jooble_jobs(
    role_query: str,
    preferred_location: str,
    max_results: int = JOB_SEARCH_MAX_RESULTS_DEFAULT,
) -> tuple[list[dict[str, Any]], str]:
    api_key = get_config_value("JOOBLE_API_KEY", "jobs", "jooble_api_key", "")
    if not api_key:
        return (
            [],
            "Set JOOBLE_API_KEY in environment/secrets to use Jooble source.",
        )

    safe_role = " ".join(str(role_query or "").split())
    if not safe_role:
        return [], "Enter a target role before searching jobs."
    safe_where = " ".join(str(preferred_location or "").split())
    limit = max(1, min(JOB_SEARCH_MAX_RESULTS_LIMIT, int(max_results or JOB_SEARCH_MAX_RESULTS_DEFAULT)))

    request_url = f"https://jooble.org/api/{api_key}"
    payload = {
        "keywords": safe_role,
        "location": safe_where,
        "page": "1",
    }
    request = Request(
        request_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "PyStreamlineAI/1.0",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=JOB_SEARCH_API_TIMEOUT_SECONDS) as response:
            raw_payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except HTTPError as ex:
        return [], f"Jooble API error ({int(ex.code)}). Check Jooble key and retry."
    except URLError:
        return [], "Jooble API connection failed. Check network access and retry."
    except Exception:
        return [], "Could not parse Jooble API response."

    raw_items = raw_payload.get("jobs", []) if isinstance(raw_payload, dict) else []
    if not isinstance(raw_items, list):
        raw_items = []

    jobs: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        location = str(item.get("location", "")).strip() or "Location not listed"
        jobs.append(
            {
                "title": strip_html_tags(title),
                "company": strip_html_tags(str(item.get("company", "")).strip()) or "Unknown company",
                "location": strip_html_tags(location),
                "description": strip_html_tags(str(item.get("snippet", "")).strip()),
                "apply_url": str(item.get("link", "")).strip(),
                "source": "Jooble",
                "employment_type": strip_html_tags(str(item.get("type", "")).strip()),
                "contract_type": strip_html_tags(str(item.get("type", "")).strip()),
                "posted_at": normalize_posted_at(item.get("updated") or item.get("created") or item.get("posted")),
            }
        )
        if len(jobs) >= limit:
            break
    if not jobs:
        return [], "No Jooble jobs matched the current role/location filter."
    return jobs, ""


def fetch_jobs_from_all_sources(
    role_query: str,
    preferred_location: str,
    max_results: int = JOB_SEARCH_MAX_RESULTS_DEFAULT,
) -> tuple[list[dict[str, Any]], str]:
    target_count = max(1, min(JOB_SEARCH_MAX_RESULTS_LIMIT, int(max_results or JOB_SEARCH_MAX_RESULTS_DEFAULT)))
    safe_role = " ".join(str(role_query or "").split())
    safe_location = " ".join(str(preferred_location or "").split())
    adzuna_app_id = get_config_value("ADZUNA_APP_ID", "jobs", "adzuna_app_id", "")
    adzuna_app_key = get_config_value("ADZUNA_APP_KEY", "jobs", "adzuna_app_key", "")
    adzuna_country = get_config_value("ADZUNA_COUNTRY", "jobs", "adzuna_country", "us").strip().lower() or "us"
    jooble_api_key = get_config_value("JOOBLE_API_KEY", "jobs", "jooble_api_key", "")
    usajobs_auth_key = get_config_value("USAJOBS_AUTH_KEY", "jobs", "usajobs_auth_key", "")
    usajobs_user_agent = get_config_value("USAJOBS_USER_AGENT", "jobs", "usajobs_user_agent", "")
    enabled_provider_count = 1
    if adzuna_app_id and adzuna_app_key:
        enabled_provider_count += 1
    if jooble_api_key:
        enabled_provider_count += 1
    if usajobs_auth_key and usajobs_user_agent:
        enabled_provider_count += 1
    per_provider_limit = max(3, min(JOB_SEARCH_MAX_RESULTS_LIMIT, int(target_count / max(1, enabled_provider_count)) + 2))
    cache_bucket = int(time.time() // max(1, JOB_SEARCH_FETCH_CACHE_TTL_SECONDS))

    cached_jobs, message = _fetch_jobs_from_all_sources_cached(
        role_query=safe_role,
        preferred_location=safe_location,
        target_count=target_count,
        per_provider_limit=per_provider_limit,
        adzuna_enabled=bool(adzuna_app_id and adzuna_app_key),
        adzuna_country=adzuna_country,
        jooble_enabled=bool(jooble_api_key),
        usajobs_enabled=bool(usajobs_auth_key and usajobs_user_agent),
        cache_bucket=cache_bucket,
    )
    return [dict(item) for item in cached_jobs if isinstance(item, dict)], message


@lru_cache(maxsize=96)
def _fetch_jobs_from_all_sources_cached(
    role_query: str,
    preferred_location: str,
    target_count: int,
    per_provider_limit: int,
    adzuna_enabled: bool,
    adzuna_country: str,
    jooble_enabled: bool,
    usajobs_enabled: bool,
    cache_bucket: int,
) -> tuple[tuple[dict[str, Any], ...], str]:
    _ = (adzuna_country, jooble_enabled, cache_bucket)

    provider_fetchers: list[tuple[str, Any]] = [("Remotive", fetch_remotive_jobs)]
    if adzuna_enabled:
        provider_fetchers.insert(0, ("Adzuna", fetch_adzuna_jobs))
    if jooble_enabled:
        provider_fetchers.append(("Jooble", fetch_jooble_jobs))
    if usajobs_enabled:
        provider_fetchers.append(("USAJobs", fetch_usajobs_jobs))

    aggregated: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, len(provider_fetchers))) as executor:
        future_map = {
            executor.submit(fetcher, role_query, preferred_location, max_results=per_provider_limit): provider
            for provider, fetcher in provider_fetchers
        }
        for future in as_completed(future_map):
            try:
                jobs, _ = future.result()
            except Exception:
                continue
            if isinstance(jobs, list) and jobs:
                aggregated.extend(job for job in jobs if isinstance(job, dict))

    seen: set[tuple[str, str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for job in aggregated:
        title = str(job.get("title", "")).strip().lower()
        company = str(job.get("company", "")).strip().lower()
        location = str(job.get("location", "")).strip().lower()
        apply_url = str(job.get("apply_url", "")).strip().lower()
        key = (title, company, location, apply_url)
        if not title or key in seen:
            continue
        seen.add(key)
        deduped.append(job)

    if not deduped:
        return tuple(), "No jobs found for this search. Try broadening role, location, or filters."

    pool_limit = min(len(deduped), max(target_count, target_count + 4))
    return tuple(dict(item) for item in deduped[:pool_limit] if isinstance(item, dict)), ""


def infer_job_position_tags(job_row: dict[str, Any]) -> list[str]:
    title = str(job_row.get("title", "")).strip().lower()
    description = str(job_row.get("description", "")).strip().lower()
    employment_type = str(job_row.get("employment_type", "")).strip().lower()
    contract_type = str(job_row.get("contract_type", "")).strip().lower()
    text = " ".join([title, description, employment_type, contract_type])

    tags: list[str] = []

    full_time_signals = ("full time", "full-time", "full_time", "permanent")
    contract_signals = ("contract", "contractor", "contract-to-hire", "contract to hire")
    part_time_signals = ("part time", "part-time", "part_time")
    w2_signals = ("w2", "w-2", "w 2", "on w2", "w2 only")
    c2c_signals = ("c2c", "corp to corp", "corp-to-corp", "1099")

    if any(token in text for token in full_time_signals):
        tags.append("Full-Time")
    if any(token in text for token in contract_signals):
        tags.append("Contract")
    if any(token in text for token in part_time_signals):
        tags.append("Part-Time")
    if any(token in text for token in w2_signals):
        tags.append("W2")
    if any(token in text for token in c2c_signals):
        tags.append("C2C")

    deduped_tags: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        cleaned = str(tag).strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        deduped_tags.append(cleaned)
    return deduped_tags


def filter_jobs_by_position_types(
    raw_jobs: list[dict[str, Any]],
    selected_types: list[str],
) -> tuple[list[dict[str, Any]], str]:
    cleaned_selected = [str(item).strip() for item in (selected_types or []) if str(item).strip()]
    if not cleaned_selected:
        enriched: list[dict[str, Any]] = []
        for job in raw_jobs:
            if not isinstance(job, dict):
                continue
            tags = infer_job_position_tags(job)
            job_copy = dict(job)
            job_copy["position_tags"] = tags
            enriched.append(job_copy)
        return enriched, ""

    selected_set = set(cleaned_selected)
    filtered: list[dict[str, Any]] = []
    for job in raw_jobs:
        if not isinstance(job, dict):
            continue
        tags = infer_job_position_tags(job)
        if not tags:
            continue
        if not any(tag in selected_set for tag in tags):
            continue
        job_copy = dict(job)
        job_copy["position_tags"] = tags
        filtered.append(job_copy)
    if not filtered:
        return [], "No jobs matched the selected position type filters."
    return filtered, ""


def filter_jobs_by_posted_within(
    raw_jobs: list[dict[str, Any]],
    posted_within_days: int,
) -> tuple[list[dict[str, Any]], str]:
    max_days = max(0, int(posted_within_days or 0))
    cleaned_jobs = [dict(job) for job in raw_jobs if isinstance(job, dict)]
    if max_days <= 0:
        return cleaned_jobs, ""

    filtered: list[dict[str, Any]] = []
    for job in cleaned_jobs:
        posted_at = str(job.get("posted_at", "")).strip()
        if is_posted_within_days(posted_at, max_days):
            filtered.append(job)
    if not filtered:
        day_label = "day" if max_days == 1 else "days"
        return [], f"No jobs were posted in the last {max_days} {day_label}. Try widening the posted-date filter."
    return filtered, ""


def sanitize_job_search_error_message(message: str) -> str:
    raw = str(message or "").strip()
    if not raw:
        return ""
    lowered = raw.lower()
    if "relevance mode:" in lowered:
        return ""
    source_markers = (
        "some sources were unavailable",
        "remotive:",
        "usajobs:",
        "adzuna:",
        "no remotive jobs matched",
        "no usajobs roles matched",
        "source",
        "unavailable",
    )
    if any(marker in lowered for marker in source_markers):
        return "No jobs found for this search. Try broadening role, location, or filters."
    return raw


def is_agentive_job_search_request(message: str) -> bool:
    text = re.sub(r"\s+", " ", str(message or "").strip().lower())
    if not text:
        return False
    has_action = any(token in text for token in AGENTIVE_JOB_ACTION_TOKENS)
    has_object = any(token in text for token in AGENTIVE_JOB_OBJECT_TOKENS)
    has_work_auth = any(token in text for token in AGENTIVE_WORK_AUTH_TOKENS)
    return bool((has_action and has_object) or (has_object and has_work_auth))


def is_zoswi_capability_request(message: str) -> bool:
    text = re.sub(r"\s+", " ", str(message or "").strip().lower())
    if not text:
        return False

    feature_terms = (
        "coding room",
        "ai coding room",
        "ai workspace",
        "live workspace",
        "zoswi live workspace",
        "careers",
        "career studio",
        "job match studio",
        "live ai interview",
        "ai interview",
        "interview room",
        "immigration updates",
        "visa updates",
        "resume-jd",
        "resume jd",
        "feature",
        "features",
        "capability",
        "capabilities",
    )
    if not any(term in text for term in feature_terms):
        return False

    intent_markers = (
        "?",
        "does",
        "do we have",
        "have",
        "available",
        "what can",
        "where is",
        "how to open",
        "open",
        "launch",
        "start",
        "not up to date",
        "not working",
    )
    if any(marker in text for marker in intent_markers):
        return True
    return "zoswi" in text


def is_zoswi_builder_request(message: str) -> bool:
    text = re.sub(r"\s+", " ", str(message or "").strip().lower())
    if not text:
        return False
    brand_markers = ("zoswi", "this app", "this assistant", "your app", "you")
    if not any(marker in text for marker in brand_markers):
        return False
    identity_terms = (
        "built",
        "created",
        "made",
        "developed",
        "founder",
        "creator",
        "builder",
        "behind",
        "owner",
    )
    if not any(term in text for term in identity_terms):
        return False
    return bool(
        re.search(r"\bwho\b", text)
        or "built by" in text
        or "created by" in text
        or "made by" in text
        or "who is behind" in text
    )


def build_zoswi_builder_response() -> str:
    builder_name = get_zoswi_builder_name()
    if builder_name:
        return f"ZoSwi team was founded by {builder_name}."
    return "ZoSwi team was founded by the ZoSwi team."


def build_zoswi_capability_response(message: str) -> str:
    text = re.sub(r"\s+", " ", str(message or "").strip().lower())
    analysis = st.session_state.get("analysis_result")
    has_analysis = isinstance(analysis, dict) and bool(analysis)
    flags = get_effective_dashboard_feature_flags(st.session_state.get("user"))
    coding_room_enabled = flags.get("coding_room", False)
    coding_room_ready = bool(has_analysis) and coding_room_enabled
    live_workspace_enabled = flags.get("ai_workspace", False)
    careers_enabled = flags.get("careers", False)
    live_interview_enabled = flags.get("live_interview", False)
    immigration_updates_enabled = flags.get("immigration_updates", False)

    if "coding room" in text or "ai coding room" in text:
        if not coding_room_enabled:
            return "AI Coding Room is currently disabled."
        if coding_room_ready:
            return (
                "Yes. ZoSwi has AI Coding Room and it is available now. "
                "Open Home and click Start 3-Stage AI Coding Room."
            )
        return (
            "Yes. ZoSwi has AI Coding Room. "
            "Run Home Resume-JD analysis once, then Start 3-Stage AI Coding Room will unlock."
        )

    if "ai workspace" in text or "live workspace" in text:
        if not live_workspace_enabled:
            return f"{ZOSWI_LIVE_WORKSPACE_NAME} is currently disabled."
        return (
            f"Yes. {ZOSWI_LIVE_WORKSPACE_NAME} is available. "
            "It supports real-time chat, file understanding, image analysis, and image generation."
        )

    if "careers" in text or "job match studio" in text:
        if not careers_enabled:
            return "ZoSwi Careers is currently disabled."
        return (
            "Yes. ZoSwi Careers is available. "
            "Use Career Match Studio to fetch live jobs and rank by resume fit, location, visa, sponsorship, and posted date."
        )

    if "interview" in text:
        if not live_interview_enabled:
            return "Live AI Interview is currently disabled."
        return (
            "Yes. Live AI Interview is available. "
            "Open Live AI Interview to launch a guided mock interview session."
        )

    if "immigration" in text or "visa updates" in text:
        if not immigration_updates_enabled:
            return "Immigration Updates is currently disabled."
        return (
            "Yes. Immigration Updates is available. "
            "Use it to review curated visa and immigration updates."
        )

    enabled_modules: list[str] = []
    if careers_enabled:
        enabled_modules.append("Careers")
    if live_workspace_enabled:
        enabled_modules.append(ZOSWI_LIVE_WORKSPACE_NAME)
    if coding_room_enabled:
        enabled_modules.append("AI Coding Room")
    if live_interview_enabled:
        enabled_modules.append("Live AI Interview")
    if immigration_updates_enabled:
        enabled_modules.append("Immigration Updates")

    modules_line = ", ".join(enabled_modules) if enabled_modules else "none"
    if not coding_room_enabled:
        coding_status = "disabled"
    elif coding_room_ready:
        coding_status = "ready now"
    else:
        coding_status = "enabled (unlocks after Resume-JD analysis)"
    return (
        f"Enabled ZoSwi modules: {modules_line}. "
        f"Coding Room status: {coding_status}."
    )


def _clean_agentive_role_text(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "")).strip(" ,.;:-")
    cleaned = re.sub(r"(?i)^(?:find|search|show|get|list|recommend|match|shortlist)\s+(?:me\s+)?", "", cleaned).strip()
    cleaned = re.sub(r"(?i)^(?:top\s+)?\d{1,2}\s+", "", cleaned).strip()
    cleaned = re.sub(r"(?i)\b(?:jobs?|roles?|openings?|positions?)\b$", "", cleaned).strip(" ,.;:-")
    cleaned = re.sub(r"[^a-zA-Z0-9/+\-&\s]", "", cleaned).strip()
    if cleaned.lower() in {"me", "my", "the", "a", "an", "all", "any"}:
        return ""
    return cleaned[:90]


def _extract_requested_role_query(message: str, fallback_role: str) -> str:
    text = re.sub(r"\s+", " ", str(message or "").strip())
    if not text:
        return str(fallback_role or "").strip()

    patterns = (
        r"(?i)\b(?:jobs?|roles?|openings?|positions?)\s+(?:for|as)\s+([a-z0-9][a-z0-9\s/&+\-]{1,90})",
        r"(?i)\b(?:find|search|show|get|list|recommend|match|shortlist)\s+(?:me\s+)?(?:jobs?|roles?|openings?|positions?)\s*(?:for|as)?\s*([a-z0-9][a-z0-9\s/&+\-]{1,90})",
        r"(?i)\bfor\s+([a-z0-9][a-z0-9\s/&+\-]{1,90})\s+(?:jobs?|roles?|openings?|positions?)\b",
        r"(?i)\b([a-z][a-z0-9\s/&+\-]{2,80})\s+(?:jobs?|roles?|openings?)\b",
    )
    split_pattern = r"(?i)\b(?:in|at|near|around|with|that|who|posted|within|last|past|for|requiring)\b"
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        candidate = re.split(split_pattern, str(match.group(1) or ""), maxsplit=1)[0]
        cleaned = _clean_agentive_role_text(candidate)
        if cleaned and cleaned.lower() not in AGENTIVE_JOB_ACTION_TOKENS:
            return cleaned
    return str(fallback_role or "").strip()


def _extract_requested_location(message: str, fallback_location: str) -> str:
    text = re.sub(r"\s+", " ", str(message or "").strip())
    lowered = text.lower()
    if re.search(r"\bremote\b", lowered):
        return "Remote"

    location_patterns = (
        r"(?i)\b(?:in|at|near|around)\s+([a-z][a-z0-9,\-\s]{2,80})",
    )
    split_pattern = (
        r"(?i)\b(?:with|for|who|that|posted|within|last|past|sponsorship|visa|h1b|full[- ]time|contract|w2|c2c)\b"
    )
    for pattern in location_patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        candidate = re.split(split_pattern, str(match.group(1) or ""), maxsplit=1)[0]
        cleaned = re.sub(r"\s+", " ", candidate).strip(" ,.;:-")[:90]
        if cleaned:
            return cleaned
    return str(fallback_location or "").strip()


def _extract_requested_position_types(message: str, fallback_types: list[str]) -> list[str]:
    text = re.sub(r"\s+", " ", str(message or "").strip().lower())
    if not text:
        return [item for item in (fallback_types or []) if item in JOB_POSITION_FILTER_OPTIONS]
    if any(token in text for token in ("all types", "any type", "all positions", "any position", "all roles")):
        return []

    selected: list[str] = []
    if any(token in text for token in ("full-time", "full time", "permanent")):
        selected.append("Full-Time")
    if "contract" in text or "contractor" in text:
        selected.append("Contract")
    if any(token in text for token in ("w2", "w-2", "w 2")):
        selected.append("W2")
    if any(token in text for token in ("c2c", "corp to corp", "corp-to-corp", "1099")):
        selected.append("C2C")
    if any(token in text for token in ("part-time", "part time")):
        selected.append("Part-Time")

    deduped: list[str] = []
    seen: set[str] = set()
    for item in selected:
        if item in JOB_POSITION_FILTER_OPTIONS and item not in seen:
            seen.add(item)
            deduped.append(item)
    if deduped:
        return deduped
    return [item for item in (fallback_types or []) if item in JOB_POSITION_FILTER_OPTIONS]


def _extract_requested_posted_within_days(message: str, fallback_days: int) -> int:
    text = re.sub(r"\s+", " ", str(message or "").strip().lower())
    if not text:
        return max(0, int(fallback_days or 0))
    if any(token in text for token in ("anytime", "any time", "all dates", "all postings")):
        return 0
    if any(token in text for token in ("today", "24 hour", "24 hours", "1 day")):
        return 1
    if any(token in text for token in ("3 day", "3 days")):
        return 3
    if any(token in text for token in ("7 day", "7 days", "1 week", "one week")):
        return 7
    if any(token in text for token in ("14 day", "14 days", "2 week", "two week")):
        return 14
    if any(token in text for token in ("30 day", "30 days", "1 month", "one month")):
        return 30

    day_match = re.search(r"(?i)\b(?:past|last|within)\s*(\d{1,2})\s*days?\b", text)
    if day_match:
        requested = max(0, int(day_match.group(1)))
        for option in (1, 3, 7, 14, 30):
            if requested <= option:
                return option
        return 30
    week_match = re.search(r"(?i)\b(?:past|last|within)\s*(\d{1,2})\s*weeks?\b", text)
    if week_match:
        weeks = max(0, int(week_match.group(1)))
        days = weeks * 7
        for option in (1, 3, 7, 14, 30):
            if days <= option:
                return option
        return 30
    return max(0, int(fallback_days or 0))


def _extract_requested_max_results(message: str, fallback_max_results: int) -> int:
    text = re.sub(r"\s+", " ", str(message or "").strip().lower())
    if not text:
        return max(3, min(JOB_SEARCH_MAX_RESULTS_LIMIT, int(fallback_max_results or JOB_SEARCH_MAX_RESULTS_DEFAULT)))
    if any(token in text for token in ("all jobs", "all roles", "all results")):
        return JOB_SEARCH_MAX_RESULTS_LIMIT

    patterns = (
        r"(?i)\b(?:top|show|list|give|find|max(?:imum)?)\s*(\d{1,2})\s*(?:jobs?|roles?|results?)?\b",
        r"(?i)\b(\d{1,2})\s*(?:jobs?|roles?|results?)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        value = int(match.group(1))
        return max(3, min(JOB_SEARCH_MAX_RESULTS_LIMIT, value))
    return max(3, min(JOB_SEARCH_MAX_RESULTS_LIMIT, int(fallback_max_results or JOB_SEARCH_MAX_RESULTS_DEFAULT)))


def _extract_requested_visa_and_sponsorship(
    message: str,
    fallback_visa_status: str,
    fallback_sponsorship_required: bool,
) -> tuple[str, bool]:
    text = re.sub(r"\s+", " ", str(message or "").strip().lower())
    visa_status = str(fallback_visa_status or JOB_SEARCH_VISA_STATUSES[0]).strip() or JOB_SEARCH_VISA_STATUSES[0]
    sponsorship_required = bool(fallback_sponsorship_required)

    if any(token in text for token in ("citizen", "green card", "gc holder", "us citizen")):
        visa_status = "US Citizen / Green Card"
    elif any(token in text for token in ("h1b", "h-1b", "h 1b")):
        visa_status = "H-1B"
    elif any(token in text for token in ("opt", "cpt", "f1", "f-1")):
        visa_status = "F-1 OPT / CPT"
    elif any(token in text for token in ("l1", "l-1", "l 1")):
        visa_status = "L-1"
    elif re.search(r"(?i)\btn\b", text):
        visa_status = "TN"

    no_sponsorship_markers = (
        "no sponsorship",
        "without sponsorship",
        "sponsorship not required",
        "dont need sponsorship",
        "do not need sponsorship",
    )
    sponsorship_markers = (
        "sponsorship",
        "h1b",
        "h-1b",
        "visa support",
        "need visa",
        "opt",
        "cpt",
    )
    if any(marker in text for marker in no_sponsorship_markers):
        sponsorship_required = False
    elif any(marker in text for marker in sponsorship_markers):
        sponsorship_required = True

    return visa_status, sponsorship_required


def build_agentive_job_search_filters(
    message: str,
    fallback_filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    defaults = fallback_filters or {}
    fallback_role = str(defaults.get("role_query", "")).strip()
    fallback_location = str(defaults.get("preferred_location", "")).strip()
    fallback_visa = str(defaults.get("visa_status", JOB_SEARCH_VISA_STATUSES[0])).strip() or JOB_SEARCH_VISA_STATUSES[0]
    fallback_sponsorship = bool(defaults.get("sponsorship_required", False))
    raw_fallback_types = defaults.get("selected_position_types", [])
    fallback_types = (
        [str(item).strip() for item in raw_fallback_types if str(item).strip()]
        if isinstance(raw_fallback_types, list)
        else []
    )
    fallback_posted_days = int(defaults.get("posted_within_days", 0) or 0)
    fallback_max_results = int(defaults.get("max_results", JOB_SEARCH_MAX_RESULTS_DEFAULT) or JOB_SEARCH_MAX_RESULTS_DEFAULT)

    role_query = _extract_requested_role_query(message, fallback_role)
    preferred_location = _extract_requested_location(message, fallback_location)
    selected_position_types = _extract_requested_position_types(message, fallback_types)
    posted_within_days = _extract_requested_posted_within_days(message, fallback_posted_days)
    max_results = _extract_requested_max_results(message, fallback_max_results)
    visa_status, sponsorship_required = _extract_requested_visa_and_sponsorship(
        message,
        fallback_visa_status=fallback_visa,
        fallback_sponsorship_required=fallback_sponsorship,
    )

    return {
        "role_query": role_query,
        "preferred_location": preferred_location,
        "visa_status": visa_status,
        "sponsorship_required": sponsorship_required,
        "selected_position_types": selected_position_types,
        "posted_within_days": posted_within_days,
        "max_results": max_results,
    }


def apply_agentive_job_filters_to_state(filters: dict[str, Any]) -> None:
    st.session_state.job_search_role_query = str(filters.get("role_query", "")).strip()
    st.session_state.job_search_preferred_location = str(filters.get("preferred_location", "")).strip()
    st.session_state.job_search_visa_status = str(filters.get("visa_status", JOB_SEARCH_VISA_STATUSES[0])).strip()
    st.session_state.job_search_sponsorship_required = bool(filters.get("sponsorship_required", False))
    raw_types = filters.get("selected_position_types", [])
    cleaned_types = [str(item).strip() for item in raw_types if str(item).strip()] if isinstance(raw_types, list) else []
    st.session_state.job_search_position_types = [item for item in cleaned_types if item in JOB_POSITION_FILTER_OPTIONS]
    st.session_state.job_search_posted_within_days = int(filters.get("posted_within_days", 0) or 0)
    st.session_state.job_search_max_results = int(filters.get("max_results", JOB_SEARCH_MAX_RESULTS_DEFAULT) or JOB_SEARCH_MAX_RESULTS_DEFAULT)


def run_agentive_job_search_pipeline(
    resume_text: str,
    target_job_description: str,
    role_query: str,
    preferred_location: str,
    visa_status: str,
    sponsorship_required: bool,
    selected_position_types: list[str],
    posted_within_days: int,
    max_results: int,
) -> dict[str, Any]:
    safe_resume = str(resume_text or "").strip()
    safe_role = re.sub(r"\s+", " ", str(role_query or "").strip())
    safe_location = re.sub(r"\s+", " ", str(preferred_location or "").strip())
    safe_visa_status = str(visa_status or "").strip() or JOB_SEARCH_VISA_STATUSES[0]
    safe_target_jd = str(target_job_description or "").strip()
    safe_types = [
        str(item).strip()
        for item in (selected_position_types or [])
        if str(item).strip() in JOB_POSITION_FILTER_OPTIONS
    ]
    safe_posted_days = max(0, int(posted_within_days or 0))
    safe_limit = max(3, min(JOB_SEARCH_MAX_RESULTS_LIMIT, int(max_results or JOB_SEARCH_MAX_RESULTS_DEFAULT)))

    filters = {
        "role_query": safe_role,
        "preferred_location": safe_location,
        "visa_status": safe_visa_status,
        "sponsorship_required": bool(sponsorship_required),
        "selected_position_types": safe_types,
        "posted_within_days": safe_posted_days,
        "max_results": safe_limit,
    }
    trace: list[str] = []

    if not safe_resume:
        return {
            "ok": False,
            "results": [],
            "error": "Upload or prepare your resume first so ZoSwi can rank jobs by fit.",
            "filters": filters,
            "trace": trace,
        }
    if not safe_role:
        return {
            "ok": False,
            "results": [],
            "error": "Share a target role (for example: Data Engineer) so ZoSwi can run job matching.",
            "filters": filters,
            "trace": trace,
        }

    trace.append("Planned fetch -> date filter -> position filter -> resume + visa ranking.")
    jobs, fetch_msg = fetch_jobs_from_all_sources(
        role_query=safe_role,
        preferred_location=safe_location,
        max_results=safe_limit,
    )
    if not jobs:
        return {
            "ok": False,
            "results": [],
            "error": sanitize_job_search_error_message(fetch_msg or "No jobs found for this search."),
            "filters": filters,
            "trace": trace,
        }

    trace.append(f"Fetched {len(jobs)} jobs from active providers.")
    date_filtered_jobs, posted_msg = filter_jobs_by_posted_within(jobs, safe_posted_days)
    if not date_filtered_jobs:
        combined_error = " ".join(part for part in [fetch_msg, posted_msg] if str(part).strip())
        return {
            "ok": False,
            "results": [],
            "error": sanitize_job_search_error_message(combined_error or "No jobs matched selected filters."),
            "filters": filters,
            "trace": trace,
        }

    trace.append(f"{len(date_filtered_jobs)} jobs remained after posted-date filter.")
    filtered_jobs, position_msg = filter_jobs_by_position_types(date_filtered_jobs, safe_types)
    if not filtered_jobs:
        combined_error = " ".join(part for part in [fetch_msg, posted_msg, position_msg] if str(part).strip())
        return {
            "ok": False,
            "results": [],
            "error": sanitize_job_search_error_message(combined_error or "No jobs matched selected filters."),
            "filters": filters,
            "trace": trace,
        }

    trace.append(f"{len(filtered_jobs)} jobs remained after position-type filter.")
    ranked = rank_jobs_for_candidate(
        resume_text=safe_resume,
        raw_jobs=filtered_jobs,
        preferred_location=safe_location,
        visa_status=safe_visa_status,
        sponsorship_required=bool(sponsorship_required),
        target_job_context=safe_target_jd,
    )
    relevance_filtered, relevance_message = filter_ranked_jobs_by_relevance(
        ranked_jobs=[dict(item) for item in (ranked or []) if isinstance(item, dict)],
        role_query=safe_role,
        max_results=safe_limit,
    )
    ranked_results = relevance_filtered[:safe_limit]
    if not ranked_results:
        return {
            "ok": False,
            "results": [],
            "error": "ZoSwi could not find strong resume-aligned matches. Refine role keywords or widen location.",
            "filters": filters,
            "trace": trace,
        }

    trace.append(f"Ranked {len(ranked_results)} jobs by resume fit + location + sponsorship signal.")
    if str(relevance_message).strip():
        trace.append(str(relevance_message).strip())
    info_message = sanitize_job_search_error_message(
        " ".join(part for part in [fetch_msg, posted_msg, position_msg] if str(part).strip())
    )
    return {
        "ok": True,
        "results": ranked_results,
        "error": info_message,
        "filters": filters,
        "trace": trace,
    }


def format_agentive_job_search_response(search_result: dict[str, Any]) -> str:
    if not bool(search_result.get("ok")):
        return str(search_result.get("error", "No jobs found for this search.")).strip()

    filters = search_result.get("filters", {})
    if not isinstance(filters, dict):
        filters = {}
    results = search_result.get("results", [])
    if not isinstance(results, list):
        results = []

    role_query = str(filters.get("role_query", "")).strip() or "Not specified"
    preferred_location = str(filters.get("preferred_location", "")).strip() or "Any"
    visa_status = str(filters.get("visa_status", "")).strip() or "Not specified"
    sponsorship_required = bool(filters.get("sponsorship_required", False))
    posted_days = int(filters.get("posted_within_days", 0) or 0)
    posted_label = get_posted_within_label(posted_days)
    position_types = filters.get("selected_position_types", [])
    if not isinstance(position_types, list):
        position_types = []
    position_label = ", ".join(str(item).strip() for item in position_types if str(item).strip()) or "All"
    sponsorship_label = "Yes" if sponsorship_required else "No"

    lines: list[str] = []
    lines.append("ZoSwi agentive job match is ready.")
    lines.append(
        f"Filters used: Role={role_query} | Location={preferred_location} | Visa={visa_status} | "
        f"Sponsorship required={sponsorship_label} | Posted={posted_label} | Position types={position_label}"
    )
    lines.append("")
    lines.append("Top matches:")
    for idx, item in enumerate(results[:5], start=1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip() or "Untitled role"
        company = str(item.get("company", "")).strip() or "Unknown company"
        location = str(item.get("location", "")).strip() or "Location not listed"
        posted = format_posted_age(str(item.get("posted_at", "")).strip())
        score = int(item.get("overall_score", 0) or 0)
        sponsorship = str(item.get("sponsorship_status", "")).strip() or "Unknown"
        apply_url = str(item.get("apply_url", "")).strip()
        lines.append(
            f"{idx}. {title} | {company} | {location} | {posted} | Readiness {score}% | Sponsorship {sponsorship}"
        )
        if apply_url:
            lines.append(f"Apply: {apply_url}")
        else:
            lines.append("Apply: URL not listed.")
        missing_points = item.get("missing_points", [])
        if isinstance(missing_points, list) and missing_points:
            first_point = str(missing_points[0]).strip()
            if first_point:
                lines.append(f"Resume boost: {first_point}")

    info_message = str(search_result.get("error", "")).strip()
    if info_message:
        lines.append("")
        lines.append(f"Note: {info_message}")
    lines.append("")
    lines.append("Next move: apply to the top 3 matches first, then iterate based on callback quality.")
    return "\n".join(lines).strip()


def run_agentive_job_search_from_message(message: str, source_profile: str) -> tuple[bool, str]:
    default_filters = {
        "role_query": str(st.session_state.get("job_search_role_query", "")).strip(),
        "preferred_location": str(st.session_state.get("job_search_preferred_location", "")).strip(),
        "visa_status": str(st.session_state.get("job_search_visa_status", JOB_SEARCH_VISA_STATUSES[0])).strip(),
        "sponsorship_required": bool(st.session_state.get("job_search_sponsorship_required", False)),
        "selected_position_types": st.session_state.get("job_search_position_types", []),
        "posted_within_days": int(st.session_state.get("job_search_posted_within_days", 0) or 0),
        "max_results": int(st.session_state.get("job_search_max_results", JOB_SEARCH_MAX_RESULTS_DEFAULT) or JOB_SEARCH_MAX_RESULTS_DEFAULT),
    }
    filters = build_agentive_job_search_filters(message, default_filters)
    apply_agentive_job_filters_to_state(filters)
    resume_text, target_job_description = get_active_careers_profile_context()
    search_result = run_agentive_job_search_pipeline(
        resume_text=resume_text,
        target_job_description=target_job_description,
        role_query=str(filters.get("role_query", "")),
        preferred_location=str(filters.get("preferred_location", "")),
        visa_status=str(filters.get("visa_status", JOB_SEARCH_VISA_STATUSES[0])),
        sponsorship_required=bool(filters.get("sponsorship_required", False)),
        selected_position_types=filters.get("selected_position_types", []),
        posted_within_days=int(filters.get("posted_within_days", 0) or 0),
        max_results=int(filters.get("max_results", JOB_SEARCH_MAX_RESULTS_DEFAULT) or JOB_SEARCH_MAX_RESULTS_DEFAULT),
    )

    ok = bool(search_result.get("ok"))
    results = search_result.get("results", [])
    if not isinstance(results, list):
        results = []
    st.session_state.job_search_results = results if ok else []
    st.session_state.job_search_last_error = sanitize_job_search_error_message(str(search_result.get("error", "")).strip())

    if ok:
        user = st.session_state.get("user") or {}
        user_id = int(user.get("id") or 0)
        if user_id > 0:
            try:
                save_job_search_history(
                    user_id=user_id,
                    source_profile=str(source_profile or "").strip()[:40] or "ZoSwi Agentive",
                    role_query=str(filters.get("role_query", "")),
                    preferred_location=str(filters.get("preferred_location", "")),
                    visa_status=str(filters.get("visa_status", "")),
                    sponsorship_required=bool(filters.get("sponsorship_required", False)),
                    results=results,
                )
            except Exception:
                pass

    response_text = format_agentive_job_search_response(search_result)
    return ok, sanitize_zoswi_response_text(response_text)


def build_application_confidence_snapshot(
    role_query: str,
    preferred_location: str,
    selected_position_types: list[str],
    sponsorship_required: bool,
    resume_text: str,
    target_job_description: str,
) -> dict[str, Any]:
    analysis_score = get_careers_analysis_score(resume_text, target_job_description)
    has_resume = bool(str(resume_text or "").strip())
    has_jd = bool(str(target_job_description or "").strip())
    has_role = bool(str(role_query or "").strip())
    has_location = bool(str(preferred_location or "").strip())
    selected_types = [str(item).strip() for item in (selected_position_types or []) if str(item).strip()]
    has_position_type = bool(selected_types)

    confidence = int(round(analysis_score * 0.62))
    if has_resume:
        confidence += 10
    if has_jd:
        confidence += 8
    if has_role:
        confidence += 8
    if has_location:
        confidence += 5
    if has_position_type:
        confidence += 5
    if sponsorship_required and analysis_score < 65:
        confidence -= 6
    confidence = max(0, min(100, confidence))

    if confidence >= 80:
        band = "High"
        summary = "Strong profile and filters. Proceed with confident applications."
    elif confidence >= 60:
        band = "Medium"
        summary = "Good readiness. Tighten filters and resume alignment for better outcomes."
    else:
        band = "Build-Up"
        summary = "Strengthen your resume with measurable achievements and ATS keywords before broad applying."

    next_steps: list[str] = []
    if has_resume:
        next_steps.append("Add 2-3 impact bullets with metrics (time saved, revenue, or efficiency gains).")
        next_steps.append("Mirror top role keywords in your resume headline, summary, and skills section.")
    else:
        next_steps.append("Upload your latest resume to unlock tailored scoring and stronger recommendations.")
    if not has_role:
        next_steps.append("Set a precise target role and align resume title to the same role.")
    if not has_location:
        next_steps.append("Set a preferred location or Remote.")
    if not has_position_type:
        next_steps.append("Pick position types like Full-Time or Contract.")
    if sponsorship_required:
        next_steps.append("Prioritize jobs with clear sponsorship wording.")
    if not next_steps:
        next_steps.append("Use Find My Best Matches and apply to top readiness roles first.")

    return {
        "score": confidence,
        "band": band,
        "summary": summary,
        "next_steps": next_steps[:3],
        "analysis_score": analysis_score,
    }


def render_application_confidence_card(
    role_query: str,
    preferred_location: str,
    selected_position_types: list[str],
    sponsorship_required: bool,
    resume_text: str,
    target_job_description: str,
) -> None:
    snapshot = build_application_confidence_snapshot(
        role_query=role_query,
        preferred_location=preferred_location,
        selected_position_types=selected_position_types,
        sponsorship_required=sponsorship_required,
        resume_text=resume_text,
        target_job_description=target_job_description,
    )
    score = int(snapshot.get("score", 0) or 0)
    band = str(snapshot.get("band", "Medium")).strip()
    summary = str(snapshot.get("summary", "")).strip()
    analysis_score = int(snapshot.get("analysis_score", 0) or 0)
    next_steps = snapshot.get("next_steps", [])
    if not isinstance(next_steps, list):
        next_steps = []
    next_line = " ".join(str(item).strip() for item in next_steps if str(item).strip())
    if not next_line:
        next_line = "Use Find My Best Matches and apply to top readiness roles first."

    band_color = "#0ea5e9"
    if band == "High":
        band_color = "#16a34a"
    elif band == "Build-Up":
        band_color = "#ea580c"

    st.markdown(
        f"""
        <div style="
            border:1px solid #c7d2fe;
            border-radius:14px;
            padding:0.62rem 0.74rem;
            background:linear-gradient(140deg,#0b1220 0%, #111f36 68%, #0f2a48 100%);
            color:#e2e8f0;
            margin:0.3rem auto 0.8rem auto;
            max-width:780px;
        ">
            <div style="display:flex;justify-content:space-between;align-items:center;gap:0.8rem;">
                <div style="font-size:0.78rem;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;color:#a5f3fc;">
                    Application Confidence
                </div>
                <div style="
                    font-size:0.68rem;
                    font-weight:700;
                    background:{band_color};
                    color:#ffffff;
                    border-radius:999px;
                    padding:0.2rem 0.55rem;
                    white-space:nowrap;
                ">
                    {html.escape(band)} Mode
                </div>
            </div>
            <div style="margin-top:0.55rem;display:flex;justify-content:space-between;align-items:flex-end;gap:0.8rem;">
                <div style="font-size:1.18rem;font-weight:800;color:#f8fafc;">{score}%</div>
                <div style="font-size:0.78rem;color:#93c5fd;">Resume-JD base score: {analysis_score}%</div>
            </div>
            <div style="margin-top:0.35rem;height:8px;background:rgba(148,163,184,0.25);border-radius:999px;overflow:hidden;">
                <div style="height:8px;width:{score}%;background:linear-gradient(90deg,#22d3ee 0%, {band_color} 100%);"></div>
            </div>
            <div style="margin-top:0.55rem;font-size:0.84rem;line-height:1.35;color:#e2e8f0;">
                {html.escape(summary)}
            </div>
            <div style="margin-top:0.38rem;font-size:0.79rem;line-height:1.35;color:#bfdbfe;">
                Next: {html.escape(next_line)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def get_active_careers_profile_context() -> tuple[str, str]:
    use_custom_profile = bool(st.session_state.get("careers_use_custom_profile", False))
    careers_resume = str(st.session_state.get("careers_resume_text", "")).strip()
    careers_jd = str(st.session_state.get("careers_target_job_description", "")).strip()
    if use_custom_profile and careers_resume:
        return careers_resume, careers_jd

    fallback_resume = str(st.session_state.get("latest_resume_text", "")).strip()
    fallback_jd = str(st.session_state.get("latest_job_description", "")).strip()
    return fallback_resume, fallback_jd


def get_careers_analysis_score(resume_text: str = "", target_job_description: str = "") -> int:
    use_custom_profile = bool(st.session_state.get("careers_use_custom_profile", False))
    if not use_custom_profile:
        analysis = st.session_state.get("analysis_result")
        if isinstance(analysis, dict):
            try:
                return max(0, min(100, int(analysis.get("score", 0))))
            except Exception:
                pass

    has_resume = bool(str(resume_text or "").strip())
    has_jd = bool(str(target_job_description or "").strip())
    if has_resume and has_jd:
        try:
            fallback_score = int(fallback_analysis(str(resume_text), str(target_job_description)).get("score", 0))
            return max(0, min(100, fallback_score))
        except Exception:
            return 58
    if has_resume:
        return 52
    return 0


def render_careers_profile_setup() -> None:
    from src.ui.pages.careers_page import render_careers_profile_setup as _impl

    return _impl()

def render_careers_motivation_hero(full_name: str, analysis_score: int) -> None:
    from src.ui.pages.careers_page import render_careers_motivation_hero as _impl

    return _impl(full_name, analysis_score)

def infer_sponsorship_status(job_text: str) -> tuple[str, int, str]:
    text = str(job_text or "").lower()
    if not text.strip():
        return "Unknown", 35, "Job posting does not mention visa sponsorship details."

    positive_signals = (
        "h-1b",
        "h1b",
        "visa sponsorship available",
        "sponsorship available",
        "sponsor transfer",
        "immigration support",
        "work visa support",
    )
    negative_signals = (
        "no sponsorship",
        "without sponsorship",
        "cannot sponsor",
        "unable to sponsor",
        "not provide sponsorship",
        "not eligible for sponsorship",
        "authorized to work in the us without sponsorship",
        "without the need for sponsorship",
        "no visa sponsorship",
    )

    has_positive = any(signal in text for signal in positive_signals)
    has_negative = any(signal in text for signal in negative_signals)
    if has_negative and has_positive:
        return "Unclear", 55, "Posting contains mixed sponsorship signals; verify with recruiter."
    if has_negative:
        return "No Sponsorship", 90, "Posting explicitly says sponsorship is not offered."
    if has_positive:
        return "Likely Sponsors H1B", 82, "Posting indicates visa/H1B sponsorship language."
    return "Unknown", 40, "No explicit sponsorship policy found in posting."


def score_location_fit(preferred_location: str, job_location: str) -> tuple[int, str]:
    preferred = str(preferred_location or "").strip().lower()
    location = str(job_location or "").strip().lower()
    if not preferred:
        return 10, "No location preference provided."
    if not location:
        return 7, "Job location not listed."
    if preferred in location:
        return 15, "Job location matches your preferred location."
    if "remote" in location and ("remote" in preferred or "any" in preferred):
        return 15, "Remote job aligns with your location preference."
    if "remote" in location:
        return 12, "Remote role can still work despite location mismatch."
    return 4, "Job location differs from your preferred location."


def estimate_role_relevance(role_query: str, title: str, description: str) -> int:
    query = re.sub(r"\s+", " ", str(role_query or "").strip().lower())
    if not query:
        return 50
    text = " ".join([str(title or "").lower(), str(description or "").lower()])
    if not text.strip():
        return 0
    if query in text:
        return 100
    tokens = [tok for tok in re.findall(r"[a-zA-Z0-9+#.\-]{3,}", query) if tok]
    if not tokens:
        return 50
    matched = sum(1 for tok in tokens if tok in text)
    base = int(round((matched / max(1, len(tokens))) * 100))
    # Slight boost when at least one meaningful role token appears in title itself.
    title_lower = str(title or "").lower()
    if any(tok in title_lower for tok in tokens):
        base = min(100, base + 10)
    return max(0, min(100, base))


def filter_ranked_jobs_by_relevance(
    ranked_jobs: list[dict[str, Any]],
    role_query: str,
    max_results: int,
) -> tuple[list[dict[str, Any]], str]:
    safe_jobs = [dict(item) for item in ranked_jobs if isinstance(item, dict)]
    if not safe_jobs:
        return [], ""

    for job in safe_jobs:
        role_relevance = estimate_role_relevance(
            role_query=role_query,
            title=str(job.get("title", "")).strip(),
            description=str(job.get("job_text_for_relevance", "")).strip(),
        )
        job["role_relevance"] = role_relevance

    strict: list[dict[str, Any]] = []
    relaxed: list[dict[str, Any]] = []
    for job in safe_jobs:
        resume_score = int(job.get("resume_match_score", 0) or 0)
        role_score = int(job.get("role_relevance", 0) or 0)
        if resume_score >= JOB_SEARCH_MIN_RESUME_MATCH_STRICT and role_score >= JOB_SEARCH_MIN_ROLE_RELEVANCE_STRICT:
            strict.append(job)
        if resume_score >= JOB_SEARCH_MIN_RESUME_MATCH_RELAXED and role_score >= JOB_SEARCH_MIN_ROLE_RELEVANCE_RELAXED:
            relaxed.append(job)

    if len(strict) >= max(2, min(4, int(max_results or JOB_SEARCH_MAX_RESULTS_DEFAULT))):
        return strict, ""
    if relaxed:
        return relaxed, ""
    return safe_jobs, ""


def get_resume_job_match_score(resume_text: str, job_description: str, allow_ai: bool = True) -> tuple[int, str]:
    jd = str(job_description or "").strip()
    if not jd:
        return 0, "Job description text was unavailable for resume matching."

    use_ai = bool(allow_ai and get_zoswiai_key())
    if use_ai:
        try:
            result = analyze_resume_with_ai(resume_text, jd)
            score = max(0, min(100, int(result.get("score", 0))))
            summary = str(result.get("summary", "")).strip()
            return score, summary or "AI match score calculated from resume and job text."
        except Exception:
            pass

    fallback = fallback_analysis(resume_text, jd)
    score = max(0, min(100, int(fallback.get("score", 0))))
    summary = str(fallback.get("summary", "")).strip()
    return score, summary or "Heuristic resume-to-job match score calculated."


def extract_resume_keyword_gaps(resume_text: str, job_text: str, limit: int = 5) -> list[str]:
    resume_lower = str(resume_text or "").lower()
    job_lower = str(job_text or "").lower()
    if not resume_lower or not job_lower:
        return []

    token_pattern = re.compile(r"[a-zA-Z][a-zA-Z0-9+#.\-]{2,}")
    resume_tokens = set(token_pattern.findall(resume_lower))
    job_tokens = token_pattern.findall(job_lower)
    if not job_tokens:
        return []

    stop_words = {
        "with",
        "from",
        "that",
        "this",
        "will",
        "must",
        "have",
        "work",
        "team",
        "role",
        "jobs",
        "using",
        "years",
        "year",
        "experience",
        "strong",
        "ability",
        "skills",
        "knowledge",
        "required",
        "preferred",
        "build",
        "design",
        "develop",
        "engineer",
        "engineering",
        "software",
    }

    freq: dict[str, int] = {}
    for token in job_tokens:
        clean = token.lower().strip(".-")
        if not clean or clean in stop_words:
            continue
        if clean in resume_tokens:
            continue
        if len(clean) < 4:
            continue
        if clean.isdigit():
            continue
        freq[clean] = freq.get(clean, 0) + 1

    ranked = sorted(freq.items(), key=lambda item: (-item[1], -len(item[0]), item[0]))
    return [token for token, _ in ranked[: max(1, int(limit or 1))]]


def build_resume_missing_points(
    resume_text: str,
    job_row: dict[str, Any],
    target_job_context: str = "",
    limit: int = 3,
) -> list[str]:
    safe_resume = str(resume_text or "").strip()
    if not safe_resume:
        return ["Upload your latest resume to generate tailored missing points before applying."]

    description = str(job_row.get("description", "")).strip()
    title = str(job_row.get("title", "")).strip()
    company = str(job_row.get("company", "")).strip()
    job_text = "\n".join(
        part for part in [title, company, description, str(target_job_context or "").strip()] if str(part).strip()
    )

    points: list[str] = []
    missing_keywords = extract_resume_keyword_gaps(safe_resume, job_text, limit=4)
    if missing_keywords:
        points.append(
            "Add these relevant keywords where accurate: " + ", ".join(missing_keywords[:4]) + "."
        )

    top_skills = extract_top_technical_skills(safe_resume, job_text, limit=6)
    missing_skills: list[str] = []
    resume_lower = safe_resume.lower()
    for skill in top_skills:
        if str(skill).lower() not in resume_lower:
            missing_skills.append(str(skill))
    if missing_skills:
        points.append(
            "If you used them, add evidence for: " + ", ".join(missing_skills[:3]) + " in Projects/Experience."
        )

    if not re.search(r"\d", safe_resume):
        points.append("Add 2 measurable bullets with numbers (impact, %, time saved, revenue, scale).")
    else:
        points.append("Strengthen 1-2 bullets with clearer business impact and ownership.")

    normalized_points: list[str] = []
    seen: set[str] = set()
    for item in points:
        clean = re.sub(r"\s+", " ", str(item).strip())
        if not clean:
            continue
        lower = clean.lower()
        if lower in seen:
            continue
        seen.add(lower)
        normalized_points.append(clean)
    return normalized_points[: max(1, int(limit or 1))]


def evaluate_job_lead_for_candidate(
    resume_text: str,
    job_row: dict[str, Any],
    preferred_location: str,
    visa_status: str,
    sponsorship_required: bool,
    target_job_context: str = "",
    allow_ai: bool = True,
) -> dict[str, Any]:
    description = str(job_row.get("description", "")).strip()
    title = str(job_row.get("title", "")).strip()
    company = str(job_row.get("company", "")).strip()
    location = str(job_row.get("location", "")).strip()
    apply_url = str(job_row.get("apply_url", "")).strip()
    posted_at = normalize_posted_at(job_row.get("posted_at", ""))
    combined_text = f"{title}\n{company}\n{location}\n{description}"

    match_context = description or combined_text
    target_context = str(target_job_context or "").strip()
    if target_context:
        match_context = f"Candidate target role context:\n{target_context}\n\nLive job posting:\n{match_context}"

    resume_match_score, resume_summary = get_resume_job_match_score(resume_text, match_context, allow_ai=allow_ai)
    sponsorship_status, sponsorship_confidence, sponsorship_note = infer_sponsorship_status(combined_text)
    location_score, location_note = score_location_fit(preferred_location, location)

    if sponsorship_required:
        if sponsorship_status == "Likely Sponsors H1B":
            visa_score = 15
        elif sponsorship_status == "No Sponsorship":
            visa_score = 0
        else:
            visa_score = 7
    else:
        visa_score = 15 if sponsorship_status != "No Sponsorship" else 10

    weighted_resume = int(round(resume_match_score * 0.7))
    overall_score = max(0, min(100, weighted_resume + location_score + visa_score))
    visa_profile = str(visa_status or "").strip() or "Not specified"
    raw_position_tags = job_row.get("position_tags", [])
    if not isinstance(raw_position_tags, list):
        raw_position_tags = []
    position_tags = [str(tag).strip() for tag in raw_position_tags if str(tag).strip()]
    if not position_tags:
        position_tags = infer_job_position_tags(job_row)
    readiness_reason = (
        f"{location_note} {sponsorship_note} Visa profile: {visa_profile}. "
        f"Resume fit: {resume_summary[:180]}"
    ).strip()
    missing_points = build_resume_missing_points(
        resume_text=resume_text,
        job_row=job_row,
        target_job_context=target_context,
        limit=3,
    )

    return {
        "title": title or "Untitled role",
        "company": company or "Unknown company",
        "location": location or "Location not listed",
        "apply_url": apply_url,
        "posted_at": posted_at,
        "source": str(job_row.get("source", "")).strip() or "External API",
        "resume_match_score": resume_match_score,
        "sponsorship_status": sponsorship_status,
        "sponsorship_confidence": sponsorship_confidence,
        "overall_score": overall_score,
        "position_tags": position_tags,
        "reason": readiness_reason[:360],
        "missing_points": missing_points,
        "job_text_for_relevance": (description or combined_text)[:1200],
    }


def rank_jobs_for_candidate(
    resume_text: str,
    raw_jobs: list[dict[str, Any]],
    preferred_location: str,
    visa_status: str,
    sponsorship_required: bool,
    target_job_context: str = "",
) -> list[dict[str, Any]]:
    valid_jobs = [job for job in raw_jobs if isinstance(job, dict)]
    if not valid_jobs:
        return []

    ai_indices: set[int] = set()
    if bool(get_zoswiai_key()):
        ai_limit = max(1, min(JOB_SEARCH_MAX_AI_EVALUATIONS, JOB_SEARCH_MAX_RESULTS_LIMIT))
        if len(valid_jobs) <= ai_limit:
            ai_indices = set(range(len(valid_jobs)))
        else:
            resume_tokens = set(re.findall(r"[a-zA-Z]{3,}", str(resume_text or "").lower()))
            candidate_scores: list[tuple[int, int]] = []
            for idx, job in enumerate(valid_jobs):
                title = str(job.get("title", "")).strip()
                company = str(job.get("company", "")).strip()
                location = str(job.get("location", "")).strip()
                description = str(job.get("description", "")).strip()
                combined_text = f"{title}\n{company}\n{location}\n{description}"
                jd_tokens = set(re.findall(r"[a-zA-Z]{3,}", combined_text.lower()))
                overlap_ratio = 0
                if resume_tokens and jd_tokens:
                    overlap_ratio = int((len(resume_tokens.intersection(jd_tokens)) / len(jd_tokens)) * 100)
                sponsorship_status, sponsorship_confidence, _ = infer_sponsorship_status(combined_text)
                location_points, _ = score_location_fit(preferred_location, location)
                if sponsorship_required:
                    sponsorship_points = 12 if sponsorship_status == "Likely Sponsors H1B" else 0
                else:
                    sponsorship_points = 8 if sponsorship_status != "No Sponsorship" else 2
                rough_score = int(round(overlap_ratio * 0.7)) + location_points + sponsorship_points + int(
                    sponsorship_confidence * 0.03
                )
                candidate_scores.append((rough_score, idx))
            candidate_scores.sort(reverse=True)
            ai_indices = {idx for _, idx in candidate_scores[:ai_limit]}

    ranked: list[dict[str, Any]] = []
    worker_count = max(1, min(JOB_SEARCH_SCORING_MAX_WORKERS, len(valid_jobs)))
    if worker_count == 1:
        for idx, raw_job in enumerate(valid_jobs):
            ranked.append(
                evaluate_job_lead_for_candidate(
                    resume_text=resume_text,
                    job_row=raw_job,
                    preferred_location=preferred_location,
                    visa_status=visa_status,
                    sponsorship_required=sponsorship_required,
                    target_job_context=target_job_context,
                    allow_ai=(idx in ai_indices),
                )
            )
    else:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(
                    evaluate_job_lead_for_candidate,
                    resume_text=resume_text,
                    job_row=raw_job,
                    preferred_location=preferred_location,
                    visa_status=visa_status,
                    sponsorship_required=sponsorship_required,
                    target_job_context=target_job_context,
                    allow_ai=(idx in ai_indices),
                ): idx
                for idx, raw_job in enumerate(valid_jobs)
            }
            for future in as_completed(futures):
                idx = futures[future]
                raw_job = valid_jobs[idx]
                try:
                    ranked.append(future.result())
                except Exception:
                    try:
                        ranked.append(
                            evaluate_job_lead_for_candidate(
                                resume_text=resume_text,
                                job_row=raw_job,
                                preferred_location=preferred_location,
                                visa_status=visa_status,
                                sponsorship_required=sponsorship_required,
                                target_job_context=target_job_context,
                                allow_ai=False,
                            )
                        )
                    except Exception:
                        continue
    ranked.sort(
        key=lambda item: (
            int(item.get("overall_score", 0) or 0),
            int(item.get("resume_match_score", 0) or 0),
            int(item.get("sponsorship_confidence", 0) or 0),
        ),
        reverse=True,
    )
    return ranked[:JOB_SEARCH_MAX_RESULTS_LIMIT]


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


def normalize_image_tool_size(raw_size: str) -> str:
    cleaned = str(raw_size or "").strip()
    if cleaned in IMAGE_TOOL_GENERATE_SIZES:
        return cleaned
    return IMAGE_TOOL_GENERATE_SIZES[0]


def apply_zoswi_watermark_to_image(image_bytes: bytes) -> bytes:
    if not image_bytes:
        return image_bytes
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return image_bytes

    try:
        with Image.open(io.BytesIO(image_bytes)) as source_img:
            output_format = str(source_img.format or "PNG").upper()
            base = source_img.convert("RGBA")
            width, height = base.size
            if width < 64 or height < 64:
                return image_bytes

            padding = max(10, min(width, height) // 45)
            font_size = max(14, min(width, height) // 28)
            try:
                font = ImageFont.truetype("arial.ttf", font_size)
            except Exception:
                font = ImageFont.load_default()

            label = "ZoSwi"
            measure = ImageDraw.Draw(base)
            if hasattr(measure, "textbbox"):
                bbox = measure.textbbox((0, 0), label, font=font)
                text_w = max(1, bbox[2] - bbox[0])
                text_h = max(1, bbox[3] - bbox[1])
            else:
                legacy_w, legacy_h = measure.textsize(label, font=font)
                text_w = max(1, int(legacy_w))
                text_h = max(1, int(legacy_h))

            text_x = max(padding, width - text_w - padding)
            text_y = max(padding, height - text_h - padding)

            overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            draw.text((text_x + 1, text_y + 1), label, font=font, fill=(2, 6, 23, 78))
            draw.text((text_x, text_y), label, font=font, fill=(248, 250, 252, 114))
            composed = Image.alpha_composite(base, overlay)

            output = io.BytesIO()
            if output_format in {"JPEG", "JPG"}:
                composed.convert("RGB").save(output, format="JPEG", quality=94, optimize=True)
            elif output_format == "WEBP":
                composed.save(output, format="WEBP", quality=94)
            else:
                composed.save(output, format="PNG")
            return output.getvalue()
    except Exception:
        return image_bytes


def convert_image_bytes_to_format(
    image_bytes: bytes,
    target_format: str,
    quality: int = 92,
) -> tuple[bool, bytes, str, str]:
    if not image_bytes:
        return False, b"", "", "Upload an image first."

    normalized_format = str(target_format or "").strip().upper()
    if normalized_format not in IMAGE_TOOL_TARGET_FORMATS:
        return False, b"", "", "Choose a valid output format."

    try:
        from PIL import Image
    except Exception:
        return (
            False,
            b"",
            "",
            "Image conversion requires Pillow. Install with: pip install pillow",
        )

    output_buffer = io.BytesIO()
    try:
        with Image.open(io.BytesIO(image_bytes)) as source_img:
            if normalized_format == "JPEG" and source_img.mode not in {"RGB", "L"}:
                source_img = source_img.convert("RGB")
            save_kwargs: dict[str, Any] = {}
            if normalized_format in {"JPEG", "WEBP"}:
                bounded_quality = max(40, min(98, int(quality or 92)))
                save_kwargs["quality"] = bounded_quality
            if normalized_format == "JPEG":
                save_kwargs["optimize"] = True
            source_img.save(output_buffer, format=normalized_format, **save_kwargs)
    except Exception:
        return False, b"", "", "Could not convert this image. Try a different file."

    mime_by_format = {
        "PNG": "image/png",
        "JPEG": "image/jpeg",
        "WEBP": "image/webp",
    }
    ext_by_format = {
        "PNG": "png",
        "JPEG": "jpg",
        "WEBP": "webp",
    }
    return True, output_buffer.getvalue(), mime_by_format[normalized_format], ext_by_format[normalized_format]


def generate_image_with_zoswiai(
    prompt: str,
    size: str,
    style_name: str,
) -> tuple[bool, bytes, str]:
    clean_prompt = str(prompt or "").strip()
    if len(clean_prompt) < 8:
        return False, b"", "Add a clearer prompt (at least 8 characters)."

    key = get_zoswiai_key()
    if not key:
        return False, b"", "ZOSWI_AI_API_KEY is required for image creation."

    normalized_size = normalize_image_tool_size(size)
    style_note = IMAGE_TOOL_STYLE_NOTES.get(str(style_name or "").strip(), IMAGE_TOOL_STYLE_NOTES["Professional"])
    enriched_prompt = (
        f"{clean_prompt}\n\n"
        f"Style preference: {style_note}. "
        "Do not include text overlays or watermarks unless explicitly requested."
    )

    try:
        client = ZoSwiAIClient(api_key=key)
        result = client.images.generate(
            model="gpt-image-1",
            prompt=enriched_prompt,
            size=normalized_size,
            n=1,
        )
    except Exception as ex:
        return False, b"", f"Image generation failed: {str(ex).strip()[:180]}"

    if not getattr(result, "data", None):
        return False, b"", "No image was returned by the model."
    first_item = result.data[0]
    b64_payload = str(getattr(first_item, "b64_json", "") or "").strip()
    if b64_payload:
        try:
            raw_image = base64.b64decode(b64_payload)
            return True, apply_zoswi_watermark_to_image(raw_image), ""
        except Exception:
            return False, b"", "Model returned unreadable image content."

    remote_url = str(getattr(first_item, "url", "") or "").strip()
    if not remote_url:
        return False, b"", "Image payload was empty."
    try:
        request = Request(remote_url, headers={"User-Agent": "ZoSwi/1.0"})
        with urlopen(request, timeout=25) as response:
            payload = response.read()
        if not payload:
            return False, b"", "Downloaded image was empty."
        return True, apply_zoswi_watermark_to_image(payload), ""
    except Exception:
        return False, b"", "Could not download generated image."


def is_supported_image_file_name(file_name: str) -> bool:
    ext = os.path.splitext(str(file_name or "").strip().lower())[1]
    return ext in AI_WORKSPACE_IMAGE_EXTENSIONS


def infer_image_mime_type_from_file_name(file_name: str) -> str:
    ext = os.path.splitext(str(file_name or "").strip().lower())[1]
    mime_by_ext = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".tiff": "image/tiff",
    }
    return mime_by_ext.get(ext, "image/png")


def is_ai_workspace_18plus_request(text: str) -> bool:
    lowered = re.sub(r"\s+", " ", str(text or "").strip().lower())
    if not lowered:
        return False
    explicit_markers = [
        "porn",
        "porno",
        "xxx",
        "nsfw",
        "nude",
        "naked",
        "sex video",
        "sexual content",
        "explicit sex",
        "erotic",
        "onlyfans",
        "fetish",
        "adult content",
        "18+",
    ]
    return any(marker in lowered for marker in explicit_markers)


def is_ai_workspace_image_generation_request(text: str) -> bool:
    lowered = re.sub(r"\s+", " ", str(text or "").strip().lower())
    if not lowered:
        return False
    if is_ai_workspace_image_conversion_request(lowered):
        return False
    action_terms = [
        "generate",
        "generated",
        "generation",
        "create",
        "creation",
        "make",
        "draw",
        "design",
        "build",
        "render",
    ]
    object_terms = ["image", "picture", "photo", "visual", "illustration", "logo", "banner", "poster"]
    has_action = any(term in lowered for term in action_terms)
    has_object = any(term in lowered for term in object_terms)
    has_creation_phrase = bool(
        re.search(r"\b(image|picture|photo|visual|illustration|logo|banner|poster)\s+(creation|generation)\b", lowered)
    )
    command_prefixes = ["/image", "image:", "img:"]
    has_command_prefix = any(lowered.startswith(prefix) for prefix in command_prefixes)
    return bool((has_object and has_action) or has_creation_phrase or has_command_prefix)


def is_ai_workspace_image_creation_command(text: str) -> bool:
    lowered = re.sub(r"\s+", " ", str(text or "").strip().lower())
    if not lowered:
        return False
    action_terms = [
        "generate",
        "generated",
        "generation",
        "create",
        "creation",
        "make",
        "draw",
        "design",
        "build",
        "render",
    ]
    object_terms = ["image", "picture", "photo", "visual", "illustration", "logo", "banner", "poster"]
    has_creation_phrase = bool(
        re.search(r"\b(image|picture|photo|visual|illustration|logo|banner|poster)\s+(creation|generation)\b", lowered)
    )
    return bool(
        (any(term in lowered for term in action_terms) and any(term in lowered for term in object_terms))
        or has_creation_phrase
    )


def is_ai_workspace_image_conversion_request(text: str) -> bool:
    lowered = re.sub(r"\s+", " ", str(text or "").strip().lower())
    if not lowered:
        return False
    convert_terms = [
        "convert",
        "change format",
        "export as",
        "save as",
        "to png",
        "to jpg",
        "to jpeg",
        "to webp",
        "as png",
        "as jpg",
        "as jpeg",
        "as webp",
    ]
    return any(term in lowered for term in convert_terms)


def infer_image_convert_target_format(text: str) -> str:
    lowered = str(text or "").strip().lower()
    if "webp" in lowered:
        return "WEBP"
    if "jpg" in lowered or "jpeg" in lowered:
        return "JPEG"
    return "PNG"


def infer_image_generation_size(text: str) -> str:
    lowered = str(text or "").strip().lower()
    if "1536x1024" in lowered or "landscape" in lowered or "wide" in lowered:
        return "1536x1024"
    if "1024x1536" in lowered or "portrait" in lowered or "vertical" in lowered:
        return "1024x1536"
    return "1024x1024"


def infer_image_generation_style(text: str) -> str:
    lowered = str(text or "").strip().lower()
    if "photo" in lowered or "realistic" in lowered:
        return "Photorealistic"
    if "illustration" in lowered or "cartoon" in lowered or "vector" in lowered:
        return "Illustration"
    if "minimal" in lowered or "clean" in lowered:
        return "Minimal"
    return "Professional"


def analyze_uploaded_image_with_ai(
    image_bytes: bytes,
    file_name: str,
    user_prompt: str,
) -> tuple[bool, str]:
    if not image_bytes:
        return False, "Uploaded image is empty."
    key = get_zoswiai_key()
    if not key:
        return False, "ZOSWI_AI_API_KEY is required for image understanding."

    prompt_text = str(user_prompt or "").strip()
    if not prompt_text:
        prompt_text = (
            "Summarize this image in a professional way. "
            "Highlight key visible details and practical next steps."
        )

    if is_ai_workspace_18plus_request(prompt_text):
        return False, AI_WORKSPACE_ADULT_BLOCK_MESSAGE

    mime_type = infer_image_mime_type_from_file_name(file_name)
    image_data_uri = build_image_data_uri(image_bytes, mime_type)
    if not image_data_uri:
        return False, "Could not read image data."

    system_text = (
        f"You are {ZOSWI_LIVE_WORKSPACE_NAME}. Provide direct, professional, actionable responses. "
        "If request or image is explicit sexual / 18+ content, refuse briefly and redirect to safe support. "
        "Do not mention or compare other AI assistants or applications by name. "
        "Do not recommend third-party apps/software; keep guidance ZoSwi-native."
    )

    try:
        client = ZoSwiAIClient(api_key=key)
        response = client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_text}],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt_text},
                        {"type": "input_image", "image_url": image_data_uri},
                    ],
                },
            ],
            max_output_tokens=320,
        )
        output_text = str(getattr(response, "output_text", "") or "").strip()
        if output_text:
            return True, sanitize_zoswi_response_text(output_text)
    except Exception:
        pass

    try:
        client = ZoSwiAIClient(api_key=key)
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_text},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {"type": "image_url", "image_url": {"url": image_data_uri}},
                    ],
                },
            ],
            max_tokens=320,
        )
        message_content = completion.choices[0].message.content if completion and completion.choices else ""
        if isinstance(message_content, str) and message_content.strip():
            return True, sanitize_zoswi_response_text(message_content.strip())
    except Exception:
        pass

    return False, "I could not analyze that image right now. Please try again."


def extract_ai_workspace_file_text(uploaded_file, max_chars: int = AI_WORKSPACE_FILE_MAX_CHARS) -> tuple[bool, str, str]:
    if uploaded_file is None:
        return False, "", "Select a file first."

    file_name = str(getattr(uploaded_file, "name", "") or "uploaded_file").strip() or "uploaded_file"
    ext = os.path.splitext(file_name.lower())[1]
    file_bytes = uploaded_file.getvalue()
    if not file_bytes:
        return False, "", "Uploaded file is empty."

    try:
        if ext == ".pdf":
            raw_text = extract_pdf_text(file_bytes)
        elif ext == ".docx":
            raw_text = extract_docx_text(file_bytes)
        else:
            if b"\x00" in file_bytes[:4096]:
                return False, "", "Binary file is not supported for insert. Upload text, PDF, or DOCX."
            raw_text = file_bytes.decode("utf-8", errors="ignore")
            if not raw_text.strip():
                raw_text = file_bytes.decode("latin-1", errors="ignore")
    except Exception:
        return False, "", "Could not read file content. Please upload a text-readable file."

    cleaned = str(raw_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not cleaned:
        return False, "", "No readable text found in the file."

    max_len = max(1000, int(max_chars or AI_WORKSPACE_FILE_MAX_CHARS))
    if len(cleaned) > max_len:
        clipped = cleaned[:max_len].rstrip()
        return True, clipped + "\n...[truncated]...", f"{file_name} inserted (truncated for prompt safety)."
    return True, cleaned, f"{file_name} inserted."


def add_ai_workspace_attachment(file_name: str, file_text: str) -> None:
    clean_name = str(file_name or "uploaded_file").strip() or "uploaded_file"
    clean_text = str(file_text or "").strip()
    if not clean_text:
        return

    digest = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()
    attachments = st.session_state.get("ai_workspace_attachments", [])
    if not isinstance(attachments, list):
        attachments = []

    filtered: list[dict[str, str]] = []
    for item in attachments:
        if not isinstance(item, dict):
            continue
        if str(item.get("digest", "")).strip() == digest:
            continue
        filtered.append(
            {
                "name": str(item.get("name", "")).strip() or "uploaded_file",
                "text": str(item.get("text", "")).strip(),
                "digest": str(item.get("digest", "")).strip(),
                "added_at": str(item.get("added_at", "")).strip(),
            }
        )

    filtered.append(
        {
            "name": clean_name,
            "text": clean_text,
            "digest": digest,
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    st.session_state.ai_workspace_attachments = filtered[-5:]


def build_ai_workspace_attachment_context(max_files: int = 3, max_chars_per_file: int = 2200) -> str:
    attachments = st.session_state.get("ai_workspace_attachments", [])
    if not isinstance(attachments, list) or not attachments:
        return ""

    files = attachments[-max(1, int(max_files or 1)) :]
    blocks: list[str] = []
    char_limit = max(500, int(max_chars_per_file or 2200))
    for item in files:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip() or "uploaded_file"
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        trimmed = text[:char_limit].rstrip()
        if len(text) > char_limit:
            trimmed += "\n...[truncated]..."
        blocks.append(f"[Attachment: {name}]\n{trimmed}")
    return "\n\n".join(blocks)


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
        cleaned = re.sub(r"\s+", " ", str(raw or "")).strip(" \t-â€¢*")
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
        cleaned = re.sub(r"\s+", " ", str(point or "")).strip().strip("-â€¢* ")
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

    key = get_zoswiai_key()
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
        llm = ZoSwiAIChat(model="gpt-4o-mini", temperature=0.2, api_key=key)
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
        cleaned = re.sub(r"^\s*[-*â€¢]+\s*", "", str(line or "")).strip()
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
        additions.append(make_paragraph(f"â€¢ {point}"))
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


def get_zoswiai_key() -> str | None:
    key_from_db = get_db_setting_value("ZOSWI_AI_API_KEY")
    if key_from_db:
        return key_from_db
    key_from_env = str(os.getenv("ZOSWI_AI_API_KEY", "")).strip()
    return key_from_env or None


def time_based_greeting() -> str:
    # Use local system time so greeting matches the user's device/browser context.
    hour = datetime.now().astimezone().hour
    if 5 <= hour < 12:
        return "Good morning"
    if 12 <= hour < 17:
        return "Good afternoon"
    return "Good evening"


def get_zoswi_success_motivation_quotes(limit: int = 100) -> list[str]:
    cleaned = [str(item).strip() for item in ZOSWI_SUCCESS_MOTIVATION_QUOTES if str(item).strip()]
    if not cleaned:
        cleaned = ["Keep moving forward with discipline and focus. - ZoSwi"]
    if len(cleaned) >= limit:
        return cleaned[:limit]
    padded = list(cleaned)
    source_len = len(cleaned)
    for index in range(limit - source_len):
        padded.append(cleaned[index % source_len])
    return padded[:limit]


def render_zoswi_header_motivation_line(first_name: str) -> None:
    safe_name = re.sub(r"[^a-zA-Z0-9 .'-]", "", str(first_name or "").strip()) or "User"
    quotes_payload = json.dumps(get_zoswi_success_motivation_quotes(100), ensure_ascii=True)
    safe_name_payload = json.dumps(safe_name, ensure_ascii=True)
    st.components.v1.html(
        f"""
        <style>
            html, body {{
                margin: 0;
                padding: 0;
                background: transparent !important;
            }}
            #zoswi-header-quote-line {{
                margin: 0.06rem 0 0.06rem 0;
                color: #64748b;
                font-size: 0.93rem;
                font-weight: 600;
                line-height: 1.35;
                letter-spacing: 0.005em;
                transition: opacity 200ms ease;
                opacity: 1;
                text-wrap: pretty;
                word-break: break-word;
            }}
        </style>
        <div id="zoswi-header-quote-line"></div>
        <script>
        (function () {{
            const userName = {safe_name_payload};
            const quotes = {quotes_payload};
            const lineEl = document.getElementById("zoswi-header-quote-line");
            if (!lineEl || !Array.isArray(quotes) || quotes.length === 0) {{
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
            function renderLine() {{
                lineEl.textContent = "Hey " + userName + " - " + quotes[activeIndex];
            }}
            function switchQuote(nextIndex) {{
                lineEl.style.opacity = "0";
                setTimeout(() => {{
                    activeIndex = nextIndex;
                    renderLine();
                    lineEl.style.opacity = "1";
                }}, 150);
            }}
            renderLine();
            setInterval(() => {{
                switchQuote(pickNext(activeIndex));
            }}, 15000);
        }})();
        </script>
        """,
        height=76,
    )


def build_zoswi_quick_links_line() -> str:
    flags = get_effective_dashboard_feature_flags(st.session_state.get("user"))
    links = ["[Home](?nav=home)"]
    if flags.get("careers", False):
        links.append("[ZoSwi Careers](?nav=careers)")
    if flags.get("ai_workspace", False):
        links.append(f"[{ZOSWI_LIVE_WORKSPACE_NAME}](?nav=ai_workspace)")
    if flags.get("coding_room", False):
        links.append("[AI Coding Room](?nav=coding_room)")
    if flags.get("live_interview", False):
        links.append("[Live AI Interview](?nav=live_interview)")
    if flags.get("immigration_updates", False):
        links.append("[Immigration Updates](?nav=immigration_updates)")
    links.extend(
        [
            "[Recent Chats](?nav=chats)",
            "[Recent Scores](?nav=scores)",
        ]
    )
    return "Quick links: " + " | ".join(links)


def ensure_quick_links_in_message_state(state_key: str) -> None:
    raw_messages = st.session_state.get(state_key, [])
    if not isinstance(raw_messages, list) or not raw_messages:
        return
    first_message = raw_messages[0]
    if not isinstance(first_message, dict):
        return
    role = str(first_message.get("role", "")).strip().lower()
    content = str(first_message.get("content", "")).strip()
    if role != "assistant" or not content:
        return
    if "quick links:" in content.lower():
        links_line = build_zoswi_quick_links_line()
        if state_key == "bot_messages":
            user = st.session_state.get("user") or {}
            full_name = str(user.get("full_name", "")).strip()
            migrated = build_bot_first_message_content(full_name)
        elif state_key == "ai_workspace_messages":
            migrated = (
                "ZoSwi Live Workspace is ready. "
                "Ask anything to get started.\n\n"
                f"{links_line}"
            )
        else:
            migrated = content.replace(
                "[AI Workspace](?nav=ai_workspace)",
                f"[{ZOSWI_LIVE_WORKSPACE_NAME}](?nav=ai_workspace)",
            )
        if migrated != content:
            updated_first = dict(first_message)
            updated_first["content"] = migrated
            updated_messages = [updated_first]
            updated_messages.extend(raw_messages[1:])
            st.session_state[state_key] = updated_messages
        return
    updated_first = dict(first_message)
    updated_first["content"] = f"{content}\n\n{build_zoswi_quick_links_line()}"
    updated_messages = [updated_first]
    updated_messages.extend(raw_messages[1:])
    st.session_state[state_key] = updated_messages


def default_bot_messages(full_name: str | None = None) -> list[dict[str, str]]:
    return [{"role": "assistant", "content": build_bot_first_message_content(full_name)}]


def build_bot_first_message_content(full_name: str | None = None) -> str:
    first_name = "User"
    cleaned_name = str(full_name or "").strip()
    if cleaned_name:
        first_name = cleaned_name.split()[0]
    intro = f"Hi {first_name}, {time_based_greeting()}. {BOT_WELCOME_MESSAGE}"
    return f"{intro}\n\n{build_zoswi_quick_links_line()}"


def default_ai_workspace_messages(full_name: str | None = None) -> list[dict[str, str]]:
    links_line = build_zoswi_quick_links_line()
    return [
        {
            "role": "assistant",
            "content": (
                "ZoSwi Live Workspace is ready. "
                "Ask anything to get started.\n\n"
                f"{links_line}"
            ),
        }
    ]


def is_home_dashboard_view() -> bool:
    return str(st.session_state.get("dashboard_view", "home")).strip().lower() == "home"


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
        st.session_state.bot_open = should_auto_open_bot_after_auth()
        st.session_state.active_chat_id = None
        st.session_state.bot_messages = default_bot_messages(full_name)
        st.session_state.bot_pending_prompt = None
        st.session_state.zoswi_submit = False
        st.session_state.clear_zoswi_input = True
        st.session_state.full_chat_submit = False
        st.session_state.clear_full_chat_input = True
        st.session_state.ai_workspace_messages = default_ai_workspace_messages(full_name)
        st.session_state.ai_workspace_pending_prompt = None
        st.session_state.ai_workspace_submit = False
        st.session_state.ai_workspace_clear_input = True
        st.session_state.ai_workspace_input = ""
        st.session_state.ai_workspace_upload_nonce = 0
        st.session_state.ai_workspace_attachments = []
        st.session_state.ai_workspace_media_bytes = b""
        st.session_state.ai_workspace_media_mime = ""
        st.session_state.ai_workspace_media_file_name = ""
        st.session_state.ai_workspace_media_label = ""
        st.session_state.ai_workspace_unlock_code = ""
        st.session_state.job_search_results = []
        st.session_state.job_search_last_error = ""
        st.session_state.job_search_role_query = ""
        st.session_state.job_search_preferred_location = ""
        st.session_state.job_search_visa_status = JOB_SEARCH_VISA_STATUSES[0]
        st.session_state.job_search_sponsorship_required = False
        st.session_state.job_search_position_types = []
        st.session_state.job_search_max_results = JOB_SEARCH_MAX_RESULTS_DEFAULT
        st.session_state.job_search_posted_within_days = 0
        st.session_state.careers_use_custom_profile = False
        st.session_state.careers_input_mode = "Resume + JD"
        st.session_state.careers_resume_text = ""
        st.session_state.careers_resume_file_name = ""
        st.session_state.careers_target_job_description = ""
        st.session_state.careers_target_job_description_input = ""
        st.session_state.careers_profile_status = ""
        unlocked = has_promo_redemption(email)
        st.session_state.ai_workspace_unlock_status = (
            "Access unlocked for this account." if unlocked else ""
        )
        st.session_state.ai_workspace_unlock_ok = unlocked
        if full_name and is_home_dashboard_view():
            first_name = full_name.split()[0]
            st.toast(f"Hi {first_name}, ZoSwi AI is live")


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
        "gaps": ["Enable ZoSwiAI key for deeper semantic analysis and stronger recommendations."],
        "recommendations": [
            "Add measurable achievements tied to the target role.",
            "Mirror role-specific keywords from the job description naturally.",
        ],
    }


@lru_cache(maxsize=12)
def build_resume_vectorstore_cached(resume_text: str, api_key: str) -> tuple[Any, int]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=900, chunk_overlap=120)
    chunks = splitter.split_text(str(resume_text or ""))
    documents = [Document(page_content=chunk) for chunk in chunks if chunk.strip()]
    if not documents:
        return None, 0
    embeddings = ZoSwiAIEmbeddings(model="text-embedding-3-small", api_key=api_key)
    vectorstore = FAISS.from_documents(documents, embeddings)
    return vectorstore, len(documents)


def analyze_resume_with_ai(resume_text: str, job_description: str) -> dict[str, Any]:
    jd_ok, jd_error = validate_job_description_text(job_description)
    if not jd_ok:
        raise ValueError(jd_error)

    key = get_zoswiai_key()
    if not key:
        return fallback_analysis(resume_text, job_description)

    try:
        vectorstore, doc_count = build_resume_vectorstore_cached(resume_text, key)
    except Exception:
        return fallback_analysis(resume_text, job_description)
    if vectorstore is None or int(doc_count or 0) <= 0:
        return fallback_analysis(resume_text, job_description)

    top_docs = vectorstore.similarity_search(job_description, k=min(4, int(doc_count or 1)))
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

    llm = ZoSwiAIChat(model="gpt-4o-mini", temperature=0.2, api_key=key)
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


def sanitize_zoswi_response_text(text: str) -> str:
    raw_text = str(text or "")
    if not raw_text:
        return ""
    cleaned = ZOSWI_BLOCKED_APP_NAME_PATTERN.sub("ZoSwi", raw_text)
    cleaned = ZOSWI_BLOCKED_EXTERNAL_APP_PATTERN.sub("ZoSwi", cleaned)
    cleaned = re.sub(
        r"(?i)\b(?:apps?|tools?|software|platforms?)\s+(?:like|such as)\s+[^.\n]+",
        "ZoSwi workflows",
        cleaned,
    )
    cleaned = re.sub(r"\bZoSwi(?:\s*,\s*ZoSwi){1,}", "ZoSwi", cleaned)
    cleaned = re.sub(r"\bZoSwi\s+or\s+ZoSwi\b", "ZoSwi", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(?m)^\s*#{1,6}\s*", "", cleaned)
    cleaned = re.sub(r"(?i)\biam\b", "I am", cleaned)
    cleaned = re.sub(r"(?i)\bican\b", "I can", cleaned)
    cleaned = re.sub(r"(?i)\biwill\b", "I will", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


def iter_sanitized_stream_text(parts: Iterable[str]) -> Iterable[str]:
    tail = ""
    for part in parts:
        piece = str(part or "")
        if not piece:
            continue
        tail += piece
        if len(tail) <= ZOSWI_STREAM_SANITIZE_TAIL_CHARS:
            continue
        emit = tail[:-ZOSWI_STREAM_SANITIZE_TAIL_CHARS]
        safe_emit = sanitize_zoswi_response_text(emit)
        if safe_emit:
            yield safe_emit
        tail = tail[-ZOSWI_STREAM_SANITIZE_TAIL_CHARS:]
    if tail:
        safe_tail = sanitize_zoswi_response_text(tail)
        if safe_tail:
            yield safe_tail


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


def infer_zoswi_response_mode(message: str, intent: str = "") -> str:
    text = re.sub(r"\s+", " ", str(message or "").strip().lower())
    if not text:
        return "brief"

    brief_markers = [
        "briefly",
        "short answer",
        "quick answer",
        "in short",
        "one line",
        "tldr",
        "tl;dr",
    ]
    detailed_markers = [
        "explain",
        "elaborate",
        "in detail",
        "detailed",
        "step by step",
        "walk me through",
        "break down",
        "breakdown",
        "deep dive",
        "compare",
        "pros and cons",
        "tradeoff",
        "roadmap",
        "checklist",
        "root cause",
        "why",
    ]
    vague_markers = [
        "help",
        "suggest",
        "idea",
        "any tips",
        "what do you think",
        "guide me",
        "not sure",
        "confused",
        "stuck",
    ]

    if any(marker in text for marker in brief_markers):
        return "brief"
    if any(marker in text for marker in detailed_markers):
        return "detailed"

    words = [token for token in text.split(" ") if token]
    word_count = len(words)
    question_count = text.count("?")
    resolved_intent = str(intent or infer_ai_workspace_intent(text)).strip().lower()

    if resolved_intent in {"troubleshooting", "planning", "decision"} and word_count >= 6:
        return "detailed"
    if resolved_intent == "coding" and any(
        token in text for token in ("error", "traceback", "exception", "bug", "fix", "fails", "failed")
    ):
        return "detailed"
    if any(marker in text for marker in vague_markers) and word_count <= 20:
        return "brief"
    if word_count <= 8 and question_count <= 1:
        return "brief"
    if word_count >= 26 or question_count >= 2:
        return "detailed"
    return "balanced"


def build_zoswi_response_mode_guidance(mode: str) -> str:
    normalized_mode = str(mode or "").strip().lower()
    if normalized_mode == "brief":
        return (
            "- Keep the response human and concise in 2-4 short sentences.\n"
            "- Give direct value without over-explaining.\n"
            "- If context is missing, end with one clarifying question."
        )
    if normalized_mode == "detailed":
        return (
            "- Start with a one-line summary.\n"
            "- Then provide a structured breakdown with concrete steps and rationale.\n"
            "- Include assumptions and a practical next move."
        )
    return (
        "- Start with a direct answer, then up to 3 practical next steps.\n"
        "- Keep it concise but complete enough for action."
    )


def _normalize_assistant_message_text(message: str) -> str:
    return re.sub(r"\s+", " ", str(message or "").strip().lower())


def is_health_or_emergency_request(message: str) -> bool:
    text = _normalize_assistant_message_text(message)
    if not text:
        return False

    emergency_markers = (
        "going to die",
        "is dying",
        "not breathing",
        "chest pain",
        "heart attack",
        "stroke",
        "seizure",
        "overdose",
        "bleeding badly",
        "bleeding heavily",
        "suicide",
        "self harm",
        "kill myself",
        "emergency",
        "ambulance",
    )
    health_markers = (
        "illness",
        "ill",
        "sick",
        "medical",
        "hospital",
        "doctor",
        "injury",
    )
    return any(marker in text for marker in emergency_markers) or (
        any(marker in text for marker in health_markers) and any(marker in text for marker in ("urgent", "help", "die", "dying"))
    )


def is_resume_jd_related_request(message: str) -> bool:
    text = _normalize_assistant_message_text(message)
    if not text:
        return False

    allowed_markers = (
        "resume",
        "cv",
        "job description",
        "jd",
        "ats",
        "keyword",
        "interview",
        "cover letter",
        "application",
        "role",
        "experience bullet",
        "work experience",
        "career",
        "job match",
        "sponsorship",
        "visa",
    )
    return any(marker in text for marker in allowed_markers)


def is_code_or_fun_request(message: str) -> bool:
    text = _normalize_assistant_message_text(message)
    if not text:
        return False

    code_markers = (
        "write code",
        "share code",
        "generate code",
        "java code",
        "python code",
        "javascript code",
        "typescript code",
        "c++ code",
        "c# code",
        "code snippet",
        "source code",
        "write a function",
        "create a script",
        "algorithm solution",
        "leetcode solution",
        "debug this code",
    )
    fun_markers = (
        "joke",
        "funny",
        "meme",
        "story",
        "poem",
        "song",
        "game",
        "roast",
    )
    return any(marker in text for marker in code_markers) or any(marker in text for marker in fun_markers)


def get_assistant_guardrail_response(message: str) -> str:
    text = _normalize_assistant_message_text(message)
    if not text:
        return ZOSWI_ASSISTANT_SCOPE_ONLY_MESSAGE
    if is_health_or_emergency_request(text):
        return ZOSWI_ASSISTANT_EMERGENCY_MESSAGE
    if is_code_or_fun_request(text):
        return ZOSWI_ASSISTANT_NO_CODE_MESSAGE
    if not is_resume_jd_related_request(text):
        return ZOSWI_ASSISTANT_SCOPE_ONLY_MESSAGE
    return ""


def build_assistant_prompt(message: str) -> str:
    analysis = st.session_state.get("analysis_result")
    user = st.session_state.get("user") or {}
    full_name = str(user.get("full_name", "")).strip() or "Candidate"
    builder_name = get_zoswi_builder_name() or "the ZoSwi team"
    module_status_summary = build_dashboard_module_status_summary()

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
    response_mode = infer_zoswi_response_mode(cleaned_message, "career")
    response_mode_guidance = build_zoswi_response_mode_guidance(response_mode)

    return f"""
You are ZoSwi, an AI assistant for professional career guidance and ZoSwi product guidance.

Conversation style:
- Use a neutral, direct, professional tone.
- Keep replies concise and factual.
- No emotional comfort language, no humor, and no casual banter.
- Use plain text formatting. Do not use markdown headings like #, ##, or ###.
- Keep language natural and readable with proper spacing and punctuation.
- Keep branding ZoSwi-only. Do not mention or compare any other AI assistant or application by name.
- Do not mention, recommend, or list any third-party app/software names. Give ZoSwi-native guidance only.
- Adapt depth by response mode: brief for vague asks, detailed for complex asks.
- Never provide programming code, scripts, pseudo-code, or coding examples.

Scope and safety:
- Primary scope: resume review, JD analysis, ATS keywords, interview prep, role-skill guidance.
- Runtime module flags: {module_status_summary}.
- Respect runtime module flags and only claim module availability when that module is enabled.
- If user asks anything outside that scope, refuse briefly and ask for a resume/JD related question.
- If user asks for code or fun/entertainment requests, refuse and redirect to resume/JD scope.
- If user message indicates a health/safety emergency, do not provide any other guidance; instruct them to contact emergency services now (911 in the U.S. or local equivalent).
- If request is harmful, illegal, or privacy-invasive, refuse briefly and redirect to safe career guidance.
- Never request or expose sensitive data like passwords, API keys, bank/identity details.

Candidate context:
- Candidate name: {full_name}
- Latest analysis snapshot: {analysis_summary}

Response mode: {response_mode}
Mode guidance:
{response_mode_guidance}

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
    guardrail_response = get_assistant_guardrail_response(message)
    if guardrail_response:
        yield sanitize_zoswi_response_text(guardrail_response)
        return

    if is_zoswi_builder_request(message):
        yield sanitize_zoswi_response_text(build_zoswi_builder_response())
        return

    if is_zoswi_capability_request(message):
        yield sanitize_zoswi_response_text(build_zoswi_capability_response(message))
        return

    if is_agentive_job_search_request(message):
        _, response_text = run_agentive_job_search_from_message(message, source_profile="ZoSwi Chat Agent")
        yield response_text
        return

    key = get_zoswiai_key()
    if not key:
        yield "ZOSWI_AI_API_KEY is required for ZoSwi responses. Please set it and retry."
        return

    response_mode = infer_zoswi_response_mode(message, "career")
    max_tokens_by_mode = {
        "brief": 220,
        "balanced": 360,
        "detailed": 620,
    }
    llm = ZoSwiAIChat(
        model="gpt-4o-mini",
        temperature=0.4,
        max_tokens=max_tokens_by_mode.get(response_mode, 360),
        max_retries=1,
        timeout=25,
        api_key=key,
    )
    prompt = build_assistant_prompt(message)
    try:
        chunk_texts = (chunk_to_text(chunk) for chunk in llm.stream(prompt))
        for text in iter_sanitized_stream_text(chunk_texts):
            yield text
    except Exception:
        yield "I hit a temporary issue generating a response. Please try again."


def ask_assistant_bot(message: str) -> str:
    guardrail_response = get_assistant_guardrail_response(message)
    if guardrail_response:
        return sanitize_zoswi_response_text(guardrail_response)

    if is_zoswi_builder_request(message):
        return sanitize_zoswi_response_text(build_zoswi_builder_response())

    if is_zoswi_capability_request(message):
        return sanitize_zoswi_response_text(build_zoswi_capability_response(message))

    if is_agentive_job_search_request(message):
        _, response_text = run_agentive_job_search_from_message(message, source_profile="ZoSwi Chat Agent")
        return response_text

    key = get_zoswiai_key()
    if not key:
        return "ZOSWI_AI_API_KEY is required for ZoSwi responses. Please set it and retry."

    response_mode = infer_zoswi_response_mode(message, "career")
    max_tokens_by_mode = {
        "brief": 220,
        "balanced": 360,
        "detailed": 620,
    }
    llm = ZoSwiAIChat(
        model="gpt-4o-mini",
        temperature=0.4,
        max_tokens=max_tokens_by_mode.get(response_mode, 360),
        max_retries=1,
        timeout=25,
        api_key=key,
    )
    prompt = build_assistant_prompt(message)

    try:
        content = llm.invoke(prompt).content
        return sanitize_zoswi_response_text(str(content))
    except Exception:
        return "I hit a temporary issue generating a response. Please try again."


def request_ai_workspace_submit() -> None:
    st.session_state.ai_workspace_submit = True


def build_ai_workspace_context(limit: int = 12) -> str:
    chat = st.session_state.get("ai_workspace_messages", [])
    if not isinstance(chat, list):
        return ""

    lines: list[str] = []
    for msg in chat[-limit:]:
        role = str(msg.get("role", "")).strip().lower()
        content = re.sub(r"\s+", " ", str(msg.get("content", "")).strip())
        if role not in {"user", "assistant"} or not content:
            continue
        lines.append(f"{role}: {content[:420]}")
    return "\n".join(lines)


def infer_ai_workspace_intent(message: str) -> str:
    text = str(message or "").strip().lower()
    if not text:
        return "general"

    if any(
        token in text
        for token in (
            "error",
            "traceback",
            "exception",
            "not working",
            "fails",
            "failed",
            "debug",
            "fix this",
            "bug",
            "issue",
            "crash",
        )
    ):
        return "troubleshooting"

    if any(
        token in text
        for token in (
            "resume",
            "job description",
            "jd",
            "interview",
            "ats",
            "cover letter",
            "career",
            "role",
            "h1b",
            "visa",
        )
    ):
        return "career"

    if any(
        token in text
        for token in (
            "code",
            "python",
            "java",
            "javascript",
            "typescript",
            "api",
            "sql",
            "function",
            "class",
            "algorithm",
            "compile",
        )
    ):
        return "coding"

    if any(
        token in text
        for token in (
            "plan",
            "roadmap",
            "mvp",
            "strategy",
            "architect",
            "design",
            "go to market",
            "execution",
        )
    ):
        return "planning"

    if any(
        token in text
        for token in (
            "compare",
            "vs",
            "tradeoff",
            "pros and cons",
            "which one",
            "decision",
            "choose",
        )
    ):
        return "decision"

    if any(
        token in text
        for token in (
            "write",
            "rewrite",
            "draft",
            "email",
            "message",
            "summary",
            "summarize",
        )
    ):
        return "writing"

    return "general"


def build_ai_workspace_intent_guidance(intent: str) -> str:
    mode = str(intent or "general").strip().lower()
    if mode == "troubleshooting":
        return (
            "- Start with immediate triage checks first.\n"
            "- List likely root causes ranked by probability.\n"
            "- Provide the minimum safe fix and a short verification checklist.\n"
            "- If logs/errors are missing, ask only one focused follow-up."
        )
    if mode == "career":
        return (
            "- Provide role-fit advice tied to resume/JD context when available.\n"
            "- Suggest high-impact actions the user can complete in 24-72 hours.\n"
            "- Call out risks (visa/sponsorship/skills gaps) clearly and politely."
        )
    if mode == "coding":
        return (
            "- Explain the fix in plain terms, then show the exact code-level steps.\n"
            "- Prefer minimal, testable changes over large rewrites.\n"
            "- Include a quick verification method or test command."
        )
    if mode == "planning":
        return (
            "- Convert the request into a practical execution plan with milestones.\n"
            "- Include trade-offs, risks, and a recommended path.\n"
            "- Keep scope realistic for MVP delivery."
        )
    if mode == "decision":
        return (
            "- Compare options using explicit criteria and trade-offs.\n"
            "- Recommend one option and justify it with constraints and risk.\n"
            "- Include a short fallback option."
        )
    if mode == "writing":
        return (
            "- Draft concise, professional text tailored to the requested tone.\n"
            "- Keep the message actionable and easy to send with minimal edits.\n"
            "- Offer one stronger alternative phrasing when useful."
        )
    return (
        "- Give a direct answer first, then practical steps.\n"
        "- Keep output specific and actionable.\n"
        "- Ask a brief clarifying question only if required."
    )


def build_ai_workspace_progress_text(
    message: str,
    has_attachment: bool = False,
    attachment_is_image: bool = False,
) -> str:
    if is_agentive_job_search_request(message):
        return "Running agentive job match..."
    if bool(attachment_is_image):
        return "Analyzing image..."
    if bool(has_attachment):
        return "Processing file..."
    intent = infer_ai_workspace_intent(message)
    status_map = {
        "troubleshooting": "Debugging issue...",
        "career": "Preparing guidance...",
        "coding": "Preparing solution...",
        "planning": "Building plan...",
        "decision": "Evaluating options...",
        "writing": "Drafting response...",
    }
    return status_map.get(intent, "Processing request...")


def build_ai_workspace_prompt(message: str) -> str:
    user = st.session_state.get("user") or {}
    full_name = str(user.get("full_name", "")).strip() or "Candidate"
    builder_name = get_zoswi_builder_name() or "the ZoSwi team"
    module_status_summary = build_dashboard_module_status_summary()
    chat_context = build_ai_workspace_context()
    attachment_context = build_ai_workspace_attachment_context()
    clean_message = message.strip()
    intent = infer_ai_workspace_intent(clean_message)
    intent_guidance = build_ai_workspace_intent_guidance(intent)
    response_mode = infer_zoswi_response_mode(clean_message, intent)
    response_mode_guidance = build_zoswi_response_mode_guidance(response_mode)
    return f"""
You are ZoSwi Live Workspace, a high-quality professional assistant.

Response rules:
- Be direct, helpful, and conversational.
- Ask short clarifying questions only when needed.
- Prefer practical answers with concrete steps.
- Do not fabricate facts. If uncertain, say so briefly.
- Keep answers concise unless the user asks for depth.
- Use plain text formatting. Do not use markdown headings like #, ##, or ###.
- Prefer one short paragraph by default; use lists only when steps are actually needed.
- Keep language natural and readable with proper spacing and punctuation.
- If the user has a real-time issue, provide immediate triage steps first, then deeper fixes.
- Do not provide or create explicit sexual / 18+ content. Refuse briefly and redirect to safe help.
- Support both research-style Q&A and coding-assistant style help in one thread.
- Keep branding ZoSwi-only. Do not mention or compare any other AI assistant or application by name.
- Do not mention, recommend, or list any third-party app/software names. Provide ZoSwi-native workflows only.
- Runtime module flags: {module_status_summary}.
- Respect runtime module flags and only claim module availability when that module is enabled.
- If asked who built ZoSwi (or who built you), answer that ZoSwi team was founded by {builder_name}.
- If the user asks for innovation ideas, include a short section named "ZoSwi Original Ideas" with practical, non-generic concepts and success metrics.
- Adapt depth by response mode: brief for vague asks, detailed for complex asks.

Detected intent mode: {intent}

Intent guidance:
{intent_guidance}

Detected response mode: {response_mode}

Response mode guidance:
{response_mode_guidance}

Context:
- User: {full_name}
- Prior conversation:
{chat_context or "No prior context."}
- Attached files available for this session:
{attachment_context or "No attached files."}

Use attached files whenever relevant to the user's question, but do not dump raw file contents back unless explicitly asked.

User message:
{clean_message}
    """.strip()


def ask_ai_workspace_stream(message: str):
    if is_ai_workspace_18plus_request(message):
        yield AI_WORKSPACE_ADULT_BLOCK_MESSAGE
        return

    if is_zoswi_builder_request(message):
        yield sanitize_zoswi_response_text(build_zoswi_builder_response())
        return

    if is_zoswi_capability_request(message):
        yield sanitize_zoswi_response_text(build_zoswi_capability_response(message))
        return

    if is_agentive_job_search_request(message):
        _, response_text = run_agentive_job_search_from_message(message, source_profile="Live Workspace Agent")
        yield response_text
        return

    key = get_zoswiai_key()
    if not key:
        yield "ZOSWI_AI_API_KEY is required for ZoSwi Live Workspace responses. Please set it and retry."
        return

    intent_mode = infer_ai_workspace_intent(message)
    response_mode = infer_zoswi_response_mode(message, intent_mode)
    max_tokens_by_mode = {
        "brief": 340,
        "balanced": 560,
        "detailed": 760,
    }
    llm = ZoSwiAIChat(
        model="gpt-4o-mini",
        temperature=0.35,
        max_tokens=max_tokens_by_mode.get(response_mode, 560),
        max_retries=1,
        timeout=30,
        api_key=key,
    )
    prompt = build_ai_workspace_prompt(message)
    try:
        chunk_texts = (chunk_to_text(chunk) for chunk in llm.stream(prompt))
        for text in iter_sanitized_stream_text(chunk_texts):
            yield text
    except Exception:
        yield "I hit a temporary issue generating a response. Please try again."


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
            cleaned = re.sub(r"\s+", " ", str(item or "")).strip().strip("-â€¢* ")
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
    key = get_zoswiai_key()
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
        llm = ZoSwiAIChat(model="gpt-4o-mini", temperature=0.35, api_key=key)
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

    key = get_zoswiai_key()
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
        llm = ZoSwiAIChat(model="gpt-4o-mini", temperature=0.15, api_key=key)
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

    key = get_zoswiai_key()
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
        llm = ZoSwiAIChat(model="gpt-4o-mini", temperature=0.2, api_key=key)
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
    key = get_zoswiai_key()
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
Do not mention or compare other AI assistants or applications by name.
Do not mention or recommend third-party software names.

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
        llm = ZoSwiAIChat(model="gpt-4o-mini", temperature=0.45, api_key=key)
        chunk_texts = (chunk_to_text(chunk) for chunk in llm.stream(prompt))
        for text in iter_sanitized_stream_text(chunk_texts):
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
            const win = window.parent;
            const doc = win && win.document ? win.document : null;
            if (!doc) {
                return;
            }
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
            if (scrollParent) {
                if (scrollParent.__zoswiObserver) {
                    try {
                        scrollParent.__zoswiObserver.disconnect();
                    } catch (error) {
                        // Ignore observer cleanup failures.
                    }
                    scrollParent.__zoswiObserver = null;
                }
                const scrollToBottom = () => {
                    scrollParent.scrollTop = scrollParent.scrollHeight;
                };
                scrollToBottom();
                win.requestAnimationFrame(scrollToBottom);
                win.setTimeout(scrollToBottom, 40);
            }
        })();
        </script>
        """,
        height=0,
    )


def render_zoswi_autoscroll_cleanup_once() -> None:
    st.components.v1.html(
        """
        <script>
        (function () {
            const win = window.parent;
            const doc = win && win.document ? win.document : null;
            if (!doc || win.__zoswiObserverCleanupDone === true) {
                return;
            }
            win.__zoswiObserverCleanupDone = true;
            try {
                const nodes = doc.querySelectorAll("*");
                nodes.forEach(function (node) {
                    if (node && node.__zoswiObserver) {
                        try {
                            node.__zoswiObserver.disconnect();
                        } catch (error) {
                            // Ignore observer cleanup failures.
                        }
                        node.__zoswiObserver = null;
                    }
                });
            } catch (error) {
                // Cleanup is best-effort and should not block rendering.
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
    safe_content = format_chat_message_html(str(content))
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


def format_chat_message_html(content: str) -> str:
    normalized = str(content or "").replace("\r\n", "\n").replace("\r", "\n")
    safe_content = html.escape(normalized)

    def _safe_chat_href(raw_href: str) -> tuple[str, bool]:
        href = html.unescape(str(raw_href or "")).strip()
        if not href:
            return "#", False
        lowered = href.lower()
        if lowered.startswith("javascript:") or lowered.startswith("data:"):
            return "#", False
        if lowered.startswith("?") or lowered.startswith("/") or lowered.startswith("#"):
            return href, False
        if lowered.startswith("http://") or lowered.startswith("https://") or lowered.startswith("mailto:"):
            return href, True
        return "#", False

    def _render_markdown_link(match: re.Match[str]) -> str:
        raw_label = html.unescape(str(match.group(1) or "")).strip()
        label = html.escape(raw_label[:120] if raw_label else "Link")
        href, is_external = _safe_chat_href(str(match.group(2) or ""))
        if href == "#":
            return label
        safe_href = html.escape(href, quote=True)
        target = "_blank" if is_external else "_self"
        rel = "noopener noreferrer" if is_external else "noopener"
        return f'<a href="{safe_href}" target="{target}" rel="{rel}">{label}</a>'

    # Render inline code safely inside the custom message bubble.
    safe_content = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", safe_content)
    # Render markdown links as safe anchors.
    safe_content = re.sub(r"\[([^\]\n]{1,120})\]\(([^)\n]{1,500})\)", _render_markdown_link, safe_content)
    # Render markdown-style bold markers used by model responses.
    safe_content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", safe_content)
    safe_content = re.sub(r"__(.+?)__", r"<strong>\1</strong>", safe_content)
    # Render markdown list markers as visual bullets.
    safe_content = re.sub(r"(?m)^\s*[-*]\s+", "• ", safe_content)
    return safe_content.replace("\n", "<br>")


def format_ai_workspace_message_html(role: str, content: str, user_name: str) -> str:
    safe_content = format_chat_message_html(str(content))
    safe_user = html.escape((user_name or "Candidate").strip()) or "Candidate"
    normalized_role = str(role or "").strip().lower()
    if normalized_role == "assistant":
        return (
            '<div class="aiws-row assistant">'
            '<div class="aiws-msg assistant">'
            '<div class="aiws-msg-head assistant">'
            '<span class="aiws-name assistant">ZoSwi</span>'
            "</div>"
            f'<div class="aiws-msg-text">{safe_content}</div>'
            "</div>"
            "</div>"
        )
    return (
        '<div class="aiws-row user">'
        '<div class="aiws-msg user">'
        '<div class="aiws-msg-head user">'
        f'<span class="aiws-name user">{safe_user[:24]}</span>'
        "</div>"
        f'<div class="aiws-msg-text">{safe_content}</div>'
        "</div>"
        "</div>"
    )


def build_image_data_uri(image_bytes: bytes, mime_type: str = "image/png") -> str:
    if not image_bytes:
        return ""
    clean_mime = str(mime_type or "image/png").strip().lower()
    if not clean_mime.startswith("image/"):
        clean_mime = "image/png"
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{clean_mime};base64,{encoded}"


def format_ai_workspace_image_message_html(
    caption_text: str,
    image_data_uri: str,
    image_alt: str = "AI generated image",
) -> str:
    raw_src = str(image_data_uri or "").strip()
    safe_caption = html.escape(str(caption_text or "").strip())
    safe_alt = html.escape(str(image_alt or "AI generated image").strip())
    safe_src = html.escape(raw_src, quote=True)
    if not safe_src:
        return format_ai_workspace_message_html("assistant", safe_caption or "Image response unavailable.", "Candidate")
    mime_ext_map = {
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "image/bmp": "bmp",
        "image/tiff": "tiff",
    }
    mime_token = ""
    if raw_src.startswith("data:") and ";" in raw_src:
        mime_token = raw_src.split(";", 1)[0].replace("data:", "").strip().lower()
    file_ext = mime_ext_map.get(mime_token, "png")
    raw_name = str(image_alt or "").strip()
    if not raw_name or raw_name.lower() in {"ai generated image", "ai image", "image"}:
        raw_name = f"ZoSwi_AI_Image_{datetime.now().strftime('%Y%m%d')}"
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", raw_name).strip("._-") or "zoswi_image"
    if re.search(rf"\.{re.escape(file_ext)}$", safe_stem, re.IGNORECASE):
        download_file_name = safe_stem
    else:
        download_file_name = f"{safe_stem}.{file_ext}"
    safe_download_name = html.escape(download_file_name, quote=True)
    modal_id = f"aiws_image_full_{hashlib.sha1(raw_src.encode('utf-8', errors='ignore')).hexdigest()[:12]}"
    safe_modal_id = html.escape(modal_id, quote=True)
    caption_html = f'<div class="aiws-msg-text">{safe_caption}</div>' if safe_caption else ""
    return (
        '<div class="aiws-row assistant">'
        '<div class="aiws-msg assistant aiws-msg-image">'
        f"{caption_html}"
        '<div class="aiws-msg-image-wrap">'
        f'<img src="{safe_src}" alt="{safe_alt}" loading="lazy" />'
        '<div class="aiws-image-actions">'
        f'<a class="aiws-image-action" href="{safe_src}" download="{safe_download_name}" title="Download image" aria-label="Download image">&#x2B07;</a>'
        f'<a class="aiws-image-action" href="#{safe_modal_id}" title="Full view" aria-label="Open full view">&#x26F6;</a>'
        "</div>"
        "</div>"
        f'<div id="{safe_modal_id}" class="aiws-image-modal">'
        f'<a class="aiws-image-modal-backdrop" href="#" aria-label="Close full view"></a>'
        '<div class="aiws-image-modal-card">'
        '<a class="aiws-image-modal-close" href="#" aria-label="Close full view">&times;</a>'
        f'<img src="{safe_src}" alt="{safe_alt}" loading="lazy" />'
        "</div>"
        "</div>"
        "</div>"
        "</div>"
    )


def compress_ai_workspace_user_message(content: str) -> str:
    text = str(content or "").strip()
    if not text:
        return ""
    if "```text" in text and "File:" in text:
        first_line = text.splitlines()[0].strip() if text.splitlines() else ""
        file_name = ""
        if first_line.lower().startswith("file:"):
            file_name = first_line.split(":", 1)[1].strip()
        if not file_name:
            file_name = "attachment"
        return f"Attached file: {file_name}"
    return text


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
    ensure_quick_links_in_message_state("bot_messages")
    if st.session_state.get("clear_zoswi_input"):
        st.session_state.zoswi_input = ""
        st.session_state.clear_zoswi_input = False

    with st.container(key="zoswi_widget"):
        if st.session_state.bot_open:
            with st.container(key="zoswi_panel"):
                top_cols = st.columns([8, 1, 1, 1])
                with top_cols[0]:
                    st.markdown("**ZoSwi AI Assistant**")
                    if is_home_dashboard_view():
                        st.caption(f"{time_based_greeting()}, {first_name}. ZoSwi AI is live.")
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

                with st.container(height=360):
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
        "bot_user_email": None,
        "active_chat_id": None,
        "zoswi_input": "",
        "zoswi_submit": False,
        "clear_zoswi_input": False,
        "bot_pending_prompt": None,
        "chat_rename_target": None,
        "dashboard_view": "home",
        "live_interview_candidate_name": "",
        "live_interview_role": "Software Engineer",
        "live_interview_requirement_type": "mixed",
        "live_interview_embed": False,
        "immigration_search_query": "",
        "immigration_selected_categories": [],
        "immigration_ai_brief": "",
        "immigration_last_refresh_message": "",
        "full_chat_input": "",
        "full_chat_submit": False,
        "clear_full_chat_input": False,
        "ai_workspace_input": "",
        "ai_workspace_submit": False,
        "ai_workspace_clear_input": False,
        "ai_workspace_pending_prompt": None,
        "ai_workspace_upload_nonce": 0,
        "ai_workspace_attachments": [],
        "ai_workspace_media_bytes": b"",
        "ai_workspace_media_mime": "",
        "ai_workspace_media_file_name": "",
        "ai_workspace_media_label": "",
        "ai_workspace_unlock_code": "",
        "ai_workspace_unlock_status": "",
        "ai_workspace_unlock_ok": False,
        "user_menu_open": False,
        "auth_session_token": None,
        "auth_cookie_value": None,
        "auth_cookie_clear": False,
        "auth_promo_code": "",
        "auth_promo_valid": False,
        "auth_promo_status": "",
        "auth_promo_checked_code": "",
        "auth_privacy_center_open": False,
        "auth_privacy_support_open": False,
        "auth_privacy_support_first_name": "",
        "auth_privacy_support_last_name": "",
        "auth_privacy_support_email": "",
        "auth_privacy_support_code_sent": False,
        "auth_privacy_support_code_email": "",
        "auth_privacy_support_code_hash": "",
        "auth_privacy_support_code_expires_at": 0.0,
        "auth_privacy_support_code_resend_after": 0.0,
        "auth_privacy_support_code_attempts": 0,
        "auth_privacy_support_verified": False,
        "auth_privacy_support_verified_email": "",
        "auth_privacy_support_otp_input": "",
        "auth_privacy_support_clear_otp_input": False,
        "auth_privacy_support_clear_identity": False,
        "auth_privacy_support_subject": "",
        "auth_privacy_support_message": "",
        "auth_privacy_support_clear_compose": False,
        "auth_privacy_support_status": "",
        "auth_privacy_support_error": "",
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
        "job_search_role_query": "",
        "job_search_preferred_location": "",
        "job_search_visa_status": JOB_SEARCH_VISA_STATUSES[0],
        "job_search_sponsorship_required": False,
        "job_search_position_types": [],
        "job_search_max_results": JOB_SEARCH_MAX_RESULTS_DEFAULT,
        "job_search_posted_within_days": 0,
        "job_search_results": [],
        "job_search_last_error": "",
        "careers_use_custom_profile": False,
        "careers_input_mode": "Resume + JD",
        "careers_resume_text": "",
        "careers_resume_file_name": "",
        "careers_target_job_description": "",
        "careers_target_job_description_input": "",
        "careers_profile_status": "",
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
    if "bot_messages" not in st.session_state:
        st.session_state.bot_messages = default_bot_messages()
    if "ai_workspace_messages" not in st.session_state:
        st.session_state.ai_workspace_messages = default_ai_workspace_messages()


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


def reset_auth_privacy_support_state(clear_identity: bool = False) -> None:
    st.session_state.auth_privacy_support_code_sent = False
    st.session_state.auth_privacy_support_code_email = ""
    st.session_state.auth_privacy_support_code_hash = ""
    st.session_state.auth_privacy_support_code_expires_at = 0.0
    st.session_state.auth_privacy_support_code_resend_after = 0.0
    st.session_state.auth_privacy_support_code_attempts = 0
    st.session_state.auth_privacy_support_verified = False
    st.session_state.auth_privacy_support_verified_email = ""
    st.session_state.auth_privacy_support_otp_input = ""
    st.session_state.auth_privacy_support_clear_otp_input = False
    st.session_state.auth_privacy_support_clear_identity = False
    st.session_state.auth_privacy_support_subject = ""
    st.session_state.auth_privacy_support_message = ""
    st.session_state.auth_privacy_support_clear_compose = False
    st.session_state.auth_privacy_support_status = ""
    st.session_state.auth_privacy_support_error = ""
    if clear_identity:
        st.session_state.auth_privacy_support_first_name = ""
        st.session_state.auth_privacy_support_last_name = ""
        st.session_state.auth_privacy_support_email = ""


def queue_auth_privacy_support_refresh(clear_identity: bool = False, keep_status: bool = False) -> None:
    st.session_state.auth_privacy_support_code_sent = False
    st.session_state.auth_privacy_support_code_email = ""
    st.session_state.auth_privacy_support_code_hash = ""
    st.session_state.auth_privacy_support_code_expires_at = 0.0
    st.session_state.auth_privacy_support_code_resend_after = 0.0
    st.session_state.auth_privacy_support_code_attempts = 0
    st.session_state.auth_privacy_support_verified = False
    st.session_state.auth_privacy_support_verified_email = ""
    st.session_state.auth_privacy_support_clear_otp_input = True
    st.session_state.auth_privacy_support_clear_compose = True
    st.session_state.auth_privacy_support_error = ""
    if clear_identity:
        st.session_state.auth_privacy_support_clear_identity = True
    if not keep_status:
        st.session_state.auth_privacy_support_status = ""


def send_auth_privacy_support_code() -> tuple[bool, str]:
    first_name = str(st.session_state.get("auth_privacy_support_first_name", "")).strip()
    last_name = str(st.session_state.get("auth_privacy_support_last_name", "")).strip()
    email = str(st.session_state.get("auth_privacy_support_email", "")).strip().lower()
    if not first_name or not last_name:
        return False, "Enter first name and last name."
    if not is_valid_email_address(email):
        return False, "Enter a valid email address."
    config_ok, config_msg = can_send_email_otp()
    if not config_ok:
        return False, config_msg

    now_ts = time.time()
    resend_after_ts = float(st.session_state.get("auth_privacy_support_code_resend_after") or 0.0)
    if resend_after_ts > now_ts:
        wait_seconds = max(1, int(resend_after_ts - now_ts))
        return False, f"Please wait {wait_seconds} seconds before requesting another code."

    ttl_minutes = get_email_otp_ttl_minutes()
    otp_code = generate_email_otp_code()
    sent, msg = send_support_verification_code_message(email, otp_code, ttl_minutes)
    if not sent:
        return False, msg

    st.session_state.auth_privacy_support_code_sent = True
    st.session_state.auth_privacy_support_code_email = email
    st.session_state.auth_privacy_support_code_hash = hash_email_otp(otp_code)
    st.session_state.auth_privacy_support_code_expires_at = now_ts + float(ttl_minutes * 60)
    st.session_state.auth_privacy_support_code_resend_after = now_ts + float(get_email_otp_resend_seconds())
    st.session_state.auth_privacy_support_code_attempts = 0
    st.session_state.auth_privacy_support_verified = False
    st.session_state.auth_privacy_support_verified_email = ""
    return True, "Verification code sent to your email."


def verify_auth_privacy_support_code() -> tuple[bool, str]:
    email = str(st.session_state.get("auth_privacy_support_email", "")).strip().lower()
    code_email = str(st.session_state.get("auth_privacy_support_code_email", "")).strip().lower()
    stored_hash = str(st.session_state.get("auth_privacy_support_code_hash", "")).strip()
    if not bool(st.session_state.get("auth_privacy_support_code_sent")) or not stored_hash:
        return False, "Request a verification code first."
    if not email or email != code_email:
        return False, "Use the same email that received the code."

    expires_at = float(st.session_state.get("auth_privacy_support_code_expires_at") or 0.0)
    if time.time() > expires_at:
        st.session_state.auth_privacy_support_code_sent = False
        st.session_state.auth_privacy_support_code_hash = ""
        return False, "Verification code expired. Request a new code."

    otp_code = re.sub(r"\D", "", str(st.session_state.get("auth_privacy_support_otp_input", "")).strip())
    if len(otp_code) != EMAIL_OTP_DIGITS:
        return False, f"Enter the {EMAIL_OTP_DIGITS}-digit verification code."

    max_attempts = get_email_otp_max_attempts()
    attempts = int(st.session_state.get("auth_privacy_support_code_attempts") or 0)
    if attempts >= max_attempts:
        return False, "Too many attempts. Request a new code."

    expected_hash = hash_email_otp(otp_code)
    if not hmac.compare_digest(stored_hash, expected_hash):
        attempts += 1
        st.session_state.auth_privacy_support_code_attempts = attempts
        remaining = max(0, max_attempts - attempts)
        if remaining <= 0:
            return False, "Invalid code. Too many attempts. Request a new code."
        return False, f"Invalid code. {remaining} attempts remaining."

    st.session_state.auth_privacy_support_verified = True
    st.session_state.auth_privacy_support_verified_email = email
    st.session_state.auth_privacy_support_clear_otp_input = True
    return True, "Email verified. You can now message support."


def render_auth_privacy_support_sheet() -> None:
    if not bool(st.session_state.get("auth_privacy_support_open", False)):
        return

    if bool(st.session_state.get("auth_privacy_support_clear_identity", False)):
        st.session_state.auth_privacy_support_first_name = ""
        st.session_state.auth_privacy_support_last_name = ""
        st.session_state.auth_privacy_support_email = ""
        st.session_state.auth_privacy_support_clear_identity = False
    if bool(st.session_state.get("auth_privacy_support_clear_otp_input", False)):
        st.session_state.auth_privacy_support_otp_input = ""
        st.session_state.auth_privacy_support_clear_otp_input = False
    if bool(st.session_state.get("auth_privacy_support_clear_compose", False)):
        st.session_state.auth_privacy_support_subject = ""
        st.session_state.auth_privacy_support_message = ""
        st.session_state.auth_privacy_support_clear_compose = False

    with st.container(key="auth_privacy_support_sheet"):
        support_title_col, support_close_col = st.columns([12, 1], gap="small")
        with support_title_col:
            st.markdown(
                """
                <div class="auth-privacy-support-title">Support Help Desk</div>
                <div class="auth-privacy-support-subtitle">
                    Verify your email first, then send a private support request.
                </div>
                """,
                unsafe_allow_html=True,
            )
        with support_close_col:
            with st.container(key="auth_privacy_support_close_btn"):
                close_support_sheet = st.button(
                    ":material/close:",
                    key="auth_privacy_support_close_icon_btn",
                    help="Close support panel",
                    use_container_width=False,
                )
        if close_support_sheet:
            st.session_state.auth_privacy_support_open = False
            queue_auth_privacy_support_refresh(clear_identity=True, keep_status=False)
            st.rerun()

        status_msg = str(st.session_state.get("auth_privacy_support_status", "")).strip()
        error_msg = str(st.session_state.get("auth_privacy_support_error", "")).strip()
        if status_msg:
            st.success(status_msg)
        if error_msg:
            st.error(error_msg)

        identity_cols = st.columns(2, gap="small")
        with identity_cols[0]:
            first_name = st.text_input(
                "First Name",
                key="auth_privacy_support_first_name",
                placeholder="First name",
            )
        with identity_cols[1]:
            last_name = st.text_input(
                "Last Name",
                key="auth_privacy_support_last_name",
                placeholder="Last name",
            )
        with st.container(key="auth_privacy_support_email_row"):
            email_col, send_code_col = st.columns([4.4, 1.6], gap="small")
            with email_col:
                contact_email = st.text_input(
                    "Email",
                    key="auth_privacy_support_email",
                    placeholder="name@example.com",
                )
            with send_code_col:
                with st.container(key="auth_privacy_support_send_code_btn"):
                    request_code = st.button(
                        "Send Code",
                        key="auth_privacy_support_send_code",
                        use_container_width=True,
                    )

        resend_after_ts = float(st.session_state.get("auth_privacy_support_code_resend_after") or 0.0)
        seconds_left = max(0, int(resend_after_ts - time.time()))
        if seconds_left > 0:
            st.caption(f"Resend available in {seconds_left}s")
        else:
            st.caption("You can request a new code any time.")

        with st.container(key="auth_privacy_support_otp_row"):
            otp_col, verify_col = st.columns([4.4, 1.6], gap="small")
            with otp_col:
                st.text_input(
                    f"{EMAIL_CODE_NAME} ({EMAIL_OTP_DIGITS} digits)",
                    key="auth_privacy_support_otp_input",
                    placeholder="Enter code",
                )
            with verify_col:
                with st.container(key="auth_privacy_support_verify_btn"):
                    verify_code = st.button(
                        "Verify",
                        key="auth_privacy_support_verify_code",
                        use_container_width=True,
                    )
        code_target = str(st.session_state.get("auth_privacy_support_code_email", "")).strip()
        if code_target:
            st.caption(f"Code sent to: {code_target}")
        else:
            st.caption("Request a code to your email and verify it here.")

        if request_code:
            st.session_state.auth_privacy_support_error = ""
            ok, msg = send_auth_privacy_support_code()
            if ok:
                st.session_state.auth_privacy_support_status = msg
            else:
                st.session_state.auth_privacy_support_status = ""
                st.session_state.auth_privacy_support_error = msg
            st.rerun()

        if verify_code:
            st.session_state.auth_privacy_support_error = ""
            ok, msg = verify_auth_privacy_support_code()
            if ok:
                st.session_state.auth_privacy_support_status = msg
            else:
                st.session_state.auth_privacy_support_status = ""
                st.session_state.auth_privacy_support_error = msg
            st.rerun()

        verified = bool(st.session_state.get("auth_privacy_support_verified", False))
        verified_email = str(st.session_state.get("auth_privacy_support_verified_email", "")).strip().lower()
        if verified and verified_email and verified_email == str(contact_email or "").strip().lower():
            st.markdown(
                "<div class='auth-privacy-support-divider'></div>",
                unsafe_allow_html=True,
            )
            st.text_input(
                "Title",
                key="auth_privacy_support_subject",
                placeholder="Brief subject",
            )
            st.text_area(
                "Message",
                key="auth_privacy_support_message",
                placeholder="Write your support message here...",
                height=130,
            )
            with st.container(key="auth_privacy_support_send_msg_btn"):
                send_message = st.button(
                    "Send :material/send:",
                    key="auth_privacy_support_send_message",
                    use_container_width=False,
                )
            if send_message:
                subject = str(st.session_state.get("auth_privacy_support_subject", "")).strip()
                message_body = str(st.session_state.get("auth_privacy_support_message", "")).strip()
                first_name = str(st.session_state.get("auth_privacy_support_first_name", "")).strip()
                last_name = str(st.session_state.get("auth_privacy_support_last_name", "")).strip()
                sender_email = str(st.session_state.get("auth_privacy_support_email", "")).strip().lower()
                if not subject:
                    st.session_state.auth_privacy_support_status = ""
                    st.session_state.auth_privacy_support_error = "Add a title before sending."
                elif len(subject) < 4:
                    st.session_state.auth_privacy_support_status = ""
                    st.session_state.auth_privacy_support_error = "Title is too short."
                elif not message_body:
                    st.session_state.auth_privacy_support_status = ""
                    st.session_state.auth_privacy_support_error = "Add your message before sending."
                elif len(message_body) < 12:
                    st.session_state.auth_privacy_support_status = ""
                    st.session_state.auth_privacy_support_error = "Message is too short."
                else:
                    sent, send_msg = send_support_contact_message(
                        first_name,
                        last_name,
                        sender_email,
                        subject,
                        message_body,
                    )
                    if sent:
                        st.session_state.auth_privacy_support_status = send_msg
                        st.session_state.auth_privacy_support_error = ""
                        queue_auth_privacy_support_refresh(clear_identity=False, keep_status=True)
                    else:
                        st.session_state.auth_privacy_support_status = ""
                        st.session_state.auth_privacy_support_error = send_msg
                st.rerun()
        else:
            st.caption("Complete verification to open the secure support message composer.")


def render_auth_privacy_center_page(logo_data_uri: str) -> None:
    last_updated = datetime.now(timezone.utc).strftime("%B %d, %Y")
    logo_block = (
        (
            '<div class="auth-privacy-wordmark-wrap">'
            f'<img src="{logo_data_uri}" alt="ZoSwi" class="auth-privacy-page-logo" />'
            "</div>"
        )
        if logo_data_uri
        else ""
    )
    st.markdown(
        f"""
        <div class="auth-privacy-page-wrap">
            <article class="auth-privacy-a4-sheet">
                <header class="auth-privacy-sheet-header">
                    <div class="auth-privacy-sheet-header-top">
                        {logo_block}
                        <span class="auth-privacy-sheet-pill">Privacy Center</span>
                    </div>
                    <h2 class="auth-privacy-heading">
                        <span class="auth-privacy-heading-text">ZoSwi Privacy Policy</span>
                        <span class="auth-privacy-inline-badge">
                            <span class="auth-privacy-inline-badge-icon" aria-hidden="true">
                                <svg viewBox="0 0 24 24" fill="none">
                                    <path d="M12 3l7 3v5c0 5-2.8 8.8-7 10-4.2-1.2-7-5-7-10V6l7-3z" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"></path>
                                    <path d="M9.2 12.3l1.9 1.9 3.9-3.9" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"></path>
                                </svg>
                            </span>
                            <span>Privacy Protected</span>
                        </span>
                    </h2>
                    <p class="auth-privacy-sheet-meta">Last updated: {last_updated}</p>
                    <p>
                        ZoSwi is built to help people apply with confidence. Your privacy comes before product
                        growth goals, and your data is not used for resale or personal-data monetization.
                    </p>
                </header>
                <section class="auth-privacy-sheet-section">
                    <h3>1. Session-First Privacy</h3>
                    <ul>
                        <li>Resume and JD analysis is handled in your active session context for career matching.</li>
                        <li>Temporary session context is cleared on logout/session reset, including in-session drafts.</li>
                        <li>You choose what to upload and can continue without sharing unnecessary personal details.</li>
                    </ul>
                </section>
                <section class="auth-privacy-sheet-section">
                    <h3>2. Why Limited Data Is Used</h3>
                    <ul>
                        <li>To authenticate users and keep your account protected.</li>
                        <li>To generate AI-driven recommendations and improve match relevance.</li>
                        <li>To support sponsorship-fit checks, role filters, and application guidance.</li>
                        <li>To keep the platform stable and secure for real users.</li>
                    </ul>
                </section>
                <section class="auth-privacy-sheet-section">
                    <h3>3. Sharing & Third-Party Services</h3>
                    <p>
                        ZoSwi may use integrated services for job feeds and AI processing only when required to run
                        requested features. ZoSwi does not sell personal data and does not treat user data as a
                        business asset.
                    </p>
                </section>
                <section class="auth-privacy-sheet-section">
                    <h3>4. Account Records & Your Controls</h3>
                    <ul>
                        <li>Account/security records are retained only for sign-in, protection, and reliability.</li>
                        <li>You can request profile/data cleanup through support channels.</li>
                        <li>You stay in control of what content you upload and keep in the system.</li>
                    </ul>
                </section>
                <section class="auth-privacy-sheet-section">
                    <h3>5. Security Commitment</h3>
                    <p>
                        We apply practical safeguards across storage, access controls, and session handling.
                        No online platform can guarantee absolute security, but ZoSwi continuously improves controls.
                    </p>
                </section>
                <section class="auth-privacy-sheet-section">
                    <h3>6. Human in the Loop Reminder</h3>
                    <p>
                        ZoSwi can generate AI-based application guidance, but you make the final decision.
                        Human judgment should always remain central to where and how you apply.
                    </p>
                </section>
                <div class="auth-privacy-contact-highlight">
                    <div class="auth-privacy-contact-note">
                        <span class="auth-privacy-contact-note-icon" aria-hidden="true">
                            <svg viewBox="0 0 24 24" fill="none">
                                <path d="M4 6.8A2.8 2.8 0 0 1 6.8 4h10.4A2.8 2.8 0 0 1 20 6.8v6.4A2.8 2.8 0 0 1 17.2 16H9l-4.1 3.6c-.4.3-.9 0-.9-.5V16.2A2.8 2.8 0 0 1 4 13.2V6.8z" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"></path>
                            </svg>
                        </span>
                        <span>Feel free to contact us using the message icon.</span>
                    </div>
                </div>
            </article>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_auth_screen() -> None:
    render_app_styles()
    render_zoswi_outside_minimize_listener(False)
    render_top_left_logo()
    render_global_music_bar()
    logo_data_uri = get_logo_data_uri()
    if "auth_privacy_center_open" not in st.session_state:
        st.session_state.auth_privacy_center_open = False
    if bool(st.session_state.get("auth_privacy_center_open", False)):
        title_col, actions_col = st.columns([20, 1.2], gap="small")
        with title_col:
            st.title("Career Command Centre")
        with actions_col:
            with st.container(key="auth_privacy_header_actions"):
                support_col, close_col = st.columns([1, 1], gap="small")
                with support_col:
                    with st.container(key="auth_privacy_header_support"):
                        toggle_support_center = st.button(
                            ":material/mail:",
                            key="auth_privacy_header_support_btn",
                            help="Support",
                            use_container_width=True,
                        )
                with close_col:
                    with st.container(key="auth_privacy_header_close"):
                        close_privacy_center = st.button(
                            ":material/close:",
                            key="auth_privacy_header_close_btn",
                            help="Close Privacy Center",
                            use_container_width=True,
                        )
        if toggle_support_center:
            next_support_open = not bool(st.session_state.get("auth_privacy_support_open", False))
            st.session_state.auth_privacy_support_open = next_support_open
            if next_support_open:
                st.session_state.auth_privacy_support_status = ""
                st.session_state.auth_privacy_support_error = ""
            else:
                queue_auth_privacy_support_refresh(clear_identity=True, keep_status=False)
            st.rerun()
        if close_privacy_center:
            st.session_state.auth_privacy_center_open = False
            st.session_state.auth_privacy_support_open = False
            reset_auth_privacy_support_state(clear_identity=True)
            st.rerun()
        render_auth_privacy_center_page(logo_data_uri)
        render_auth_privacy_support_sheet()
        return
    st.title("Career Command Centre")
    apply_pending_signup_form_reset()
    apply_pending_password_reset_form_reset()
    if "auth_view_selector" not in st.session_state:
        st.session_state.auth_view_selector = read_auth_view_from_query_params()
    quote_role_context = "login"
    if normalize_auth_view(str(st.session_state.get("auth_view_selector", "Login"))) == "Create Account":
        quote_role_context = str(st.session_state.get("signup_role_selector", "Candidate")).strip().lower()
    is_mobile = is_mobile_browser()

    if is_mobile:
        oauth_col = st.container()
        account_col = st.container()
    else:
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

            oauth_top_spacing = "0.6rem" if is_mobile else "2in"
            st.markdown(f"<div style='height:{oauth_top_spacing};'></div>", unsafe_allow_html=True)
            with st.container(key="oauth_social_stack"):
                if is_mobile:
                    button_col = st.container()
                else:
                    left_space, button_col, right_space = st.columns([1, 2, 1], gap="large")
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
                            apply_promo = False
                            if is_mobile:
                                promo_code_text = st.text_input(
                                    "Have a promo code",
                                    key="auth_promo_code",
                                    placeholder="Have a promo code",
                                    label_visibility="collapsed",
                                )
                                apply_promo = st.button(
                                    "Apply Promo Code",
                                    key="oauth_promo_send",
                                    help="Apply promo code",
                                    use_container_width=True,
                                )
                            else:
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

                            if not is_mobile:
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
                    if is_mobile:
                        spacer_height = "1rem" if promo_enabled else "1.4rem"
                    else:
                        spacer_height = "3.2rem" if promo_enabled else "5.8rem"
                    st.markdown(f"<div style='height:{spacer_height};'></div>", unsafe_allow_html=True)
                    with st.container(key="oauth_motivation_popup"):
                        render_auth_motivation_quote_box(quote_role_context)
        else:
            if is_mobile:
                st.info("Google OAuth is not configured yet. Use login or create account below.")
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
            horizontal=not is_mobile,
            label_visibility="collapsed",
        )
        sync_auth_view_query_param(auth_view)

        if auth_view == "Login":
            email = ""
            password = ""
            open_reset = False
            submit = False
            with st.container(key="login_form_shell"):
                with st.form("login_form"):
                    form_scope = st.container()
                    if not is_mobile:
                        left_gap, center_col, right_gap = st.columns([1, 3, 1], gap="small")
                        form_scope = center_col
                    with form_scope:
                        with st.container(key="login_form_center"):
                            email = st.text_input("Email")
                            password = st.text_input("Password", type="password")
                            with st.container(key="login_actions"):
                                with st.container(key="login_submit_btn"):
                                    submit = st.form_submit_button("Login", use_container_width=is_mobile, type="primary")
            with st.container(key="login_forgot_row"):
                st.markdown(
                    '<div class="auth-forgot-label">Don\'t remember your password?</div>',
                    unsafe_allow_html=True,
                )
                with st.container(key="login_forgot_reset_btn"):
                    open_reset = st.button(
                        "reset",
                        key="login_open_reset_btn",
                        use_container_width=is_mobile,
                    )
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
                    st.session_state.bot_open = should_auto_open_bot_after_auth()
                    st.session_state.bot_messages = default_bot_messages(full_name)
                    st.session_state.bot_pending_prompt = None
                    st.session_state.zoswi_submit = False
                    st.session_state.clear_zoswi_input = True
                    st.session_state.full_chat_submit = False
                    st.session_state.clear_full_chat_input = True
                    st.session_state.ai_workspace_media_bytes = b""
                    st.session_state.ai_workspace_media_mime = ""
                    st.session_state.ai_workspace_media_file_name = ""
                    st.session_state.ai_workspace_media_label = ""
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
                    horizontal=not is_mobile,
                    key="signup_role_selector",
                )
                if is_mobile:
                    first_name = st.text_input("First Name", key="signup_first_name")
                    last_name = st.text_input("Last Name", key="signup_last_name")
                else:
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
                if role == "Recruiter":
                    recruiter_restriction = get_recruiter_role_restriction_reason(email)
                    if recruiter_restriction:
                        st.info(recruiter_restriction)
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
                if is_mobile:
                    password = st.text_input("Password", type="password", key="signup_password")
                    confirm_password = st.text_input(
                        "Re-enter Password",
                        type="password",
                        key="signup_confirm_password",
                    )
                    password_policy = get_password_policy_status(password)
                    render_password_policy_checklist(password_policy, password, confirm_password)
                    if password and confirm_password and password != confirm_password:
                        st.markdown(
                            "<span style='color:#dc2626;font-size:0.86rem;font-weight:600;'>"
                            "The password entered is wrong."
                            "</span>",
                            unsafe_allow_html=True,
                        )
                else:
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
                    use_container_width=is_mobile,
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
        with st.container(key="auth_privacy_center_link"):
            if is_mobile:
                privacy_center_toggle = st.button(
                    "Privacy Center",
                    key="auth_privacy_center_toggle_btn",
                    use_container_width=True,
                )
            else:
                spacer_col, privacy_col = st.columns([8.2, 1.8], gap="small")
                with spacer_col:
                    st.markdown("", unsafe_allow_html=True)
                with privacy_col:
                    privacy_center_toggle = st.button(
                        "Privacy Center",
                        key="auth_privacy_center_toggle_btn",
                        use_container_width=True,
                    )
        if privacy_center_toggle:
            next_open = not bool(st.session_state.get("auth_privacy_center_open", False))
            st.session_state.auth_privacy_center_open = next_open
            if next_open:
                st.session_state.auth_privacy_support_open = False
                reset_auth_privacy_support_state(clear_identity=True)
            st.rerun()


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
    st.session_state.ai_workspace_messages = default_ai_workspace_messages()
    st.session_state.ai_workspace_input = ""
    st.session_state.ai_workspace_submit = False
    st.session_state.ai_workspace_clear_input = False
    st.session_state.ai_workspace_pending_prompt = None
    st.session_state.ai_workspace_upload_nonce = 0
    st.session_state.ai_workspace_attachments = []
    st.session_state.ai_workspace_media_bytes = b""
    st.session_state.ai_workspace_media_mime = ""
    st.session_state.ai_workspace_media_file_name = ""
    st.session_state.ai_workspace_media_label = ""
    st.session_state.ai_workspace_unlock_code = ""
    st.session_state.ai_workspace_unlock_status = ""
    st.session_state.ai_workspace_unlock_ok = False
    st.session_state.user_menu_open = False
    st.session_state.auth_session_token = None
    st.session_state.auth_privacy_center_open = False
    st.session_state.auth_privacy_support_open = False
    reset_auth_privacy_support_state(clear_identity=True)
    st.session_state.latest_resume_text = ""
    st.session_state.latest_job_description = ""
    st.session_state.latest_resume_file_name = ""
    st.session_state.resume_editor_draft_text = ""
    st.session_state.resume_editor_source_sig = ""
    st.session_state.resume_export_panel_open = False
    st.session_state.job_search_role_query = ""
    st.session_state.job_search_preferred_location = ""
    st.session_state.job_search_visa_status = JOB_SEARCH_VISA_STATUSES[0]
    st.session_state.job_search_sponsorship_required = False
    st.session_state.job_search_position_types = []
    st.session_state.job_search_max_results = JOB_SEARCH_MAX_RESULTS_DEFAULT
    st.session_state.job_search_posted_within_days = 0
    st.session_state.job_search_results = []
    st.session_state.job_search_last_error = ""
    st.session_state.careers_use_custom_profile = False
    st.session_state.careers_input_mode = "Resume + JD"
    st.session_state.careers_resume_text = ""
    st.session_state.careers_resume_file_name = ""
    st.session_state.careers_target_job_description = ""
    st.session_state.careers_target_job_description_input = ""
    st.session_state.careers_profile_status = ""
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


def build_dashboard_top_nav_options(user: dict[str, Any]) -> list[tuple[str, str]]:
    feature_flags = get_effective_dashboard_feature_flags(user)
    options: list[tuple[str, str]] = [
        ("Home", "home"),
        ("Recent Chats", "chats"),
        ("Recent Scores", "scores"),
    ]
    if feature_flags.get("careers", False):
        options.append(("ZoSwi Careers", "careers"))
    if feature_flags.get("ai_workspace", False):
        options.append((ZOSWI_LIVE_WORKSPACE_NAME, "ai_workspace"))
    if feature_flags.get("coding_room", False):
        options.append(("AI Coding Room", "coding_room"))
    if feature_flags.get("live_interview", False):
        options.append(("Live AI Interview", "live_interview"))
    if feature_flags.get("immigration_updates", False):
        options.append(("Immigration Updates", "immigration_updates"))
    return options


def render_dashboard_top_navigation(user: dict[str, Any]) -> None:
    options = build_dashboard_top_nav_options(user)
    if not options:
        return

    labels = [label for label, _ in options]
    label_to_view = {label: view for label, view in options}
    current_view = str(st.session_state.get("dashboard_view", "home")).strip().lower()
    selected_label_default = next((label for label, view in options if view == current_view), labels[0])

    full_name_raw = str(user.get("full_name", "")).strip()
    first_name = html.escape(full_name_raw.split()[0] if full_name_raw else "Candidate")
    greeting = html.escape(time_based_greeting())
    st.markdown(
        (
            '<div class="dashboard-shell-header">'
            f'<div class="dashboard-shell-title">{greeting}, {first_name}</div>'
            '<div class="dashboard-shell-subtitle">Choose what you want to work on next across careers, workspace, interviews, and coding.</div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )

    selected_label = None
    with st.container(key="dashboard_top_nav_shell"):
        try:
            selected_label = st.segmented_control(
                "Navigation",
                options=labels,
                selection_mode="single",
                default=selected_label_default,
                key="dashboard_top_nav",
                label_visibility="collapsed",
            )
        except Exception:
            selected_index = labels.index(selected_label_default) if selected_label_default in labels else 0
            selected_label = st.radio(
                "Navigation",
                options=labels,
                index=selected_index,
                key="dashboard_top_nav_fallback",
                horizontal=True,
                label_visibility="collapsed",
            )

    if not selected_label:
        return

    next_view = str(label_to_view.get(str(selected_label), current_view or "home")).strip().lower()
    if next_view == "coding_room" and not bool(st.session_state.get("analysis_result")):
        st.caption("AI Coding Room unlocks after your first resume analysis.")
        return
    if next_view != current_view:
        st.session_state.dashboard_view = next_view
        if next_view != "scores":
            st.session_state.bot_open = False
        st.rerun()


def render_candidate_sidebar(user: dict[str, Any]) -> None:
    user_menu_open = bool(st.session_state.get("user_menu_open", False))
    is_mobile = is_mobile_browser()
    full_name_raw = str(user.get("full_name", "")).strip()
    first_name = full_name_raw.split()[0] if full_name_raw else "Candidate"
    menu_title = f"{first_name}'s Menu"
    signed_in_name = html.escape(first_name)

    with st.sidebar:
        with st.container(key="sidebar_menu_body"):
            with st.container(key="sidebar_signed_row"):
                signed_cols = st.columns([8.6, 1.4], gap="small") if is_mobile else st.columns([7, 3], gap="small")
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
                            type="tertiary",
                        ):
                            logout_current_user()
                            st.rerun()
            with st.container(key="sidebar_menu_toggle"):
                if st.button(f"\u2630 {menu_title}", key="sidebar_menu_toggle_btn", use_container_width=True):
                    st.session_state.user_menu_open = not user_menu_open
                    st.rerun()

            if user_menu_open:
                with st.container(key="sidebar_nav_menu"):
                    feature_flags = get_effective_dashboard_feature_flags(user)
                    if st.button("Recent Chats", key="sidebar_nav_chats", use_container_width=True):
                        st.session_state.dashboard_view = "chats"
                        st.session_state.bot_open = False
                        st.rerun()
                    if st.button("Recent Scores", key="sidebar_nav_scores", use_container_width=True):
                        st.session_state.dashboard_view = "scores"
                        st.rerun()
                    if feature_flags.get("coding_room", False):
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
                    if feature_flags.get("ai_workspace", False):
                        if st.button("ZoSwi Live Workspace", key="sidebar_nav_ai_workspace", use_container_width=True):
                            st.session_state.dashboard_view = "ai_workspace"
                            st.session_state.bot_open = False
                            st.rerun()
                    if feature_flags.get("careers", False):
                        if st.button("ZoSwi Careers", key="sidebar_nav_careers", use_container_width=True):
                            st.session_state.dashboard_view = "careers"
                            st.session_state.bot_open = False
                            st.rerun()
                    if feature_flags.get("live_interview", False):
                        if st.button("Live AI Interview", key="sidebar_nav_live_interview", use_container_width=True):
                            st.session_state.dashboard_view = "live_interview"
                            st.session_state.bot_open = False
                            st.rerun()
                    if feature_flags.get("immigration_updates", False):
                        if st.button("Immigration Updates", key="sidebar_nav_immigration_updates", use_container_width=True):
                            st.session_state.dashboard_view = "immigration_updates"
                            st.session_state.bot_open = False
                            st.rerun()
                    if st.button("Home", key="sidebar_nav_home", use_container_width=True):
                        st.session_state.dashboard_view = "home"
                        st.rerun()


def render_home_dashboard(user: dict[str, Any]) -> None:
    is_mobile = is_mobile_browser()
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
    with st.container(key="home_dashboard_input_cols"):
        if is_mobile:
            uploaded_file = st.file_uploader("Upload Resume (PDF or DOCX)", type=["pdf", "docx"])
            job_description = st.text_area("Paste Job Description", height=240)
            st.caption(f"JD must include role details and at least {MIN_JOB_DESCRIPTION_WORDS} words.")
            with st.container(key="home_jd_analyze_btn"):
                analyze_clicked = st.button(
                    "Run Resume-JD Analysis",
                    key="home_run_resume_jd_analysis_btn",
                    use_container_width=True,
                )
        else:
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
                st.session_state.job_search_results = []
                st.session_state.job_search_last_error = ""
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
        coding_room_feature_enabled = is_dashboard_module_enabled("coding_room")
        with action_cols[0]:
            panel_open = bool(st.session_state.get("resume_export_panel_open"))
            toggle_label = "Resume Add Points" if not panel_open else "Hide Resume Add Points"
            with st.container(key="home_resume_add_points_btn"):
                if st.button(toggle_label, key="home_resume_add_points_toggle_btn", use_container_width=False):
                    st.session_state.resume_export_panel_open = not panel_open
        with action_cols[1]:
            if coding_room_feature_enabled:
                with st.container(key="home_launch_coding_room_btn"):
                    if st.button("Start 3-Stage AI Coding Room", key="home_open_coding_room_btn", use_container_width=False):
                        st.session_state.dashboard_view = "coding_room"
                        st.session_state.bot_open = False
                        st.rerun()
        render_resume_export_assistant(show_toggle_button=False)
        st.caption("ZoSwi is available in the round memoji button at the bottom-right.")


def render_job_match_mvp_panel(user: dict[str, Any]) -> None:
    from src.ui.pages.careers_page import render_job_match_mvp_panel as _impl

    return _impl(user)

def render_careers_view(user: dict[str, Any]) -> None:
    from src.ui.pages.careers_page import render_careers_view as _impl

    return _impl(user)

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
    is_mobile = is_mobile_browser()
    full_chat_height = 420 if is_mobile else 560
    active_chat_id = int(st.session_state.get("active_chat_id") or 0)
    recent_sessions = get_recent_chat_sessions(user_id, limit=40)

    if active_chat_id <= 0 and recent_sessions:
        initial_session_id = int(recent_sessions[0]["id"])
        load_chat_session_into_state(user_id, initial_session_id, full_name)
        active_chat_id = initial_session_id
    if not st.session_state.get("bot_messages"):
        st.session_state.bot_messages = default_bot_messages(full_name)
    ensure_quick_links_in_message_state("bot_messages")
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
                st.caption("Recent conversation history")

                with st.container(height=full_chat_height):
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
                    input_cols = st.columns([8.4, 1.6]) if is_mobile else st.columns([9, 1])
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


def render_ai_workspace_view(user: dict[str, Any]) -> None:
    from src.ui.pages.ai_workspace_page import render_ai_workspace_view as _impl

    return _impl(user)

def render_coding_room_view(user: dict[str, Any]) -> None:
    from src.ui.pages.coding_room_page import render_coding_room_view as _impl

    return _impl(user)


def render_live_interview_view(user: dict[str, Any]) -> None:
    from src.ui.pages.live_interview_page import render_live_interview_view as _impl

    return _impl(user)


def render_immigration_updates_view(user: dict[str, Any]) -> None:
    from src.ui.pages.immigration_updates import render_immigration_updates_view as _impl

    return _impl(user)

def render_main_screen() -> None:
    user = st.session_state.user
    query_view = pop_dashboard_view_from_query_params()
    if query_view:
        st.session_state.dashboard_view = query_view
    render_app_styles()
    render_top_left_logo()
    render_global_music_bar()
    sync_bot_for_logged_in_user()
    ensure_quick_links_in_message_state("bot_messages")
    ensure_quick_links_in_message_state("ai_workspace_messages")
    render_dashboard_top_navigation(user)
    render_candidate_sidebar(user)

    view = str(st.session_state.get("dashboard_view", "home")).strip().lower()
    if not is_dashboard_module_enabled(view):
        st.session_state.dashboard_view = "home"
        view = "home"

    if view == "chats":
        st.session_state.bot_open = False
        render_recent_chats_view(user)
        render_zoswi_outside_minimize_listener(False)
        return
    if view == "scores":
        render_recent_scores_view(user)
        render_zoswi_widget()
        return
    if view == "ai_workspace":
        st.session_state.bot_open = False
        render_ai_workspace_view(user)
        render_zoswi_outside_minimize_listener(False)
        return
    if view == "careers":
        st.session_state.bot_open = False
        render_careers_view(user)
        render_zoswi_outside_minimize_listener(False)
        return
    if view == "coding_room":
        st.session_state.bot_open = False
        render_coding_room_view(user)
        render_zoswi_outside_minimize_listener(False)
        return
    if view == "live_interview":
        st.session_state.bot_open = False
        render_live_interview_view(user)
        render_zoswi_outside_minimize_listener(False)
        return
    if view == "immigration_updates":
        st.session_state.bot_open = False
        render_immigration_updates_view(user)
        render_zoswi_outside_minimize_listener(False)
        return

    render_home_dashboard(user)
    render_zoswi_widget()


def get_current_session_user() -> Any:
    return st.session_state.get("user")


def main() -> None:
    if os.path.exists(BROWSER_ICON_PATH):
        page_icon = BROWSER_ICON_PATH
    else:
        page_icon = LOGO_IMAGE_PATH if os.path.exists(LOGO_IMAGE_PATH) else None
    config = PageConfigDTO(
        page_title="Career Command Centre",
        layout="wide",
        initial_sidebar_state="auto",
        page_icon=page_icon,
    )
    handlers = AppRuntimeHandlersDTO(
        bootstrap_runtime=bootstrap_runtime,
        init_db=init_db,
        init_state=init_state,
        sync_promo_codes_from_secrets=sync_promo_codes_from_secrets,
        try_restore_user_from_cookie=try_restore_user_from_cookie,
        sync_user_from_oauth_session=sync_user_from_oauth_session,
        render_auth_cookie_sync=render_auth_cookie_sync,
        render_auth_screen=render_auth_screen,
        render_main_screen=render_main_screen,
        get_current_user=get_current_session_user,
    )
    run_app_runtime(config, handlers)


if __name__ == "__main__":
    main()
