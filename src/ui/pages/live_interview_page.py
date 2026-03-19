from __future__ import annotations

# Transitional extraction: page rendering moved out of app_runtime.
from src.app_runtime import *  # noqa: F401,F403


def render_live_interview_view(user: dict[str, Any]) -> None:
    full_name = str(user.get("full_name", "")).strip()
    default_name = full_name or "Candidate"
    default_role = str(user.get("role", "")).strip() or "Software Engineer"

    if not str(st.session_state.get("live_interview_candidate_name", "")).strip():
        st.session_state.live_interview_candidate_name = default_name
    if not str(st.session_state.get("live_interview_role", "")).strip():
        st.session_state.live_interview_role = default_role
    st.session_state.live_interview_requirement_type = normalize_interview_requirement_type(
        str(st.session_state.get("live_interview_requirement_type", "mixed"))
    )

    st.markdown(
        """
        <style>
        .live-intv-shell {
            border: 1px solid #dbeafe;
            border-radius: 18px;
            padding: 1rem;
            background:
                radial-gradient(760px 250px at -10% -12%, rgba(14, 165, 233, 0.14) 0%, transparent 56%),
                radial-gradient(580px 240px at 100% 0%, rgba(20, 184, 166, 0.14) 0%, transparent 58%),
                #ffffff;
            box-shadow: 0 18px 36px rgba(15, 23, 42, 0.08);
        }
        .live-intv-title {
            margin: 0;
            color: #0f172a;
            font-size: 1.38rem;
            line-height: 1.2;
            font-weight: 900;
        }
        .live-intv-sub {
            margin: 0.28rem 0 0 0;
            color: #475569;
            font-size: 0.9rem;
            line-height: 1.45;
        }
        .live-intv-link {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 100%;
            margin-top: 0.35rem;
            border-radius: 999px;
            border: 1px solid #0284c7;
            background: linear-gradient(130deg, #22d3ee 0%, #0284c7 100%);
            color: #ffffff;
            font-weight: 700;
            text-decoration: none;
            padding: 0.5rem 0.86rem;
            box-shadow: 0 10px 20px rgba(2, 132, 199, 0.24);
        }
        .live-intv-link:hover {
            filter: brightness(1.05);
            text-decoration: none;
            color: #ffffff;
        }
        .live-intv-url {
            margin-top: 0.45rem;
            font-size: 0.72rem;
            color: #334155;
            word-break: break-all;
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            padding: 0.55rem 0.7rem;
        }
        .st-key-live_interview_open_btn {
            display: inline-flex;
            margin-top: 0.35rem;
            margin-bottom: 0.2rem;
        }
        .st-key-live_interview_open_btn button {
            border-radius: 999px !important;
            border: 1px solid #0ea5e9 !important;
            background: linear-gradient(135deg, #ecfeff 0%, #cffafe 48%, #e0f2fe 100%) !important;
            color: #075985 !important;
            font-weight: 700 !important;
            min-height: 2rem !important;
            padding: 0.18rem 0.78rem !important;
            box-shadow: 0 7px 16px rgba(14, 165, 233, 0.2) !important;
            transition: transform 0.18s ease, box-shadow 0.2s ease, filter 0.2s ease !important;
            animation: live-intv-btn-glow 2.1s ease-in-out infinite;
        }
        .st-key-live_interview_open_btn button:hover {
            transform: translateY(-1px) scale(1.02);
            filter: saturate(1.08);
            box-shadow: 0 10px 20px rgba(2, 132, 199, 0.24) !important;
        }
        .st-key-live_interview_open_btn button:active {
            transform: translateY(0) scale(0.98);
        }
        .st-key-live_interview_open_btn button p {
            font-size: 0.8rem !important;
        }
        @keyframes live-intv-btn-glow {
            0%, 100% { box-shadow: 0 7px 16px rgba(14, 165, 233, 0.2); }
            50% { box-shadow: 0 10px 22px rgba(14, 165, 233, 0.3); }
        }
        </style>
        <div class="live-intv-shell">
            <h2 class="live-intv-title">Live AI Interview Integration</h2>
            <p class="live-intv-sub">
                Launch your real-time ZoSwi interview room with candidate context and requirement type.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Interview Launch Setup")
    is_mobile = is_mobile_browser()
    if is_mobile:
        candidate_name = st.text_input("Candidate Name", key="live_interview_candidate_name")
        target_role = st.text_input("Target Role", key="live_interview_role")
        requirement_type = st.selectbox(
            "Requirement Type",
            options=["mixed", "technical", "behavioral"],
            key="live_interview_requirement_type",
            format_func=lambda value: str(value).title(),
        )
    else:
        col1, col2, col3 = st.columns([3.6, 3.2, 2.2], gap="small")
        with col1:
            candidate_name = st.text_input("Candidate Name", key="live_interview_candidate_name")
        with col2:
            target_role = st.text_input("Target Role", key="live_interview_role")
        with col3:
            requirement_type = st.selectbox(
                "Requirement Type",
                options=["mixed", "technical", "behavioral"],
                key="live_interview_requirement_type",
                format_func=lambda value: str(value).title(),
            )

    requirement_type = normalize_interview_requirement_type(requirement_type)
    launch_url = build_zoswi_live_interview_launch_url(candidate_name, target_role, requirement_type, user=user)
    base_url = get_zoswi_live_interview_base_url()
    launch_secret_ready = bool(str(get_interview_launch_secret() or "").strip())

    if not base_url:
        st.error(
            "Interview app URL is not configured. Set ZOSWI_INTERVIEW_APP_URL in env or [interview].app_url in "
            "Streamlit secrets."
        )
        return

    if not launch_secret_ready:
        st.error(
            "Secure interview launch is not configured. Set STREAMLIT_LAUNCH_SECRET (same value) in Streamlit and Render."
        )
        return

    if not launch_url:
        st.warning("Enter both candidate name and target role to generate the launch URL.")
        return

    open_now = st.button(
        "Open in New Tab",
        key="live_interview_open_btn",
        icon=":material/open_in_new:",
        use_container_width=False,
    )
    safe_launch_url = html.escape(launch_url, quote=True)

    if open_now:
        st.components.v1.html(
            f"<script>window.open('{safe_launch_url}', '_blank', 'noopener,noreferrer');</script>",
            height=0,
        )

    st.markdown(
        '<div class="live-intv-url">Secure one-time launch link generated from this signed-in session.</div>',
        unsafe_allow_html=True,
    )

    embed_inside = st.toggle("Embed interview inside Streamlit (beta)", key="live_interview_embed")
    if embed_inside:
        iframe_height = 620 if is_mobile else 840
        st.components.v1.html(
            f"""
            <iframe
                src="{safe_launch_url}"
                style="width:100%;height:{iframe_height}px;border:1px solid #dbeafe;border-radius:16px;background:#fff;"
                allow="microphone; camera; autoplay; clipboard-read; clipboard-write"
            ></iframe>
            """,
            height=iframe_height + 30,
            scrolling=True,
        )
        st.caption("If mic/camera permissions are blocked in embed mode, use the new-tab launch button.")
