from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import streamlit as st

from src.service.careers_applications_service import CareersApplicationsService


APPLICATION_STATUS_OPTIONS = [
    "saved",
    "applied",
    "interview",
    "offer",
    "rejected",
    "withdrawn",
]


def render_applications_tab(
    user: dict[str, Any],
    applications_service: CareersApplicationsService,
) -> None:
    user_id = int(user.get("id") or 0)
    if user_id <= 0:
        st.info("Log in to view applications.")
        return

    st.markdown("### Application Tracker")
    st.caption("Track application progress and update status or notes.")

    records = applications_service.fetch_tracker_list(user_id=user_id, limit=500, offset=0)
    if not records:
        st.info("No applications yet. Add one from Jobs or Saved tabs.")
        return

    for index, record in enumerate(records):
        job = record.job
        title = _escape(job.title)
        company = _escape(job.company)
        location = _escape(job.location)
        source = _escape(job.source)
        status = str(record.status or "applied").strip().lower() or "applied"
        applied_at = _escape(record.applied_at or "Not set")
        notes = str(record.notes or "").strip()

        st.markdown(
            f"""
            <div class="careers-app-card">
                <div class="careers-app-title">{title}</div>
                <div class="careers-app-meta">{company} | {location} | {source}</div>
                <div class="careers-app-status">Current status: {status}</div>
                <div class="careers-app-date">Applied at: {applied_at}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if _is_valid_job_url(job.job_url):
            st.markdown(f"[View Job Posting]({_escape_link(job.job_url)})")

        select_key = f"careers_app_status_{job.job_id}_{index}"
        note_key = f"careers_app_note_{job.job_id}_{index}"
        action_cols = st.columns([1.2, 2.35, 0.75], gap="small")
        with action_cols[0]:
            selected_status = st.selectbox(
                "Status",
                APPLICATION_STATUS_OPTIONS,
                index=_status_index(status),
                key=select_key,
            )
        with action_cols[1]:
            updated_notes = st.text_input(
                "Notes",
                value=notes,
                key=note_key,
                placeholder="Interview rounds, recruiter updates, offer details...",
            )
        with action_cols[2]:
            if st.button("Update", key=f"careers_app_update_{job.job_id}_{index}", use_container_width=False):
                updated = applications_service.update_application_status(
                    user_id=user_id,
                    job_id=job.job_id,
                    status=selected_status,
                    notes=updated_notes,
                )
                if updated is None:
                    st.error("Could not update this application.")
                else:
                    st.success("Application updated.")
                    st.rerun()

def _status_index(status: str) -> int:
    cleaned = str(status or "").strip().lower()
    for idx, value in enumerate(APPLICATION_STATUS_OPTIONS):
        if value == cleaned:
            return idx
    return 0


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
