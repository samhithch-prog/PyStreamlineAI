import asyncio
import logging
import sys
import uuid
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes.auth import router as auth_router
from app.api.routes.interview import router as interview_router
from app.api.routes.recruiter import router as recruiter_router
from app.core.config import get_settings
from app.core.db import engine, init_db
from app.core.exceptions import AppError, app_error_handler
from app.core.http_rate_limit_middleware import HttpRateLimitMiddleware
from app.core.logging import configure_logging
from app.core.metrics import metrics_store
from app.core.observability import configure_observability

settings = get_settings()
request_logger = logging.getLogger("app.requests")

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _get_allowed_origins() -> list[str]:
    raw_value = str(settings.frontend_origin or "").strip()
    if not raw_value:
        return ["http://localhost:3000"]
    origins: list[str] = []
    for origin in raw_value.split(","):
        cleaned = str(origin or "").strip().rstrip("/")
        if cleaned:
            origins.append(cleaned)
    return origins or ["http://localhost:3000"]


ALLOWED_ORIGINS = _get_allowed_origins()


def _normalize_origin(origin: str) -> str:
    return str(origin or "").strip().rstrip("/")


def _resolve_allowed_request_origin(request: Request) -> str:
    origin = _normalize_origin(request.headers.get("origin", ""))
    if not origin:
        return ""
    return origin if origin in ALLOWED_ORIGINS else ""


def _append_vary_origin(existing: str) -> str:
    cleaned = str(existing or "").strip()
    if not cleaned:
        return "Origin"
    parts = [item.strip() for item in cleaned.split(",") if item.strip()]
    if any(item.lower() == "origin" for item in parts):
        return cleaned
    return f"{cleaned}, Origin"


def _attach_cors_headers(request: Request, response) -> None:
    if str(response.headers.get("access-control-allow-origin", "")).strip():
        return
    allowed_origin = _resolve_allowed_request_origin(request)
    if not allowed_origin:
        return
    response.headers["access-control-allow-origin"] = allowed_origin
    response.headers["access-control-allow-credentials"] = "true"
    response.headers["vary"] = _append_vary_origin(response.headers.get("vary", ""))


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting %s in %s mode", settings.app_name, settings.app_env)
    logger.info("Configured CORS origins: %s", ", ".join(ALLOWED_ORIGINS))
    configure_observability(app, engine)
    await init_db()
    yield
    logger.info("Shutting down %s", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
)

app.add_exception_handler(AppError, app_error_handler)
app.add_middleware(HttpRateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(interview_router)
app.include_router(auth_router)
app.include_router(recruiter_router)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id
    started = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        request_logger.exception(
            "Unhandled request error.",
            extra={
                "request_id": request_id,
                "session_id": str(request.query_params.get("session_id", "") or ""),
                "user_id": str(getattr(request.state, "user_id", "") or ""),
            },
        )
        response = JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error.",
                "request_id": request_id,
            },
        )
    _attach_cors_headers(request, response)
    response.headers["x-request-id"] = request_id
    duration_ms = round((perf_counter() - started) * 1000, 2)
    request_logger.info(
        "HTTP request completed.",
        extra={
            "request_id": request_id,
            "latency": duration_ms,
            "session_id": str(request.query_params.get("session_id", "") or ""),
            "user_id": str(getattr(request.state, "user_id", "") or ""),
        },
    )
    return response


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
async def metrics_snapshot() -> dict:
    return metrics_store.snapshot()
