from __future__ import annotations

from src.dto.auth_dto import PasswordResetInputDTO, ServiceResultDTO
from src.dto.runtime_dto import AppRuntimeHandlersDTO, PageConfigDTO


def test_auth_dto_dataclasses_are_constructible() -> None:
    result = ServiceResultDTO(ok=True, message="done")
    request = PasswordResetInputDTO(
        email="user@example.com",
        otp_code="123456",
        new_password="Strong@123",
        confirm_password="Strong@123",
    )

    assert result.ok is True
    assert result.message == "done"
    assert request.email == "user@example.com"
    assert request.otp_code == "123456"


def test_runtime_dto_dataclasses_are_constructible() -> None:
    called: list[str] = []
    handlers = AppRuntimeHandlersDTO(
        bootstrap_runtime=lambda: called.append("bootstrap"),
        init_db=lambda: called.append("init_db"),
        init_state=lambda: called.append("init_state"),
        sync_promo_codes_from_secrets=lambda: called.append("sync_promo"),
        try_restore_user_from_cookie=lambda: called.append("restore_cookie"),
        render_auth_cookie_sync=lambda: called.append("render_cookie_sync"),
        render_auth_screen=lambda: called.append("render_auth"),
        render_main_screen=lambda: called.append("render_main"),
        get_current_user=lambda: None,
    )
    config = PageConfigDTO(page_title="Career Command Centre")

    handlers.bootstrap_runtime()
    handlers.render_auth_screen()

    assert called == ["bootstrap", "render_auth"]
    assert config.page_title == "Career Command Centre"
    assert config.layout == "wide"
