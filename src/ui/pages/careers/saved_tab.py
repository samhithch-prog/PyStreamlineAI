from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import streamlit as st

from src.service.careers_applications_service import CareersApplicationsService


APPLICATION_MOVE_OPTIONS = [
    "applied",
    "interview",
    "offer",
    "rejected",
    "withdrawn",
]


def render_saved_tab(
    user: dict[str, Any],
    applications_service: CareersApplicationsService,
) -> None:
    user_id = int(user.get("id") or 0)
    if user_id <= 0:
        st.info("Log in to view saved jobs.")
        return

    st.markdown("### Saved Jobs Queue")
    st.caption("Review saved roles and move relevant ones into your application tracker.")

    saved_jobs = applications_service.fetch_saved_jobs(user_id=user_id, limit=300, offset=0)
    if not saved_jobs:
        st.info("No saved jobs yet. Save jobs from the Jobs tab.")
        return

    for index, saved in enumerate(saved_jobs):
        job = saved.job
        title = _escape(job.title)
        company = _escape(job.company)
        location = _escape(job.location)
        source = _escape(job.source)
        posted_at = _escape(job.posted_at or "Date unavailable")
        st.markdown(
            f"""
            <div class="careers-saved-card">
                <div class="careers-saved-title">{title}</div>
                <div class="careers-saved-meta">{company} | {location} | {source} | {posted_at}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if _is_valid_job_url(job.job_url):
            st.markdown(f"[View Job Posting]({_escape_link(job.job_url)})")

        status_key = f"careers_saved_status_{job.job_id}_{index}"
        note_key = f"careers_saved_note_{job.job_id}_{index}"
        action_cols = st.columns([1.2, 1.95, 1.25], gap="small")
        with action_cols[0]:
            selected_status = st.selectbox(
                "Move As",
                APPLICATION_MOVE_OPTIONS,
                index=0,
                key=status_key,
            )
        with action_cols[1]:
            notes = st.text_input(
                "Notes",
                key=note_key,
                placeholder="Optional note for tracker...",
            )
        with action_cols[2]:
            move_col, remove_col = st.columns(2, gap="small")
            with move_col:
                if st.button("Move", key=f"careers_saved_move_{job.job_id}_{index}", use_container_width=True):
                    record = applications_service.move_saved_job_to_application_tracker(
                        user_id=user_id,
                        job_id=job.job_id,
                        status=selected_status,
                        notes=notes,
                    )
                    if record is None:
                        st.error("Could not move this job to tracker.")
                    else:
                        st.success("Moved to application tracker.")
                        st.rerun()
            with remove_col:
                if st.button("Remove", key=f"careers_saved_remove_{job.job_id}_{index}", use_container_width=True):
                    removed = applications_service.remove_from_saved_jobs(user_id=user_id, job_id=job.job_id)
                    if not removed:
                        st.error("Could not remove this job.")
                    else:
                        st.success("Removed from saved jobs.")
                        st.rerun()

def _escape(value: str) -> str:
    text = str(value or "")
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;").replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    return text


def _escape_link(value: str) -> str:
    return _escape(value).replace(" ", "%20")


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
    path_tokens = (
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
    if any(token in path for token in path_tokens):
        return True
    query_tokens = (
        "jobid=",
        "job_id=",
        "gh_jid=",
        "requisitionid=",
        "requisition_id=",
        "reqid=",
        "postingid=",
        "vacancyid=",
    )
    return any(token in query for token in query_tokens)
