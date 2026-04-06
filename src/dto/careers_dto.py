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
class JobCard:
    job_id: str
    title: str
    company: str
    location: str
    source: str
    job_url: str = ""
    description: str = ""
    posted_at: str = ""
    domain: str = ""
    work_type: str = ""
    level: str = ""
    industry: str = ""
    certifications: tuple[str, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "JobCard":
        raw = dict(payload or {})
        return cls(
            job_id=_clean_text(raw.get("job_id")),
            title=_clean_text(raw.get("title")),
            company=_clean_text(raw.get("company")),
            location=_clean_text(raw.get("location")),
            source=_clean_text(raw.get("source")),
            job_url=_clean_text(raw.get("job_url")),
            description=_clean_text(raw.get("description")),
            posted_at=_clean_text(raw.get("posted_at")),
            domain=_clean_text(raw.get("domain")),
            work_type=_clean_text(raw.get("work_type")),
            level=_clean_text(raw.get("level")),
            industry=_clean_text(raw.get("industry")),
            certifications=_normalize_str_tuple(raw.get("certifications")),
            tags=_normalize_str_tuple(raw.get("tags")),
            raw_payload=_normalize_payload(raw.get("raw_payload")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "source": self.source,
            "job_url": self.job_url,
            "description": self.description,
            "posted_at": self.posted_at,
            "domain": self.domain,
            "work_type": self.work_type,
            "level": self.level,
            "industry": self.industry,
            "certifications": list(self.certifications),
            "tags": list(self.tags),
            "raw_payload": dict(self.raw_payload),
        }


@dataclass(frozen=True)
class JobFilters:
    query: str = ""
    location: str = ""
    role_match_mode: str = "balanced"
    posted_within_days: int = 0
    domains: tuple[str, ...] = field(default_factory=tuple)
    work_types: tuple[str, ...] = field(default_factory=tuple)
    levels: tuple[str, ...] = field(default_factory=tuple)
    industries: tuple[str, ...] = field(default_factory=tuple)
    certifications: tuple[str, ...] = field(default_factory=tuple)
    sources: tuple[str, ...] = field(default_factory=tuple)
    recommendations: tuple[str, ...] = field(default_factory=tuple)
    min_match_score: int = 0
    limit: int = 25
    offset: int = 0

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "JobFilters":
        raw = dict(payload or {})
        return cls(
            query=_clean_text(raw.get("query")),
            location=_clean_text(raw.get("location")),
            role_match_mode=(
                _clean_text(raw.get("role_match_mode")).lower()
                if _clean_text(raw.get("role_match_mode")).lower() in {"strict", "balanced", "broad"}
                else "balanced"
            ),
            posted_within_days=_normalize_int(raw.get("posted_within_days"), default=0, min_value=0, max_value=60),
            domains=_normalize_str_tuple(raw.get("domains")),
            work_types=_normalize_str_tuple(raw.get("work_types")),
            levels=_normalize_str_tuple(raw.get("levels")),
            industries=_normalize_str_tuple(raw.get("industries")),
            certifications=_normalize_str_tuple(raw.get("certifications")),
            sources=_normalize_str_tuple(raw.get("sources")),
            recommendations=_normalize_str_tuple(raw.get("recommendations")),
            min_match_score=_normalize_int(raw.get("min_match_score"), default=0, min_value=0, max_value=100),
            limit=_normalize_int(raw.get("limit"), default=25, min_value=1, max_value=200),
            offset=_normalize_int(raw.get("offset"), default=0, min_value=0),
        )


@dataclass(frozen=True)
class SavedJob:
    id: int
    user_id: int
    job: JobCard
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ApplicationRecord:
    id: int
    user_id: int
    job: JobCard
    status: str
    notes: str
    applied_at: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class JobMatchResult:
    job_id: str
    match_score: int
    why_fit: str = ""
    ai_summary: str = ""
    why_fit_points: tuple[str, ...] = field(default_factory=tuple)
    missing_skills: tuple[str, ...] = field(default_factory=tuple)
    recommendation: str = "IMPROVE_FIRST"
    improvement_suggestions: tuple[str, ...] = field(default_factory=tuple)
    computed_at: str = ""
    analysis_timestamp: str = ""
    analysis_source: str = ""
