from app.api.routes.interview import router as interview_router
from app.api.routes.auth import router as auth_router
from app.api.routes.instant_builder import router as instant_builder_router
from app.api.routes.recruiter import router as recruiter_router

__all__ = ["interview_router", "auth_router", "instant_builder_router", "recruiter_router"]
