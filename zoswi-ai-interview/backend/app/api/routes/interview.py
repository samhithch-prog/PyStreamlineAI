import base64
import json
import logging
import uuid

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.api.deps import (
    get_ai_service,
    get_interview_engine,
    get_interview_service,
    get_scoring_engine,
    require_roles,
)
from app.core.auth import AuthContext, UserRole, decode_ws_token
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.exceptions import AppError
from app.core.metrics import metrics_store
from app.core.rate_limit import enforce_candidate_interview_limits, enforce_ws_event_limit, limiter
from app.repositories.interview_repository import InterviewRepository
from app.schemas.interview import InterviewResultResponse, StartInterviewRequest, StartInterviewResponse
from app.services.interview_service import InterviewService

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(tags=["interview"])


def _normalize_interview_type(raw_value: str) -> str:
    cleaned = str(raw_value or "").strip().lower().replace(" ", "_").replace("-", "_")
    if cleaned in {"technical", "behavioral", "behavioural"}:
        return "behavioral" if cleaned == "behavioural" else cleaned
    return "mixed"


@router.post("/start-interview", response_model=StartInterviewResponse)
async def start_interview(
    payload: StartInterviewRequest,
    service: InterviewService = Depends(get_interview_service),
    auth_ctx: AuthContext = Depends(require_roles(UserRole.candidate, UserRole.recruiter, UserRole.admin)),
) -> StartInterviewResponse:
    interview_type = _normalize_interview_type(payload.interview_type)
    if auth_ctx.role == UserRole.candidate:
        await enforce_candidate_interview_limits(auth_ctx.user_id, service.repository.db)
    return await service.start_interview(
        payload,
        interview_type=interview_type,
        owner_user_id=auth_ctx.user_id,
        org_id=auth_ctx.org_id or "",
    )


@router.get("/interview-result", response_model=InterviewResultResponse)
async def get_interview_result(
    session_id: uuid.UUID,
    service: InterviewService = Depends(get_interview_service),
    auth_ctx: AuthContext = Depends(require_roles(UserRole.candidate, UserRole.recruiter, UserRole.admin)),
) -> InterviewResultResponse:
    session = await service.repository.get_session(session_id)
    if session is None:
        raise AppError(status_code=404, message="Interview session not found.")
    if (
        auth_ctx.role == UserRole.candidate
        and str(session.owner_user_id or "").strip()
        and str(session.owner_user_id).strip() != auth_ctx.user_id
    ):
        raise AppError(status_code=403, message="Candidate cannot access this interview result.")
    return await service.get_interview_result(session_id=session_id)


@router.websocket("/ws/interview")
async def interview_websocket(websocket: WebSocket):
    ai_service = get_ai_service()
    interview_engine = get_interview_engine()
    scoring_engine = get_scoring_engine()

    query_ws_token = str(websocket.query_params.get("ws_token", "")).strip()
    query_session_id = str(websocket.query_params.get("session_id", "")).strip()
    bound_session_id: uuid.UUID | None = None
    if query_session_id:
        try:
            bound_session_id = uuid.UUID(query_session_id)
        except Exception:
            bound_session_id = None

    try:
        if not query_ws_token:
            await websocket.close(code=1008, reason="Missing ws_token")
            return
        auth_ctx = decode_ws_token(query_ws_token, expected_session_id=bound_session_id)
    except Exception:
        await websocket.close(code=1008, reason="Invalid websocket token")
        return

    await websocket.accept()

    active_session_id: uuid.UUID | None = bound_session_id
    active_interview_type = "mixed"
    active_mime_type = "audio/webm"
    candidate_audio_buffer = bytearray()

    await websocket.send_json({"type": "connection_status", "status": "connected"})

    try:
        while True:
            await enforce_ws_event_limit(auth_ctx.user_id, str(active_session_id or bound_session_id or "pending"))

            raw_message = await websocket.receive_text()
            try:
                payload = json.loads(raw_message)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON payload."})
                continue

            message_type = payload.get("type")

            if message_type == "session_start":
                candidate_name = str(payload.get("candidate_name", "")).strip()
                role = str(payload.get("role", "Software Engineer")).strip() or "Software Engineer"
                interview_type = _normalize_interview_type(str(payload.get("interview_type", "mixed")))
                payload_session_id = str(payload.get("session_id", "")).strip()
                session_id = active_session_id
                if payload_session_id:
                    try:
                        session_id = uuid.UUID(payload_session_id)
                    except Exception:
                        await websocket.send_json({"type": "error", "message": "Invalid session_id format."})
                        continue

                if session_id is None:
                    await websocket.send_json({"type": "error", "message": "session_id is required for authenticated websocket sessions."})
                    continue

                async with SessionLocal() as db:
                    repository = InterviewRepository(db)
                    service = InterviewService(
                        repository=repository,
                        ai_service=ai_service,
                        interview_engine=interview_engine,
                        scoring_engine=scoring_engine,
                    )

                    if session_id is not None:
                        existing = await repository.get_session(session_id)
                        if existing is None:
                            await websocket.send_json({"type": "error", "message": "Interview session not found."})
                            continue
                        if (
                            auth_ctx.role == UserRole.candidate
                            and str(existing.owner_user_id or "").strip()
                            and str(existing.owner_user_id).strip() != auth_ctx.user_id
                        ):
                            await websocket.send_json({"type": "error", "message": "Session ownership mismatch."})
                            continue
                        latest_question = await repository.get_latest_ai_question(existing.id)
                        opening_question = latest_question.question_text if latest_question else existing.current_question
                        start_response = StartInterviewResponse(
                            session_id=existing.id,
                            websocket_path="/ws/interview",
                            opening_question=opening_question or "Welcome. Let's begin.",
                            interview_type=existing.interview_type,
                            interview_duration_seconds=settings.interview_duration_seconds,
                            max_turns=existing.max_turns,
                        )
                    else:
                        if len(candidate_name) < 2:
                            await websocket.send_json({"type": "error", "message": "candidate_name is required."})
                            continue
                        if auth_ctx.role == UserRole.candidate:
                            await enforce_candidate_interview_limits(auth_ctx.user_id, db)
                        start_response = await service.start_interview(
                            StartInterviewRequest(
                                candidate_name=candidate_name,
                                role=role,
                                interview_type=interview_type,
                            ),
                            interview_type=interview_type,
                            owner_user_id=auth_ctx.user_id,
                            org_id=auth_ctx.org_id or "",
                        )
                    opening_audio = await ai_service.synthesize_speech(start_response.opening_question, db=db)

                active_session_id = start_response.session_id
                active_interview_type = start_response.interview_type
                candidate_audio_buffer.clear()
                await limiter.bind_ws_session(str(start_response.session_id), auth_ctx.user_id)

                await websocket.send_json(
                    {
                        "type": "session_started",
                        "session_id": str(start_response.session_id),
                        "opening_question": start_response.opening_question,
                        "interview_type": start_response.interview_type,
                        "max_turns": start_response.max_turns,
                        "interview_duration_seconds": start_response.interview_duration_seconds,
                    }
                )
                await websocket.send_json(
                    {
                        "type": "transcript",
                        "speaker": "ai",
                        "text": start_response.opening_question,
                    }
                )

                if opening_audio:
                    await websocket.send_json({"type": "connection_status", "status": "speaking"})
                    await websocket.send_json(
                        {
                            "type": "ai_audio",
                            "mime_type": "audio/mpeg",
                            "audio_base64": base64.b64encode(opening_audio).decode("utf-8"),
                        }
                    )
                await websocket.send_json({"type": "connection_status", "status": "listening"})
                continue

            if message_type == "audio_chunk":
                if active_session_id is None:
                    await websocket.send_json({"type": "error", "message": "Session not initialized."})
                    continue
                chunk_base64 = payload.get("chunk_base64")
                if not chunk_base64:
                    continue
                try:
                    candidate_audio_buffer.extend(base64.b64decode(chunk_base64))
                except Exception:
                    await websocket.send_json({"type": "error", "message": "Invalid audio chunk encoding."})
                    continue
                active_mime_type = str(payload.get("mime_type", active_mime_type))
                continue

            if message_type == "candidate_turn_end":
                if active_session_id is None:
                    await websocket.send_json({"type": "error", "message": "Session not initialized."})
                    continue
                if not candidate_audio_buffer:
                    await websocket.send_json({"type": "warning", "message": "No audio captured for this turn."})
                    continue

                await websocket.send_json({"type": "connection_status", "status": "thinking"})
                async with SessionLocal() as db:
                    repository = InterviewRepository(db)
                    service = InterviewService(
                        repository=repository,
                        ai_service=ai_service,
                        interview_engine=interview_engine,
                        scoring_engine=scoring_engine,
                    )
                    turn_result = await service.process_live_turn(
                        session_id=active_session_id,
                        audio_bytes=bytes(candidate_audio_buffer),
                        mime_type=active_mime_type,
                        interview_type=active_interview_type,
                    )
                candidate_audio_buffer.clear()

                await websocket.send_json(
                    {
                        "type": "transcript",
                        "speaker": "candidate",
                        "text": turn_result.candidate_transcript,
                    }
                )
                await websocket.send_json({"type": "evaluation_signals", **turn_result.signals})
                await websocket.send_json(
                    {
                        "type": "next_question",
                        "question_text": turn_result.next_question_text,
                        "question_order": turn_result.question_order,
                    }
                )
                await websocket.send_json(
                    {
                        "type": "transcript",
                        "speaker": "ai",
                        "text": turn_result.next_question_text,
                    }
                )

                if turn_result.ai_audio_bytes:
                    await websocket.send_json({"type": "connection_status", "status": "speaking"})
                    await websocket.send_json(
                        {
                            "type": "ai_audio",
                            "mime_type": "audio/mpeg",
                            "audio_base64": base64.b64encode(turn_result.ai_audio_bytes).decode("utf-8"),
                        }
                    )

                if turn_result.completed:
                    await websocket.send_json(
                        {
                            "type": "session_complete",
                            "session_id": str(turn_result.session_id),
                            "signals": turn_result.signals,
                        }
                    )
                    await websocket.send_json({"type": "connection_status", "status": "completed"})
                else:
                    await websocket.send_json({"type": "connection_status", "status": "listening"})
                continue

            if message_type == "session_end":
                if active_session_id:
                    async with SessionLocal() as db:
                        repository = InterviewRepository(db)
                        service = InterviewService(
                            repository=repository,
                            ai_service=ai_service,
                            interview_engine=interview_engine,
                            scoring_engine=scoring_engine,
                        )
                        await service.end_session(active_session_id)
                await websocket.send_json({"type": "session_complete", "session_id": str(active_session_id or "")})
                await websocket.send_json({"type": "connection_status", "status": "closed"})
                await websocket.close()
                return

            if message_type == "integrity_event":
                if active_session_id is None:
                    await websocket.send_json({"type": "error", "message": "Session not initialized."})
                    continue
                event_type = str(payload.get("event_type", "")).strip() or "unknown"
                severity = float(payload.get("severity", 0.0) or 0.0)
                details = payload.get("details", {})
                async with SessionLocal() as db:
                    repository = InterviewRepository(db)
                    await repository.add_integrity_event(
                        session_id=active_session_id,
                        event_type=event_type,
                        severity=severity,
                        details=details if isinstance(details, dict) else {"raw": details},
                    )
                    await repository.commit()
                metrics_store.increment_integrity_event()
                continue

            await websocket.send_json({"type": "error", "message": f"Unsupported event type: {message_type}"})

    except WebSocketDisconnect:
        metrics_store.increment_ws_disconnect()
        logger.info("Interview websocket disconnected. session_id=%s", active_session_id)
    except AppError as exc:
        try:
            await websocket.send_json({"type": "error", "message": exc.message, "details": exc.details})
        except WebSocketDisconnect:
            logger.info("Client disconnected before AppError could be sent. session_id=%s", active_session_id)
    except Exception as exc:
        error_type = type(exc).__name__
        error_text = str(exc).strip()
        detail = error_type if not error_text else f"{error_type}: {error_text}"
        logger.exception("Unhandled websocket error: %s", detail)
        try:
            await websocket.send_json({"type": "error", "message": f"Internal websocket error ({detail[:240]})."})
        except WebSocketDisconnect:
            logger.info("Client disconnected before internal error could be sent. session_id=%s", active_session_id)
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
