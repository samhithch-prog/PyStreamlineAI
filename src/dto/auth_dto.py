from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceResultDTO:
    ok: bool
    message: str


@dataclass(frozen=True)
class PasswordResetInputDTO:
    email: str
    otp_code: str
    new_password: str
    confirm_password: str

