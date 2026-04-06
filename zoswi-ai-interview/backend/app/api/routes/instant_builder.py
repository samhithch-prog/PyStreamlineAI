from __future__ import annotations

from fastapi import APIRouter

from app.schemas.instant_builder import InstantBuilderGenerateRequest, InstantBuilderGenerateResponse
from app.services.instant_builder_service import generate_instant_builder_payload

router = APIRouter(prefix="/instant-builder", tags=["instant-builder"])


@router.post("/generate", response_model=InstantBuilderGenerateResponse)
async def generate_instant_builder_app(payload: InstantBuilderGenerateRequest) -> InstantBuilderGenerateResponse:
    result = generate_instant_builder_payload(
        prompt=payload.prompt,
        current_spec=payload.current_spec,
        current_files=payload.current_files,
        current_preview_html=payload.current_preview_html,
    )
    return InstantBuilderGenerateResponse(**result)

