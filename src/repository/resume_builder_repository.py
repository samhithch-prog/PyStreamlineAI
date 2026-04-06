from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Callable

from src.dto.resume_builder_dto import (
    GeneratedResume,
    ResumeCertification,
    ResumeEducation,
    ResumeExperience,
    ResumeProfile,
    ResumeProject,
)


class ResumeBuilderRepository:
    """Persistence layer for resume profile drafts and generated resumes."""

    def __init__(self, db_connect: Callable[[], Any]) -> None:
        self._db_connect = db_connect

    @staticmethod
    def get_table_creation_sql(backend: str) -> list[str]:
        normalized_backend = str(backend or "").strip().lower()
        id_pk_sql = "BIGSERIAL PRIMARY KEY" if normalized_backend == "postgres" else "INTEGER PRIMARY KEY AUTOINCREMENT"
        fk_type = "BIGINT" if normalized_backend == "postgres" else "INTEGER"
        return [
            f"""
            CREATE TABLE IF NOT EXISTS resume_profile_drafts (
                id {id_pk_sql},
                user_id {fk_type} NOT NULL UNIQUE,
                full_name TEXT,
                email TEXT,
                phone TEXT,
                location TEXT,
                linkedin_url TEXT,
                portfolio_url TEXT,
                summary TEXT,
                skills_json TEXT NOT NULL DEFAULT '[]',
                experiences_json TEXT NOT NULL DEFAULT '[]',
                educations_json TEXT NOT NULL DEFAULT '[]',
                projects_json TEXT NOT NULL DEFAULT '[]',
                certifications_json TEXT NOT NULL DEFAULT '[]',
                target_role TEXT,
                target_job_link TEXT,
                target_job_description TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS generated_resumes (
                id {id_pk_sql},
                user_id {fk_type} NOT NULL,
                resume_title TEXT,
                professional_summary TEXT,
                resume_markdown TEXT,
                resume_text TEXT,
                sections_json TEXT NOT NULL DEFAULT '{{}}',
                profile_snapshot_json TEXT NOT NULL DEFAULT '{{}}',
                model_name TEXT,
                prompt_version TEXT,
                source_job_id TEXT,
                target_job_title TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """,
        ]

    @staticmethod
    def get_index_creation_sql() -> list[str]:
        return [
            "CREATE INDEX IF NOT EXISTS idx_resume_profile_drafts_user_id ON resume_profile_drafts(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_resume_profile_drafts_updated_at ON resume_profile_drafts(updated_at)",
            "CREATE INDEX IF NOT EXISTS idx_generated_resumes_user_id ON generated_resumes(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_generated_resumes_updated_at ON generated_resumes(updated_at)",
            "CREATE INDEX IF NOT EXISTS idx_generated_resumes_created_at ON generated_resumes(created_at)",
        ]

    def create_tables(self) -> None:
        conn = self._db_connect()
        try:
            backend = str(getattr(conn, "backend", "sqlite")).strip().lower()
            for statement in self.get_table_creation_sql(backend):
                conn.execute(statement)
            self._ensure_schema_columns(conn)
            for statement in self.get_index_creation_sql():
                conn.execute(statement)
            conn.commit()
        finally:
            conn.close()

    def save_resume_profile_draft(self, user_id: int, profile: ResumeProfile | dict[str, Any]) -> ResumeProfile | None:
        safe_user_id = int(user_id or 0)
        if safe_user_id <= 0:
            return None

        normalized = self._normalize_profile(profile, safe_user_id)
        now_iso = self._now_iso()
        conn = self._db_connect()
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(
                """
                INSERT INTO resume_profile_drafts (
                    user_id, full_name, email, phone, location, linkedin_url, portfolio_url, summary,
                    skills_json, experiences_json, educations_json, projects_json, certifications_json,
                    target_role, target_job_link, target_job_description, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    full_name = excluded.full_name,
                    email = excluded.email,
                    phone = excluded.phone,
                    location = excluded.location,
                    linkedin_url = excluded.linkedin_url,
                    portfolio_url = excluded.portfolio_url,
                    summary = excluded.summary,
                    skills_json = excluded.skills_json,
                    experiences_json = excluded.experiences_json,
                    educations_json = excluded.educations_json,
                    projects_json = excluded.projects_json,
                    certifications_json = excluded.certifications_json,
                    target_role = excluded.target_role,
                    target_job_link = excluded.target_job_link,
                    target_job_description = excluded.target_job_description,
                    updated_at = excluded.updated_at
                """,
                (
                    safe_user_id,
                    normalized.full_name,
                    normalized.email,
                    normalized.phone,
                    normalized.location,
                    normalized.linkedin_url,
                    normalized.portfolio_url,
                    normalized.summary,
                    self._dump_json(list(normalized.skills), "[]"),
                    self._dump_json([item.to_dict() for item in normalized.experiences], "[]"),
                    self._dump_json([item.to_dict() for item in normalized.educations], "[]"),
                    self._dump_json([item.to_dict() for item in normalized.projects], "[]"),
                    self._dump_json([item.to_dict() for item in normalized.certifications], "[]"),
                    normalized.target_role,
                    normalized.target_job_link,
                    normalized.target_job_description,
                    now_iso,
                    now_iso,
                ),
            )
            conn.commit()
            row = conn.execute(
                """
                SELECT
                    id, user_id, full_name, email, phone, location, linkedin_url, portfolio_url, summary,
                    skills_json, experiences_json, educations_json, projects_json, certifications_json,
                    target_role, target_job_link, target_job_description, created_at, updated_at
                FROM resume_profile_drafts
                WHERE user_id = ?
                LIMIT 1
                """,
                (safe_user_id,),
            ).fetchone()
            if row is None:
                return None
            return self._map_resume_profile(row)
        finally:
            conn.close()

    def get_resume_profile_draft(self, user_id: int) -> ResumeProfile | None:
        safe_user_id = int(user_id or 0)
        if safe_user_id <= 0:
            return None

        conn = self._db_connect()
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                """
                SELECT
                    id, user_id, full_name, email, phone, location, linkedin_url, portfolio_url, summary,
                    skills_json, experiences_json, educations_json, projects_json, certifications_json,
                    target_role, target_job_link, target_job_description, created_at, updated_at
                FROM resume_profile_drafts
                WHERE user_id = ?
                LIMIT 1
                """,
                (safe_user_id,),
            ).fetchone()
            if row is None:
                return None
            return self._map_resume_profile(row)
        finally:
            conn.close()

    def save_generated_resume(
        self,
        user_id: int,
        generated_resume: GeneratedResume | dict[str, Any],
    ) -> GeneratedResume | None:
        safe_user_id = int(user_id or 0)
        if safe_user_id <= 0:
            return None

        normalized = self._normalize_generated_resume(generated_resume, safe_user_id)
        now_iso = self._now_iso()
        conn = self._db_connect()
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(
                """
                INSERT INTO generated_resumes (
                    user_id, resume_title, professional_summary, resume_markdown, resume_text,
                    sections_json, profile_snapshot_json, model_name, prompt_version,
                    source_job_id, target_job_title, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    safe_user_id,
                    normalized.resume_title,
                    normalized.professional_summary,
                    normalized.resume_markdown,
                    normalized.resume_text,
                    self._dump_json(normalized.sections, "{}"),
                    self._dump_json(normalized.profile_snapshot, "{}"),
                    normalized.model_name,
                    normalized.prompt_version,
                    normalized.source_job_id,
                    normalized.target_job_title,
                    now_iso,
                    now_iso,
                ),
            )
            conn.commit()
            row = conn.execute(
                """
                SELECT
                    id, user_id, resume_title, professional_summary, resume_markdown, resume_text,
                    sections_json, profile_snapshot_json, model_name, prompt_version,
                    source_job_id, target_job_title, created_at, updated_at
                FROM generated_resumes
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (safe_user_id,),
            ).fetchone()
            if row is None:
                return None
            return self._map_generated_resume(row)
        finally:
            conn.close()

    def list_generated_resumes(self, user_id: int, limit: int = 20, offset: int = 0) -> list[GeneratedResume]:
        safe_user_id = int(user_id or 0)
        if safe_user_id <= 0:
            return []

        safe_limit = max(1, min(200, int(limit or 20)))
        safe_offset = max(0, int(offset or 0))
        conn = self._db_connect()
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT
                    id, user_id, resume_title, professional_summary, resume_markdown, resume_text,
                    sections_json, profile_snapshot_json, model_name, prompt_version,
                    source_job_id, target_job_title, created_at, updated_at
                FROM generated_resumes
                WHERE user_id = ?
                ORDER BY updated_at DESC, created_at DESC
                LIMIT ? OFFSET ?
                """,
                (safe_user_id, safe_limit, safe_offset),
            ).fetchall()
            return [self._map_generated_resume(row) for row in rows]
        finally:
            conn.close()

    def get_latest_generated_resume(self, user_id: int) -> GeneratedResume | None:
        safe_user_id = int(user_id or 0)
        if safe_user_id <= 0:
            return None

        conn = self._db_connect()
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                """
                SELECT
                    id, user_id, resume_title, professional_summary, resume_markdown, resume_text,
                    sections_json, profile_snapshot_json, model_name, prompt_version,
                    source_job_id, target_job_title, created_at, updated_at
                FROM generated_resumes
                WHERE user_id = ?
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 1
                """,
                (safe_user_id,),
            ).fetchone()
            if row is None:
                return None
            return self._map_generated_resume(row)
        finally:
            conn.close()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _dump_json(payload: Any, fallback: str) -> str:
        try:
            return json.dumps(payload, ensure_ascii=True)
        except Exception:
            return fallback

    @staticmethod
    def _load_json(raw_payload: Any, fallback: Any) -> Any:
        raw_text = str(raw_payload or "").strip()
        if not raw_text:
            return fallback
        try:
            return json.loads(raw_text)
        except Exception:
            return fallback

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

    def _normalize_profile(self, profile: ResumeProfile | dict[str, Any], user_id: int) -> ResumeProfile:
        base = profile if isinstance(profile, ResumeProfile) else ResumeProfile.from_dict(profile if isinstance(profile, dict) else {})
        return ResumeProfile(
            id=int(base.id or 0),
            user_id=int(user_id),
            full_name=str(base.full_name or "").strip(),
            email=str(base.email or "").strip().lower(),
            phone=str(base.phone or "").strip(),
            location=str(base.location or "").strip(),
            linkedin_url=str(base.linkedin_url or "").strip(),
            portfolio_url=str(base.portfolio_url or "").strip(),
            summary=str(base.summary or "").strip(),
            skills=tuple(str(item).strip() for item in base.skills if str(item).strip()),
            experiences=tuple(base.experiences),
            educations=tuple(base.educations),
            projects=tuple(base.projects),
            certifications=tuple(base.certifications),
            target_role=str(base.target_role or "").strip(),
            target_job_link=str(base.target_job_link or "").strip(),
            target_job_description=str(base.target_job_description or "").strip(),
            created_at=str(base.created_at or "").strip(),
            updated_at=str(base.updated_at or "").strip(),
        )

    def _normalize_generated_resume(self, generated: GeneratedResume | dict[str, Any], user_id: int) -> GeneratedResume:
        base = generated if isinstance(generated, GeneratedResume) else GeneratedResume.from_dict(generated if isinstance(generated, dict) else {})
        return GeneratedResume(
            id=int(base.id or 0),
            user_id=int(user_id),
            resume_title=str(base.resume_title or "").strip(),
            professional_summary=str(base.professional_summary or "").strip(),
            resume_markdown=str(base.resume_markdown or "").strip(),
            resume_text=str(base.resume_text or "").strip(),
            sections=dict(base.sections or {}),
            profile_snapshot=dict(base.profile_snapshot or {}),
            model_name=str(base.model_name or "").strip(),
            prompt_version=str(base.prompt_version or "").strip(),
            source_job_id=str(base.source_job_id or "").strip(),
            target_job_title=str(base.target_job_title or "").strip(),
            created_at=str(base.created_at or "").strip(),
            updated_at=str(base.updated_at or "").strip(),
        )

    def _map_resume_profile(self, row: Any) -> ResumeProfile:
        experiences_raw = self._load_json(self._row_value(row, "experiences_json", "[]"), [])
        educations_raw = self._load_json(self._row_value(row, "educations_json", "[]"), [])
        projects_raw = self._load_json(self._row_value(row, "projects_json", "[]"), [])
        certifications_raw = self._load_json(self._row_value(row, "certifications_json", "[]"), [])

        experiences = tuple(
            ResumeExperience.from_dict(item) for item in experiences_raw if isinstance(item, dict)
        )
        educations = tuple(
            ResumeEducation.from_dict(item) for item in educations_raw if isinstance(item, dict)
        )
        projects = tuple(
            ResumeProject.from_dict(item) for item in projects_raw if isinstance(item, dict)
        )
        certifications = tuple(
            ResumeCertification.from_dict(item) for item in certifications_raw if isinstance(item, dict)
        )

        skills_raw = self._load_json(self._row_value(row, "skills_json", "[]"), [])
        skills = tuple(str(item).strip() for item in skills_raw if str(item).strip()) if isinstance(skills_raw, list) else tuple()

        return ResumeProfile(
            id=int(self._row_value(row, "id", 0) or 0),
            user_id=int(self._row_value(row, "user_id", 0) or 0),
            full_name=str(self._row_value(row, "full_name", "") or "").strip(),
            email=str(self._row_value(row, "email", "") or "").strip().lower(),
            phone=str(self._row_value(row, "phone", "") or "").strip(),
            location=str(self._row_value(row, "location", "") or "").strip(),
            linkedin_url=str(self._row_value(row, "linkedin_url", "") or "").strip(),
            portfolio_url=str(self._row_value(row, "portfolio_url", "") or "").strip(),
            summary=str(self._row_value(row, "summary", "") or "").strip(),
            skills=skills,
            experiences=experiences,
            educations=educations,
            projects=projects,
            certifications=certifications,
            target_role=str(self._row_value(row, "target_role", "") or "").strip(),
            target_job_link=str(self._row_value(row, "target_job_link", "") or "").strip(),
            target_job_description=str(self._row_value(row, "target_job_description", "") or "").strip(),
            created_at=str(self._row_value(row, "created_at", "") or "").strip(),
            updated_at=str(self._row_value(row, "updated_at", "") or "").strip(),
        )

    def _map_generated_resume(self, row: Any) -> GeneratedResume:
        sections = self._load_json(self._row_value(row, "sections_json", "{}"), {})
        profile_snapshot = self._load_json(self._row_value(row, "profile_snapshot_json", "{}"), {})
        if not isinstance(sections, dict):
            sections = {}
        if not isinstance(profile_snapshot, dict):
            profile_snapshot = {}

        return GeneratedResume(
            id=int(self._row_value(row, "id", 0) or 0),
            user_id=int(self._row_value(row, "user_id", 0) or 0),
            resume_title=str(self._row_value(row, "resume_title", "") or "").strip(),
            professional_summary=str(self._row_value(row, "professional_summary", "") or "").strip(),
            resume_markdown=str(self._row_value(row, "resume_markdown", "") or "").strip(),
            resume_text=str(self._row_value(row, "resume_text", "") or "").strip(),
            sections=sections,
            profile_snapshot=profile_snapshot,
            model_name=str(self._row_value(row, "model_name", "") or "").strip(),
            prompt_version=str(self._row_value(row, "prompt_version", "") or "").strip(),
            source_job_id=str(self._row_value(row, "source_job_id", "") or "").strip(),
            target_job_title=str(self._row_value(row, "target_job_title", "") or "").strip(),
            created_at=str(self._row_value(row, "created_at", "") or "").strip(),
            updated_at=str(self._row_value(row, "updated_at", "") or "").strip(),
        )

    def _ensure_schema_columns(self, conn: Any) -> None:
        profile_columns = self._get_table_columns(conn, "resume_profile_drafts")
        if "target_job_link" not in profile_columns:
            conn.execute("ALTER TABLE resume_profile_drafts ADD COLUMN target_job_link TEXT")

    @staticmethod
    def _get_table_columns(conn: Any, table_name: str) -> set[str]:
        backend = str(getattr(conn, "backend", "sqlite")).strip().lower()
        if backend == "postgres":
            rows = conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = ?
                """,
                (str(table_name or "").strip(),),
            ).fetchall()
            names: set[str] = set()
            for row in rows:
                if isinstance(row, dict):
                    names.add(str(row.get("column_name", "")).strip())
                elif isinstance(row, (tuple, list)) and row:
                    names.add(str(row[0]).strip())
            return names

        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        names: set[str] = set()
        for row in rows:
            if isinstance(row, dict):
                names.add(str(row.get("name", "")).strip())
            elif isinstance(row, (tuple, list)) and len(row) > 1:
                names.add(str(row[1]).strip())
        return names
