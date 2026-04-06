from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import urlsplit

from src.dto.careers_dto import JobCard, JobFilters, JobMatchResult
from src.repository.careers_repository import CareersRepository
from src.service.careers_job_analysis_prompts import build_job_analysis_prompt

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional runtime dependency
    OpenAI = None  # type: ignore[assignment]


@dataclass(frozen=True)
class EnrichedJobCard:
    job: JobCard
    match: JobMatchResult

    def to_dict(self) -> dict[str, Any]:
        payload = self.job.to_dict()
        payload["match"] = {
            "job_id": self.match.job_id,
            "match_score": self.match.match_score,
            "ai_summary": self.match.ai_summary,
            "why_fit": self.match.why_fit,
            "why_fit_points": list(self.match.why_fit_points),
            "missing_skills": list(self.match.missing_skills),
            "recommendation": self.match.recommendation,
            "improvement_suggestions": list(self.match.improvement_suggestions),
            "computed_at": self.match.computed_at,
            "analysis_timestamp": self.match.analysis_timestamp,
            "analysis_source": self.match.analysis_source,
        }
        return payload


class CareersJobsService:
    """Job normalization, filtering, and placeholder AI-enrichment logic."""

    _SKILL_KEYWORDS = {
        "python",
        "java",
        "spring",
        "spring boot",
        "javascript",
        "typescript",
        "go",
        "c#",
        ".net",
        "sql",
        "postgresql",
        "mysql",
        "mongodb",
        "redis",
        "aws",
        "azure",
        "gcp",
        "docker",
        "kubernetes",
        "terraform",
        "microservices",
        "rest api",
        "graphql",
        "kafka",
        "ci/cd",
        "react",
        "angular",
        "node",
        "fastapi",
        "flask",
        "django",
        "spark",
        "airflow",
        "tableau",
        "power bi",
        "git",
        "machine learning",
        "genai",
        "llm",
        "data engineering",
    }
    _VALID_RECOMMENDATIONS = {"APPLY", "IMPROVE_FIRST", "SKIP"}
    _QUERY_FAMILY_FALLBACKS: dict[str, tuple[str, ...]] = {
        "java": ("java", "spring", "spring boot", "j2ee", "jvm"),
        "python": ("python", "django", "flask", "fastapi", "py"),
        "backend": ("backend", "api", "microservice", "server", "distributed"),
        "frontend": ("frontend", "react", "angular", "ui", "web"),
        "fullstack": ("full stack", "fullstack", "frontend", "backend"),
        "devops": ("devops", "sre", "kubernetes", "terraform", "cloud"),
        "data": ("data", "etl", "analytics", "pipeline", "sql"),
    }
    _GENERIC_QUERY_TOKENS = {
        "developer",
        "engineer",
        "software",
        "full",
        "stack",
        "senior",
        "lead",
        "principal",
        "staff",
        "associate",
        "specialist",
        "analyst",
        "manager",
        "intern",
        "remote",
        "onsite",
        "hybrid",
    }
    _LANGUAGE_QUERY_TOKENS = {
        "java",
        "python",
        "javascript",
        "typescript",
        "c#",
        "csharp",
        ".net",
        "dotnet",
        "go",
        "golang",
        "node",
        "ruby",
        "php",
        "scala",
        "kotlin",
    }
    _ROLE_MARKER_TOKENS = {
        "engineer",
        "developer",
        "analyst",
        "architect",
        "scientist",
        "designer",
        "manager",
        "administrator",
        "consultant",
    }
    _LOCATION_ALIAS_MAP: dict[str, tuple[str, ...]] = {
        "usa": ("usa", "us", "u.s.", "united states", "united states of america"),
        "us": ("usa", "us", "u.s.", "united states", "united states of america"),
        "united states": ("usa", "us", "u.s.", "united states", "united states of america"),
        "new york": ("new york", "nyc", "ny"),
        "new jersey": ("new jersey", "nj"),
        "california": ("california", "ca"),
        "texas": ("texas", "tx"),
        "washington": ("washington", "wa", "seattle"),
        "massachusetts": ("massachusetts", "ma", "boston"),
        "illinois": ("illinois", "il", "chicago"),
        "virginia": ("virginia", "va"),
        "north carolina": ("north carolina", "nc"),
        "florida": ("florida", "fl"),
    }

    def __init__(
        self,
        repository: CareersRepository | None = None,
        ai_key_getter: Callable[[], str | None] | None = None,
        ai_model: str = "gpt-4o-mini",
    ) -> None:
        self._repo = repository
        self._ai_key_getter = ai_key_getter
        self._ai_model = str(ai_model or "gpt-4o-mini").strip() or "gpt-4o-mini"
        self._cached_client: Any = None
        self._cached_key = ""

    def normalize_raw_job(self, raw_job: dict[str, Any]) -> JobCard:
        raw = dict(raw_job or {})
        title = self._clean_text(raw.get("title")) or "Untitled role"
        company = self._clean_text(raw.get("company")) or "Unknown company"
        location = self._normalize_location_for_storage(self._clean_text(raw.get("location")))
        source = self._clean_text(raw.get("source")) or "Unknown source"
        job_url = (
            self._clean_text(raw.get("job_url"))
            or self._clean_text(raw.get("apply_url"))
            or self._clean_text(raw.get("url"))
        )
        if job_url:
            source_hint = f"{self._clean_text(raw.get('source'))} {self._clean_text(raw.get('company'))}".lower()
            if "jpmorgan" in source_hint or "jpmc" in source_hint:
                job_url = re.sub(
                    r"/requisitions/([0-9]{6,12})(?:[/?#]|$)",
                    r"/job/\1",
                    job_url,
                    flags=re.IGNORECASE,
                )
        description = (
            self._clean_text(raw.get("description"))
            or self._clean_text(raw.get("summary"))
            or self._clean_text(raw.get("snippet"))
        )
        posted_at = (
            self._clean_text(raw.get("posted_at"))
            or self._clean_text(raw.get("published_at"))
            or self._clean_text(raw.get("created_at"))
            or self._clean_text(raw.get("date_posted"))
        )
        domain = self._clean_text(raw.get("domain"))
        work_type = self._clean_text(raw.get("work_type")) or self._clean_text(raw.get("employment_type"))
        level = self._clean_text(raw.get("level")) or self._clean_text(raw.get("seniority"))
        industry = self._clean_text(raw.get("industry"))
        if not industry:
            industry = self._infer_industry_label(
                title=title,
                company=company,
                source=source,
                description=description,
            )
        certifications = self._normalize_str_tuple(raw.get("certifications"))
        tags = self._normalize_str_tuple(raw.get("tags") or raw.get("position_tags"))

        job_id = self._clean_text(raw.get("job_id")) or self._clean_text(raw.get("id"))
        if not job_id:
            fingerprint = "|".join(
                [
                    title.lower(),
                    company.lower(),
                    location.lower(),
                    source.lower(),
                    job_url.lower(),
                ]
            )
            job_id = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:24]

        return JobCard(
            job_id=job_id,
            title=title,
            company=company,
            location=location,
            source=source,
            job_url=job_url,
            description=description,
            posted_at=posted_at,
            domain=domain,
            work_type=work_type,
            level=level,
            industry=industry,
            certifications=certifications,
            tags=tags,
            raw_payload=raw,
        )

    def normalize_jobs(self, raw_jobs: list[dict[str, Any]] | list[JobCard]) -> list[JobCard]:
        normalized: list[JobCard] = []
        seen: set[str] = set()
        for item in raw_jobs:
            if isinstance(item, JobCard):
                job = item
            elif isinstance(item, dict):
                job = self.normalize_raw_job(item)
            else:
                continue
            dedupe_key = f"{job.job_id}|{job.title.lower()}|{job.company.lower()}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            normalized.append(job)
        return normalized

    def filter_jobs(self, jobs: list[JobCard], filters: JobFilters) -> list[JobCard]:
        query = self._clean_text(filters.query).lower()
        query_tokens = self._build_query_tokens(query)
        role_match_mode = self._normalize_role_match_mode(getattr(filters, "role_match_mode", "balanced"))
        location = self._clean_text(filters.location).lower()
        source_tokens = {item.lower() for item in filters.sources if str(item or "").strip()}
        official_alias_enabled = any(token in {"official careers", "official"} for token in source_tokens)
        sources = {token for token in source_tokens if token not in {"official careers", "official"}}
        domains = {item.lower() for item in filters.domains}
        work_types = {item.lower() for item in filters.work_types}
        levels = {item.lower() for item in filters.levels}
        industries = {item.lower() for item in filters.industries}
        required_certs = {item.lower() for item in filters.certifications}
        posted_within_days = max(0, int(filters.posted_within_days or 0))

        filtered: list[JobCard] = []
        for job in jobs:
            if not self._is_valid_job_url(job.job_url):
                continue
            if query:
                haystack = self._compact_text(
                    f"{job.title} {job.company} {job.description} {' '.join(job.tags)}"
                ).lower()
                if not self._query_matches_job(
                    query=query,
                    query_tokens=query_tokens,
                    haystack=haystack,
                    role_match_mode=role_match_mode,
                    title_text=self._compact_text(job.title).lower(),
                ):
                    continue

            if location and not self._is_location_match(location, job.location):
                continue
            if sources or official_alias_enabled:
                source_value = job.source.lower()
                has_source_substring_match = any(token in source_value for token in sources)
                if source_value not in sources and not has_source_substring_match:
                    is_official_source = "careers" in source_value
                    if not (official_alias_enabled and is_official_source):
                        continue
            if domains and job.domain.lower() not in domains:
                continue
            if work_types and job.work_type.lower() not in work_types:
                continue
            if levels and job.level.lower() not in levels:
                continue
            if industries and job.industry.lower() not in industries:
                continue

            if required_certs:
                job_certs = {item.lower() for item in job.certifications}
                if not required_certs.intersection(job_certs):
                    continue

            if posted_within_days > 0 and not self._is_posted_within_days(job.posted_at, posted_within_days):
                continue

            filtered.append(job)

        if filters.offset > 0:
            filtered = filtered[filters.offset :]
        return filtered

    def compute_ai_match_score_placeholder(
        self,
        job: JobCard,
        user_profile: dict[str, Any],
        target_job_description: str = "",
    ) -> int:
        # TODO: Replace with embedding + LLM scoring pipeline when model service is wired.
        profile_skills = self._extract_profile_skills(user_profile)
        profile_text = self._extract_profile_text(user_profile)
        profile_tokens = self._tokenize(" ".join(profile_skills))
        profile_tokens.update(self._tokenize(profile_text))

        job_text = " ".join(
            [
                job.title,
                job.description,
                job.domain,
                job.work_type,
                job.level,
                job.industry,
                " ".join(job.certifications),
                " ".join(job.tags),
            ]
        )
        job_tokens = self._tokenize(job_text)
        if not job_tokens:
            return 0

        matched_skills = self._matched_profile_skills_for_job(job, user_profile)
        skill_bonus = min(48, len(matched_skills) * 8)

        token_overlap = len(profile_tokens.intersection(job_tokens))
        token_bonus = min(18, token_overlap * 2)

        title_overlap = len(self._tokenize(job.title).intersection(profile_tokens))
        title_bonus = min(12, title_overlap * 4)

        target_role = str(user_profile.get("target_role", "")).strip()
        target_role_tokens = self._tokenize(target_role)
        role_overlap = len(target_role_tokens.intersection(self._tokenize(job.title)))
        role_bonus = min(10, role_overlap * 3)

        target_bonus = 0
        if target_job_description.strip():
            target_tokens = self._tokenize(target_job_description)
            target_overlap = len(target_tokens.intersection(job_tokens))
            target_bonus = min(12, target_overlap * 2)

        recency_bonus = self._recency_bonus(job.posted_at)

        base_score = 20
        if not matched_skills and token_overlap <= 1:
            base_score -= 6

        score = base_score + skill_bonus + token_bonus + title_bonus + role_bonus + target_bonus + recency_bonus
        matched_count = len(matched_skills)
        if matched_count >= 1:
            score = max(score, 35)
        if matched_count >= 2:
            score = max(score, 45)
        if matched_count >= 3:
            score = max(score, 55)
        return max(0, min(100, score))

    def generate_why_fit_text_placeholder(
        self,
        job: JobCard,
        user_profile: dict[str, Any],
        target_job_description: str = "",
        match_score: int = 0,
    ) -> str:
        why_fit_points = self._build_why_fit_points_fallback(
            job=job,
            user_profile=user_profile,
            target_job_description=target_job_description,
        )
        return f"Match {int(match_score)}% - " + " ".join(why_fit_points[:3])

    def detect_missing_skills_placeholder(
        self,
        job: JobCard,
        user_profile: dict[str, Any],
        max_items: int = 5,
    ) -> list[str]:
        # TODO: Replace with AI-driven skills gap extraction tuned by role level.
        profile_skills = {self._normalize_skill_label(item) for item in self._extract_profile_skills(user_profile)}
        job_text = self._compact_text(
            " ".join([job.title, job.description, " ".join(job.tags), " ".join(job.certifications)])
        ).lower()

        missing: list[str] = []
        for keyword in self._ordered_job_skill_mentions(job_text):
            normalized = self._normalize_skill_label(keyword)
            if normalized in profile_skills:
                continue
            missing.append(self._display_skill_label(keyword))
            if len(missing) >= max(1, int(max_items or 5)):
                break
        return missing

    def build_job_match_result(
        self,
        job: JobCard,
        user_profile: dict[str, Any],
        target_job_description: str = "",
    ) -> JobMatchResult:
        now_iso = datetime.now(timezone.utc).isoformat()
        fallback_score = self.compute_ai_match_score_placeholder(job, user_profile, target_job_description)
        fallback_missing = tuple(self.detect_missing_skills_placeholder(job, user_profile, max_items=5))
        fallback_points = tuple(
            self._build_why_fit_points_fallback(
                job=job,
                user_profile=user_profile,
                target_job_description=target_job_description,
            )[:3]
        )
        fallback_summary = self._build_ai_summary_fallback(job, fallback_score, fallback_points)
        ai_result = self._analyze_job_with_ai(
            job=job,
            user_profile=user_profile,
            target_job_description=target_job_description,
        )

        if isinstance(ai_result, dict):
            score = max(0, min(100, int(ai_result.get("match_score", fallback_score) or fallback_score)))
            ai_summary = self._compact_text(str(ai_result.get("ai_summary", "") or "")) or fallback_summary
            why_fit_points = self._normalize_str_tuple(ai_result.get("why_fit"))[:3]
            if not why_fit_points:
                why_fit_points = fallback_points
            missing_skills = self._normalize_str_tuple(ai_result.get("missing_skills"))[:5]
            if not missing_skills:
                missing_skills = fallback_missing
            recommendation = self._normalize_recommendation(
                str(ai_result.get("recommendation", "") or ""),
                score=score,
                missing_skills=missing_skills,
            )
            analysis_source = "openai"
            analysis_timestamp = now_iso
        else:
            score = fallback_score
            ai_summary = fallback_summary
            why_fit_points = fallback_points
            missing_skills = fallback_missing
            recommendation = self._normalize_recommendation("", score=score, missing_skills=missing_skills)
            analysis_source = "deterministic_fallback"
            analysis_timestamp = now_iso

        why_fit = " ".join(f"- {point}" for point in why_fit_points if point)
        improvement_suggestions = self._build_improvement_suggestions(job, missing_skills)
        return JobMatchResult(
            job_id=job.job_id,
            match_score=score,
            ai_summary=ai_summary,
            why_fit=why_fit,
            why_fit_points=why_fit_points,
            missing_skills=missing_skills,
            recommendation=recommendation,
            improvement_suggestions=improvement_suggestions,
            computed_at=now_iso,
            analysis_timestamp=analysis_timestamp,
            analysis_source=analysis_source,
        )

    def get_enriched_job_cards(
        self,
        raw_jobs: list[dict[str, Any]] | list[JobCard],
        filters: JobFilters,
        user_profile: dict[str, Any],
        target_job_description: str = "",
        cache_key: str = "",
        use_cache: bool = True,
        cache_ttl_seconds: int = 300,
    ) -> list[EnrichedJobCard]:
        normalized_jobs: list[JobCard] = []
        fresh_jobs = self.normalize_jobs(raw_jobs)
        cleaned_cache_key = self._clean_text(cache_key).lower()
        cache_refresh_needed = False

        if use_cache and cleaned_cache_key and self._repo is not None:
            cached = self._repo.get_cached_jobs(cleaned_cache_key, limit=max(50, filters.limit * 2))
            if cached:
                normalized_jobs = cached
                if fresh_jobs:
                    merged_jobs = self.normalize_jobs([*cached, *fresh_jobs])
                    if len(merged_jobs) > len(cached):
                        normalized_jobs = merged_jobs
                        cache_refresh_needed = True

        if not normalized_jobs:
            normalized_jobs = fresh_jobs
            cache_refresh_needed = bool(normalized_jobs)

        if cleaned_cache_key and self._repo is not None and normalized_jobs and (cache_refresh_needed or not use_cache):
            for job in normalized_jobs:
                self._repo.upsert_cached_job(cleaned_cache_key, job, ttl_seconds=cache_ttl_seconds)
        elif cleaned_cache_key and self._repo is not None and normalized_jobs and use_cache:
            existing_cached = self._repo.get_cached_jobs(cleaned_cache_key, limit=1)
            if not existing_cached:
                for job in normalized_jobs:
                    self._repo.upsert_cached_job(cleaned_cache_key, job, ttl_seconds=cache_ttl_seconds)

        filtered_jobs = self.filter_jobs(normalized_jobs, filters)
        enriched: list[EnrichedJobCard] = []
        recommendation_filters = {item.strip().upper() for item in filters.recommendations if str(item or "").strip()}
        for job in filtered_jobs:
            result = self.build_job_match_result(job, user_profile, target_job_description)
            if result.match_score < max(0, min(100, int(filters.min_match_score or 0))):
                continue
            if recommendation_filters and result.recommendation.upper() not in recommendation_filters:
                continue
            enriched.append(EnrichedJobCard(job=job, match=result))
        enriched.sort(key=lambda item: item.match.match_score, reverse=True)
        if filters.limit > 0:
            enriched = enriched[: int(filters.limit)]
        return enriched

    @staticmethod
    def _extract_profile_text(user_profile: dict[str, Any]) -> str:
        parts: list[str] = []
        for key in ("summary", "experience", "education", "projects", "resume_text", "target_role"):
            value = user_profile.get(key)
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, (list, tuple)):
                parts.extend(str(item) for item in value)
        return " ".join(part for part in parts if str(part).strip())

    @staticmethod
    def _extract_profile_skills(user_profile: dict[str, Any]) -> list[str]:
        raw = user_profile.get("skills", [])
        if isinstance(raw, str):
            candidates = [token.strip() for token in re.split(r"[,/;\n]", raw)]
        elif isinstance(raw, (list, tuple, set)):
            candidates = [str(item).strip() for item in raw]
        else:
            candidates = []

        deduped: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            if not candidate:
                continue
            lowered = candidate.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            deduped.append(candidate)
        return deduped

    @staticmethod
    def _tokenize(value: str) -> set[str]:
        tokens = re.findall(r"[a-zA-Z0-9\+\#\.\-]{2,}", str(value or "").lower())
        return {token for token in tokens if len(token) >= 2}

    @staticmethod
    def _normalize_skill_label(value: str) -> str:
        cleaned = re.sub(r"\s+", " ", str(value or "").strip().lower())
        if cleaned in {"ci cd", "cicd"}:
            return "ci/cd"
        if cleaned in {"spring boot", "springboot", "spring-boot"}:
            return "spring"
        return cleaned

    @staticmethod
    def _display_skill_label(value: str) -> str:
        cleaned = str(value or "").strip()
        if not cleaned:
            return ""
        lowered = cleaned.lower()
        display_map = {
            "aws": "AWS",
            "gcp": "GCP",
            "ci/cd": "CI/CD",
            "llm": "LLM",
            "sql": "SQL",
            "fastapi": "FastAPI",
            "postgresql": "PostgreSQL",
            "c#": "C#",
            ".net": ".NET",
            "graphql": "GraphQL",
            "rest api": "REST API",
        }
        if lowered in display_map:
            return display_map[lowered]
        return cleaned.title()

    @staticmethod
    def _infer_industry_label(title: str, company: str, source: str, description: str) -> str:
        text = " ".join(
            [
                str(title or "").lower(),
                str(company or "").lower(),
                str(source or "").lower(),
                str(description or "").lower(),
            ]
        )
        if not text.strip():
            return ""

        industry_rules: list[tuple[str, tuple[str, ...]]] = [
            (
                "Finance",
                (
                    "bank",
                    "jpmorgan",
                    "goldman",
                    "morgan stanley",
                    "capital one",
                    "citi",
                    "wells fargo",
                    "american express",
                    "fintech",
                    "asset management",
                ),
            ),
            (
                "Healthcare",
                (
                    "healthcare",
                    "hospital",
                    "medical",
                    "biotech",
                    "pharma",
                    "weill cornell",
                    "bayer",
                    "boston scientific",
                    "clinical",
                ),
            ),
            (
                "Retail",
                (
                    "retail",
                    "ecommerce",
                    "consumer goods",
                    "merchandising",
                ),
            ),
            (
                "Education",
                (
                    "education",
                    "university",
                    "college",
                    "school",
                    "edtech",
                ),
            ),
            (
                "Manufacturing",
                (
                    "manufacturing",
                    "industrial",
                    "boeing",
                    "aerospace",
                    "l3harris",
                    "factory",
                    "supply chain",
                ),
            ),
            (
                "Consulting",
                (
                    "consulting",
                    "advisory",
                    "deloitte",
                    "pwc",
                    "ey",
                    "kpmg",
                ),
            ),
            (
                "Technology",
                (
                    "software",
                    "cloud",
                    "developer",
                    "engineer",
                    "tech",
                    "sap",
                    "dell",
                    "comcast",
                    "at&t",
                    "devops",
                    "api",
                ),
            ),
        ]
        for industry_name, tokens in industry_rules:
            if any(token in text for token in tokens):
                return industry_name
        return ""

    @classmethod
    def _ordered_job_skill_mentions(cls, job_text: str) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        lowered_text = str(job_text or "").lower()
        for keyword in cls._SKILL_KEYWORDS:
            if keyword not in lowered_text:
                continue
            norm = cls._normalize_skill_label(keyword)
            if norm in seen:
                continue
            seen.add(norm)
            ordered.append(keyword)
        ordered.sort(key=lambda item: lowered_text.find(item))
        return ordered

    def _matched_profile_skills_for_job(self, job: JobCard, user_profile: dict[str, Any]) -> list[str]:
        profile_skills = self._extract_profile_skills(user_profile)
        if not profile_skills:
            return []
        job_text = self._compact_text(
            " ".join([job.title, job.description, " ".join(job.tags), " ".join(job.certifications)])
        ).lower()
        matched: list[str] = []
        seen: set[str] = set()
        for skill in profile_skills:
            normalized = self._normalize_skill_label(skill)
            if not normalized:
                continue
            if normalized in seen:
                continue
            if normalized not in job_text:
                continue
            seen.add(normalized)
            matched.append(self._display_skill_label(skill))
        return matched

    @staticmethod
    def _build_improvement_suggestions(job: JobCard, missing_skills: tuple[str, ...]) -> tuple[str, ...]:
        suggestions: list[str] = []
        for skill in list(missing_skills)[:2]:
            clean_skill = str(skill).strip()
            if not clean_skill:
                continue
            suggestions.append(f"Add one measurable project bullet proving {clean_skill} in production.")
        if job.title:
            suggestions.append(f"Tailor your summary to the role focus: {job.title}.")
        if job.domain:
            suggestions.append(f"Highlight domain outcomes relevant to {job.domain}.")
        deduped: list[str] = []
        seen: set[str] = set()
        for item in suggestions:
            lowered = item.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            deduped.append(item)
            if len(deduped) >= 3:
                break
        return tuple(deduped)

    def _build_why_fit_points_fallback(
        self,
        *,
        job: JobCard,
        user_profile: dict[str, Any],
        target_job_description: str = "",
    ) -> tuple[str, ...]:
        points: list[str] = []
        matched_skills = self._matched_profile_skills_for_job(job, user_profile)
        if matched_skills:
            points.append(f"Your profile matches key skills: {', '.join(matched_skills[:3])}.")

        target_role = self._compact_text(str(user_profile.get("target_role", "") or ""))
        if target_role and target_role.lower() in self._compact_text(job.title).lower():
            points.append(f"The role title aligns with your target role focus: {target_role}.")

        target_text = self._compact_text(str(target_job_description or ""))
        if target_text:
            target_overlap = len(self._tokenize(target_text).intersection(self._tokenize(job.title + " " + job.description)))
            if target_overlap > 0:
                points.append("There is clear overlap with your target job description requirements.")

        if job.work_type:
            points.append(f"Work type fit: {job.work_type}.")
        if job.level:
            points.append(f"Seniority alignment observed at {job.level} level.")
        if not points:
            points.append("Role shows baseline alignment with your profile context.")

        deduped: list[str] = []
        seen: set[str] = set()
        for point in points:
            clean = self._compact_text(point)
            if not clean:
                continue
            key = clean.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(clean)
            if len(deduped) >= 3:
                break
        while len(deduped) < 3:
            deduped.append("This role can be targeted with focused resume tailoring.")
        return tuple(deduped[:3])

    @staticmethod
    def _build_ai_summary_fallback(job: JobCard, score: int, why_fit_points: tuple[str, ...]) -> str:
        first_point = str(why_fit_points[0] if why_fit_points else "").strip()
        if first_point:
            return f"{job.title} at {job.company} is a {int(score)}% fit. {first_point}"
        return f"{job.title} at {job.company} is a {int(score)}% fit based on role, skills, and context overlap."

    def _normalize_recommendation(self, raw_value: str, *, score: int, missing_skills: tuple[str, ...]) -> str:
        cleaned = str(raw_value or "").strip().upper()
        if cleaned in self._VALID_RECOMMENDATIONS:
            return cleaned
        if int(score) >= 74 and len(missing_skills) <= 3:
            return "APPLY"
        if int(score) >= 46:
            return "IMPROVE_FIRST"
        return "SKIP"

    def _analyze_job_with_ai(
        self,
        *,
        job: JobCard,
        user_profile: dict[str, Any],
        target_job_description: str = "",
    ) -> dict[str, Any] | None:
        client = self._get_ai_client()
        if client is None:
            return None
        prompt = build_job_analysis_prompt(
            user_profile=user_profile,
            job_payload=job.to_dict(),
            target_job_description=target_job_description,
        )
        try:
            response = client.chat.completions.create(
                model=self._ai_model,
                temperature=0.15,
                max_tokens=700,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a strict careers ranking model. "
                            "Return valid JSON only and follow schema exactly."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            raw = str(response.choices[0].message.content or "").strip()
        except Exception:
            return None

        parsed = self._safe_json_load(raw)
        if not isinstance(parsed, dict):
            return None
        if "match_score" not in parsed:
            return None
        return parsed

    def _get_ai_client(self) -> Any:
        if OpenAI is None:
            return None
        if self._ai_key_getter is None:
            return None
        key = str(self._ai_key_getter() or "").strip()
        if not key:
            return None
        if self._cached_client is not None and self._cached_key == key:
            return self._cached_client
        try:
            self._cached_client = OpenAI(api_key=key)
            self._cached_key = key
            return self._cached_client
        except Exception:
            return None

    @staticmethod
    def _safe_json_load(raw_text: str) -> Any:
        cleaned = str(raw_text or "").strip()
        if not cleaned:
            return {}
        try:
            return json.loads(cleaned)
        except Exception:
            pass
        start_idx = cleaned.find("{")
        end_idx = cleaned.rfind("}")
        if start_idx >= 0 and end_idx > start_idx:
            try:
                return json.loads(cleaned[start_idx : end_idx + 1])
            except Exception:
                return {}
        return {}

    @staticmethod
    def _recency_bonus(posted_at: str) -> int:
        parsed = CareersJobsService._parse_posted_at(posted_at)
        if parsed is None:
            return 0
        now = datetime.now(timezone.utc)
        delta_days = max(0, int((now - parsed).total_seconds() / 86400))
        if delta_days <= 3:
            return 6
        if delta_days <= 7:
            return 4
        if delta_days <= 14:
            return 2
        return 0

    @staticmethod
    def _parse_posted_at(posted_at: str) -> datetime | None:
        cleaned = str(posted_at or "").strip()
        if not cleaned:
            return None
        lowered = cleaned.lower()
        now_utc = datetime.now(timezone.utc)
        if lowered in {"now", "just now", "today", "posted today"}:
            return now_utc
        if "yesterday" in lowered:
            return now_utc - timedelta(days=1)
        relative_match = re.search(
            r"(?i)(\d+)\s*\+?\s*(minute|min|hour|hr|day|week|month|year)s?\s+ago",
            lowered,
        )
        if relative_match:
            amount = max(0, int(relative_match.group(1) or 0))
            unit = str(relative_match.group(2) or "").lower()
            if unit in {"minute", "min"}:
                return now_utc - timedelta(minutes=amount)
            if unit in {"hour", "hr"}:
                return now_utc - timedelta(hours=amount)
            if unit == "day":
                return now_utc - timedelta(days=amount)
            if unit == "week":
                return now_utc - timedelta(weeks=amount)
            if unit == "month":
                return now_utc - timedelta(days=amount * 30)
            if unit == "year":
                return now_utc - timedelta(days=amount * 365)
        parsed: datetime | None = None
        try:
            parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        except Exception:
            parsed = None
        if parsed is None:
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
                try:
                    parsed = datetime.strptime(cleaned, fmt).replace(tzinfo=timezone.utc)
                    break
                except Exception:
                    continue
        if parsed is None:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    @staticmethod
    def _build_query_tokens(query: str) -> list[str]:
        cleaned = re.sub(r"\s+", " ", str(query or "").strip().lower())
        if not cleaned:
            return []
        raw_tokens = re.findall(r"[a-z0-9][a-z0-9+.#/_-]*", cleaned)
        stop_tokens = {
            "a",
            "an",
            "and",
            "or",
            "the",
            "for",
            "to",
            "with",
            "of",
            "in",
            "on",
            "at",
            "by",
            "job",
            "jobs",
            "role",
            "roles",
            "position",
            "positions",
        }
        deduped: list[str] = []
        seen: set[str] = set()
        for token in raw_tokens:
            compact = token.strip().lower()
            if not compact or compact in stop_tokens or len(compact) <= 1:
                continue
            if compact in seen:
                continue
            seen.add(compact)
            deduped.append(compact)
        return deduped

    def _query_matches_job(
        self,
        *,
        query: str,
        query_tokens: list[str],
        haystack: str,
        role_match_mode: str,
        title_text: str,
    ) -> bool:
        clean_haystack = str(haystack or "").lower()
        clean_title = str(title_text or "").lower()
        if not clean_haystack:
            return False
        if not query_tokens:
            return query in clean_haystack if query else True
        if query and query in clean_haystack:
            return True

        must_tokens = [token for token in query_tokens if token not in self._GENERIC_QUERY_TOKENS]
        if not must_tokens:
            must_tokens = list(query_tokens[:1])

        token_hits = sum(1 for token in query_tokens if self._token_matches_haystack(token, clean_haystack))
        must_hits = sum(1 for token in must_tokens if self._token_matches_haystack(token, clean_haystack))

        if role_match_mode == "strict":
            if must_hits < len(must_tokens):
                return False
            min_total_hits = len(query_tokens) if len(query_tokens) <= 2 else max(2, len(query_tokens) - 1)
            if token_hits < min_total_hits:
                return False
            role_tokens = [token for token in query_tokens if token in self._ROLE_MARKER_TOKENS]
            if role_tokens and not any(token in clean_title for token in role_tokens):
                return False
            return True

        if role_match_mode == "broad":
            if must_hits > 0:
                return True
            if self._is_language_intent(query_tokens):
                broad_role_markers = (
                    "software engineer",
                    "software developer",
                    "backend engineer",
                    "backend developer",
                    "full stack",
                    "api",
                    "microservice",
                )
                if any(marker in clean_haystack for marker in broad_role_markers):
                    return True
            return self._is_query_adjacent_match(query_tokens=query_tokens, haystack=clean_haystack)

        # balanced mode (default)
        if must_hits == 0:
            return False
        if len(must_tokens) >= 2 and must_hits < len(must_tokens) - 1:
            return False
        required_total_hits = 1 if len(query_tokens) <= 2 else 2
        if token_hits >= required_total_hits:
            role_tokens = [token for token in query_tokens if token in self._ROLE_MARKER_TOKENS]
            if role_tokens and not any(token in clean_title for token in role_tokens):
                if self._is_language_intent(query_tokens):
                    adjacent_role_markers = (
                        "software engineer",
                        "software developer",
                        "engineer",
                        "developer",
                        "architect",
                        "programmer",
                        "backend",
                        "full stack",
                    )
                    if not (
                        any(marker in clean_title for marker in adjacent_role_markers)
                        or any(marker in clean_haystack for marker in adjacent_role_markers)
                    ):
                        return False
                else:
                    return False
            return True
        return self._is_query_adjacent_match(query_tokens=query_tokens, haystack=clean_haystack)

    @staticmethod
    def _normalize_role_match_mode(raw_value: str) -> str:
        cleaned = str(raw_value or "").strip().lower()
        if cleaned in {"strict", "balanced", "broad"}:
            return cleaned
        return "balanced"

    @staticmethod
    def _token_matches_haystack(token: str, haystack: str) -> bool:
        clean_token = str(token or "").strip().lower()
        if not clean_token:
            return False
        if clean_token == "java":
            return re.search(r"\bjava\b", haystack) is not None
        if clean_token in {"javascript", "js"}:
            return re.search(r"\b(javascript|js)\b", haystack) is not None
        if clean_token in {"typescript", "ts"}:
            return re.search(r"\b(typescript|ts)\b", haystack) is not None
        if clean_token in {"c#", "csharp"}:
            return re.search(r"\b(c#|csharp)\b", haystack) is not None
        if clean_token in {".net", "dotnet"}:
            return re.search(r"\b(\.net|dotnet)\b", haystack) is not None
        if clean_token in {"go", "golang"}:
            return re.search(r"\b(golang|go language)\b", haystack) is not None
        if clean_token == "node":
            return re.search(r"\b(node|nodejs|node\.js)\b", haystack) is not None
        if clean_token == "backend":
            return re.search(r"\b(back[- ]?end|server[- ]?side|microservice|api)\b", haystack) is not None
        return clean_token in haystack

    @classmethod
    def _is_language_intent(cls, query_tokens: list[str]) -> bool:
        return any(str(token or "").strip().lower() in cls._LANGUAGE_QUERY_TOKENS for token in query_tokens)

    @classmethod
    def _is_query_adjacent_match(cls, query_tokens: list[str], haystack: str) -> bool:
        clean_haystack = str(haystack or "").lower()
        if not clean_haystack:
            return False
        role_marker_tokens = ("engineer", "developer", "architect", "programmer", "software", "backend", "full stack")
        generic_role_aliases: dict[str, tuple[str, ...]] = {
            "software": ("software engineer", "software developer", "engineer", "developer", "sde", "programmer"),
            "engineer": ("engineer", "developer", "sde", "programmer", "architect"),
            "developer": ("developer", "engineer", "sde", "programmer"),
            "analyst": ("analyst", "business analyst", "data analyst", "systems analyst"),
            "manager": ("manager", "product manager", "program manager", "engineering manager", "lead"),
            "scientist": ("scientist", "researcher", "machine learning engineer", "ml engineer", "ai engineer"),
            "architect": ("architect", "solutions architect", "principal engineer"),
            "intern": ("intern", "internship", "co-op"),
        }
        for token in query_tokens:
            compact = str(token or "").strip().lower()
            if not compact:
                continue
            generic_family = generic_role_aliases.get(compact)
            if generic_family and any(alias in clean_haystack for alias in generic_family):
                return True
            family = cls._QUERY_FAMILY_FALLBACKS.get(compact)
            if family and any(alias in clean_haystack for alias in family):
                return True
            if compact in {"python", "node", "react", "backend", "frontend", "devops", "data"} and any(
                marker in clean_haystack for marker in role_marker_tokens
            ):
                return True
        return False

    @classmethod
    def _is_location_match(cls, preferred_location: str, job_location: str) -> bool:
        wanted = " ".join(str(preferred_location or "").strip().lower().split())
        if not wanted:
            return True
        location_text = " ".join(str(job_location or "").strip().lower().split())
        unknown_location_markers = {
            "",
            "location not listed",
            "location unavailable",
            "unknown",
            "n/a",
            "not specified",
        }
        if location_text in unknown_location_markers:
            location_text = ""
        if not location_text:
            return wanted in {
                "usa",
                "us",
                "u.s.",
                "united states",
                "united states of america",
                "remote",
                "worldwide",
                "global",
                "any",
            }
        if "remote" in wanted and "remote" in location_text:
            return True
        if wanted in location_text:
            return True
        aliases = list(cls._LOCATION_ALIAS_MAP.get(wanted, ()))
        if aliases and any(alias in location_text for alias in aliases):
            return True
        wanted_tokens = [token for token in re.split(r"[,\s/|;-]+", wanted) if token]
        if not wanted_tokens:
            return True
        token_hits = sum(1 for token in wanted_tokens if token in location_text)
        return token_hits >= min(2, len(wanted_tokens))

    @staticmethod
    def _is_valid_job_url(job_url: str) -> bool:
        cleaned = str(job_url or "").strip()
        if not cleaned:
            return False
        try:
            parsed = urlsplit(cleaned)
        except Exception:
            return False
        if str(parsed.scheme or "").lower() not in {"http", "https"}:
            return False
        path = str(parsed.path or "").strip().lower()
        query = str(parsed.query or "").strip().lower()
        if not path:
            return False
        if path.rstrip("/").endswith("/404") or "/404/" in path:
            return False
        generic_landing_markers = (
            "/search",
            "/search-jobs",
            "/job-search",
            "/search-results",
            "/jobs/search",
            "/careers/search",
            "/careers/results",
            "/jobs/results",
        )
        if any(marker in path for marker in generic_landing_markers):
            return False
        strong_path_tokens = (
            "/job/",
            "/jobs/",
            "/job-detail/",
            "/jobdetail",
            "/requisition",
            "/requisitions/",
            "/vacancy/",
            "/opening/",
            "/opportunity/",
            "/positions/",
            "/viewjob",
            "/remote-jobs/",
        )
        if any(token in path for token in strong_path_tokens):
            return True
        strong_query_tokens = (
            "jobid=",
            "job_id=",
            "gh_jid=",
            "requisitionid=",
            "requisition_id=",
            "reqid=",
            "postingid=",
            "vacancyid=",
        )
        if any(token in query for token in strong_query_tokens):
            return True
        return False

    @staticmethod
    def _is_posted_within_days(posted_at: str, days: int) -> bool:
        parsed = CareersJobsService._parse_posted_at(posted_at)
        if parsed is None:
            return False
        threshold = datetime.now(timezone.utc) - timedelta(days=max(0, int(days or 0)))
        return parsed >= threshold

    @staticmethod
    def _normalize_str_tuple(items: Any) -> tuple[str, ...]:
        if isinstance(items, str):
            values = [token.strip() for token in re.split(r"[,;|]", items)]
        elif isinstance(items, (list, tuple, set)):
            values = [str(item).strip() for item in items]
        else:
            values = []

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
    def _clean_text(value: Any) -> str:
        return str(value or "").strip()

    @staticmethod
    def _normalize_location_for_storage(location: str) -> str:
        cleaned = " ".join(str(location or "").split()).strip()
        if not cleaned:
            return "Location not listed"
        lowered = cleaned.lower()
        if (
            "united states" in lowered
            or "united states of america" in lowered
            or "u.s." in lowered
            or re.search(r"\busa\b", lowered)
            or re.search(r"\bus\b", lowered)
        ):
            return "United States of America"
        return cleaned

    @staticmethod
    def _compact_text(value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip())
