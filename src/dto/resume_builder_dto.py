from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_int(value: Any, default: int = 0, min_value: int | None = None, max_value: int | None = None) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = int(default)
    if min_value is not None:
        parsed = max(int(min_value), parsed)
    if max_value is not None:
        parsed = min(int(max_value), parsed)
    return parsed


def _normalize_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    cleaned = str(value or "").strip().lower()
    if not cleaned:
        return default
    return cleaned in {"1", "true", "yes", "y", "on"}


def _normalize_str_tuple(items: Any) -> tuple[str, ...]:
    if isinstance(items, str):
        values = [item.strip() for item in items.split(",")]
    elif isinstance(items, (list, tuple, set)):
        values = [str(item).strip() for item in items]
    else:
        values = []

    deduped: list[str] = []
    seen: set[str] = set()
    for item in values:
        if not item:
            continue
        lowered = item.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(item)
    return tuple(deduped)


def _normalize_payload(raw: Any) -> dict[str, Any]:
    return dict(raw) if isinstance(raw, dict) else {}


@dataclass(frozen=True)
class ResumeExperience:
    company: str = ""
    role: str = ""
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    is_current: bool = False
    description: str = ""
    bullets: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ResumeExperience":
        raw = dict(payload or {})
        return cls(
            company=_clean_text(raw.get("company")),
            role=_clean_text(raw.get("role")),
            location=_clean_text(raw.get("location")),
            start_date=_clean_text(raw.get("start_date")),
            end_date=_clean_text(raw.get("end_date")),
            is_current=_normalize_bool(raw.get("is_current"), default=False),
            description=_clean_text(raw.get("description")),
            bullets=_normalize_str_tuple(raw.get("bullets")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "company": self.company,
            "role": self.role,
            "location": self.location,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "is_current": self.is_current,
            "description": self.description,
            "bullets": list(self.bullets),
        }


@dataclass(frozen=True)
class ResumeEducation:
    institution: str = ""
    degree: str = ""
    field_of_study: str = ""
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    grade: str = ""
    details: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ResumeEducation":
        raw = dict(payload or {})
        return cls(
            institution=_clean_text(raw.get("institution")),
            degree=_clean_text(raw.get("degree")),
            field_of_study=_clean_text(raw.get("field_of_study")),
            location=_clean_text(raw.get("location")),
            start_date=_clean_text(raw.get("start_date")),
            end_date=_clean_text(raw.get("end_date")),
            grade=_clean_text(raw.get("grade")),
            details=_clean_text(raw.get("details")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "institution": self.institution,
            "degree": self.degree,
            "field_of_study": self.field_of_study,
            "location": self.location,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "grade": self.grade,
            "details": self.details,
        }


@dataclass(frozen=True)
class ResumeProject:
    name: str = ""
    role: str = ""
    summary: str = ""
    technologies: tuple[str, ...] = field(default_factory=tuple)
    link: str = ""
    bullets: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ResumeProject":
        raw = dict(payload or {})
        return cls(
            name=_clean_text(raw.get("name")),
            role=_clean_text(raw.get("role")),
            summary=_clean_text(raw.get("summary")),
            technologies=_normalize_str_tuple(raw.get("technologies")),
            link=_clean_text(raw.get("link")),
            bullets=_normalize_str_tuple(raw.get("bullets")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "summary": self.summary,
            "technologies": list(self.technologies),
            "link": self.link,
            "bullets": list(self.bullets),
        }


@dataclass(frozen=True)
class ResumeCertification:
    name: str = ""
    issuer: str = ""
    issue_date: str = ""
    expiry_date: str = ""
    credential_id: str = ""
    credential_url: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ResumeCertification":
        raw = dict(payload or {})
        return cls(
            name=_clean_text(raw.get("name")),
            issuer=_clean_text(raw.get("issuer")),
            issue_date=_clean_text(raw.get("issue_date")),
            expiry_date=_clean_text(raw.get("expiry_date")),
            credential_id=_clean_text(raw.get("credential_id")),
            credential_url=_clean_text(raw.get("credential_url")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "issuer": self.issuer,
            "issue_date": self.issue_date,
            "expiry_date": self.expiry_date,
            "credential_id": self.credential_id,
            "credential_url": self.credential_url,
        }


@dataclass(frozen=True)
class ResumeProfile:
    id: int = 0
    user_id: int = 0
    full_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin_url: str = ""
    portfolio_url: str = ""
    summary: str = ""
    skills: tuple[str, ...] = field(default_factory=tuple)
    experiences: tuple[ResumeExperience, ...] = field(default_factory=tuple)
    educations: tuple[ResumeEducation, ...] = field(default_factory=tuple)
    projects: tuple[ResumeProject, ...] = field(default_factory=tuple)
    certifications: tuple[ResumeCertification, ...] = field(default_factory=tuple)
    target_role: str = ""
    target_job_link: str = ""
    target_job_description: str = ""
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ResumeProfile":
        raw = dict(payload or {})
        experiences = tuple(
            item if isinstance(item, ResumeExperience) else ResumeExperience.from_dict(item)
            for item in _normalize_list_of_dicts(raw.get("experiences"))
        )
        educations = tuple(
            item if isinstance(item, ResumeEducation) else ResumeEducation.from_dict(item)
            for item in _normalize_list_of_dicts(raw.get("educations"))
        )
        projects = tuple(
            item if isinstance(item, ResumeProject) else ResumeProject.from_dict(item)
            for item in _normalize_list_of_dicts(raw.get("projects"))
        )
        certifications = tuple(
            item if isinstance(item, ResumeCertification) else ResumeCertification.from_dict(item)
            for item in _normalize_list_of_dicts(raw.get("certifications"))
        )

        return cls(
            id=_normalize_int(raw.get("id"), default=0, min_value=0),
            user_id=_normalize_int(raw.get("user_id"), default=0, min_value=0),
            full_name=_clean_text(raw.get("full_name")),
            email=_clean_text(raw.get("email")).lower(),
            phone=_clean_text(raw.get("phone")),
            location=_clean_text(raw.get("location")),
            linkedin_url=_clean_text(raw.get("linkedin_url")),
            portfolio_url=_clean_text(raw.get("portfolio_url")),
            summary=_clean_text(raw.get("summary")),
            skills=_normalize_str_tuple(raw.get("skills")),
            experiences=experiences,
            educations=educations,
            projects=projects,
            certifications=certifications,
            target_role=_clean_text(raw.get("target_role")),
            target_job_link=_clean_text(raw.get("target_job_link")),
            target_job_description=_clean_text(raw.get("target_job_description")),
            created_at=_clean_text(raw.get("created_at")),
            updated_at=_clean_text(raw.get("updated_at")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "full_name": self.full_name,
            "email": self.email,
            "phone": self.phone,
            "location": self.location,
            "linkedin_url": self.linkedin_url,
            "portfolio_url": self.portfolio_url,
            "summary": self.summary,
            "skills": list(self.skills),
            "experiences": [item.to_dict() for item in self.experiences],
            "educations": [item.to_dict() for item in self.educations],
            "projects": [item.to_dict() for item in self.projects],
            "certifications": [item.to_dict() for item in self.certifications],
            "target_role": self.target_role,
            "target_job_link": self.target_job_link,
            "target_job_description": self.target_job_description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class GeneratedResume:
    id: int = 0
    user_id: int = 0
    resume_title: str = ""
    professional_summary: str = ""
    resume_markdown: str = ""
    resume_text: str = ""
    sections: dict[str, Any] = field(default_factory=dict)
    profile_snapshot: dict[str, Any] = field(default_factory=dict)
    model_name: str = ""
    prompt_version: str = ""
    source_job_id: str = ""
    target_job_title: str = ""
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "GeneratedResume":
        raw = dict(payload or {})
        return cls(
            id=_normalize_int(raw.get("id"), default=0, min_value=0),
            user_id=_normalize_int(raw.get("user_id"), default=0, min_value=0),
            resume_title=_clean_text(raw.get("resume_title")),
            professional_summary=_clean_text(raw.get("professional_summary")),
            resume_markdown=_clean_text(raw.get("resume_markdown")),
            resume_text=_clean_text(raw.get("resume_text")),
            sections=_normalize_payload(raw.get("sections")),
            profile_snapshot=_normalize_payload(raw.get("profile_snapshot")),
            model_name=_clean_text(raw.get("model_name")),
            prompt_version=_clean_text(raw.get("prompt_version")),
            source_job_id=_clean_text(raw.get("source_job_id")),
            target_job_title=_clean_text(raw.get("target_job_title")),
            created_at=_clean_text(raw.get("created_at")),
            updated_at=_clean_text(raw.get("updated_at")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "resume_title": self.resume_title,
            "professional_summary": self.professional_summary,
            "resume_markdown": self.resume_markdown,
            "resume_text": self.resume_text,
            "sections": dict(self.sections),
            "profile_snapshot": dict(self.profile_snapshot),
            "model_name": self.model_name,
            "prompt_version": self.prompt_version,
            "source_job_id": self.source_job_id,
            "target_job_title": self.target_job_title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class ResumeExportResult:
    ok: bool
    message: str
    export_format: str
    file_name: str
    mime_type: str
    content: bytes = b""


def _normalize_list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, (list, tuple)):
        return [dict(item) for item in value if isinstance(item, dict)]
    return []
