from __future__ import annotations

import io
import json
from datetime import datetime
from typing import Any

import streamlit as st

from src.dto.resume_builder_dto import (
    GeneratedResume,
    ResumeCertification,
    ResumeEducation,
    ResumeExperience,
    ResumeProfile,
    ResumeProject,
)
from src.service.resume_builder_service import ResumeBuilderService
from src.service.resume_export_service import ResumeExportService

try:
    import pdfplumber
except Exception:  # pragma: no cover - optional dependency
    pdfplumber = None  # type: ignore[assignment]

try:
    from docx import Document as DocxDocument
except Exception:  # pragma: no cover - optional dependency
    DocxDocument = None  # type: ignore[assignment]

try:
    from PIL import Image
except Exception:  # pragma: no cover - optional dependency
    Image = None  # type: ignore[assignment]

try:
    import pytesseract
except Exception:  # pragma: no cover - optional dependency
    pytesseract = None  # type: ignore[assignment]


def render_resume_builder_tab(
    user: dict[str, Any],
    resume_builder_service: ResumeBuilderService,
    resume_export_service: ResumeExportService,
) -> None:
    user_id = int(user.get("id") or 0)
    if user_id <= 0:
        st.info("Log in to use Resume Builder.")
        return

    _ensure_resume_builder_state(user_id, resume_builder_service)
    _apply_pending_profile_updates_if_any()
    _apply_pending_scan_updates_if_any()
    st.markdown(
        """
        <div class="resume-builder-hero">
            <div class="resume-builder-hero-icon-wrap">
                <span class="material-symbols-outlined">description</span>
            </div>
            <div>
                <h3>AI Resume Builder</h3>
                <p>Build profile, generate from target position + job context, and export as DOCX/PDF.</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.container(key="resume_builder_profile_form"):
        _render_profile_inputs()
        _render_experience_inputs()
        _render_education_inputs()
        _render_project_inputs()
        _render_certification_inputs()

    profile = _collect_profile_from_state(user_id)
    _render_resume_scan_rag_panel(
        profile=profile,
        resume_builder_service=resume_builder_service,
    )
    profile = _collect_profile_from_state(user_id)

    action_cols = st.columns(3, gap="small")
    with action_cols[0]:
        save_clicked = st.button("Save Draft", key="resume_builder_save_draft_btn", use_container_width=True)
    with action_cols[1]:
        generate_clicked = st.button("Generate Resume", key="resume_builder_generate_btn", use_container_width=True)
    with action_cols[2]:
        reload_clicked = st.button("Load Latest", key="resume_builder_load_latest_btn", use_container_width=True)
    if save_clicked:
        saved = resume_builder_service.save_profile_draft(user_id=user_id, profile=profile)
        if saved is None:
            st.error("Could not save resume profile draft.")
        else:
            st.success("Profile draft saved.")

    if generate_clicked:
        profile = _ensure_profile_target_position(profile)
        generated = _generate_resume_live(
            user_id=user_id,
            profile=profile,
            resume_builder_service=resume_builder_service,
            action_label="Generating",
        )
        if generated is None:
            st.error("Resume generation failed.")
        else:
            st.session_state["resume_builder_generated_resume"] = generated.to_dict()
            st.success("Resume generated.")

    if reload_clicked:
        latest = resume_builder_service.get_latest_generated_resume(user_id=user_id)
        if latest is None:
            st.info("No generated resume found yet.")
        else:
            st.session_state["resume_builder_generated_resume"] = latest.to_dict()
            st.success("Loaded latest generated resume.")

    active_generated_resume = _get_generated_resume_from_state()
    history_items = resume_builder_service.list_generated_resumes(user_id=user_id, limit=50, offset=0)
    selected_history_resume: GeneratedResume | None = None
    with st.container(key="resume_builder_history_shell"):
        selected_history_resume = _render_generated_resume_history(
            generated_resumes=history_items,
            active_resume_id=int(active_generated_resume.id or 0) if active_generated_resume is not None else 0,
        )
    if selected_history_resume is not None:
        st.session_state["resume_builder_generated_resume"] = selected_history_resume.to_dict()
        _seed_profile_from_generated_resume(user_id=user_id, generated_resume=selected_history_resume)
        st.success("Loaded selected resume version.")
        st.rerun()

    generated_resume = _get_generated_resume_from_state()
    st.markdown("### Resume Preview")
    with st.container(key="resume_preview_shell"):
        if generated_resume is None:
            st.caption("Generated preview will appear after you click Generate Resume.")
            draft_markdown = _build_draft_profile_markdown(profile)
            if draft_markdown:
                st.markdown(draft_markdown)
            else:
                st.caption("Add profile details to see a draft preview.")
            return

        preview_mode = st.radio(
            "Preview Mode",
            options=["Formatted", "Markdown", "JSON"],
            key="resume_builder_preview_mode",
            horizontal=True,
        )
        if preview_mode == "Formatted":
            st.markdown(generated_resume.resume_markdown or "No markdown generated yet.")
        elif preview_mode == "Markdown":
            st.code(generated_resume.resume_markdown or "", language="markdown")
        else:
            st.code(json.dumps(generated_resume.to_dict(), indent=2), language="json")

    with st.container(key="resume_actions_download_shell"):
        action_export_cols = st.columns(4, gap="small")
        with action_export_cols[0]:
            improve_summary_clicked = st.button(
                "Improve Summary",
                key="resume_builder_improve_summary_btn",
                use_container_width=True,
            )
        with action_export_cols[1]:
            regenerate_clicked = st.button(
                "Regenerate Resume",
                key="resume_builder_regenerate_btn",
                use_container_width=True,
            )
        with action_export_cols[2]:
            docx_result = resume_export_service.export_generated_resume_to_docx(
                generated_resume=generated_resume,
                file_name=generated_resume.resume_title or profile.full_name or "resume",
            )
            if docx_result.ok and docx_result.content:
                st.download_button(
                    "Download DOCX",
                    data=docx_result.content,
                    file_name=docx_result.file_name,
                    mime=docx_result.mime_type,
                    key="resume_builder_download_docx_btn",
                    use_container_width=True,
                )
            else:
                st.button("Download DOCX", disabled=True, key="resume_builder_download_docx_disabled", use_container_width=True)
        with action_export_cols[3]:
            pdf_result = resume_export_service.export_generated_resume_to_pdf(
                generated_resume=generated_resume,
                file_name=generated_resume.resume_title or profile.full_name or "resume",
            )
            download_label = "Download PDF" if pdf_result.ok else "Download PDF Fallback"
            if pdf_result.content:
                st.download_button(
                    download_label,
                    data=pdf_result.content,
                    file_name=pdf_result.file_name,
                    mime=pdf_result.mime_type,
                    key="resume_builder_download_pdf_btn",
                    use_container_width=True,
                )
            else:
                st.button("Download PDF", disabled=True, key="resume_builder_download_pdf_disabled", use_container_width=True)

    if improve_summary_clicked:
        improved_summary = resume_builder_service.generate_professional_summary(
            profile=profile,
            current_summary=generated_resume.professional_summary,
            target_job_description=profile.target_job_description,
        )
        merged_sections = dict(generated_resume.sections or {})
        merged_sections["professional_summary"] = improved_summary
        updated_resume = GeneratedResume.from_dict(
            {
                **generated_resume.to_dict(),
                "professional_summary": improved_summary,
                "sections": merged_sections,
            }
        )
        saved = resume_builder_service.save_generated_resume(user_id=user_id, generated_resume=updated_resume)
        final_resume = saved or updated_resume
        st.session_state["resume_builder_generated_resume"] = final_resume.to_dict()
        st.success("Professional summary updated.")
        st.rerun()

    if regenerate_clicked:
        profile = _ensure_profile_target_position(profile)
        regenerated = _generate_resume_live(
            user_id=user_id,
            profile=profile,
            resume_builder_service=resume_builder_service,
            action_label="Regenerating",
        )
        if regenerated is None:
            st.error("Regeneration failed.")
        else:
            st.session_state["resume_builder_generated_resume"] = regenerated.to_dict()
            st.success("Resume regenerated.")
            st.rerun()


def _generate_resume_live(
    user_id: int,
    profile: ResumeProfile,
    resume_builder_service: ResumeBuilderService,
    action_label: str,
) -> GeneratedResume | None:
    safe_label = str(action_label or "Generating").strip() or "Generating"

    if hasattr(st, "status"):
        with st.status(f"{safe_label} resume...", expanded=True) as status:
            st.write("Analyzing your target role and job context...")
            if str(profile.target_job_link or "").strip():
                st.write("Matching with details from the job link...")
            st.write("Selecting strongest strengths and achievements...")
            generated = resume_builder_service.generate_resume(
                user_id=user_id,
                profile=profile,
                target_job_description=profile.target_job_description,
                target_job_title=profile.target_role,
            )
            if generated is None:
                status.update(label=f"{safe_label} failed", state="error")
                return None
            st.write("Finalizing ATS-friendly format for preview and export...")
            status.update(label=f"{safe_label} complete", state="complete")
            return generated

    with st.spinner(f"{safe_label} resume..."):
        return resume_builder_service.generate_resume(
            user_id=user_id,
            profile=profile,
            target_job_description=profile.target_job_description,
            target_job_title=profile.target_role,
        )


def _render_profile_inputs() -> None:
    _render_icon_section_header("badge", "Profile", "Personal and target job details")
    top_cols = st.columns(3, gap="small")
    with top_cols[0]:
        st.text_input("Full Name", key="rb_full_name")
    with top_cols[1]:
        st.text_input("Email", key="rb_email")
    with top_cols[2]:
        st.text_input("Phone", key="rb_phone")

    second_cols = st.columns(3, gap="small")
    with second_cols[0]:
        st.text_input("Location", key="rb_location")
    with second_cols[1]:
        st.text_input("LinkedIn", key="rb_linkedin_url")
    with second_cols[2]:
        st.text_input("Portfolio", key="rb_portfolio_url")

    third_cols = st.columns(2, gap="small")
    with third_cols[0]:
        st.text_input("Target Position", key="rb_target_role")
    with third_cols[1]:
        st.text_input("Target Job Link (optional)", key="rb_target_job_link")

    st.text_input("Skills (comma-separated)", key="rb_skills_csv")
    st.text_area("Professional Summary", key="rb_summary", height=120)
    st.text_area("Target Job Description (optional)", key="rb_target_job_description", height=130)


def _render_experience_inputs() -> None:
    _render_icon_section_header("work_history", "Experience", "Add roles and outcomes")
    exp_count = st.number_input("Number of Experience Entries", min_value=0, max_value=10, step=1, key="rb_experience_count")
    count = int(exp_count or 0)
    for idx in range(count):
        with st.expander(f"Experience {idx + 1}", expanded=idx == 0):
            row1 = st.columns(3, gap="small")
            with row1[0]:
                st.text_input("Company", key=f"rb_exp_company_{idx}")
            with row1[1]:
                st.text_input("Role", key=f"rb_exp_role_{idx}")
            with row1[2]:
                st.text_input("Location", key=f"rb_exp_location_{idx}")
            row2 = st.columns(3, gap="small")
            with row2[0]:
                st.text_input("Start Date", key=f"rb_exp_start_{idx}")
            with row2[1]:
                st.text_input("End Date", key=f"rb_exp_end_{idx}")
            with row2[2]:
                st.checkbox("Current Role", key=f"rb_exp_is_current_{idx}")
            st.text_area("Description", key=f"rb_exp_description_{idx}", height=90)
            st.text_area("Bullets (one per line)", key=f"rb_exp_bullets_{idx}", height=90)


def _render_education_inputs() -> None:
    _render_icon_section_header("school", "Education", "Academic history")
    edu_count = st.number_input("Number of Education Entries", min_value=0, max_value=8, step=1, key="rb_education_count")
    count = int(edu_count or 0)
    for idx in range(count):
        with st.expander(f"Education {idx + 1}", expanded=False):
            row1 = st.columns(3, gap="small")
            with row1[0]:
                st.text_input("Institution", key=f"rb_edu_institution_{idx}")
            with row1[1]:
                st.text_input("Degree", key=f"rb_edu_degree_{idx}")
            with row1[2]:
                st.text_input("Field of Study", key=f"rb_edu_field_{idx}")
            row2 = st.columns(3, gap="small")
            with row2[0]:
                st.text_input("Start Date", key=f"rb_edu_start_{idx}")
            with row2[1]:
                st.text_input("End Date", key=f"rb_edu_end_{idx}")
            with row2[2]:
                st.text_input("Grade", key=f"rb_edu_grade_{idx}")
            st.text_input("Location", key=f"rb_edu_location_{idx}")
            st.text_area("Details", key=f"rb_edu_details_{idx}", height=80)


def _render_project_inputs() -> None:
    _render_icon_section_header("terminal", "Projects", "Portfolio-ready implementation work")
    proj_count = st.number_input("Number of Project Entries", min_value=0, max_value=10, step=1, key="rb_project_count")
    count = int(proj_count or 0)
    for idx in range(count):
        with st.expander(f"Project {idx + 1}", expanded=False):
            row1 = st.columns(3, gap="small")
            with row1[0]:
                st.text_input("Project Name", key=f"rb_proj_name_{idx}")
            with row1[1]:
                st.text_input("Role", key=f"rb_proj_role_{idx}")
            with row1[2]:
                st.text_input("Link", key=f"rb_proj_link_{idx}")
            st.text_input("Technologies (comma-separated)", key=f"rb_proj_tech_{idx}")
            st.text_area("Summary", key=f"rb_proj_summary_{idx}", height=80)
            st.text_area("Bullets (one per line)", key=f"rb_proj_bullets_{idx}", height=90)


def _render_certification_inputs() -> None:
    _render_icon_section_header("workspace_premium", "Certifications", "Relevant credentials")
    cert_count = st.number_input("Number of Certification Entries", min_value=0, max_value=12, step=1, key="rb_cert_count")
    count = int(cert_count or 0)
    for idx in range(count):
        with st.expander(f"Certification {idx + 1}", expanded=False):
            row1 = st.columns(3, gap="small")
            with row1[0]:
                st.text_input("Name", key=f"rb_cert_name_{idx}")
            with row1[1]:
                st.text_input("Issuer", key=f"rb_cert_issuer_{idx}")
            with row1[2]:
                st.text_input("Issue Date", key=f"rb_cert_issue_date_{idx}")
            row2 = st.columns(3, gap="small")
            with row2[0]:
                st.text_input("Expiry Date", key=f"rb_cert_expiry_date_{idx}")
            with row2[1]:
                st.text_input("Credential ID", key=f"rb_cert_credential_id_{idx}")
            with row2[2]:
                st.text_input("Credential URL", key=f"rb_cert_credential_url_{idx}")


def _collect_profile_from_state(user_id: int) -> ResumeProfile:
    experiences: list[ResumeExperience] = []
    for idx in range(int(st.session_state.get("rb_experience_count", 0) or 0)):
        bullets = _split_lines(st.session_state.get(f"rb_exp_bullets_{idx}", ""))
        exp = ResumeExperience(
            company=str(st.session_state.get(f"rb_exp_company_{idx}", "") or "").strip(),
            role=str(st.session_state.get(f"rb_exp_role_{idx}", "") or "").strip(),
            location=str(st.session_state.get(f"rb_exp_location_{idx}", "") or "").strip(),
            start_date=str(st.session_state.get(f"rb_exp_start_{idx}", "") or "").strip(),
            end_date=str(st.session_state.get(f"rb_exp_end_{idx}", "") or "").strip(),
            is_current=bool(st.session_state.get(f"rb_exp_is_current_{idx}", False)),
            description=str(st.session_state.get(f"rb_exp_description_{idx}", "") or "").strip(),
            bullets=tuple(bullets),
        )
        if exp.company or exp.role or exp.description or exp.bullets:
            experiences.append(exp)

    educations: list[ResumeEducation] = []
    for idx in range(int(st.session_state.get("rb_education_count", 0) or 0)):
        edu = ResumeEducation(
            institution=str(st.session_state.get(f"rb_edu_institution_{idx}", "") or "").strip(),
            degree=str(st.session_state.get(f"rb_edu_degree_{idx}", "") or "").strip(),
            field_of_study=str(st.session_state.get(f"rb_edu_field_{idx}", "") or "").strip(),
            location=str(st.session_state.get(f"rb_edu_location_{idx}", "") or "").strip(),
            start_date=str(st.session_state.get(f"rb_edu_start_{idx}", "") or "").strip(),
            end_date=str(st.session_state.get(f"rb_edu_end_{idx}", "") or "").strip(),
            grade=str(st.session_state.get(f"rb_edu_grade_{idx}", "") or "").strip(),
            details=str(st.session_state.get(f"rb_edu_details_{idx}", "") or "").strip(),
        )
        if edu.institution or edu.degree or edu.field_of_study:
            educations.append(edu)

    projects: list[ResumeProject] = []
    for idx in range(int(st.session_state.get("rb_project_count", 0) or 0)):
        proj = ResumeProject(
            name=str(st.session_state.get(f"rb_proj_name_{idx}", "") or "").strip(),
            role=str(st.session_state.get(f"rb_proj_role_{idx}", "") or "").strip(),
            summary=str(st.session_state.get(f"rb_proj_summary_{idx}", "") or "").strip(),
            technologies=tuple(_split_csv(st.session_state.get(f"rb_proj_tech_{idx}", ""))),
            link=str(st.session_state.get(f"rb_proj_link_{idx}", "") or "").strip(),
            bullets=tuple(_split_lines(st.session_state.get(f"rb_proj_bullets_{idx}", ""))),
        )
        if proj.name or proj.summary or proj.bullets:
            projects.append(proj)

    certifications: list[ResumeCertification] = []
    for idx in range(int(st.session_state.get("rb_cert_count", 0) or 0)):
        cert = ResumeCertification(
            name=str(st.session_state.get(f"rb_cert_name_{idx}", "") or "").strip(),
            issuer=str(st.session_state.get(f"rb_cert_issuer_{idx}", "") or "").strip(),
            issue_date=str(st.session_state.get(f"rb_cert_issue_date_{idx}", "") or "").strip(),
            expiry_date=str(st.session_state.get(f"rb_cert_expiry_date_{idx}", "") or "").strip(),
            credential_id=str(st.session_state.get(f"rb_cert_credential_id_{idx}", "") or "").strip(),
            credential_url=str(st.session_state.get(f"rb_cert_credential_url_{idx}", "") or "").strip(),
        )
        if cert.name or cert.issuer:
            certifications.append(cert)

    profile = ResumeProfile(
        user_id=int(user_id),
        full_name=str(st.session_state.get("rb_full_name", "") or "").strip(),
        email=str(st.session_state.get("rb_email", "") or "").strip().lower(),
        phone=str(st.session_state.get("rb_phone", "") or "").strip(),
        location=str(st.session_state.get("rb_location", "") or "").strip(),
        linkedin_url=str(st.session_state.get("rb_linkedin_url", "") or "").strip(),
        portfolio_url=str(st.session_state.get("rb_portfolio_url", "") or "").strip(),
        summary=str(st.session_state.get("rb_summary", "") or "").strip(),
        skills=tuple(_split_csv(st.session_state.get("rb_skills_csv", ""))),
        experiences=tuple(experiences),
        educations=tuple(educations),
        projects=tuple(projects),
        certifications=tuple(certifications),
        target_role=str(st.session_state.get("rb_target_role", "") or "").strip(),
        target_job_link=str(st.session_state.get("rb_target_job_link", "") or "").strip(),
        target_job_description=str(st.session_state.get("rb_target_job_description", "") or "").strip(),
    )
    return profile


def _ensure_resume_builder_state(user_id: int, service: ResumeBuilderService) -> None:
    loaded_user_id = int(st.session_state.get("rb_loaded_user_id", 0) or 0)
    if loaded_user_id == int(user_id):
        return

    draft = service.get_profile_draft(user_id=user_id)
    latest = service.get_latest_generated_resume(user_id=user_id)

    if draft is None:
        draft = ResumeProfile(
            user_id=user_id,
            full_name=str(st.session_state.get("user", {}).get("full_name", "") or "").strip(),
            email=str(st.session_state.get("user", {}).get("email", "") or "").strip().lower(),
        )

    _seed_profile_state(draft)
    if latest is not None:
        st.session_state["resume_builder_generated_resume"] = latest.to_dict()
    else:
        st.session_state.setdefault("resume_builder_generated_resume", None)
    st.session_state["rb_loaded_user_id"] = int(user_id)
    st.session_state.setdefault("resume_builder_preview_mode", "Formatted")


def _seed_profile_state(profile: ResumeProfile) -> None:
    for key, value in _build_profile_state_updates(profile).items():
        st.session_state[str(key)] = value


def _build_profile_state_updates(profile: ResumeProfile) -> dict[str, Any]:
    updates: dict[str, Any] = {
        "rb_full_name": profile.full_name,
        "rb_email": profile.email,
        "rb_phone": profile.phone,
        "rb_location": profile.location,
        "rb_linkedin_url": profile.linkedin_url,
        "rb_portfolio_url": profile.portfolio_url,
        "rb_summary": profile.summary,
        "rb_target_role": profile.target_role,
        "rb_target_job_link": profile.target_job_link,
        "rb_target_job_description": profile.target_job_description,
        "rb_skills_csv": ", ".join(profile.skills),
        "rb_experience_count": len(profile.experiences),
        "rb_education_count": len(profile.educations),
        "rb_project_count": len(profile.projects),
        "rb_cert_count": len(profile.certifications),
    }

    for idx, exp in enumerate(profile.experiences):
        updates[f"rb_exp_company_{idx}"] = exp.company
        updates[f"rb_exp_role_{idx}"] = exp.role
        updates[f"rb_exp_location_{idx}"] = exp.location
        updates[f"rb_exp_start_{idx}"] = exp.start_date
        updates[f"rb_exp_end_{idx}"] = exp.end_date
        updates[f"rb_exp_is_current_{idx}"] = exp.is_current
        updates[f"rb_exp_description_{idx}"] = exp.description
        updates[f"rb_exp_bullets_{idx}"] = "\n".join(exp.bullets)

    for idx, edu in enumerate(profile.educations):
        updates[f"rb_edu_institution_{idx}"] = edu.institution
        updates[f"rb_edu_degree_{idx}"] = edu.degree
        updates[f"rb_edu_field_{idx}"] = edu.field_of_study
        updates[f"rb_edu_location_{idx}"] = edu.location
        updates[f"rb_edu_start_{idx}"] = edu.start_date
        updates[f"rb_edu_end_{idx}"] = edu.end_date
        updates[f"rb_edu_grade_{idx}"] = edu.grade
        updates[f"rb_edu_details_{idx}"] = edu.details

    for idx, proj in enumerate(profile.projects):
        updates[f"rb_proj_name_{idx}"] = proj.name
        updates[f"rb_proj_role_{idx}"] = proj.role
        updates[f"rb_proj_summary_{idx}"] = proj.summary
        updates[f"rb_proj_tech_{idx}"] = ", ".join(proj.technologies)
        updates[f"rb_proj_link_{idx}"] = proj.link
        updates[f"rb_proj_bullets_{idx}"] = "\n".join(proj.bullets)

    for idx, cert in enumerate(profile.certifications):
        updates[f"rb_cert_name_{idx}"] = cert.name
        updates[f"rb_cert_issuer_{idx}"] = cert.issuer
        updates[f"rb_cert_issue_date_{idx}"] = cert.issue_date
        updates[f"rb_cert_expiry_date_{idx}"] = cert.expiry_date
        updates[f"rb_cert_credential_id_{idx}"] = cert.credential_id
        updates[f"rb_cert_credential_url_{idx}"] = cert.credential_url

    return updates


def _seed_profile_from_generated_resume(user_id: int, generated_resume: GeneratedResume) -> None:
    snapshot = generated_resume.profile_snapshot
    if not isinstance(snapshot, dict) or not snapshot:
        return
    try:
        profile = ResumeProfile.from_dict(
            {
                **dict(snapshot),
                "user_id": int(user_id),
            }
        )
    except Exception:
        return
    current_pending = st.session_state.get("rb_pending_profile_updates")
    pending_updates = dict(current_pending) if isinstance(current_pending, dict) else {}
    pending_updates.update(_build_profile_state_updates(profile))
    st.session_state["rb_pending_profile_updates"] = pending_updates


def _apply_pending_profile_updates_if_any() -> None:
    pending_updates = st.session_state.pop("rb_pending_profile_updates", None)
    if not isinstance(pending_updates, dict) or not pending_updates:
        return
    for key, value in pending_updates.items():
        st.session_state[str(key)] = value


def _apply_pending_scan_updates_if_any() -> None:
    pending_updates = st.session_state.pop("rb_pending_scan_updates", None)
    if not isinstance(pending_updates, dict) or not pending_updates:
        return
    for key, value in pending_updates.items():
        st.session_state[str(key)] = value


def _render_resume_scan_rag_panel(
    profile: ResumeProfile,
    resume_builder_service: ResumeBuilderService,
) -> None:
    with st.container(key="resume_scan_rag_shell"):
        _render_icon_section_header("upload_file", "Resume Scan Assistant", "Upload your current resume and auto-tailor it to your target job.")
        uploaded_scan = st.file_uploader(
            "Upload Current Resume",
            type=["pdf", "docx", "txt", "md", "png", "jpg", "jpeg", "webp", "bmp", "tiff"],
            key="rb_resume_scan_upload",
            help="Supported: PDF, DOCX, TXT, and scan images.",
        )
        analyze_clicked = st.button(
            "Analyze & Apply Improvements",
            key="rb_scan_analyze_btn",
            use_container_width=True,
        )

        if analyze_clicked:
            if uploaded_scan is None:
                st.error("Upload a resume scan first.")
            else:
                extracted_resume = _extract_uploaded_resume_text(uploaded_scan)
                if not extracted_resume:
                    st.error("Could not extract text from uploaded file. Try a clearer PDF/DOCX/image.")
                else:
                    with st.spinner("Analyzing resume and applying job-focused improvements..."):
                        analysis = resume_builder_service.analyze_resume_scan_with_rag(
                            resume_text=extracted_resume,
                            profile=profile,
                            target_job_description=profile.target_job_description,
                        )
                    st.session_state["rb_scan_analysis"] = analysis
                    updates = _build_scan_updates_from_analysis(profile=profile, analysis=analysis)
                    if updates:
                        st.session_state["rb_pending_scan_updates"] = updates
                        st.success("Improvements applied from your uploaded resume.")
                        st.rerun()
                    st.success("Analysis complete.")

        analysis_payload = st.session_state.get("rb_scan_analysis")
        if isinstance(analysis_payload, dict) and analysis_payload:
            _render_scan_analysis_block(analysis_payload)
            apply_clicked = st.button(
                "Re-Apply Improvements",
                key="rb_scan_apply_btn",
                use_container_width=False,
            )
            if apply_clicked:
                updates = _build_scan_updates_from_analysis(profile=profile, analysis=analysis_payload)
                if not updates:
                    st.info("No updates available from scan analysis.")
                else:
                    st.session_state["rb_pending_scan_updates"] = updates
                    st.success("Applying scan updates...")
                    st.rerun()


def _extract_uploaded_resume_text(uploaded_scan: Any) -> str:
    if uploaded_scan is None:
        return ""
    file_name = str(getattr(uploaded_scan, "name", "") or "").strip().lower()
    raw_bytes = bytes(getattr(uploaded_scan, "getvalue", lambda: b"")() or b"")
    if not raw_bytes:
        return ""

    if file_name.endswith((".txt", ".md", ".log", ".json")):
        return _normalize_extracted_text(raw_bytes.decode("utf-8", errors="ignore"))

    if file_name.endswith(".docx") and DocxDocument is not None:
        try:
            doc = DocxDocument(io.BytesIO(raw_bytes))
            lines = [str(paragraph.text or "").strip() for paragraph in doc.paragraphs]
            joined = "\n".join(line for line in lines if line)
            return _normalize_extracted_text(joined)
        except Exception:
            pass

    if file_name.endswith(".pdf") and pdfplumber is not None:
        try:
            with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
                pages: list[str] = []
                for page in pdf.pages:
                    page_text = str(page.extract_text() or "").strip()
                    if page_text:
                        pages.append(page_text)
                if pages:
                    return _normalize_extracted_text("\n\n".join(pages))
        except Exception:
            pass

    if file_name.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff")) and Image is not None and pytesseract is not None:
        try:
            image = Image.open(io.BytesIO(raw_bytes))
            extracted = str(pytesseract.image_to_string(image) or "").strip()
            return _normalize_extracted_text(extracted)
        except Exception:
            pass

    return _normalize_extracted_text(raw_bytes.decode("utf-8", errors="ignore"))


def _normalize_extracted_text(raw_text: str) -> str:
    lines = [str(line or "").strip() for line in str(raw_text or "").replace("\r\n", "\n").split("\n")]
    filtered = [line for line in lines if line]
    return "\n".join(filtered).strip()


def _build_scan_updates_from_analysis(profile: ResumeProfile, analysis: dict[str, Any]) -> dict[str, Any]:
    updates: dict[str, Any] = {}

    summary_points = analysis.get("summary_points", [])
    if isinstance(summary_points, (list, tuple)):
        normalized_points: list[str] = []
        for item in summary_points:
            clean = str(item or "").strip().lstrip("-").strip()
            if clean:
                normalized_points.append(f"- {clean}")
            if len(normalized_points) >= 6:
                break
        if normalized_points:
            updates["rb_summary"] = "\n".join(normalized_points)

    existing_skills = [str(skill).strip() for skill in profile.skills if str(skill).strip()]
    recommended_skills = analysis.get("recommended_skills", [])
    merged_skills: list[str] = []
    seen: set[str] = set()
    for skill in [*existing_skills, *(recommended_skills if isinstance(recommended_skills, (list, tuple)) else [])]:
        clean = str(skill or "").strip()
        if not clean:
            continue
        lowered = clean.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        merged_skills.append(clean)
        if len(merged_skills) >= 24:
            break
    if merged_skills:
        updates["rb_skills_csv"] = ", ".join(merged_skills)

    extracted_title = str(analysis.get("extracted_title", "") or "").strip()
    if extracted_title and not str(profile.target_role or "").strip():
        updates["rb_target_role"] = extracted_title

    return updates


def _render_scan_analysis_block(analysis: dict[str, Any]) -> None:
    st.caption("Suggested updates based on your uploaded resume and target job.")

    summary_points = analysis.get("summary_points", [])
    if isinstance(summary_points, (list, tuple)) and summary_points:
        st.markdown("**Updated Summary Points:**")
        for point in summary_points[:6]:
            clean = str(point or "").strip().lstrip("-").strip()
            if clean:
                st.write(f"- {clean}")

    recommended_skills = analysis.get("recommended_skills", [])
    if isinstance(recommended_skills, (list, tuple)) and recommended_skills:
        st.markdown("**Skills To Highlight:**")
        chips = " ".join(
            f"<span class='careers-skill-chip'>{str(skill).strip()}</span>"
            for skill in recommended_skills[:18]
            if str(skill).strip()
        )
        if chips:
            st.markdown(chips, unsafe_allow_html=True)

    missing_skills = analysis.get("missing_skills", [])
    if isinstance(missing_skills, (list, tuple)) and missing_skills:
        st.markdown("**Skills To Add For Better Match:**")
        for item in missing_skills[:8]:
            clean = str(item or "").strip()
            if clean:
                st.write(f"- {clean}")


def _render_icon_section_header(icon_name: str, title: str, subtitle: str = "") -> None:
    safe_icon = str(icon_name or "").strip() or "description"
    safe_title = str(title or "").strip()
    safe_subtitle = str(subtitle or "").strip()
    subtitle_html = f'<p class="resume-builder-section-subtitle">{safe_subtitle}</p>' if safe_subtitle else ""
    st.markdown(
        f"""
        <div class="resume-builder-section-head">
            <div class="resume-builder-section-row">
                <span class="resume-builder-section-icon material-symbols-outlined">{safe_icon}</span>
                <h4>{safe_title}</h4>
            </div>
            {subtitle_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _ensure_profile_target_position(profile: ResumeProfile) -> ResumeProfile:
    if str(profile.target_role or "").strip():
        return profile
    for exp in profile.experiences:
        candidate = str(exp.role or "").strip()
        if candidate:
            return ResumeProfile.from_dict(
                {
                    **profile.to_dict(),
                    "target_role": candidate,
                }
            )
    return profile


def _build_draft_profile_markdown(profile: ResumeProfile) -> str:
    lines: list[str] = []
    full_name = str(profile.full_name or "").strip()
    if full_name:
        lines.append(f"# {full_name}")

    contact_parts = [
        str(profile.email or "").strip(),
        str(profile.phone or "").strip(),
        str(profile.location or "").strip(),
        str(profile.linkedin_url or "").strip(),
        str(profile.portfolio_url or "").strip(),
    ]
    contact_line = " | ".join(part for part in contact_parts if part)
    if contact_line:
        lines.append(contact_line)

    if profile.target_role:
        lines.extend(["", "## Target Position", str(profile.target_role).strip()])

    summary = str(profile.summary or "").strip()
    if summary:
        lines.extend(["", "## Professional Summary", summary])

    if profile.skills:
        lines.extend(["", "## Skills", ", ".join(profile.skills)])

    if profile.experiences:
        lines.extend(["", "## Experience"])
        for exp in profile.experiences:
            heading = " - ".join(part for part in [exp.role, exp.company] if str(part or "").strip())
            if heading:
                lines.append(f"**{heading}**")
            date_line = " to ".join(part for part in [exp.start_date, exp.end_date or ("Present" if exp.is_current else "")] if str(part or "").strip())
            if date_line:
                lines.append(date_line)
            bullets = list(exp.bullets)
            if not bullets and exp.description:
                bullets = [str(exp.description).strip()]
            for bullet in bullets[:6]:
                bullet_text = str(bullet or "").strip()
                if bullet_text:
                    lines.append(f"- {bullet_text}")

    if profile.educations:
        lines.extend(["", "## Education"])
        for edu in profile.educations:
            heading = ", ".join(part for part in [edu.degree, edu.field_of_study] if str(part or "").strip())
            if heading:
                lines.append(f"**{heading}**")
            institution = str(edu.institution or "").strip()
            if institution:
                lines.append(institution)

    if profile.projects:
        lines.extend(["", "## Projects"])
        for proj in profile.projects:
            name = str(proj.name or "").strip()
            if name:
                lines.append(f"**{name}**")
            if proj.summary:
                lines.append(str(proj.summary).strip())
            for bullet in list(proj.bullets)[:5]:
                bullet_text = str(bullet or "").strip()
                if bullet_text:
                    lines.append(f"- {bullet_text}")

    if profile.certifications:
        lines.extend(["", "## Certifications"])
        for cert in profile.certifications:
            name = str(cert.name or "").strip()
            issuer = str(cert.issuer or "").strip()
            if name and issuer:
                lines.append(f"- {name} ({issuer})")
            elif name:
                lines.append(f"- {name}")

    return "\n".join(lines).strip()


def _get_generated_resume_from_state() -> GeneratedResume | None:
    raw = st.session_state.get("resume_builder_generated_resume")
    if isinstance(raw, GeneratedResume):
        return raw
    if isinstance(raw, dict):
        try:
            return GeneratedResume.from_dict(raw)
        except Exception:
            return None
    return None


def _render_generated_resume_history(
    generated_resumes: list[GeneratedResume],
    active_resume_id: int = 0,
) -> GeneratedResume | None:
    st.markdown("#### Resume Versions")
    if not generated_resumes:
        st.caption("No generated resume versions yet.")
        return None

    options: list[str] = []
    option_to_id: dict[str, int] = {}
    id_to_resume: dict[int, GeneratedResume] = {}
    for item in generated_resumes:
        safe_id = int(item.id or 0)
        label = _build_resume_history_label(item)
        options.append(label)
        option_to_id[label] = safe_id
        if safe_id > 0:
            id_to_resume[safe_id] = item

    selected_index = 0
    if active_resume_id > 0:
        for idx, label in enumerate(options):
            if option_to_id.get(label, 0) == active_resume_id:
                selected_index = idx
                break

    selected_label = st.selectbox(
        "Select a generated resume",
        options=options,
        index=selected_index,
        key="resume_builder_history_select",
    )
    selected_id = int(option_to_id.get(str(selected_label), 0) or 0)
    selected_resume = id_to_resume.get(selected_id)
    if selected_resume is None and generated_resumes:
        selected_resume = generated_resumes[0]

    if selected_resume is None:
        return None

    cols = st.columns(2, gap="small")
    with cols[0]:
        st.caption(
            "Saved: "
            + (
                _format_resume_timestamp(selected_resume.updated_at)
                or _format_resume_timestamp(selected_resume.created_at)
                or "Unknown"
            )
        )
    with cols[1]:
        st.caption(
            "Model: "
            + (str(selected_resume.model_name or "").strip() or "placeholder")
        )

    load_selected_clicked = st.button(
        "Load Selected Version",
        key="resume_builder_load_selected_btn",
        use_container_width=False,
    )
    if load_selected_clicked:
        return selected_resume
    return None


def _build_resume_history_label(generated_resume: GeneratedResume) -> str:
    title = str(generated_resume.resume_title or "").strip() or "Resume"
    timestamp = _format_resume_timestamp(generated_resume.updated_at) or _format_resume_timestamp(
        generated_resume.created_at
    )
    if timestamp:
        return f"{title} | {timestamp}"
    return title


def _format_resume_timestamp(raw_value: Any) -> str:
    raw_text = str(raw_value or "").strip()
    if not raw_text:
        return ""
    normalized = raw_text.replace("Z", "+00:00")
    parsed = None
    try:
        parsed = datetime.fromisoformat(normalized)
    except Exception:
        parsed = None
    if parsed is None:
        return raw_text[:19]
    return parsed.strftime("%Y-%m-%d %H:%M")


def _split_csv(raw_value: Any) -> list[str]:
    raw = str(raw_value or "").strip()
    if not raw:
        return []
    parts = [item.strip() for item in raw.replace(";", ",").split(",")]
    return [part for part in parts if part]


def _split_lines(raw_value: Any) -> list[str]:
    lines = [str(item).strip() for item in str(raw_value or "").splitlines()]
    return [line for line in lines if line]
