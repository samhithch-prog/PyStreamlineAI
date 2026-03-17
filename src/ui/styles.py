from __future__ import annotations

import streamlit as st

def render_app_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,500,0,0');
        @import url('https://fonts.googleapis.com/icon?family=Material+Icons+Outlined');
        :root {
            --ai-ink: #102a43;
            --ai-muted: #486581;
            --ai-accent-soft: #e6fffa;
            --ai-card: #ffffff;
            --ai-line: #d9e2ec;
        }
        .stApp {
            background:
                radial-gradient(1200px 500px at 15% -10%, #e8f2ff 0%, transparent 55%),
                radial-gradient(900px 450px at 100% 0%, #fff4d8 0%, transparent 60%),
                #f8fafc;
        }
        .ai-hero {
            border: 1px solid var(--ai-line);
            background: linear-gradient(115deg, #ffffff 0%, #f0fdfa 100%);
            border-radius: 16px;
            padding: 20px 22px;
            margin-bottom: 14px;
            box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
        }
        .ai-hero h1 {
            margin: 0 0 8px 0;
            color: var(--ai-ink);
            font-size: 1.7rem;
            line-height: 1.2;
        }
        .ai-hero p {
            margin: 0;
            color: var(--ai-muted);
            font-size: 0.98rem;
        }
        .dashboard-shell-header {
            margin: 0 0 0.62rem 0;
            padding: 0.72rem 0.8rem;
            border: 1px solid #dbeafe;
            border-radius: 12px;
            background: linear-gradient(115deg, rgba(255, 255, 255, 0.95) 0%, rgba(239, 246, 255, 0.92) 100%);
        }
        .dashboard-shell-title {
            margin: 0;
            color: #0f172a;
            font-size: 1.03rem;
            font-weight: 800;
            letter-spacing: 0.01em;
        }
        .dashboard-shell-subtitle {
            margin-top: 0.16rem;
            color: #475569;
            font-size: 0.84rem;
            line-height: 1.35;
        }
        .st-key-dashboard_top_nav_shell {
            margin: 0 0 0.85rem 0;
            padding: 0.16rem 0.3rem 0.2rem 0.3rem;
            border: 1px solid #dbeafe;
            border-radius: 12px;
            background: rgba(255, 255, 255, 0.84);
        }
        .st-key-dashboard_top_nav_shell [data-baseweb="tag"] {
            border-radius: 999px !important;
            font-weight: 700 !important;
        }
        .ai-card {
            border: 1px solid var(--ai-line);
            background: var(--ai-card);
            border-radius: 14px;
            padding: 14px 16px;
            margin-bottom: 10px;
        }
        .ai-card-title {
            margin: 0 0 6px 0;
            color: var(--ai-ink);
            font-size: 1rem;
            font-weight: 700;
        }
        .ai-chip {
            display: inline-block;
            border: 1px solid #a7f3d0;
            background: var(--ai-accent-soft);
            color: #065f46;
            border-radius: 999px;
            padding: 2px 10px;
            font-size: 0.76rem;
            margin-bottom: 8px;
        }
        .ai-muted {
            color: var(--ai-muted);
            font-size: 0.92rem;
            margin: 0 0 4px 0;
        }
        .st-key-global_music_bar {
            position: fixed;
            top: 5.2rem;
            right: 0.85rem;
            z-index: 1005;
            width: min(350px, calc(100vw - 1.35rem));
            border: 1px solid rgba(191, 219, 254, 0.9);
            border-radius: 14px;
            padding: 0.34rem 0.5rem 0.42rem 0.5rem;
            background: linear-gradient(120deg, rgba(255, 255, 255, 0.72) 0%, rgba(239, 246, 255, 0.68) 100%);
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
            box-shadow: 0 12px 24px rgba(15, 23, 42, 0.12);
        }
        .st-key-global_music_bar [data-testid="stVerticalBlock"] {
            gap: 0.28rem !important;
        }
        .st-key-global_music_bar .zoswi-music-title {
            margin: 0;
            color: #334155;
            font-size: 0.74rem;
            font-weight: 800;
            letter-spacing: 0.02em;
            text-transform: uppercase;
        }
        .st-key-global_music_search_row [data-testid="stHorizontalBlock"] {
            align-items: center !important;
        }
        .st-key-global_music_search_input [data-testid="stTextInputRootElement"] input {
            min-height: 1.95rem !important;
            border-radius: 10px !important;
            border: 1px solid #bfdbfe !important;
            background: rgba(255, 255, 255, 0.92) !important;
            padding: 0.2rem 0.58rem !important;
            font-size: 0.82rem !important;
        }
        .st-key-global_music_search_btn_wrap button {
            min-height: 1.95rem !important;
            border-radius: 10px !important;
            border: 1px solid #0ea5e9 !important;
            background: linear-gradient(120deg, #e0f2fe 0%, #dbeafe 100%) !important;
            color: #0c4a6e !important;
            font-size: 0.78rem !important;
            font-weight: 800 !important;
            box-shadow: none !important;
            padding: 0.18rem 0.46rem !important;
        }
        .st-key-global_music_search_btn_wrap button:hover {
            border-color: #0284c7 !important;
            background: linear-gradient(120deg, #dbeafe 0%, #bfdbfe 100%) !important;
            color: #0f172a !important;
        }
        .st-key-global_music_bar [data-baseweb="select"] > div {
            min-height: 1.95rem !important;
            border-radius: 10px !important;
            border: 1px solid #bfdbfe !important;
            background: rgba(255, 255, 255, 0.9) !important;
        }
        .st-key-global_music_bar [data-baseweb="select"] * {
            font-size: 0.82rem !important;
            color: #0f172a !important;
        }
        .st-key-global_music_bar audio {
            width: 100%;
            height: 34px;
            border-radius: 10px;
        }
        .st-key-oauth_social_stack {
            margin-top: 0;
        }
        .st-key-oauth_social_stack [data-testid="stVerticalBlock"] {
            gap: 0.6rem;
        }
        .st-key-oauth_motivation_popup {
            margin-top: clamp(2.6rem, 11vh, 8rem);
        }
        @media (max-width: 980px) {
            .st-key-global_music_bar {
                display: none !important;
            }
            .st-key-oauth_motivation_popup {
                margin-top: 1.25rem;
            }
        }
        .st-key-oauth_login_btn button,
        .st-key-oauth_login_btn [data-testid^="baseButton"],
        .st-key-oauth_login_linkedin_btn button,
        .st-key-oauth_login_linkedin_btn [data-testid^="baseButton"] {
            border: 1px solid #d1d5db !important;
            background: #ffffff !important;
            color: #0f172a !important;
            border-radius: 12px !important;
            font-weight: 700 !important;
            box-shadow: 0 6px 16px rgba(15, 23, 42, 0.08) !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            gap: 0.45rem !important;
            overflow: visible !important;
        }
        .st-key-oauth_login_btn button:hover,
        .st-key-oauth_login_btn [data-testid^="baseButton"]:hover,
        .st-key-oauth_login_linkedin_btn button:hover,
        .st-key-oauth_login_linkedin_btn [data-testid^="baseButton"]:hover {
            border: 1px solid #9ca3af !important;
            background: #f8fafc !important;
            transform: translateY(-1px);
        }
        .st-key-oauth_login_btn button img,
        .st-key-oauth_login_btn [data-testid^="baseButton"] img,
        .st-key-oauth_login_linkedin_btn button img,
        .st-key-oauth_login_linkedin_btn [data-testid^="baseButton"] img {
            width: 15px !important;
            height: 15px !important;
            object-fit: contain !important;
            margin-right: 0.1rem !important;
            vertical-align: middle !important;
        }
        .st-key-oauth_login_btn button p,
        .st-key-oauth_login_btn button span,
        .st-key-oauth_login_linkedin_btn button p,
        .st-key-oauth_login_linkedin_btn button span {
            margin: 0 !important;
        }
        .st-key-login_actions {
            margin-top: 0.25rem;
            margin-bottom: 0.15rem;
        }
        .st-key-login_form_shell {
            position: relative;
            overflow: hidden;
            border: 1px solid #bfdbfe;
            border-radius: 16px;
            background: linear-gradient(180deg, #ffffff 0%, #f6fcff 100%);
            padding: 0.72rem 0.9rem 0.44rem 0.9rem;
            box-shadow: 0 14px 30px rgba(14, 116, 144, 0.12);
            margin-top: 0.2rem;
        }
        .st-key-login_form_shell::before {
            content: "";
            position: absolute;
            left: 0;
            right: 0;
            top: 0;
            height: 3px;
            background: linear-gradient(90deg, #0284c7 0%, #0ea5e9 45%, #22d3ee 76%, #34d399 100%);
            background-size: 180% 100%;
            animation: loginLinerShift 4.2s linear infinite;
        }
        .st-key-login_form_shell [data-testid="stForm"] {
            border: 0 !important;
            padding: 0 !important;
            background: transparent !important;
        }
        @keyframes loginLinerShift {
            0% { background-position: 0% 50%; }
            100% { background-position: 100% 50%; }
        }
        .st-key-login_forgot_row {
            margin-top: 0.08rem;
            margin-bottom: 0.16rem;
        }
        .st-key-login_form_center [data-testid="stTextInputRootElement"] input {
            min-height: 2rem !important;
            border-radius: 10px !important;
            padding-top: 0.38rem !important;
            padding-bottom: 0.38rem !important;
        }
        .st-key-login_form_center [data-testid="stTextInputRootElement"] label {
            font-size: 0.82rem !important;
        }
        html body .stApp [data-testid="InputInstructions"],
        html body .stApp [data-testid*="InputInstructions"],
        html body [data-testid="stAppViewContainer"] [data-testid="InputInstructions"],
        html body [data-testid="stAppViewContainer"] [data-testid*="InputInstructions"],
        html body .stTextInput [data-testid="InputInstructions"],
        html body .stTextArea [data-testid="InputInstructions"] {
            display: none !important;
            visibility: hidden !important;
            height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            overflow: hidden !important;
            opacity: 0 !important;
            pointer-events: none !important;
        }
        html body .stApp [data-testid="InputInstructions"] *,
        html body .stApp [data-testid*="InputInstructions"] * {
            display: none !important;
            visibility: hidden !important;
        }
        .auth-forgot-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.6rem;
            margin-top: -0.15rem;
            margin-bottom: 0.15rem;
        }
        .auth-forgot-label {
            font-size: 0.76rem;
            color: #64748b;
            line-height: 1.2;
            font-weight: 500;
        }
        .auth-forgot-reset {
            font-size: 0.76rem;
            color: #64748b;
            text-decoration: none;
            font-weight: 600;
        }
        .auth-forgot-reset:hover {
            color: #334155;
            text-decoration: underline;
            text-underline-offset: 2px;
        }
        .st-key-login_forgot_row [data-testid="stHorizontalBlock"] {
            align-items: flex-start;
        }
        .st-key-login_forgot_reset_btn .stButton {
            display: flex;
            justify-content: flex-start;
            margin-top: 0.02rem;
        }
        .st-key-login_forgot_reset_btn .stButton > button,
        .st-key-login_forgot_reset_btn button,
        .st-key-login_forgot_reset_btn [data-testid^="baseButton"] {
            border: 0 !important;
            background: transparent !important;
            color: #475569 !important;
            min-height: auto !important;
            height: auto !important;
            padding: 0 !important;
            font-size: 0.66rem !important;
            line-height: 1.15 !important;
            font-weight: 500 !important;
            text-decoration: none !important;
            border-radius: 0 !important;
            justify-content: flex-start !important;
            box-shadow: none !important;
            transition: color 130ms ease, transform 130ms ease !important;
        }
        .st-key-login_forgot_reset_btn .stButton > button:hover,
        .st-key-login_forgot_reset_btn button:hover,
        .st-key-login_forgot_reset_btn [data-testid^="baseButton"]:hover {
            color: #1e293b !important;
            text-decoration: underline !important;
            text-underline-offset: 2px !important;
            background: transparent !important;
            border: 0 !important;
            box-shadow: none !important;
            transform: none !important;
        }
        .st-key-login_submit_btn button,
        .st-key-login_submit_btn [data-testid="baseButton-primary"] {
            border: 1px solid #0284c7 !important;
            background: linear-gradient(115deg, #0ea5e9 0%, #22d3ee 100%) !important;
            color: #ffffff !important;
            border-radius: 9px !important;
            font-weight: 800 !important;
            font-size: 0.84rem !important;
            min-height: 2.02rem !important;
            padding: 0.2rem 0.82rem !important;
            box-shadow: none !important;
            transition: transform 120ms ease, border-color 120ms ease !important;
        }
        .st-key-login_submit_btn button:hover,
        .st-key-login_submit_btn [data-testid="baseButton-primary"]:hover {
            transform: translateY(-1px) !important;
            border-color: #0369a1 !important;
        }
        .st-key-login_submit_btn button p,
        .st-key-login_submit_btn button span {
            margin: 0 !important;
        }
        .st-key-auth_privacy_center_link .stButton {
            display: flex;
            justify-content: flex-end;
            margin-top: 0.02rem;
            margin-bottom: 0;
            padding-right: 0.06rem;
            width: 100%;
        }
        .st-key-auth_privacy_center_link [data-testid="stElementContainer"] {
            width: 100% !important;
            display: flex !important;
            justify-content: flex-end !important;
        }
        .st-key-auth_privacy_center_link .stButton > button,
        .st-key-auth_privacy_center_link button,
        .st-key-auth_privacy_center_link [data-testid^="baseButton"] {
            border: 0 !important;
            background: transparent !important;
            color: #94a3b8 !important;
            min-height: auto !important;
            height: auto !important;
            padding: 0.01rem 0.12rem !important;
            font-size: 0.64rem !important;
            font-weight: 500 !important;
            letter-spacing: 0.01em !important;
            text-decoration: none !important;
            box-shadow: none !important;
            border-radius: 0 !important;
            opacity: 0.92 !important;
        }
        .st-key-auth_privacy_center_link .stButton > button:hover,
        .st-key-auth_privacy_center_link button:hover,
        .st-key-auth_privacy_center_link [data-testid^="baseButton"]:hover {
            color: #64748b !important;
            text-decoration: underline !important;
            text-underline-offset: 2px !important;
            background: transparent !important;
            border: 0 !important;
            box-shadow: none !important;
        }
        .st-key-auth_privacy_header_actions [data-testid="stHorizontalBlock"] {
            align-items: center;
            justify-content: flex-end;
            gap: 0.12rem !important;
        }
        .st-key-auth_privacy_header_close .stButton {
            display: flex;
            justify-content: center;
            margin-top: 0.52rem;
            margin-bottom: 0;
            padding-right: 0;
        }
        .st-key-auth_privacy_header_support .stButton {
            display: flex;
            justify-content: center;
            margin-top: 0.52rem;
            margin-bottom: 0;
            padding-right: 0;
        }
        .st-key-auth_privacy_header_close .stButton > button,
        .st-key-auth_privacy_header_close button,
        .st-key-auth_privacy_header_close [data-testid^="baseButton"],
        .st-key-auth_privacy_header_support .stButton > button,
        .st-key-auth_privacy_header_support button,
        .st-key-auth_privacy_header_support [data-testid^="baseButton"] {
            border: 1px solid #d7e2ee !important;
            background: #ffffff !important;
            min-height: 2.04rem !important;
            height: 2.04rem !important;
            width: 2.04rem !important;
            padding: 0 !important;
            border-radius: 8px !important;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08) !important;
            line-height: 1 !important;
            transition: transform 140ms ease, border-color 140ms ease, box-shadow 140ms ease !important;
        }
        .st-key-auth_privacy_header_close .stButton > button,
        .st-key-auth_privacy_header_close button,
        .st-key-auth_privacy_header_close [data-testid^="baseButton"] {
            color: #64748b !important;
            font-size: 1.1rem !important;
            font-weight: 800 !important;
        }
        .st-key-auth_privacy_header_close .stButton > button:hover,
        .st-key-auth_privacy_header_close button:hover,
        .st-key-auth_privacy_header_close [data-testid^="baseButton"]:hover {
            color: #0f172a !important;
            border-color: #cbd5e1 !important;
            background: #f8fafc !important;
            transform: translateY(-1px) !important;
        }
        .st-key-auth_privacy_header_close .stButton > button:focus,
        .st-key-auth_privacy_header_close button:focus,
        .st-key-auth_privacy_header_close [data-testid^="baseButton"]:focus,
        .st-key-auth_privacy_header_close .stButton > button:focus-visible,
        .st-key-auth_privacy_header_close button:focus-visible,
        .st-key-auth_privacy_header_close [data-testid^="baseButton"]:focus-visible {
            outline: none !important;
            box-shadow: none !important;
        }
        .st-key-auth_privacy_header_support .stButton > button,
        .st-key-auth_privacy_header_support button,
        .st-key-auth_privacy_header_support [data-testid^="baseButton"] {
            color: #0284c7 !important;
            font-size: 1rem !important;
            font-weight: 800 !important;
            white-space: nowrap !important;
        }
        .st-key-auth_privacy_header_support .stButton > button:hover,
        .st-key-auth_privacy_header_support button:hover,
        .st-key-auth_privacy_header_support [data-testid^="baseButton"]:hover {
            color: #0369a1 !important;
            border-color: #7dd3fc !important;
            background: #f0f9ff !important;
            transform: translateY(-1px) !important;
        }
        .st-key-auth_privacy_header_support .stButton > button:focus,
        .st-key-auth_privacy_header_support button:focus,
        .st-key-auth_privacy_header_support [data-testid^="baseButton"]:focus,
        .st-key-auth_privacy_header_support .stButton > button:focus-visible,
        .st-key-auth_privacy_header_support button:focus-visible,
        .st-key-auth_privacy_header_support [data-testid^="baseButton"]:focus-visible {
            outline: none !important;
            box-shadow: none !important;
        }
        .st-key-auth_privacy_support_sheet {
            position: fixed;
            right: 0.9rem;
            top: 5.2rem;
            bottom: 0.9rem;
            width: min(430px, calc(100vw - 1.4rem));
            z-index: 9999;
            animation: privacySupportSlideIn 260ms cubic-bezier(0.2, 0.9, 0.2, 1);
        }
        .st-key-auth_privacy_support_sheet > [data-testid="stVerticalBlock"] {
            background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
            border: 1px solid #cfe3f5;
            border-radius: 16px;
            box-shadow: 0 18px 38px rgba(15, 23, 42, 0.16);
            padding: 0.68rem 0.78rem 0.74rem 0.78rem;
            height: 100%;
            max-height: none;
            overflow-y: auto;
        }
        .auth-privacy-support-title {
            color: #0f172a;
            font-size: 0.98rem;
            font-weight: 800;
            line-height: 1.2;
            margin-bottom: 0.1rem;
        }
        .auth-privacy-support-subtitle {
            color: #475569;
            font-size: 0.79rem;
            line-height: 1.35;
            margin-bottom: 0.2rem;
        }
        .st-key-auth_privacy_support_close_btn .stButton {
            display: flex;
            justify-content: flex-end;
            margin-top: 0.02rem;
            margin-bottom: 0;
        }
        .st-key-auth_privacy_support_close_btn .stButton > button,
        .st-key-auth_privacy_support_close_btn button,
        .st-key-auth_privacy_support_close_btn [data-testid^="baseButton"] {
            border: 0 !important;
            background: transparent !important;
            color: #64748b !important;
            min-height: auto !important;
            height: auto !important;
            padding: 0 !important;
            border-radius: 0 !important;
            box-shadow: none !important;
            font-size: 1.08rem !important;
            font-weight: 800 !important;
            line-height: 1 !important;
            transition: transform 180ms ease, color 180ms ease, text-shadow 180ms ease !important;
            animation: supportCloseGlow 2.4s ease-in-out infinite;
        }
        .st-key-auth_privacy_support_close_btn .stButton > button:hover,
        .st-key-auth_privacy_support_close_btn button:hover,
        .st-key-auth_privacy_support_close_btn [data-testid^="baseButton"]:hover {
            color: #0f172a !important;
            background: transparent !important;
            border: 0 !important;
            box-shadow: none !important;
            transform: rotate(90deg) scale(1.08) !important;
            text-shadow: 0 0 10px rgba(14, 165, 233, 0.24);
        }
        .st-key-auth_privacy_support_close_btn .stButton > button:focus,
        .st-key-auth_privacy_support_close_btn button:focus,
        .st-key-auth_privacy_support_close_btn [data-testid^="baseButton"]:focus,
        .st-key-auth_privacy_support_close_btn .stButton > button:focus-visible,
        .st-key-auth_privacy_support_close_btn button:focus-visible,
        .st-key-auth_privacy_support_close_btn [data-testid^="baseButton"]:focus-visible {
            outline: none !important;
            box-shadow: none !important;
        }
        .auth-privacy-support-divider {
            height: 1px;
            margin: 0.28rem 0 0.34rem 0;
            background: linear-gradient(90deg, rgba(2, 132, 199, 0.22), rgba(148, 163, 184, 0.05));
        }
        @keyframes supportCloseGlow {
            0%, 100% { opacity: 0.82; transform: translateY(0px); }
            50% { opacity: 1; transform: translateY(-1px); }
        }
        .st-key-auth_privacy_support_email_row [data-testid="stHorizontalBlock"],
        .st-key-auth_privacy_support_otp_row [data-testid="stHorizontalBlock"] {
            align-items: end;
        }
        .st-key-auth_privacy_support_send_code_btn .stButton,
        .st-key-auth_privacy_support_verify_btn .stButton {
            margin-top: 0;
        }
        .st-key-auth_privacy_support_send_code_btn .stButton > button,
        .st-key-auth_privacy_support_send_code_btn button,
        .st-key-auth_privacy_support_send_code_btn [data-testid^="baseButton"] {
            border: 1px solid #bae6fd !important;
            background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%) !important;
            color: #0369a1 !important;
            border-radius: 8px !important;
            font-size: 0.69rem !important;
            font-weight: 700 !important;
            min-height: 2rem !important;
            padding: 0.1rem 0.48rem !important;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06) !important;
            white-space: nowrap !important;
            line-height: 1 !important;
            letter-spacing: 0.005em !important;
        }
        .st-key-auth_privacy_support_send_code_btn .stButton > button:hover,
        .st-key-auth_privacy_support_send_code_btn button:hover,
        .st-key-auth_privacy_support_send_code_btn [data-testid^="baseButton"]:hover {
            border-color: #7dd3fc !important;
            background: #f0f9ff !important;
            transform: translateY(-1px) !important;
        }
        .st-key-auth_privacy_support_verify_btn .stButton > button,
        .st-key-auth_privacy_support_verify_btn button,
        .st-key-auth_privacy_support_verify_btn [data-testid^="baseButton"] {
            border: 1px solid #93c5fd !important;
            background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%) !important;
            color: #1d4ed8 !important;
            border-radius: 8px !important;
            font-size: 0.69rem !important;
            font-weight: 700 !important;
            min-height: 2rem !important;
            padding: 0.1rem 0.48rem !important;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06) !important;
            white-space: nowrap !important;
            line-height: 1 !important;
            letter-spacing: 0.005em !important;
        }
        .st-key-auth_privacy_support_verify_btn .stButton > button:hover,
        .st-key-auth_privacy_support_verify_btn button:hover,
        .st-key-auth_privacy_support_verify_btn [data-testid^="baseButton"]:hover {
            border-color: #60a5fa !important;
            background: #eff6ff !important;
            transform: translateY(-1px) !important;
        }
        .st-key-auth_privacy_support_send_msg_btn .stButton > button,
        .st-key-auth_privacy_support_send_msg_btn button,
        .st-key-auth_privacy_support_send_msg_btn [data-testid^="baseButton"] {
            border: 1px solid #0ea5e9 !important;
            background: linear-gradient(120deg, #0ea5e9 0%, #22d3ee 100%) !important;
            color: #ffffff !important;
            border-radius: 999px !important;
            font-size: 0.76rem !important;
            font-weight: 800 !important;
            min-height: 1.86rem !important;
            padding: 0.12rem 0.8rem !important;
            box-shadow: none !important;
        }
        @keyframes privacySupportSlideIn {
            from { opacity: 0; transform: translateX(22px); }
            to { opacity: 1; transform: translateX(0px); }
        }
        .auth-privacy-page-wrap {
            width: 100%;
            display: flex;
            justify-content: center;
            padding: 0.32rem 0 1.2rem 0;
        }
        .auth-privacy-a4-sheet {
            width: min(100%, 794px);
            min-height: 1123px;
            background: #ffffff;
            border: 1px solid #dbe4ef;
            border-radius: 18px;
            box-shadow: 0 18px 42px rgba(15, 23, 42, 0.12);
            padding: 1.28rem 1.34rem 1.24rem 1.34rem;
            position: relative;
            overflow: hidden;
        }
        .auth-privacy-a4-sheet::before {
            content: "";
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 5px;
            background: linear-gradient(90deg, #0284c7 0%, #06b6d4 48%, #22d3ee 100%);
        }
        .auth-privacy-sheet-header {
            border-bottom: 1px solid #e2e8f0;
            padding-bottom: 0.82rem;
            margin-bottom: 0.9rem;
        }
        .auth-privacy-sheet-header-top {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
            margin-bottom: 0.6rem;
        }
        .auth-privacy-wordmark-wrap {
            width: 164px;
            height: 64px;
            border-radius: 10px;
            overflow: hidden;
            border: 0;
            background: transparent;
            box-shadow: none;
            flex: 0 0 auto;
        }
        .auth-privacy-page-logo {
            height: 64px;
            width: auto;
            max-width: none;
            margin-left: -56px;
            display: block;
        }
        .auth-privacy-sheet-pill {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 0.73rem;
            font-weight: 700;
            color: #0f172a;
            background: linear-gradient(120deg, #e0f2fe 0%, #ecfeff 100%);
            border: 1px solid #bae6fd;
            border-radius: 999px;
            padding: 0.16rem 0.62rem;
            white-space: nowrap;
        }
        .auth-privacy-sheet-header h2 {
            margin: 0;
            color: #0f172a;
            font-size: 1.56rem;
            font-weight: 800;
            letter-spacing: 0.01em;
        }
        .auth-privacy-heading {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.72rem;
            width: 100%;
            white-space: normal;
        }
        .auth-privacy-heading-text {
            flex: 1 1 auto;
            min-width: 0;
        }
        .auth-privacy-inline-badge {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 0.26rem;
            font-size: 0.66rem;
            font-weight: 700;
            line-height: 1;
            color: #065f46;
            background: #ecfdf5;
            border: 1px solid #a7f3d0;
            border-radius: 999px;
            padding: 0.22rem 0.52rem;
            letter-spacing: 0.01em;
            transform: translateY(1px);
            margin-left: auto;
            flex: 0 0 auto;
        }
        .auth-privacy-inline-badge-icon {
            width: 0.78rem;
            height: 0.78rem;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            flex: 0 0 auto;
        }
        .auth-privacy-inline-badge-icon svg {
            width: 100%;
            height: 100%;
            display: block;
        }
        .auth-privacy-sheet-meta {
            margin: 0.32rem 0 0.42rem 0 !important;
            color: #64748b !important;
            font-size: 0.82rem !important;
            font-weight: 600 !important;
        }
        .auth-privacy-sheet-header p {
            margin: 0.16rem 0 0 0;
            color: #334155;
            font-size: 0.92rem;
            line-height: 1.55;
        }
        .auth-privacy-sheet-section {
            margin-top: 0.86rem;
        }
        .auth-privacy-sheet-section h3 {
            margin: 0 0 0.28rem 0;
            color: #0f172a;
            font-size: 1rem;
            font-weight: 800;
        }
        .auth-privacy-sheet-section p {
            margin: 0;
            color: #334155;
            font-size: 0.9rem;
            line-height: 1.6;
        }
        .auth-privacy-sheet-section ul {
            margin: 0.15rem 0 0 1.1rem;
            padding: 0;
        }
        .auth-privacy-sheet-section li {
            color: #334155;
            font-size: 0.9rem;
            line-height: 1.55;
            margin: 0.16rem 0;
        }
        .auth-privacy-contact-highlight {
            margin-top: 0.92rem;
            padding-top: 0.58rem;
            border-top: 1px solid #d1d5db;
            display: flex;
            justify-content: center;
        }
        .auth-privacy-contact-note {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 0.36rem;
            color: #475569;
            font-size: 0.78rem;
            font-weight: 600;
            line-height: 1.25;
            background: #f1f5f9;
            border: 1px solid #dbe5ee;
            border-radius: 999px;
            padding: 0.28rem 0.66rem;
            text-align: center;
        }
        .auth-privacy-contact-note-icon {
            width: 0.9rem;
            height: 0.9rem;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            flex: 0 0 auto;
            color: #0284c7;
        }
        .auth-privacy-contact-note-icon svg {
            width: 100%;
            height: 100%;
            display: block;
        }
        @media (max-width: 900px) {
            .st-key-auth_privacy_support_sheet {
                width: min(97vw, 560px);
                right: 0.45rem;
                top: 4.9rem;
                bottom: 0.55rem;
            }
            .auth-privacy-a4-sheet {
                min-height: auto;
                border-radius: 14px;
                padding: 1rem 0.92rem;
            }
            .auth-privacy-sheet-header h2 {
                font-size: 1.22rem;
            }
            .auth-privacy-heading {
                gap: 0.42rem;
            }
            .auth-privacy-heading-text {
                font-size: 1.22rem;
            }
            .auth-privacy-inline-badge {
                font-size: 0.58rem;
                padding: 0.18rem 0.42rem;
            }
            .auth-privacy-wordmark-wrap {
                width: 148px;
                height: 58px;
            }
            .auth-privacy-page-logo {
                height: 58px;
                margin-left: -50px;
            }
            .auth-privacy-contact-note {
                font-size: 0.72rem;
                padding: 0.24rem 0.54rem;
            }
        }
        .st-key-password_reset_actions [data-testid="stHorizontalBlock"] {
            align-items: center;
            justify-content: center;
            gap: 0.42rem !important;
        }
        .st-key-password_reset_actions {
            max-width: 26rem;
            margin: 0.24rem auto 0 auto;
        }
        .st-key-password_reset_resend_proxy {
            position: absolute !important;
            width: 1px !important;
            height: 1px !important;
            overflow: hidden !important;
            opacity: 0 !important;
            pointer-events: none !important;
        }
        .password-reset-timer-pill {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 84px;
            padding: 0.34rem 0.62rem;
            border-radius: 999px;
            border: 1px solid #7dd3fc;
            background: #f0f9ff;
            color: #0369a1;
            font-size: 0.73rem;
            font-weight: 700;
            line-height: 1;
            margin-top: 0.16rem;
            white-space: nowrap;
        }
        .st-key-password_reset_resend_btn .stButton > button,
        .st-key-password_reset_resend_btn button,
        .st-key-password_reset_resend_btn [data-testid^="baseButton"] {
            border: 1px solid #7dd3fc !important;
            background: #ffffff !important;
            color: #0369a1 !important;
            border-radius: 999px !important;
            font-size: 0.73rem !important;
            font-weight: 700 !important;
            min-height: 1.75rem !important;
            padding: 0.12rem 0.62rem !important;
            box-shadow: none !important;
        }
        .st-key-password_reset_resend_btn .stButton > button:hover,
        .st-key-password_reset_resend_btn button:hover,
        .st-key-password_reset_resend_btn [data-testid^="baseButton"]:hover {
            border-color: #38bdf8 !important;
            background: #f0f9ff !important;
            transform: translateY(-1px) !important;
        }
        .st-key-password_reset_email_wrap [data-testid="stHorizontalBlock"] {
            align-items: center;
        }
        .st-key-password_reset_email_wrap [data-testid="stTextInputRootElement"] > div {
            max-width: 26rem;
            margin: 0 auto;
        }
        .st-key-password_reset_email_wrap [data-testid="stTextInputRootElement"] [data-baseweb="input"] {
            border: 1px solid #7dd3fc !important;
            border-radius: 10px !important;
            background: #ffffff !important;
            box-shadow: none !important;
        }
        .st-key-password_reset_email_wrap [data-testid="stTextInputRootElement"] [data-baseweb="input"]:focus-within {
            border-color: #0ea5e9 !important;
            box-shadow: 0 0 0 2px rgba(14, 165, 233, 0.16) !important;
        }
        .st-key-password_reset_email_wrap [data-testid="stTextInputRootElement"] input {
            min-height: 2rem !important;
            border: none !important;
            border-radius: 10px !important;
            background: transparent !important;
            color: #0f172a !important;
            box-shadow: none !important;
        }
        .st-key-password_reset_email_wrap [data-testid="stTextInputRootElement"] input::placeholder {
            color: #64748b !important;
            opacity: 1 !important;
        }
        .st-key-password_reset_email_wrap [data-testid="stTextInputRootElement"] input:focus,
        .st-key-password_reset_email_wrap [data-testid="stTextInputRootElement"] input:focus-visible {
            border: none !important;
            box-shadow: none !important;
            outline: none !important;
        }
        .st-key-password_reset_fields_wrap [data-testid="stHorizontalBlock"] {
            align-items: center;
        }
        .st-key-password_reset_fields_wrap [data-testid="stTextInputRootElement"] > div {
            max-width: 26rem;
            margin: 0 auto;
        }
        .st-key-password_reset_fields_wrap [data-testid="stTextInputRootElement"] [data-baseweb="input"] {
            border: 1px solid #bfdbfe !important;
            border-radius: 10px !important;
            background: #ffffff !important;
            box-shadow: none !important;
        }
        .st-key-password_reset_fields_wrap [data-testid="stTextInputRootElement"] [data-baseweb="input"]:focus-within {
            border-color: #38bdf8 !important;
            box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.16) !important;
        }
        .st-key-password_reset_fields_wrap [data-testid="stTextInputRootElement"] input {
            min-height: 1.95rem !important;
            border: none !important;
            background: transparent !important;
            color: #0f172a !important;
        }
        html body .stApp input[type="password"]::-ms-reveal,
        html body .stApp input[type="password"]::-ms-clear,
        html body .stApp input[type="password"]::-webkit-password-toggle-button,
        html body .stApp input[type="password"]::-webkit-credentials-auto-fill-button,
        html body .stApp input[type="password"]::-webkit-contacts-auto-fill-button {
            display: none !important;
            visibility: hidden !important;
            pointer-events: none !important;
        }
        .st-key-password_reset_submit_btn .stButton > button,
        .st-key-password_reset_submit_btn button,
        .st-key-password_reset_submit_btn [data-testid^="baseButton"] {
            border: 1px solid #0284c7 !important;
            background: linear-gradient(120deg, #0284c7 0%, #0ea5e9 55%, #22d3ee 100%) !important;
            color: #ffffff !important;
            border-radius: 9px !important;
            font-size: 0.78rem !important;
            font-weight: 800 !important;
            min-height: 1.9rem !important;
            padding: 0.16rem 0.74rem !important;
            box-shadow: 0 8px 16px rgba(2, 132, 199, 0.22) !important;
        }
        .st-key-password_reset_submit_btn .stButton > button:hover,
        .st-key-password_reset_submit_btn button:hover,
        .st-key-password_reset_submit_btn [data-testid^="baseButton"]:hover {
            border-color: #0369a1 !important;
            transform: translateY(-1px) !important;
            filter: brightness(1.04);
        }
        .st-key-email_verification_panel_wrap [data-testid="stHorizontalBlock"] {
            align-items: center;
        }
        .st-key-email_verification_panel_wrap [data-testid="stTextInputRootElement"] > div {
            max-width: 26rem;
            margin: 0 auto;
        }
        .st-key-email_verification_panel_wrap [data-testid="stTextInputRootElement"] [data-baseweb="input"] {
            border: 1px solid #bfdbfe !important;
            border-radius: 10px !important;
            background: #ffffff !important;
            box-shadow: none !important;
        }
        .st-key-email_verification_panel_wrap [data-testid="stTextInputRootElement"] [data-baseweb="input"]:focus-within {
            border-color: #38bdf8 !important;
            box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.16) !important;
        }
        .st-key-email_verification_panel_wrap [data-testid="stTextInputRootElement"] input {
            min-height: 1.95rem !important;
            border: none !important;
            background: transparent !important;
            color: #0f172a !important;
        }
        .st-key-email_verification_actions [data-testid="stHorizontalBlock"] {
            align-items: center;
            gap: 0.4rem !important;
        }
        .st-key-email_verify_btn .stButton > button,
        .st-key-email_verify_btn button,
        .st-key-email_verify_btn [data-testid^="baseButton"] {
            border: 1px solid #0284c7 !important;
            background: linear-gradient(120deg, #0284c7 0%, #0ea5e9 55%, #22d3ee 100%) !important;
            color: #ffffff !important;
            border-radius: 8px !important;
            min-height: 1.8rem !important;
            font-size: 0.75rem !important;
            font-weight: 800 !important;
            padding: 0.1rem 0.58rem !important;
        }
        .st-key-email_resend_btn .stButton > button,
        .st-key-email_resend_btn button,
        .st-key-email_resend_btn [data-testid^="baseButton"] {
            border: 1px solid #7dd3fc !important;
            background: #ffffff !important;
            color: #0369a1 !important;
            border-radius: 8px !important;
            min-height: 1.8rem !important;
            font-size: 0.74rem !important;
            font-weight: 700 !important;
            padding: 0.1rem 0.58rem !important;
        }
        .st-key-email_cancel_btn .stButton > button,
        .st-key-email_cancel_btn button,
        .st-key-email_cancel_btn [data-testid^="baseButton"] {
            border: 1px solid #cbd5e1 !important;
            background: #ffffff !important;
            color: #475569 !important;
            border-radius: 8px !important;
            min-height: 1.8rem !important;
            font-size: 0.74rem !important;
            font-weight: 700 !important;
            padding: 0.1rem 0.58rem !important;
        }
        .st-key-password_reset_send_btn .stButton > button,
        .st-key-password_reset_send_btn button,
        .st-key-password_reset_send_btn [data-testid="baseButton-secondary"] {
            border: 1px solid #0369a1 !important;
            background: linear-gradient(120deg, #0284c7 0%, #0ea5e9 55%, #22d3ee 100%) !important;
            background-color: #0284c7 !important;
            color: #ffffff !important;
            border-radius: 999px !important;
            font-size: 0.74rem !important;
            font-weight: 800 !important;
            min-height: 1.58rem !important;
            min-width: 7.1rem !important;
            padding: 0.08rem 0.58rem !important;
            box-shadow: 0 6px 12px rgba(2, 132, 199, 0.24) !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            gap: 0.26rem !important;
            white-space: nowrap !important;
            line-height: 1 !important;
            transition: transform 120ms ease, border-color 120ms ease, filter 120ms ease !important;
        }
        .st-key-password_reset_send_btn .stButton > button p,
        .st-key-password_reset_send_btn .stButton > button span,
        .st-key-password_reset_send_btn button p,
        .st-key-password_reset_send_btn button span {
            margin: 0 !important;
            white-space: nowrap !important;
            line-height: 1 !important;
        }
        .st-key-password_reset_send_btn .stButton > button::before,
        .st-key-password_reset_send_btn button::before,
        .st-key-password_reset_send_btn [data-testid="baseButton-secondary"]::before {
            content: "âœ‰";
            font-size: 0.64rem;
            line-height: 1;
            opacity: 0.94;
            margin-right: 0.04rem;
        }
        .st-key-password_reset_send_btn .stButton > button:hover,
        .st-key-password_reset_send_btn button:hover,
        .st-key-password_reset_send_btn [data-testid="baseButton-secondary"]:hover {
            transform: translateY(-1px) !important;
            border-color: #075985 !important;
            filter: brightness(1.06);
        }
        .st-key-password_reset_send_btn .stButton > button::before,
        .st-key-password_reset_send_btn button::before,
        .st-key-password_reset_send_btn [data-testid="baseButton-secondary"]::before {
            content: "" !important;
            margin-right: 0 !important;
        }
        .st-key-password_reset_close_btn .stButton > button,
        .st-key-password_reset_close_btn button,
        .st-key-password_reset_close_btn [data-testid="baseButton-secondary"] {
            border: 1px solid #7dd3fc !important;
            background: linear-gradient(120deg, #eff9ff 0%, #dff6ff 100%) !important;
            background-color: #eff9ff !important;
            color: #0369a1 !important;
            border-radius: 999px !important;
            font-size: 0.72rem !important;
            font-weight: 800 !important;
            min-height: 1.58rem !important;
            min-width: 5.45rem !important;
            padding: 0.08rem 0.56rem !important;
            box-shadow: 0 4px 10px rgba(56, 189, 248, 0.14) !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            gap: 0.26rem !important;
            transition: transform 120ms ease, border-color 120ms ease, filter 120ms ease !important;
        }
        .st-key-password_reset_close_btn .stButton > button::before,
        .st-key-password_reset_close_btn button::before,
        .st-key-password_reset_close_btn [data-testid="baseButton-secondary"]::before {
            content: "âœ•";
            font-size: 0.62rem;
            line-height: 1;
            opacity: 0.86;
            margin-right: 0.04rem;
        }
        .st-key-password_reset_close_btn .stButton > button:hover,
        .st-key-password_reset_close_btn button:hover,
        .st-key-password_reset_close_btn [data-testid="baseButton-secondary"]:hover {
            transform: translateY(-1px) !important;
            border-color: #38bdf8 !important;
            filter: brightness(1.01);
        }
        .st-key-password_reset_close_btn .stButton > button,
        .st-key-password_reset_close_btn button,
        .st-key-password_reset_close_btn [data-testid^="baseButton"] {
            min-height: 1.58rem !important;
            font-size: 0.74rem !important;
            white-space: nowrap !important;
            line-height: 1 !important;
        }
        .st-key-password_reset_close_btn .stButton > button p,
        .st-key-password_reset_close_btn .stButton > button span,
        .st-key-password_reset_close_btn button p,
        .st-key-password_reset_close_btn button span {
            margin: 0 !important;
            white-space: nowrap !important;
            line-height: 1 !important;
        }
        .st-key-password_reset_close_btn .stButton > button::before,
        .st-key-password_reset_close_btn button::before,
        .st-key-password_reset_close_btn [data-testid^="baseButton"]::before {
            content: "" !important;
            margin-right: 0 !important;
            width: 0 !important;
        }
        .st-key-oauth_promo_code [data-testid="stTextInputRootElement"] > div {
            background: transparent !important;
        }
        .st-key-oauth_promo_code [data-testid="stTextInputRootElement"] input {
            background: #ffffff !important;
            border: 1px solid #ffffff !important;
            border-radius: 12px !important;
            color: #0f172a !important;
            box-shadow: 0 6px 16px rgba(15, 23, 42, 0.08) !important;
            text-align: center !important;
        }
        .st-key-oauth_promo_code [data-testid="stTextInputRootElement"] input::placeholder {
            color: #64748b !important;
            opacity: 1 !important;
        }
        .st-key-oauth_promo_code [data-testid="stTextInputRootElement"] input:focus,
        .st-key-oauth_promo_code [data-testid="stTextInputRootElement"] input:focus-visible {
            border: 1px solid #d1d5db !important;
            outline: none !important;
        }
        .st-key-oauth_promo_send button,
        .st-key-oauth_promo_send [data-testid="baseButton-secondary"] {
            border: 1px solid #ffffff !important;
            background: #ffffff !important;
            color: #0f172a !important;
            border-radius: 12px !important;
            min-height: 2.45rem !important;
            font-weight: 800 !important;
            box-shadow: 0 6px 16px rgba(15, 23, 42, 0.08) !important;
        }
        .st-key-oauth_promo_send button:hover,
        .st-key-oauth_promo_send [data-testid="baseButton-secondary"]:hover {
            border: 1px solid #d1d5db !important;
            background: #f8fafc !important;
            transform: translateY(-1px);
        }
        .st-key-oauth_promo_send button p {
            margin: 0 !important;
            font-size: 1rem !important;
        }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #f8fbff 0%, #eefbf7 100%);
            border-right: 1px solid #d9e2ec;
        }
        [data-testid="stSidebarHeader"] {
            display: none !important;
        }
        [data-testid="stSidebarCollapseButton"] {
            display: none !important;
        }
        [data-testid="stSidebarCollapsedControl"] {
            display: none !important;
        }
        [data-testid="stSidebar"] [data-testid="stSidebarContent"] {
            padding-bottom: 0;
            height: 100vh;
            overflow: hidden !important;
        }
        [data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
            min-height: 100%;
            height: 100%;
            display: flex;
            flex-direction: column;
            overflow: hidden !important;
        }
        .st-key-sidebar_menu_body {
            flex: 1 1 auto;
            overflow: hidden;
        }
        .ai-sidebar-signed {
            margin: 0 0 6px 0;
            color: #0f172a;
            font-size: 0.82rem;
            font-weight: 600;
        }
        .ai-sidebar-signed strong {
            color: #0b3b6f;
            font-weight: 800;
        }
        .st-key-sidebar_signed_row [data-testid="stHorizontalBlock"] {
            align-items: center;
        }
        .st-key-sidebar_header_logout .stButton,
        .st-key-sidebar_header_logout [data-testid="stButton"],
        .st-key-sidebar_header_logout_btn .stButton,
        .st-key-sidebar_header_logout_btn [data-testid="stButton"] {
            margin: 0 !important;
            display: flex !important;
            justify-content: flex-end !important;
        }
        .st-key-sidebar_header_logout .stButton > button,
        .st-key-sidebar_header_logout [data-testid="baseButton-secondary"],
        .st-key-sidebar_header_logout_btn .stButton > button,
        .st-key-sidebar_header_logout_btn [data-testid="baseButton-secondary"] {
            border: none !important;
            background: transparent !important;
            background-color: transparent !important;
            box-shadow: none !important;
            border-radius: 0 !important;
            min-height: 0 !important;
            min-width: 0 !important;
            width: auto !important;
            height: auto !important;
            padding: 0.02rem !important;
            margin: 0 !important;
            color: #9f1239 !important;
            font-size: 0 !important;
            line-height: 0 !important;
            font-weight: 800 !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            appearance: none !important;
            -webkit-appearance: none !important;
            text-transform: none !important;
            letter-spacing: 0.015em;
            white-space: nowrap !important;
            writing-mode: horizontal-tb !important;
            text-shadow: none !important;
            animation: none !important;
            transition: transform 140ms ease, color 140ms ease, filter 140ms ease !important;
        }
        .st-key-sidebar_header_logout .stButton > button p,
        .st-key-sidebar_header_logout .stButton > button span,
        .st-key-sidebar_header_logout_btn .stButton > button p,
        .st-key-sidebar_header_logout_btn .stButton > button span {
            margin: 0 !important;
            font-size: 0 !important;
            line-height: 0 !important;
            color: #9f1239 !important;
            font-weight: 800 !important;
            letter-spacing: 0.015em;
            white-space: nowrap !important;
            writing-mode: horizontal-tb !important;
            text-shadow: none !important;
        }
        .st-key-sidebar_header_logout .stButton > button svg,
        .st-key-sidebar_header_logout [data-testid="baseButton-secondary"] svg,
        .st-key-sidebar_header_logout_btn .stButton > button svg,
        .st-key-sidebar_header_logout_btn [data-testid="baseButton-secondary"] svg {
            width: 1rem !important;
            height: 1rem !important;
            color: #9f1239 !important;
            fill: currentColor !important;
        }
        .st-key-sidebar_header_logout .stButton > button:focus,
        .st-key-sidebar_header_logout .stButton > button:focus-visible,
        .st-key-sidebar_header_logout .stButton > button:active,
        .st-key-sidebar_header_logout [data-testid="baseButton-secondary"]:focus,
        .st-key-sidebar_header_logout [data-testid="baseButton-secondary"]:focus-visible,
        .st-key-sidebar_header_logout [data-testid="baseButton-secondary"]:active,
        .st-key-sidebar_header_logout_btn .stButton > button:focus,
        .st-key-sidebar_header_logout_btn .stButton > button:focus-visible,
        .st-key-sidebar_header_logout_btn .stButton > button:active,
        .st-key-sidebar_header_logout_btn [data-testid="baseButton-secondary"]:focus,
        .st-key-sidebar_header_logout_btn [data-testid="baseButton-secondary"]:focus-visible,
        .st-key-sidebar_header_logout_btn [data-testid="baseButton-secondary"]:active {
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
            outline: 0 !important;
        }
        .st-key-sidebar_header_logout .stButton > button:hover,
        .st-key-sidebar_header_logout [data-testid="baseButton-secondary"]:hover,
        .st-key-sidebar_header_logout_btn .stButton > button:hover,
        .st-key-sidebar_header_logout_btn [data-testid="baseButton-secondary"]:hover {
            border: none !important;
            background: transparent !important;
            color: #881337 !important;
            box-shadow: none !important;
            filter: saturate(1.06) !important;
            transform: translateX(1px) scale(1.06) !important;
            text-decoration: none;
            letter-spacing: 0.02em;
        }
        .st-key-sidebar_menu_toggle .stButton > button {
            border: none !important;
            background: linear-gradient(120deg, #0284c7 0%, #0ea5e9 55%, #22d3ee 100%) !important;
            color: #ffffff !important;
            border-radius: 999px !important;
            padding: 0.4rem 0.72rem !important;
            min-height: 0 !important;
            font-weight: 800 !important;
            font-size: 0.9rem !important;
            box-shadow: 0 8px 18px rgba(2, 132, 199, 0.35) !important;
            justify-content: flex-start !important;
            text-align: left !important;
            transition: transform 150ms ease, filter 150ms ease, box-shadow 150ms ease !important;
        }
        .st-key-sidebar_menu_toggle .stButton > button p {
            margin: 0 !important;
        }
        .st-key-sidebar_menu_toggle .stButton > button:hover {
            border: none !important;
            background: linear-gradient(120deg, #0284c7 0%, #06b6d4 60%, #22d3ee 100%) !important;
            transform: translateY(-1px) scale(1.01);
            filter: brightness(1.05);
            box-shadow: 0 10px 24px rgba(14, 165, 233, 0.42) !important;
        }
        .st-key-sidebar_nav_menu {
            margin-top: 4px;
            margin-bottom: 2px;
        }
        .st-key-sidebar_nav_menu [data-testid="stVerticalBlock"] {
            gap: 0.06rem !important;
        }
        .st-key-sidebar_nav_menu [data-testid="stElementContainer"] {
            margin-bottom: 0 !important;
        }
        .st-key-sidebar_nav_menu .stButton {
            margin: 0 !important;
        }
        .st-key-sidebar_nav_menu .stButton > button {
            border: none !important;
            background: transparent !important;
            color: #0c4a6e !important;
            border-radius: 0 !important;
            padding: 0.12rem 0 !important;
            min-height: 0 !important;
            font-weight: 700 !important;
            font-size: 0.84rem !important;
            box-shadow: none !important;
            justify-content: flex-start !important;
            text-align: left !important;
            transition: transform 140ms ease, color 140ms ease, filter 140ms ease !important;
        }
        .st-key-sidebar_nav_menu .stButton > button p {
            margin: 0 !important;
        }
        .st-key-sidebar_nav_menu .stButton > button:hover {
            border: none !important;
            background: transparent !important;
            color: #0284c7 !important;
            transform: translateX(3px);
            filter: drop-shadow(0 0 5px rgba(14, 165, 233, 0.32));
        }
        .st-key-full_chat_shell {
            border: 1px solid #dbeafe;
            border-radius: 18px;
            background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
            padding: 10px;
            box-shadow: 0 14px 30px rgba(30, 64, 175, 0.08);
        }
        .st-key-full_recent_chats {
            border: 1px solid #dbeafe;
            border-radius: 14px;
            background: #ffffff;
            padding: 8px 10px;
            min-height: 72vh;
        }
        .st-key-full_recent_chats .stButton > button {
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
            justify-content: flex-start !important;
            text-align: left !important;
            padding: 0.3rem 0 !important;
            min-height: 0 !important;
            color: #1e3a8a !important;
            border-radius: 0 !important;
            font-size: 0.84rem !important;
        }
        .st-key-full_recent_chats .stButton > button p {
            margin: 0 !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
        }
        .st-key-full_recent_chats .stButton > button:hover {
            color: #0f172a !important;
            transform: translateX(2px);
        }
        .st-key-full_chat_panel {
            border: 1px solid #dbeafe;
            border-radius: 14px;
            background: #ffffff;
            padding: 10px 12px;
            min-height: 72vh;
        }
        .st-key-full_chat_input_wrap .stButton > button {
            border-radius: 12px !important;
        }
        .st-key-full_scores_table {
            border: 1px solid #dbeafe;
            border-radius: 14px;
            background: #ffffff;
            padding: 8px;
        }
        .st-key-sidebar_recent_chats .stButton > button {
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
            justify-content: flex-start !important;
            text-align: left !important;
            padding: 0.22rem 0 !important;
            min-height: 0 !important;
            color: #1e3a8a !important;
            font-weight: 600 !important;
            border-radius: 0 !important;
        }
        .st-key-sidebar_recent_chats .stButton > button > div {
            width: 100%;
            overflow: hidden;
        }
        .st-key-sidebar_recent_chats .stButton > button p {
            margin: 0 !important;
            width: 100%;
            font-size: 0.82rem !important;
            line-height: 1.2 !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
        }
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_edit_"] button,
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_delete_"] button,
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_save_"] button,
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_cancel_"] button {
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
            border-radius: 0 !important;
            justify-content: center !important;
            text-align: center !important;
            padding: 0.2rem 0 !important;
            min-height: 0 !important;
            font-size: 0.95rem !important;
            font-weight: 700 !important;
            transition: transform 140ms ease, color 140ms ease, filter 140ms ease !important;
        }
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_edit_"] button,
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_save_"] button {
            color: #0f766e !important;
        }
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_delete_"] button,
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_cancel_"] button {
            color: #be123c !important;
        }
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_edit_"] button p,
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_delete_"] button p,
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_save_"] button p,
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_cancel_"] button p {
            font-size: 1rem !important;
            text-overflow: clip !important;
        }
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_edit_"] button:hover,
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_delete_"] button:hover,
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_save_"] button:hover,
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_cancel_"] button:hover {
            background: transparent !important;
            border: none !important;
            transform: translateY(-1px) scale(1.12) !important;
            filter: drop-shadow(0 0 6px rgba(15, 118, 110, 0.25));
        }
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_delete_"] button:hover,
        .st-key-sidebar_recent_chats [class*="st-key-sidebar_chat_cancel_"] button:hover {
            filter: drop-shadow(0 0 6px rgba(190, 24, 93, 0.3));
        }
        .st-key-sidebar_recent_chats .stButton > button:hover {
            color: #0f172a !important;
            transform: translateX(2px);
        }
        .st-key-zoswi_minimize button,
        .st-key-zoswi_reset button,
        .st-key-zoswi_close button {
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
            border-radius: 0 !important;
            padding: 0.08rem 0.22rem !important;
            min-height: 0 !important;
            color: #0b3b6f !important;
            font-weight: 700 !important;
            transition: transform 140ms ease, color 140ms ease, filter 140ms ease !important;
        }
        .st-key-zoswi_minimize button:hover,
        .st-key-zoswi_reset button:hover,
        .st-key-zoswi_close button:hover {
            background: transparent !important;
            border: none !important;
            color: #0284c7 !important;
            transform: translateY(-1px) scale(1.12) !important;
            filter: drop-shadow(0 0 6px rgba(2, 132, 199, 0.28));
        }
        .ai-sidebar-title {
            font-size: 1rem;
            font-weight: 800;
            color: #0b3b6f;
            margin: 4px 0 10px 0;
        }
        .ai-side-card {
            border: 1px solid #c7d2fe;
            background: #ffffff;
            border-radius: 14px;
            padding: 12px 12px 10px 12px;
            box-shadow: 0 8px 20px rgba(15, 23, 42, 0.06);
            margin-top: 6px;
        }
        .ai-side-card p {
            margin: 0 0 5px 0;
            color: #334e68;
            font-size: 0.9rem;
        }
        .ai-side-card .title {
            margin: 0 0 8px 0;
            color: #102a43;
            font-size: 0.98rem;
            font-weight: 700;
        }
        .st-key-sidebar_logout button {
            margin-top: 0;
            width: auto !important;
            height: auto !important;
            min-height: 0 !important;
            border-radius: 0 !important;
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
            color: #9f1239 !important;
            font-size: 1.6rem !important;
            font-weight: 700 !important;
            padding: 0 !important;
            line-height: 1 !important;
            transition: transform 150ms ease, color 150ms ease;
            filter: drop-shadow(0 0 4px rgba(190, 24, 93, 0.26));
            animation: ai-logout-float 2.8s ease-in-out infinite, ai-logout-glow 3s ease-in-out infinite;
        }
        .st-key-sidebar_logout button,
        .st-key-sidebar_logout button p {
            font-family: "Material Symbols Outlined", "Segoe UI Symbol", sans-serif !important;
            font-feature-settings: "liga";
            font-variation-settings: "FILL" 0, "wght" 500, "GRAD" 0, "opsz" 24;
            letter-spacing: normal !important;
            text-transform: none !important;
        }
        .st-key-sidebar_logout button:hover {
            border: none !important;
            background: transparent !important;
            color: #be123c !important;
            transform: translateX(2px) scale(1.1);
        }
        .st-key-sidebar_fixed_actions {
            position: relative;
            bottom: 0;
            width: 100%;
            z-index: 10;
            margin-top: auto;
            padding: 8px 0 8px 0;
            background: linear-gradient(
                180deg,
                rgba(248, 251, 255, 0) 0%,
                rgba(248, 251, 255, 0.96) 28%,
                rgba(238, 251, 247, 0.99) 100%
            );
            backdrop-filter: blur(4px);
            border-top: 1px solid rgba(148, 163, 184, 0.22);
        }
        .st-key-sidebar_fixed_actions [data-testid="stHorizontalBlock"] {
            gap: 10px;
        }
        .st-key-zoswi_widget {
            position: fixed;
            right: 14px;
            bottom: 14px;
            z-index: 1000;
            width: min(380px, calc(100vw - 24px));
            display: flex;
            flex-direction: column;
            align-items: flex-end;
        }
        .st-key-zoswi_panel {
            border: 1px solid #bfdbfe;
            background: linear-gradient(135deg, #ffffff 0%, #eff6ff 45%, #ecfeff 100%);
            background-size: 180% 180%;
            border-radius: 30px;
            padding: 10px 12px;
            box-shadow: 0 16px 34px rgba(30, 64, 175, 0.2);
            margin-bottom: 10px;
            position: relative;
            overflow: visible;
            backdrop-filter: blur(6px);
            transform-origin: bottom right;
            animation: zoswi-think-pop 420ms cubic-bezier(0.2, 0.8, 0.2, 1),
                       zoswi-think-breathe 3.8s ease-in-out infinite 420ms,
                       zoswi-panel-gradient 8s ease-in-out infinite 420ms;
        }
        .st-key-zoswi_panel::before,
        .st-key-zoswi_panel::after {
            content: "";
            position: absolute;
            border-radius: 50%;
            background: radial-gradient(circle at 35% 35%, #ffffff 0%, #eff6ff 100%);
            border: 1px solid #bfdbfe;
            box-shadow: 0 4px 12px rgba(30, 64, 175, 0.14);
            pointer-events: none;
            animation: zoswi-tail-bob 2.2s ease-in-out infinite;
        }
        .st-key-zoswi_panel::before {
            width: 14px;
            height: 14px;
            right: 46px;
            bottom: -12px;
            animation-delay: 0.1s;
        }
        .st-key-zoswi_panel::after {
            width: 9px;
            height: 9px;
            right: 30px;
            bottom: -23px;
            animation-delay: 0.35s;
        }
        .st-key-zoswi_panel .stButton > button {
            border-radius: 10px;
        }
        .st-key-zoswi_panel [data-testid="stVerticalBlockBorderWrapper"] {
            scroll-behavior: smooth;
        }
        .st-key-zoswi_panel .zoswi-msg {
            margin: 0.24rem 0 0.52rem 0;
        }
        .st-key-zoswi_panel .zoswi-msg.assistant {
            text-align: left;
        }
        .st-key-zoswi_panel .zoswi-msg.user {
            text-align: right;
        }
        .st-key-zoswi_panel .zoswi-msg-head {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 0.82rem;
            font-weight: 700;
            color: #1e3a8a;
            letter-spacing: 0.01em;
            margin-bottom: 2px;
        }
        .st-key-zoswi_panel .zoswi-msg.user .zoswi-msg-head {
            justify-content: flex-end;
            color: #0f766e;
        }
        .st-key-zoswi_panel .zoswi-msg-text {
            display: inline-block;
            max-width: 92%;
            color: #0f172a;
            font-size: 0.94rem;
            line-height: 1.4;
            white-space: pre-wrap;
            word-break: break-word;
        }
        .st-key-zoswi_panel .zoswi-msg-text strong {
            font-weight: 800;
            color: #0b1220;
        }
        .st-key-zoswi_panel .zoswi-msg-text code {
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
            background: rgba(148, 163, 184, 0.18);
            border: 1px solid rgba(148, 163, 184, 0.32);
            border-radius: 6px;
            padding: 0.05rem 0.28rem;
            font-size: 0.82em;
        }
        .st-key-zoswi_panel .zoswi-msg.user .zoswi-msg-text {
            text-align: left;
        }
        .st-key-zoswi_minimize button,
        .st-key-zoswi_reset button,
        .st-key-zoswi_close button {
            width: auto;
            height: auto;
            min-height: 0;
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
            color: #0b3b6f;
            font-weight: 800;
            font-size: 1.05rem;
            line-height: 1;
            border-radius: 0 !important;
            padding: 0.08rem 0.22rem !important;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-left: auto;
            transition: transform 140ms ease, color 140ms ease, filter 140ms ease;
        }
        .st-key-zoswi_minimize button:hover,
        .st-key-zoswi_reset button:hover,
        .st-key-zoswi_close button:hover {
            background: transparent !important;
            border: none !important;
            color: #0284c7 !important;
            transform: translateY(-1px) scale(1.12);
            filter: drop-shadow(0 0 6px rgba(2, 132, 199, 0.28));
        }
        @keyframes zoswi-pulse {
            0% {
                transform: translateY(0) scale(1);
                filter: saturate(1.2) brightness(1.06);
            }
            50% {
                transform: translateY(-4px) scale(1.13);
                filter: saturate(1.55) brightness(1.2);
            }
            100% {
                transform: translateY(0) scale(1);
                filter: saturate(1.2) brightness(1.06);
            }
        }
        .st-key-zoswi_fab {
            position: relative;
            overflow: visible;
        }
        .st-key-zoswi_fab::before {
            content: "";
            position: absolute;
            right: 10px;
            bottom: 8px;
            width: 56px;
            height: 56px;
            border-radius: 50%;
            background: radial-gradient(circle, rgba(56, 189, 248, 0.55) 0%, rgba(14, 116, 144, 0) 72%);
            filter: blur(6px);
            pointer-events: none;
            animation: zoswi-fab-halo 2.4s ease-in-out infinite;
        }
        .st-key-zoswi_fab::after {
            content: "âœ¦";
            position: absolute;
            right: 2px;
            bottom: 52px;
            font-size: 0.95rem;
            color: #0ea5e9;
            text-shadow: 0 0 10px rgba(14, 165, 233, 0.65);
            pointer-events: none;
            animation: zoswi-spark 2.8s ease-in-out infinite;
        }
        .st-key-zoswi_fab button {
            width: 76px;
            height: 76px;
            border-radius: 50%;
            border: none !important;
            background: transparent !important;
            color: #0f172a;
            font-size: 4.1rem !important;
            line-height: 1;
            padding: 0 !important;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: none !important;
            text-shadow: 0 10px 18px rgba(59, 130, 246, 0.5);
            animation: zoswi-pulse 1.65s ease-in-out infinite, zoswi-wiggle 5.6s ease-in-out infinite;
        }
        .st-key-zoswi_fab button p {
            margin: 0 !important;
            font-size: 4.1rem !important;
            line-height: 1 !important;
        }
        .st-key-zoswi_fab button:hover {
            filter: saturate(1.6) brightness(1.2);
        }
        .zoswi-think-symbol {
            font-size: 1.05rem;
            line-height: 1;
            margin-top: -2px;
            margin-bottom: 2px;
            display: inline-block;
            color: #7c3aed;
            filter: drop-shadow(0 0 6px rgba(168, 85, 247, 0.42));
            animation: zoswi-think-symbol 1.35s ease-in-out infinite;
        }
        @keyframes zoswi-think-pop {
            0% {
                opacity: 0;
                transform: translateY(22px) scale(0.88);
                filter: blur(8px);
            }
            70% {
                opacity: 1;
                transform: translateY(-2px) scale(1.03);
                filter: blur(0);
            }
            100% {
                opacity: 1;
                transform: translateY(0) scale(1);
                filter: blur(0);
            }
        }
        @keyframes zoswi-think-breathe {
            0%, 100% { box-shadow: 0 16px 34px rgba(30, 64, 175, 0.2); }
            50% { box-shadow: 0 18px 40px rgba(124, 58, 237, 0.24); }
        }
        @keyframes zoswi-panel-gradient {
            0%, 100% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
        }
        @keyframes zoswi-tail-bob {
            0%, 100% { transform: translateY(0) scale(1); opacity: 0.95; }
            50% { transform: translateY(-2px) scale(1.05); opacity: 1; }
        }
        @keyframes zoswi-fab-halo {
            0%, 100% { transform: scale(0.9); opacity: 0.58; }
            50% { transform: scale(1.16); opacity: 0.9; }
        }
        @keyframes zoswi-wiggle {
            0%, 80%, 100% { transform: rotate(0deg); }
            84% { transform: rotate(-6deg); }
            88% { transform: rotate(6deg); }
            92% { transform: rotate(-4deg); }
            96% { transform: rotate(3deg); }
        }
        @keyframes zoswi-spark {
            0%, 100% { opacity: 0.3; transform: translateY(1px) scale(0.85) rotate(-8deg); }
            50% { opacity: 1; transform: translateY(-4px) scale(1.14) rotate(8deg); }
        }
        @keyframes zoswi-think-symbol {
            0%, 100% { transform: translateY(0) scale(1); opacity: 0.76; }
            50% { transform: translateY(-3px) scale(1.14); opacity: 1; }
        }
        @keyframes ai-logout-float {
            0%, 100% { transform: translateY(0) scale(1); }
            50% { transform: translateY(-2px) scale(1.05); }
        }
        @keyframes ai-logout-glow {
            0%, 100% { filter: drop-shadow(0 0 4px rgba(190, 24, 93, 0.24)); }
            50% { filter: drop-shadow(0 0 10px rgba(225, 29, 72, 0.55)); }
        }
        @media (max-width: 980px) {
            [data-testid="stSidebar"] {
                width: min(86vw, 320px) !important;
            }
            .st-key-sidebar_signed_row [data-testid="stHorizontalBlock"] {
                align-items: center !important;
                gap: 0.3rem !important;
            }
            .st-key-sidebar_signed_row [data-testid="column"]:first-child {
                min-width: 0 !important;
            }
            .st-key-sidebar_signed_row [data-testid="column"]:last-child {
                width: auto !important;
                min-width: fit-content !important;
                flex: 0 0 auto !important;
            }
            .st-key-sidebar_header_logout .stButton > button,
            .st-key-sidebar_header_logout [data-testid="baseButton-secondary"],
            .st-key-sidebar_header_logout_btn .stButton > button,
            .st-key-sidebar_header_logout_btn [data-testid="baseButton-secondary"] {
                padding: 0.08rem !important;
                min-width: 1.65rem !important;
                min-height: 1.65rem !important;
                line-height: 1 !important;
                display: inline-flex !important;
                align-items: center !important;
                justify-content: center !important;
            }
            .st-key-sidebar_header_logout .stButton > button svg,
            .st-key-sidebar_header_logout [data-testid="baseButton-secondary"] svg,
            .st-key-sidebar_header_logout_btn .stButton > button svg,
            .st-key-sidebar_header_logout_btn [data-testid="baseButton-secondary"] svg {
                width: 1.08rem !important;
                height: 1.08rem !important;
            }
            .st-key-home_dashboard_input_cols [data-testid="stHorizontalBlock"],
            .st-key-careers_profile_setup_cols [data-testid="stHorizontalBlock"],
            .st-key-full_chat_shell [data-testid="stHorizontalBlock"] {
                flex-wrap: wrap !important;
                gap: 0.55rem !important;
            }
            .st-key-home_dashboard_input_cols [data-testid="column"],
            .st-key-careers_profile_setup_cols [data-testid="column"],
            .st-key-full_chat_shell [data-testid="column"] {
                flex: 1 1 100% !important;
                min-width: 100% !important;
                width: 100% !important;
            }
            .st-key-full_chat_panel {
                margin-top: 0.18rem;
            }
            .st-key-zoswi_widget {
                right: 8px;
                bottom: 8px;
                width: min(97vw, 420px);
            }
            .st-key-zoswi_panel {
                border-radius: 18px;
                padding: 0.52rem 0.62rem;
                margin-bottom: 8px;
            }
            .st-key-zoswi_panel [data-testid="stHorizontalBlock"] {
                align-items: center !important;
            }
            .st-key-zoswi_minimize button,
            .st-key-zoswi_reset button,
            .st-key-zoswi_close button {
                min-width: 1.55rem !important;
                min-height: 1.55rem !important;
                padding: 0 !important;
                line-height: 1 !important;
                display: inline-flex !important;
                align-items: center !important;
                justify-content: center !important;
            }
            .st-key-zoswi_fab::before {
                width: 44px;
                height: 44px;
                right: 8px;
                bottom: 7px;
            }
            .st-key-zoswi_fab::after {
                right: 0;
                bottom: 43px;
            }
            .st-key-zoswi_fab button {
                width: 62px;
                height: 62px;
                font-size: 3.3rem !important;
            }
            .st-key-zoswi_fab button p {
                font-size: 3.3rem !important;
            }
        }
        </style>
        <script>
        (function () {
            const hostWin = window.parent && window.parent.document ? window.parent : window;
            const hostDoc = hostWin && hostWin.document ? hostWin.document : document;
            if (!hostDoc || !hostDoc.body) {
                return;
            }
            function hideSubmitHints() {
                const hintTexts = new Set([
                    "",
                    "press enter to apply",
                    "press enter to submit",
                ]);
                const nodes = hostDoc.querySelectorAll("div, span, p, small, label");
                nodes.forEach((el) => {
                    const text = (el.textContent || "").trim().toLowerCase();
                    if (hintTexts.has(text)) {
                        el.style.display = "none";
                    }
                });
            }
            hideSubmitHints();
            if (hostWin.__zoswiSubmitHintsObserverActive) {
                return;
            }
            hostWin.__zoswiSubmitHintsObserverActive = true;
            const observer = new MutationObserver(() => hideSubmitHints());
            observer.observe(hostDoc.body, { childList: true, subtree: true });
        })();
        </script>
        """,
        unsafe_allow_html=True,
    )


