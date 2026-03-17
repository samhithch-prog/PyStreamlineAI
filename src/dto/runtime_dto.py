from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class PageConfigDTO:
    page_title: str
    layout: str = "wide"
    initial_sidebar_state: str = "expanded"


@dataclass(frozen=True)
class AppRuntimeHandlersDTO:
    bootstrap_runtime: Callable[[], None]
    init_db: Callable[[], None]
    init_state: Callable[[], None]
    sync_promo_codes_from_secrets: Callable[[], None]
    try_restore_user_from_cookie: Callable[[], None]
    render_auth_cookie_sync: Callable[[], None]
    render_auth_screen: Callable[[], None]
    render_main_screen: Callable[[], None]
    get_current_user: Callable[[], Any]
