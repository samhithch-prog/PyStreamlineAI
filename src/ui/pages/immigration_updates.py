from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from src.app_runtime import *  # noqa: F401,F403
from src.repository.immigration_repository import ImmigrationRepository
from src.service.immigration_updates_service import (
    IMMIGRATION_REFRESH_SETTING_KEY,
    ImmigrationUpdatesService,
)

AUTO_REFRESH_CHECK_INTERVAL_SECONDS = 60


def _parse_iso_to_local(raw_value: str) -> str:
    cleaned = str(raw_value or "").strip()
    if not cleaned:
        return "Unknown time"
    try:
        dt = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local_dt = dt.astimezone()
        return local_dt.strftime("%b %d, %Y %I:%M %p %Z")
    except Exception:
        return cleaned


def _toggle_category(category: str) -> None:
    current = list(st.session_state.get("immigration_selected_categories", []))
    if category in current:
        st.session_state.immigration_selected_categories = [item for item in current if item != category]
        return
    current.append(category)
    st.session_state.immigration_selected_categories = current


def _render_feed_cards(items: list[dict[str, Any]]) -> None:
    if not items:
        st.info(
            "No updates found for this query/filter. Try terms like `H1B registration`, "
            "`selection notice`, or `visa bulletin EB2`."
        )
        return
    for index, item in enumerate(items):
        title = str(item.get("title", "")).strip() or "Immigration Update"
        summary = str(item.get("summary", "")).strip() or "Summary unavailable."
        source = str(item.get("source", "")).strip() or "Source unavailable"
        visa_category = str(item.get("visa_category", "")).strip() or "General"
        link = str(item.get("link", "")).strip()
        published_text = _parse_iso_to_local(str(item.get("published_date", "")).strip())
        tags = [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]
        with st.expander(f"{title}", expanded=index < 2):
            st.markdown(summary)
            st.caption(f"{source} | {visa_category} | {published_text}")
            if tags:
                st.markdown(" ".join(f"`{tag}`" for tag in tags[:8]))
            if link:
                st.markdown(f"[Read Original Source]({link})")


@st.cache_data(ttl=90, show_spinner=False)
def _cached_search_updates(
    query: str,
    selected_categories: tuple[str, ...],
    limit: int,
) -> list[dict[str, Any]]:
    repo = ImmigrationRepository(db_connect=db_connect)
    summary_model = get_config_value("IMMIGRATION_SUMMARY_MODEL", "immigration", "summary_model", "gpt-4o-mini")
    service = ImmigrationUpdatesService(
        repository=repo,
        ai_key_getter=get_zoswiai_key,
        llm_model=summary_model,
    )
    return service.search_updates(query=query, visa_categories=list(selected_categories), limit=limit)


@st.cache_data(ttl=120, show_spinner=False)
def _cached_recent_alerts(lookback_hours: int, limit: int) -> list[dict[str, Any]]:
    repo = ImmigrationRepository(db_connect=db_connect)
    summary_model = get_config_value("IMMIGRATION_SUMMARY_MODEL", "immigration", "summary_model", "gpt-4o-mini")
    service = ImmigrationUpdatesService(
        repository=repo,
        ai_key_getter=get_zoswiai_key,
        llm_model=summary_model,
    )
    return service.list_recent_alerts(lookback_hours=lookback_hours, limit=limit)


@st.cache_data(ttl=30, show_spinner=False)
def _cached_refresh_setting(setting_key: str) -> str:
    repo = ImmigrationRepository(db_connect=db_connect)
    return repo.get_setting(setting_key)


def render_immigration_updates_view(user: dict[str, Any]) -> None:
    _ = user
    is_mobile = is_mobile_browser()
    repo = ImmigrationRepository(db_connect=db_connect)
    summary_model = get_config_value("IMMIGRATION_SUMMARY_MODEL", "immigration", "summary_model", "gpt-4o-mini")
    service = ImmigrationUpdatesService(
        repository=repo,
        ai_key_getter=get_zoswiai_key,
        llm_model=summary_model,
    )

    categories = service.categories()
    if "immigration_selected_categories" not in st.session_state:
        st.session_state.immigration_selected_categories = []
    if "immigration_search_query" not in st.session_state:
        st.session_state.immigration_search_query = ""
    if "immigration_ai_brief" not in st.session_state:
        st.session_state.immigration_ai_brief = ""
    if "immigration_last_refresh_message" not in st.session_state:
        st.session_state.immigration_last_refresh_message = ""
    if "immigration_live_search_token" not in st.session_state:
        st.session_state.immigration_live_search_token = ""
    if "immigration_live_search_note" not in st.session_state:
        st.session_state.immigration_live_search_note = ""
    if "immigration_live_answer_token" not in st.session_state:
        st.session_state.immigration_live_answer_token = ""
    if "immigration_live_answer_text" not in st.session_state:
        st.session_state.immigration_live_answer_text = ""
    if "immigration_search_results_token" not in st.session_state:
        st.session_state.immigration_search_results_token = ""
    if "immigration_search_results" not in st.session_state:
        st.session_state.immigration_search_results = []
    if "immigration_only_visa_feed" not in st.session_state:
        st.session_state.immigration_only_visa_feed = False
    if "immigration_feed_page" not in st.session_state:
        st.session_state.immigration_feed_page = 1
    if "immigration_feed_page_size" not in st.session_state:
        st.session_state.immigration_feed_page_size = 8
    if "immigration_feed_result_token" not in st.session_state:
        st.session_state.immigration_feed_result_token = ""
    if "immigration_auto_refresh_checked_at" not in st.session_state:
        st.session_state.immigration_auto_refresh_checked_at = 0.0

    st.markdown(
        """
        <style>
        .immigration-shell {
            border: 1px solid #dbeafe;
            border-radius: 18px;
            padding: 1rem;
            background:
                radial-gradient(760px 260px at -12% -10%, rgba(14, 165, 233, 0.14) 0%, transparent 58%),
                radial-gradient(640px 260px at 100% 2%, rgba(20, 184, 166, 0.12) 0%, transparent 62%),
                #ffffff;
            box-shadow: 0 16px 34px rgba(15, 23, 42, 0.08);
        }
        .immigration-title {
            margin: 0;
            color: #0f172a;
            font-size: 1.42rem;
            font-weight: 900;
            line-height: 1.2;
        }
        .immigration-sub {
            margin: 0.3rem 0 0 0;
            color: #475569;
            font-size: 0.9rem;
        }
        .st-key-immigration_filter_buttons [data-testid="stVerticalBlock"] {
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: nowrap !important;
            align-items: center !important;
            gap: 0.35rem !important;
            overflow-x: auto !important;
            overflow-y: hidden !important;
            white-space: nowrap !important;
            padding-bottom: 0.1rem !important;
        }
        .st-key-immigration_filter_buttons [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] {
            display: inline-flex !important;
            width: auto !important;
            flex: 0 0 auto !important;
            margin: 0 !important;
        }
        .st-key-immigration_filter_buttons [data-testid="stPills"] {
            width: 100% !important;
        }
        .st-key-immigration_filter_buttons [data-testid="stPills"] [role="group"] {
            display: flex !important;
            flex-wrap: nowrap !important;
            gap: 0.45rem !important;
            overflow-x: auto !important;
            white-space: nowrap !important;
            padding-bottom: 0.15rem !important;
        }
        .st-key-immigration_filter_buttons [data-testid="stPills"] button {
            border-radius: 999px !important;
            border: 1px solid #93c5fd !important;
            background: linear-gradient(180deg, #f8fdff 0%, #eef6ff 100%) !important;
            color: #0f172a !important;
            font-weight: 700 !important;
            min-height: 2.3rem !important;
            padding: 0.45rem 0.9rem !important;
            box-shadow: 0 4px 12px rgba(56, 189, 248, 0.12) !important;
            transition: all 150ms ease !important;
        }
        .st-key-immigration_filter_buttons [data-testid="stPills"] button:hover {
            border-color: #38bdf8 !important;
            background: linear-gradient(180deg, #ffffff 0%, #e0f2fe 100%) !important;
        }
        .st-key-immigration_filter_buttons [data-testid="stPills"] button[aria-pressed="true"] {
            border-color: #0ea5e9 !important;
            background: linear-gradient(135deg, #0ea5e9 0%, #14b8a6 100%) !important;
            color: #ffffff !important;
            box-shadow: 0 8px 18px rgba(14, 165, 233, 0.28) !important;
        }
        .st-key-immigration_filter_buttons .stButton {
            width: auto !important;
            margin: 0 !important;
        }
        .st-key-immigration_filter_buttons .stButton > button,
        .st-key-immigration_filter_buttons .stButton [data-testid^="baseButton"] {
            border-radius: 999px !important;
            border: 1px solid #93c5fd !important;
            background: linear-gradient(180deg, #f8fdff 0%, #eef6ff 100%) !important;
            color: #0f172a !important;
            font-weight: 700 !important;
            min-height: 2.45rem !important;
            width: auto !important;
            padding-left: 0.9rem !important;
            padding-right: 0.9rem !important;
            box-shadow: 0 4px 14px rgba(56, 189, 248, 0.14) !important;
            transition: all 160ms ease !important;
        }
        .st-key-immigration_filter_buttons .stButton > button:hover,
        .st-key-immigration_filter_buttons .stButton [data-testid^="baseButton"]:hover {
            border-color: #38bdf8 !important;
            background: linear-gradient(180deg, #ffffff 0%, #e0f2fe 100%) !important;
            transform: translateY(-1px) !important;
            box-shadow: 0 8px 20px rgba(14, 165, 233, 0.18) !important;
        }
        .st-key-immigration_search_btn_wrap .stButton > button,
        .st-key-immigration_search_btn_wrap .stButton [data-testid^="baseButton"] {
            border: 0 !important;
            border-radius: 12px !important;
            min-height: 2.55rem !important;
            color: #ffffff !important;
            font-weight: 800 !important;
            background: linear-gradient(135deg, #0ea5e9 0%, #14b8a6 100%) !important;
            box-shadow: 0 10px 24px rgba(14, 165, 233, 0.28) !important;
        }
        .st-key-immigration_search_btn_wrap .stButton > button:hover,
        .st-key-immigration_search_btn_wrap .stButton [data-testid^="baseButton"]:hover {
            filter: brightness(1.03) saturate(1.05) !important;
            transform: translateY(-1px) !important;
            box-shadow: 0 12px 28px rgba(20, 184, 166, 0.26) !important;
        }
        .st-key-immigration_refresh_btn_wrap .stButton > button,
        .st-key-immigration_refresh_btn_wrap .stButton [data-testid^="baseButton"] {
            border-radius: 12px !important;
            min-height: 2.55rem !important;
            border: 1px solid #7dd3fc !important;
            color: #0f172a !important;
            font-weight: 700 !important;
            background: linear-gradient(180deg, #ffffff 0%, #f0f9ff 100%) !important;
        }
        .st-key-immigration_refresh_btn_wrap .stButton > button:hover,
        .st-key-immigration_refresh_btn_wrap .stButton [data-testid^="baseButton"]:hover {
            border-color: #38bdf8 !important;
            background: linear-gradient(180deg, #ffffff 0%, #e0f2fe 100%) !important;
        }
        </style>
        <div class="immigration-shell">
            <h2 class="immigration-title">Immigration &amp; Visa Updates</h2>
            <p class="immigration-sub">
                Centralized policy intelligence from trusted sources including USCIS, Department of State, and
                immigration law updates. Summaries are informational only and not legal advice.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if is_mobile:
        query = st.text_input(
            "Search immigration topics",
            key="immigration_search_query",
            placeholder="Search immigration topics (e.g., H1B lottery, STEM OPT extension, visa bulletin EB2)",
            label_visibility="collapsed",
        )
        search_action_col, refresh_action_col = st.columns(2, gap="small")
        with search_action_col:
            with st.container(key="immigration_search_btn_wrap"):
                search_clicked = st.button(
                    "Search",
                    key="immigration_search_now",
                    icon=":material/travel_explore:",
                    use_container_width=True,
                    type="primary",
                )
        with refresh_action_col:
            with st.container(key="immigration_refresh_btn_wrap"):
                refresh_clicked = st.button(
                    "Refresh",
                    key="immigration_refresh_now",
                    icon=":material/autorenew:",
                    use_container_width=True,
                )
    else:
        search_col, search_action_col, refresh_action_col = st.columns([6.2, 1.9, 1.9], gap="small")
        with search_col:
            query = st.text_input(
                "Search immigration topics",
                key="immigration_search_query",
                placeholder="Search immigration topics (e.g., H1B lottery, STEM OPT extension, visa bulletin EB2)",
                label_visibility="collapsed",
            )
        with search_action_col:
            with st.container(key="immigration_search_btn_wrap"):
                search_clicked = st.button(
                    "Search",
                    key="immigration_search_now",
                    icon=":material/travel_explore:",
                    use_container_width=True,
                    type="primary",
                )
        with refresh_action_col:
            with st.container(key="immigration_refresh_btn_wrap"):
                refresh_clicked = st.button(
                    "Refresh",
                    key="immigration_refresh_now",
                    icon=":material/autorenew:",
                    use_container_width=True,
                )

    st.caption(
        "Source note: Updates shown here are pulled from official/public immigration sources. "
        "ZoSwi AI only summarizes and explains the source data."
    )

    if refresh_clicked:
        with st.spinner("Refreshing immigration updates..."):
            refresh_result = service.refresh_updates(force=True, interval_hours=6)
        _cached_search_updates.clear()
        _cached_recent_alerts.clear()
        _cached_refresh_setting.clear()
        st.session_state.immigration_last_refresh_message = refresh_result.message
        st.session_state.immigration_auto_refresh_checked_at = time.time()
        st.session_state.immigration_ai_brief = ""
        st.session_state.immigration_live_search_token = ""
        st.session_state.immigration_live_search_note = ""
        st.session_state.immigration_live_answer_token = ""
        st.session_state.immigration_live_answer_text = ""
        st.session_state.immigration_search_results_token = ""
        st.session_state.immigration_search_results = []
        st.session_state.immigration_feed_page = 1
        st.session_state.immigration_feed_result_token = ""
    else:
        now_ts = time.time()
        last_check_ts = float(st.session_state.get("immigration_auto_refresh_checked_at", 0.0) or 0.0)
        if now_ts - last_check_ts >= AUTO_REFRESH_CHECK_INTERVAL_SECONDS:
            refresh_result = service.refresh_updates(force=False, interval_hours=6)
            st.session_state.immigration_auto_refresh_checked_at = now_ts
            if refresh_result.refreshed:
                _cached_search_updates.clear()
                _cached_recent_alerts.clear()
                _cached_refresh_setting.clear()
                st.session_state.immigration_last_refresh_message = refresh_result.message

    with st.container(key="immigration_filter_buttons"):
        st.markdown("**Quick Filters**")
        previous_selected = [
            item for item in st.session_state.get("immigration_selected_categories", []) if item in categories
        ]
        selected_from_ui = st.pills(
            "Quick Filters",
            options=categories,
            selection_mode="multi",
            default=previous_selected,
            key="immigration_quick_filter_pills",
            label_visibility="collapsed",
        )
        updated_selected = [item for item in (selected_from_ui or []) if item in categories]
        if updated_selected != previous_selected:
            st.session_state.immigration_selected_categories = updated_selected
            st.session_state.immigration_search_results_token = ""
            st.session_state.immigration_search_results = []
            st.session_state.immigration_live_answer_token = ""
            st.session_state.immigration_live_answer_text = ""
            st.session_state.immigration_live_search_note = ""
            st.session_state.immigration_feed_page = 1
            st.session_state.immigration_feed_result_token = ""
            st.rerun()

    selected_categories = [
        item for item in st.session_state.get("immigration_selected_categories", []) if item in categories
    ]
    cleaned_query = str(query or "").strip()
    query_token = f"{cleaned_query.lower()}|{'|'.join(sorted(selected_categories))}"
    updates: list[dict[str, Any]]
    if not cleaned_query:
        updates = _cached_search_updates(
            query="",
            selected_categories=tuple(selected_categories),
            limit=40,
        )
        st.session_state.immigration_live_search_token = ""
        st.session_state.immigration_live_search_note = ""
        st.session_state.immigration_live_answer_token = ""
        st.session_state.immigration_live_answer_text = ""
        st.session_state.immigration_search_results_token = ""
        st.session_state.immigration_search_results = []
    elif search_clicked:
        with st.spinner("Checking live immigration sources for this query..."):
            updates, live_note, _live_refresh_used = service.search_updates_live(
                query=cleaned_query,
                visa_categories=selected_categories,
                limit=40,
                force_refresh_on_miss=True,
            )
        _cached_search_updates.clear()
        _cached_recent_alerts.clear()
        _cached_refresh_setting.clear()
        st.session_state.immigration_live_search_token = query_token
        st.session_state.immigration_search_results_token = query_token
        st.session_state.immigration_search_results = updates
        st.session_state.immigration_live_search_note = str(live_note or "").strip()
        answer_token = f"{query_token}|{len(updates)}"
        with st.spinner("Preparing a direct answer from live updates..."):
            st.session_state.immigration_live_answer_text = service.answer_query_from_updates(cleaned_query, updates)
        st.session_state.immigration_live_answer_token = answer_token
    elif st.session_state.get("immigration_search_results_token", "") == query_token:
        updates = list(st.session_state.get("immigration_search_results", []))
    else:
        updates = _cached_search_updates(
            query="",
            selected_categories=tuple(selected_categories),
            limit=40,
        )
        st.session_state.immigration_live_search_note = "Click Search to run live lookup for this query."
        st.session_state.immigration_live_answer_token = ""
        st.session_state.immigration_live_answer_text = ""

    alerts = _cached_recent_alerts(lookback_hours=48, limit=6)
    last_refresh_text = _cached_refresh_setting(IMMIGRATION_REFRESH_SETTING_KEY)
    if st.session_state.get("immigration_last_refresh_message"):
        st.caption(st.session_state.get("immigration_last_refresh_message"))
    if last_refresh_text:
        st.caption(f"Last refresh: {_parse_iso_to_local(last_refresh_text)}")
    if st.session_state.get("immigration_live_search_note"):
        st.caption(st.session_state.get("immigration_live_search_note"))
    if st.session_state.get("immigration_live_answer_text"):
        st.markdown("### ZoSwi Answer")
        st.info(str(st.session_state.get("immigration_live_answer_text", "")).strip())
        st.caption(
            "Privacy note: This answer is generated from your query and live source updates. "
            "Please avoid entering sensitive personal information."
        )

    def _render_feed_panel() -> None:
        feed_title_col, feed_toggle_col = st.columns([6.8, 2.2], gap="small")
        if is_mobile:
            feed_title_col, feed_toggle_col = st.columns([3.8, 2.2], gap="small")
        with feed_title_col:
            st.markdown("### Latest Updates Feed")
        with feed_toggle_col:
            st.toggle(
                "Only VISA related",
                key="immigration_only_visa_feed",
                label_visibility="visible",
            )
        if st.session_state.get("immigration_only_visa_feed"):
            visa_only_categories = {"H1B", "F1", "OPT", "STEM OPT", "Visa Bulletin", "Green Card"}
            updates_for_feed = [
                item
                for item in updates
                if str(item.get("visa_category", "")).strip() in visa_only_categories
            ]
        else:
            updates_for_feed = updates
        feed_token = (
            f"{cleaned_query.lower()}|{'|'.join(sorted(selected_categories))}|"
            f"{int(bool(st.session_state.get('immigration_only_visa_feed')))}|{len(updates_for_feed)}|"
            f"{','.join(str(item.get('id', '')) for item in updates_for_feed[:20])}"
        )
        if feed_token != st.session_state.get("immigration_feed_result_token", ""):
            st.session_state.immigration_feed_result_token = feed_token
            st.session_state.immigration_feed_page = 1

        page_size = max(4, min(20, int(st.session_state.get("immigration_feed_page_size", 8) or 8)))
        st.session_state.immigration_feed_page_size = page_size
        total_items = len(updates_for_feed)
        total_pages = max(1, (total_items + page_size - 1) // page_size)
        current_page = max(1, min(total_pages, int(st.session_state.get("immigration_feed_page", 1) or 1)))
        st.session_state.immigration_feed_page = current_page

        if is_mobile:
            pager_col1, pager_col2 = st.columns(2, gap="small")
            with pager_col1:
                if st.button("Prev", key="immigration_feed_prev", use_container_width=True, disabled=current_page <= 1):
                    st.session_state.immigration_feed_page = max(1, current_page - 1)
                    st.rerun()
            with pager_col2:
                if st.button("Next", key="immigration_feed_next", use_container_width=True, disabled=current_page >= total_pages):
                    st.session_state.immigration_feed_page = min(total_pages, current_page + 1)
                    st.rerun()
            page_size_selected = st.selectbox(
                "Per page",
                options=[6, 8, 10, 12, 16],
                index=[6, 8, 10, 12, 16].index(page_size) if page_size in {6, 8, 10, 12, 16} else 1,
                key="immigration_feed_page_size_select",
                label_visibility="visible",
            )
            if int(page_size_selected) != page_size:
                st.session_state.immigration_feed_page_size = int(page_size_selected)
                st.session_state.immigration_feed_page = 1
                st.rerun()
            st.caption(f"Page {current_page} of {total_pages} ({total_items} updates)")
        else:
            pager_col1, pager_col2, pager_col3, pager_col4 = st.columns([1.1, 1.4, 1.5, 4.0], gap="small")
            with pager_col1:
                if st.button("Prev", key="immigration_feed_prev", use_container_width=True, disabled=current_page <= 1):
                    st.session_state.immigration_feed_page = max(1, current_page - 1)
                    st.rerun()
            with pager_col2:
                if st.button("Next", key="immigration_feed_next", use_container_width=True, disabled=current_page >= total_pages):
                    st.session_state.immigration_feed_page = min(total_pages, current_page + 1)
                    st.rerun()
            with pager_col3:
                page_size_selected = st.selectbox(
                    "Per page",
                    options=[6, 8, 10, 12, 16],
                    index=[6, 8, 10, 12, 16].index(page_size) if page_size in {6, 8, 10, 12, 16} else 1,
                    key="immigration_feed_page_size_select",
                    label_visibility="collapsed",
                )
                if int(page_size_selected) != page_size:
                    st.session_state.immigration_feed_page_size = int(page_size_selected)
                    st.session_state.immigration_feed_page = 1
                    st.rerun()
            with pager_col4:
                st.caption(f"Showing page {current_page} of {total_pages} ({total_items} total updates)")

        start_idx = (current_page - 1) * page_size
        end_idx = start_idx + page_size
        _render_feed_cards(updates_for_feed[start_idx:end_idx])

    def _render_ai_summary_panel() -> None:
        st.markdown("### AI Summary Panel")
        if st.button("Generate AI Brief", key="immigration_generate_ai_brief", use_container_width=True):
            with st.spinner("Generating AI summary..."):
                st.session_state.immigration_ai_brief = service.build_ai_brief(
                    updates,
                    query=cleaned_query,
                    categories=selected_categories,
                )
        if not st.session_state.get("immigration_ai_brief"):
            st.info("Click **Generate AI Brief** to see a concise policy snapshot.")
        else:
            st.markdown(str(st.session_state.get("immigration_ai_brief", "")).strip())

        st.markdown("### Latest Alerts")
        if not alerts:
            st.caption("No recent alerts in the configured lookback window.")
        else:
            for alert in alerts:
                title = str(alert.get("title", "")).strip()
                category = str(alert.get("visa_category", "")).strip() or "General"
                published = _parse_iso_to_local(str(alert.get("published_date", "")).strip())
                link = str(alert.get("link", "")).strip()
                st.markdown(f"**{title}**")
                st.caption(f"{category} | {published}")
                if link:
                    st.markdown(f"[Open Source]({link})")
                st.markdown("---")

    if is_mobile:
        _render_feed_panel()
        st.markdown("---")
        _render_ai_summary_panel()
    else:
        left_col, right_col = st.columns([2.2, 1], gap="large")
        with left_col:
            _render_feed_panel()
        with right_col:
            _render_ai_summary_panel()
