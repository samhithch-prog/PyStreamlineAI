"""DTO layer for app runtime contracts."""

from .immigration_dto import (
    ImmigrationArticleDTO,
    ImmigrationRefreshResultDTO,
    ImmigrationSearchInputDTO,
)
from .careers_dto import (
    ApplicationRecord,
    JobCard,
    JobFilters,
    JobMatchResult,
    SavedJob,
)

__all__ = [
    "ApplicationRecord",
    "ImmigrationArticleDTO",
    "ImmigrationRefreshResultDTO",
    "ImmigrationSearchInputDTO",
    "JobCard",
    "JobFilters",
    "JobMatchResult",
    "SavedJob",
]
