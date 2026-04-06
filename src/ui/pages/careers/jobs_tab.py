from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import re
import time
from typing import Any, Callable
from urllib.parse import quote_plus, urlsplit

import streamlit as st

from src.dto.careers_dto import JobCard, JobFilters, JobMatchResult
from src.service.careers_applications_service import CareersApplicationsService
from src.service.careers_jobs_service import CareersJobsService, EnrichedJobCard


DEFAULT_POSTED_OPTIONS: list[tuple[str, int]] = [
    ("Anytime", 0),
    ("Past 24 hours", 1),
    ("Past 3 days", 3),
    ("Past 7 days", 7),
    ("Past 14 days", 14),
    ("Past 30 days", 30),
]

DEFAULT_WORK_TYPE_OPTIONS = [
    "Full-Time",
    "Part-Time",
    "Contract",
    "W2",
    "C2C",
    "Internship",
    "Remote",
    "Hybrid",
    "Onsite",
]

DEFAULT_LEVEL_OPTIONS = [
    "Intern",
    "Entry",
    "Associate",
    "Mid",
    "Senior",
    "Lead",
    "Manager",
    "Director",
    "Principal",
]

DEFAULT_INDUSTRY_OPTIONS = [
    "Technology",
    "Finance",
    "Healthcare",
    "Retail",
    "Education",
    "Manufacturing",
    "Consulting",
]

DEFAULT_DOMAIN_OPTIONS = [
    "Software Engineering",
    "Data Engineering",
    "Data Science",
    "AI/ML",
    "DevOps",
    "Cloud",
    "Cybersecurity",
    "Product",
]

DEFAULT_RECOMMENDATION_OPTIONS = [
    "All",
    "APPLY",
    "IMPROVE_FIRST",
    "SKIP",
]
LEGACY_SOURCE_FILTER_PLACEHOLDERS = {
    "official careers, greenhouse network, adzuna",
    "official careers, greenhouse network",
    "official careers, adzuna",
}
LEGACY_CERT_FILTER_PLACEHOLDERS = {
    "aws, pmp, cka",
}
IT_STRONG_LOCATION_OPTIONS = [
    "United States of America",
    "Canada",
    "United Kingdom",
    "Germany",
    "Netherlands",
    "Ireland",
    "India",
    "Singapore",
    "Australia",
    "United Arab Emirates",
    "Switzerland",
    "Sweden",
    "Poland",
]
IT_LOCATION_QUERY_MAP: dict[str, str] = {
    "United States of America": "united states of america",
    "Canada": "canada",
    "United Kingdom": "united kingdom",
    "Germany": "germany",
    "Netherlands": "netherlands",
    "Ireland": "ireland",
    "India": "india",
    "Singapore": "singapore",
    "Australia": "australia",
    "United Arab Emirates": "united arab emirates",
    "Switzerland": "switzerland",
    "Sweden": "sweden",
    "Poland": "poland",
}
DEFAULT_ROLE_MATCH_OPTIONS: list[tuple[str, str]] = [
    ("Broad", "broad"),
    ("Balanced", "balanced"),
    ("Strict", "strict"),
]
ROLE_HINTS_LOGIC_VERSION = "v3"
JOB_FETCH_LOADING_ENGINE_NAME = "ZoSwi Match Engine"
JOB_FETCH_LOADING_LABEL = "Hold on - ZoSwi Match Engine is finding live jobs and preparing AI fit insights..."
JOB_FETCH_LOADING_HINT = "We are validating live apply links and ranking the best-fit roles for you."
JOB_FETCH_LOADING_FINAL_HINT = "We are finishing this search now. A few more seconds..."
JOB_FETCH_LOADING_FINAL_SECONDS = 15.0
CAREERS_ADVISOR_SCOPE_MESSAGE = (
    "Share a role or company and I will find jobs. You can add location and 'last 24h' for recent posts."
)
CAREERS_ADVISOR_PRIVACY_GUARD_MESSAGE = (
    "I cannot provide code or handle personal or secret information. Ask only for job search support."
)
CAREERS_ADVISOR_NO_RESULTS_MESSAGE = (
    "I could not find matching jobs yet. Try role or company, add location, or ask for jobs posted in the last 24h."
)
CAREERS_ADVISOR_ACK_MESSAGE = (
    "Ready. Tell me a role or company, plus location if needed, and I will fetch recent jobs."
)
CAREERS_ADVISOR_GREETING_MESSAGE = (
    "Hi. I can help with job search. Share a role or company, and add location or 'last 24h' if you want recent posts."
)
CAREERS_ADVISOR_DEFAULT_RESULT_LIMIT = 8
CAREERS_ADVISOR_MAX_RESULT_LIMIT = 12
CAREERS_ADVISOR_RESULT_FETCH_MULTIPLIER = 10
CAREERS_ADVISOR_MIN_CACHE_HITS = 4
CAREERS_ADVISOR_DEFAULT_RECENT_DAYS = 1
CAREERS_ADVISOR_COMPANY_ALIASES: dict[str, str] = {
    "sales force": "salesforce",
    "salesforce": "salesforce",
    "sap": "sap",
    "jpmc": "jpmorgan chase",
    "jp morgan": "jpmorgan chase",
    "jpmorgan": "jpmorgan chase",
    "bank of america": "bank of america",
    "weill cornell": "weill cornell",
    "l3harris": "l3harris",
    "boeing": "boeing",
    "at&t": "at&t",
    "att": "at&t",
    "comcast": "comcast",
    "dell": "dell",
    "bayer": "bayer",
    "boston scientific": "boston scientific",
    "citi": "citi",
    "capital one": "capital one",
    "pwc": "pwc",
    "ey": "ey",
    "deloitte": "deloitte",
    "kpmg": "kpmg",
    "airbnb": "airbnb",
    "anthropic": "anthropic",
    "coinbase": "coinbase",
    "cloudflare": "cloudflare",
    "datadog": "datadog",
    "dropbox": "dropbox",
    "figma": "figma",
    "mongodb": "mongodb",
    "okta": "okta",
    "stripe": "stripe",
    "duolingo": "duolingo",
    "reddit": "reddit",
}


def render_jobs_tab(
    user: dict[str, Any],
    jobs_service: CareersJobsService,
    applications_service: CareersApplicationsService,
    fetch_jobs_func: Callable[[str, str, int], tuple[list[dict[str, Any]], str]] | None = None,
    default_profile: dict[str, Any] | None = None,
) -> None:
    user_id = int(user.get("id") or 0)
    if user_id <= 0:
        st.info("Log in to use careers jobs.")
        return

    _ensure_jobs_state()
    _refresh_resume_role_hints()
    profile = _build_user_profile(default_profile)
    target_jd = str(st.session_state.get("careers_target_job_description", "") or "").strip()
    resume_role_suggestions = _safe_role_suggestions(st.session_state.get("careers_jobs_role_suggestions"))
    resume_default_role = str(st.session_state.get("careers_jobs_resume_default_role", "") or "").strip()
    # Keep fetch volume stable while hiding advanced controls from the primary UI.
    default_fetch_limit = 120
    max_results = max(
        25,
        min(200, int(st.session_state.get("careers_jobs_fetch_limit", default_fetch_limit) or default_fetch_limit)),
    )
    st.session_state["careers_jobs_fetch_limit"] = int(max_results)
    min_match_score = 0
    st.session_state["careers_jobs_min_score"] = 0
    role_placeholder = "Software Engineer, Data Scientist..."
    if resume_default_role and not str(st.session_state.get("careers_jobs_role_query", "") or "").strip():
        role_placeholder = f"Try: {resume_default_role}"

    st.markdown("### Smart Job Board")
    st.caption("Filter jobs, save roles, and track AI fit in one place.")
    if resume_role_suggestions:
        _render_resume_role_suggestion_row(resume_role_suggestions)
    _render_careers_advisor_panel(
        user_id=user_id,
        jobs_service=jobs_service,
        fetch_jobs_func=fetch_jobs_func,
        profile=profile,
        target_job_description=target_jd,
    )

    with st.form("careers_jobs_filter_form", clear_on_submit=False):
        query_col, location_col = st.columns([2.4, 1.6], gap="small")
        with query_col:
            role_query = st.text_input(
                "Role",
                key="careers_jobs_role_query",
                placeholder=role_placeholder,
            )
        with location_col:
            selected_location_label = st.selectbox(
                "Location",
                IT_STRONG_LOCATION_OPTIONS,
                key="careers_jobs_location_query",
            )
            preferred_location = _location_query_value(selected_location_label)

        filter_cols = st.columns(3, gap="small")
        posted_labels = [label for label, _ in DEFAULT_POSTED_OPTIONS]
        default_posted_idx = _default_posted_index(int(st.session_state.get("careers_jobs_posted_within_days", 0)))
        with filter_cols[0]:
            selected_posted_label = st.selectbox("Posted", posted_labels, index=default_posted_idx)
        with filter_cols[1]:
            selected_work_types = st.multiselect(
                "Work Type",
                DEFAULT_WORK_TYPE_OPTIONS,
                default=st.session_state.get("careers_jobs_work_types", []),
            )
        with filter_cols[2]:
            selected_levels = st.multiselect(
                "Level",
                DEFAULT_LEVEL_OPTIONS,
                default=st.session_state.get("careers_jobs_levels", []),
            )

        secondary_cols = st.columns(4, gap="small")
        with secondary_cols[0]:
            selected_domains = st.multiselect(
                "Domain",
                DEFAULT_DOMAIN_OPTIONS,
                default=st.session_state.get("careers_jobs_domains", []),
            )
        with secondary_cols[1]:
            selected_industries = st.multiselect(
                "Industry",
                DEFAULT_INDUSTRY_OPTIONS,
                default=st.session_state.get("careers_jobs_industries", []),
            )
        with secondary_cols[2]:
            normalized_certifications_value = _normalize_certifications_raw_input(
                str(st.session_state.get("careers_jobs_certifications_raw", "") or "")
            )
            certifications_raw = st.text_input(
                "Certifications",
                value=normalized_certifications_value,
                placeholder="AWS, PMP, CKA",
            )
        with secondary_cols[3]:
            normalized_sources_value = _normalize_sources_raw_input(str(st.session_state.get("careers_jobs_sources_raw", "") or ""))
            sources_raw = st.text_input(
                "Sources",
                value=normalized_sources_value,
            )
            st.caption("Leave blank to search all integrated ATS and official career sources.")

        recommendation_cols = st.columns(2, gap="small")
        with recommendation_cols[0]:
            recommendation_index = max(
                0,
                min(
                    len(DEFAULT_RECOMMENDATION_OPTIONS) - 1,
                    int(st.session_state.get("careers_jobs_recommendation_filter_index", 0) or 0),
                ),
            )
            selected_recommendation = st.selectbox(
                "Recommendation",
                DEFAULT_RECOMMENDATION_OPTIONS,
                index=recommendation_index,
            )
        with recommendation_cols[1]:
            role_mode_lookup = {label: value for label, value in DEFAULT_ROLE_MATCH_OPTIONS}
            current_role_match_mode = str(st.session_state.get("careers_jobs_role_match_mode", "broad") or "broad").strip().lower()
            role_mode_labels = [label for label, _ in DEFAULT_ROLE_MATCH_OPTIONS]
            role_mode_index = 0
            for idx, (_label, mode_value) in enumerate(DEFAULT_ROLE_MATCH_OPTIONS):
                if mode_value == current_role_match_mode:
                    role_mode_index = idx
                    break
            selected_role_mode_label = st.selectbox(
                "Role Match",
                role_mode_labels,
                index=role_mode_index,
            )
            selected_role_match_mode = str(role_mode_lookup.get(selected_role_mode_label, "balanced") or "balanced").strip().lower()

        st.markdown('<div class="careers-find-matches-powered">Powered by ZoSwi</div>', unsafe_allow_html=True)
        submitted = st.form_submit_button(
            "Find My Best Matches",
            key="careers_find_matches_btn",
            use_container_width=False,
        )

    if submitted:
        effective_role_query = str(role_query or "").strip()
        if not effective_role_query:
            effective_role_query = str(st.session_state.get("careers_jobs_resume_default_role", "") or "").strip()
            if effective_role_query:
                st.caption(f"Using role from attached resume: {effective_role_query}")

        posted_within_days = _posted_days_from_label(selected_posted_label)
        st.session_state["careers_jobs_posted_within_days"] = posted_within_days
        st.session_state["careers_jobs_work_types"] = selected_work_types
        st.session_state["careers_jobs_levels"] = selected_levels
        st.session_state["careers_jobs_min_score"] = 0
        st.session_state["careers_jobs_domains"] = selected_domains
        st.session_state["careers_jobs_industries"] = selected_industries
        normalized_certifications_raw = _normalize_certifications_raw_input(certifications_raw)
        st.session_state["careers_jobs_certifications_raw"] = normalized_certifications_raw
        normalized_sources_raw = _normalize_sources_raw_input(sources_raw)
        st.session_state["careers_jobs_sources_raw"] = normalized_sources_raw
        st.session_state["careers_jobs_role_match_mode"] = selected_role_match_mode
        st.session_state["careers_jobs_effective_role_match_mode"] = selected_role_match_mode
        st.session_state["careers_jobs_effective_location"] = preferred_location
        st.session_state["careers_jobs_effective_query"] = effective_role_query
        st.session_state["careers_jobs_auto_relaxed"] = False
        st.session_state["careers_jobs_recommendation_filter_index"] = int(
            DEFAULT_RECOMMENDATION_OPTIONS.index(selected_recommendation)
            if selected_recommendation in DEFAULT_RECOMMENDATION_OPTIONS
            else 0
        )

        loading_started_at = time.time()
        loading_hint_slot = st.empty()
        loading_hint_slot.caption(JOB_FETCH_LOADING_HINT)
        with st.spinner(JOB_FETCH_LOADING_LABEL):
            fetch_role_query = _build_industry_aware_fetch_query(
                role_query=effective_role_query,
                industries=selected_industries,
            )
            raw_jobs, fetch_note = _fetch_raw_jobs(
                fetch_jobs_func=fetch_jobs_func,
                role_query=fetch_role_query,
                preferred_location=preferred_location,
                max_results=max_results,
            )
            if time.time() - loading_started_at >= JOB_FETCH_LOADING_FINAL_SECONDS:
                loading_hint_slot.caption(JOB_FETCH_LOADING_FINAL_HINT)
            st.session_state["careers_jobs_fetch_note"] = fetch_note
            if raw_jobs is not None:
                st.session_state["careers_jobs_last_raw"] = raw_jobs

            filters = JobFilters(
                query=effective_role_query,
                location=preferred_location,
                posted_within_days=posted_within_days,
                domains=tuple(selected_domains),
                work_types=tuple(selected_work_types),
                levels=tuple(selected_levels),
                industries=tuple(selected_industries),
                certifications=tuple(_parse_csv_tokens(normalized_certifications_raw)),
                sources=tuple(_expand_source_aliases(_parse_csv_tokens(normalized_sources_raw))),
                recommendations=tuple(
                    [selected_recommendation] if str(selected_recommendation).upper() in {"APPLY", "IMPROVE_FIRST", "SKIP"} else []
                ),
                role_match_mode=selected_role_match_mode,
                min_match_score=int(min_match_score),
                limit=int(max_results),
                offset=0,
            )

            cache_key = _build_cache_key(
                user_id=user_id,
                role_query=fetch_role_query,
                preferred_location=preferred_location,
                fetch_limit=int(max_results or 0),
                industries=selected_industries,
            )
            if time.time() - loading_started_at >= JOB_FETCH_LOADING_FINAL_SECONDS:
                loading_hint_slot.caption(JOB_FETCH_LOADING_FINAL_HINT)
            enriched_cards = jobs_service.get_enriched_job_cards(
                raw_jobs=st.session_state.get("careers_jobs_last_raw", []),
                filters=filters,
                user_profile=profile,
                target_job_description=target_jd,
                cache_key=cache_key,
                use_cache=True,
                cache_ttl_seconds=300,
            )
            raw_jobs_count = len(st.session_state.get("careers_jobs_last_raw", []) or [])
            enriched_count = len(enriched_cards or [])
            coverage_ratio = float(enriched_count) / float(raw_jobs_count) if raw_jobs_count > 0 else 1.0
            should_soft_relax_for_low_volume = bool(
                isinstance(enriched_cards, list)
                and (
                    (0 < enriched_count <= 8)
                    or (raw_jobs_count >= 45 and coverage_ratio < 0.55)
                )
            )
            if (not enriched_cards or should_soft_relax_for_low_volume) and st.session_state.get("careers_jobs_last_raw"):
                if time.time() - loading_started_at >= JOB_FETCH_LOADING_FINAL_SECONDS:
                    loading_hint_slot.caption(JOB_FETCH_LOADING_FINAL_HINT)
                relax_reasons: list[str] = []
                relaxed_posted_days = int(posted_within_days or 0)
                if int(min_match_score or 0) > 0:
                    relax_reasons.append("minimum match threshold")
                if str(selected_recommendation or "").upper() in {"APPLY", "IMPROVE_FIRST", "SKIP"}:
                    relax_reasons.append("recommendation filter")
                relaxed_filters = JobFilters(
                    query=effective_role_query if should_soft_relax_for_low_volume else "",
                    location=preferred_location if should_soft_relax_for_low_volume else "",
                    posted_within_days=relaxed_posted_days,
                    domains=tuple(selected_domains) if should_soft_relax_for_low_volume else tuple(),
                    work_types=tuple(selected_work_types) if should_soft_relax_for_low_volume else tuple(),
                    levels=tuple(selected_levels) if should_soft_relax_for_low_volume else tuple(),
                    industries=tuple(selected_industries) if should_soft_relax_for_low_volume else tuple(),
                    certifications=tuple(_parse_csv_tokens(normalized_certifications_raw)) if should_soft_relax_for_low_volume else tuple(),
                    sources=tuple(_expand_source_aliases(_parse_csv_tokens(normalized_sources_raw))) if should_soft_relax_for_low_volume else tuple(),
                    recommendations=tuple(),
                    role_match_mode="broad" if should_soft_relax_for_low_volume else selected_role_match_mode,
                    min_match_score=0,
                    limit=int(max_results),
                    offset=0,
                )
                relaxed_cards = jobs_service.get_enriched_job_cards(
                    raw_jobs=st.session_state.get("careers_jobs_last_raw", []),
                    filters=relaxed_filters,
                    user_profile=profile,
                    target_job_description=target_jd,
                    cache_key=f"{cache_key}-relaxed",
                    use_cache=True,
                    cache_ttl_seconds=180,
                )
                relaxed_count = len(relaxed_cards or [])
                relaxed_coverage = float(relaxed_count) / float(raw_jobs_count) if raw_jobs_count > 0 else 1.0
                if should_soft_relax_for_low_volume and (
                    relaxed_count <= 8 or relaxed_coverage < 0.55
                ):
                    broader_filters = JobFilters(
                        query=effective_role_query,
                        location=preferred_location,
                        posted_within_days=relaxed_posted_days,
                        domains=tuple(),
                        work_types=tuple(),
                        levels=tuple(),
                        industries=tuple(selected_industries) if selected_industries else tuple(),
                        certifications=tuple(),
                        sources=tuple(_expand_source_aliases(_parse_csv_tokens(normalized_sources_raw))) if normalized_sources_raw else tuple(),
                        recommendations=tuple(),
                        role_match_mode="broad",
                        min_match_score=0,
                        limit=int(max_results),
                        offset=0,
                    )
                    broader_cards = jobs_service.get_enriched_job_cards(
                        raw_jobs=st.session_state.get("careers_jobs_last_raw", []),
                        filters=broader_filters,
                        user_profile=profile,
                        target_job_description=target_jd,
                        cache_key=f"{cache_key}-broader",
                        use_cache=True,
                        cache_ttl_seconds=180,
                    )
                    if broader_cards and len(broader_cards) > len(relaxed_cards):
                        relaxed_cards = broader_cards
                        relax_reasons.append("broader role matching")
                target_min_results = 25 if int(posted_within_days or 0) == 1 else 0
                if int(posted_within_days or 0) > 0 and (
                    not relaxed_cards or len(relaxed_cards) < max(10, target_min_results)
                ):
                    for fallback_days in (3, 7, 14, 30, 0):
                        if fallback_days != 0 and fallback_days <= int(posted_within_days or 0):
                            continue
                        date_relaxed_filters = JobFilters(
                            query=effective_role_query,
                            location=preferred_location,
                            posted_within_days=int(fallback_days),
                            domains=tuple(),
                            work_types=tuple(),
                            levels=tuple(),
                            industries=tuple(selected_industries) if selected_industries else tuple(),
                            certifications=tuple(),
                            sources=tuple(_expand_source_aliases(_parse_csv_tokens(normalized_sources_raw)))
                            if normalized_sources_raw
                            else tuple(),
                            recommendations=tuple(),
                            role_match_mode="broad",
                            min_match_score=0,
                            limit=int(max_results),
                            offset=0,
                        )
                        date_relaxed_cards = jobs_service.get_enriched_job_cards(
                            raw_jobs=st.session_state.get("careers_jobs_last_raw", []),
                            filters=date_relaxed_filters,
                            user_profile=profile,
                            target_job_description=target_jd,
                            cache_key=f"{cache_key}-date-relax-{fallback_days}",
                            use_cache=True,
                            cache_ttl_seconds=180,
                        )
                        if date_relaxed_cards and len(date_relaxed_cards) > len(relaxed_cards or []):
                            relaxed_cards = date_relaxed_cards
                            if fallback_days == 0:
                                relax_reasons.append(f"posted date window {int(posted_within_days or 0)}d->anytime")
                            else:
                                relax_reasons.append(
                                    f"posted date window {int(posted_within_days or 0)}d->{int(fallback_days)}d"
                                )
                        if relaxed_cards and len(relaxed_cards) >= max(12, target_min_results):
                            break

                if int(posted_within_days or 0) == 1 and (
                    not relaxed_cards or len(relaxed_cards) < max(12, target_min_results)
                ):
                    unknown_date_filters = JobFilters(
                        query=effective_role_query,
                        location=preferred_location,
                        posted_within_days=0,
                        domains=tuple(),
                        work_types=tuple(),
                        levels=tuple(),
                        industries=tuple(selected_industries) if selected_industries else tuple(),
                        certifications=tuple(),
                        sources=tuple(_expand_source_aliases(_parse_csv_tokens(normalized_sources_raw)))
                        if normalized_sources_raw
                        else tuple(),
                        recommendations=tuple(),
                        role_match_mode="broad",
                        min_match_score=0,
                        limit=int(max_results),
                        offset=0,
                    )
                    unknown_date_candidates = jobs_service.get_enriched_job_cards(
                        raw_jobs=st.session_state.get("careers_jobs_last_raw", []),
                        filters=unknown_date_filters,
                        user_profile=profile,
                        target_job_description=target_jd,
                        cache_key=f"{cache_key}-unknown-date",
                        use_cache=True,
                        cache_ttl_seconds=180,
                    )
                    merged_cards = list(relaxed_cards or [])
                    seen_keys: set[tuple[str, str]] = {
                        (
                            str(card.job.job_url or "").strip().lower(),
                            str(card.job.title or "").strip().lower(),
                        )
                        for card in merged_cards
                        if isinstance(card, EnrichedJobCard)
                    }
                    added_unknown = 0
                    ordered_unknown = sorted(
                        [card for card in unknown_date_candidates if isinstance(card, EnrichedJobCard)],
                        key=lambda card: int(card.match.match_score or 0),
                        reverse=True,
                    )
                    for card in ordered_unknown:
                        if str(card.job.posted_at or "").strip():
                            continue
                        dedupe_key = (
                            str(card.job.job_url or "").strip().lower(),
                            str(card.job.title or "").strip().lower(),
                        )
                        if dedupe_key in seen_keys:
                            continue
                        seen_keys.add(dedupe_key)
                        merged_cards.append(card)
                        added_unknown += 1
                        if len(merged_cards) >= max(12, target_min_results):
                            break
                    if added_unknown > 0:
                        relaxed_cards = merged_cards
                        relax_reasons.append(f"included {added_unknown} postings with unavailable posted date")
                if relaxed_cards and (not enriched_cards or len(relaxed_cards) > len(enriched_cards)):
                    enriched_cards = relaxed_cards
                    st.session_state["careers_jobs_effective_role_match_mode"] = "broad"
                    st.session_state["careers_jobs_effective_location"] = preferred_location
                    st.session_state["careers_jobs_effective_query"] = effective_role_query
                    st.session_state["careers_jobs_auto_relaxed"] = True
                    prior_note = str(st.session_state.get("careers_jobs_fetch_note", "") or "").strip()
                    if relax_reasons:
                        reason_text = ", ".join(relax_reasons[:3])
                        relaxed_note = (
                            "Showing closest active matches after auto-relaxing strict filters "
                            f"({reason_text})."
                        )
                    else:
                        relaxed_note = "Showing closest active matches after auto-relaxing strict filters."
                    st.session_state["careers_jobs_fetch_note"] = (
                        f"{prior_note} {relaxed_note}".strip() if prior_note else relaxed_note
                    )
            st.session_state["careers_jobs_last_enriched"] = enriched_cards
        loading_hint_slot.empty()

    enriched_cards = _coerce_enriched_cards(st.session_state.get("careers_jobs_last_enriched", []))

    if not enriched_cards:
        st.info("No matching jobs found for your current filters.")
        return
    enriched_cards = sorted(enriched_cards, key=lambda card: int(card.match.match_score or 0), reverse=True)
    enriched_cards = _diversify_cards_by_source(enriched_cards)
    if not enriched_cards:
        st.info("No matching jobs found for your current filters.")
        return

    _render_jobs_ai_summary(enriched_cards)
    for index, item in enumerate(enriched_cards):
        if not isinstance(item, EnrichedJobCard):
            continue
        _render_job_card(item, index, user_id, applications_service)


def _request_careers_advisor_submit() -> None:
    st.session_state["careers_advisor_submit"] = True


def _default_careers_advisor_messages() -> list[dict[str, Any]]:
    return [
        {
            "role": "assistant",
            "content": (
                "I am ZoSwi Career Advisor. Tell me role, location, and posted window "
                "(example: show Java backend jobs posted in 24h)."
            ),
            "results": [],
            "role_query": "",
            "location_query": "",
            "posted_within_days": 0,
        }
    ]


def _format_careers_advisor_message_html(role: str, content: str) -> str:
    safe_content = _escape(str(content or "").strip()).replace("\n", "<br>")
    normalized_role = str(role or "").strip().lower()
    if normalized_role == "assistant":
        return (
            '<div class="careers-advisor-msg assistant">'
            '<div class="careers-advisor-msg-head"><span>ZoSwi</span></div>'
            f'<div class="careers-advisor-msg-text">{safe_content}</div>'
            "</div>"
        )
    return (
        '<div class="careers-advisor-msg user">'
        '<div class="careers-advisor-msg-head"><span>You</span></div>'
        f'<div class="careers-advisor-msg-text">{safe_content}</div>'
        "</div>"
    )


def _render_careers_advisor_panel(
    *,
    user_id: int,
    jobs_service: CareersJobsService,
    fetch_jobs_func: Callable[[str, str, int], tuple[list[dict[str, Any]], str]] | None,
    profile: dict[str, Any],
    target_job_description: str,
) -> None:
    raw_messages = st.session_state.get("careers_advisor_messages")
    if not isinstance(raw_messages, list) or not raw_messages:
        st.session_state["careers_advisor_messages"] = _default_careers_advisor_messages()
        raw_messages = st.session_state.get("careers_advisor_messages", [])
    messages: list[dict[str, Any]] = [dict(item) for item in raw_messages if isinstance(item, dict)]
    if not messages:
        messages = _default_careers_advisor_messages()
        st.session_state["careers_advisor_messages"] = list(messages)

    if bool(st.session_state.get("careers_advisor_clear_input", False)):
        st.session_state["careers_advisor_input"] = ""
        st.session_state["careers_advisor_clear_input"] = False

    with st.container(key="careers_advisor_widget"):
        advisor_open = bool(st.session_state.get("careers_advisor_open", False))
        if advisor_open:
            with st.container(key="careers_advisor_panel"):
                top_cols = st.columns([7.4, 1.0, 1.0, 1.0], gap="small")
                with top_cols[0]:
                    st.markdown("**ZoSwi Career Advisor**")
                with top_cols[1]:
                    if st.button("\u2212", key="careers_advisor_minimize", help="Minimize"):
                        st.session_state["careers_advisor_open"] = False
                        st.rerun()
                with top_cols[2]:
                    if st.button("\u21ba", key="careers_advisor_reset", help="Reset"):
                        st.session_state["careers_advisor_messages"] = _default_careers_advisor_messages()
                        st.session_state["careers_advisor_pending_prompt"] = ""
                        st.session_state["careers_advisor_submit"] = False
                        st.session_state["careers_advisor_clear_input"] = True
                        st.rerun()
                with top_cols[3]:
                    if st.button("\u00d7", key="careers_advisor_close", help="Close"):
                        st.session_state["careers_advisor_open"] = False
                        st.session_state["careers_advisor_pending_prompt"] = ""
                        st.session_state["careers_advisor_submit"] = False
                        st.rerun()

                with st.container(height=340):
                    for msg in messages:
                        role_value = str(msg.get("role", "assistant")).strip().lower()
                        content_value = str(msg.get("content", "")).strip()
                        if content_value:
                            st.markdown(
                                _format_careers_advisor_message_html(role_value, content_value),
                                unsafe_allow_html=True,
                            )
                        if role_value == "assistant":
                            _render_careers_advisor_result_cards(msg)

                pending_prompt = str(st.session_state.get("careers_advisor_pending_prompt", "") or "").strip()
                is_waiting_for_reply = bool(pending_prompt)
                input_cols = st.columns([6, 1], gap="small")
                with input_cols[0]:
                    message = st.text_input(
                        "Ask ZoSwi Career Advisor",
                        key="careers_advisor_input",
                        placeholder="Ask me anything..",
                        on_change=_request_careers_advisor_submit,
                        label_visibility="collapsed",
                        disabled=is_waiting_for_reply,
                    )
                with input_cols[1]:
                    send = st.button(
                        "\u2191",
                        key="careers_advisor_send",
                        help="Send",
                        use_container_width=True,
                        disabled=is_waiting_for_reply,
                    )

                submit_requested = send or bool(st.session_state.get("careers_advisor_submit", False))
                if submit_requested:
                    st.session_state["careers_advisor_submit"] = False

                if submit_requested and not is_waiting_for_reply and str(message or "").strip():
                    clean_message = str(message or "").strip()
                    messages.append({"role": "user", "content": clean_message})
                    st.session_state["careers_advisor_messages"] = messages
                    st.session_state["careers_advisor_pending_prompt"] = clean_message
                    st.session_state["careers_advisor_clear_input"] = True
                    st.rerun()

                if pending_prompt:
                    with st.spinner("Finding jobs..."):
                        response_payload = _run_careers_advisor_request(
                            user_id=user_id,
                            request_text=pending_prompt,
                            jobs_service=jobs_service,
                            fetch_jobs_func=fetch_jobs_func,
                            profile=profile,
                            target_job_description=target_job_description,
                        )
                    messages.append(
                        {
                            "role": "assistant",
                            "content": _build_careers_advisor_success_message(response_payload),
                            "results": response_payload.get("results", []),
                            "role_query": response_payload.get("role_query", ""),
                            "location_query": response_payload.get("location_query", ""),
                            "posted_within_days": int(response_payload.get("posted_within_days", 0) or 0),
                        }
                    )
                    st.session_state["careers_advisor_messages"] = messages
                    st.session_state["careers_advisor_pending_prompt"] = ""
                    st.rerun()

        fab_icon = "\U0001F4BC" if not advisor_open else "\U0001F5C2\uFE0F"
        fab_help = "Open ZoSwi Career Advisor" if not advisor_open else "Close ZoSwi Career Advisor"
        if st.button(fab_icon, key="careers_advisor_fab", help=fab_help):
            st.session_state["careers_advisor_open"] = not advisor_open
            st.rerun()


def _run_careers_advisor_request(
    *,
    user_id: int,
    request_text: str,
    jobs_service: CareersJobsService,
    fetch_jobs_func: Callable[[str, str, int], tuple[list[dict[str, Any]], str]] | None,
    profile: dict[str, Any],
    target_job_description: str,
) -> dict[str, Any]:
    clean_request = re.sub(r"\s+", " ", str(request_text or "").strip())
    if not clean_request:
        return {
            "message": "Enter a job request first.",
            "results": [],
            "role_query": "",
            "location_query": "",
            "posted_within_days": 0,
        }

    lowered_request = clean_request.lower()
    if _contains_disallowed_careers_request(lowered_request):
        return {
            "message": CAREERS_ADVISOR_PRIVACY_GUARD_MESSAGE,
            "results": [],
            "role_query": "",
            "location_query": "",
            "posted_within_days": 0,
        }
    normalized_request = _normalize_careers_advisor_request(lowered_request)
    if not _looks_like_career_request(normalized_request):
        if _is_careers_greeting_request(normalized_request):
            return {
                "message": CAREERS_ADVISOR_GREETING_MESSAGE,
                "results": [],
                "role_query": "",
                "location_query": "",
                "posted_within_days": 0,
            }
        if _is_careers_acknowledgement_request(normalized_request):
            return {
                "message": CAREERS_ADVISOR_ACK_MESSAGE,
                "results": [],
                "role_query": "",
                "location_query": "",
                "posted_within_days": 0,
            }
        return {
            "message": CAREERS_ADVISOR_SCOPE_MESSAGE,
            "results": [],
            "role_query": "",
            "location_query": "",
            "posted_within_days": 0,
        }

    fallback_role = str(st.session_state.get("careers_jobs_role_query", "") or "").strip()
    if not fallback_role:
        fallback_role = str(st.session_state.get("careers_jobs_resume_default_role", "") or "").strip()
    fallback_location_label = str(
        st.session_state.get("careers_jobs_location_query", IT_STRONG_LOCATION_OPTIONS[0]) or IT_STRONG_LOCATION_OPTIONS[0]
    )
    fallback_location = _location_query_value(fallback_location_label)

    requested_posted_days = _extract_posted_window_days(normalized_request)
    if requested_posted_days <= 0:
        requested_posted_days = CAREERS_ADVISOR_DEFAULT_RECENT_DAYS
    requested_limit = _extract_requested_result_limit(lowered_request)
    requested_location = _extract_requested_location(normalized_request, fallback_location)
    requested_role = _extract_requested_role(normalized_request, requested_location, fallback_role)
    if not requested_role:
        return {
            "message": "Add a target role in your request, for example: Java backend jobs.",
            "results": [],
            "role_query": "",
            "location_query": requested_location,
            "posted_within_days": requested_posted_days,
        }
    requested_role = _normalize_careers_advisor_request(requested_role)

    recent_windows = _build_advisor_recent_windows(requested_posted_days)
    cached_raw = st.session_state.get("careers_jobs_last_raw", [])
    quick_cards: list[EnrichedJobCard] = []
    used_posted_within_days = int(requested_posted_days)
    for window_days in recent_windows:
        filters = JobFilters(
            query=requested_role,
            location=requested_location,
            posted_within_days=int(window_days),
            role_match_mode="balanced",
            limit=max(10, int(requested_limit * 2)),
            offset=0,
        )
        candidate_cards = _build_quick_advisor_cards_from_raw(
            raw_jobs=cached_raw if isinstance(cached_raw, list) else [],
            jobs_service=jobs_service,
            filters=filters,
            user_profile=profile,
            target_job_description=str(target_job_description or ""),
            limit=requested_limit,
        )
        if candidate_cards:
            quick_cards = list(candidate_cards)
            used_posted_within_days = int(window_days)
        if len(candidate_cards) >= min(CAREERS_ADVISOR_MIN_CACHE_HITS, requested_limit):
            break
    fetch_note = ""
    normalized_cards = list(quick_cards)

    if len(normalized_cards) < min(CAREERS_ADVISOR_MIN_CACHE_HITS, requested_limit):
        fetch_limit = max(12, min(48, int(requested_limit * 2)))
        raw_jobs, fetch_note = _fetch_raw_jobs(
            fetch_jobs_func=fetch_jobs_func,
            role_query=requested_role,
            preferred_location=requested_location,
            max_results=fetch_limit,
            fast_mode=True,
        )
        if not isinstance(raw_jobs, list):
            raw_jobs = []
        if raw_jobs:
            st.session_state["careers_jobs_last_raw"] = raw_jobs
        normalized_cards = []
        for window_days in recent_windows:
            filters = JobFilters(
                query=requested_role,
                location=requested_location,
                posted_within_days=int(window_days),
                role_match_mode="balanced",
                limit=max(10, int(requested_limit * 2)),
                offset=0,
            )
            candidate_cards = _build_quick_advisor_cards_from_raw(
                raw_jobs=raw_jobs,
                jobs_service=jobs_service,
                filters=filters,
                user_profile=profile,
                target_job_description=str(target_job_description or ""),
                limit=requested_limit,
            )
            if candidate_cards:
                normalized_cards = list(candidate_cards)
                used_posted_within_days = int(window_days)
            if len(candidate_cards) >= min(CAREERS_ADVISOR_MIN_CACHE_HITS, requested_limit):
                break
        if not normalized_cards and quick_cards:
            normalized_cards = list(quick_cards)

    if not normalized_cards and _is_company_only_query(requested_role):
        company_term = _extract_primary_company_term(requested_role) or _normalize_careers_advisor_request(requested_role)
        company_rows: list[dict[str, Any]] = []
        for company_query in _build_company_boost_queries(company_term):
            raw_jobs, fetch_note = _fetch_raw_jobs(
                fetch_jobs_func=fetch_jobs_func,
                role_query=company_query,
                preferred_location=requested_location,
                max_results=max(12, min(48, int(requested_limit * 2))),
                fast_mode=False,
            )
            if not isinstance(raw_jobs, list):
                raw_jobs = []
            if raw_jobs:
                company_rows.extend(raw_jobs)
                company_rows = _dedupe_jobs(company_rows)
            if len(company_rows) >= max(12, int(requested_limit * 2)):
                break
        company_rows = _filter_rows_for_company_terms(company_rows, company_term)
        if company_rows:
            st.session_state["careers_jobs_last_raw"] = company_rows
            for window_days in recent_windows:
                company_filters = JobFilters(
                    query=company_term,
                    location=requested_location,
                    posted_within_days=int(window_days),
                    role_match_mode="broad",
                    limit=max(10, int(requested_limit * 2)),
                    offset=0,
                )
                candidate_cards = _build_quick_advisor_cards_from_raw(
                    raw_jobs=company_rows,
                    jobs_service=jobs_service,
                    filters=company_filters,
                    user_profile=profile,
                    target_job_description=str(target_job_description or ""),
                    limit=requested_limit,
                )
                if candidate_cards:
                    normalized_cards = list(candidate_cards)
                    used_posted_within_days = int(window_days)
                if len(candidate_cards) >= min(CAREERS_ADVISOR_MIN_CACHE_HITS, requested_limit):
                    break

    if normalized_cards:
        if used_posted_within_days > int(requested_posted_days):
            message = (
                f"Expanded recent window from {_advisor_recent_days_label(requested_posted_days)} "
                f"to {_advisor_recent_days_label(used_posted_within_days)} to return more jobs."
            )
        else:
            message = ""
    else:
        fetch_note_clean = str(fetch_note or "").strip().lower()
        if fetch_note_clean.startswith("job fetch failed"):
            message = "Could not fetch jobs right now. Try again."
        else:
            message = CAREERS_ADVISOR_NO_RESULTS_MESSAGE
    return {
        "message": message,
        "results": [item.to_dict() for item in normalized_cards if isinstance(item, EnrichedJobCard)],
        "role_query": requested_role,
        "location_query": requested_location,
        "posted_within_days": int(used_posted_within_days),
    }


def _render_careers_advisor_result_cards(raw_payload: dict[str, Any]) -> None:
    results = _coerce_enriched_cards(raw_payload.get("results", []) if isinstance(raw_payload, dict) else [])
    if not results:
        return
    for idx, card in enumerate(results, start=1):
        if not isinstance(card, EnrichedJobCard):
            continue
        title = _escape(str(card.job.title or "").strip() or "Untitled role")
        company = _escape(str(card.job.company or "").strip() or "Unknown company")
        location = _escape(_normalize_job_location_for_display(str(card.job.location or "").strip()))
        posted = _escape(_advisor_posted_label(str(card.job.posted_at or "").strip()))
        source = _escape(str(card.job.source or "").strip() or "External source")
        score = int(card.match.match_score or 0)
        job_url = str(card.job.job_url or "").strip()
        link_html = ""
        if job_url:
            safe_link = _escape_link(job_url)
            link_html = (
                f'<a class="careers-advisor-link" href="{safe_link}" target="_blank" rel="noopener noreferrer">'
                "Open Job</a>"
            )
        st.markdown(
            f"""
            <div class="careers-advisor-result-card">
                <div class="careers-advisor-result-head">
                    <div class="careers-advisor-result-title">{idx}. {title}</div>
                    <div class="careers-advisor-result-score">ZoSwi Match {score}%</div>
                </div>
                <div class="careers-advisor-result-meta">{company} | {location} | {posted}</div>
                <div class="careers-advisor-result-source">{source}</div>
                {link_html}
            </div>
            """,
            unsafe_allow_html=True,
        )


def _build_careers_advisor_success_message(raw_payload: dict[str, Any]) -> str:
    if not isinstance(raw_payload, dict):
        return CAREERS_ADVISOR_NO_RESULTS_MESSAGE
    explicit_message = str(raw_payload.get("message", "") or "").strip()
    if explicit_message:
        return explicit_message
    results = _coerce_enriched_cards(raw_payload.get("results", []))
    result_count = len(results)
    if result_count <= 0:
        return CAREERS_ADVISOR_NO_RESULTS_MESSAGE
    role_query = str(raw_payload.get("role_query", "") or "").strip()
    posted_within_days = int(raw_payload.get("posted_within_days", 0) or 0)
    base = f"Found {result_count} jobs"
    if role_query:
        base += f" for {role_query}"
    if posted_within_days == 1:
        base += " posted in the last 24h"
    elif posted_within_days > 1:
        base += f" posted in the last {posted_within_days} days"
    return f"{base}."


def _build_quick_advisor_cards_from_raw(
    *,
    raw_jobs: list[dict[str, Any]],
    jobs_service: CareersJobsService,
    filters: JobFilters,
    user_profile: dict[str, Any],
    target_job_description: str,
    limit: int,
) -> list[EnrichedJobCard]:
    if not isinstance(raw_jobs, list) or not raw_jobs:
        return []
    try:
        normalized_jobs = jobs_service.normalize_jobs(raw_jobs)
        filtered_jobs = jobs_service.filter_jobs(normalized_jobs, filters)
    except Exception:
        return []
    if not filtered_jobs:
        return []

    max_candidates = max(10, min(80, int(limit or CAREERS_ADVISOR_DEFAULT_RESULT_LIMIT) * 3))
    candidate_cards: list[EnrichedJobCard] = []
    for job in filtered_jobs[:max_candidates]:
        try:
            score = int(
                jobs_service.compute_ai_match_score_placeholder(
                    job=job,
                    user_profile=user_profile,
                    target_job_description=target_job_description,
                )
                or 0
            )
        except Exception:
            score = 0
        if score >= 74:
            recommendation = "APPLY"
        elif score >= 46:
            recommendation = "IMPROVE_FIRST"
        else:
            recommendation = "SKIP"
        candidate_cards.append(
            EnrichedJobCard(
                job=job,
                match=JobMatchResult(
                    job_id=str(job.job_id or "").strip(),
                    match_score=max(0, min(100, int(score))),
                    why_fit="",
                    ai_summary="",
                    why_fit_points=tuple(),
                    missing_skills=tuple(),
                    recommendation=recommendation,
                    improvement_suggestions=tuple(),
                    computed_at="",
                    analysis_timestamp="",
                    analysis_source="quick",
                ),
            )
        )
    if not candidate_cards:
        return []
    candidate_cards = sorted(
        candidate_cards,
        key=lambda item: (int(item.match.match_score or 0), _advisor_posted_sort_value(item.job.posted_at)),
        reverse=True,
    )
    candidate_cards = _diversify_cards_by_source(candidate_cards)
    return candidate_cards[: max(1, int(limit or CAREERS_ADVISOR_DEFAULT_RESULT_LIMIT))]


def _advisor_posted_sort_value(posted_at: str) -> float:
    parsed = CareersJobsService._parse_posted_at(str(posted_at or "").strip())
    if parsed is None:
        return 0.0
    return float(parsed.timestamp())


def _looks_like_career_request(lowered_request: str) -> bool:
    clean = str(lowered_request or "").strip().lower()
    if not clean:
        return False
    career_terms = {
        "job",
        "jobs",
        "role",
        "roles",
        "career",
        "careers",
        "opening",
        "openings",
        "position",
        "positions",
        "hiring",
        "apply",
        "posted",
        "recent",
    }
    role_terms = {
        "engineer",
        "developer",
        "scientist",
        "analyst",
        "manager",
        "architect",
        "devops",
        "frontend",
        "backend",
        "full stack",
        "data",
        "cloud",
        "security",
        "qa",
        "intern",
        "java",
        "python",
        "react",
    }
    if any(token in clean for token in career_terms):
        return True
    if any(token in clean for token in role_terms):
        return True
    if _contains_known_company_term(clean):
        return True
    tokens = [token for token in re.findall(r"[a-z0-9+#/.]+", clean) if token]
    if not tokens:
        return False
    conversational_tokens = {
        "hi",
        "hello",
        "hey",
        "thanks",
        "thank",
        "ok",
        "okay",
        "yo",
        "help",
        "what",
        "why",
        "how",
        "who",
        "when",
        "where",
    }
    meaningful = [token for token in tokens if token not in conversational_tokens]
    if not meaningful:
        return False
    return len(meaningful) <= 3 and any(len(token) >= 3 for token in meaningful)


def _is_careers_acknowledgement_request(text: str) -> bool:
    clean = re.sub(r"\s+", " ", str(text or "").strip().lower())
    if not clean:
        return False
    return clean in {
        "k",
        "kk",
        "ok",
        "okay",
        "alright",
        "all right",
        "got it",
        "cool",
        "thanks",
        "thank you",
        "thx",
    }


def _is_careers_greeting_request(text: str) -> bool:
    clean = re.sub(r"\s+", " ", str(text or "").strip().lower())
    if not clean:
        return False
    return clean in {
        "hi",
        "hello",
        "hey",
        "hiya",
        "good morning",
        "good afternoon",
        "good evening",
    }


def _contains_disallowed_careers_request(lowered_request: str) -> bool:
    clean = str(lowered_request or "").strip().lower()
    if not clean:
        return False
    code_pattern = re.compile(
        r"\b(write|generate|create|build|debug|fix|show)\b.{0,30}\b(code|script|program|function|algorithm|regex|sql query)\b",
        flags=re.IGNORECASE,
    )
    if code_pattern.search(clean):
        return True
    personal_markers = (
        "password",
        "otp",
        "one time code",
        "social security",
        "ssn",
        "credit card",
        "cvv",
        "bank account",
        "api key",
        "secret key",
        "private key",
        "date of birth",
        "dob",
    )
    return any(marker in clean for marker in personal_markers)


def _extract_requested_result_limit(lowered_request: str) -> int:
    clean = str(lowered_request or "").strip().lower()
    if not clean:
        return CAREERS_ADVISOR_DEFAULT_RESULT_LIMIT
    explicit_match = re.search(
        r"\b(?:top|show|find|get|list)\s+(\d{1,2})\s*(?:jobs?|roles?|results?)\b",
        clean,
    )
    if explicit_match:
        try:
            requested = int(explicit_match.group(1))
        except Exception:
            requested = CAREERS_ADVISOR_DEFAULT_RESULT_LIMIT
        return max(1, min(CAREERS_ADVISOR_MAX_RESULT_LIMIT, requested))
    return CAREERS_ADVISOR_DEFAULT_RESULT_LIMIT


def _extract_posted_window_days(lowered_request: str) -> int:
    clean = str(lowered_request or "").strip().lower()
    if not clean:
        return 0
    if re.search(r"\b(24\s*(h|hr|hrs|hour|hours)|past day|last day|today)\b", clean):
        return 1
    if "recently posted" in clean or "recent postings" in clean:
        return 1
    days_match = re.search(r"\b(?:past|last|within)\s+(\d{1,2})\s*days?\b", clean)
    if days_match:
        return _normalize_supported_posted_window_days(int(days_match.group(1) or 0))
    weeks_match = re.search(r"\b(?:past|last|within)\s+(\d{1,2})\s*weeks?\b", clean)
    if weeks_match:
        return _normalize_supported_posted_window_days(int(weeks_match.group(1) or 0) * 7)
    months_match = re.search(r"\b(?:past|last|within)\s+(\d{1,2})\s*months?\b", clean)
    if months_match:
        return _normalize_supported_posted_window_days(int(months_match.group(1) or 0) * 30)
    return 0


def _normalize_supported_posted_window_days(days: int) -> int:
    safe_days = max(0, int(days or 0))
    if safe_days <= 0:
        return 0
    if safe_days <= 1:
        return 1
    if safe_days <= 3:
        return 3
    if safe_days <= 7:
        return 7
    if safe_days <= 14:
        return 14
    return 30


def _build_advisor_recent_windows(base_days: int) -> list[int]:
    normalized_days = _normalize_supported_posted_window_days(int(base_days or 0))
    if normalized_days <= 0:
        normalized_days = CAREERS_ADVISOR_DEFAULT_RECENT_DAYS
    fallback_map: dict[int, list[int]] = {
        1: [1, 3, 7],
        3: [3, 7, 14],
        7: [7, 14, 30],
        14: [14, 30],
        30: [30],
    }
    values = fallback_map.get(normalized_days, [normalized_days])
    deduped: list[int] = []
    seen: set[int] = set()
    for item in values:
        safe = _normalize_supported_posted_window_days(int(item or 0))
        if safe <= 0 or safe in seen:
            continue
        seen.add(safe)
        deduped.append(safe)
    return deduped or [CAREERS_ADVISOR_DEFAULT_RECENT_DAYS]


def _advisor_recent_days_label(days: int) -> str:
    safe_days = _normalize_supported_posted_window_days(int(days or 0))
    if safe_days <= 1:
        return "24h"
    return f"{safe_days}d"


def _extract_requested_location(lowered_request: str, fallback_location: str) -> str:
    clean = re.sub(r"\s+", " ", str(lowered_request or "").strip().lower())
    if not clean:
        return str(fallback_location or "").strip()
    if re.search(r"\bremote\b", clean):
        return "remote"

    for label, query_value in IT_LOCATION_QUERY_MAP.items():
        label_lower = str(label or "").strip().lower()
        if label_lower and re.search(rf"\b{re.escape(label_lower)}\b", clean):
            return str(query_value or "").strip()

    location_aliases: dict[str, str] = {
        "usa": "united states of america",
        "us": "united states of america",
        "u.s.": "united states of america",
        "united states": "united states of america",
        "uk": "united kingdom",
        "u.k.": "united kingdom",
        "uae": "united arab emirates",
    }
    for alias, normalized in location_aliases.items():
        if re.search(rf"\b{re.escape(alias)}\b", clean):
            return normalized

    in_match = re.search(r"\bin\s+([a-z][a-z\s,&./-]{1,40})", clean)
    if in_match:
        candidate = str(in_match.group(1) or "").strip()
        candidate = re.split(
            r"\b(job|jobs|role|roles|position|positions|posted|within|past|last|top|show|find|get)\b",
            candidate,
            maxsplit=1,
        )[0]
        candidate = re.sub(r"[^a-z\s,&./-]", " ", candidate)
        candidate = re.sub(r"\s+", " ", candidate).strip(" ,.-")
        if candidate:
            return candidate
    return str(fallback_location or "").strip()


def _extract_requested_role(lowered_request: str, requested_location: str, fallback_role: str) -> str:
    clean = str(lowered_request or "").strip().lower()
    if not clean:
        return str(fallback_role or "").strip()
    tokens = re.findall(r"[a-z0-9+#/.]+", clean)
    stop_tokens = {
        "show",
        "find",
        "get",
        "list",
        "search",
        "looking",
        "look",
        "for",
        "me",
        "my",
        "please",
        "can",
        "you",
        "need",
        "want",
        "job",
        "jobs",
        "role",
        "roles",
        "career",
        "careers",
        "opening",
        "openings",
        "position",
        "positions",
        "posted",
        "posting",
        "postings",
        "recent",
        "recently",
        "past",
        "last",
        "within",
        "hour",
        "hours",
        "day",
        "days",
        "week",
        "weeks",
        "month",
        "months",
        "today",
        "latest",
        "new",
        "newest",
        "top",
        "all",
        "any",
        "only",
        "in",
        "at",
        "from",
        "to",
        "the",
        "a",
        "an",
        "with",
        "without",
    }
    location_tokens = set(re.findall(r"[a-z0-9]+", str(requested_location or "").lower()))
    role_tokens: list[str] = []
    for token in tokens:
        if not token:
            continue
        if token in stop_tokens:
            continue
        if token in location_tokens:
            continue
        if re.fullmatch(r"\d+[a-z]*", token):
            continue
        role_tokens.append(token)
    extracted_role = re.sub(r"\s+", " ", " ".join(role_tokens)).strip()
    if not extracted_role:
        return str(fallback_role or "").strip()
    if extracted_role in {"job", "jobs", "role", "roles"}:
        return str(fallback_role or "").strip()
    normalized_role = _normalize_careers_advisor_request(extracted_role)
    primary_company = _extract_primary_company_term(normalized_role)
    if primary_company:
        return primary_company
    return normalized_role


def _normalize_careers_advisor_request(text: str) -> str:
    normalized = re.sub(r"\s+", " ", str(text or "").strip().lower())
    if not normalized:
        return ""
    aliases = sorted(
        CAREERS_ADVISOR_COMPANY_ALIASES.items(),
        key=lambda item: len(str(item[0] or "")),
        reverse=True,
    )
    for alias, canonical in aliases:
        alias_clean = str(alias or "").strip().lower()
        canonical_clean = str(canonical or "").strip().lower()
        if not alias_clean or not canonical_clean:
            continue
        pattern = rf"(?<![a-z0-9]){re.escape(alias_clean)}(?![a-z0-9])"
        source_text = normalized

        def _replace_alias(match: re.Match[str]) -> str:
            start = int(match.start())
            if source_text[start : start + len(canonical_clean)] == canonical_clean:
                return str(match.group(0) or "")
            return canonical_clean

        normalized = re.sub(pattern, _replace_alias, source_text)
    return re.sub(r"\s+", " ", normalized).strip()


def _contains_known_company_term(text: str) -> bool:
    clean = str(text or "").strip().lower()
    if not clean:
        return False
    candidate_terms = {
        str(term or "").strip().lower()
        for term in (
            list(CAREERS_ADVISOR_COMPANY_ALIASES.keys()) + list(CAREERS_ADVISOR_COMPANY_ALIASES.values())
        )
    }
    for term in sorted(candidate_terms, key=len, reverse=True):
        if not term:
            continue
        pattern = rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])"
        if re.search(pattern, clean):
            return True
    return False


def _extract_primary_company_term(text: str) -> str:
    clean = _normalize_careers_advisor_request(text)
    if not clean:
        return ""
    best_term = ""
    best_start = -1
    for alias, canonical in CAREERS_ADVISOR_COMPANY_ALIASES.items():
        alias_clean = str(alias or "").strip().lower()
        canonical_clean = str(canonical or "").strip().lower()
        if not alias_clean or not canonical_clean:
            continue
        for needle in (canonical_clean, alias_clean):
            pattern = rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])"
            match = re.search(pattern, clean)
            if match is None:
                continue
            start = int(match.start())
            if best_start < 0 or start < best_start:
                best_start = start
                best_term = canonical_clean
            elif start == best_start and len(canonical_clean) > len(best_term):
                best_term = canonical_clean
    return best_term


def _build_company_boost_queries(company_term: str) -> list[str]:
    primary = _extract_primary_company_term(company_term) or _normalize_careers_advisor_request(company_term)
    if not primary:
        return []
    candidates = [
        primary,
        f"{primary} jobs",
        f"{primary} careers",
        f"software engineer {primary}",
    ]
    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        clean_candidate = re.sub(r"\s+", " ", str(candidate or "").strip())
        key = clean_candidate.lower()
        if not clean_candidate or key in seen:
            continue
        seen.add(key)
        deduped.append(clean_candidate)
    return deduped


def _company_search_terms(company_term: str) -> list[str]:
    normalized = _normalize_careers_advisor_request(company_term)
    if not normalized:
        return []
    canonical_hits: set[str] = set()
    for alias, canonical in CAREERS_ADVISOR_COMPANY_ALIASES.items():
        alias_clean = str(alias or "").strip().lower()
        canonical_clean = str(canonical or "").strip().lower()
        if not alias_clean or not canonical_clean:
            continue
        alias_pattern = rf"(?<![a-z0-9]){re.escape(alias_clean)}(?![a-z0-9])"
        canonical_pattern = rf"(?<![a-z0-9]){re.escape(canonical_clean)}(?![a-z0-9])"
        if re.search(alias_pattern, normalized) or re.search(canonical_pattern, normalized):
            canonical_hits.add(canonical_clean)
    if not canonical_hits:
        primary = _extract_primary_company_term(normalized)
        if primary:
            canonical_hits.add(primary)
    terms: set[str] = set()
    for canonical in canonical_hits:
        terms.add(canonical)
        for alias, mapped in CAREERS_ADVISOR_COMPANY_ALIASES.items():
            mapped_clean = str(mapped or "").strip().lower()
            alias_clean = str(alias or "").strip().lower()
            if mapped_clean == canonical and alias_clean:
                terms.add(alias_clean)
    if not terms and normalized:
        terms.add(normalized)
    return sorted((term for term in terms if term), key=len, reverse=True)


def _filter_rows_for_company_terms(rows: list[dict[str, Any]], company_term: str) -> list[dict[str, Any]]:
    if not isinstance(rows, list) or not rows:
        return []
    terms = _company_search_terms(company_term)
    if not terms:
        return list(rows)
    filtered: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        blob = _normalize_careers_advisor_request(
            " ".join(
                [
                    str(item.get("title", "") or ""),
                    str(item.get("company", "") or ""),
                    str(item.get("source", "") or ""),
                    str(item.get("job_url", item.get("apply_url", "")) or ""),
                ]
            )
        )
        if not blob:
            continue
        if any(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", blob) for term in terms):
            filtered.append(dict(item))
    return filtered


def _is_company_only_query(role_query: str) -> bool:
    clean = _normalize_careers_advisor_request(role_query)
    if not clean:
        return False
    role_markers = {
        "engineer",
        "developer",
        "scientist",
        "analyst",
        "manager",
        "architect",
        "intern",
        "devops",
        "frontend",
        "backend",
        "full stack",
        "qa",
        "cloud",
        "security",
    }
    if any(marker in clean for marker in role_markers):
        return False
    return bool(_extract_primary_company_term(clean))


def _advisor_posted_label(posted_at: str) -> str:
    posted_text = str(posted_at or "").strip()
    if not posted_text:
        return "Posted date unavailable"
    parsed_posted_at = CareersJobsService._parse_posted_at(posted_text)
    if parsed_posted_at is None:
        return posted_text
    age_seconds = max(0.0, (datetime.now(timezone.utc) - parsed_posted_at).total_seconds())
    age_hours = age_seconds / 3600.0
    if age_hours <= 1.5:
        return "Posted within 1h"
    if age_hours <= 24.5:
        return f"Posted {int(max(1, round(age_hours)))}h ago"
    age_days = age_hours / 24.0
    if age_days <= 30.5:
        return f"Posted {int(max(1, round(age_days)))}d ago"
    return parsed_posted_at.strftime("Posted %b %d, %Y")


def _render_job_card(
    item: EnrichedJobCard,
    index: int,
    user_id: int,
    applications_service: CareersApplicationsService,
) -> None:
    job = item.job
    match = item.match
    title = _escape(job.title)
    company = _escape(job.company)
    location = _escape(_normalize_job_location_for_display(job.location))
    raw_location = str(job.location or "").strip().lower()
    location_unverified = raw_location in {
        "",
        "location not listed",
        "location unavailable",
        "unknown",
        "n/a",
        "not specified",
    }
    source = _escape(job.source)
    posted = _escape(job.posted_at or "Date unavailable")
    work_type = _escape(job.work_type or "Not specified")
    level = _escape(job.level or "Not specified")
    industry = _escape(job.industry or "Not specified")
    ai_summary = _escape(match.ai_summary or "AI summary unavailable.")
    why_fit_points = [str(point).strip() for point in list(match.why_fit_points)[:3] if str(point).strip()]
    if not why_fit_points:
        fallback = _truncate_text(str(match.why_fit or "").replace("- ", " ").strip(), 160)
        if fallback:
            why_fit_points = [fallback]
    if not why_fit_points:
        why_fit_points = ["Role aligns with your profile context."]
    deduped_points: list[str] = []
    seen_points: set[str] = set()
    for point in why_fit_points:
        key = re.sub(r"\s+", " ", str(point or "").strip()).lower()
        if key in seen_points:
            continue
        seen_points.add(key)
        deduped_points.append(point)
    why_fit_points = deduped_points[:3]
    recommendation_label, recommendation_class = _recommendation_style(
        recommendation=str(match.recommendation or "").strip().upper(),
        score=int(match.match_score or 0),
    )
    recommendation_tooltip = _recommendation_tooltip(
        recommendation_label,
        score=int(match.match_score or 0),
        missing_skills_count=len(match.missing_skills),
    )
    match_tooltip = (
        f"ZoSwi Match {int(match.match_score)}% estimates fit using role relevance, "
        "skill overlap, and profile-to-job context alignment."
    )
    recent_posted_badge_html = _build_recent_posted_badge_html(job.posted_at)
    verified_url = _is_valid_job_url(job.job_url)
    contact_emails = _extract_contact_emails(job.description, max_items=2)
    why_fit_html = "".join(f"<li>{_escape(point)}</li>" for point in why_fit_points[:3])
    verified_badge_html = ""
    if verified_url:
        verified_badge_html = (
            '<div class="careers-job-verified" title="ZoSwi Verified the source" aria-label="ZoSwi Verified the source">'
            '<span class="careers-job-verified-icon" aria-hidden="true">'
            '<svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">'
            '<path d="M12 2.4 4.5 5.5v5.8c0 5.2 3.2 9.9 7.5 11.7 4.3-1.8 7.5-6.5 7.5-11.7V5.5L12 2.4zm3.9 7.2-4.4 4.4a1 1 0 0 1-1.4 0l-2.1-2.1a1 1 0 1 1 1.4-1.4l1.4 1.4 3.7-3.7a1 1 0 0 1 1.4 1.4z"></path>'
            "</svg>"
            "</span>"
            "<span>ZoSwi</span>"
            "</div>"
        )

    card_html = (
        f'<div class="careers-job-card">'
        f'<div class="careers-job-head">'
        f'<div>'
        f'<div class="careers-job-title">{title}</div>'
        f'<div class="careers-job-meta">{company} | {location} | {source} | {posted}</div>'
        f"</div>"
        f'<div class="careers-job-badge-wrap">'
        f'<div class="careers-job-badge" title="{_escape(match_tooltip)}" aria-label="{_escape(match_tooltip)}">'
        f"ZoSwi Match {int(match.match_score)}%"
        f"</div>"
        f'<div class="careers-job-reco {recommendation_class}" title="{_escape(recommendation_tooltip)}">{_escape(recommendation_label)}</div>'
        f"{verified_badge_html}"
        f"</div>"
        f"</div>"
        f'<div class="careers-job-submeta">{work_type} | {level} | {industry}</div>'
        f"{recent_posted_badge_html}"
        f'{"<div class=\'careers-job-note\'>Location unverified for this posting.</div>" if location_unverified else ""}'
        f'<div class="careers-job-summary"><strong>AI Summary:</strong> {ai_summary}</div>'
        f'<div class="careers-job-why"><strong>Why this job fits:</strong><ul>{why_fit_html}</ul></div>'
        f"</div>"
    )
    st.markdown(card_html, unsafe_allow_html=True)

    if match.missing_skills:
        chips_html = " ".join(
            (
                '<span class="careers-skill-chip" '
                'title="Detected in this job posting, but not found in your current resume/profile skills used for scoring.">'
                f"{_escape(skill)}"
                "</span>"
            )
            for skill in match.missing_skills[:6]
        )
        st.markdown(
            (
                '<div class="careers-job-chips">'
                '<strong title="These skills appear in the job posting but were not detected in your resume/profile context.">'
                "Missing skills:"
                "</strong> "
                f"{chips_html}"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
    else:
        st.caption("Missing skills: no meaningful gaps detected.")

    st.markdown(
        (
            '<div class="careers-job-reco-inline">'
            "<strong>Recommendation:</strong> "
            f'<span class="{recommendation_class}" title="{_escape(recommendation_tooltip)}">{_escape(recommendation_label)}</span>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )

    if str(job.job_url or "").strip():
        source_lower = str(job.source or "").strip().lower()
        is_official_source = ("official careers" in source_lower) or source_lower.endswith("careers")
        if is_official_source:
            link_label = "Open Official Direct Apply"
        elif verified_url:
            link_label = "Open Direct Apply"
        else:
            link_label = "Open Apply Link"
        st.markdown(f"[{link_label}]({_escape_link(job.job_url)})")

    if match.improvement_suggestions:
        suggestions_html = "".join(
            f"<li>{_escape(_truncate_text(text, 140))}</li>" for text in list(match.improvement_suggestions)[:3]
        )
        st.markdown(
            f'<div class="careers-job-actions"><strong>AI action plan:</strong><ul>{suggestions_html}</ul></div>',
            unsafe_allow_html=True,
        )
    if contact_emails:
        contacts = ", ".join(_escape(email) for email in contact_emails)
        st.markdown(f"<div class='careers-job-contact'><strong>Contact:</strong> {contacts}</div>", unsafe_allow_html=True)

    action_cols = st.columns([0.9, 0.9, 0.9, 5.3], gap="small")
    with action_cols[0]:
        if st.button("Save", key=f"careers_save_job_{job.job_id}_{index}", use_container_width=True):
            saved = applications_service.add_to_saved_jobs(user_id=user_id, job=job)
            if saved is None:
                st.error("Could not save this job.")
            else:
                st.success("Saved to your queue.")
    with action_cols[1]:
        if st.button("Apply", key=f"careers_apply_job_{job.job_id}_{index}", use_container_width=True):
            record = applications_service.move_job_to_application_tracker(
                user_id=user_id,
                job=job,
                status="applied",
                notes="Added from Jobs tab.",
            )
            if record is None:
                st.error("Could not add this job to applications.")
            else:
                st.success("Added to application tracker.")
    with action_cols[2]:
        if st.button("Add", key=f"careers_add_job_{job.job_id}_{index}", use_container_width=True):
            saved = applications_service.add_to_saved_jobs(user_id=user_id, job=job)
            if saved is None:
                st.error("Could not add this job.")
            else:
                st.success("Added to saved queue.")
    with action_cols[3]:
        st.empty()


def _build_recent_posted_badge_html(posted_at: str) -> str:
    posted_text = str(posted_at or "").strip()
    if not posted_text:
        return ""
    parsed_posted_at = CareersJobsService._parse_posted_at(posted_text)
    if parsed_posted_at is None:
        return ""
    age_seconds = max(0.0, (datetime.now(timezone.utc) - parsed_posted_at).total_seconds())
    age_hours = age_seconds / 3600.0
    if age_hours <= 24.5:
        tooltip = "Posted in the last 24 hours."
        return (
            '<div class="careers-job-recent careers-job-recent-24h" '
            f'title="{_escape(tooltip)}" aria-label="{_escape(tooltip)}">'
            "&#10003; Recently Posted"
            "</div>"
        )
    if age_hours <= 72.5:
        tooltip = "Posted in the last 3 days."
        return (
            '<div class="careers-job-recent careers-job-recent-3d" '
            f'title="{_escape(tooltip)}" aria-label="{_escape(tooltip)}">'
            "&#10003; Recently Posted"
            "</div>"
        )
    return ""

def _build_user_profile(default_profile: dict[str, Any] | None = None) -> dict[str, Any]:
    profile = dict(default_profile or {})
    resume_text = str(st.session_state.get("careers_resume_text", "") or "").strip()
    if not resume_text:
        resume_text = str(st.session_state.get("latest_resume_text", "") or "").strip()
    target_jd = str(st.session_state.get("careers_target_job_description", "") or "").strip()

    if "resume_text" not in profile:
        profile["resume_text"] = resume_text
    if "summary" not in profile:
        profile["summary"] = resume_text[:1200]
    if "skills" not in profile:
        profile["skills"] = _extract_skills_from_text(resume_text)
    if "target_role" not in profile or not str(profile.get("target_role", "") or "").strip():
        profile["target_role"] = (
            str(st.session_state.get("careers_jobs_role_query", "") or "").strip()
            or str(st.session_state.get("careers_jobs_resume_default_role", "") or "").strip()
        )
    if target_jd and "target_job_description" not in profile:
        profile["target_job_description"] = target_jd
    return profile


def _fetch_raw_jobs(
    fetch_jobs_func: Callable[[str, str, int], tuple[list[dict[str, Any]], str]] | None,
    role_query: str,
    preferred_location: str,
    max_results: int,
    fast_mode: bool = False,
) -> tuple[list[dict[str, Any]] | None, str]:
    cleaned_role = str(role_query or "").strip()
    if not cleaned_role:
        return [], "Enter a role to search jobs."
    if fetch_jobs_func is None:
        return [], "Job fetch function is not configured in this tab yet."
    try:
        rows, note = fetch_jobs_func(cleaned_role, str(preferred_location or "").strip(), int(max_results or 25))
        if not isinstance(rows, list):
            rows = []
        rows = [dict(item) for item in rows if isinstance(item, dict)]
        if bool(fast_mode):
            quick_rows = _dedupe_jobs(rows)[: max(1, int(max_results or 25))]
            return quick_rows, str(note or "").strip()

        min_target = max(8, min(25, int(max_results or 25) // 2))
        expanded = False
        merged_rows = _dedupe_jobs(rows)
        source_count, top_source_share = _source_diversity_metrics(merged_rows)
        low_diversity = bool(source_count <= 2 or top_source_share >= 0.72)

        if len(merged_rows) < min_target or low_diversity:
            expanded = True
            alt_queries = _expand_role_queries(cleaned_role)
            for alt_query in alt_queries:
                alt_rows, _ = fetch_jobs_func(alt_query, str(preferred_location or "").strip(), int(max_results or 25))
                if isinstance(alt_rows, list):
                    merged_rows.extend(dict(item) for item in alt_rows if isinstance(item, dict))
                    merged_rows = _dedupe_jobs(merged_rows)
                    source_count, top_source_share = _source_diversity_metrics(merged_rows)
                if len(merged_rows) >= int(max_results or 25):
                    break
                if source_count >= 4 and top_source_share < 0.62 and len(merged_rows) >= min_target:
                    break

        if (len(merged_rows) < min_target or source_count <= 2) and str(preferred_location or "").strip():
            expanded = True
            broad_rows, _ = fetch_jobs_func(cleaned_role, "", int(max_results or 25))
            if isinstance(broad_rows, list):
                merged_rows.extend(dict(item) for item in broad_rows if isinstance(item, dict))
                merged_rows = _dedupe_jobs(merged_rows)
                source_count, top_source_share = _source_diversity_metrics(merged_rows)

        final_rows = _rebalance_rows_by_source(merged_rows)[: max(1, int(max_results or 25))]
        base_note = str(note or "").strip()
        if expanded:
            extra = "Expanded query automatically to increase relevant direct job postings and source diversity."
            base_note = f"{base_note} {extra}".strip()
        return final_rows, base_note
    except Exception as ex:
        return [], f"Job fetch failed: {ex}"


def _expand_role_queries(role_query: str) -> list[str]:
    clean = str(role_query or "").strip()
    if not clean:
        return []
    lowered = clean.lower()
    candidates: list[str] = []
    if "developer" not in lowered:
        candidates.append(f"{clean} developer")
    if "engineer" not in lowered:
        candidates.append(f"{clean} engineer")
    if "software" not in lowered:
        candidates.append(f"{clean} software")
    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.lower().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(candidate.strip())
    return deduped[:3]


def _dedupe_jobs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in rows:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip().lower()
        company = str(item.get("company", "")).strip().lower()
        location = str(item.get("location", "")).strip().lower()
        apply_url = str(item.get("apply_url", item.get("job_url", ""))).strip().lower()
        key = (title, company, location, apply_url)
        if not title or not apply_url or key in seen:
            continue
        seen.add(key)
        deduped.append(dict(item))
    return deduped


def _source_diversity_metrics(rows: list[dict[str, Any]]) -> tuple[int, float]:
    if not isinstance(rows, list) or not rows:
        return 0, 1.0
    counts: Counter[str] = Counter()
    total = 0
    for item in rows:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source", "") or "").strip() or "Unknown source"
        counts[source] += 1
        total += 1
    if total <= 0:
        return 0, 1.0
    top_source_count = int(max(counts.values()) if counts else total)
    return len(counts), float(top_source_count) / float(total)


def _rebalance_rows_by_source(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(rows, list) or len(rows) <= 1:
        return list(rows or [])
    buckets: dict[str, list[dict[str, Any]]] = {}
    ordered_sources: list[str] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source", "") or "").strip() or "Unknown source"
        if source not in buckets:
            buckets[source] = []
            ordered_sources.append(source)
        buckets[source].append(item)
    rebalanced: list[dict[str, Any]] = []
    while True:
        progressed = False
        for source in ordered_sources:
            source_rows = buckets.get(source, [])
            if not source_rows:
                continue
            rebalanced.append(source_rows.pop(0))
            progressed = True
        if not progressed:
            break
    return rebalanced


def _build_cache_key(
    user_id: int,
    role_query: str,
    preferred_location: str,
    fetch_limit: int = 0,
    industries: list[str] | tuple[str, ...] | None = None,
) -> str:
    safe_limit = max(0, int(fetch_limit or 0))
    safe_industries = "|".join(
        sorted(
            {
                str(item or "").strip().lower()
                for item in (industries or [])
                if str(item or "").strip()
            }
        )
    )
    base = (
        f"v3|{int(user_id or 0)}|{str(role_query or '').strip().lower()}|"
        f"{str(preferred_location or '').strip().lower()}|{safe_limit}|{safe_industries}"
    )
    digest = hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]
    return f"careers-jobs-{digest}"


def _extract_skills_from_text(text: str) -> list[str]:
    if not str(text or "").strip():
        return []
    keywords = [
        "python",
        "java",
        "javascript",
        "typescript",
        "sql",
        "aws",
        "azure",
        "gcp",
        "docker",
        "kubernetes",
        "react",
        "node",
        "fastapi",
        "django",
        "flask",
        "spark",
        "airflow",
        "tableau",
        "power bi",
        "machine learning",
        "data engineering",
        "devops",
    ]
    lowered = str(text).lower()
    found = [token.title() for token in keywords if token in lowered]
    deduped: list[str] = []
    seen: set[str] = set()
    for skill in found:
        key = skill.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(skill)
    return deduped


def _extract_contact_emails(text: str, max_items: int = 2) -> list[str]:
    raw_text = str(text or "")
    if not raw_text.strip():
        return []
    matches = re.findall(r"(?i)\\b[a-z0-9._%+-]+@[a-z0-9.-]+\\.[a-z]{2,}\\b", raw_text)
    deduped: list[str] = []
    seen: set[str] = set()
    for email in matches:
        clean = str(email or "").strip()
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(clean)
        if len(deduped) >= max(1, int(max_items or 2)):
            break
    return deduped


def _parse_csv_tokens(value: str) -> list[str]:
    parts = [token.strip() for token in re.split(r"[,;|]", str(value or ""))]
    return [part for part in parts if part]


def _build_industry_aware_fetch_query(role_query: str, industries: list[str] | tuple[str, ...] | None) -> str:
    clean_role = str(role_query or "").strip()
    if not clean_role:
        return ""
    industry_tokens = _industry_query_tokens(industries)
    if not industry_tokens:
        return clean_role
    return f"{clean_role} {' '.join(industry_tokens)}".strip()


def _industry_query_tokens(industries: list[str] | tuple[str, ...] | None) -> list[str]:
    if not isinstance(industries, (list, tuple)):
        return []
    token_map: dict[str, list[str]] = {
        "technology": ["software", "tech"],
        "finance": ["finance", "banking"],
        "healthcare": ["healthcare", "medical"],
        "retail": ["retail", "ecommerce"],
        "education": ["education"],
        "manufacturing": ["manufacturing", "industrial"],
        "consulting": ["consulting", "advisory"],
    }
    selected_tokens: list[str] = []
    seen: set[str] = set()
    for industry in industries:
        key = str(industry or "").strip().lower()
        if key not in token_map:
            continue
        for token in token_map[key]:
            if token in seen:
                continue
            seen.add(token)
            selected_tokens.append(token)
            if len(selected_tokens) >= 3:
                return selected_tokens
    return selected_tokens


def _expand_source_aliases(sources: list[str]) -> list[str]:
    expanded: list[str] = []
    for source in sources:
        clean = str(source or "").strip()
        if not clean:
            continue
        lowered = clean.lower()
        if lowered in {"official careers", "official"}:
            expanded.extend(
                [
                    "JPMorgan Careers",
                    "Bank of America Careers",
                    "Weill Cornell Careers",
                    "L3Harris Careers",
                    "SAP Careers",
                    "Boeing Careers",
                    "AT&T Careers",
                    "Comcast Careers",
                    "Dell Careers",
                    "Bayer Careers",
                    "Boston Scientific Careers",
                    "Citi Careers",
                    "Capital One Careers",
                    "PwC Careers",
                    "EY Careers",
                    "Deloitte Careers",
                    "KPMG Careers",
                ]
            )
            continue
        if lowered in {"greenhouse", "greenhouse network", "partner careers"}:
            expanded.extend(
                [
                    "Airbnb Careers",
                    "Anthropic Careers",
                    "Coinbase Careers",
                    "Cloudflare Careers",
                    "Datadog Careers",
                    "Dropbox Careers",
                    "Figma Careers",
                    "MongoDB Careers",
                    "Okta Careers",
                    "Stripe Careers",
                    "Duolingo Careers",
                    "Reddit Careers",
                ]
            )
            continue
        if lowered in {"smartrecruiters", "smartrecruiters network"}:
            expanded.extend(
                [
                    "Visa Careers (SmartRecruiters)",
                    "ServiceNow Careers (SmartRecruiters)",
                    "Uber Careers (SmartRecruiters)",
                ]
            )
            continue
        if lowered in {"jobvite", "jobvite network"}:
            expanded.extend(
                [
                    "Palo Alto Networks Careers (Jobvite)",
                    "Nutanix Careers (Jobvite)",
                ]
            )
            continue
        if lowered in {"breezy", "breezy hr", "breezy hr network"}:
            expanded.append("Breezy HR")
            continue
        if lowered in {"jazzhr", "jazz hr", "jazzhr network"}:
            expanded.append("JazzHR")
            continue
        if lowered in {"teamtailor", "teamtailor network"}:
            expanded.extend(
                [
                    "Instabee Careers (Teamtailor)",
                    "Paradox Interactive Careers (Teamtailor)",
                    "Storytel Careers (Teamtailor)",
                    "Anyfin Careers (Teamtailor)",
                    "Airmee Careers (Teamtailor)",
                ]
            )
            continue
        if lowered in {
            "oracle recruiting cloud",
            "oracle recruiting cloud network",
            "oracle cloud",
            "oracle",
        }:
            expanded.extend(
                [
                    "Oracle Recruiting Cloud",
                    "JPMorgan Chase Careers (Oracle Recruiting Cloud)",
                ]
            )
            continue
        if lowered in {"successfactors", "sap successfactors", "successfactors network"}:
            expanded.extend(
                [
                    "SAP Careers (SuccessFactors)",
                    "Bayer Careers (SuccessFactors)",
                ]
            )
            continue
        expanded.append(clean)
    deduped: list[str] = []
    seen: set[str] = set()
    for source in expanded:
        key = source.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(source)
    return deduped


def _normalize_sources_raw_input(value: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        return ""
    compact = " ".join(cleaned.split())
    lowered = compact.lower()
    if lowered in LEGACY_SOURCE_FILTER_PLACEHOLDERS:
        return ""
    # If this legacy default was persisted with extra spacing/casing, clear it.
    if (
        "official careers" in lowered
        and "greenhouse network" in lowered
        and "adzuna" in lowered
        and len(_parse_csv_tokens(compact)) <= 3
    ):
        return ""
    tokens = {token.strip().lower() for token in _parse_csv_tokens(compact) if token.strip()}
    legacy_tokens = {"official careers", "greenhouse network", "adzuna"}
    if tokens and tokens.issubset(legacy_tokens):
        return ""
    return compact


def _normalize_certifications_raw_input(value: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        return ""
    compact = " ".join(cleaned.split())
    lowered = compact.lower()
    if lowered in LEGACY_CERT_FILTER_PLACEHOLDERS:
        return ""
    tokens = [token.strip() for token in _parse_csv_tokens(compact) if token.strip()]
    if len(tokens) == 3 and {token.lower() for token in tokens} == {"aws", "pmp", "cka"}:
        return ""
    return compact


def _normalize_location_state_value(value: str) -> str:
    cleaned = " ".join(str(value or "").split()).strip()
    if not cleaned:
        return IT_STRONG_LOCATION_OPTIONS[0]
    lowered = cleaned.lower()
    if lowered in {"usa", "us", "u.s.", "united states", "united states of america"}:
        return "United States of America"
    if lowered in {"uk", "u.k.", "great britain", "britain"}:
        return "United Kingdom"
    if lowered in {"uae", "u.a.e.", "emirates"}:
        return "United Arab Emirates"
    for option in IT_STRONG_LOCATION_OPTIONS:
        if lowered == option.lower():
            return option
    return IT_STRONG_LOCATION_OPTIONS[0]


def _location_query_value(location_label: str) -> str:
    normalized_label = _normalize_location_state_value(location_label)
    return str(IT_LOCATION_QUERY_MAP.get(normalized_label, "united states of america") or "united states of america")


def _normalize_job_location_for_display(location: str) -> str:
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


def _posted_days_from_label(label: str) -> int:
    lookup = {name: days for name, days in DEFAULT_POSTED_OPTIONS}
    return int(lookup.get(str(label or ""), 0))


def _default_posted_index(days: int) -> int:
    for idx, (_label, value) in enumerate(DEFAULT_POSTED_OPTIONS):
        if int(value) == int(days):
            return idx
    return 0


def _escape(value: str) -> str:
    text = str(value or "")
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;").replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    return text


def _coerce_enriched_cards(raw_value: Any) -> list[EnrichedJobCard]:
    if not isinstance(raw_value, list):
        return []
    coerced: list[EnrichedJobCard] = []
    for item in raw_value:
        if isinstance(item, EnrichedJobCard):
            coerced.append(item)
            continue
        if not isinstance(item, dict):
            continue
        try:
            job = JobCard.from_dict(item)
            if not job.job_id:
                continue
            raw_match = item.get("match")
            match_payload = dict(raw_match) if isinstance(raw_match, dict) else {}
            match = JobMatchResult(
                job_id=str(match_payload.get("job_id", "") or job.job_id).strip() or job.job_id,
                match_score=int(match_payload.get("match_score", 0) or 0),
                why_fit=str(match_payload.get("why_fit", "") or "").strip(),
                ai_summary=str(match_payload.get("ai_summary", "") or "").strip(),
                why_fit_points=tuple(
                    str(point).strip()
                    for point in list(match_payload.get("why_fit_points", []) or [])
                    if str(point).strip()
                )[:3],
                missing_skills=tuple(
                    str(skill).strip()
                    for skill in list(match_payload.get("missing_skills", []) or [])
                    if str(skill).strip()
                )[:6],
                recommendation=str(match_payload.get("recommendation", "") or "").strip().upper() or "IMPROVE_FIRST",
                improvement_suggestions=tuple(
                    str(item).strip()
                    for item in list(match_payload.get("improvement_suggestions", []) or [])
                    if str(item).strip()
                )[:3],
                computed_at=str(match_payload.get("computed_at", "") or "").strip(),
                analysis_timestamp=str(match_payload.get("analysis_timestamp", "") or "").strip(),
                analysis_source=str(match_payload.get("analysis_source", "") or "").strip(),
            )
            coerced.append(EnrichedJobCard(job=job, match=match))
        except Exception:
            continue
    return coerced


def _diversify_cards_by_source(cards: list[EnrichedJobCard]) -> list[EnrichedJobCard]:
    if len(cards) <= 1:
        return cards
    buckets: dict[str, list[EnrichedJobCard]] = {}
    ordered_sources: list[str] = []
    for card in cards:
        source = str(card.job.source or "Unknown source").strip() or "Unknown source"
        if source not in buckets:
            buckets[source] = []
            ordered_sources.append(source)
        buckets[source].append(card)

    diversified: list[EnrichedJobCard] = []
    while True:
        progressed = False
        for source in ordered_sources:
            source_cards = buckets.get(source, [])
            if not source_cards:
                continue
            diversified.append(source_cards.pop(0))
            progressed = True
        if not progressed:
            break
    return _rebalance_top_cards_by_company(diversified, top_window=24, max_per_company=2)


def _rebalance_top_cards_by_company(
    cards: list[EnrichedJobCard],
    *,
    top_window: int = 24,
    max_per_company: int = 2,
) -> list[EnrichedJobCard]:
    if len(cards) <= 1:
        return cards

    safe_window = max(6, int(top_window or 24))
    safe_window = min(len(cards), safe_window)
    safe_cap = max(1, int(max_per_company or 2))
    head = list(cards[:safe_window])
    tail = list(cards[safe_window:])

    company_counts: dict[str, int] = {}
    prioritized: list[EnrichedJobCard] = []
    overflow: list[EnrichedJobCard] = []

    for card in head:
        company_key = str(card.job.company or "Unknown company").strip().lower() or "unknown company"
        seen = int(company_counts.get(company_key, 0) or 0)
        if seen < safe_cap:
            company_counts[company_key] = seen + 1
            prioritized.append(card)
            continue
        overflow.append(card)

    interleaved_prioritized = _interleave_cards_by_company(prioritized)
    return interleaved_prioritized + overflow + tail


def _interleave_cards_by_company(cards: list[EnrichedJobCard]) -> list[EnrichedJobCard]:
    if len(cards) <= 1:
        return list(cards)

    buckets: dict[str, list[EnrichedJobCard]] = {}
    company_order: list[str] = []
    for card in cards:
        company_key = str(card.job.company or "Unknown company").strip().lower() or "unknown company"
        if company_key not in buckets:
            buckets[company_key] = []
            company_order.append(company_key)
        buckets[company_key].append(card)

    interleaved: list[EnrichedJobCard] = []
    while True:
        progressed = False
        for company_key in company_order:
            queue = buckets.get(company_key, [])
            if not queue:
                continue
            interleaved.append(queue.pop(0))
            progressed = True
        if not progressed:
            break
    return interleaved


def _build_result_count_explainer(raw_count: int, visible_count: int) -> str:
    safe_raw = max(0, int(raw_count or 0))
    safe_visible = max(0, int(visible_count or 0))
    if safe_raw <= 0:
        return ""
    if safe_visible >= safe_raw:
        return ""

    active_filters: list[str] = []
    effective_location = str(st.session_state.get("careers_jobs_effective_location", "") or "").strip()
    if effective_location:
        active_filters.append("location")
    effective_query = str(st.session_state.get("careers_jobs_effective_query", "") or "").strip()
    role_query = effective_query or str(st.session_state.get("careers_jobs_role_query", "") or "").strip()
    if role_query:
        role_mode = str(
            st.session_state.get(
                "careers_jobs_effective_role_match_mode",
                st.session_state.get("careers_jobs_role_match_mode", "broad"),
            )
            or "broad"
        ).strip().lower()
        active_filters.append(f"role-{role_mode}")
    posted_days = int(st.session_state.get("careers_jobs_posted_within_days", 0) or 0)
    if posted_days > 0:
        active_filters.append(f"posted-within {posted_days}d")
    if list(st.session_state.get("careers_jobs_work_types", []) or []):
        active_filters.append("work type")
    if list(st.session_state.get("careers_jobs_levels", []) or []):
        active_filters.append("level")
    if list(st.session_state.get("careers_jobs_domains", []) or []):
        active_filters.append("domain")
    if list(st.session_state.get("careers_jobs_industries", []) or []):
        active_filters.append("industry")
    if str(st.session_state.get("careers_jobs_certifications_raw", "") or "").strip():
        active_filters.append("certifications")
    if str(st.session_state.get("careers_jobs_sources_raw", "") or "").strip():
        active_filters.append("sources")
    recommendation_index = int(st.session_state.get("careers_jobs_recommendation_filter_index", 0) or 0)
    if recommendation_index > 0:
        active_filters.append("recommendation")
    if bool(st.session_state.get("careers_jobs_auto_relaxed", False)):
        active_filters.append("auto-relaxed")

    filter_hint = ", ".join(active_filters[:4])
    if filter_hint:
        return f"Showing {safe_visible} of {safe_raw} jobs after filters and AI ranking ({filter_hint})."
    return f"Showing {safe_visible} of {safe_raw} jobs after filters and AI ranking."


def _build_source_mix_note(enriched_cards: list[EnrichedJobCard]) -> str:
    if not isinstance(enriched_cards, list) or not enriched_cards:
        return ""
    source_counter: Counter[str] = Counter(
        str(item.job.source or "").strip() or "Unknown source"
        for item in enriched_cards
        if isinstance(item, EnrichedJobCard)
    )
    if not source_counter:
        return ""
    top_items = source_counter.most_common(6)
    top_text = ", ".join(f"{name}: {count}" for name, count in top_items)
    if len(source_counter) == 1:
        only_source = top_items[0][0]
        return (
            f"Source mix: {top_text}. Results are currently dominated by {only_source}. "
            "Try clearing Sources filter or changing Role Match to Broad for wider provider coverage."
        )
    return f"Source mix: {top_text}."


def _escape_link(value: str) -> str:
    return _escape(value).replace(" ", "%20")


def _truncate_text(value: str, limit: int = 320) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return ""
    max_len = max(24, int(limit or 320))
    if len(text) <= max_len:
        return text
    trimmed = text[: max_len - 1].rstrip(" ,.;:-")
    return f"{trimmed}..."


def _recommendation_for_score(score: int) -> tuple[str, str]:
    safe_score = max(0, min(100, int(score or 0)))
    if safe_score >= 80:
        return "Strong Apply", "careers-job-reco-high"
    if safe_score >= 62:
        return "Apply With Tailoring", "careers-job-reco-mid"
    return "Upskill First", "careers-job-reco-low"


def _recommendation_style(recommendation: str, score: int) -> tuple[str, str]:
    safe_rec = str(recommendation or "").strip().upper()
    if safe_rec == "APPLY":
        return "APPLY", "careers-job-reco-high"
    if safe_rec == "SKIP":
        return "SKIP", "careers-job-reco-low"
    if safe_rec == "IMPROVE_FIRST":
        return "IMPROVE_FIRST", "careers-job-reco-mid"
    return _recommendation_for_score(score)


def _recommendation_tooltip(recommendation: str, score: int, missing_skills_count: int) -> str:
    safe_rec = str(recommendation or "").strip().upper()
    safe_score = max(0, min(100, int(score or 0)))
    safe_missing = max(0, int(missing_skills_count or 0))
    signal_line = f"Current signal: ZoSwi Match {safe_score}%. Missing skills detected: {safe_missing}."

    if safe_rec in {"APPLY", "STRONG APPLY"}:
        return f"APPLY means strong fit and lower skill gaps. {signal_line}"
    if safe_rec in {"IMPROVE_FIRST", "APPLY WITH TAILORING"}:
        return f"IMPROVE_FIRST means partial fit. Improve key gaps or tailor resume before applying. {signal_line}"
    if safe_rec in {"SKIP", "UPSKILL FIRST"}:
        return f"SKIP means current fit is low for this role right now. {signal_line}"
    return f"Recommendation is based on fit score plus detected skill gaps. {signal_line}"


def _render_jobs_ai_summary(enriched_cards: list[EnrichedJobCard]) -> None:
    valid = [item for item in enriched_cards if isinstance(item, EnrichedJobCard)]
    if not valid:
        return
    total_jobs = len(valid)
    avg_match = int(round(sum(int(item.match.match_score) for item in valid) / max(1, total_jobs)))
    strong_apply_count = sum(1 for item in valid if int(item.match.match_score) >= 80)
    st.markdown(
        f"""
        <div class="careers-ai-summary">
            <div class="careers-ai-summary-grid">
                <div class="careers-ai-summary-item">
                    <div class="careers-ai-summary-label">Jobs Returned</div>
                    <div class="careers-ai-summary-value">{total_jobs}</div>
                </div>
                <div class="careers-ai-summary-item">
                    <div
                        class="careers-ai-summary-label"
                        title="ZoSwi Match is calculated from role relevance, skill overlap, and profile-to-job context."
                    >
                        Average ZoSwi Match
                    </div>
                    <div class="careers-ai-summary-value">{avg_match}%</div>
                </div>
                <div class="careers-ai-summary-item">
                    <div class="careers-ai-summary-label">Strong Apply</div>
                    <div class="careers-ai-summary-value">{strong_apply_count}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _build_google_site_query_url(domain: str, role: str, location: str = "") -> str:
    query = f"site:{str(domain or '').strip()} {str(role or '').strip()} jobs {str(location or '').strip()}".strip()
    return f"https://www.google.com/search?q={quote_plus(query)}"


def _safe_markdown_label(label: str) -> str:
    cleaned = str(label or "").strip()
    if not cleaned:
        return "Open resource"
    return re.sub(r"[\[\]\(\)]", "", cleaned)


def _render_resource_links_in_columns(links: list[tuple[str, str]], columns: int = 2) -> None:
    valid_links = [
        (str(label or "").strip(), str(url or "").strip())
        for label, url in links
        if str(label or "").strip() and str(url or "").strip()
    ]
    if not valid_links:
        st.caption("No resources available for this category yet.")
        return
    col_count = max(1, min(3, int(columns or 2)))
    cols = st.columns(col_count, gap="small")
    for idx, (label, url) in enumerate(valid_links):
        with cols[idx % col_count]:
            st.markdown(f"- [{_safe_markdown_label(label)}]({url})")


def _build_job_resource_catalog(
    role_query: str,
    preferred_location: str,
    enriched_cards: list[EnrichedJobCard],
) -> list[tuple[str, list[tuple[str, str]]]]:
    safe_role = str(role_query or "").strip()
    safe_location = str(preferred_location or "").strip()
    role_param = quote_plus(safe_role)
    location_param = quote_plus(safe_location) if safe_location else ""
    search_phrase = f"{safe_role} {safe_location}".strip()

    core_boards: list[tuple[str, str]] = [
        (
            "LinkedIn Jobs",
            f"https://www.linkedin.com/jobs/search/?keywords={role_param}&location={location_param}"
            if safe_location
            else f"https://www.linkedin.com/jobs/search/?keywords={role_param}",
        ),
        (
            "Indeed",
            f"https://www.indeed.com/jobs?q={role_param}&l={location_param}"
            if safe_location
            else f"https://www.indeed.com/jobs?q={role_param}",
        ),
        (
            "Google Jobs",
            f"https://www.google.com/search?q={quote_plus(f'{safe_role} jobs {safe_location}')}"
            if safe_location
            else f"https://www.google.com/search?q={quote_plus(f'{safe_role} jobs')}",
        ),
        (
            "ZipRecruiter",
            f"https://www.ziprecruiter.com/jobs-search?search={role_param}&location={location_param}"
            if safe_location
            else f"https://www.ziprecruiter.com/jobs-search?search={role_param}",
        ),
        ("Glassdoor", f"https://www.glassdoor.com/Job/jobs.htm?sc.keyword={role_param}"),
        (
            "Monster",
            f"https://www.monster.com/jobs/search/?q={role_param}&where={location_param}"
            if safe_location
            else f"https://www.monster.com/jobs/search/?q={role_param}",
        ),
        (
            "CareerBuilder",
            f"https://www.careerbuilder.com/jobs?keywords={role_param}&location={location_param}"
            if safe_location
            else f"https://www.careerbuilder.com/jobs?keywords={role_param}",
        ),
        (
            "Dice",
            f"https://www.dice.com/jobs?q={role_param}&location={location_param}"
            if safe_location
            else f"https://www.dice.com/jobs?q={role_param}",
        ),
        (
            "SimplyHired",
            f"https://www.simplyhired.com/search?q={role_param}&l={location_param}"
            if safe_location
            else f"https://www.simplyhired.com/search?q={role_param}",
        ),
        ("Jooble (site search)", _build_google_site_query_url("jooble.org", safe_role, safe_location)),
        ("Jobrapido (site search)", _build_google_site_query_url("jobrapido.com", safe_role, safe_location)),
    ]

    tech_boards: list[tuple[str, str]] = [
        ("Wellfound Startups", _build_google_site_query_url("wellfound.com/jobs", safe_role, safe_location)),
        ("Built In", _build_google_site_query_url("builtin.com/jobs", safe_role, safe_location)),
        ("Y Combinator Jobs", _build_google_site_query_url("ycombinator.com/jobs", safe_role, safe_location)),
        ("Hacker News Jobs", f"https://news.ycombinator.com/jobs"),
        ("Levels.fyi Jobs", _build_google_site_query_url("levels.fyi/jobs", safe_role, safe_location)),
        ("Arc Remote Tech Jobs", _build_google_site_query_url("arc.dev/remote-jobs", safe_role, safe_location)),
        ("DevJobsScanner", _build_google_site_query_url("devjobsscanner.com", safe_role, safe_location)),
        ("Tech Ladies Jobs", _build_google_site_query_url("jobs.hiretechladies.com", safe_role, safe_location)),
    ]

    remote_boards: list[tuple[str, str]] = [
        ("We Work Remotely", f"https://weworkremotely.com/remote-jobs/search?term={role_param}"),
        ("Remote OK", _build_google_site_query_url("remoteok.com", safe_role, safe_location or "remote")),
        ("Remotive", _build_google_site_query_url("remotive.com/remote-jobs", safe_role, safe_location or "remote")),
        ("FlexJobs", _build_google_site_query_url("flexjobs.com", safe_role, safe_location or "remote")),
        ("Working Nomads", _build_google_site_query_url("workingnomads.com/jobs", safe_role, safe_location or "remote")),
        ("JustRemote", _build_google_site_query_url("justremote.co", safe_role, safe_location or "remote")),
        ("Remote.co", _build_google_site_query_url("remote.co/remote-jobs", safe_role, safe_location or "remote")),
        ("Jobspresso", _build_google_site_query_url("jobspresso.co", safe_role, safe_location or "remote")),
    ]

    public_and_mission: list[tuple[str, str]] = [
        (
            "USAJobs",
            f"https://www.usajobs.gov/Search/Results?k={role_param}&l={location_param}"
            if safe_location
            else f"https://www.usajobs.gov/Search/Results?k={role_param}",
        ),
        (
            "ClearanceJobs",
            f"https://www.clearancejobs.com/jobs?keywords={role_param}&location={location_param}"
            if safe_location
            else f"https://www.clearancejobs.com/jobs?keywords={role_param}",
        ),
        ("Idealist", _build_google_site_query_url("idealist.org/jobs", safe_role, safe_location)),
        ("HigherEdJobs", _build_google_site_query_url("higheredjobs.com", safe_role, safe_location)),
        ("GovJobs", _build_google_site_query_url("governmentjobs.com", safe_role, safe_location)),
    ]

    ats_xray: list[tuple[str, str]] = [
        ("Greenhouse Boards", _build_google_site_query_url("boards.greenhouse.io", safe_role, safe_location)),
        ("Lever Jobs", _build_google_site_query_url("jobs.lever.co", safe_role, safe_location)),
        ("Workday Careers", _build_google_site_query_url("myworkdayjobs.com", safe_role, safe_location)),
        ("SmartRecruiters", _build_google_site_query_url("jobs.smartrecruiters.com", safe_role, safe_location)),
        ("Oracle Career Cloud", _build_google_site_query_url("fa.oraclecloud.com/hcmUI/CandidateExperience", safe_role, safe_location)),
        ("iCIMS Careers", _build_google_site_query_url("careers.icims.com", safe_role, safe_location)),
        ("Taleo Careers", _build_google_site_query_url("taleo.net/careersection", safe_role, safe_location)),
    ]

    company_sources = Counter()
    for item in enriched_cards:
        if not isinstance(item, EnrichedJobCard):
            continue
        company = str(item.job.company or "").strip()
        if company:
            company_sources[company] += 1
    company_links: list[tuple[str, str]] = []
    for company, _count in company_sources.most_common(6):
        query = f"{company} careers {search_phrase}".strip()
        company_links.append((f"{company} Careers", f"https://www.google.com/search?q={quote_plus(query)}"))

    return [
        ("Core Job Boards", core_boards),
        ("Tech & Product Boards", tech_boards),
        ("Remote & Flexible", remote_boards),
        ("Government & Mission", public_and_mission),
        ("Direct ATS Search", ats_xray),
        ("Company Careers (From Results)", company_links),
    ]


def _render_search_resources(role_query: str, preferred_location: str, enriched_cards: list[EnrichedJobCard]) -> None:
    safe_role = str(role_query or "").strip()
    safe_location = str(preferred_location or "").strip()
    if not safe_role:
        return

    resource_groups = _build_job_resource_catalog(
        role_query=safe_role,
        preferred_location=safe_location,
        enriched_cards=enriched_cards,
    )
    active_groups = [(name, links) for name, links in resource_groups if isinstance(links, list) and links]
    total_sources = sum(len(links) for _name, links in active_groups)

    st.markdown(
        f"""
        <div class="careers-resource-card">
            <div class="careers-resource-title">Premium Job Finding Resources</div>
            <div class="careers-resource-subtitle">
                <strong>{int(total_sources)}</strong> trusted sources aligned to
                <strong>{_escape(safe_role)}</strong>
                {" in <strong>" + _escape(safe_location) + "</strong>" if safe_location else ""}.
                Use these when you want broader coverage beyond current live feed.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not active_groups:
        st.caption("No additional resources available for this search context.")
        return

    with st.container(key="careers_resources_hub"):
        tabs = st.tabs([f"{name} ({len(links)})" for name, links in active_groups])
        for idx, (_group_name, links) in enumerate(active_groups):
            with tabs[idx]:
                _render_resource_links_in_columns(links, columns=2)


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


def _ensure_jobs_state() -> None:
    defaults: dict[str, Any] = {
        "careers_jobs_role_query": "",
        "careers_jobs_location_query": IT_STRONG_LOCATION_OPTIONS[0],
        "careers_jobs_fetch_limit": 80,
        "careers_jobs_posted_within_days": 0,
        "careers_jobs_work_types": [],
        "careers_jobs_levels": [],
        "careers_jobs_domains": [],
        "careers_jobs_industries": [],
        "careers_jobs_min_score": 0,
        "careers_jobs_recommendation_filter_index": 0,
        "careers_jobs_role_match_mode": "broad",
        "careers_jobs_certifications_raw": "",
        "careers_jobs_sources_raw": "",
        "careers_jobs_last_raw": [],
        "careers_jobs_last_enriched": [],
        "careers_jobs_fetch_note": "",
        "careers_jobs_role_suggestions": [],
        "careers_jobs_resume_default_role": "",
        "careers_jobs_role_prefill_signature": "",
        "careers_jobs_effective_role_match_mode": "broad",
        "careers_jobs_effective_location": "",
        "careers_jobs_effective_query": "",
        "careers_jobs_auto_relaxed": False,
        "careers_advisor_open": False,
        "careers_advisor_messages": [],
        "careers_advisor_input": "",
        "careers_advisor_submit": False,
        "careers_advisor_pending_prompt": "",
        "careers_advisor_clear_input": False,
        "careers_jobs_state_migrated_v2": False,
        "careers_jobs_state_migrated_v3": False,
        "careers_jobs_state_migrated_v4": False,
        "careers_jobs_state_migrated_v5": False,
        "careers_jobs_state_migrated_v6": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    role_match_mode = str(st.session_state.get("careers_jobs_role_match_mode", "broad") or "broad").strip().lower()
    if role_match_mode not in {"strict", "balanced", "broad"}:
        st.session_state["careers_jobs_role_match_mode"] = "broad"
    st.session_state["careers_jobs_location_query"] = _normalize_location_state_value(
        str(st.session_state.get("careers_jobs_location_query", "") or "")
    )
    advisor_messages = st.session_state.get("careers_advisor_messages")
    if not isinstance(advisor_messages, list) or not advisor_messages:
        st.session_state["careers_advisor_messages"] = _default_careers_advisor_messages()

    if not bool(st.session_state.get("careers_jobs_state_migrated_v2", False)):
        try:
            current_limit = int(st.session_state.get("careers_jobs_fetch_limit", 80) or 80)
        except Exception:
            current_limit = 80
        if current_limit < 40:
            st.session_state["careers_jobs_fetch_limit"] = 80
        st.session_state["careers_jobs_state_migrated_v2"] = True
    if not bool(st.session_state.get("careers_jobs_state_migrated_v3", False)):
        raw_sources = str(st.session_state.get("careers_jobs_sources_raw", "") or "").strip()
        if raw_sources:
            source_tokens = _parse_csv_tokens(raw_sources)
            filtered_tokens = [token for token in source_tokens if "arbeitnow" not in str(token).lower()]
            st.session_state["careers_jobs_sources_raw"] = ", ".join(filtered_tokens)
        st.session_state["careers_jobs_state_migrated_v3"] = True
    if not bool(st.session_state.get("careers_jobs_state_migrated_v4", False)):
        raw_sources = str(st.session_state.get("careers_jobs_sources_raw", "") or "")
        st.session_state["careers_jobs_sources_raw"] = _normalize_sources_raw_input(raw_sources)
        st.session_state["careers_jobs_state_migrated_v4"] = True
    if not bool(st.session_state.get("careers_jobs_state_migrated_v5", False)):
        st.session_state["careers_jobs_location_query"] = _normalize_location_state_value(
            str(st.session_state.get("careers_jobs_location_query", "") or "")
        )
        st.session_state["careers_jobs_state_migrated_v5"] = True
    if not bool(st.session_state.get("careers_jobs_state_migrated_v6", False)):
        raw_sources = str(st.session_state.get("careers_jobs_sources_raw", "") or "")
        raw_certs = str(st.session_state.get("careers_jobs_certifications_raw", "") or "")
        st.session_state["careers_jobs_sources_raw"] = _normalize_sources_raw_input(raw_sources)
        st.session_state["careers_jobs_certifications_raw"] = _normalize_certifications_raw_input(raw_certs)
        st.session_state["careers_jobs_state_migrated_v6"] = True


def _render_resume_role_suggestion_row(role_suggestions: list[str]) -> None:
    display_roles = [role for role in role_suggestions[:6] if str(role).strip()]
    if not display_roles:
        return
    hints_token = str(st.session_state.get("careers_jobs_role_prefill_signature", "") or "")[:8]
    with st.container(key="careers_role_suggestions_shell"):
        st.caption("Role suggestions from your attached resume")
        for row_start in range(0, len(display_roles), 3):
            row_roles = display_roles[row_start : row_start + 3]
            row_cols = st.columns(len(row_roles), gap="small")
            for idx, role in enumerate(row_roles):
                role_label = str(role).strip()
                with row_cols[idx]:
                    if st.button(
                        role_label,
                        key=f"careers_role_hint_{row_start + idx}_{hints_token}",
                        use_container_width=True,
                    ):
                        st.session_state["careers_jobs_role_query"] = role_label
                        suggested_domain = _domain_from_role(role_label)
                        if suggested_domain and not st.session_state.get("careers_jobs_domains"):
                            st.session_state["careers_jobs_domains"] = [suggested_domain]
                        st.rerun()


def _safe_role_suggestions(raw_value: Any) -> list[str]:
    if not isinstance(raw_value, (list, tuple)):
        return []
    deduped: list[str] = []
    seen: set[str] = set()
    for item in raw_value:
        clean = str(item or "").strip()
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(clean)
    return deduped


def _refresh_resume_role_hints() -> None:
    resume_text = str(st.session_state.get("careers_resume_text", "") or "").strip()
    if not resume_text:
        resume_text = str(st.session_state.get("latest_resume_text", "") or "").strip()
    target_jd = str(st.session_state.get("careers_target_job_description", "") or "").strip()

    if not resume_text:
        st.session_state["careers_jobs_role_suggestions"] = []
        st.session_state["careers_jobs_resume_default_role"] = ""
        st.session_state["careers_jobs_role_prefill_signature"] = ""
        return

    fingerprint_input = f"{ROLE_HINTS_LOGIC_VERSION}|{resume_text[:8000]}|{target_jd[:2000]}"
    role_signature = hashlib.sha256(fingerprint_input.encode("utf-8")).hexdigest()[:16]
    previous_signature = str(st.session_state.get("careers_jobs_role_prefill_signature", "") or "")

    if role_signature == previous_signature and _safe_role_suggestions(st.session_state.get("careers_jobs_role_suggestions")):
        return

    hints = derive_resume_role_hints(resume_text=resume_text, target_job_description=target_jd)
    suggestions = _safe_role_suggestions(hints.get("suggestions", []))
    default_role = str(hints.get("default_role", "") or "").strip()

    st.session_state["careers_jobs_role_suggestions"] = suggestions
    st.session_state["careers_jobs_resume_default_role"] = default_role
    st.session_state["careers_jobs_role_prefill_signature"] = str(hints.get("signature", role_signature) or role_signature)

    current_role = str(st.session_state.get("careers_jobs_role_query", "") or "").strip()
    if not current_role and default_role:
        st.session_state["careers_jobs_role_query"] = default_role
    elif default_role and current_role:
        analyst_roles = {"business analyst", "data analyst"}
        technical_defaults = {
            "backend engineer",
            "software engineer",
            "full stack engineer",
            "frontend engineer",
            "data engineer",
            "devops engineer",
            "cloud engineer",
            "machine learning engineer",
            "data scientist",
            "site reliability engineer",
            "security engineer",
            "qa engineer",
        }
        if current_role.lower() in analyst_roles and default_role.lower() in technical_defaults:
            st.session_state["careers_jobs_role_query"] = default_role

    current_domains = st.session_state.get("careers_jobs_domains")
    if default_role and (not isinstance(current_domains, list) or not current_domains):
        suggested_domain = _domain_from_role(default_role)
        if suggested_domain:
            st.session_state["careers_jobs_domains"] = [suggested_domain]


def derive_resume_role_hints(resume_text: str, target_job_description: str = "") -> dict[str, Any]:
    safe_resume = str(resume_text or "").strip()
    safe_jd = str(target_job_description or "").strip()
    if not safe_resume:
        return {
            "suggestions": [],
            "default_role": "",
            "default_domain": "",
            "signature": "",
        }
    fingerprint_input = f"{ROLE_HINTS_LOGIC_VERSION}|{safe_resume[:8000]}|{safe_jd[:2000]}"
    role_signature = hashlib.sha256(fingerprint_input.encode("utf-8")).hexdigest()[:16]
    suggestions = _extract_role_candidates(resume_text=safe_resume, target_job_description=safe_jd, limit=6)
    default_role = str(suggestions[0] if suggestions else "").strip()
    default_domain = _domain_from_role(default_role) if default_role else ""
    return {
        "suggestions": suggestions,
        "default_role": default_role,
        "default_domain": default_domain,
        "signature": role_signature,
    }


def _extract_role_candidates(resume_text: str, target_job_description: str, limit: int = 6) -> list[str]:
    resume_only = str(resume_text or "").strip()
    target_jd_only = str(target_job_description or "").strip()
    combined = f"{resume_only}\n{target_jd_only}".strip()
    if not combined:
        return []
    resume_lower = resume_only.lower()
    jd_lower = target_jd_only.lower()
    score = Counter()
    role_priority: dict[str, int] = {
        "Backend Engineer": 130,
        "Full Stack Engineer": 126,
        "Software Engineer": 124,
        "Data Engineer": 122,
        "Machine Learning Engineer": 120,
        "DevOps Engineer": 118,
        "Cloud Engineer": 116,
        "Frontend Engineer": 114,
        "Data Scientist": 112,
        "Analytics Engineer": 110,
        "Site Reliability Engineer": 108,
        "Security Engineer": 106,
        "QA Engineer": 100,
        "Product Manager": 55,
        "Data Analyst": 45,
        "Business Analyst": 40,
    }

    keyword_roles: list[tuple[str, str]] = [
        ("machine learning engineer", "Machine Learning Engineer"),
        ("ml engineer", "Machine Learning Engineer"),
        ("data scientist", "Data Scientist"),
        ("data engineer", "Data Engineer"),
        ("analytics engineer", "Analytics Engineer"),
        ("backend engineer", "Backend Engineer"),
        ("front end engineer", "Frontend Engineer"),
        ("frontend engineer", "Frontend Engineer"),
        ("full stack engineer", "Full Stack Engineer"),
        ("software engineer", "Software Engineer"),
        ("devops engineer", "DevOps Engineer"),
        ("site reliability engineer", "Site Reliability Engineer"),
        ("cloud engineer", "Cloud Engineer"),
        ("qa engineer", "QA Engineer"),
        ("security engineer", "Security Engineer"),
        ("product manager", "Product Manager"),
        ("business analyst", "Business Analyst"),
        ("data analyst", "Data Analyst"),
    ]
    for token, role_label in keyword_roles:
        resume_hits = resume_lower.count(token)
        jd_hits = jd_lower.count(token)
        if resume_hits > 0:
            score[role_label] += resume_hits * 6
        if jd_hits > 0:
            # Keep JD as weak signal only; resume should drive role identity.
            score[role_label] += jd_hits * 1

    role_line_pattern = re.compile(
        r"(?i)\b(?:senior|sr|lead|principal|staff|junior|jr)?\s*"
        r"(?:software|backend|front\s*end|frontend|full\s*stack|data|machine learning|ml|devops|cloud|qa|security|analytics|product)\s+"
        r"(?:engineer|developer|scientist|analyst|manager|architect)\b"
    )
    for line in str(resume_text or "").splitlines()[:220]:
        clean = re.sub(r"\s+", " ", str(line or "").strip())
        if not clean or len(clean) > 90:
            continue
        found = role_line_pattern.search(clean)
        if not found:
            continue
        normalized = _normalize_role_label(found.group(0))
        if normalized:
            score[normalized] += 4

    skill_role_boosts: list[tuple[tuple[str, ...], str, int]] = [
        (("java", "spring", "spring boot", "hibernate", "junit", "microservice", "microservices", "rest", "api"), "Backend Engineer", 3),
        (("java", "spring", "microservices", "kafka", "sql"), "Software Engineer", 3),
        (("react", "frontend", "front end", "javascript", "typescript", "html", "css"), "Frontend Engineer", 3),
        (("python", "fastapi", "django", "flask", "api", "backend"), "Backend Engineer", 2),
        (("aws", "azure", "gcp", "docker", "kubernetes", "terraform"), "Cloud Engineer", 2),
        (("airflow", "spark", "etl", "dbt", "warehouse"), "Data Engineer", 2),
        (("tensorflow", "pytorch", "llm", "machine learning"), "Machine Learning Engineer", 2),
    ]
    engineering_signal_count = 0
    for tokens, role_label, per_hit_points in skill_role_boosts:
        local_hits = 0
        for token in tokens:
            if token in resume_lower:
                local_hits += 1
        if local_hits > 0:
            score[role_label] += local_hits * per_hit_points
            engineering_signal_count += local_hits

    if engineering_signal_count >= 4:
        if "Business Analyst" in score:
            score["Business Analyst"] = max(0, int(score["Business Analyst"]) - 12)
        if "Data Analyst" in score:
            score["Data Analyst"] = max(0, int(score["Data Analyst"]) - 8)
        if "Product Manager" in score:
            score["Product Manager"] = max(0, int(score["Product Manager"]) - 6)

    inferred = _infer_role_from_skills(resume_text=resume_text, target_job_description=target_job_description)
    if inferred:
        score[inferred] += 5

    if not score:
        return []
    ordered_pairs = sorted(
        score.items(),
        key=lambda item: (int(item[1]), int(role_priority.get(str(item[0]), 0))),
        reverse=True,
    )
    top_score = int(ordered_pairs[0][1]) if ordered_pairs else 0
    min_keep_score = 2 if top_score < 6 else max(3, int(top_score * 0.35))
    ordered = [
        str(role)
        for role, role_score in ordered_pairs
        if int(role_score) >= min_keep_score
    ][: max(2, int(limit * 2))]
    if not ordered:
        ordered = [str(role) for role, _count in ordered_pairs[: max(2, int(limit * 2))]]
    deduped: list[str] = []
    seen: set[str] = set()
    for role in ordered:
        clean = str(role or "").strip()
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(clean)
        if len(deduped) >= limit:
            break
    return deduped


def _normalize_role_label(raw_role: str) -> str:
    clean = re.sub(r"\s+", " ", str(raw_role or "").strip())
    if not clean:
        return ""
    lowered = clean.lower()
    normalized_map: list[tuple[str, str]] = [
        ("machine learning", "Machine Learning Engineer"),
        ("data scientist", "Data Scientist"),
        ("data engineer", "Data Engineer"),
        ("analytics engineer", "Analytics Engineer"),
        ("backend", "Backend Engineer"),
        ("front end", "Frontend Engineer"),
        ("frontend", "Frontend Engineer"),
        ("full stack", "Full Stack Engineer"),
        ("devops", "DevOps Engineer"),
        ("site reliability", "Site Reliability Engineer"),
        ("cloud engineer", "Cloud Engineer"),
        ("security engineer", "Security Engineer"),
        ("qa engineer", "QA Engineer"),
        ("software engineer", "Software Engineer"),
        ("product manager", "Product Manager"),
        ("business analyst", "Business Analyst"),
        ("data analyst", "Data Analyst"),
    ]
    for token, label in normalized_map:
        if token in lowered:
            return label
    title_words = [piece.capitalize() for piece in clean.split()[:6]]
    return " ".join(title_words)


def _infer_role_from_skills(resume_text: str, target_job_description: str) -> str:
    corpus = f"{str(resume_text or '')}\n{str(target_job_description or '')}".lower()
    if "machine learning" in corpus or "tensorflow" in corpus or "pytorch" in corpus:
        return "Machine Learning Engineer"
    if "data engineer" in corpus or "airflow" in corpus or "spark" in corpus:
        return "Data Engineer"
    if "data scientist" in corpus or "statistics" in corpus:
        return "Data Scientist"
    if "react" in corpus or "frontend" in corpus or "front end" in corpus:
        return "Frontend Engineer"
    if "devops" in corpus or "kubernetes" in corpus:
        return "DevOps Engineer"
    if "cloud" in corpus and ("aws" in corpus or "azure" in corpus or "gcp" in corpus):
        return "Cloud Engineer"
    if "backend" in corpus or "api" in corpus or "microservice" in corpus:
        return "Backend Engineer"
    return "Software Engineer"


def _domain_from_role(role: str) -> str:
    lowered = str(role or "").strip().lower()
    mapping: list[tuple[str, str]] = [
        ("data engineer", "Data Engineering"),
        ("data scientist", "Data Science"),
        ("machine learning", "AI/ML"),
        ("ml engineer", "AI/ML"),
        ("devops", "DevOps"),
        ("cloud", "Cloud"),
        ("security", "Cybersecurity"),
        ("product manager", "Product"),
        ("software engineer", "Software Engineering"),
        ("backend engineer", "Software Engineering"),
        ("frontend engineer", "Software Engineering"),
        ("full stack engineer", "Software Engineering"),
    ]
    for token, domain in mapping:
        if token in lowered:
            return domain
    return ""
