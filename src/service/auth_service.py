from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from src.dto.auth_dto import PasswordResetInputDTO, ServiceResultDTO


@dataclass(frozen=True)
class AuthServiceDependencies:
    email_code_name: str
    is_valid_email_address: Callable[[str], bool]
    can_send_email_otp: Callable[[], tuple[bool, str]]
    get_user_by_email: Callable[[str], dict[str, Any] | None]
    get_password_reset_resend_seconds: Callable[[], int]
    send_email_verification_otp: Callable[..., tuple[bool, str]]
    validate_password_strength: Callable[[str], tuple[bool, str]]
    verify_email_verification_otp: Callable[[int, str, str], tuple[bool, str]]
    hash_password: Callable[[str], str]
    update_password_and_revoke_sessions: Callable[[int, str], None]


class AuthService:
    """Auth business logic independent from Streamlit UI code."""

    def __init__(self, deps: AuthServiceDependencies) -> None:
        self._deps = deps

    def send_password_reset_code(self, email: str) -> ServiceResultDTO:
        cleaned_email = str(email or "").strip().lower()
        if not self._deps.is_valid_email_address(cleaned_email):
            return ServiceResultDTO(False, "Enter a valid email address.")

        config_ok, config_msg = self._deps.can_send_email_otp()
        if not config_ok:
            return ServiceResultDTO(False, config_msg)

        user = self._deps.get_user_by_email(cleaned_email)
        if user is None:
            return ServiceResultDTO(False, "Not an active user. Please create an account first.")

        user_id = int(user.get("id") or 0)
        resend_seconds = self._deps.get_password_reset_resend_seconds()
        sent, send_msg = self._deps.send_email_verification_otp(
            user_id,
            cleaned_email,
            resend_seconds_override=resend_seconds,
        )
        if sent:
            return ServiceResultDTO(True, f"Reset {self._deps.email_code_name} sent to your email.")
        return ServiceResultDTO(False, send_msg)

    def reset_password_with_code(self, request: PasswordResetInputDTO) -> ServiceResultDTO:
        cleaned_email = str(request.email or "").strip().lower()
        if not self._deps.is_valid_email_address(cleaned_email):
            return ServiceResultDTO(False, "Enter a valid email address.")
        if str(request.new_password or "") != str(request.confirm_password or ""):
            return ServiceResultDTO(False, "Passwords do not match.")

        password_ok, password_msg = self._deps.validate_password_strength(str(request.new_password or ""))
        if not password_ok:
            return ServiceResultDTO(False, password_msg)

        user = self._deps.get_user_by_email(cleaned_email)
        if user is None:
            return ServiceResultDTO(
                False,
                f"Invalid reset request. Check your email and {self._deps.email_code_name.lower()}.",
            )

        user_id = int(user.get("id") or 0)
        verified, verify_msg = self._deps.verify_email_verification_otp(user_id, cleaned_email, request.otp_code)
        if not verified:
            return ServiceResultDTO(False, verify_msg)

        new_hash = self._deps.hash_password(str(request.new_password or ""))
        self._deps.update_password_and_revoke_sessions(user_id, new_hash)
        return ServiceResultDTO(True, "Password reset successful. Please log in with your new password.")

