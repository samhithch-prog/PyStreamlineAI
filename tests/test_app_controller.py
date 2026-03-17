from __future__ import annotations

from src.controller import app_controller
from src.dto.runtime_dto import AppRuntimeHandlersDTO, PageConfigDTO


def _build_handlers(current_user: object, calls: list[str]) -> AppRuntimeHandlersDTO:
    return AppRuntimeHandlersDTO(
        bootstrap_runtime=lambda: calls.append("bootstrap"),
        init_db=lambda: calls.append("init_db"),
        init_state=lambda: calls.append("init_state"),
        sync_promo_codes_from_secrets=lambda: calls.append("sync_promo"),
        try_restore_user_from_cookie=lambda: calls.append("restore_cookie"),
        render_auth_cookie_sync=lambda: calls.append("cookie_sync"),
        render_auth_screen=lambda: calls.append("render_auth"),
        render_main_screen=lambda: calls.append("render_main"),
        get_current_user=lambda: current_user,
    )


def test_run_app_runtime_renders_auth_when_user_missing(monkeypatch) -> None:
    calls: list[str] = []
    set_page_calls: list[dict[str, str]] = []

    monkeypatch.setattr(
        app_controller.st,
        "set_page_config",
        lambda **kwargs: set_page_calls.append(kwargs),
    )
    config = PageConfigDTO(page_title="My App", layout="wide", initial_sidebar_state="auto")
    handlers = _build_handlers(None, calls)

    app_controller.run_app_runtime(config, handlers)

    assert set_page_calls == [
        {
            "page_title": "My App",
            "layout": "wide",
            "initial_sidebar_state": "auto",
        }
    ]
    assert calls == [
        "bootstrap",
        "init_state",
        "restore_cookie",
        "cookie_sync",
        "render_auth",
    ]


def test_run_app_runtime_renders_main_when_user_exists(monkeypatch) -> None:
    calls: list[str] = []
    set_page_calls: list[dict[str, str]] = []

    monkeypatch.setattr(
        app_controller.st,
        "set_page_config",
        lambda **kwargs: set_page_calls.append(kwargs),
    )
    config = PageConfigDTO(page_title="My App", layout="centered", initial_sidebar_state="collapsed")
    handlers = _build_handlers({"id": 1}, calls)

    app_controller.run_app_runtime(config, handlers)

    assert set_page_calls == [
        {
            "page_title": "My App",
            "layout": "centered",
            "initial_sidebar_state": "collapsed",
        }
    ]
    assert calls == [
        "bootstrap",
        "init_state",
        "restore_cookie",
        "cookie_sync",
        "render_main",
    ]
