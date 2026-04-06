from __future__ import annotations

import json
from typing import Any


def build_job_analysis_prompt(
    *,
    user_profile: dict[str, Any],
    job_payload: dict[str, Any],
    target_job_description: str = "",
) -> str:
    safe_profile = _sanitize_profile(user_profile)
    safe_job = _sanitize_job(job_payload)
    safe_target_jd = str(target_job_description or "").strip()
    payload = {
        "user_profile": safe_profile,
        "job": safe_job,
        "target_job_description": safe_target_jd,
        "output_schema": {
            "match_score": "integer 0-100",
            "ai_summary": "single concise sentence",
            "why_fit": ["string", "string", "string"],
            "missing_skills": ["string"],
            "recommendation": "APPLY | IMPROVE_FIRST | SKIP",
        },
        "rules": [
            "Return valid JSON only.",
            "why_fit must include exactly 3 concise bullet strings.",
            "missing_skills should include only meaningful role gaps.",
            "recommendation must be one of APPLY, IMPROVE_FIRST, SKIP.",
            "Do not include markdown fences.",
            "Be strict, avoid inflated match scoring.",
        ],
    }
    return (
        "You are an expert AI careers analyst for job fit decisions.\n"
        "Analyze the user's profile against the job and return structured decision guidance.\n\n"
        f"Input: {json.dumps(payload, ensure_ascii=True)}"
    )


def _sanitize_profile(profile: dict[str, Any]) -> dict[str, Any]:
    raw = dict(profile or {})
    skills = raw.get("skills", [])
    if isinstance(skills, str):
        skill_list = [item.strip() for item in skills.split(",") if item.strip()]
    elif isinstance(skills, (list, tuple, set)):
        skill_list = [str(item).strip() for item in skills if str(item).strip()]
    else:
        skill_list = []
    return {
        "target_role": str(raw.get("target_role", "") or "").strip(),
        "summary": str(raw.get("summary", "") or "").strip()[:2000],
        "skills": skill_list[:40],
        "experience": _clip_any(raw.get("experience", raw.get("experiences", "")), 2200),
        "education": _clip_any(raw.get("education", ""), 1200),
        "projects": _clip_any(raw.get("projects", ""), 1200),
        "resume_text": _clip_any(raw.get("resume_text", ""), 2600),
    }


def _sanitize_job(job: dict[str, Any]) -> dict[str, Any]:
    raw = dict(job or {})
    return {
        "job_id": str(raw.get("job_id", "") or "").strip(),
        "title": str(raw.get("title", "") or "").strip(),
        "company": str(raw.get("company", "") or "").strip(),
        "location": str(raw.get("location", "") or "").strip(),
        "source": str(raw.get("source", "") or "").strip(),
        "work_type": str(raw.get("work_type", "") or "").strip(),
        "level": str(raw.get("level", "") or "").strip(),
        "industry": str(raw.get("industry", "") or "").strip(),
        "description": str(raw.get("description", "") or "").strip()[:3800],
        "certifications": _to_text_list(raw.get("certifications", []), limit=20),
        "tags": _to_text_list(raw.get("tags", []), limit=30),
    }


def _to_text_list(value: Any, *, limit: int = 20) -> list[str]:
    if isinstance(value, str):
        items = [item.strip() for item in value.split(",")]
    elif isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value]
    else:
        items = []
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not item:
            continue
        lowered = item.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(item)
        if len(deduped) >= max(1, int(limit or 20)):
            break
    return deduped


def _clip_any(value: Any, max_len: int) -> str:
    if isinstance(value, str):
        return str(value).strip()[: max(200, int(max_len or 1200))]
    if isinstance(value, (list, tuple, set)):
        joined = " | ".join(str(item).strip() for item in value if str(item).strip())
        return joined[: max(200, int(max_len or 1200))]
    if isinstance(value, dict):
        try:
            serialized = json.dumps(value, ensure_ascii=True)
        except Exception:
            serialized = str(value)
        return serialized[: max(200, int(max_len or 1200))]
    return str(value or "").strip()[: max(200, int(max_len or 1200))]
