from __future__ import annotations

import hashlib
import html
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from src.dto.immigration_dto import (
    ImmigrationArticleDTO,
    ImmigrationRefreshResultDTO,
    ImmigrationSearchInputDTO,
)
from src.repository.immigration_repository import ImmigrationRepository

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency in some envs
    OpenAI = None  # type: ignore[assignment]


@dataclass(frozen=True)
class ImmigrationSourceConfig:
    name: str
    source_type: str  # rss | html_visa_bulletin | html_uscis_news | html_sevp_whats_new
    url: str
    trust_level: str = "official"


IMMIGRATION_REFRESH_SETTING_KEY = "IMMIGRATION_UPDATES_LAST_FETCH_AT"
IMMIGRATION_CATEGORIES = ["H1B", "F1", "OPT", "STEM OPT", "Visa Bulletin", "Green Card", "General"]


class ImmigrationUpdatesService:
    _source_payload_cache: dict[str, tuple[float, str]] = {}
    _source_payload_cache_max_entries: int = 200
    _source_payload_cache_default_ttl_seconds: int = 900

    def __init__(
        self,
        repository: ImmigrationRepository,
        ai_key_getter: Callable[[], str | None] | None = None,
        llm_model: str = "gpt-4o-mini",
    ) -> None:
        self._repo = repository
        self._ai_key_getter = ai_key_getter
        self._llm_model = str(llm_model or "gpt-4o-mini").strip() or "gpt-4o-mini"
        self._cached_ai_client: Any = None
        self._cached_ai_key = ""
        self._sources = [
            ImmigrationSourceConfig(
                name="USCIS Alerts",
                source_type="html_uscis_news",
                url="https://www.uscis.gov/newsroom/alerts",
            ),
            ImmigrationSourceConfig(
                name="USCIS News Releases",
                source_type="html_uscis_news",
                url="https://www.uscis.gov/newsroom/news-releases",
            ),
            ImmigrationSourceConfig(
                name="US Department of State Visa Bulletin",
                source_type="html_visa_bulletin",
                url="https://travel.state.gov/content/travel/en/legal/visa-law0/visa-bulletin.html",
            ),
            ImmigrationSourceConfig(
                name="Study in the States (DHS)",
                source_type="rss",
                url="https://studyinthestates.dhs.gov/rss.xml",
            ),
            ImmigrationSourceConfig(
                name="ICE SEVP Broadcast Messages",
                source_type="html_sevp_whats_new",
                url="https://www.ice.gov/sevis/whats-new",
            ),
        ]

    def refresh_updates(self, force: bool = False, interval_hours: int = 6) -> ImmigrationRefreshResultDTO:
        last_fetch_iso = self._repo.get_setting(IMMIGRATION_REFRESH_SETTING_KEY)
        now_utc = datetime.now(timezone.utc)
        safe_interval = max(1, min(24, int(interval_hours or 6)))
        if not force and self._is_recent(last_fetch_iso, now_utc, safe_interval):
            return ImmigrationRefreshResultDTO(
                refreshed=False,
                message=f"Cache is fresh. Auto-refresh runs every {safe_interval} hours.",
            )

        collected_raw: list[dict[str, str]] = []
        for source in self._sources:
            try:
                payload = self._fetch_text(
                    source.url,
                    timeout_seconds=20,
                    use_cache=not force,
                    cache_ttl_seconds=self._source_payload_cache_default_ttl_seconds,
                )
            except Exception:
                continue
            if not payload.strip():
                continue
            if source.source_type == "rss":
                collected_raw.extend(self._parse_rss_items(source.name, payload, source.url, max_items=30))
            elif source.source_type == "html_visa_bulletin":
                collected_raw.extend(self._parse_visa_bulletin_links(source.name, payload, source.url, max_items=20))
            elif source.source_type == "html_uscis_news":
                collected_raw.extend(self._parse_uscis_news_items(source.name, payload, source.url, max_items=40))
            elif source.source_type == "html_sevp_whats_new":
                collected_raw.extend(self._parse_sevp_whats_new_items(source.name, payload, source.url, max_items=45))

        unique_raw: list[dict[str, str]] = []
        seen_links: set[str] = set()
        for item in collected_raw:
            link_key = self._canonicalize_link(item.get("link", ""))
            if not link_key or link_key in seen_links:
                continue
            seen_links.add(link_key)
            unique_raw.append(item)

        ai_budget = 12
        ready_articles: list[ImmigrationArticleDTO] = []
        for index, item in enumerate(unique_raw):
            title = str(item.get("title", "")).strip()
            link = self._canonicalize_link(item.get("link", ""))
            source = str(item.get("source", "")).strip()
            if not title or not link or not source:
                continue

            raw_text = self._compact_text(
                " ".join(
                    [
                        title,
                        str(item.get("description", "")).strip(),
                        str(item.get("raw_text", "")).strip(),
                    ]
                )
            )
            published = self._normalize_datetime(str(item.get("published_date", "")).strip()) or now_utc.isoformat()
            category, tag_list = self._classify_item(title=title, raw_text=raw_text, link=link, source=source)

            summary_seed = str(item.get("description", "")).strip() or raw_text
            summary = self._heuristic_summary(title=title, raw_text=summary_seed, category=category)
            if index < ai_budget:
                ai_summary = self._summarize_with_ai(title=title, raw_text=summary_seed, category=category)
                if ai_summary:
                    summary = ai_summary

            article_hash = hashlib.sha256(
                f"{title}|{summary_seed}|{source}|{link}|{published}|{category}".encode("utf-8")
            ).hexdigest()
            ready_articles.append(
                ImmigrationArticleDTO(
                    title=title[:280],
                    summary=summary[:600],
                    source=source[:180],
                    link=link[:1000],
                    visa_category=category,
                    published_date=published,
                    tags=tuple(tag_list),
                    original_text=summary_seed[:4000],
                    content_hash=article_hash,
                )
            )

        inserted, updated, skipped = self._repo.upsert_articles(ready_articles)
        self._repo.cleanup_noise_entries()
        self._repo.set_setting(IMMIGRATION_REFRESH_SETTING_KEY, now_utc.isoformat())
        return ImmigrationRefreshResultDTO(
            refreshed=True,
            message="Immigration updates refreshed successfully.",
            fetched_count=len(ready_articles),
            inserted_count=inserted,
            updated_count=updated,
            skipped_count=skipped,
        )

    def search_updates(self, query: str, visa_categories: list[str], limit: int = 30) -> list[dict[str, Any]]:
        cleaned_categories = [
            item for item in [str(cat or "").strip() for cat in visa_categories] if item in IMMIGRATION_CATEGORIES
        ]
        search_input = ImmigrationSearchInputDTO(
            query=str(query or "").strip(),
            visa_categories=tuple(cleaned_categories),
            limit=max(1, min(100, int(limit or 30))),
            offset=0,
        )
        return self._repo.search_updates(search_input)

    def search_updates_live(
        self,
        query: str,
        visa_categories: list[str],
        limit: int = 30,
        force_refresh_on_miss: bool = False,
    ) -> tuple[list[dict[str, Any]], str, bool]:
        cleaned_query = self._compact_text(str(query or ""))
        cleaned_categories = [
            item for item in [str(cat or "").strip() for cat in visa_categories] if item in IMMIGRATION_CATEGORIES
        ]
        inferred_categories = self._infer_categories_from_query(cleaned_query)
        search_categories = list(cleaned_categories)
        category_override_note = ""
        if inferred_categories:
            if not search_categories:
                search_categories = list(inferred_categories)
            else:
                intersection = [item for item in search_categories if item in inferred_categories]
                if intersection:
                    search_categories = intersection
                else:
                    search_categories = list(inferred_categories)
                    category_override_note = (
                        f'Using inferred category from query: {", ".join(inferred_categories)} '
                        f'(instead of current filter: {", ".join(cleaned_categories)}).'
                    )
        query_variants = self._build_query_variants(cleaned_query)

        for idx, candidate_query in enumerate(query_variants):
            rows = self.search_updates(query=candidate_query, visa_categories=search_categories, limit=limit)
            if rows:
                if idx == 0:
                    return rows, category_override_note, False
                note = f'Showing results using related search terms for "{cleaned_query}".'
                if category_override_note:
                    note = f"{category_override_note} {note}"
                return rows, note, False

        if not cleaned_query:
            rows = self.search_updates(query="", visa_categories=search_categories, limit=limit)
            return rows, "", False

        if not force_refresh_on_miss:
            return [], "", False

        refresh_result = self.refresh_updates(force=True, interval_hours=6)
        for idx, candidate_query in enumerate(query_variants):
            rows = self.search_updates(query=candidate_query, visa_categories=search_categories, limit=limit)
            if rows:
                if idx == 0:
                    note = (
                        f"Live refresh completed ({refresh_result.inserted_count} new, "
                        f"{refresh_result.updated_count} updated)."
                    )
                else:
                    note = (
                        f"Live refresh completed ({refresh_result.inserted_count} new, "
                        f"{refresh_result.updated_count} updated). "
                        f'Showing related results for "{cleaned_query}".'
                    )
                if category_override_note:
                    note = f"{category_override_note} {note}"
                return rows, note, True

        fallback_categories = search_categories or inferred_categories or cleaned_categories
        fallback_rows = self.search_updates(query="", visa_categories=fallback_categories, limit=limit)
        if fallback_rows:
            if fallback_categories:
                category_label = ", ".join(fallback_categories)
                note = (
                    f'No exact match for "{cleaned_query}". Showing latest live updates in: {category_label}.'
                )
            else:
                note = f'No exact match for "{cleaned_query}". Showing latest live immigration updates.'
            if category_override_note:
                note = f"{category_override_note} {note}"
            return fallback_rows, note, True

        return (
            [],
            (
                f'No live updates found for "{cleaned_query}" after refresh. '
                "Try terms like H1B registration, selection notice, visa bulletin, or STEM OPT."
            ),
            True,
        )

    def answer_query_from_updates(self, query: str, updates: list[dict[str, Any]]) -> str:
        question = self._compact_text(str(query or ""))
        if not question:
            return ""
        rows, has_direct_match = self._select_query_relevant_updates(question, updates, limit=8)
        if not rows:
            return (
                "I could not find enough related updates to answer this yet. "
                "Try a specific query like H1B lottery selection notice or visa bulletin EB2."
            )
        if self.looks_like_question(question) and not has_direct_match:
            return (
                f'I could not find a direct live match for "{question}" in the latest source updates. '
                "Try a more specific keyword like H1B registration, visa bulletin EB2, or STEM OPT."
            )
        h1b_live_answer = self._build_h1b_results_live_answer(question, rows)
        if h1b_live_answer:
            return h1b_live_answer

        client = self._get_ai_client()
        if client is not None:
            try:
                context_rows = [
                    {
                        "title": str(item.get("title", "")).strip(),
                        "summary": str(item.get("summary", "")).strip(),
                        "source": str(item.get("source", "")).strip(),
                        "published_date": str(item.get("published_date", "")).strip(),
                        "visa_category": str(item.get("visa_category", "")).strip(),
                        "link": str(item.get("link", "")).strip(),
                    }
                    for item in rows
                ]
                response = client.chat.completions.create(
                    model=self._llm_model,
                    temperature=0.15,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You answer immigration dashboard questions using only provided updates. "
                                "Be factual, concise, and non-speculative. If an official date is not present, "
                                "state that clearly. Do not provide legal advice."
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                f"Question: {question}\n"
                                f"Today's date (UTC): {datetime.now(timezone.utc).date().isoformat()}\n"
                                f"Updates JSON: {json.dumps(context_rows, ensure_ascii=True)}\n"
                                "Answer in 2-4 sentences. Include exact dates when available and mention source names."
                            ),
                        },
                    ],
                )
                content = self._compact_text(str(response.choices[0].message.content or ""))
                if content:
                    return content
            except Exception:
                pass
        return self._heuristic_question_answer(question, rows)

    def _build_h1b_results_live_answer(self, query: str, updates: list[dict[str, Any]]) -> str:
        lowered = str(query or "").strip().lower()
        h1b_terms = ("h1b", "h-1b")
        results_terms = ("result", "results", "selection", "selected", "lottery", "date", "when", "timeline")
        if not any(term in lowered for term in h1b_terms):
            return ""
        if not any(term in lowered for term in results_terms):
            return ""
        ranked = sorted([row for row in updates if isinstance(row, dict)], key=self._sort_key_published_date, reverse=True)
        if not ranked:
            return ""
        h1b_rows = [
            row
            for row in ranked
            if str(row.get("visa_category", "")).strip() == "H1B"
            or "h1b" in self._compact_text(
                f"{row.get('title', '')} {row.get('summary', '')} {' '.join(str(tag) for tag in row.get('tags', []))}"
            ).lower().replace("-", "")
        ]
        if not h1b_rows:
            return ""
        latest = h1b_rows[0]
        latest_title = self._compact_text(str(latest.get("title", "")).strip()) or "H1B update"
        latest_source = self._compact_text(str(latest.get("source", "")).strip()) or "USCIS"
        latest_link = self._compact_text(str(latest.get("link", "")).strip())
        latest_date = self._format_date_label(str(latest.get("published_date", "")).strip())
        fiscal_match = re.search(r"\bfy\s*(20\d{2})\b", latest_title.lower())
        if fiscal_match:
            fiscal_label = fiscal_match.group(1)
            answer = (
                f"Live USCIS-linked H1B update: {latest_title} ({latest_source}, {latest_date}). "
                f"Based on this update, USCIS has posted FY {fiscal_label} selection-process status."
            )
        else:
            answer = f"Live USCIS-linked H1B update: {latest_title} ({latest_source}, {latest_date})."
        if latest_link:
            answer += f" Source: {latest_link}"
        return answer

    def list_recent_alerts(self, lookback_hours: int = 48, limit: int = 6) -> list[dict[str, Any]]:
        return self._repo.list_recent_alerts(lookback_hours=lookback_hours, limit=limit)

    def build_ai_brief(self, articles: list[dict[str, Any]], query: str = "", categories: list[str] | None = None) -> str:
        top_articles = [item for item in articles if isinstance(item, dict)][:8]
        if not top_articles:
            return "No immigration updates available for the current filter."
        prompt_rows = []
        for item in top_articles:
            prompt_rows.append(
                {
                    "title": str(item.get("title", "")).strip(),
                    "summary": str(item.get("summary", "")).strip(),
                    "source": str(item.get("source", "")).strip(),
                    "visa_category": str(item.get("visa_category", "")).strip(),
                    "published_date": str(item.get("published_date", "")).strip(),
                }
            )

        client = self._get_ai_client()
        if client is None:
            return self._build_heuristic_brief(top_articles, query=query, categories=categories or [])

        try:
            response = client.chat.completions.create(
                model=self._llm_model,
                temperature=0.2,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an immigration policy brief assistant. Create concise, factual, non-legal-advice "
                            "summaries for international students and job seekers."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"User Search Query: {str(query or '').strip()}\n"
                            f"User Category Filters: {categories or []}\n"
                            f"Updates JSON: {json.dumps(prompt_rows, ensure_ascii=True)}\n"
                            "Write:\n"
                            "1) One 2-3 sentence overview.\n"
                            "2) 3 bullet points: most impactful updates.\n"
                            "3) One practical next-step sentence."
                        ),
                    },
                ],
            )
            content = str(response.choices[0].message.content or "").strip()
            if content:
                return content
        except Exception:
            pass
        return self._build_heuristic_brief(top_articles, query=query, categories=categories or [])

    @staticmethod
    def categories() -> list[str]:
        return list(IMMIGRATION_CATEGORIES)

    @staticmethod
    def looks_like_question(query: str) -> bool:
        cleaned = str(query or "").strip().lower()
        if not cleaned:
            return False
        if "?" in cleaned:
            return True
        prefixes = ("when ", "what ", "which ", "how ", "is ", "are ", "can ", "do ", "does ")
        return cleaned.startswith(prefixes)

    def _fetch_text(
        self,
        url: str,
        timeout_seconds: int = 20,
        use_cache: bool = True,
        cache_ttl_seconds: int = 900,
    ) -> str:
        cache_key = str(url or "").strip()
        now_ts = time.time()
        ttl_seconds = max(30, int(cache_ttl_seconds or 900))
        if use_cache and cache_key:
            cached = self.__class__._source_payload_cache.get(cache_key)
            if cached is not None:
                cached_ts, cached_payload = cached
                if now_ts - float(cached_ts) <= ttl_seconds:
                    return str(cached_payload or "")

        request = Request(
            str(url or "").strip(),
            headers={
                "User-Agent": "ZoSwi-Immigration-Updates/1.0",
                "Accept": "text/html,application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        with urlopen(request, timeout=max(5, int(timeout_seconds or 20))) as response:
            raw = response.read().decode("utf-8", errors="ignore")
        payload = str(raw or "")
        if cache_key and use_cache:
            cache = self.__class__._source_payload_cache
            cache[cache_key] = (now_ts, payload)
            if len(cache) > int(self._source_payload_cache_max_entries):
                expired_keys = [key for key, (ts, _) in cache.items() if now_ts - float(ts) > ttl_seconds]
                for key in expired_keys[: max(0, len(cache) - self._source_payload_cache_max_entries)]:
                    cache.pop(key, None)
                if len(cache) > int(self._source_payload_cache_max_entries):
                    ordered = sorted(cache.items(), key=lambda item: float(item[1][0]))
                    overflow = len(cache) - int(self._source_payload_cache_max_entries)
                    for key, _ in ordered[:overflow]:
                        cache.pop(key, None)
        return payload

    def _parse_rss_items(self, source_name: str, xml_text: str, source_url: str, max_items: int = 30) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        cleaned_xml = str(xml_text or "").strip()
        if not cleaned_xml:
            return items
        try:
            root = ET.fromstring(cleaned_xml)
        except ET.ParseError:
            return items

        # RSS and Atom support
        rss_items = root.findall(".//item")
        atom_entries = root.findall(".//{http://www.w3.org/2005/Atom}entry")
        iterable_nodes = rss_items + atom_entries
        for node in iterable_nodes[: max(1, int(max_items or 30))]:
            title = self._node_text(node, "title")
            link = self._node_link(node)
            description = (
                self._node_text(node, "description")
                or self._node_text(node, "summary")
                or self._node_text(node, "content")
                or ""
            )
            published_raw = (
                self._node_text(node, "pubDate")
                or self._node_text(node, "published")
                or self._node_text(node, "updated")
                or ""
            )
            published_date = self._normalize_datetime(published_raw)
            if not title or not link:
                continue
            items.append(
                {
                    "title": title,
                    "link": link,
                    "description": self._strip_html(description),
                    "raw_text": self._strip_html(description),
                    "source": source_name,
                    "source_url": source_url,
                    "published_date": published_date,
                }
            )
        return items

    def _parse_visa_bulletin_links(
        self,
        source_name: str,
        html_text: str,
        source_url: str,
        max_items: int = 20,
    ) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        cleaned = str(html_text or "")
        if not cleaned:
            return items
        anchor_pattern = re.compile(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.IGNORECASE | re.DOTALL)
        for href, text in anchor_pattern.findall(cleaned):
            link = self._resolve_link(source_url, href)
            lower_link = link.lower()
            if "visa-bulletin" not in lower_link:
                continue
            title = self._compact_text(self._strip_html(text))
            if not title:
                title = "Visa Bulletin Update"
            published_date = self._parse_month_year_to_iso(title)
            if not published_date:
                published_date = self._parse_month_year_to_iso(link)
            if not published_date:
                # Skip navigation/noise entries that do not represent a monthly bulletin.
                continue
            items.append(
                {
                    "title": title,
                    "link": link,
                    "description": "Visa Bulletin monthly update from US Department of State.",
                    "raw_text": f"{title}. Visa Bulletin monthly update from US Department of State.",
                    "source": source_name,
                    "source_url": source_url,
                    "published_date": published_date,
                }
            )
            if len(items) >= max(1, int(max_items or 20)):
                break
        return items

    def _parse_uscis_news_items(
        self,
        source_name: str,
        html_text: str,
        source_url: str,
        max_items: int = 40,
    ) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        cleaned = str(html_text or "")
        if not cleaned:
            return items
        entry_pattern = re.compile(
            r'<a\s+href="(?P<href>/newsroom/(?:alerts|news-releases)/[^"]+)"[^>]*>(?P<title>.*?)</a>',
            re.IGNORECASE,
        )
        seen_links: set[str] = set()
        for match in entry_pattern.finditer(cleaned):
            href = str(match.group("href") or "").strip()
            title_html = str(match.group("title") or "").strip()
            span_start = int(match.end())
            tail = cleaned[span_start : span_start + 3200]
            datetime_match = re.search(r'<time\s+datetime="([^"]+)"', tail, flags=re.IGNORECASE)
            datetime_raw = str(datetime_match.group(1) or "").strip() if datetime_match else ""

            link = self._resolve_link(source_url, href)
            if not link:
                continue
            link_key = self._canonicalize_link(link)
            if not link_key or link_key in seen_links:
                continue
            seen_links.add(link_key)

            title = self._compact_text(self._strip_html(title_html))
            if not title:
                continue

            body_match = re.search(
                r'<div\s+class="views-field\s+views-field-body"[^>]*>[\s\S]*?'
                r'<div\s+class="field-content">(?P<body>[\s\S]*?)</div>',
                tail,
                flags=re.IGNORECASE,
            )
            body_html = str(body_match.group("body") or "").strip() if body_match else ""
            body_text = self._compact_text(self._strip_html(body_html))
            if not body_text:
                paragraph_match = re.search(r"<p>([\s\S]{0,1200}?)</p>", tail, flags=re.IGNORECASE)
                if paragraph_match:
                    body_text = self._compact_text(self._strip_html(str(paragraph_match.group(1) or "")))

            published_date = self._normalize_datetime(datetime_raw)
            items.append(
                {
                    "title": title,
                    "link": link,
                    "description": body_text[:1200] if body_text else title,
                    "raw_text": body_text[:2400] if body_text else title,
                    "source": source_name,
                    "source_url": source_url,
                    "published_date": published_date,
                }
            )
            if len(items) >= max(1, int(max_items or 40)):
                break
        return items

    def _parse_sevp_whats_new_items(
        self,
        source_name: str,
        html_text: str,
        source_url: str,
        max_items: int = 45,
    ) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        cleaned = str(html_text or "")
        if not cleaned:
            return items
        section_match = re.search(
            r'<a\s+name="bcm"[^>]*>[\s\S]*?<h2>\s*Broadcast Messages\s*</h2>(?P<section>[\s\S]{0,220000})',
            cleaned,
            flags=re.IGNORECASE,
        )
        target = str(section_match.group("section") or "") if section_match else cleaned
        month_block_pattern = re.compile(
            r'<h3\s+class="accordion-title">[\s\S]*?<a[^>]*>(?P<month_label>[^<]+)</a>[\s\S]*?</h3>\s*'
            r'<div\s+class="accordion-description">(?P<body>[\s\S]*?)(?=<h3\s+class="accordion-title"|$)',
            flags=re.IGNORECASE,
        )
        anchor_pattern = re.compile(r'<a[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>', flags=re.IGNORECASE | re.DOTALL)
        seen_links: set[str] = set()
        for block in month_block_pattern.finditer(target):
            month_label = self._compact_text(self._strip_html(str(block.group("month_label") or "")))
            body = str(block.group("body") or "")
            published_date = self._parse_month_year_to_iso(month_label)
            if not published_date:
                continue
            for anchor in anchor_pattern.finditer(body):
                href = str(anchor.group("href") or "").strip()
                title = self._compact_text(self._strip_html(str(anchor.group("title") or "")))
                if not href or not title:
                    continue
                link = self._resolve_link(source_url, href)
                if not link:
                    continue
                link_key = self._canonicalize_link(link)
                if not link_key or link_key in seen_links:
                    continue
                seen_links.add(link_key)
                raw_text = f"{month_label}. {title}. SEVP Broadcast Message update."
                items.append(
                    {
                        "title": title,
                        "link": link,
                        "description": f"{month_label} SEVP broadcast update.",
                        "raw_text": raw_text,
                        "source": source_name,
                        "source_url": source_url,
                        "published_date": published_date,
                    }
                )
                if len(items) >= max(1, int(max_items or 45)):
                    return items
        return items

    @staticmethod
    def _parse_month_year_to_iso(raw_value: str) -> str:
        cleaned = str(raw_value or "").strip()
        if not cleaned:
            return ""
        month_pattern = re.compile(
            r"\b("
            r"january|february|march|april|may|june|july|august|september|october|november|december"
            r")\s+(20\d{2})\b",
            flags=re.IGNORECASE,
        )
        match = month_pattern.search(cleaned)
        if not match:
            return ""
        month_name = str(match.group(1) or "").strip().lower()
        year_value = int(str(match.group(2) or "0"))
        month_map = {
            "january": 1,
            "february": 2,
            "march": 3,
            "april": 4,
            "may": 5,
            "june": 6,
            "july": 7,
            "august": 8,
            "september": 9,
            "october": 10,
            "november": 11,
            "december": 12,
        }
        month_value = int(month_map.get(month_name, 0))
        if month_value <= 0:
            return ""
        try:
            dt = datetime(year_value, month_value, 1, tzinfo=timezone.utc)
            return dt.isoformat()
        except Exception:
            return ""

    def _summarize_with_ai(self, title: str, raw_text: str, category: str) -> str:
        client = self._get_ai_client()
        if client is None:
            return ""
        safe_title = str(title or "").strip()
        safe_text = self._compact_text(str(raw_text or "").strip())[:2200]
        if not safe_title and not safe_text:
            return ""
        try:
            response = client.chat.completions.create(
                model=self._llm_model,
                temperature=0.25,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Summarize immigration policy updates in simple language for job seekers. "
                            "Keep it factual and concise. Do not provide legal advice."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Category: {category}\n"
                            f"Title: {safe_title}\n"
                            f"Content: {safe_text}\n"
                            "Return 1-2 sentences under 55 words."
                        ),
                    },
                ],
            )
            content = str(response.choices[0].message.content or "").strip()
            return self._compact_text(content)[:420]
        except Exception:
            return ""

    def _get_ai_client(self) -> Any | None:
        if OpenAI is None or self._ai_key_getter is None:
            return None
        key = str(self._ai_key_getter() or "").strip()
        if not key:
            return None
        if self._cached_ai_client is not None and key == self._cached_ai_key:
            return self._cached_ai_client
        try:
            self._cached_ai_client = OpenAI(api_key=key)
            self._cached_ai_key = key
            return self._cached_ai_client
        except Exception:
            self._cached_ai_client = None
            self._cached_ai_key = ""
            return None

    @staticmethod
    def _heuristic_summary(title: str, raw_text: str, category: str) -> str:
        safe_title = str(title or "").strip()
        cleaned = re.sub(r"\s+", " ", str(raw_text or "").strip())
        if not cleaned:
            cleaned = safe_title
        if not cleaned:
            return "Immigration policy update available. Open the source article for details."
        sentence_match = re.match(r"(.{40,260}?[.!?])(\s|$)", cleaned)
        snippet = sentence_match.group(1).strip() if sentence_match else cleaned[:220].strip()
        if safe_title and snippet.lower() not in safe_title.lower():
            return f"{safe_title}. {snippet}"
        if category and category != "General":
            return f"{snippet} ({category})"
        return snippet

    @staticmethod
    def _build_heuristic_brief(articles: list[dict[str, Any]], query: str, categories: list[str]) -> str:
        first = articles[0]
        scope_line = "Latest immigration updates are available across trusted sources."
        if query:
            scope_line = f'Latest results for "{query}" across trusted immigration sources.'
        if categories:
            scope_line += f" Focus categories: {', '.join(categories)}."
        bullets: list[str] = []
        for row in articles[:3]:
            title = str(row.get("title", "")).strip()
            source = str(row.get("source", "")).strip()
            category = str(row.get("visa_category", "")).strip()
            if title:
                label = f"- {title}"
                if category:
                    label += f" [{category}]"
                if source:
                    label += f" ({source})"
                bullets.append(label)
        if not bullets:
            bullets = ["- No highlights available yet."]
        return (
            scope_line
            + "\n\nKey updates:\n"
            + "\n".join(bullets)
            + "\n\nNext step: review source links and verify date-specific guidance before acting."
        )

    def _classify_item(self, title: str, raw_text: str, link: str, source: str) -> tuple[str, list[str]]:
        corpus = " ".join([str(title or ""), str(raw_text or ""), str(link or ""), str(source or "")]).lower()
        category_patterns: list[tuple[str, list[str]]] = [
            ("Visa Bulletin", ["visa bulletin", "priority date", "final action date", "dates for filing"]),
            ("STEM OPT", ["stem opt", "i-983", "training plan", "24-month extension"]),
            ("OPT", ["opt", "optional practical training", "post-completion opt", "sevp"]),
            ("F1", ["f-1", "f1", "sevis", "international student"]),
            ("H1B", ["h-1b", "h1b", "specialty occupation", "cap registration", "lottery"]),
            ("Green Card", ["green card", "adjustment of status", "i-485", "permanent resident", "eb-1", "eb-2", "eb-3"]),
        ]
        matched_tags: list[str] = []
        category = "General"
        for candidate, keywords in category_patterns:
            for keyword in keywords:
                if keyword in corpus:
                    matched_tags.append(keyword.upper() if keyword.isalpha() and len(keyword) <= 5 else keyword)
                    if category == "General":
                        category = candidate
                    break
        normalized_tags = [self._compact_text(tag).replace(" ", "-") for tag in matched_tags if self._compact_text(tag)]
        base_tags = [category, "US-immigration", source]
        merged = []
        seen: set[str] = set()
        for item in base_tags + normalized_tags:
            clean = self._compact_text(item)
            if not clean:
                continue
            key = clean.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(clean[:60])
        return category, merged[:10]

    def _heuristic_question_answer(self, query: str, updates: list[dict[str, Any]]) -> str:
        lowered = str(query or "").strip().lower()
        ranked = sorted(updates, key=self._sort_key_published_date, reverse=True)
        if not ranked:
            return (
                "I do not have enough current updates to answer this exactly. "
                "Try refreshing and asking with a specific visa keyword."
            )

        if "h1b" in lowered or "h-1b" in lowered or "lottery" in lowered:
            h1b_rows = [
                row
                for row in ranked
                if str(row.get("visa_category", "")).strip() == "H1B"
                or "h1b" in self._compact_text(
                    f"{row.get('title', '')} {row.get('summary', '')} {row.get('tags', '')}"
                ).lower()
            ]
            if h1b_rows:
                latest = h1b_rows[0]
                latest_date = self._format_date_label(str(latest.get("published_date", "")).strip())
                latest_title = str(latest.get("title", "")).strip() or "H1B update"
                latest_source = str(latest.get("source", "")).strip() or "source"
                latest_link = str(latest.get("link", "")).strip()
                if "result" in lowered or "selection" in lowered:
                    base = (
                        f"The latest H1B-related update in this dashboard is from {latest_date} "
                        f"({latest_source}): {latest_title}."
                    )
                    if "2027" in lowered:
                        base += " I do not currently see an official FY2027 selection-result date in the fetched updates."
                    if latest_link:
                        base += f" Source: {latest_link}"
                    return base
                return (
                    f"Latest H1B-related update: {latest_title} ({latest_source}, {latest_date}). "
                    f"Open the source link in the feed for full details."
                )

        latest = ranked[0]
        latest_date = self._format_date_label(str(latest.get("published_date", "")).strip())
        latest_title = str(latest.get("title", "")).strip() or "Immigration update"
        latest_source = str(latest.get("source", "")).strip() or "source"
        latest_link = str(latest.get("link", "")).strip()
        answer = f"Latest related update: {latest_title} ({latest_source}, {latest_date})."
        if latest_link:
            answer += f" Source: {latest_link}"
        return answer

    def _build_h1b_timeline_answer(self, query: str) -> str:
        lowered = str(query or "").strip().lower()
        if "h1b" not in lowered and "h-1b" not in lowered:
            return ""
        timeline_keywords = {"result", "results", "selection", "selected", "lottery", "date", "when"}
        if not any(keyword in lowered for keyword in timeline_keywords):
            return ""
        year_match = re.search(r"\b(20\d{2})\b", lowered)
        if year_match:
            fiscal_year = int(year_match.group(1))
            if fiscal_year < 2010 or fiscal_year > 2100:
                return ""
        else:
            now_year = datetime.now(timezone.utc).year
            fiscal_year = now_year + 1
        registration_year = fiscal_year - 1
        return (
            f"For FY {fiscal_year} H-1B cap, USCIS selection notifications are typically issued by "
            f"March 31, {registration_year}. Based on that timeline, expected result date is March 31, "
            f"{registration_year}. Final confirmation depends on USCIS publishing the FY {fiscal_year} notice."
        )

    @staticmethod
    def _infer_categories_from_query(query: str) -> list[str]:
        lowered = str(query or "").strip().lower()
        if not lowered:
            return []
        inferred: list[str] = []
        mapping: list[tuple[str, list[str]]] = [
            ("H1B", ["h1b", "h-1b", "lottery", "cap registration", "registration selection"]),
            ("STEM OPT", ["stem opt", "i-983", "24 month extension"]),
            ("OPT", ["opt", "optional practical training", "post-completion"]),
            ("F1", ["f1", "f-1", "sevis", "international student"]),
            ("Visa Bulletin", ["visa bulletin", "priority date", "final action date", "dates for filing"]),
            ("Green Card", ["green card", "i-485", "adjustment of status", "eb1", "eb2", "eb3"]),
        ]
        for category, keywords in mapping:
            if any(keyword in lowered for keyword in keywords):
                inferred.append(category)
        deduped: list[str] = []
        seen: set[str] = set()
        for category in inferred:
            key = category.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(category)
        return deduped

    def _build_query_variants(self, query: str) -> list[str]:
        cleaned = self._compact_text(str(query or ""))
        if not cleaned:
            return [""]
        variants: list[str] = [cleaned]
        lowered = cleaned.lower()
        raw_tokens = re.findall(r"[a-zA-Z0-9\-]+", lowered)
        stop_words = {
            "when",
            "what",
            "where",
            "which",
            "who",
            "why",
            "how",
            "is",
            "are",
            "the",
            "a",
            "an",
            "of",
            "for",
            "to",
            "in",
            "on",
            "and",
            "new",
            "latest",
            "update",
            "updates",
            "about",
            "with",
            "from",
            "at",
            "by",
            "results",
            "result",
        }
        tokens: list[str] = []
        for token in raw_tokens:
            normalized = token.replace("-", "")
            if normalized in {"h1b", "f1"}:
                tokens.append(normalized)
                continue
            if token in stop_words:
                continue
            if len(token) < 2:
                continue
            tokens.append(token)
        if tokens:
            variants.append(" ".join(tokens[:6]))

        high_signal_order = [
            "h1b",
            "lottery",
            "registration",
            "selection",
            "visa",
            "bulletin",
            "stem",
            "opt",
            "f1",
            "green",
            "card",
            "eb1",
            "eb2",
            "eb3",
        ]
        high_signal = [term for term in high_signal_order if term in tokens or term in lowered]
        if high_signal:
            variants.append(" ".join(high_signal[:3]))

        if "h1b" in lowered or "h-1b" in lowered or "lottery" in lowered:
            variants.extend(
                [
                    "h1b lottery",
                    "h1b cap registration",
                    "h1b registration selection",
                ]
            )
        if "visa bulletin" in lowered or ("visa" in lowered and "bulletin" in lowered):
            variants.append("visa bulletin")
        if "stem opt" in lowered or ("stem" in lowered and "opt" in lowered):
            variants.append("stem opt extension")
        if "green card" in lowered:
            variants.append("green card adjustment of status")

        deduped: list[str] = []
        seen: set[str] = set()
        for item in variants:
            normalized_item = self._compact_text(item)
            if not normalized_item:
                continue
            key = normalized_item.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(normalized_item)
        return deduped[:8]

    def _select_query_relevant_updates(
        self,
        query: str,
        updates: list[dict[str, Any]],
        limit: int = 8,
    ) -> tuple[list[dict[str, Any]], bool]:
        rows = [item for item in updates if isinstance(item, dict)]
        if not rows:
            return [], False
        safe_limit = max(1, min(20, int(limit or 8)))
        ranked_latest = sorted(rows, key=self._sort_key_published_date, reverse=True)
        cleaned_query = self._compact_text(str(query or "")).lower()
        if not cleaned_query:
            return ranked_latest[:safe_limit], bool(ranked_latest)

        raw_tokens = re.findall(r"[a-z0-9\-]+", cleaned_query)
        stop_words = {
            "when",
            "what",
            "where",
            "which",
            "who",
            "why",
            "how",
            "is",
            "are",
            "was",
            "were",
            "the",
            "a",
            "an",
            "of",
            "for",
            "to",
            "in",
            "on",
            "and",
            "with",
            "about",
            "from",
            "any",
            "there",
            "this",
            "that",
            "current",
            "today",
            "latest",
            "new",
            "news",
            "update",
            "updates",
            "status",
        }
        tokens: list[str] = []
        for token in raw_tokens:
            normalized = token.replace("-", "")
            if normalized in {"h1b", "f1", "eb1", "eb2", "eb3"}:
                tokens.append(normalized)
                continue
            if token in stop_words:
                continue
            if len(token) < 3:
                continue
            tokens.append(token)
        deduped_tokens: list[str] = []
        seen_tokens: set[str] = set()
        for token in tokens:
            key = token.lower()
            if key in seen_tokens:
                continue
            seen_tokens.add(key)
            deduped_tokens.append(key)

        broad_only_tokens = {
            "immigration",
            "visa",
            "visas",
            "bulletin",
            "policy",
            "policies",
        }
        if deduped_tokens and all(token in broad_only_tokens for token in deduped_tokens):
            return ranked_latest[:safe_limit], True

        inferred_categories = set(self._infer_categories_from_query(cleaned_query))
        scored_rows: list[tuple[int, float, dict[str, Any]]] = []
        for row in rows:
            haystack = self._compact_text(
                " ".join(
                    [
                        str(row.get("title", "")).strip(),
                        str(row.get("summary", "")).strip(),
                        str(row.get("source", "")).strip(),
                        str(row.get("visa_category", "")).strip(),
                        " ".join(str(tag).strip() for tag in row.get("tags", []) if str(tag).strip()),
                    ]
                )
            ).lower()
            dense_haystack = haystack.replace("-", "")
            score = 0
            if cleaned_query and cleaned_query in haystack:
                score += 4
            for token in deduped_tokens:
                if token in {"h1b", "f1", "eb1", "eb2", "eb3"}:
                    if token in dense_haystack:
                        score += 3
                elif token in haystack:
                    score += 2
            row_category = str(row.get("visa_category", "")).strip()
            if row_category and row_category in inferred_categories:
                score += 3
            scored_rows.append((score, self._sort_key_published_date(row), row))

        ranked_scored = sorted(scored_rows, key=lambda item: (item[0], item[1]), reverse=True)
        matched_rows = [row for score, _ts, row in ranked_scored if score > 0]
        if matched_rows:
            return matched_rows[:safe_limit], True

        if inferred_categories:
            category_rows = [
                row
                for row in ranked_latest
                if str(row.get("visa_category", "")).strip() in inferred_categories
            ]
            if category_rows:
                return category_rows[:safe_limit], True

        return ranked_latest[:safe_limit], False

    @staticmethod
    def _sort_key_published_date(row: dict[str, Any]) -> float:
        raw_value = str(row.get("published_date", "")).strip()
        if not raw_value:
            return 0.0
        normalized = ImmigrationUpdatesService._normalize_datetime(raw_value)
        if not normalized:
            return 0.0
        try:
            parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp()
        except Exception:
            return 0.0

    @staticmethod
    def _format_date_label(raw_value: str) -> str:
        normalized = ImmigrationUpdatesService._normalize_datetime(raw_value)
        if not normalized:
            return "unknown date"
        try:
            parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.date().isoformat()
        except Exception:
            return normalized

    @staticmethod
    def _is_recent(last_fetch_iso: str, now_utc: datetime, interval_hours: int) -> bool:
        cleaned = str(last_fetch_iso or "").strip()
        if not cleaned:
            return False
        try:
            parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
        except Exception:
            return False
        return (now_utc - parsed) < timedelta(hours=max(1, int(interval_hours or 6)))

    @staticmethod
    def _normalize_datetime(raw: str) -> str:
        cleaned = str(raw or "").strip()
        if not cleaned:
            return ""
        try:
            dt = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except Exception:
            pass
        try:
            dt2 = parsedate_to_datetime(cleaned)
            if dt2.tzinfo is None:
                dt2 = dt2.replace(tzinfo=timezone.utc)
            return dt2.astimezone(timezone.utc).isoformat()
        except Exception:
            return ""

    @staticmethod
    def _node_text(node: ET.Element, name: str) -> str:
        # RSS
        direct = node.find(name)
        if direct is not None and str(direct.text or "").strip():
            return str(direct.text or "").strip()
        # Atom
        atom = node.find(f"{{http://www.w3.org/2005/Atom}}{name}")
        if atom is not None and str(atom.text or "").strip():
            return str(atom.text or "").strip()
        return ""

    @staticmethod
    def _node_link(node: ET.Element) -> str:
        link = node.find("link")
        if link is not None:
            text_value = str(link.text or "").strip()
            if text_value:
                return text_value
            href_value = str(link.attrib.get("href", "")).strip()
            if href_value:
                return href_value
        atom_link = node.find("{http://www.w3.org/2005/Atom}link")
        if atom_link is not None:
            href = str(atom_link.attrib.get("href", "")).strip()
            if href:
                return href
        return ""

    @staticmethod
    def _strip_html(raw_html: str) -> str:
        cleaned = re.sub(r"<script[\s\S]*?</script>", " ", str(raw_html or ""), flags=re.IGNORECASE)
        cleaned = re.sub(r"<style[\s\S]*?</style>", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        cleaned = html.unescape(cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()

    @staticmethod
    def _canonicalize_link(raw_link: str) -> str:
        cleaned = str(raw_link or "").strip()
        if not cleaned:
            return ""
        cleaned = html.unescape(cleaned)
        cleaned = re.sub(r"#.*$", "", cleaned)
        return cleaned[:1000]

    @staticmethod
    def _resolve_link(base_url: str, href: str) -> str:
        raw = str(href or "").strip()
        if not raw:
            return ""
        if raw.lower().startswith(("http://", "https://")):
            return raw
        base = str(base_url or "").strip().rstrip("/")
        if not base:
            return raw
        if raw.startswith("/"):
            match = re.match(r"^(https?://[^/]+)", base, flags=re.IGNORECASE)
            if not match:
                return f"{base}{raw}"
            return f"{match.group(1)}{raw}"
        return f"{base}/{raw}"

    @staticmethod
    def _compact_text(value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip())
