from __future__ import annotations

import json
from typing import Any

from src.dto.resume_builder_dto import GeneratedResume, ResumeExperience, ResumeProfile


def build_generate_full_resume_prompt(profile: ResumeProfile, target_job_description: str = "") -> str:
    role_text = str(profile.target_role or "").strip()
    target_link = str(profile.target_job_link or "").strip()
    jd_text = str(target_job_description or profile.target_job_description or "").strip()
    payload = {
        "user_profile": profile.to_dict(),
        "job_description": {
            "job_title": role_text,
            "company_name": "",
            "key_responsibilities": jd_text,
            "required_skills": "",
            "preferred_qualifications": "",
            "job_link": target_link,
            "raw_job_description": jd_text,
        },
    }
    return (
        "You are an expert resume writer and career strategist.\n"
        "Act like a live resume builder creating the resume in real time based on the target role.\n\n"
        "Your task is to generate a professional, ATS-friendly resume tailored for a specific job role.\n\n"
        "## Input Data\n\n"
        "You will receive:\n\n"
        "1. User Profile:\n"
        "- Full Name\n"
        "- Email\n"
        "- Phone\n"
        "- Location\n"
        "- LinkedIn / GitHub (optional)\n"
        "- Summary (optional)\n"
        "- Skills\n"
        "- Experience (roles, companies, duration, bullets)\n"
        "- Education\n"
        "- Certifications (optional)\n"
        "- Projects (optional)\n\n"
        "2. Job Description:\n"
        "- Job Title\n"
        "- Company Name\n"
        "- Key Responsibilities\n"
        "- Required Skills\n"
        "- Preferred Qualifications\n\n"
        "---\n\n"
        "## Your Goal\n\n"
        "Generate a clean, concise, and impactful resume optimized for this job.\n\n"
        "---\n\n"
        "## Output Requirements\n\n"
        "### 1. Structure (STRICT FORMAT)\n\n"
        "Generate resume in this exact order:\n\n"
        "FULL NAME\n"
        "Phone | Email | LinkedIn (if available) | Location\n\n"
        "**TARGET ROLE / TITLE**\n"
        "(Align this with the job title)\n\n"
        "**PROFESSIONAL SUMMARY**\n\n"
        "- 5-6 bullet points\n"
        "- Strong, impactful, no fluff\n"
        "- Tailored to job\n"
        "- Include years of experience if available\n\n"
        "**SKILLS**\n"
        "Group skills into categories like:\n"
        "- Programming Languages\n"
        "- Frameworks & Libraries\n"
        "- Tools & Technologies\n"
        "- Databases\n\n"
        "Only include relevant skills for the job.\n\n"
        "**PROFESSIONAL EXPERIENCE**\n"
        "For each role:\n"
        "- Job Title - Company Name | Dates\n"
        "- 3-5 bullet points:\n"
        "  - Start with action verbs\n"
        "  - Include measurable impact where possible\n"
        "  - Align bullets with job description\n"
        "  - Highlight backend, API, system design, or relevant domain\n\n"
        "**PROJECTS (if available)**\n"
        "- Project Name\n"
        "- 1-2 strong bullets describing impact and technologies\n\n"
        "**EDUCATION**\n"
        "- Degree - University | Year\n\n"
        "**CERTIFICATIONS (if available)**\n\n"
        "## Optimization Rules\n"
        "- Tailor resume to the given job description\n"
        "- Remove irrelevant skills/experience\n"
        "- Highlight matching technologies\n"
        "- Emphasize backend, APIs, cloud, data, or domain depending on job\n"
        "- Use concise and professional language\n"
        "- No generic phrases like 'hardworking' or 'team player'\n"
        "- No paragraphs longer than 3 lines\n"
        "- Bullet points must be impactful and specific\n\n"
        "## Formatting Rules\n"
        "- Clean and minimal formatting\n"
        "- No emojis\n"
        "- No excessive styling\n"
        "- Plain text but structured for DOCX/PDF conversion\n"
        "- Consistent spacing\n\n"
        "## Output Format\n"
        "Return ONLY the final resume text.\n"
        "Do not explain anything.\n"
        "Do not include headings like 'Here is your resume'.\n"
        "Do not include markdown code blocks.\n\n"
        "## Advanced Behavior (Important)\n"
        "- If user data is incomplete, intelligently fill gaps using industry-standard assumptions\n"
        "- Prioritize relevance over completeness\n"
        "- Rewrite weak experience bullets into strong impact statements\n"
        "- Align everything to maximize chances of passing ATS screening\n"
        "- If job description is limited, optimize aggressively using target title context\n\n"
        "## Example Target Role\n"
        "If job is 'Senior Backend Engineer':\n"
        "- Emphasize APIs, scalability, distributed systems, databases, performance\n"
        "- Highlight Python, Java, Go, cloud, microservices if present\n\n"
        "Now generate the resume.\n\n"
        f"Input: {json.dumps(payload, ensure_ascii=True)}"
    )


def build_improve_professional_summary_prompt(
    profile: ResumeProfile,
    current_summary: str,
    target_job_description: str = "",
) -> str:
    payload = {
        "profile": profile.to_dict(),
        "current_summary": str(current_summary or "").strip(),
        "target_role": str(profile.target_role or "").strip(),
        "target_job_link": str(profile.target_job_link or "").strip(),
        "target_job_description": str(target_job_description or "").strip(),
        "rules": [
            "Return exactly 5 to 6 bullet points",
            "Keep it factual and specific",
            "Prioritize measurable outcomes and core strengths",
            "Avoid generic fluff",
        ],
    }
    return (
        "Improve the professional summary for this candidate. Return plain text only.\n"
        f"Input: {json.dumps(payload, ensure_ascii=True)}"
    )


def build_rewrite_experience_bullets_prompt(
    experience: ResumeExperience,
    target_role: str = "",
    target_job_description: str = "",
) -> str:
    payload = {
        "experience": experience.to_dict(),
        "target_role": str(target_role or "").strip(),
        "target_job_description": str(target_job_description or "").strip(),
        "rules": [
            "Return JSON array of 4 to 6 bullet strings",
            "Use action verb + outcome + scope/impact",
            "Keep each bullet under 28 words",
            "No placeholders",
        ],
    }
    return (
        "Rewrite experience bullets for higher impact and ATS relevance.\n"
        f"Input: {json.dumps(payload, ensure_ascii=True)}"
    )


def build_tailor_resume_to_selected_job_prompt(
    generated_resume: GeneratedResume,
    selected_job: dict[str, Any],
) -> str:
    job_payload = {
        "title": str(selected_job.get("title", "") or "").strip(),
        "company": str(selected_job.get("company", "") or "").strip(),
        "description": str(selected_job.get("description", "") or "").strip(),
        "skills": selected_job.get("skills", []),
        "requirements": selected_job.get("requirements", []),
    }
    payload = {
        "generated_resume": generated_resume.to_dict(),
        "selected_job": job_payload,
        "rules": [
            "Return JSON with fields: professional_summary, updated_experience_bullets, missing_skills, suggestions",
            "Do not fabricate employers or dates",
            "Keep content concise and specific to job fit",
        ],
    }
    return (
        "Tailor this generated resume to the selected job. Keep original facts intact.\n"
        f"Input: {json.dumps(payload, ensure_ascii=True)}"
    )


def build_resume_scan_rag_prompt(
    resume_text: str,
    retrieved_chunks: list[str],
    target_context: str,
    profile: ResumeProfile,
) -> str:
    payload = {
        "target_context": str(target_context or "").strip(),
        "current_profile": profile.to_dict(),
        "retrieved_resume_chunks": [str(item or "").strip() for item in retrieved_chunks if str(item or "").strip()],
        "raw_resume_text_excerpt": str(resume_text or "").strip()[:10000],
        "output_schema": {
            "extracted_title": "string",
            "summary_points": ["string", "string", "string", "string", "string"],
            "recommended_skills": ["string"],
            "missing_skills": ["string"],
            "focus_improvements": ["string"],
        },
    }
    return (
        "You are a resume optimization assistant using retrieval-augmented analysis.\n"
        "Use only provided resume evidence and target context.\n"
        "Return valid JSON only without markdown fences.\n"
        "summary_points must be 5 to 6 concise, impactful bullet strings.\n"
        "Do not fabricate employment history or education.\n\n"
        f"Input: {json.dumps(payload, ensure_ascii=True)}"
    )
