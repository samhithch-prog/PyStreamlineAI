from __future__ import annotations

from typing import Any

from src.dto.careers_dto import ApplicationRecord, JobCard, SavedJob
from src.repository.careers_repository import CareersRepository


class CareersApplicationsService:
    """Orchestrates saved jobs and application tracker actions."""

    def __init__(self, repository: CareersRepository) -> None:
        self._repo = repository

    def add_to_saved_jobs(self, user_id: int, job: JobCard | dict[str, Any]) -> SavedJob | None:
        return self._repo.save_job(user_id, job)

    def remove_from_saved_jobs(self, user_id: int, job_id: str) -> bool:
        return self._repo.unsave_job(user_id, job_id)

    def fetch_saved_jobs(self, user_id: int, limit: int = 100, offset: int = 0) -> list[SavedJob]:
        return self._repo.list_saved_jobs(user_id=user_id, limit=limit, offset=offset)

    def move_saved_job_to_application_tracker(
        self,
        user_id: int,
        job_id: str,
        status: str = "applied",
        notes: str = "",
    ) -> ApplicationRecord | None:
        safe_user_id = int(user_id or 0)
        cleaned_job_id = str(job_id or "").strip()
        if safe_user_id <= 0 or not cleaned_job_id:
            return None

        saved_jobs = self._repo.list_saved_jobs(user_id=safe_user_id, limit=500, offset=0)
        selected_saved = next((item for item in saved_jobs if item.job.job_id == cleaned_job_id), None)
        if selected_saved is None:
            return None

        record = self._repo.create_or_update_application_record(
            user_id=safe_user_id,
            job=selected_saved.job,
            status=status,
            notes=notes,
        )
        if record is not None:
            self._repo.unsave_job(user_id=safe_user_id, job_id=cleaned_job_id)
        return record

    def move_job_to_application_tracker(
        self,
        user_id: int,
        job: JobCard | dict[str, Any],
        status: str = "applied",
        notes: str = "",
    ) -> ApplicationRecord | None:
        return self._repo.create_or_update_application_record(
            user_id=user_id,
            job=job,
            status=status,
            notes=notes,
        )

    def update_application_status(
        self,
        user_id: int,
        job_id: str,
        status: str,
        notes: str | None = None,
    ) -> ApplicationRecord | None:
        return self._repo.update_application_record(
            user_id=user_id,
            job_id=job_id,
            status=status,
            notes=notes,
        )

    def fetch_tracker_list(self, user_id: int, limit: int = 200, offset: int = 0) -> list[ApplicationRecord]:
        return self._repo.list_application_records(user_id=user_id, limit=limit, offset=offset)
