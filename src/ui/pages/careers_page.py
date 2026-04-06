from __future__ import annotations

# Transitional extraction: page rendering moved out of app_runtime.
from src.app_runtime import *  # noqa: F401,F403
from urllib.parse import quote_plus

from src.repository.careers_repository import CareersRepository
from src.repository.resume_builder_repository import ResumeBuilderRepository
from src.service.careers_applications_service import CareersApplicationsService
from src.service.careers_jobs_service import CareersJobsService
from src.service.resume_builder_service import ResumeBuilderService
from src.service.resume_export_service import ResumeExportService
from src.ui.pages.careers.applications_tab import render_applications_tab
from src.ui.pages.careers.jobs_tab import derive_resume_role_hints, render_jobs_tab
from src.ui.pages.careers.resume_builder_tab import render_resume_builder_tab
from src.ui.pages.careers.saved_tab import render_saved_tab


def _resolve_resume_role_hint(resume_text: str, role_query: str) -> str:
    clean_role = re.sub(r"\s+", " ", str(role_query or "").strip())
    if clean_role:
        return clean_role

    resume_lower = str(resume_text or "").lower()
    role_patterns: list[tuple[str, str]] = [
        ("machine learning engineer", "Machine Learning Engineer"),
        ("data scientist", "Data Scientist"),
        ("data engineer", "Data Engineer"),
        ("frontend engineer", "Frontend Engineer"),
        ("front end engineer", "Frontend Engineer"),
        ("backend engineer", "Backend Engineer"),
        ("back end engineer", "Backend Engineer"),
        ("full stack", "Full Stack Engineer"),
        ("software engineer", "Software Engineer"),
        ("devops engineer", "DevOps Engineer"),
        ("site reliability engineer", "Site Reliability Engineer"),
        ("qa engineer", "QA Engineer"),
        ("product manager", "Product Manager"),
        ("business analyst", "Business Analyst"),
    ]
    for pattern, label in role_patterns:
        if pattern in resume_lower:
            return label

    skills = extract_top_technical_skills(str(resume_text or ""), "", limit=1)
    if skills:
        return f"{skills[0]} Engineer"
    return "Software Engineer"


def render_top_company_career_links(
    resume_text: str,
    role_query: str,
    preferred_location: str,
    visa_status: str,
    sponsorship_required: bool,
    selected_position_types: list[str],
) -> None:
    role_hint = _resolve_resume_role_hint(resume_text, role_query)
    clean_location = re.sub(r"\s+", " ", str(preferred_location or "").strip())
    safe_types = [re.sub(r"\s+", " ", str(item).strip()) for item in (selected_position_types or []) if str(item).strip()]

    query_tokens: list[str] = [role_hint]
    query_tokens.extend(safe_types[:2])
    query_text = " ".join(token for token in query_tokens if token).strip() or "software engineer"

    role_token = quote_plus(query_text)
    location_token = quote_plus(clean_location)

    company_links = [
        {
            "name": "Google",
            "url": (
                f"https://careers.google.com/jobs/results/?q={role_token}"
                + (f"&location={location_token}" if location_token else "")
            ),
        },
        {
            "name": "Apple",
            "url": (
                f"https://jobs.apple.com/en-us/search?search={role_token}"
                + (f"&location={location_token}" if location_token else "")
            ),
        },
        {
            "name": "Microsoft",
            "url": (
                f"https://jobs.careers.microsoft.com/global/en/search?q={role_token}"
                + (f"&l={location_token}" if location_token else "")
            ),
        },
        {
            "name": "Amazon",
            "url": (
                f"https://www.amazon.jobs/en/search?base_query={role_token}"
                + (f"&loc_query={location_token}" if location_token else "")
            ),
        },
        {"name": "Meta", "url": f"https://www.metacareers.com/jobs/?q={role_token}"},
        {"name": "NVIDIA", "url": f"https://www.nvidia.com/en-us/about-nvidia/careers/?keyword={role_token}"},
        {"name": "Adobe", "url": f"https://careers.adobe.com/us/en/search-results?keywords={role_token}"},
        {"name": "Salesforce", "url": f"https://careers.salesforce.com/en/jobs/?keywords={role_token}"},
    ]

    location_label = clean_location or "Any location"
    st.markdown("#### Top Company Career Links")
    st.caption(f"Generated from Career Match Studio filters. Role: {role_hint} | Location: {location_label}")
    cols_per_row = 1 if is_mobile_browser() else 4
    cols = st.columns(cols_per_row, gap="small")
    for idx, item in enumerate(company_links):
        with cols[idx % cols_per_row]:
            st.markdown(f"[{item['name']} Careers]({item['url']})")

def render_careers_profile_setup() -> None:
    if bool(st.session_state.get("careers_profile_clear_requested", False)):
        _clear_careers_prepared_profile_state()
        st.session_state["careers_profile_clear_requested"] = False

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
        <style>
        .careers-mode-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 0.55rem;
            margin: 0.15rem 0 0.55rem 0;
        }
        @media (max-width: 900px) {
            .careers-mode-grid {
                grid-template-columns: 1fr;
            }
        }
        </style>
        <div class="careers-mode-grid">
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
        role_hint_note = _seed_jobs_role_hints_from_prepared_profile(
            resume_text=str(prepared_resume or ""),
            target_job_description=str(prepared_jd or ""),
        )
        st.session_state.careers_profile_status = (
            f"Profile ready in {mode} mode. {source_note}".strip()
        )
        if role_hint_note:
            st.session_state["careers_profile_role_hint_note"] = role_hint_note
        st.success(str(st.session_state.get("careers_profile_status", "")).strip() or "Careers profile prepared.")

    current_status = str(st.session_state.get("careers_profile_status", "")).strip()
    if current_status:
        st.caption(current_status)

    uploaded_file_name = str(st.session_state.get("careers_resume_file_name", "") or "").strip()
    has_prepared_resume = bool(str(st.session_state.get("careers_resume_text", "") or "").strip())
    if uploaded_file_name and has_prepared_resume:
        st.markdown(
            """
            <style>
            .careers-uploaded-resume-row {
                display: flex;
                align-items: center;
                gap: 0.45rem;
                border: 1px solid #dbeafe;
                background: #f8fbff;
                border-radius: 999px;
                padding: 0.24rem 0.62rem;
                margin-top: 0.1rem;
            }
            .careers-uploaded-resume-doc {
                font-size: 0.9rem;
                line-height: 1;
            }
            .careers-uploaded-resume-name {
                color: #0f172a;
                font-size: 0.8rem;
                font-weight: 650;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .st-key-careers_resume_remove_btn button,
            .st-key-careers_resume_remove_btn [data-testid^="baseButton"] {
                min-height: 1.75rem !important;
                height: 1.75rem !important;
                width: 1.75rem !important;
                border-radius: 999px !important;
                border: 1px solid #ef4444 !important;
                background: #fff1f2 !important;
                color: #b91c1c !important;
                font-weight: 800 !important;
                padding: 0 !important;
                animation: careersRemoveXBlink 1.05s ease-in-out infinite;
            }
            .st-key-careers_resume_remove_btn button:hover,
            .st-key-careers_resume_remove_btn [data-testid^="baseButton"]:hover {
                background: #fee2e2 !important;
                border-color: #dc2626 !important;
            }
            @keyframes careersRemoveXBlink {
                0% { opacity: 1; transform: scale(1); }
                50% { opacity: 0.35; transform: scale(0.95); }
                100% { opacity: 1; transform: scale(1); }
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        row_cols = st.columns([0.92, 0.08], gap="small")
        with row_cols[0]:
            safe_name = html.escape(uploaded_file_name)
            st.markdown(
                f"""
                <div class="careers-uploaded-resume-row">
                    <span class="careers-uploaded-resume-doc">[doc]</span>
                    <span class="careers-uploaded-resume-name">{safe_name}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with row_cols[1]:
            with st.container(key="careers_resume_remove_btn"):
                if st.button("x", key="careers_remove_resume_profile_btn", help="Remove uploaded resume"):
                    st.session_state["careers_profile_clear_requested"] = True
                    st.rerun()
    role_hint_note = str(st.session_state.get("careers_profile_role_hint_note", "") or "").strip()
    if role_hint_note:
        st.caption(role_hint_note)

    active_resume, active_jd = get_active_careers_profile_context()
    if active_resume:
        active_mode = str(st.session_state.get("careers_input_mode", "Resume Only")).strip() or "Resume Only"
        jd_state = "Attached" if active_jd else "Not attached"
        st.caption(f"Active profile: {active_mode} | Target JD: {jd_state}")


def _clear_careers_prepared_profile_state() -> None:
    st.session_state["careers_resume_text"] = ""
    st.session_state["careers_resume_file_name"] = ""
    st.session_state["careers_target_job_description"] = ""
    st.session_state["careers_profile_status"] = ""
    st.session_state["careers_profile_role_hint_note"] = ""
    st.session_state["careers_jobs_role_suggestions"] = []
    st.session_state["careers_jobs_resume_default_role"] = ""
    st.session_state["careers_jobs_role_prefill_signature"] = ""
    st.session_state.pop("careers_target_job_description_input", None)
    st.session_state.pop("careers_resume_upload", None)


def _seed_jobs_role_hints_from_prepared_profile(resume_text: str, target_job_description: str) -> str:
    hints = derive_resume_role_hints(
        resume_text=str(resume_text or "").strip(),
        target_job_description=str(target_job_description or "").strip(),
    )
    suggestions_raw = hints.get("suggestions", [])
    suggestions = [str(item).strip() for item in suggestions_raw if str(item).strip()] if isinstance(suggestions_raw, list) else []
    default_role = str(hints.get("default_role", "") or "").strip()
    default_domain = str(hints.get("default_domain", "") or "").strip()
    signature = str(hints.get("signature", "") or "").strip()

    st.session_state["careers_jobs_role_suggestions"] = suggestions
    st.session_state["careers_jobs_resume_default_role"] = default_role
    st.session_state["careers_jobs_role_prefill_signature"] = signature

    current_role_query = str(st.session_state.get("careers_jobs_role_query", "") or "").strip()
    if not current_role_query and default_role:
        st.session_state["careers_jobs_role_query"] = default_role

    current_domains = st.session_state.get("careers_jobs_domains")
    if default_domain and (not isinstance(current_domains, list) or not current_domains):
        st.session_state["careers_jobs_domains"] = [default_domain]

    if default_role and default_domain:
        return f"Smart Job Board ready: default role '{default_role}' with domain '{default_domain}'."
    if default_role:
        return f"Smart Job Board ready: default role '{default_role}'."
    return ""



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
        st.caption(last_error)

    if isinstance(results, list) and results:
        st.markdown("#### Recommended Jobs")
        source_counts: dict[str, int] = {}
        for row in results:
            if not isinstance(row, dict):
                continue
            source_name = str(row.get("source", "")).strip() or "External API"
            source_counts[source_name] = source_counts.get(source_name, 0) + 1
        if source_counts:
            source_summary = " | ".join(
                f"{name}: {count}" for name, count in sorted(source_counts.items(), key=lambda item: item[0])
            )
            st.caption(f"Source coverage in current shortlist: {source_summary}")
        for idx, item in enumerate(results):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip() or "Untitled role"
            company = str(item.get("company", "")).strip() or "Unknown company"
            location = str(item.get("location", "")).strip() or "Location not listed"
            posted_label = format_posted_age(str(item.get("posted_at", "")).strip())
            source_name = str(item.get("source", "")).strip() or "External API"
            overall_score = int(item.get("overall_score", 0) or 0)
            resume_match_score = int(item.get("resume_match_score", 0) or 0)
            sponsorship_status = str(item.get("sponsorship_status", "")).strip() or "Unknown"
            sponsorship_confidence = int(item.get("sponsorship_confidence", 0) or 0)
            role_relevance = int(item.get("role_relevance", 0) or 0)
            reason = str(item.get("reason", "")).strip()
            missing_points = item.get("missing_points", [])
            if not isinstance(missing_points, list):
                missing_points = []
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
                            <p style="margin:0.1rem 0 0 0;font-size:0.9rem;color:#1e293b;">{html.escape(company)} | {html.escape(location)} | {html.escape(posted_label)} | Source: {html.escape(source_name)}</p>
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
                st.caption(f"Role relevance: {role_relevance}%")
            else:
                detail_cols = st.columns(4, gap="small")
                with detail_cols[0]:
                    st.caption(f"Resume match: {resume_match_score}%")
                with detail_cols[1]:
                    st.caption(f"Sponsorship: {sponsorship_status}")
                with detail_cols[2]:
                    st.caption(f"Sponsorship confidence: {sponsorship_confidence}%")
                with detail_cols[3]:
                    st.caption(f"Role relevance: {role_relevance}%")
            st.caption(f"Position types: {position_tags_text}")
            if reason:
                st.caption(reason)
            if missing_points:
                st.markdown("**Resume boost suggestions:**")
                for tip in missing_points[:3]:
                    safe_tip = str(tip).strip()
                    if safe_tip:
                        st.caption(f"- {safe_tip}")
            if apply_url:
                st.markdown(f"[Apply Now]({apply_url})")
            else:
                st.caption("Apply URL not available in this posting.")
            if idx < len(results) - 1:
                st.markdown("---")
    else:
        st.info("No strong matches from current APIs yet. Try direct company portals below.")

    render_top_company_career_links(
        resume_text=str(resume_text or ""),
        role_query=str(role_query or ""),
        preferred_location=str(preferred_location or ""),
        visa_status=str(visa_status or ""),
        sponsorship_required=bool(sponsorship_required),
        selected_position_types=selected_position_types if isinstance(selected_position_types, list) else [],
    )

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

    if home_profile_ready:
        st.caption("Home Resume-JD profile found. You can reuse it or upload a custom Careers profile.")
        st.toggle(
            "Use Careers Tailoring Setup Here",
            key="careers_use_custom_profile",
            help="Turn on to upload resume/JD in Careers instead of reusing Home profile.",
        )
        if bool(st.session_state.get("careers_use_custom_profile", False)):
            render_careers_profile_setup()
    else:
        st.info("Home resume/JD profile not found. Prepare your profile in Careers setup below.")
        render_careers_profile_setup()

    active_resume_text, active_target_jd = get_active_careers_profile_context()
    default_profile = _build_careers_default_profile(active_resume_text, active_target_jd)

    careers_repo = CareersRepository(db_connect=db_connect)
    careers_repo.create_tables()
    jobs_service = CareersJobsService(
        repository=careers_repo,
        ai_key_getter=get_zoswiai_key,
        ai_model=str(get_config_value("ZOSWI_AI_MODEL", "ai", "model_name", "gpt-4o-mini") or "gpt-4o-mini").strip(),
    )
    applications_service = CareersApplicationsService(repository=careers_repo)
    resume_repo = ResumeBuilderRepository(db_connect=db_connect)
    resume_repo.create_tables()
    resume_builder_service = ResumeBuilderService(
        repository=resume_repo,
        ai_key_getter=get_zoswiai_key,
        model_name=str(get_config_value("ZOSWI_AI_MODEL", "ai", "model_name", "gpt-4o-mini") or "gpt-4o-mini").strip(),
    )
    resume_export_service = ResumeExportService()

    with st.container(key="careers_workspace_scope"):
        jobs_tab, saved_tab, applications_tab, resume_builder_tab = st.tabs(
            ["Jobs", "Saved", "Applications", "Resume Builder"]
        )
        with jobs_tab:
            render_jobs_tab(
                user=user,
                jobs_service=jobs_service,
                applications_service=applications_service,
                fetch_jobs_func=fetch_jobs_from_all_sources,
                default_profile=default_profile,
            )
        with saved_tab:
            render_saved_tab(user=user, applications_service=applications_service)
        with applications_tab:
            render_applications_tab(user=user, applications_service=applications_service)
        with resume_builder_tab:
            render_resume_builder_tab(
                user=user,
                resume_builder_service=resume_builder_service,
                resume_export_service=resume_export_service,
            )


def _build_careers_default_profile(resume_text: str, target_job_description: str) -> dict[str, Any]:
    clean_resume = str(resume_text or "").strip()
    clean_target_jd = str(target_job_description or "").strip()
    return {
        "resume_text": clean_resume,
        "summary": clean_resume[:1200],
        "skills": extract_top_technical_skills(clean_resume, clean_target_jd, limit=12) if clean_resume else [],
        "target_job_description": clean_target_jd,
    }



