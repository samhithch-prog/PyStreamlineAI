from __future__ import annotations

# Transitional extraction: page rendering moved out of app_runtime.
from src.app_runtime import *  # noqa: F401,F403

def render_careers_profile_setup() -> None:
    is_mobile = is_mobile_browser()
    st.markdown("### Career Tailoring Setup")
    st.caption("Choose how ZoSwi should tailor your job matching context.")
    mode = st.radio(
        "Tailoring Mode",
        options=["Resume + JD", "Resume Only"],
        key="careers_input_mode",
        horizontal=True,
    )
    st.markdown(
        """
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.55rem;margin:0.15rem 0 0.55rem 0;">
            <div style="border:1px solid #bae6fd;border-radius:12px;padding:0.52rem 0.62rem;background:#f0f9ff;">
                <p style="margin:0;color:#075985;font-size:0.78rem;font-weight:800;letter-spacing:0.01em;">Resume + JD</p>
                <p style="margin:0.22rem 0 0 0;color:#0f172a;font-size:0.79rem;line-height:1.35;">
                    Targeted mode. ZoSwi aligns live jobs to both your resume and the job description you provide.
                    Best when you are applying for a specific role family.
                </p>
            </div>
            <div style="border:1px solid #d1fae5;border-radius:12px;padding:0.52rem 0.62rem;background:#ecfdf5;">
                <p style="margin:0;color:#065f46;font-size:0.78rem;font-weight:800;letter-spacing:0.01em;">Resume Only</p>
                <p style="margin:0.22rem 0 0 0;color:#0f172a;font-size:0.79rem;line-height:1.35;">
                    Discovery mode. ZoSwi uses your resume plus filters to surface broader opportunities
                    across different use cases and job styles.
                </p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if mode == "Resume + JD":
        st.caption("Smart targeting enabled: rankings prioritize jobs closest to your target JD intent.")
    else:
        st.caption("Smart discovery enabled: rankings explore wider role possibilities from your resume profile.")

    with st.container(key="careers_profile_setup_cols"):
        if is_mobile:
            uploaded_resume = st.file_uploader(
                "Upload Resume for Careers (PDF or DOCX)",
                type=["pdf", "docx"],
                key="careers_resume_upload",
            )
            jd_placeholder = "Paste target JD to tune matching quality..." if mode == "Resume + JD" else ""
            target_jd_input = st.text_area(
                "Target Job Description",
                key="careers_target_job_description_input",
                height=170,
                placeholder=jd_placeholder,
                disabled=(mode != "Resume + JD"),
            )
            if mode != "Resume + JD":
                st.caption("Resume Only mode selected. Matching will use your resume + live job postings.")
        else:
            setup_cols = st.columns(2, gap="small")
            with setup_cols[0]:
                uploaded_resume = st.file_uploader(
                    "Upload Resume for Careers (PDF or DOCX)",
                    type=["pdf", "docx"],
                    key="careers_resume_upload",
                )
            with setup_cols[1]:
                jd_placeholder = "Paste target JD to tune matching quality..." if mode == "Resume + JD" else ""
                target_jd_input = st.text_area(
                    "Target Job Description",
                    key="careers_target_job_description_input",
                    height=170,
                    placeholder=jd_placeholder,
                    disabled=(mode != "Resume + JD"),
                )
                if mode != "Resume + JD":
                    st.caption("Resume Only mode selected. Matching will use your resume + live job postings.")

    with st.container(key="careers_prepare_profile_btn_wrap"):
        prepare_clicked = st.button(
            "Prepare Careers Profile",
            key="careers_prepare_profile_btn",
            use_container_width=False,
        )

    if prepare_clicked:
        prepared_resume = ""
        source_note = ""
        if uploaded_resume is not None:
            try:
                prepared_resume = extract_resume_text(uploaded_resume)
            except Exception as ex:
                st.error(f"Could not read resume file: {ex}")
                return
            if not str(prepared_resume or "").strip():
                st.error("Could not extract text from resume file. Try another PDF or DOCX.")
                return
            st.session_state.careers_resume_file_name = str(getattr(uploaded_resume, "name", "resume")).strip()
            source_note = f"Using uploaded resume: {st.session_state.careers_resume_file_name}"
        else:
            existing_careers_resume = str(st.session_state.get("careers_resume_text", "")).strip()
            fallback_resume = str(st.session_state.get("latest_resume_text", "")).strip()
            if existing_careers_resume:
                prepared_resume = existing_careers_resume
                source_note = "Using previously prepared Careers resume."
            elif fallback_resume:
                prepared_resume = fallback_resume
                source_note = "Using resume from Home analysis."

        if not str(prepared_resume or "").strip():
            st.error("Upload a resume here or run Resume-JD analysis in Home first.")
            return

        prepared_jd = ""
        if mode == "Resume + JD":
            prepared_jd = str(target_jd_input or "").strip()
            if not prepared_jd:
                fallback_jd = str(st.session_state.get("latest_job_description", "")).strip()
                if fallback_jd:
                    prepared_jd = fallback_jd
            if not prepared_jd:
                st.error("Paste a target JD or switch to Resume Only mode.")
                return

        st.session_state.careers_resume_text = str(prepared_resume or "").strip()
        st.session_state.careers_target_job_description = prepared_jd
        st.session_state.careers_profile_status = (
            f"Profile ready in {mode} mode. {source_note}".strip()
        )
        st.success(str(st.session_state.get("careers_profile_status", "")).strip() or "Careers profile prepared.")

    current_status = str(st.session_state.get("careers_profile_status", "")).strip()
    if current_status:
        st.caption(current_status)

    active_resume, active_jd = get_active_careers_profile_context()
    if active_resume:
        active_mode = str(st.session_state.get("careers_input_mode", "Resume Only")).strip() or "Resume Only"
        jd_state = "Attached" if active_jd else "Not attached"
        st.caption(f"Active profile: {active_mode} | Target JD: {jd_state}")



def render_careers_motivation_hero(full_name: str, analysis_score: int) -> None:
    is_mobile = is_mobile_browser()
    first_name = str(full_name or "").strip().split(" ")[0] if str(full_name or "").strip() else "Candidate"
    safe_name = str(first_name or "Candidate").strip() or "Candidate"
    safe_score = max(0, min(100, int(analysis_score or 0)))
    if safe_score >= 80:
        tip_lines = [
            f"{safe_name}, your profile is strong. Apply to the highest-fit roles first.",
            "Prioritize jobs posted recently to improve your callback chances.",
            "Use achievement-first bullets when customizing your resume before applying.",
            "Apply to 3 high-fit roles today instead of sending 20 generic applications.",
            "Mirror must-have keywords from the job post in your resume summary.",
        ]
    elif safe_score >= 60:
        tip_lines = [
            f"{safe_name}, your profile is progressing well. Keep applications focused.",
            "Target 2-3 job matches and tailor your top skills to each role.",
            "Use location and job-type filters to avoid low-fit applications.",
            "Highlight measurable outcomes to improve recruiter confidence.",
            "Refine one weak section before applying broadly.",
        ]
    else:
        tip_lines = [
            f"{safe_name}, start with best-fit roles and build momentum step by step.",
            "Pick one role type and optimize your resume for that target first.",
            "Apply to roles where your core skills clearly match required skills.",
            "Use W2/Contract/Full-Time filters to avoid wasting applications.",
            "Small focused wins now will improve your confidence quickly.",
        ]
    tips_payload = json.dumps(tip_lines, ensure_ascii=True)

    st.components.v1.html(
        f"""
        <style>
            html, body {{
                margin: 0;
                padding: 0;
                background: transparent !important;
                font-family: "Plus Jakarta Sans", "Segoe UI", sans-serif;
            }}
            #careers-hero-card {{
                border: 1px solid #cbd5e1;
                border-radius: 14px;
                background: linear-gradient(140deg, #eef7f7 0%, #e8f2f3 52%, #edf7f8 100%);
                padding: 16px 18px;
                box-sizing: border-box;
            }}
            #careers-hero-chip {{
                display: inline-block;
                font-size: 0.72rem;
                color: #0f766e;
                border: 1px solid rgba(13, 148, 136, 0.35);
                border-radius: 999px;
                padding: 0.2rem 0.6rem;
                margin-bottom: 0.45rem;
                background: rgba(20, 184, 166, 0.08);
            }}
            #careers-hero-title {{
                margin: 0;
                font-size: 2rem;
                line-height: 1.15;
                letter-spacing: 0.01em;
                color: #0f172a;
                font-weight: 800;
            }}
            #careers-hero-sub {{
                margin-top: 0.35rem;
                margin-bottom: 0.45rem;
                color: #334155;
                font-size: 0.95rem;
                line-height: 1.4;
            }}
            #careers-zoswi-brand {{
                background: linear-gradient(120deg, #C7F2F5 0%, #C5E5F7 40%, #9D7DE9 72%, #C274F5 100%);
                -webkit-background-clip: text;
                background-clip: text;
                -webkit-text-fill-color: transparent;
                color: #9D7DE9;
                font-weight: 800;
            }}
            #careers-motivation-wrap {{
                margin-top: 0.15rem;
                border: 1px solid rgba(15, 118, 110, 0.24);
                border-radius: 10px;
                background: rgba(255, 255, 255, 0.78);
                padding: 0.6rem 0.72rem;
            }}
            #careers-motivation-head {{
                margin: 0;
                font-size: 0.7rem;
                font-weight: 700;
                letter-spacing: 0.04em;
                text-transform: uppercase;
                color: #0f766e;
            }}
            #careers-motivation-tip {{
                margin-top: 0.32rem;
                color: #0f3b66;
                font-size: 0.9rem;
                line-height: 1.35;
                font-weight: 650;
                animation: careersBlink 1.25s ease-in-out infinite;
            }}
            @keyframes careersBlink {{
                0% {{ opacity: 1; }}
                50% {{ opacity: 0.42; }}
                100% {{ opacity: 1; }}
            }}
        </style>
        <div id="careers-hero-card">
            <div id="careers-hero-chip">ZoSwi Careers</div>
        <h1 id="careers-hero-title">Let's Find Jobs You Can Actually Land</h1>
            <p id="careers-hero-sub">Tell us your role, location, visa needs, and job type. <span id="careers-zoswi-brand">ZoSwi</span> will shortlist the best matches so you can apply with confidence.</p>
            <div id="careers-motivation-wrap">
                <p id="careers-motivation-head">Application Tip</p>
                <div id="careers-motivation-tip"></div>
            </div>
        </div>
        <script>
        (function () {{
            const tips = {tips_payload};
            const tipEl = document.getElementById("careers-motivation-tip");
            if (!tipEl || !Array.isArray(tips) || tips.length === 0) {{
                return;
            }}

            function pickNext(currentIndex) {{
                if (tips.length <= 1) {{
                    return 0;
                }}
                let next = currentIndex;
                while (next === currentIndex) {{
                    next = Math.floor(Math.random() * tips.length);
                }}
                return next;
            }}

            let activeIndex = Math.floor(Math.random() * tips.length);
            tipEl.textContent = tips[activeIndex];

            setInterval(() => {{
                const nextIndex = pickNext(activeIndex);
                tipEl.style.opacity = "0.18";
                setTimeout(() => {{
                    activeIndex = nextIndex;
                    tipEl.textContent = tips[activeIndex];
                    tipEl.style.opacity = "1";
                }}, 180);
            }}, 15000);
        }})();
        </script>
        """,
        height=260 if is_mobile else 230,
    )



def render_job_match_mvp_panel(user: dict[str, Any]) -> None:
    is_mobile = is_mobile_browser()
    user_id = int(user.get("id") or 0)
    resume_text, target_job_description = get_active_careers_profile_context()
    if not resume_text:
        st.info("Prepare your Careers profile first by uploading a resume.")
        return

    st.markdown("### Career Match Studio: Work Authorization + Sponsorship Insights")
    st.caption(
        "Agentive mode: ZoSwi plans and runs live role fetch, filter validation, and resume + sponsorship ranking in one flow."
    )
    context_mode = "Resume + JD" if str(target_job_description or "").strip() else "Resume Only"
    st.caption(f"Active tailoring mode: {context_mode}")
    if context_mode == "Resume + JD":
        st.caption("Matching logic: resume fit + alignment to your target JD + sponsorship/location/job-type filters.")
    else:
        st.caption("Matching logic: resume fit + broad discovery across varied roles + sponsorship/location/job-type filters.")

    st.markdown(
        """
        <style>
        .st-key-careers_job_filters_compact .stTextInput,
        .st-key-careers_job_filters_compact .stSelectbox,
        .st-key-careers_job_filters_compact .stMultiSelect {
            width: min(76%, 460px);
            max-width: 76%;
        }
        .st-key-careers_job_filters_compact .stTextInput [data-baseweb="input"],
        .st-key-careers_job_filters_compact .stSelectbox [data-baseweb="select"],
        .st-key-careers_job_filters_compact .stMultiSelect [data-baseweb="select"] {
            min-height: 2rem;
        }
        .st-key-careers_job_filters_compact .stTextInput input {
            padding-top: 0.22rem;
            padding-bottom: 0.22rem;
        }
        @media (max-width: 900px) {
            .st-key-careers_job_filters_compact .stTextInput,
            .st-key-careers_job_filters_compact .stSelectbox,
            .st-key-careers_job_filters_compact .stMultiSelect {
                width: 100%;
                max-width: 100%;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    with st.container(key="careers_job_filters_compact"):
        if is_mobile:
            role_query = st.text_input(
                "Target Role",
                key="job_search_role_query",
                placeholder="ex: Software Engineer, Data Scientist",
            )
            preferred_location = st.text_input(
                "Preferred Location",
                key="job_search_preferred_location",
                placeholder="ex: New York, Austin, Remote",
            )
            posted_options = [value for _, value in JOB_SEARCH_POSTED_WITHIN_OPTIONS]
            posted_within_days = st.selectbox(
                "Recently Posted",
                options=posted_options,
                key="job_search_posted_within_days",
                format_func=get_posted_within_label,
                help="Filter jobs by posted date, such as past 24 hours or past 7 days.",
            )
            visa_status = st.selectbox(
                "Visa Status",
                options=JOB_SEARCH_VISA_STATUSES,
                key="job_search_visa_status",
            )
            sponsorship_required = st.checkbox(
                "Need employer visa/H1B sponsorship",
                key="job_search_sponsorship_required",
            )
            max_results = st.slider(
                "Max results",
                min_value=3,
                max_value=JOB_SEARCH_MAX_RESULTS_LIMIT,
                value=JOB_SEARCH_MAX_RESULTS_DEFAULT,
                key="job_search_max_results",
            )
            selected_position_types = st.multiselect(
                "Position Type Filters",
                options=JOB_POSITION_FILTER_OPTIONS,
                key="job_search_position_types",
                help="Choose one or more filters like Full-Time, Contract, or W2.",
            )
        else:
            filter_cols = st.columns(2, gap="small")
            with filter_cols[0]:
                role_query = st.text_input(
                    "Target Role",
                    key="job_search_role_query",
                    placeholder="ex: Software Engineer, Data Scientist",
                )
                preferred_location = st.text_input(
                    "Preferred Location",
                    key="job_search_preferred_location",
                    placeholder="ex: New York, Austin, Remote",
                )
                posted_options = [value for _, value in JOB_SEARCH_POSTED_WITHIN_OPTIONS]
                posted_within_days = st.selectbox(
                    "Recently Posted",
                    options=posted_options,
                    key="job_search_posted_within_days",
                    format_func=get_posted_within_label,
                    help="Filter jobs by posted date, such as past 24 hours or past 7 days.",
                )
            with filter_cols[1]:
                visa_status = st.selectbox(
                    "Visa Status",
                    options=JOB_SEARCH_VISA_STATUSES,
                    key="job_search_visa_status",
                )
                sponsorship_required = st.checkbox(
                    "Need employer visa/H1B sponsorship",
                    key="job_search_sponsorship_required",
                )
                max_results = st.slider(
                    "Max results",
                    min_value=3,
                    max_value=JOB_SEARCH_MAX_RESULTS_LIMIT,
                    value=JOB_SEARCH_MAX_RESULTS_DEFAULT,
                    key="job_search_max_results",
                )
                selected_position_types = st.multiselect(
                    "Position Type Filters",
                    options=JOB_POSITION_FILTER_OPTIONS,
                    key="job_search_position_types",
                    help="Choose one or more filters like Full-Time, Contract, or W2.",
                )

    render_application_confidence_card(
        role_query=str(role_query or ""),
        preferred_location=str(preferred_location or ""),
        selected_position_types=selected_position_types,
        sponsorship_required=bool(sponsorship_required),
        resume_text=resume_text,
        target_job_description=target_job_description,
    )
    st.markdown(
        """
        <style>
        .st-key-home_job_search_btn button,
        .st-key-home_job_search_btn [data-testid^="baseButton"] {
            border-radius: 999px !important;
            border: 1px solid #0f766e !important;
            background: linear-gradient(120deg, #14b8a6 0%, #0ea5e9 52%, #2563eb 100%) !important;
            color: #ffffff !important;
            font-weight: 800 !important;
            letter-spacing: 0.01em !important;
            padding: 0.45rem 1.1rem !important;
            box-shadow: 0 10px 24px rgba(14, 165, 233, 0.34) !important;
            animation: careersCtaPulse 1.8s ease-in-out infinite;
        }
        .st-key-home_job_search_btn button:hover,
        .st-key-home_job_search_btn [data-testid^="baseButton"]:hover {
            filter: brightness(1.07) !important;
            border-color: #0f3b66 !important;
            transform: translateY(-1px);
        }
        .st-key-home_job_search_btn button p,
        .st-key-home_job_search_btn button span {
            color: #ffffff !important;
            font-weight: 800 !important;
        }
        @keyframes careersCtaPulse {
            0% { box-shadow: 0 8px 18px rgba(14, 165, 233, 0.24); }
            50% { box-shadow: 0 12px 28px rgba(20, 184, 166, 0.42); }
            100% { box-shadow: 0 8px 18px rgba(14, 165, 233, 0.24); }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.container(key="home_job_search_btn"):
        st.markdown(
            "<div style='font-size:0.74rem;color:#64748b;margin-bottom:0.18rem;'>Powered by ZoSwi</div>",
            unsafe_allow_html=True,
        )
        search_clicked = st.button(
            "Find My Best Matches",
            key="home_find_rank_jobs_btn",
            use_container_width=False,
        )

    if search_clicked:
        if not str(role_query or "").strip():
            st.error("Enter a role to search for job matches.")
            return

        with st.spinner("Fetching jobs and computing resume + visa fit..."):
            search_result = run_agentive_job_search_pipeline(
                resume_text=resume_text,
                target_job_description=str(target_job_description or ""),
                role_query=str(role_query or ""),
                preferred_location=str(preferred_location or ""),
                visa_status=str(visa_status or ""),
                sponsorship_required=bool(sponsorship_required),
                selected_position_types=selected_position_types,
                posted_within_days=int(posted_within_days or 0),
                max_results=int(max_results or JOB_SEARCH_MAX_RESULTS_DEFAULT),
            )
            ok = bool(search_result.get("ok"))
            search_results = search_result.get("results", [])
            if not isinstance(search_results, list):
                search_results = []
            search_filters = search_result.get("filters", {})
            st.session_state.job_search_results = search_results if ok else []
            st.session_state.job_search_last_error = sanitize_job_search_error_message(
                str(search_result.get("error", "")).strip()
            )
            if ok and user_id > 0:
                history_role = str(search_filters.get("role_query", role_query)) if isinstance(search_filters, dict) else str(role_query)
                history_location = (
                    str(search_filters.get("preferred_location", preferred_location))
                    if isinstance(search_filters, dict)
                    else str(preferred_location)
                )
                history_visa = str(search_filters.get("visa_status", visa_status)) if isinstance(search_filters, dict) else str(visa_status)
                history_sponsorship = (
                    bool(search_filters.get("sponsorship_required", sponsorship_required))
                    if isinstance(search_filters, dict)
                    else bool(sponsorship_required)
                )
                save_job_search_history(
                    user_id=user_id,
                    source_profile="Careers Agentive",
                    role_query=history_role,
                    preferred_location=history_location,
                    visa_status=history_visa,
                    sponsorship_required=history_sponsorship,
                    results=search_results,
                )

    results = st.session_state.get("job_search_results", [])
    last_error = sanitize_job_search_error_message(str(st.session_state.get("job_search_last_error", "")).strip())
    st.session_state.job_search_last_error = last_error
    if last_error:
        if isinstance(results, list) and results:
            st.info(last_error)
        else:
            st.warning(last_error)

    if isinstance(results, list) and results:
        st.markdown("#### Recommended Jobs")
        for idx, item in enumerate(results):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip() or "Untitled role"
            company = str(item.get("company", "")).strip() or "Unknown company"
            location = str(item.get("location", "")).strip() or "Location not listed"
            posted_label = format_posted_age(str(item.get("posted_at", "")).strip())
            overall_score = int(item.get("overall_score", 0) or 0)
            resume_match_score = int(item.get("resume_match_score", 0) or 0)
            sponsorship_status = str(item.get("sponsorship_status", "")).strip() or "Unknown"
            sponsorship_confidence = int(item.get("sponsorship_confidence", 0) or 0)
            reason = str(item.get("reason", "")).strip()
            apply_url = str(item.get("apply_url", "")).strip()
            position_tags = item.get("position_tags", [])
            if not isinstance(position_tags, list):
                position_tags = []
            position_tags_text = ", ".join(str(tag).strip() for tag in position_tags if str(tag).strip()) or "Not specified"

            st.markdown(
                f"""
                <div style="border:1px solid #dbeafe;border-radius:14px;padding:0.8rem 0.92rem;margin:0.38rem 0;background:#ffffff;">
                    <div style="display:flex;justify-content:space-between;gap:1rem;align-items:flex-start;">
                        <div>
                            <p style="margin:0;font-size:1rem;font-weight:700;color:#0f172a;">{html.escape(title)}</p>
                            <p style="margin:0.1rem 0 0 0;font-size:0.9rem;color:#1e293b;">{html.escape(company)} | {html.escape(location)} | {html.escape(posted_label)}</p>
                        </div>
                        <div style="text-align:right;">
                            <p style="margin:0;font-size:0.8rem;color:#475569;">Apply readiness</p>
                            <p style="margin:0;font-size:1.05rem;font-weight:800;color:#0f766e;">{overall_score}%</p>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if is_mobile:
                st.caption(f"Resume match: {resume_match_score}%")
                st.caption(f"Sponsorship: {sponsorship_status}")
                st.caption(f"Sponsorship confidence: {sponsorship_confidence}%")
            else:
                detail_cols = st.columns(3, gap="small")
                with detail_cols[0]:
                    st.caption(f"Resume match: {resume_match_score}%")
                with detail_cols[1]:
                    st.caption(f"Sponsorship: {sponsorship_status}")
                with detail_cols[2]:
                    st.caption(f"Sponsorship confidence: {sponsorship_confidence}%")
            st.caption(f"Position types: {position_tags_text}")
            if reason:
                st.caption(reason)
            if apply_url:
                st.markdown(f"[Apply Now]({apply_url})")
            else:
                st.caption("Apply URL not available in this posting.")
            if idx < len(results) - 1:
                st.markdown("---")

    recent_searches = get_recent_job_search_history(user_id, limit=5)
    if recent_searches:
        rows: list[dict[str, str]] = []
        for item in recent_searches:
            rows.append(
                {
                    "When": format_history_time(str(item.get("created_at", ""))),
                    "Role": str(item.get("role_query", "")),
                    "Location": str(item.get("preferred_location", "")),
                    "Visa": str(item.get("visa_status", "")),
                    "Need Sponsorship": "Yes" if int(item.get("sponsorship_required", 0) or 0) == 1 else "No",
                    "Results": str(item.get("result_count", 0)),
                }
            )
        with st.expander("Recent Job Searches", expanded=False):
            st.dataframe(rows, use_container_width=True, hide_index=True)



def render_careers_view(user: dict[str, Any]) -> None:
    home_resume_text = str(st.session_state.get("latest_resume_text", "")).strip()
    home_analysis = st.session_state.get("analysis_result")
    home_has_score = isinstance(home_analysis, dict) and bool(home_analysis)
    home_profile_ready = bool(home_resume_text) and home_has_score

    if not home_profile_ready:
        st.session_state.careers_use_custom_profile = True

    active_resume_text, active_target_jd = get_active_careers_profile_context()
    analysis_score = get_careers_analysis_score(active_resume_text, active_target_jd)
    full_name = str(user.get("full_name", "")).strip()
    render_careers_motivation_hero(full_name, analysis_score)
    st.markdown(
        """
        <style>
            @keyframes careers-tip-blink {
                0%, 100% { opacity: 1; box-shadow: 0 0 0 rgba(194, 116, 245, 0); }
                50% { opacity: 0.72; box-shadow: 0 0 14px rgba(194, 116, 245, 0.28); }
            }
        </style>
        <div style="text-align:center;">
            <div style="display:inline-block;max-width:92%;margin:0.38rem auto 0.62rem auto;color:#475569;font-size:0.82rem;line-height:1.35;font-weight:700;border:1px solid rgba(157,125,233,0.34);background:linear-gradient(90deg, rgba(194,116,245,0.08), rgba(199,242,245,0.11));border-radius:10px;padding:0.34rem 0.5rem;animation:careers-tip-blink 1.2s ease-in-out infinite;text-align:center;white-space:normal;overflow-wrap:anywhere;">
                <span style="display:inline-flex;align-items:center;justify-content:center;width:0.95rem;height:0.95rem;border:1px solid #94a3b8;border-radius:999px;color:#64748b;font-size:0.68rem;font-weight:800;line-height:1;vertical-align:middle;margin-right:0.28rem;">i</span>
                <span style="color:#9D7DE9;font-weight:800;">ZoSwi</span>
                can create AI-based applications that help you apply to jobs faster, but you still know best what you are truly capable of.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if home_profile_ready:
        st.caption("Home Resume-JD score found. You can use it directly or switch to Careers tailoring setup.")
        st.toggle(
            "Use Careers Tailoring Setup Here",
            key="careers_use_custom_profile",
            help="Turn on to upload resume/JD directly in Careers instead of reusing Home profile.",
        )
        if bool(st.session_state.get("careers_use_custom_profile", False)):
            render_careers_profile_setup()
    else:
        st.info("Home resume/JD score was not found. Please prepare your profile in Careers setup below.")
        render_careers_profile_setup()

    active_resume_text, _ = get_active_careers_profile_context()
    if not str(active_resume_text or "").strip():
        st.info("Upload your resume in Careers setup to start job matching.")
        st.caption("You can also run Home analysis first and Careers will reuse that resume automatically.")
        return
    render_job_match_mvp_panel(user)



