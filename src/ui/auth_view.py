from __future__ import annotations

import streamlit as st


def render_password_policy_checklist(password_policy: dict[str, bool], password: str, confirm_password: str) -> None:
    """Render live password policy hints used by auth forms."""
    password_started = bool(str(password or "").strip()) or bool(str(confirm_password or "").strip())
    if not password_started:
        return

    st.markdown(
        "<div style='font-size:0.82rem;color:#334155;font-weight:700;'>we care about you</div>",
        unsafe_allow_html=True,
    )
    for is_ok, label in [
        (bool(password_policy.get("min_length")), "8+ characters"),
        (bool(password_policy.get("has_upper")), "1 uppercase letter"),
        (bool(password_policy.get("has_special")), "1 special character"),
    ]:
        icon = "&#10003;" if is_ok else "&#10007;"
        color = "#16a34a" if is_ok else "#dc2626"
        st.markdown(
            f"<div style='font-size:0.82rem;color:{color};font-weight:600;'>{icon} {label}</div>",
            unsafe_allow_html=True,
        )

    if confirm_password:
        match_ok = str(password or "") == str(confirm_password or "")
        match_icon = "&#10003;" if match_ok else "&#10007;"
        match_color = "#16a34a" if match_ok else "#dc2626"
        st.markdown(
            f"<div style='font-size:0.82rem;color:{match_color};font-weight:600;'>{match_icon} passwords match</div>",
            unsafe_allow_html=True,
        )

