from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.models.interview import InterviewSession, UserInterviewQuota
from app.core.redis_client import get_redis_client

settings = get_settings()


class RateLimiter:
    async def hit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        if limit <= 0:
            return True, 0
        redis = get_redis_client()
        if redis is None:
            return True, max(0, limit - 1)
        try:
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, max(1, window_seconds))
            remaining = max(0, int(limit) - int(count))
            return count <= limit, remaining
        except Exception:
            # Fail open if Redis is unavailable to avoid global API outage.
            return True, max(0, limit - 1)

    async def bind_ws_session(self, session_id: str, user_id: str, ttl_seconds: int = 3600) -> None:
        redis = get_redis_client()
        if redis is None:
            return
        try:
            await redis.setex(f"ws:session:{session_id}:user", max(30, int(ttl_seconds)), str(user_id))
        except Exception:
            return

    async def get_ws_session_user(self, session_id: str) -> str:
        redis = get_redis_client()
        if redis is None:
            return ""
        try:
            return str(await redis.get(f"ws:session:{session_id}:user") or "").strip()
        except Exception:
            return ""


limiter = RateLimiter()


async def _get_candidate_total_chances(user_id: str, db: AsyncSession) -> int:
    default_total = max(1, int(settings.candidate_max_interviews_total))
    safe_user_id = str(user_id or "").strip()
    if not safe_user_id:
        return default_total

    try:
        result = await db.execute(
            select(UserInterviewQuota).where(UserInterviewQuota.user_id == safe_user_id).limit(1)
        )
        quota = result.scalar_one_or_none()
        if quota is None:
            quota = UserInterviewQuota(user_id=safe_user_id, total_chances=default_total)
            db.add(quota)
            await db.flush()
        return max(1, int(quota.total_chances or default_total))
    except Exception:
        await db.rollback()
        return default_total


async def enforce_candidate_interview_limits(user_id: str, db: AsyncSession) -> None:
    safe_user_id = str(user_id or "").strip()
    if not safe_user_id:
        raise AppError(status_code=401, message="Missing user id for candidate limits.")

    active_limit = max(1, int(settings.candidate_max_active_interviews))
    daily_limit = max(1, int(settings.candidate_max_interviews_per_day))
    total_limit = await _get_candidate_total_chances(safe_user_id, db)

    total_started = 0
    try:
        total_result = await db.execute(
            select(func.count(InterviewSession.id)).where(InterviewSession.owner_user_id == safe_user_id)
        )
        total_started = int(total_result.scalar_one() or 0)
    except Exception:
        # Backward-compatible mode if interview_sessions table/column is not ready yet.
        total_started = 0

    if total_started >= total_limit:
        raise AppError(
            status_code=429,
            message=(
                f"AI interview chances exhausted ({total_limit}/{total_limit} used). "
                "Contact support to enable more interview credits."
            ),
        )

    active_count = 0
    try:
        result = await db.execute(
            text(
                """
                SELECT COUNT(*)::INT
                FROM interview_sessions
                WHERE status = 'in_progress' AND owner_user_id = :user_id
                """
            ),
            {"user_id": safe_user_id},
        )
        active_count = int(result.scalar_one() or 0)
    except Exception:
        # Backward-compatible mode before migrations add owner_user_id.
        active_count = 0

    if active_count >= active_limit:
        raise AppError(status_code=429, message="Candidate active interview limit reached.")

    day_bucket = datetime.now(timezone.utc).strftime("%Y%m%d")
    allowed, _ = await limiter.hit(
        key=f"ratelimit:candidate:{safe_user_id}:interviews:{day_bucket}",
        limit=daily_limit,
        window_seconds=24 * 60 * 60,
    )
    if not allowed:
        raise AppError(status_code=429, message="Candidate daily interview limit reached.")


async def enforce_recruiter_review_rate_limit(user_id: str) -> None:
    safe_user_id = str(user_id or "").strip()
    if not safe_user_id:
        raise AppError(status_code=401, message="Missing user id for recruiter limits.")

    allowed, _ = await limiter.hit(
        key=f"ratelimit:recruiter:{safe_user_id}:reviews",
        limit=max(1, int(settings.recruiter_review_limit_per_minute)),
        window_seconds=60,
    )
    if not allowed:
        raise AppError(status_code=429, message="Recruiter review rate limit reached.")


async def enforce_ws_event_limit(user_id: str, session_id: str) -> None:
    safe_user_id = str(user_id or "").strip()
    safe_session_id = str(session_id or "").strip()
    if not safe_user_id or not safe_session_id:
        return
    allowed, _ = await limiter.hit(
        key=f"ratelimit:ws:{safe_user_id}:{safe_session_id}",
        limit=max(1, int(settings.ws_events_per_minute)),
        window_seconds=60,
    )
    if not allowed:
        raise AppError(status_code=429, message="WebSocket event rate limit reached.")
