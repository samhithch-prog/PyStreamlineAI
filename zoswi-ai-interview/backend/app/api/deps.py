from collections.abc import Callable

from fastapi import Depends
from fastapi import Header, HTTPException, status
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, UserRole, decode_access_token
from app.core.db import get_db
from app.repositories.interview_repository import InterviewRepository
from app.services.ai_service import AIService
from app.services.interview_engine import InterviewEngine
from app.services.interview_service import InterviewService
from app.services.scoring_engine import ScoringEngine

ai_service = AIService()
interview_engine = InterviewEngine()
scoring_engine = ScoringEngine()


async def get_interview_service(db: AsyncSession = Depends(get_db)) -> InterviewService:
    repository = InterviewRepository(db)
    return InterviewService(
        repository=repository,
        ai_service=ai_service,
        interview_engine=interview_engine,
        scoring_engine=scoring_engine,
    )


def get_ai_service() -> AIService:
    return ai_service


def get_interview_engine() -> InterviewEngine:
    return interview_engine


def get_scoring_engine() -> ScoringEngine:
    return scoring_engine


def _extract_bearer_token(authorization: str | None) -> str:
    raw = str(authorization or "").strip()
    if not raw.lower().startswith("bearer "):
        return ""
    return raw[7:].strip()


async def get_current_auth_context(
    request: Request,
    authorization: str | None = Header(default=None),
) -> AuthContext:
    token = _extract_bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token.")
    context = decode_access_token(token)
    request.state.user_id = context.user_id
    return context


def require_roles(*allowed_roles: UserRole) -> Callable:
    allowed = {role.value for role in allowed_roles}

    async def _dependency(auth_ctx: AuthContext = Depends(get_current_auth_context)) -> AuthContext:
        if auth_ctx.role.value not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role permissions.")
        return auth_ctx

    return _dependency
