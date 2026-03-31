from __future__ import annotations

from src.service.immigration_updates_service import ImmigrationUpdatesService


class _RepoStub:
    def get_setting(self, _setting_key: str) -> str:
        return ""

    def set_setting(self, _setting_key: str, _setting_value: str) -> None:
        return None

    def upsert_articles(self, _articles):  # type: ignore[no-untyped-def]
        return 0, 0, 0

    def cleanup_noise_entries(self) -> int:
        return 0

    def search_updates(self, _search_input):  # type: ignore[no-untyped-def]
        return []

    def list_recent_alerts(self, lookback_hours: int = 48, limit: int = 6) -> list[dict]:
        _ = lookback_hours, limit
        return []


def _update_row(
    *,
    title: str,
    summary: str,
    source: str,
    link: str,
    visa_category: str,
    published_date: str,
) -> dict:
    return {
        "title": title,
        "summary": summary,
        "source": source,
        "link": link,
        "visa_category": visa_category,
        "published_date": published_date,
        "tags": [],
    }


def test_answer_query_from_updates_returns_no_direct_live_match_for_unrelated_specific_question() -> None:
    service = ImmigrationUpdatesService(repository=_RepoStub())
    updates = [
        _update_row(
            title="Visa Bulletin For April 2026",
            summary="Department of State released the monthly visa bulletin.",
            source="US Department of State Visa Bulletin",
            link="https://example.test/visa-bulletin-apr-2026",
            visa_category="Visa Bulletin",
            published_date="2026-03-01T00:00:00+00:00",
        )
    ]

    answer = service.answer_query_from_updates("When are H1B lottery results for FY 2027?", updates)

    assert "direct live match" in answer
    assert "H1B registration" in answer


def test_answer_query_from_updates_prefers_relevant_h1b_update() -> None:
    service = ImmigrationUpdatesService(repository=_RepoStub())
    updates = [
        _update_row(
            title="Visa Bulletin For April 2026",
            summary="Department of State released the monthly visa bulletin.",
            source="US Department of State Visa Bulletin",
            link="https://example.test/visa-bulletin-apr-2026",
            visa_category="Visa Bulletin",
            published_date="2026-03-01T00:00:00+00:00",
        ),
        _update_row(
            title="USCIS Completes Initial Registration Selection Process for FY 2027 H-1B Cap",
            summary="USCIS announced updates related to H-1B cap registration selection.",
            source="USCIS Alerts",
            link="https://example.test/h1b-fy2027-selection",
            visa_category="H1B",
            published_date="2026-03-29T00:00:00+00:00",
        ),
    ]

    answer = service.answer_query_from_updates("When will H1B selection results be available?", updates)

    assert answer.startswith("---\nOverview:")
    assert "Key Updates:" in answer
    assert "Next Step:" in answer
    assert "Status Line (very important):" in answer
    assert "Registration Closed - Lottery Completed - Results Released - Petition Filing Phase" in answer
    assert "USCIS Alerts" in answer
    assert "http://" not in answer
    assert "https://" not in answer


def test_answer_query_from_updates_keeps_generic_latest_query_live() -> None:
    service = ImmigrationUpdatesService(repository=_RepoStub())
    updates = [
        _update_row(
            title="USCIS Announces New Form Guidance",
            summary="USCIS updated filing guidance for certain forms.",
            source="USCIS News Releases",
            link="https://example.test/uscis-form-guidance",
            visa_category="General",
            published_date="2026-03-20T00:00:00+00:00",
        ),
        _update_row(
            title="SEVP Broadcast Message March 2026",
            summary="SEVP posted a broadcast message for schools and students.",
            source="ICE SEVP Broadcast Messages",
            link="https://example.test/sevp-march-2026",
            visa_category="F1",
            published_date="2026-03-28T00:00:00+00:00",
        ),
    ]

    answer = service.answer_query_from_updates("Latest immigration updates?", updates)

    assert "direct live match" not in answer
    assert "Latest related update" in answer
    assert "http://" not in answer
    assert "https://" not in answer
