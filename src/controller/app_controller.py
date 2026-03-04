from __future__ import annotations

import streamlit as st

from src.dto.runtime_dto import AppRuntimeHandlersDTO, PageConfigDTO


def run_app_runtime(config: PageConfigDTO, handlers: AppRuntimeHandlersDTO) -> None:
    """Top-level controller for app startup and page routing."""
    st.set_page_config(
        page_title=config.page_title,
        layout=config.layout,
        initial_sidebar_state=config.initial_sidebar_state,
    )
    handlers.init_db()
    handlers.init_state()
    handlers.sync_promo_codes_from_secrets()
    handlers.try_restore_user_from_cookie()
    handlers.render_auth_cookie_sync()

    if handlers.get_current_user() is None:
        handlers.render_auth_screen()
        return
    handlers.render_main_screen()

