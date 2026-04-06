from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from src.dto.careers_dto import ApplicationRecord, JobCard, SavedJob


class CareersRepository:
    """Persistence layer for careers jobs, saved queue, and applications."""

    _VALID_APPLICATION_STATUSES = {
        "saved",
        "applied",
        "interview",
        "interviewing",
        "offer",
        "rejected",
        "withdrawn",
    }

    def __init__(self, db_connect: Callable[[], Any]) -> None:
        self._db_connect = db_connect

    @staticmethod
    def get_table_creation_sql(backend: str) -> list[str]:
        normalized_backend = str(backend or "").strip().lower()
        id_pk_sql = "BIGSERIAL PRIMARY KEY" if normalized_backend == "postgres" else "INTEGER PRIMARY KEY AUTOINCREMENT"
        fk_type = "BIGINT" if normalized_backend == "postgres" else "INTEGER"
        return [
            f"""
            CREATE TABLE IF NOT EXISTS careers_saved_jobs (
                id {id_pk_sql},
                user_id {fk_type} NOT NULL,
                job_id TEXT NOT NULL,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT NOT NULL,
                source TEXT NOT NULL,
                job_url TEXT,
                posted_at TEXT,
                domain TEXT,
                work_type TEXT,
                level TEXT,
                industry TEXT,
                certifications_json TEXT NOT NULL DEFAULT '[]',
                raw_payload_json TEXT NOT NULL DEFAULT '{{}}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, job_id),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS careers_application_records (
                id {id_pk_sql},
                user_id {fk_type} NOT NULL,
                job_id TEXT NOT NULL,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT NOT NULL,
                source TEXT NOT NULL,
                job_url TEXT,
                posted_at TEXT,
                status TEXT NOT NULL DEFAULT 'applied',
                notes TEXT,
                applied_at TEXT,
                domain TEXT,
                work_type TEXT,
                level TEXT,
                industry TEXT,
                certifications_json TEXT NOT NULL DEFAULT '[]',
                raw_payload_json TEXT NOT NULL DEFAULT '{{}}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, job_id),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS careers_cached_jobs (
                id {id_pk_sql},
                cache_key TEXT NOT NULL,
                job_id TEXT NOT NULL,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT NOT NULL,
                source TEXT NOT NULL,
                job_url TEXT,
                posted_at TEXT,
                domain TEXT,
                work_type TEXT,
                level TEXT,
                industry TEXT,
                certifications_json TEXT NOT NULL DEFAULT '[]',
                raw_payload_json TEXT NOT NULL DEFAULT '{{}}',
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(cache_key, job_id)
            )
            """,
        ]

    @staticmethod
    def get_index_creation_sql() -> list[str]:
        return [
            "CREATE INDEX IF NOT EXISTS idx_careers_saved_jobs_user_id ON careers_saved_jobs(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_careers_saved_jobs_updated_at ON careers_saved_jobs(updated_at)",
            "CREATE INDEX IF NOT EXISTS idx_careers_applications_user_id ON careers_application_records(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_careers_applications_status ON careers_application_records(status)",
            "CREATE INDEX IF NOT EXISTS idx_careers_applications_updated_at ON careers_application_records(updated_at)",
            "CREATE INDEX IF NOT EXISTS idx_careers_cached_jobs_cache_key ON careers_cached_jobs(cache_key)",
            "CREATE INDEX IF NOT EXISTS idx_careers_cached_jobs_expires_at ON careers_cached_jobs(expires_at)",
            "CREATE INDEX IF NOT EXISTS idx_careers_cached_jobs_updated_at ON careers_cached_jobs(updated_at)",
        ]

    def create_tables(self) -> None:
        conn = self._db_connect()
        try:
            backend = str(getattr(conn, "backend", "sqlite")).strip().lower()
            for statement in self.get_table_creation_sql(backend):
                conn.execute(statement)
            for statement in self.get_index_creation_sql():
                conn.execute(statement)
            conn.commit()
        finally:
            conn.close()

    def save_job(self, user_id: int, job: JobCard | dict[str, Any]) -> SavedJob | None:
        safe_user_id = int(user_id or 0)
        if safe_user_id <= 0:
            return None

        normalized_job = self._normalize_job_card(job)
        now_iso = self._now_iso()
        conn = self._db_connect()
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(
                """
                INSERT INTO careers_saved_jobs (
                    user_id, job_id, title, company, location, source, job_url, posted_at,
                    domain, work_type, level, industry, certifications_json, raw_payload_json,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, job_id) DO UPDATE SET
                    title = excluded.title,
                    company = excluded.company,
                    location = excluded.location,
                    source = excluded.source,
                    job_url = excluded.job_url,
                    posted_at = excluded.posted_at,
                    domain = excluded.domain,
                    work_type = excluded.work_type,
                    level = excluded.level,
                    industry = excluded.industry,
                    certifications_json = excluded.certifications_json,
                    raw_payload_json = excluded.raw_payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    safe_user_id,
                    normalized_job.job_id,
                    normalized_job.title,
                    normalized_job.company,
                    normalized_job.location,
                    normalized_job.source,
                    normalized_job.job_url,
                    normalized_job.posted_at,
                    normalized_job.domain,
                    normalized_job.work_type,
                    normalized_job.level,
                    normalized_job.industry,
                    self._dump_json(list(normalized_job.certifications), "[]"),
                    self._dump_json(normalized_job.raw_payload, "{}"),
                    now_iso,
                    now_iso,
                ),
            )
            conn.commit()
            row = conn.execute(
                """
                SELECT
                    id, user_id, job_id, title, company, location, source, job_url, posted_at,
                    domain, work_type, level, industry, certifications_json, raw_payload_json,
                    created_at, updated_at
                FROM careers_saved_jobs
                WHERE user_id = ? AND job_id = ?
                LIMIT 1
                """,
                (safe_user_id, normalized_job.job_id),
            ).fetchone()
            if row is None:
                return None
            return self._map_saved_job(row)
        finally:
            conn.close()

    def unsave_job(self, user_id: int, job_id: str) -> bool:
        safe_user_id = int(user_id or 0)
        cleaned_job_id = str(job_id or "").strip()
        if safe_user_id <= 0 or not cleaned_job_id:
            return False

        conn = self._db_connect()
        try:
            cursor = conn.execute(
                "DELETE FROM careers_saved_jobs WHERE user_id = ? AND job_id = ?",
                (safe_user_id, cleaned_job_id),
            )
            conn.commit()
            return int(getattr(cursor, "rowcount", 0) or 0) > 0
        finally:
            conn.close()

    def list_saved_jobs(self, user_id: int, limit: int = 100, offset: int = 0) -> list[SavedJob]:
        safe_user_id = int(user_id or 0)
        if safe_user_id <= 0:
            return []

        safe_limit = max(1, min(500, int(limit or 100)))
        safe_offset = max(0, int(offset or 0))
        conn = self._db_connect()
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT
                    id, user_id, job_id, title, company, location, source, job_url, posted_at,
                    domain, work_type, level, industry, certifications_json, raw_payload_json,
                    created_at, updated_at
                FROM careers_saved_jobs
                WHERE user_id = ?
                ORDER BY updated_at DESC, created_at DESC
                LIMIT ? OFFSET ?
                """,
                (safe_user_id, safe_limit, safe_offset),
            ).fetchall()
            return [self._map_saved_job(row) for row in rows]
        finally:
            conn.close()

    def create_application_record(
        self,
        user_id: int,
        job: JobCard | dict[str, Any],
        status: str = "applied",
        notes: str = "",
        applied_at: str = "",
    ) -> ApplicationRecord | None:
        return self.create_or_update_application_record(
            user_id=user_id,
            job=job,
            status=status,
            notes=notes,
            applied_at=applied_at,
        )

    def create_or_update_application_record(
        self,
        user_id: int,
        job: JobCard | dict[str, Any],
        status: str = "applied",
        notes: str = "",
        applied_at: str = "",
    ) -> ApplicationRecord | None:
        safe_user_id = int(user_id or 0)
        if safe_user_id <= 0:
            return None

        normalized_job = self._normalize_job_card(job)
        status_value = self._normalize_status(status)
        notes_value = str(notes or "").strip()
        now_iso = self._now_iso()
        applied_value = str(applied_at or "").strip()
        if not applied_value and status_value == "applied":
            applied_value = now_iso

        conn = self._db_connect()
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(
                """
                INSERT INTO careers_application_records (
                    user_id, job_id, title, company, location, source, job_url, posted_at,
                    status, notes, applied_at, domain, work_type, level, industry,
                    certifications_json, raw_payload_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, job_id) DO UPDATE SET
                    title = excluded.title,
                    company = excluded.company,
                    location = excluded.location,
                    source = excluded.source,
                    job_url = excluded.job_url,
                    posted_at = excluded.posted_at,
                    status = excluded.status,
                    notes = excluded.notes,
                    applied_at = CASE
                        WHEN excluded.applied_at IS NOT NULL AND excluded.applied_at <> '' THEN excluded.applied_at
                        ELSE careers_application_records.applied_at
                    END,
                    domain = excluded.domain,
                    work_type = excluded.work_type,
                    level = excluded.level,
                    industry = excluded.industry,
                    certifications_json = excluded.certifications_json,
                    raw_payload_json = excluded.raw_payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    safe_user_id,
                    normalized_job.job_id,
                    normalized_job.title,
                    normalized_job.company,
                    normalized_job.location,
                    normalized_job.source,
                    normalized_job.job_url,
                    normalized_job.posted_at,
                    status_value,
                    notes_value,
                    applied_value,
                    normalized_job.domain,
                    normalized_job.work_type,
                    normalized_job.level,
                    normalized_job.industry,
                    self._dump_json(list(normalized_job.certifications), "[]"),
                    self._dump_json(normalized_job.raw_payload, "{}"),
                    now_iso,
                    now_iso,
                ),
            )
            conn.commit()
            row = conn.execute(
                """
                SELECT
                    id, user_id, job_id, title, company, location, source, job_url, posted_at,
                    status, notes, applied_at, domain, work_type, level, industry,
                    certifications_json, raw_payload_json, created_at, updated_at
                FROM careers_application_records
                WHERE user_id = ? AND job_id = ?
                LIMIT 1
                """,
                (safe_user_id, normalized_job.job_id),
            ).fetchone()
            if row is None:
                return None
            return self._map_application_record(row)
        finally:
            conn.close()

    def update_application_record(
        self,
        user_id: int,
        job_id: str,
        status: str | None = None,
        notes: str | None = None,
        applied_at: str | None = None,
    ) -> ApplicationRecord | None:
        safe_user_id = int(user_id or 0)
        cleaned_job_id = str(job_id or "").strip()
        if safe_user_id <= 0 or not cleaned_job_id:
            return None

        conn = self._db_connect()
        conn.row_factory = sqlite3.Row
        try:
            existing = conn.execute(
                """
                SELECT
                    id, user_id, job_id, title, company, location, source, job_url, posted_at,
                    status, notes, applied_at, domain, work_type, level, industry,
                    certifications_json, raw_payload_json, created_at, updated_at
                FROM careers_application_records
                WHERE user_id = ? AND job_id = ?
                LIMIT 1
                """,
                (safe_user_id, cleaned_job_id),
            ).fetchone()
            if existing is None:
                return None

            next_status = self._normalize_status(status) if status is not None else str(
                self._row_value(existing, "status", "applied")
            )
            next_notes = (
                str(notes or "").strip()
                if notes is not None
                else str(self._row_value(existing, "notes", "") or "").strip()
            )
            next_applied_at = (
                str(applied_at or "").strip()
                if applied_at is not None
                else str(self._row_value(existing, "applied_at", "") or "").strip()
            )

            now_iso = self._now_iso()
            if not next_applied_at and next_status == "applied":
                next_applied_at = now_iso

            conn.execute(
                """
                UPDATE careers_application_records
                SET
                    status = ?,
                    notes = ?,
                    applied_at = ?,
                    updated_at = ?
                WHERE user_id = ? AND job_id = ?
                """,
                (next_status, next_notes, next_applied_at, now_iso, safe_user_id, cleaned_job_id),
            )
            conn.commit()
            row = conn.execute(
                """
                SELECT
                    id, user_id, job_id, title, company, location, source, job_url, posted_at,
                    status, notes, applied_at, domain, work_type, level, industry,
                    certifications_json, raw_payload_json, created_at, updated_at
                FROM careers_application_records
                WHERE user_id = ? AND job_id = ?
                LIMIT 1
                """,
                (safe_user_id, cleaned_job_id),
            ).fetchone()
            if row is None:
                return None
            return self._map_application_record(row)
        finally:
            conn.close()

    def list_application_records(self, user_id: int, limit: int = 200, offset: int = 0) -> list[ApplicationRecord]:
        safe_user_id = int(user_id or 0)
        if safe_user_id <= 0:
            return []

        safe_limit = max(1, min(500, int(limit or 200)))
        safe_offset = max(0, int(offset or 0))
        conn = self._db_connect()
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT
                    id, user_id, job_id, title, company, location, source, job_url, posted_at,
                    status, notes, applied_at, domain, work_type, level, industry,
                    certifications_json, raw_payload_json, created_at, updated_at
                FROM careers_application_records
                WHERE user_id = ?
                ORDER BY updated_at DESC, created_at DESC
                LIMIT ? OFFSET ?
                """,
                (safe_user_id, safe_limit, safe_offset),
            ).fetchall()
            return [self._map_application_record(row) for row in rows]
        finally:
            conn.close()

    def upsert_cached_job(
        self,
        cache_key: str,
        job: JobCard | dict[str, Any],
        ttl_seconds: int = 300,
    ) -> JobCard | None:
        cleaned_cache_key = self._normalize_cache_key(cache_key)
        if not cleaned_cache_key:
            return None

        normalized_job = self._normalize_job_card(job)
        now = datetime.now(timezone.utc)
        safe_ttl_seconds = max(30, min(86400, int(ttl_seconds or 300)))
        expires_at = (now + timedelta(seconds=safe_ttl_seconds)).isoformat()
        now_iso = now.isoformat()

        conn = self._db_connect()
        try:
            conn.execute(
                """
                INSERT INTO careers_cached_jobs (
                    cache_key, job_id, title, company, location, source, job_url, posted_at,
                    domain, work_type, level, industry, certifications_json, raw_payload_json,
                    expires_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key, job_id) DO UPDATE SET
                    title = excluded.title,
                    company = excluded.company,
                    location = excluded.location,
                    source = excluded.source,
                    job_url = excluded.job_url,
                    posted_at = excluded.posted_at,
                    domain = excluded.domain,
                    work_type = excluded.work_type,
                    level = excluded.level,
                    industry = excluded.industry,
                    certifications_json = excluded.certifications_json,
                    raw_payload_json = excluded.raw_payload_json,
                    expires_at = excluded.expires_at,
                    updated_at = excluded.updated_at
                """,
                (
                    cleaned_cache_key,
                    normalized_job.job_id,
                    normalized_job.title,
                    normalized_job.company,
                    normalized_job.location,
                    normalized_job.source,
                    normalized_job.job_url,
                    normalized_job.posted_at,
                    normalized_job.domain,
                    normalized_job.work_type,
                    normalized_job.level,
                    normalized_job.industry,
                    self._dump_json(list(normalized_job.certifications), "[]"),
                    self._dump_json(normalized_job.raw_payload, "{}"),
                    expires_at,
                    now_iso,
                    now_iso,
                ),
            )
            conn.commit()
            return normalized_job
        finally:
            conn.close()

    def get_cached_jobs(self, cache_key: str, limit: int = 200) -> list[JobCard]:
        cleaned_cache_key = self._normalize_cache_key(cache_key)
        if not cleaned_cache_key:
            return []

        safe_limit = max(1, min(500, int(limit or 200)))
        now_iso = self._now_iso()
        conn = self._db_connect()
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(
                "DELETE FROM careers_cached_jobs WHERE cache_key = ? AND expires_at <= ?",
                (cleaned_cache_key, now_iso),
            )
            rows = conn.execute(
                """
                SELECT
                    job_id, title, company, location, source, job_url, posted_at,
                    domain, work_type, level, industry, certifications_json, raw_payload_json
                FROM careers_cached_jobs
                WHERE cache_key = ? AND expires_at > ?
                ORDER BY updated_at DESC, created_at DESC
                LIMIT ?
                """,
                (cleaned_cache_key, now_iso, safe_limit),
            ).fetchall()
            conn.commit()
            return [self._map_job_card(row) for row in rows]
        finally:
            conn.close()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _normalize_cache_key(cache_key: str) -> str:
        cleaned = str(cache_key or "").strip().lower()
        if not cleaned:
            return ""
        return cleaned[:180]

    def _normalize_job_card(self, job: JobCard | dict[str, Any]) -> JobCard:
        base = job if isinstance(job, JobCard) else JobCard.from_dict(job if isinstance(job, dict) else {})
        normalized_certifications = self._normalize_str_tuple(base.certifications)
        normalized_tags = self._normalize_str_tuple(base.tags)
        normalized_payload = dict(base.raw_payload) if isinstance(base.raw_payload, dict) else {}
        candidate_id = str(base.job_id or "").strip()
        if not candidate_id:
            raw_key = "|".join(
                [
                    str(base.title or "").strip().lower(),
                    str(base.company or "").strip().lower(),
                    str(base.location or "").strip().lower(),
                    str(base.source or "").strip().lower(),
                    str(base.job_url or "").strip().lower(),
                ]
            )
            candidate_id = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:24]

        return JobCard(
            job_id=candidate_id,
            title=str(base.title or "").strip() or "Untitled role",
            company=str(base.company or "").strip() or "Unknown company",
            location=str(base.location or "").strip() or "Location not listed",
            source=str(base.source or "").strip() or "Unknown source",
            job_url=str(base.job_url or "").strip(),
            description=str(base.description or "").strip(),
            posted_at=str(base.posted_at or "").strip(),
            domain=str(base.domain or "").strip(),
            work_type=str(base.work_type or "").strip(),
            level=str(base.level or "").strip(),
            industry=str(base.industry or "").strip(),
            certifications=normalized_certifications,
            tags=normalized_tags,
            raw_payload=normalized_payload,
        )

    @staticmethod
    def _normalize_status(raw_status: str) -> str:
        cleaned = str(raw_status or "").strip().lower().replace("-", "_").replace(" ", "_")
        if cleaned == "interviewing":
            cleaned = "interview"
        if cleaned in CareersRepository._VALID_APPLICATION_STATUSES:
            return cleaned
        return "applied"

    @staticmethod
    def _normalize_str_tuple(items: tuple[str, ...] | list[str] | str) -> tuple[str, ...]:
        if isinstance(items, str):
            values = [token.strip() for token in items.split(",")]
        else:
            values = [str(item).strip() for item in list(items)]

        deduped: list[str] = []
        seen: set[str] = set()
        for value in values:
            if not value:
                continue
            lowered = value.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            deduped.append(value)
        return tuple(deduped)

    @staticmethod
    def _dump_json(payload: Any, fallback: str) -> str:
        try:
            return json.dumps(payload, ensure_ascii=True)
        except Exception:
            return fallback

    @staticmethod
    def _load_json_dict(raw_payload: Any) -> dict[str, Any]:
        raw_text = str(raw_payload or "").strip()
        if not raw_text:
            return {}
        try:
            parsed = json.loads(raw_text)
        except Exception:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}

    @staticmethod
    def _load_json_list_as_tuple(raw_payload: Any) -> tuple[str, ...]:
        raw_text = str(raw_payload or "").strip()
        if not raw_text:
            return tuple()
        try:
            parsed = json.loads(raw_text)
        except Exception:
            return tuple()
        if not isinstance(parsed, list):
            return tuple()
        return tuple(str(item).strip() for item in parsed if str(item).strip())

    @staticmethod
    def _row_value(row: Any, key: str, default: Any = None) -> Any:
        if isinstance(row, dict):
            return row.get(key, default)
        if hasattr(row, "__getitem__"):
            try:
                return row[key]
            except Exception:
                return default
        return default

    def _map_job_card(self, row: Any) -> JobCard:
        return JobCard(
            job_id=str(self._row_value(row, "job_id", "") or "").strip(),
            title=str(self._row_value(row, "title", "") or "").strip(),
            company=str(self._row_value(row, "company", "") or "").strip(),
            location=str(self._row_value(row, "location", "") or "").strip(),
            source=str(self._row_value(row, "source", "") or "").strip(),
            job_url=str(self._row_value(row, "job_url", "") or "").strip(),
            description=str(self._row_value(row, "description", "") or "").strip(),
            posted_at=str(self._row_value(row, "posted_at", "") or "").strip(),
            domain=str(self._row_value(row, "domain", "") or "").strip(),
            work_type=str(self._row_value(row, "work_type", "") or "").strip(),
            level=str(self._row_value(row, "level", "") or "").strip(),
            industry=str(self._row_value(row, "industry", "") or "").strip(),
            certifications=self._load_json_list_as_tuple(self._row_value(row, "certifications_json", "[]")),
            tags=self._normalize_str_tuple(self._row_value(row, "tags", ()) or ()),
            raw_payload=self._load_json_dict(self._row_value(row, "raw_payload_json", "{}")),
        )

    def _map_saved_job(self, row: Any) -> SavedJob:
        return SavedJob(
            id=int(self._row_value(row, "id", 0) or 0),
            user_id=int(self._row_value(row, "user_id", 0) or 0),
            job=self._map_job_card(row),
            created_at=str(self._row_value(row, "created_at", "") or "").strip(),
            updated_at=str(self._row_value(row, "updated_at", "") or "").strip(),
        )

    def _map_application_record(self, row: Any) -> ApplicationRecord:
        return ApplicationRecord(
            id=int(self._row_value(row, "id", 0) or 0),
            user_id=int(self._row_value(row, "user_id", 0) or 0),
            job=self._map_job_card(row),
            status=str(self._row_value(row, "status", "applied") or "applied").strip().lower(),
            notes=str(self._row_value(row, "notes", "") or "").strip(),
            applied_at=str(self._row_value(row, "applied_at", "") or "").strip(),
            created_at=str(self._row_value(row, "created_at", "") or "").strip(),
            updated_at=str(self._row_value(row, "updated_at", "") or "").strip(),
        )
