from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class InstantBuilderGenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=5000)
    current_spec: dict[str, Any] | None = None
    current_files: dict[str, str] | None = None
    current_preview_html: str | None = None


class InstantBuilderGenerateResponse(BaseModel):
    mode: str
    status_text: str
    spec: dict[str, Any] = Field(default_factory=dict)
    preview_html: str = ""
    files: dict[str, str] = Field(default_factory=dict)
    project_zip_base64: str = ""

