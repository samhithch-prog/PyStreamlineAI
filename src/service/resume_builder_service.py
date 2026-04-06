from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html import unescape
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from src.dto.resume_builder_dto import (
    GeneratedResume,
    ResumeExperience,
    ResumeProfile,
)
from src.repository.resume_builder_repository import ResumeBuilderRepository
from src.service.resume_prompts import (
    build_generate_full_resume_prompt,
    build_improve_professional_summary_prompt,
    build_resume_scan_rag_prompt,
    build_rewrite_experience_bullets_prompt,
    build_tailor_resume_to_selected_job_prompt,
)

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional runtime dependency
    OpenAI = None  # type: ignore[assignment]


class ResumeBuilderService:
    """Resume-builder orchestration with safe fallback behavior."""

    def __init__(
        self,
        repository: ResumeBuilderRepository,
        ai_key_getter: Callable[[], str | None] | None = None,
        model_name: str = "gpt-4o-mini",
    ) -> None:
        self._repo = repository
        self._ai_key_getter = ai_key_getter
        self._model_name = str(model_name or "gpt-4o-mini").strip() or "gpt-4o-mini"
        self._cached_client: Any = None
        self._cached_key = ""

    def normalize_profile(self, profile: ResumeProfile | dict[str, Any], user_id: int) -> ResumeProfile:
        base = profile if isinstance(profile, ResumeProfile) else ResumeProfile.from_dict(profile if isinstance(profile, dict) else {})
        return ResumeProfile.from_dict({**base.to_dict(), "user_id": int(user_id or 0)})

    def save_profile_draft(self, user_id: int, profile: ResumeProfile | dict[str, Any]) -> ResumeProfile | None:
        normalized = self.normalize_profile(profile, user_id)
        return self._repo.save_resume_profile_draft(user_id=user_id, profile=normalized)

    def get_profile_draft(self, user_id: int) -> ResumeProfile | None:
        return self._repo.get_resume_profile_draft(user_id=user_id)

    def save_generated_resume(
        self,
        user_id: int,
        generated_resume: GeneratedResume | dict[str, Any],
    ) -> GeneratedResume | None:
        return self._repo.save_generated_resume(user_id=user_id, generated_resume=generated_resume)

    def list_generated_resumes(self, user_id: int, limit: int = 20, offset: int = 0) -> list[GeneratedResume]:
        return self._repo.list_generated_resumes(user_id=user_id, limit=limit, offset=offset)

    def get_latest_generated_resume(self, user_id: int) -> GeneratedResume | None:
        return self._repo.get_latest_generated_resume(user_id=user_id)

    def analyze_resume_scan_with_rag(
        self,
        resume_text: str,
        profile: ResumeProfile,
        target_job_description: str = "",
    ) -> dict[str, Any]:
        clean_resume = self._normalize_multiline_text(str(resume_text or ""))
        if not clean_resume:
            return {
                "extracted_title": "",
                "summary_points": [],
                "recommended_skills": [],
                "missing_skills": [],
                "focus_improvements": [],
                "retrieved_chunks": [],
            }

        target_context = self._build_target_context(profile, target_job_description=target_job_description)
        retrieved_chunks = self._retrieve_relevant_resume_chunks(
            resume_text=clean_resume,
            target_context=target_context,
            top_k=6,
        )

        prompt = build_resume_scan_rag_prompt(
            resume_text=clean_resume,
            retrieved_chunks=retrieved_chunks,
            target_context=target_context,
            profile=profile,
        )
        ai_text = self._try_ai_text(prompt, max_tokens=1200, preserve_newlines=True)
        parsed = self._safe_json_load(ai_text) if ai_text else {}

        extracted_title = ""
        summary_points: list[str] = []
        recommended_skills: list[str] = []
        missing_skills: list[str] = []
        focus_improvements: list[str] = []

        if isinstance(parsed, dict):
            extracted_title = self._compact_text(str(parsed.get("extracted_title", "") or ""))
            summary_points = self._normalize_str_list(parsed.get("summary_points", []), limit=6)
            recommended_skills = self._normalize_str_list(parsed.get("recommended_skills", []), limit=20)
            missing_skills = self._normalize_str_list(parsed.get("missing_skills", []), limit=12)
            focus_improvements = self._normalize_str_list(parsed.get("focus_improvements", []), limit=12)

        if not summary_points:
            summary_points = self._build_summary_points(
                summary=clean_resume,
                profile=profile,
                skills=list(profile.skills),
                role_text=profile.target_role,
            )

        inferred_skills = self._extract_candidate_skills_from_text(clean_resume, limit=24)
        merged_skills = self._merge_unique_texts(
            [*recommended_skills, *inferred_skills, *list(profile.skills)],
            limit=24,
        )
        if not recommended_skills:
            recommended_skills = merged_skills[:18]

        if not missing_skills:
            missing_skills = self._extract_priority_terms(target_context, limit=8)
            lowered_rec = {item.lower() for item in recommended_skills}
            missing_skills = [item for item in missing_skills if item.lower() not in lowered_rec][:8]

        if not focus_improvements:
            focus_improvements = [
                "Align the top 2 experience bullets directly to target responsibilities.",
                "Quantify impact metrics in recent role bullets.",
                "Prioritize target-role keywords in summary and skills section.",
            ]

        if not extracted_title:
            extracted_title = self._infer_title_from_resume_text(clean_resume) or self._compact_text(profile.target_role)

        return {
            "extracted_title": extracted_title,
            "summary_points": summary_points[:6],
            "recommended_skills": recommended_skills[:18],
            "missing_skills": missing_skills[:8],
            "focus_improvements": focus_improvements[:8],
            "retrieved_chunks": retrieved_chunks,
        }

    def generate_professional_summary(
        self,
        profile: ResumeProfile,
        current_summary: str = "",
        target_job_description: str = "",
    ) -> str:
        prompt = build_improve_professional_summary_prompt(profile, current_summary, target_job_description)
        ai_text = self._try_ai_text(prompt, max_tokens=280)
        if ai_text:
            return self._compact_text(ai_text)

        # TODO: Replace fallback with LLM-based summarization when AI provider is configured.
        role_hint = str(profile.target_role or "professional").strip()
        top_skills = ", ".join(profile.skills[:6]) if profile.skills else "core technical and delivery skills"
        exp_years = max(0, len(profile.experiences))
        summary_lines = [
            f"{profile.full_name or 'Candidate'} is a {role_hint} with {exp_years}+ relevant experience blocks.",
            f"Core strengths include {top_skills}.",
            "Delivers measurable outcomes through collaboration, ownership, and execution focus.",
        ]
        if target_job_description.strip():
            summary_lines.append("Profile aligned to target job requirements and key responsibilities.")
        return " ".join(self._compact_text(line) for line in summary_lines if line.strip())

    def rewrite_experience_bullets(
        self,
        experience: ResumeExperience,
        target_role: str = "",
        target_job_description: str = "",
    ) -> tuple[str, ...]:
        prompt = build_rewrite_experience_bullets_prompt(experience, target_role, target_job_description)
        ai_text = self._try_ai_text(prompt, max_tokens=420)
        parsed = self._extract_bullets_from_ai(ai_text) if ai_text else []
        if parsed:
            return tuple(parsed[:6])

        # TODO: Replace fallback with model-assisted rewriting.
        seed_lines: list[str] = []
        if experience.bullets:
            seed_lines.extend([self._compact_text(item) for item in experience.bullets if self._compact_text(item)])
        if experience.description:
            seed_lines.extend(self._sentence_split(experience.description))
        if not seed_lines:
            seed_lines = [
                f"Delivered impact in {experience.role or 'role'} at {experience.company or 'company'}.",
                "Improved delivery quality and execution consistency across responsibilities.",
            ]

        rewritten: list[str] = []
        for idx, line in enumerate(seed_lines):
            if idx >= 6:
                break
            rewritten.append(self._rewrite_line_placeholder(line, experience))
        return tuple(rewritten)

    def format_resume_sections(
        self,
        profile: ResumeProfile,
        professional_summary: str = "",
        rewritten_experience_bullets: dict[int, tuple[str, ...]] | None = None,
    ) -> dict[str, Any]:
        bullets_map = rewritten_experience_bullets or {}
        summary_text = self._compact_text(professional_summary or profile.summary)

        experience_sections: list[dict[str, Any]] = []
        for idx, exp in enumerate(profile.experiences):
            bullets = bullets_map.get(idx, exp.bullets)
            experience_sections.append(
                {
                    "company": exp.company,
                    "role": exp.role,
                    "location": exp.location,
                    "start_date": exp.start_date,
                    "end_date": "Present" if exp.is_current else exp.end_date,
                    "bullets": [self._compact_text(item) for item in bullets if self._compact_text(item)],
                }
            )

        education_sections = [
            {
                "institution": edu.institution,
                "degree": edu.degree,
                "field_of_study": edu.field_of_study,
                "location": edu.location,
                "start_date": edu.start_date,
                "end_date": edu.end_date,
                "grade": edu.grade,
                "details": edu.details,
            }
            for edu in profile.educations
        ]

        project_sections = [
            {
                "name": proj.name,
                "role": proj.role,
                "summary": proj.summary,
                "technologies": list(proj.technologies),
                "link": proj.link,
                "bullets": list(proj.bullets),
            }
            for proj in profile.projects
        ]

        certification_sections = [
            {
                "name": cert.name,
                "issuer": cert.issuer,
                "issue_date": cert.issue_date,
                "expiry_date": cert.expiry_date,
                "credential_id": cert.credential_id,
                "credential_url": cert.credential_url,
            }
            for cert in profile.certifications
        ]

        return {
            "header": {
                "full_name": profile.full_name,
                "email": profile.email,
                "phone": profile.phone,
                "location": profile.location,
                "linkedin_url": profile.linkedin_url,
                "portfolio_url": profile.portfolio_url,
                "target_role": profile.target_role,
                "target_job_link": profile.target_job_link,
            },
            "professional_summary": summary_text,
            "skills": list(profile.skills),
            "experience": experience_sections,
            "education": education_sections,
            "projects": project_sections,
            "certifications": certification_sections,
        }

    def generate_resume(
        self,
        user_id: int,
        profile: ResumeProfile | dict[str, Any],
        target_job_description: str = "",
        source_job_id: str = "",
        target_job_title: str = "",
    ) -> GeneratedResume | None:
        safe_user_id = int(user_id or 0)
        if safe_user_id <= 0:
            return None

        normalized_profile = self.normalize_profile(profile, safe_user_id)
        self.save_profile_draft(safe_user_id, normalized_profile)
        effective_target_context = self._build_target_context(
            profile=normalized_profile,
            target_job_description=target_job_description,
        )

        ai_resume = self._try_ai_generate_full_resume(normalized_profile, effective_target_context)
        if ai_resume is not None:
            generated = GeneratedResume.from_dict(
                {
                    **ai_resume.to_dict(),
                    "user_id": safe_user_id,
                    "source_job_id": self._compact_text(source_job_id),
                    "target_job_title": self._compact_text(target_job_title),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        else:
            summary = self.generate_professional_summary(
                normalized_profile,
                current_summary=normalized_profile.summary,
                target_job_description=effective_target_context,
            )
            rewritten_map: dict[int, tuple[str, ...]] = {}
            for idx, exp in enumerate(normalized_profile.experiences):
                rewritten_map[idx] = self.rewrite_experience_bullets(
                    experience=exp,
                    target_role=normalized_profile.target_role,
                    target_job_description=effective_target_context,
                )
            sections = self.format_resume_sections(
                normalized_profile,
                professional_summary=summary,
                rewritten_experience_bullets=rewritten_map,
            )
            markdown_body = self._render_resume_ats_text(normalized_profile, sections)
            text_body = markdown_body
            role_fragment = self._compact_text(normalized_profile.target_role)
            if role_fragment:
                title = f"{normalized_profile.full_name or 'Candidate'} - {role_fragment} Resume"
            else:
                title = f"{normalized_profile.full_name or 'Candidate'} Resume"
            generated = GeneratedResume(
                user_id=safe_user_id,
                resume_title=title,
                professional_summary=summary,
                resume_markdown=markdown_body,
                resume_text=text_body,
                sections=sections,
                profile_snapshot=normalized_profile.to_dict(),
                model_name="placeholder",
                prompt_version="resume-builder-v1-fallback",
                source_job_id=self._compact_text(source_job_id),
                target_job_title=self._compact_text(target_job_title),
                created_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
            )

        saved = self.save_generated_resume(safe_user_id, generated)
        return saved or generated

    def tailor_generated_resume_to_job(
        self,
        generated_resume: GeneratedResume,
        selected_job: dict[str, Any],
    ) -> dict[str, Any]:
        prompt = build_tailor_resume_to_selected_job_prompt(generated_resume, selected_job)
        ai_text = self._try_ai_text(prompt, max_tokens=520)
        parsed = self._safe_json_load(ai_text) if ai_text else {}
        if isinstance(parsed, dict) and parsed:
            return parsed

        # TODO: Replace fallback with model-driven tailoring output.
        job_desc = self._compact_text(str(selected_job.get("description", "") or ""))
        job_title = self._compact_text(str(selected_job.get("title", "") or "target role"))
        resume_skills = [str(skill).strip().lower() for skill in generated_resume.sections.get("skills", [])]
        inferred_missing = self._infer_missing_keywords(job_desc, resume_skills)
        return {
            "professional_summary": generated_resume.professional_summary,
            "updated_experience_bullets": {},
            "missing_skills": inferred_missing[:8],
            "suggestions": [
                f"Align summary and top bullets to {job_title}.",
                "Add quantified impact in recent experience bullets.",
                "Highlight direct keyword overlap from the job description.",
            ],
        }

    def _try_ai_generate_full_resume(self, profile: ResumeProfile, target_job_description: str) -> GeneratedResume | None:
        prompt = build_generate_full_resume_prompt(profile, target_job_description)
        ai_text = self._try_ai_text(prompt, max_tokens=2200, preserve_newlines=True)
        if not ai_text:
            return None
        parsed = self._safe_json_load(ai_text)

        if isinstance(parsed, dict) and parsed:
            summary = self._compact_text(str(parsed.get("professional_summary", "") or ""))
            sections = parsed.get("sections", {})
            if not isinstance(sections, dict):
                sections = self.format_resume_sections(profile, professional_summary=summary)
            else:
                sections = self._normalize_sections_from_ai(profile, sections, summary)
            markdown_body = self._render_resume_ats_text(profile, sections)
            text_body = markdown_body
            role_fragment = self._compact_text(profile.target_role)
            if role_fragment:
                title = f"{profile.full_name or 'Candidate'} - {role_fragment} Resume"
            else:
                title = f"{profile.full_name or 'Candidate'} Resume"
            parsed_title = self._compact_text(str(parsed.get("resume_title", "") or ""))
            return GeneratedResume(
                user_id=int(profile.user_id or 0),
                resume_title=parsed_title or title,
                professional_summary=summary,
                resume_markdown=markdown_body,
                resume_text=text_body,
                sections=sections,
                profile_snapshot=profile.to_dict(),
                model_name=self._model_name,
                prompt_version="resume-builder-v2-ai-structured",
                source_job_id="",
                target_job_title="",
                created_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
            )

        normalized_text = self._normalize_multiline_text(ai_text)
        normalized_text = self._enforce_summary_points_in_resume_text(normalized_text, profile)
        summary = self._extract_summary_from_resume_text(normalized_text) or self._compact_text(profile.summary)
        sections = self.format_resume_sections(profile, professional_summary=summary)
        role_fragment = self._compact_text(profile.target_role)
        if role_fragment:
            title = f"{profile.full_name or 'Candidate'} - {role_fragment} Resume"
        else:
            title = f"{profile.full_name or 'Candidate'} Resume"
        return GeneratedResume(
            user_id=int(profile.user_id or 0),
            resume_title=title,
            professional_summary=summary,
            resume_markdown=normalized_text,
            resume_text=normalized_text,
            sections=sections,
            profile_snapshot=profile.to_dict(),
            model_name=self._model_name,
            prompt_version="resume-builder-v2-ai-text",
            source_job_id="",
            target_job_title="",
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    def _normalize_sections_from_ai(
        self,
        profile: ResumeProfile,
        sections: dict[str, Any],
        summary: str,
    ) -> dict[str, Any]:
        merged = self.format_resume_sections(profile, professional_summary=summary)
        for key in ("header", "professional_summary", "skills", "experience", "education", "projects", "certifications"):
            if key in sections:
                merged[key] = sections[key]
        if not isinstance(merged.get("skills"), list):
            merged["skills"] = list(profile.skills)
        return merged

    def _build_target_context(self, profile: ResumeProfile, target_job_description: str = "") -> str:
        jd_text = self._compact_text(target_job_description or profile.target_job_description)
        role_text = self._compact_text(profile.target_role)
        job_link = self._compact_text(profile.target_job_link)
        extracted_from_link = self._fetch_job_description_from_url(job_link)
        parts: list[str] = []
        if role_text:
            parts.append(f"Target Position: {role_text}")
        if job_link:
            parts.append(f"Target Job Link: {job_link}")
        if jd_text:
            parts.append(f"Target Job Description:\n{jd_text}")
        if extracted_from_link:
            parts.append(f"Job URL Extracted Context:\n{extracted_from_link}")
        return "\n\n".join(part for part in parts if part).strip()

    def _fetch_job_description_from_url(self, job_link: str, max_chars: int = 5000) -> str:
        cleaned_link = self._normalize_job_url(job_link)
        if not cleaned_link:
            return ""
        try:
            request = Request(
                cleaned_link,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml",
                },
            )
            with urlopen(request, timeout=10) as response:
                raw_bytes = response.read(850000)
        except (HTTPError, URLError, TimeoutError, ValueError, OSError):
            return ""
        except Exception:
            return ""

        try:
            html_text = raw_bytes.decode("utf-8", errors="ignore")
        except Exception:
            return ""
        extracted = self._extract_job_text_from_html(html_text, max_chars=max_chars)
        return extracted

    @staticmethod
    def _normalize_job_url(job_link: str) -> str:
        raw = str(job_link or "").strip()
        if not raw:
            return ""
        parsed = urlparse(raw)
        if parsed.scheme not in {"http", "https"}:
            return ""
        if not parsed.netloc:
            return ""
        return raw

    def _extract_job_text_from_html(self, html_text: str, max_chars: int = 5000) -> str:
        raw_html = str(html_text or "")
        if not raw_html.strip():
            return ""

        title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw_html)
        title_text = self._compact_text(unescape(title_match.group(1))) if title_match else ""

        meta_desc_match = re.search(
            r'(?is)<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
            raw_html,
        )
        if not meta_desc_match:
            meta_desc_match = re.search(
                r'(?is)<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']description["\']',
                raw_html,
            )
        meta_desc_text = self._compact_text(unescape(meta_desc_match.group(1))) if meta_desc_match else ""

        sanitized = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", raw_html)
        sanitized = re.sub(r"(?is)<!--.*?-->", " ", sanitized)
        sanitized = re.sub(r"(?is)</(p|li|h1|h2|h3|h4|h5|h6|div|section|article|tr)>", "\n", sanitized)
        sanitized = re.sub(r"(?is)<br\s*/?>", "\n", sanitized)
        sanitized = re.sub(r"(?is)<[^>]+>", " ", sanitized)
        plain_text = unescape(sanitized)
        plain_text = re.sub(r"[ \t]+", " ", plain_text)
        lines = [self._compact_text(line) for line in plain_text.splitlines()]
        useful_lines: list[str] = []
        for line in lines:
            if len(line) < 28:
                continue
            lowered = line.lower()
            if lowered.startswith(("cookie", "accept all", "privacy policy", "terms of use", "sign in", "log in")):
                continue
            useful_lines.append(line)
            if len(useful_lines) >= 120:
                break

        parts: list[str] = []
        if title_text:
            parts.append(f"Page Title: {title_text}")
        if meta_desc_text:
            parts.append(f"Page Description: {meta_desc_text}")
        if useful_lines:
            parts.append("Extracted Job Content:\n" + "\n".join(useful_lines[:80]))

        combined = "\n\n".join(part for part in parts if part).strip()
        if not combined:
            return ""
        return combined[: max(800, int(max_chars or 5000))].strip()

    def _try_ai_text(self, prompt: str, max_tokens: int = 900, preserve_newlines: bool = False) -> str:
        client = self._get_ai_client()
        if client is None:
            return ""
        try:
            response = client.chat.completions.create(
                model=self._model_name,
                temperature=0.2,
                max_tokens=max(120, int(max_tokens or 900)),
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a senior resume writer. Follow user instructions precisely and return concise output."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            raw_text = str(response.choices[0].message.content or "")
            if preserve_newlines:
                return self._normalize_multiline_text(raw_text)
            return self._compact_text(raw_text)
        except Exception:
            return ""

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
    def _rewrite_line_placeholder(line: str, experience: ResumeExperience) -> str:
        clean_line = re.sub(r"\s+", " ", str(line or "").strip())
        if not clean_line:
            clean_line = f"Contributed to delivery outcomes in {experience.role or 'role'}."
        if len(clean_line) > 180:
            clean_line = clean_line[:177].rstrip() + "..."
        prefix = "Delivered"
        lowered = clean_line.lower()
        if lowered.startswith(("built ", "created ", "designed ", "implemented ", "led ", "managed ")):
            prefix = clean_line.split(" ", 1)[0].capitalize()
            rest = clean_line.split(" ", 1)[1] if " " in clean_line else ""
            return f"{prefix} {rest}".strip()
        return f"{prefix} {clean_line[0].lower() + clean_line[1:] if len(clean_line) > 1 else clean_line}."

    @staticmethod
    def _extract_bullets_from_ai(ai_text: str) -> list[str]:
        cleaned = str(ai_text or "").strip()
        if not cleaned:
            return []

        parsed = ResumeBuilderService._safe_json_load(cleaned)
        if isinstance(parsed, list):
            return [ResumeBuilderService._compact_text(str(item)) for item in parsed if ResumeBuilderService._compact_text(str(item))]
        if isinstance(parsed, dict):
            for key in ("bullets", "updated_experience_bullets", "items"):
                candidate = parsed.get(key)
                if isinstance(candidate, list):
                    return [ResumeBuilderService._compact_text(str(item)) for item in candidate if ResumeBuilderService._compact_text(str(item))]

        lines: list[str] = []
        for raw_line in cleaned.splitlines():
            line = raw_line.strip().lstrip("-").lstrip("*").strip()
            if not line:
                continue
            lines.append(ResumeBuilderService._compact_text(line))
        return lines

    @staticmethod
    def _normalize_multiline_text(value: str) -> str:
        raw = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
        cleaned_lines = [line.rstrip() for line in raw.split("\n")]
        normalized: list[str] = []
        previous_blank = False
        for line in cleaned_lines:
            if line.strip():
                normalized.append(line.strip())
                previous_blank = False
            else:
                if not previous_blank:
                    normalized.append("")
                previous_blank = True
        return "\n".join(normalized).strip()

    @staticmethod
    def _extract_summary_from_resume_text(resume_text: str) -> str:
        normalized = str(resume_text or "").replace("**", "")
        lines = [line.strip() for line in normalized.splitlines()]
        if not lines:
            return ""

        summary_headings = {"PROFESSIONAL SUMMARY", "SUMMARY"}
        stop_headings = {
            "SKILLS",
            "PROFESSIONAL EXPERIENCE",
            "EXPERIENCE",
            "PROJECTS",
            "EDUCATION",
            "CERTIFICATIONS",
            "TARGET ROLE / TITLE",
            "TARGET ROLE",
        }

        summary_start = -1
        for idx, line in enumerate(lines):
            if line.upper() in summary_headings:
                summary_start = idx + 1
                break
        if summary_start < 0:
            return ""

        collected: list[str] = []
        for line in lines[summary_start:]:
            upper = line.upper()
            if upper in stop_headings:
                break
            if line:
                cleaned = re.sub(r"^\s*[-*]\s*", "", line).strip()
                if cleaned:
                    collected.append(cleaned)
            if len(collected) >= 6:
                break
        return " ".join(collected).strip()

    def _render_resume_ats_text(self, profile: ResumeProfile, sections: dict[str, Any]) -> str:
        header = sections.get("header", {}) if isinstance(sections.get("header"), dict) else {}
        full_name = str(header.get("full_name", "") or profile.full_name or "").strip()
        email = str(header.get("email", "") or profile.email or "").strip()
        phone = str(header.get("phone", "") or profile.phone or "").strip()
        location = str(header.get("location", "") or profile.location or "").strip()
        linkedin = str(header.get("linkedin_url", "") or profile.linkedin_url or "").strip()
        portfolio = str(header.get("portfolio_url", "") or profile.portfolio_url or "").strip()
        role = str(profile.target_role or header.get("target_role", "") or "").strip()
        summary = str(sections.get("professional_summary", "") or profile.summary or "").strip()
        skills = sections.get("skills", [])
        experience = sections.get("experience", [])
        education = sections.get("education", [])
        projects = sections.get("projects", [])
        certifications = sections.get("certifications", [])

        lines: list[str] = []
        if full_name:
            lines.append(full_name)

        contact_parts = [part for part in [phone, email, linkedin, portfolio, location] if str(part or "").strip()]
        if contact_parts:
            lines.append(" | ".join(contact_parts))

        lines.extend(["", "**TARGET ROLE / TITLE**"])
        lines.append(role or "Target Role")

        lines.extend(["", "**PROFESSIONAL SUMMARY**"])
        normalized_summary = self._build_role_aligned_summary(
            summary=summary,
            profile=profile,
            skills=skills if isinstance(skills, list) else list(profile.skills),
        )
        summary_points = self._build_summary_points(
            summary=normalized_summary,
            profile=profile,
            skills=skills if isinstance(skills, list) else list(profile.skills),
            role_text=role,
        )
        for point in summary_points:
            lines.append(f"- {point}")

        lines.extend(["", "**SKILLS**"])
        grouped_skills = self._group_skills_for_resume(
            skills if isinstance(skills, list) else list(profile.skills),
            role_text=role,
        )
        for category in ("Programming Languages", "Frameworks & Libraries", "Tools & Technologies", "Databases"):
            items = grouped_skills.get(category, [])
            if items:
                lines.append(f"{category}: {', '.join(items)}")

        if isinstance(experience, list) and experience:
            lines.extend(["", "**PROFESSIONAL EXPERIENCE**"])
            for exp in experience:
                if not isinstance(exp, dict):
                    continue
                role_line = str(exp.get("role", "") or "").strip()
                company_line = str(exp.get("company", "") or "").strip()
                start = str(exp.get("start_date", "") or "").strip()
                end = str(exp.get("end_date", "") or "").strip()
                heading = " — ".join(part for part in [role_line, company_line] if part)
                date_text = " to ".join(part for part in [start, end] if part)
                if heading and date_text:
                    lines.append(f"{heading} | {date_text}")
                elif heading:
                    lines.append(heading)
                bullets = exp.get("bullets", [])
                if isinstance(bullets, list):
                    prioritized_bullets = self._prioritize_bullets_for_role(
                        bullets=bullets,
                        role_text=role,
                        job_description=str(profile.target_job_description or "").strip(),
                    )
                    for bullet in prioritized_bullets[:5]:
                        bullet_text = str(bullet or "").strip()
                        if bullet_text:
                            lines.append(f"- {bullet_text}")

        if isinstance(projects, list) and projects:
            lines.extend(["", "**PROJECTS**"])
            for proj in projects:
                if not isinstance(proj, dict):
                    continue
                name = str(proj.get("name", "") or "").strip()
                if name:
                    lines.append(name)
                project_bullets = proj.get("bullets", [])
                if isinstance(project_bullets, list) and project_bullets:
                    for bullet in project_bullets[:2]:
                        bullet_text = str(bullet or "").strip()
                        if bullet_text:
                            lines.append(f"- {bullet_text}")
                else:
                    summary_line = str(proj.get("summary", "") or "").strip()
                    if summary_line:
                        lines.append(f"- {summary_line}")

        if isinstance(education, list) and education:
            lines.extend(["", "**EDUCATION**"])
            for edu in education:
                if not isinstance(edu, dict):
                    continue
                degree = str(edu.get("degree", "") or "").strip()
                field = str(edu.get("field_of_study", "") or "").strip()
                institution = str(edu.get("institution", "") or "").strip()
                end_date = str(edu.get("end_date", "") or "").strip()
                degree_title = " ".join(part for part in [degree, field] if part).strip()
                main_text = " — ".join(part for part in [degree_title, institution] if part).strip()
                if main_text and end_date:
                    lines.append(f"{main_text} | {end_date}")
                elif main_text:
                    lines.append(main_text)

        if isinstance(certifications, list) and certifications:
            lines.extend(["", "**CERTIFICATIONS**"])
            for cert in certifications:
                if not isinstance(cert, dict):
                    continue
                name = str(cert.get("name", "") or "").strip()
                issuer = str(cert.get("issuer", "") or "").strip()
                cert_line = f"{name} — {issuer}" if name and issuer else name
                if cert_line:
                    lines.append(cert_line)

        return self._normalize_multiline_text("\n".join(lines))

    def _group_skills_for_resume(self, skills: list[Any], role_text: str = "") -> dict[str, list[str]]:
        language_set = {
            "python", "java", "javascript", "typescript", "go", "golang", "c", "c++", "c#", "ruby", "scala", "kotlin", "php", "sql",
        }
        framework_set = {
            "django", "flask", "fastapi", "spring", "spring boot", "react", "node", "nodejs", "express", "angular", "vue",
            "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch",
        }
        database_set = {
            "postgres", "postgresql", "mysql", "sqlite", "mongodb", "redis", "dynamodb", "cassandra", "oracle", "snowflake",
        }

        grouped: dict[str, list[str]] = {
            "Programming Languages": [],
            "Frameworks & Libraries": [],
            "Tools & Technologies": [],
            "Databases": [],
        }

        seen: set[str] = set()
        for raw_skill in skills or []:
            skill = str(raw_skill or "").strip()
            if not skill:
                continue
            lowered = skill.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            if lowered in language_set:
                grouped["Programming Languages"].append(skill)
            elif lowered in framework_set:
                grouped["Frameworks & Libraries"].append(skill)
            elif lowered in database_set:
                grouped["Databases"].append(skill)
            else:
                grouped["Tools & Technologies"].append(skill)

        for inferred_skill in self._infer_role_skills(role_text):
            lowered = inferred_skill.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            if lowered in language_set:
                grouped["Programming Languages"].append(inferred_skill)
            elif lowered in framework_set:
                grouped["Frameworks & Libraries"].append(inferred_skill)
            elif lowered in database_set:
                grouped["Databases"].append(inferred_skill)
            else:
                grouped["Tools & Technologies"].append(inferred_skill)

        return grouped

    def _build_role_aligned_summary(self, summary: str, profile: ResumeProfile, skills: list[Any]) -> str:
        clean_summary = self._compact_text(summary)
        role = self._compact_text(profile.target_role)
        years = max(1, len(profile.experiences))
        top_skills = [str(item).strip() for item in skills if str(item).strip()]
        top_skill_text = ", ".join(top_skills[:5]) if top_skills else "relevant technologies"

        if clean_summary:
            if role and role.lower() not in clean_summary.lower():
                return self._compact_text(f"{role} with {years}+ experience blocks. {clean_summary}")
            return clean_summary

        if role:
            return (
                f"{role} with {years}+ experience blocks delivering production outcomes. "
                f"Strong focus on {top_skill_text}. "
                "Builds scalable, reliable solutions with measurable impact."
            )
        return (
            f"Professional with {years}+ experience blocks delivering production outcomes. "
            f"Strong focus on {top_skill_text}. "
            "Builds scalable, reliable solutions with measurable impact."
        )

    def _build_summary_points(
        self,
        summary: str,
        profile: ResumeProfile,
        skills: list[Any],
        role_text: str = "",
    ) -> list[str]:
        normalized = self._normalize_multiline_text(summary)
        candidates: list[str] = []
        for raw_line in normalized.splitlines():
            line = re.sub(r"^\s*[-*]\s*", "", raw_line).strip()
            if not line:
                continue
            segments = [item.strip() for item in re.split(r"(?<=[.!?])\s+", line) if item.strip()]
            if segments:
                candidates.extend(segments)
            else:
                candidates.append(line)

        years = max(1, len(profile.experiences))
        role = self._compact_text(role_text or profile.target_role)
        clean_skills = [str(item).strip() for item in skills if str(item).strip()]
        top_skill_text = ", ".join(clean_skills[:5]) if clean_skills else "relevant technologies"
        jd_terms = self._extract_priority_terms(profile.target_job_description, limit=4)

        fallback_points: list[str] = []
        if role:
            fallback_points.append(f"{role} with {years}+ experience blocks delivering production-ready outcomes.")
        else:
            fallback_points.append(f"Professional with {years}+ experience blocks delivering production-ready outcomes.")
        fallback_points.append(f"Core technical strengths include {top_skill_text}.")
        if jd_terms:
            fallback_points.append(f"Directly aligned to requirements in {', '.join(jd_terms)}.")
        fallback_points.append("Builds scalable and reliable services with measurable impact.")
        fallback_points.append("Improves API and system performance through practical architecture choices.")
        fallback_points.append("Executes end-to-end delivery with ownership, quality, and maintainability focus.")

        seen: set[str] = set()
        merged: list[str] = []
        for item in [*candidates, *fallback_points]:
            clean = self._compact_text(str(item or "").strip().strip("-"))
            if len(clean) < 8:
                continue
            lowered = clean.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            if clean[-1] not in {".", "!", "?"}:
                clean = f"{clean}."
            merged.append(clean)
            if len(merged) >= 6:
                break

        while len(merged) < 5:
            generic = "Delivers outcomes aligned to role requirements and business priorities."
            if generic.lower() not in seen:
                merged.append(generic)
                seen.add(generic.lower())
            else:
                merged.append("Builds solutions with reliability, scalability, and strong execution discipline.")

        return merged[:6]

    def _enforce_summary_points_in_resume_text(self, resume_text: str, profile: ResumeProfile) -> str:
        normalized = self._normalize_multiline_text(resume_text)
        if not normalized:
            return normalized

        lines = normalized.splitlines()
        summary_headings = {"PROFESSIONAL SUMMARY", "SUMMARY"}
        stop_headings = {
            "SKILLS",
            "PROFESSIONAL EXPERIENCE",
            "EXPERIENCE",
            "PROJECTS",
            "EDUCATION",
            "CERTIFICATIONS",
            "TARGET ROLE / TITLE",
            "TARGET ROLE",
        }

        summary_idx = -1
        for idx, line in enumerate(lines):
            normalized_heading = line.strip().replace("**", "").strip().upper()
            if normalized_heading in summary_headings:
                summary_idx = idx
                break
        if summary_idx < 0:
            return normalized

        end_idx = len(lines)
        for idx in range(summary_idx + 1, len(lines)):
            normalized_heading = lines[idx].strip().replace("**", "").strip().upper()
            if normalized_heading in stop_headings:
                end_idx = idx
                break
            if lines[idx].strip().startswith("**") and lines[idx].strip().endswith("**"):
                end_idx = idx
                break

        current_summary_block = "\n".join(lines[summary_idx + 1 : end_idx]).strip()
        summary_points = self._build_summary_points(
            summary=current_summary_block,
            profile=profile,
            skills=list(profile.skills),
            role_text=profile.target_role,
        )
        replacement_lines = [f"- {point}" for point in summary_points]
        merged_lines = lines[: summary_idx + 1] + replacement_lines + lines[end_idx:]
        return self._normalize_multiline_text("\n".join(merged_lines))

    @staticmethod
    def _extract_priority_terms(raw_text: str, limit: int = 4) -> list[str]:
        text = str(raw_text or "").strip().lower()
        if not text:
            return []
        tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9+#.\-]{2,}", text)
        stopwords = {
            "with",
            "that",
            "from",
            "your",
            "have",
            "will",
            "this",
            "role",
            "team",
            "years",
            "experience",
            "skills",
            "work",
            "ability",
            "using",
            "strong",
            "knowledge",
            "development",
            "engineering",
            "software",
            "data",
            "and",
            "the",
            "for",
            "job",
            "position",
        }
        seen: set[str] = set()
        ordered: list[str] = []
        for token in tokens:
            if token in stopwords:
                continue
            if token in seen:
                continue
            seen.add(token)
            ordered.append(token.title())
            if len(ordered) >= max(1, int(limit or 4)):
                break
        return ordered

    def _retrieve_relevant_resume_chunks(self, resume_text: str, target_context: str, top_k: int = 6) -> list[str]:
        clean_resume = self._normalize_multiline_text(resume_text)
        if not clean_resume:
            return []

        paragraphs = [item.strip() for item in re.split(r"\n{2,}", clean_resume) if item.strip()]
        if not paragraphs:
            paragraphs = [line.strip() for line in clean_resume.splitlines() if len(line.strip()) > 30]
        if not paragraphs:
            return []

        target_tokens = {
            token.lower()
            for token in re.findall(r"[a-zA-Z][a-zA-Z0-9+#.\-]{2,}", str(target_context or ""))
            if len(token) > 2
        }
        if not target_tokens:
            return paragraphs[: max(1, int(top_k or 6))]

        scored: list[tuple[int, str]] = []
        for paragraph in paragraphs:
            lowered = paragraph.lower()
            score = sum(1 for token in target_tokens if token in lowered)
            if score <= 0:
                continue
            scored.append((score, paragraph))

        if not scored:
            return paragraphs[: max(1, int(top_k or 6))]
        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored[: max(1, int(top_k or 6))]]

    @staticmethod
    def _normalize_str_list(raw_items: Any, limit: int = 20) -> list[str]:
        if isinstance(raw_items, str):
            raw_list = [item.strip() for item in re.split(r"[,;\n]", raw_items)]
        elif isinstance(raw_items, (list, tuple, set)):
            raw_list = [str(item).strip() for item in raw_items]
        else:
            raw_list = []
        deduped: list[str] = []
        seen: set[str] = set()
        for item in raw_list:
            clean = re.sub(r"^\s*[-*]\s*", "", item).strip()
            if not clean:
                continue
            lowered = clean.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            deduped.append(clean)
            if len(deduped) >= max(1, int(limit or 20)):
                break
        return deduped

    def _merge_unique_texts(self, items: list[Any], limit: int = 20) -> list[str]:
        return self._normalize_str_list(items, limit=limit)

    @staticmethod
    def _extract_candidate_skills_from_text(resume_text: str, limit: int = 24) -> list[str]:
        text = str(resume_text or "").lower()
        if not text:
            return []

        skill_catalog = [
            "Python", "Java", "JavaScript", "TypeScript", "Go", "SQL",
            "FastAPI", "Django", "Flask", "Spring", "React", "Node.js",
            "PostgreSQL", "MySQL", "MongoDB", "Redis", "Snowflake",
            "Docker", "Kubernetes", "AWS", "GCP", "Azure", "Terraform",
            "Airflow", "Spark", "Pandas", "NumPy", "Scikit-learn",
            "REST APIs", "Microservices", "CI/CD", "Git",
        ]
        detected: list[str] = []
        for skill in skill_catalog:
            pattern = r"\b" + re.escape(skill.lower()).replace(r"\ ", r"\s+") + r"\b"
            if re.search(pattern, text):
                detected.append(skill)
            if len(detected) >= max(1, int(limit or 24)):
                break
        return detected

    @staticmethod
    def _infer_title_from_resume_text(resume_text: str) -> str:
        lines = [line.strip() for line in str(resume_text or "").splitlines() if line.strip()]
        title_keywords = ("engineer", "developer", "scientist", "manager", "analyst", "architect", "consultant")
        for line in lines[:40]:
            lowered = line.lower()
            if any(keyword in lowered for keyword in title_keywords):
                if len(line.split()) <= 10:
                    return line
        return ""

    @staticmethod
    def _prioritize_bullets_for_role(bullets: list[Any], role_text: str, job_description: str = "") -> list[str]:
        role_tokens = {
            token.lower()
            for token in re.findall(r"[a-zA-Z][a-zA-Z0-9+#.-]+", str(role_text or ""))
            if len(token) > 2
        }
        jd_tokens = {
            token.lower()
            for token in re.findall(r"[a-zA-Z][a-zA-Z0-9+#.-]+", str(job_description or ""))
            if len(token) > 3
        }
        scoring_tokens = role_tokens.union(jd_tokens)

        scored: list[tuple[int, str]] = []
        for item in bullets or []:
            bullet_text = str(item or "").strip()
            if not bullet_text:
                continue
            lowered = bullet_text.lower()
            score = sum(1 for token in scoring_tokens if token in lowered)
            scored.append((score, bullet_text))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored]

    @staticmethod
    def _infer_role_skills(role_text: str) -> list[str]:
        lowered = str(role_text or "").lower()
        if not lowered:
            return []

        mapping: list[tuple[tuple[str, ...], list[str]]] = [
            (("backend", "api", "microservice", "distributed"), ["Python", "FastAPI", "PostgreSQL", "Redis", "Docker", "AWS"]),
            (("data engineer", "etl", "pipeline"), ["Python", "SQL", "Airflow", "Spark", "PostgreSQL", "AWS"]),
            (("data scientist", "machine learning", "ml"), ["Python", "Pandas", "NumPy", "Scikit-learn", "SQL", "Jupyter"]),
            (("frontend", "ui", "react"), ["JavaScript", "TypeScript", "React", "HTML", "CSS", "REST APIs"]),
            (("devops", "sre", "platform"), ["Linux", "Docker", "Kubernetes", "Terraform", "AWS", "CI/CD"]),
        ]
        for patterns, skill_list in mapping:
            if any(pattern in lowered for pattern in patterns):
                return skill_list
        return []

    @staticmethod
    def _render_resume_markdown(sections: dict[str, Any]) -> str:
        header = sections.get("header", {}) if isinstance(sections.get("header"), dict) else {}
        full_name = str(header.get("full_name", "") or "").strip()
        email = str(header.get("email", "") or "").strip()
        phone = str(header.get("phone", "") or "").strip()
        location = str(header.get("location", "") or "").strip()
        linkedin = str(header.get("linkedin_url", "") or "").strip()
        portfolio = str(header.get("portfolio_url", "") or "").strip()
        summary = str(sections.get("professional_summary", "") or "").strip()
        skills = sections.get("skills", [])
        experience = sections.get("experience", [])
        education = sections.get("education", [])
        projects = sections.get("projects", [])
        certifications = sections.get("certifications", [])

        lines: list[str] = []
        if full_name:
            lines.append(f"# {full_name}")
        contact_parts = [part for part in [email, phone, location, linkedin, portfolio] if part]
        if contact_parts:
            lines.append(" | ".join(contact_parts))
        if summary:
            lines.extend(["", "## Professional Summary", summary])
        if isinstance(skills, list) and skills:
            skill_text = ", ".join(str(item).strip() for item in skills if str(item).strip())
            if skill_text:
                lines.extend(["", "## Skills", skill_text])
        if isinstance(experience, list) and experience:
            lines.extend(["", "## Experience"])
            for exp in experience:
                if not isinstance(exp, dict):
                    continue
                role = str(exp.get("role", "") or "").strip()
                company = str(exp.get("company", "") or "").strip()
                start = str(exp.get("start_date", "") or "").strip()
                end = str(exp.get("end_date", "") or "").strip()
                heading = " - ".join(part for part in [role, company] if part)
                if heading:
                    lines.append(f"**{heading}**")
                date_line = " to ".join(part for part in [start, end] if part)
                if date_line:
                    lines.append(date_line)
                bullets = exp.get("bullets", [])
                if isinstance(bullets, list):
                    for bullet in bullets:
                        bullet_text = str(bullet or "").strip()
                        if bullet_text:
                            lines.append(f"- {bullet_text}")
        if isinstance(education, list) and education:
            lines.extend(["", "## Education"])
            for edu in education:
                if not isinstance(edu, dict):
                    continue
                degree = str(edu.get("degree", "") or "").strip()
                field = str(edu.get("field_of_study", "") or "").strip()
                institution = str(edu.get("institution", "") or "").strip()
                heading = ", ".join(part for part in [degree, field] if part)
                if heading:
                    lines.append(f"**{heading}**")
                if institution:
                    lines.append(institution)
        if isinstance(projects, list) and projects:
            lines.extend(["", "## Projects"])
            for proj in projects:
                if not isinstance(proj, dict):
                    continue
                name = str(proj.get("name", "") or "").strip()
                summary_line = str(proj.get("summary", "") or "").strip()
                if name:
                    lines.append(f"**{name}**")
                if summary_line:
                    lines.append(summary_line)
                bullets = proj.get("bullets", [])
                if isinstance(bullets, list):
                    for bullet in bullets:
                        bullet_text = str(bullet or "").strip()
                        if bullet_text:
                            lines.append(f"- {bullet_text}")
        if isinstance(certifications, list) and certifications:
            lines.extend(["", "## Certifications"])
            for cert in certifications:
                if not isinstance(cert, dict):
                    continue
                name = str(cert.get("name", "") or "").strip()
                issuer = str(cert.get("issuer", "") or "").strip()
                if name and issuer:
                    lines.append(f"- {name} ({issuer})")
                elif name:
                    lines.append(f"- {name}")

        return "\n".join(lines).strip()

    @staticmethod
    def _render_resume_text(sections: dict[str, Any]) -> str:
        markdown = ResumeBuilderService._render_resume_markdown(sections)
        return re.sub(r"[*#`_>\-\[\]]+", "", markdown)

    @staticmethod
    def _sentence_split(text: str) -> list[str]:
        parts = re.split(r"(?<=[.!?])\s+", str(text or "").strip())
        return [ResumeBuilderService._compact_text(item) for item in parts if ResumeBuilderService._compact_text(item)]

    @staticmethod
    def _infer_missing_keywords(job_description: str, existing_skills: list[str]) -> list[str]:
        if not job_description.strip():
            return []
        tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9\+\#\.\-]{2,}", job_description.lower())
        stopwords = {
            "with",
            "that",
            "from",
            "your",
            "have",
            "will",
            "this",
            "role",
            "team",
            "years",
            "experience",
            "skills",
            "work",
            "ability",
            "using",
            "strong",
            "knowledge",
            "development",
            "engineering",
            "software",
            "data",
            "and",
            "the",
            "for",
        }
        existing = {item.lower() for item in existing_skills}
        ranked: list[str] = []
        seen: set[str] = set()
        for token in tokens:
            if token in stopwords:
                continue
            if token in existing:
                continue
            if token in seen:
                continue
            seen.add(token)
            ranked.append(token.title())
            if len(ranked) >= 20:
                break
        return ranked

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
                pass
        start_idx = cleaned.find("[")
        end_idx = cleaned.rfind("]")
        if start_idx >= 0 and end_idx > start_idx:
            try:
                return json.loads(cleaned[start_idx : end_idx + 1])
            except Exception:
                pass
        return {}

    @staticmethod
    def _compact_text(value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip())
