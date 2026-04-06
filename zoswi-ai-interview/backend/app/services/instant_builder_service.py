from __future__ import annotations

import base64
import io
import json
import re
import textwrap
import zipfile
from datetime import datetime, timezone
from typing import Any

INTENT_BUILD = "build"
INTENT_EDIT = "edit"
INTENT_SHOW_CODE = "show_code"
INTENT_EXPORT_CODE = "export_code"
INTENT_EXPLAIN = "explain"
INTENT_LOCAL = "local"
INTENT_DEPLOY = "deploy"
INTENT_GIT = "git"
INTENT_NOOP = "noop"

MODE_BUILD_PREVIEW = "build+preview"
MODE_EDIT = "edit"

_FRIENDLY_FEATURES = {
    "email_password_login": "email/password login",
    "signup": "signup flow",
    "google_login": "Google login",
    "form_validation": "form validation",
    "dark_mode": "dark mode",
    "admin_dashboard": "admin dashboard",
    "database": "database schema",
    "backend_api": "backend API scaffolding",
    "responsive_ui": "mobile responsive UI",
    "modern_ui": "modern visual polish",
    "analytics_cards": "analytics cards",
    "job_filters": "job filters",
    "resume_board": "resume tracker board",
    "application_storage": "application data storage",
    "lead_pipeline": "CRM lead pipeline",
    "status_filters": "status filters",
    "quick_create": "create another action",
    "record_editing": "record editing action",
    "zoswi_branding": "ZoSwi branding",
}


def _normalize_prompt(prompt: str) -> str:
    return re.sub(r"\s+", " ", str(prompt or "").strip())


def _disables_login(text: str) -> bool:
    lowered = _normalize_prompt(text).lower()
    if not lowered:
        return False
    disable_markers = (
        "without login",
        "without a login",
        "without sign in",
        "without signin",
        "without sign-in",
        "no login",
        "no sign in",
        "no signin",
        "without auth",
        "without authentication",
        "anonymous access",
        "guest access",
        "guest mode",
        "public access",
    )
    return any(marker in lowered for marker in disable_markers)


def _wants_login(text: str) -> bool:
    lowered = _normalize_prompt(text).lower()
    if not lowered or _disables_login(lowered):
        return False
    login_terms = ("login", "sign in", "signin", "authentication", "auth")
    return any(term in lowered for term in login_terms)


def _looks_like_app_request(prompt: str) -> bool:
    text = _normalize_prompt(prompt).lower()
    if not text:
        return False
    builders = ("build", "create", "generate", "make", "design")
    app_terms = (
        "app",
        "dashboard",
        "portal",
        "tracker",
        "application",
        "data",
        "crm",
        "lead",
        "login",
        "landing page",
        "website",
        "admin",
        "resume",
        "job",
    )
    return any(term in text for term in builders) or any(term in text for term in app_terms)


def _looks_like_information_request(text: str) -> bool:
    lowered = _normalize_prompt(text).lower()
    if not lowered:
        return False
    info_terms = (
        "update",
        "updates",
        "latest",
        "news",
        "rule",
        "rules",
        "policy",
        "policies",
        "law",
        "laws",
        "immigration",
        "visa",
        "uscis",
        "green card",
        "h1b",
        "asylum",
        "travel ban",
        "work permit",
    )
    if not any(term in lowered for term in info_terms):
        return False
    return not _looks_like_app_request(lowered)


def _looks_like_explicit_new_build_request(text: str) -> bool:
    lowered = _normalize_prompt(text).lower()
    if not lowered:
        return False
    direct_markers = (
        "new app",
        "from scratch",
        "start over",
        "create an app",
        "create a app",
        "build an app",
        "build a app",
        "generate an app",
        "generate a app",
    )
    if any(marker in lowered for marker in direct_markers):
        return True
    # Explicitly ask to create/build/generate a concrete app type.
    return bool(re.search(r"\b(create|build|generate)\b[^.]{0,80}\b(app|dashboard|tracker|portal|website|crm|login|resume|job)\b", lowered))


def _detect_intent(prompt: str, has_current: bool) -> str:
    text = _normalize_prompt(prompt).lower()
    if not text:
        return INTENT_NOOP

    if any(token in text for token in ("show code", "view code", "open code")):
        return INTENT_SHOW_CODE
    if any(token in text for token in ("download code", "export code", "download zip", "export zip")):
        return INTENT_EXPORT_CODE
    if any(token in text for token in ("run locally", "local setup", "how do i run", "how to run locally")):
        return INTENT_LOCAL
    if any(token in text for token in ("deploy", "deployment", "publish this app")):
        return INTENT_DEPLOY
    if any(token in text for token in ("commit to git", "git commit", "push to git", "github commit")):
        return INTENT_GIT
    if any(token in text for token in ("explain architecture", "explain code", "how this works", "architecture")):
        return INTENT_EXPLAIN
    if _looks_like_information_request(text):
        return INTENT_EXPLAIN

    if has_current and _looks_like_explicit_new_build_request(text):
        return INTENT_BUILD

    edit_markers = ("make it better", "improve", "refine", "update", "modify", "add ", "connect ", "change ")
    if has_current and any(marker in text for marker in edit_markers):
        return INTENT_EDIT
    if _looks_like_app_request(text):
        return INTENT_BUILD if not has_current else INTENT_EDIT
    if has_current:
        return INTENT_EDIT
    return INTENT_NOOP


def _infer_kind(prompt: str, fallback: str = "") -> str:
    text = _normalize_prompt(prompt).lower()
    if "crm" in text or ("lead" in text and any(token in text for token in ("track", "tracker", "pipeline", "status"))):
        return "crm_lead_tracker"
    if (
        "application" in text
        and any(token in text for token in ("store", "track", "tracker", "data", "status", "history", "save"))
    ):
        return "application_tracker"
    if "resume" in text and "tracker" in text:
        return "resume_tracker"
    if "job" in text and "dashboard" in text:
        return "job_dashboard"
    if _wants_login(text):
        return "login_app"
    if "admin" in text and "dashboard" in text:
        return "admin_dashboard"
    if fallback:
        return fallback
    return "web_app"


def _derive_title(prompt: str, kind: str, fallback: str = "") -> str:
    if fallback:
        return fallback
    match = re.search(r"(?i)(?:called|named)\s+([a-z0-9][a-z0-9 \-]{2,50})", prompt)
    if match:
        raw = re.sub(r"\s+", " ", str(match.group(1) or "")).strip(" .,-")
        if raw:
            return raw.title()
    defaults = {
        "crm_lead_tracker": "ZoSwi CRM Lead Tracker",
        "application_tracker": "ZoSwi Application Tracker",
        "login_app": "ZoSwi Login App",
        "job_dashboard": "ZoSwi Job Dashboard",
        "resume_tracker": "ZoSwi Resume Tracker",
        "admin_dashboard": "ZoSwi Admin Dashboard",
        "web_app": "ZoSwi Web App",
    }
    return defaults.get(kind, "ZoSwi Web App")


def _extract_features(prompt: str, base: set[str]) -> set[str]:
    text = _normalize_prompt(prompt).lower()
    features = set(base)
    if _disables_login(text):
        features.discard("email_password_login")
        features.discard("signup")
        features.discard("google_login")
    if _wants_login(text) or "email password" in text:
        features.add("email_password_login")
    if not _disables_login(text) and any(token in text for token in ("signup", "sign up", "register")):
        features.add("signup")
    if not _disables_login(text) and any(token in text for token in ("google login", "oauth", "google auth")):
        features.add("google_login")
    if "dark mode" in text:
        features.add("dark_mode")
    if "black" in text and any(token in text for token in ("theme", "color", "mode", "ui", "background")):
        features.add("dark_mode")
    if "admin" in text:
        features.add("admin_dashboard")
    if any(token in text for token in ("database", "postgres", "sqlite", "supabase")):
        features.add("database")
    if any(token in text for token in ("api", "backend")):
        features.add("backend_api")
    if any(token in text for token in ("validation", "validate", "error message")):
        features.add("form_validation")
    if any(token in text for token in ("responsive", "mobile", "tablet")):
        features.add("responsive_ui")
    if any(token in text for token in ("modern", "clean ui", "beautiful")):
        features.add("modern_ui")
    if "analytics" in text:
        features.add("analytics_cards")
    if "job" in text:
        features.add("job_filters")
    if "crm" in text or "lead" in text:
        features.add("lead_pipeline")
    if any(token in text for token in ("status filter", "status filters", "filter by status")):
        features.add("status_filters")
    if any(token in text for token in ("create another", "add another", "new record button")):
        features.add("quick_create")
    if any(token in text for token in ("edit button", "edit selected", "edit created", "edit the created", "update selected")):
        features.add("record_editing")
    if "resume" in text:
        features.add("resume_board")
    if "application" in text and any(token in text for token in ("store", "track", "data", "save", "status")):
        features.add("application_storage")
    features.add("zoswi_branding")
    return features


def _base_features_for_kind(kind: str) -> set[str]:
    if kind == "crm_lead_tracker":
        return {
            "lead_pipeline",
            "status_filters",
            "quick_create",
            "record_editing",
            "form_validation",
            "responsive_ui",
            "modern_ui",
            "zoswi_branding",
        }
    if kind == "application_tracker":
        return {"application_storage", "form_validation", "responsive_ui", "modern_ui", "zoswi_branding"}
    if kind == "login_app":
        return {"email_password_login", "form_validation", "responsive_ui", "modern_ui", "zoswi_branding"}
    if kind == "job_dashboard":
        return {"job_filters", "analytics_cards", "responsive_ui", "modern_ui", "zoswi_branding"}
    if kind == "resume_tracker":
        return {
            "email_password_login",
            "resume_board",
            "form_validation",
            "responsive_ui",
            "modern_ui",
            "zoswi_branding",
        }
    if kind == "admin_dashboard":
        return {"admin_dashboard", "analytics_cards", "responsive_ui", "modern_ui", "zoswi_branding"}
    return {"responsive_ui", "modern_ui", "zoswi_branding"}


def _pick_database(prompt: str, existing_database: str = "") -> str:
    text = _normalize_prompt(prompt).lower()
    if "supabase" in text:
        return "Supabase"
    if "postgres" in text or "postgresql" in text:
        return "PostgreSQL"
    if "sqlite" in text:
        return "SQLite"
    if existing_database:
        return existing_database
    return ""


def _choose_stack(features: set[str]) -> str:
    backend_markers = {"database", "backend_api", "google_login", "admin_dashboard"}
    if features.intersection(backend_markers):
        return "React + FastAPI"
    return "HTML/CSS/JavaScript"


def _friendly_feature_list(features: list[str]) -> list[str]:
    labels: list[str] = []
    for feature in features:
        labels.append(_FRIENDLY_FEATURES.get(feature, feature.replace("_", " ")))
    return labels


def _build_spec(prompt: str, current_spec: dict[str, Any] | None, intent: str) -> dict[str, Any]:
    current = current_spec if isinstance(current_spec, dict) else {}
    edit_mode = intent == INTENT_EDIT and bool(current)
    current_kind = str(current.get("kind", "")).strip()
    kind_fallback = current_kind if edit_mode else ""
    kind = _infer_kind(prompt, fallback=kind_fallback)
    current_title = str(current.get("title", "")).strip()
    title_fallback = current_title if edit_mode and current_kind == kind else ""
    title = _derive_title(prompt, kind, fallback=title_fallback)

    base_features = _base_features_for_kind(kind)
    existing_features = set(current.get("features", [])) if edit_mode else set()
    features = _extract_features(prompt, base_features.union(existing_features))
    stack = _choose_stack(features)
    database = _pick_database(prompt, existing_database=str(current.get("database", "")).strip() if edit_mode else "")
    backend_required = stack == "React + FastAPI"
    if backend_required and not database and "database" in features:
        database = "SQLite"

    features_sorted = sorted(features)
    summary = f"{title} with {', '.join(_friendly_feature_list(features_sorted[:4]))}"
    preview_only = backend_required
    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        "title": title,
        "kind": kind,
        "stack": stack,
        "summary": summary,
        "features": features_sorted,
        "feature_labels": _friendly_feature_list(features_sorted),
        "backend_required": backend_required,
        "database": database,
        "preview_only": preview_only,
        "status": "ready",
        "last_prompt": _normalize_prompt(prompt),
        "generated_at": now_iso,
        "mode": MODE_EDIT if edit_mode else MODE_BUILD_PREVIEW,
    }


def _wrap_preview_html(spec: dict[str, Any], body_html: str, script_js: str) -> str:
    title = str(spec.get("title", "ZoSwi App")).strip()
    prompt_text = _normalize_prompt(str(spec.get("last_prompt", ""))).lower()
    preview_note = (
        "Preview-only mode: frontend is fully interactive; backend/database are scaffolded and ready to wire."
        if bool(spec.get("preview_only"))
        else "Preview is fully interactive inside ZoSwi."
    )
    has_dark_mode = "dark_mode" in set(spec.get("features", []))
    prefers_dark = has_dark_mode and (
        "dark mode" in prompt_text
        or "dark theme" in prompt_text
        or ("black" in prompt_text and any(token in prompt_text for token in ("theme", "color", "ui", "mode", "background")))
    )
    dark_toggle = (
        '<button id="darkModeToggle" class="chip" type="button">Toggle Dark Mode</button>'
        if has_dark_mode
        else ""
    )
    return textwrap.dedent(
        f"""\
        <!doctype html>
        <html lang="en">
        <head>
          <meta charset="utf-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1" />
          <title>{title}</title>
          <style>
            :root {{
              --bg: #eef5ff;
              --panel: #ffffff;
              --panel-soft: #f8fbff;
              --text: #0f2038;
              --muted: #506884;
              --line: #d8e6f8;
              --line-strong: #c5d8f1;
              --brandA: #0ea5e9;
              --brandB: #14b8a6;
              --shadow-soft: 0 10px 24px rgba(15, 23, 42, 0.07);
              --shadow-main: 0 24px 52px rgba(15, 23, 42, 0.14);
            }}
            html.dark {{
              --bg: #081423;
              --panel: #0f2136;
              --panel-soft: #132a43;
              --text: #e6f2ff;
              --muted: #97b3cf;
              --line: #1f3550;
              --line-strong: #2c4667;
              --brandA: #22d3ee;
              --brandB: #34d399;
              --shadow-soft: 0 8px 20px rgba(2, 6, 23, 0.35);
              --shadow-main: 0 20px 44px rgba(2, 6, 23, 0.5);
            }}
            * {{ box-sizing: border-box; }}
            body {{
              margin: 0;
              font-family: "Plus Jakarta Sans", "Inter", "Segoe UI", "Helvetica Neue", Arial, sans-serif;
              background:
                radial-gradient(920px 420px at 0% -20%, rgba(14, 165, 233, 0.22) 0%, transparent 56%),
                radial-gradient(840px 360px at 100% -15%, rgba(20, 184, 166, 0.18) 0%, transparent 58%),
                linear-gradient(180deg, color-mix(in oklab, var(--bg) 94%, #ffffff 6%), var(--bg));
              color: var(--text);
              min-height: 100vh;
              padding: 24px;
              position: relative;
              overflow-x: hidden;
              letter-spacing: 0.01em;
            }}
            body::before {{
              content: "";
              position: fixed;
              inset: -20% -10%;
              pointer-events: none;
              opacity: 0.35;
              background:
                radial-gradient(520px 220px at 12% 10%, color-mix(in oklab, var(--brandA) 55%, transparent 45%) 0%, transparent 70%),
                radial-gradient(520px 250px at 88% 0%, color-mix(in oklab, var(--brandB) 55%, transparent 45%) 0%, transparent 74%);
              filter: blur(34px);
              animation: ambientShift 16s ease-in-out infinite alternate;
            }}
            body::after {{
              content: "";
              position: fixed;
              inset: 0;
              pointer-events: none;
              background-image: linear-gradient(
                to right,
                color-mix(in oklab, var(--line) 24%, transparent 76%) 1px,
                transparent 1px
              );
              background-size: 44px 44px;
              opacity: 0.22;
            }}
            .shell {{
              width: min(1280px, 100%);
              margin: 0 auto;
              border: 1px solid var(--line);
              background: linear-gradient(
                160deg,
                color-mix(in oklab, var(--panel) 96%, white 4%),
                color-mix(in oklab, var(--panel-soft) 95%, white 5%)
              );
              border-radius: 24px;
              box-shadow: var(--shadow-main);
              overflow: hidden;
              animation: shellIn 420ms ease-out;
            }}
            .top {{
              padding: 22px 24px;
              border-bottom: 1px solid var(--line);
              display: flex;
              align-items: center;
              justify-content: space-between;
              gap: 14px;
              flex-wrap: wrap;
              background: linear-gradient(
                120deg,
                color-mix(in oklab, var(--panel-soft) 90%, var(--brandA) 10%),
                color-mix(in oklab, var(--panel-soft) 92%, var(--brandB) 8%)
              );
            }}
            .title {{
              margin: 0;
              font-size: clamp(1.2rem, 2.4vw, 1.6rem);
              font-weight: 800;
              color: var(--text);
              letter-spacing: 0.01em;
            }}
            .subtitle {{
              margin: 6px 0 0 0;
              color: var(--muted);
              font-size: 0.86rem;
              font-weight: 600;
            }}
            .chip-row {{
              display: flex;
              align-items: center;
              gap: 8px;
              flex-wrap: wrap;
            }}
            .chip {{
              border: 1px solid var(--line-strong);
              border-radius: 999px;
              padding: 6px 12px;
              background: color-mix(in oklab, var(--panel) 76%, white 24%);
              color: var(--text);
              font-size: 0.75rem;
              font-weight: 800;
              letter-spacing: 0.08em;
              text-transform: uppercase;
            }}
            .chip.brand {{
              border-color: color-mix(in oklab, var(--brandA) 50%, var(--line) 50%);
              background: linear-gradient(
                120deg,
                color-mix(in oklab, var(--brandA) 32%, white 68%),
                color-mix(in oklab, var(--brandB) 28%, white 72%)
              );
            }}
            .note {{
              margin: 0;
              padding: 12px 24px;
              border-bottom: 1px dashed var(--line);
              color: var(--muted);
              font-size: 0.85rem;
              background: color-mix(in oklab, var(--panel-soft) 82%, white 18%);
            }}
            .content {{
              padding: 22px;
              display: grid;
              gap: 16px;
            }}
            .card {{
              border: 1px solid var(--line);
              border-radius: 16px;
              background: linear-gradient(
                160deg,
                color-mix(in oklab, var(--panel) 94%, white 6%),
                color-mix(in oklab, var(--panel-soft) 96%, white 4%)
              );
              padding: 16px;
              box-shadow: var(--shadow-soft);
            }}
            .section-title {{
              margin: 0;
              font-size: 1.08rem;
              font-weight: 800;
              color: var(--text);
            }}
            .row {{
              display: grid;
              grid-template-columns: repeat(2, minmax(0, 1fr));
              gap: 12px;
            }}
            .row-3 {{
              grid-template-columns: repeat(3, minmax(0, 1fr));
            }}
            label {{
              display: block;
              margin: 0 0 6px 0;
              color: var(--muted);
              font-size: 0.73rem;
              font-weight: 800;
              letter-spacing: 0.08em;
              text-transform: uppercase;
            }}
            .input, .select {{
              width: 100%;
              border: 1px solid var(--line);
              border-radius: 12px;
              background: color-mix(in oklab, var(--panel) 94%, white 6%);
              color: var(--text);
              padding: 11px 12px;
              font-size: 0.9rem;
              transition: border-color 160ms ease, box-shadow 160ms ease, transform 160ms ease;
            }}
            .input:focus, .select:focus {{
              outline: none;
              border-color: color-mix(in oklab, var(--brandA) 55%, var(--line) 45%);
              box-shadow: 0 0 0 4px color-mix(in oklab, var(--brandA) 20%, transparent 80%);
            }}
            .btn {{
              border: 0;
              border-radius: 12px;
              font-weight: 800;
              padding: 10px 14px;
              cursor: pointer;
              transition: transform 150ms ease, box-shadow 150ms ease, filter 150ms ease;
            }}
            .btn:hover {{
              transform: translateY(-1px);
            }}
            .btn.primary {{
              background: linear-gradient(120deg, var(--brandA), var(--brandB));
              color: #072528;
              box-shadow: 0 10px 18px color-mix(in oklab, var(--brandA) 35%, transparent 65%);
            }}
            .btn.primary:hover {{
              filter: brightness(1.03);
            }}
            .btn.secondary {{
              border: 1px solid var(--line);
              background: color-mix(in oklab, var(--panel) 90%, white 10%);
              color: var(--text);
            }}
            .status {{
              margin: 10px 0 0 0;
              font-size: 0.84rem;
              color: var(--muted);
            }}
            .actions-row {{
              display: flex;
              gap: 10px;
              flex-wrap: wrap;
              margin-top: 14px;
            }}
            .toolbar {{
              display: flex;
              align-items: center;
              justify-content: space-between;
              gap: 10px;
              flex-wrap: wrap;
            }}
            .toolbar-controls {{
              display: flex;
              gap: 10px;
              flex-wrap: wrap;
              width: min(560px, 100%);
            }}
            .stats-grid {{
              display: grid;
              grid-template-columns: repeat(4, minmax(0, 1fr));
              gap: 12px;
            }}
            .stat-card {{
              border: 1px solid var(--line);
              border-radius: 14px;
              background: linear-gradient(
                150deg,
                color-mix(in oklab, var(--panel) 94%, white 6%),
                color-mix(in oklab, var(--panel-soft) 92%, white 8%)
              );
              padding: 12px;
            }}
            .stat-label {{
              margin: 0;
              font-size: 0.72rem;
              font-weight: 800;
              letter-spacing: 0.08em;
              text-transform: uppercase;
              color: var(--muted);
            }}
            .stat-value {{
              margin: 6px 0 0 0;
              font-size: 1.42rem;
              font-weight: 800;
              color: var(--text);
            }}
            .table-wrap {{
              margin-top: 12px;
              border: 1px solid var(--line);
              border-radius: 14px;
              overflow-x: auto;
              background: color-mix(in oklab, var(--panel) 95%, white 5%);
            }}
            table {{
              width: 100%;
              border-collapse: collapse;
              font-size: 0.88rem;
            }}
            th {{
              text-align: left;
              padding: 11px 10px;
              border-bottom: 1px solid var(--line);
              color: var(--muted);
              font-size: 0.72rem;
              font-weight: 800;
              letter-spacing: 0.08em;
              text-transform: uppercase;
              background: color-mix(in oklab, var(--panel-soft) 90%, white 10%);
            }}
            td {{
              border-bottom: 1px solid color-mix(in oklab, var(--line) 84%, transparent 16%);
              text-align: left;
              padding: 11px 10px;
            }}
            tbody tr:nth-child(odd) {{
              background: color-mix(in oklab, var(--panel-soft) 84%, transparent 16%);
            }}
            tbody tr:hover {{
              background: color-mix(in oklab, var(--brandA) 10%, var(--panel) 90%);
            }}
            .badge {{
              display: inline-flex;
              align-items: center;
              border: 1px solid var(--line);
              border-radius: 999px;
              padding: 4px 9px;
              font-size: 0.72rem;
              font-weight: 800;
              letter-spacing: 0.04em;
              text-transform: uppercase;
            }}
            .badge.applied {{
              border-color: #9ec8fb;
              background: #eaf4ff;
              color: #1e5aa8;
            }}
            .badge.interview {{
              border-color: #a7efd9;
              background: #e7fcf5;
              color: #0f7f65;
            }}
            .badge.offer {{
              border-color: #9be8be;
              background: #e5faee;
              color: #13724d;
            }}
            .badge.rejected {{
              border-color: #f6b3b9;
              background: #ffedf0;
              color: #b4233a;
            }}
            .footer {{
              border-top: 1px solid var(--line);
              padding: 14px 24px;
              font-size: 0.8rem;
              color: var(--muted);
              text-align: right;
              font-weight: 700;
              background: color-mix(in oklab, var(--panel-soft) 88%, white 12%);
            }}
            @keyframes shellIn {{
              from {{ opacity: 0; transform: translateY(10px); }}
              to {{ opacity: 1; transform: translateY(0); }}
            }}
            @keyframes ambientShift {{
              from {{ transform: translate3d(-1.5%, 0, 0) scale(1); }}
              to {{ transform: translate3d(1.5%, -1%, 0) scale(1.03); }}
            }}
            @media (max-width: 1024px) {{
              .stats-grid {{
                grid-template-columns: repeat(2, minmax(0, 1fr));
              }}
              .row-3 {{
                grid-template-columns: repeat(2, minmax(0, 1fr));
              }}
            }}
            @media (max-width: 768px) {{
              body {{
                padding: 12px;
              }}
              .row {{
                grid-template-columns: 1fr;
              }}
              .row-3 {{
                grid-template-columns: 1fr;
              }}
              .top {{
                align-items: flex-start;
              }}
              .toolbar-controls {{
                width: 100%;
              }}
              .stats-grid {{
                grid-template-columns: 1fr;
              }}
              .shell {{
                border-radius: 18px;
              }}
            }}
          </style>
        </head>
        <body>
          <div class="shell">
            <div class="top">
              <div>
                <h1 class="title">{title}</h1>
                <p class="subtitle">Built with ZoSwi Instant App Builder</p>
              </div>
              <div class="chip-row">
                <span class="chip brand">Build + Preview</span>
                <span class="chip">{str(spec.get("stack", "HTML/CSS/JavaScript"))}</span>
                {dark_toggle}
              </div>
            </div>
            <p class="note">{preview_note}</p>
            <div class="content">
              {body_html}
            </div>
            <div class="footer">Powered by ZoSwi</div>
          </div>
          <script>
            (() => {{
              const darkModeEnabled = {str(has_dark_mode).lower()};
              const preferDark = {str(prefers_dark).lower()};
              if (darkModeEnabled) {{
                const root = document.documentElement;
                const toggle = document.getElementById("darkModeToggle");
                const cached = localStorage.getItem("zoswi_builder_dark");
                if (cached === "1") {{
                  root.classList.add("dark");
                }} else if (cached !== "0" && preferDark) {{
                  root.classList.add("dark");
                }}
                if (toggle) {{
                  toggle.addEventListener("click", () => {{
                    root.classList.toggle("dark");
                    localStorage.setItem("zoswi_builder_dark", root.classList.contains("dark") ? "1" : "0");
                  }});
                }}
              }}
              {script_js}
            }})();
          </script>
        </body>
        </html>
        """
    ).strip()


def _build_login_preview(spec: dict[str, Any]) -> tuple[str, str]:
    features = set(spec.get("features", []))
    google_button = (
        '<button id="googleLoginBtn" class="btn secondary" type="button">Continue with Google</button>'
        if "google_login" in features
        else ""
    )
    signup_line = (
        '<p class="status">Need an account? <a href="#" style="color:inherit;font-weight:700;">Create one</a></p>'
        if "signup" in features
        else ""
    )
    body = (
        '<div class="card">'
        '<h2 style="margin:0 0 10px 0;">Welcome Back</h2>'
        '<p style="margin:0 0 12px 0;color:var(--muted);">Sign in to continue.</p>'
        '<form id="loginForm">'
        '<div class="row">'
        '<div><label>Email</label><input id="emailInput" class="input" type="email" placeholder="you@example.com" required /></div>'
        '<div><label>Password</label><input id="passwordInput" class="input" type="password" placeholder="********" required /></div>'
        "</div>"
        '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:12px;">'
        '<button class="btn primary" type="submit">Login</button>'
        f"{google_button}"
        "</div>"
        '<p id="loginStatus" class="status">Ready.</p>'
        "</form>"
        f"{signup_line}"
        "</div>"
    )
    script = (
        "const loginForm = document.getElementById('loginForm');"
        "const loginStatus = document.getElementById('loginStatus');"
        "if (loginForm) {"
        "  loginForm.addEventListener('submit', (event) => {"
        "    event.preventDefault();"
        "    const email = String(document.getElementById('emailInput')?.value || '').trim();"
        "    const password = String(document.getElementById('passwordInput')?.value || '');"
        "    if (!email || !password) {"
        "      loginStatus.textContent = 'Please enter email and password.';"
        "      return;"
        "    }"
        "    loginStatus.textContent = `Signed in as ${email}. (Preview mode)`;"
        "  });"
        "}"
        "const googleBtn = document.getElementById('googleLoginBtn');"
        "if (googleBtn) {"
        "  googleBtn.addEventListener('click', () => {"
        "    loginStatus.textContent = 'Google OAuth preview triggered. Backend wiring can be added next.';"
        "  });"
        "}"
    )
    return body, script


def _build_job_dashboard_preview(spec: dict[str, Any]) -> tuple[str, str]:
    features = set(spec.get("features", []))
    admin_card = ""
    if "admin_dashboard" in features:
        admin_card = (
            '<div class="card"><h3 style="margin-top:0;">Admin Snapshot</h3>'
            '<div class="row">'
            '<div><strong>46</strong><p class="status">Active applications</p></div>'
            '<div><strong>12</strong><p class="status">Interviews in progress</p></div>'
            "</div></div>"
        )
    body = (
        '<div class="card">'
        '<h2 style="margin:0 0 10px 0;">Job Dashboard</h2>'
        '<div class="row">'
        '<input id="jobQueryInput" class="input" placeholder="Search role..." />'
        '<input id="jobLocationInput" class="input" placeholder="Location..." />'
        "</div>"
        '<div style="margin-top:12px;"><button id="jobFilterBtn" class="btn primary" type="button">Apply Filters</button></div>'
        "</div>"
        '<div class="card">'
        '<table><thead><tr><th>Role</th><th>Location</th><th>Status</th><th>Fit</th></tr></thead><tbody id="jobRows"></tbody></table>'
        '<p id="jobStatus" class="status">Showing recommended matches.</p>'
        "</div>"
        f"{admin_card}"
    )
    sample_jobs = [
        {"role": "Backend Engineer", "location": "Austin, TX", "status": "Applied", "fit": "92%"},
        {"role": "Frontend Engineer", "location": "Remote", "status": "Interview", "fit": "88%"},
        {"role": "Full Stack Developer", "location": "New York, NY", "status": "Saved", "fit": "83%"},
        {"role": "Platform Engineer", "location": "Seattle, WA", "status": "Applied", "fit": "86%"},
    ]
    jobs_json = json.dumps(sample_jobs)
    script = (
        f"const allJobs = {jobs_json};"
        "const rows = document.getElementById('jobRows');"
        "const jobStatus = document.getElementById('jobStatus');"
        "const queryInput = document.getElementById('jobQueryInput');"
        "const locationInput = document.getElementById('jobLocationInput');"
        "function renderJobs(jobs) {"
        "  if (!rows) { return; }"
        "  rows.innerHTML = jobs.map((job) => `<tr><td>${job.role}</td><td>${job.location}</td><td>${job.status}</td><td>${job.fit}</td></tr>`).join('');"
        "  if (jobStatus) { jobStatus.textContent = `${jobs.length} jobs shown (preview dataset).`; }"
        "}"
        "renderJobs(allJobs);"
        "const btn = document.getElementById('jobFilterBtn');"
        "if (btn) {"
        "  btn.addEventListener('click', () => {"
        "    const query = String(queryInput?.value || '').toLowerCase();"
        "    const location = String(locationInput?.value || '').toLowerCase();"
        "    const filtered = allJobs.filter((job) => job.role.toLowerCase().includes(query) && job.location.toLowerCase().includes(location));"
        "    renderJobs(filtered);"
        "  });"
        "}"
    )
    return body, script


def _build_resume_tracker_preview(spec: dict[str, Any]) -> tuple[str, str]:
    body = (
        '<div class="card">'
        '<h2 style="margin:0 0 10px 0;">Resume Tracker</h2>'
        '<div class="row">'
        '<input id="resumeTitleInput" class="input" placeholder="Resume title (e.g. Backend v3)" />'
        '<select id="resumeStatusInput" class="select"><option value="Draft">Draft</option><option value="Submitted">Submitted</option><option value="Interview">Interview</option></select>'
        "</div>"
        '<div style="margin-top:12px;"><button id="resumeAddBtn" class="btn primary" type="button">Add Resume Entry</button></div>'
        '<p id="resumeStatusText" class="status">Track versions, submissions, and interview outcomes.</p>'
        "</div>"
        '<div class="card"><table><thead><tr><th>Resume</th><th>Status</th><th>Last Updated</th></tr></thead><tbody id="resumeRows"></tbody></table></div>'
    )
    initial_rows = [
        {"title": "Backend Engineer Resume", "status": "Submitted", "updated": "2026-03-30"},
        {"title": "Full Stack Resume", "status": "Interview", "updated": "2026-03-28"},
    ]
    rows_json = json.dumps(initial_rows)
    script = (
        f"const resumes = {rows_json};"
        "const rows = document.getElementById('resumeRows');"
        "const statusText = document.getElementById('resumeStatusText');"
        "function renderResumes() {"
        "  if (!rows) { return; }"
        "  rows.innerHTML = resumes.map((item) => `<tr><td>${item.title}</td><td>${item.status}</td><td>${item.updated}</td></tr>`).join('');"
        "}"
        "renderResumes();"
        "const addBtn = document.getElementById('resumeAddBtn');"
        "if (addBtn) {"
        "  addBtn.addEventListener('click', () => {"
        "    const title = String(document.getElementById('resumeTitleInput')?.value || '').trim();"
        "    const status = String(document.getElementById('resumeStatusInput')?.value || 'Draft');"
        "    if (!title) {"
        "      if (statusText) { statusText.textContent = 'Enter a resume title first.'; }"
        "      return;"
        "    }"
        "    resumes.unshift({ title, status, updated: new Date().toISOString().slice(0, 10) });"
        "    renderResumes();"
        "    if (statusText) { statusText.textContent = `${title} added (preview state).`; }"
        "  });"
        "}"
    )
    return body, script


def _build_crm_lead_tracker_preview(spec: dict[str, Any]) -> tuple[str, str]:
    body = textwrap.dedent(
        """\
        <div class="stats-grid">
          <article class="stat-card">
            <p class="stat-label">Total Leads</p>
            <p id="leadStatTotal" class="stat-value">0</p>
          </article>
          <article class="stat-card">
            <p class="stat-label">Qualified + Proposal</p>
            <p id="leadStatQualified" class="stat-value">0</p>
          </article>
          <article class="stat-card">
            <p class="stat-label">Won Deals</p>
            <p id="leadStatWon" class="stat-value">0</p>
          </article>
          <article class="stat-card">
            <p class="stat-label">Win Rate</p>
            <p id="leadStatWinRate" class="stat-value">0%</p>
          </article>
        </div>
        <div class="card">
          <div class="toolbar">
            <div>
              <h2 class="section-title">CRM Lead Tracker</h2>
              <p class="status">Manage leads, filter pipeline statuses, and edit selected records.</p>
            </div>
            <span class="chip">Responsive Layout</span>
          </div>
          <div class="row row-3" style="margin-top:12px;">
            <div>
              <label for="leadNameInput">Lead Name</label>
              <input id="leadNameInput" class="input" placeholder="Alex Morgan" />
            </div>
            <div>
              <label for="leadCompanyInput">Company</label>
              <input id="leadCompanyInput" class="input" placeholder="Northwind Labs" />
            </div>
            <div>
              <label for="leadEmailInput">Email</label>
              <input id="leadEmailInput" class="input" placeholder="alex@northwindlabs.com" />
            </div>
          </div>
          <div class="row" style="margin-top:12px;">
            <div>
              <label for="leadStatusInput">Pipeline Status</label>
              <select id="leadStatusInput" class="select">
                <option value="New">New</option>
                <option value="Contacted">Contacted</option>
                <option value="Qualified">Qualified</option>
                <option value="Proposal">Proposal</option>
                <option value="Won">Won</option>
                <option value="Lost">Lost</option>
              </select>
            </div>
            <div>
              <label for="leadNextStepInput">Next Step</label>
              <input id="leadNextStepInput" class="input" placeholder="Schedule discovery call" />
            </div>
          </div>
          <div class="actions-row">
            <button id="leadSaveBtn" class="btn primary" type="button">Save Lead</button>
            <button id="leadCreateAnotherBtn" class="btn secondary" type="button">Create Another</button>
            <button id="leadEditBtn" class="btn secondary" type="button">Edit Selected</button>
          </div>
          <p id="leadStatusText" class="status">Select a row, click Edit Selected, update fields, then Save Lead.</p>
        </div>
        <div class="card">
          <div class="toolbar">
            <h3 class="section-title">Lead Pipeline</h3>
            <div class="toolbar-controls">
              <input id="leadSearchInput" class="input" placeholder="Search lead, company, or email..." />
              <select id="leadFilterInput" class="select">
                <option value="">All statuses</option>
                <option value="New">New</option>
                <option value="Contacted">Contacted</option>
                <option value="Qualified">Qualified</option>
                <option value="Proposal">Proposal</option>
                <option value="Won">Won</option>
                <option value="Lost">Lost</option>
              </select>
            </div>
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Lead</th>
                  <th>Company</th>
                  <th>Email</th>
                  <th>Status</th>
                  <th>Next Step</th>
                  <th>Updated</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody id="leadRows"></tbody>
            </table>
          </div>
        </div>
        """
    ).strip()

    initial_rows = [
        {
            "id": "lead-1001",
            "name": "Ava Johnson",
            "company": "Northwind Labs",
            "email": "ava@northwindlabs.com",
            "status": "Qualified",
            "next_step": "Demo walkthrough",
            "updated": "2026-03-31",
        },
        {
            "id": "lead-1002",
            "name": "Liam Carter",
            "company": "Helio Systems",
            "email": "liam@heliosystems.com",
            "status": "Proposal",
            "next_step": "Commercial proposal review",
            "updated": "2026-03-30",
        },
        {
            "id": "lead-1003",
            "name": "Sophia Reed",
            "company": "BluePeak AI",
            "email": "sophia@bluepeak.ai",
            "status": "New",
            "next_step": "Send intro email",
            "updated": "2026-03-29",
        },
    ]
    rows_json = json.dumps(initial_rows)
    script_template = textwrap.dedent(
        """\
        const leads = __ROWS_JSON__;
        let selectedLeadId = leads.length > 0 ? String(leads[0].id) : "";
        let editingLeadId = "";

        const rows = document.getElementById("leadRows");
        const statusText = document.getElementById("leadStatusText");
        const searchInput = document.getElementById("leadSearchInput");
        const filterInput = document.getElementById("leadFilterInput");
        const statTotal = document.getElementById("leadStatTotal");
        const statQualified = document.getElementById("leadStatQualified");
        const statWon = document.getElementById("leadStatWon");
        const statWinRate = document.getElementById("leadStatWinRate");

        function sanitize(input) {
          return String(input || "").trim();
        }

        function getStatusClass(status) {
          const value = String(status || "").toLowerCase();
          if (value.includes("won")) { return "offer"; }
          if (value.includes("qualified") || value.includes("proposal") || value.includes("contacted")) { return "interview"; }
          if (value.includes("lost")) { return "rejected"; }
          return "applied";
        }

        function renderStats() {
          const total = leads.length;
          const qualified = leads.filter((lead) => {
            const value = String(lead.status || "").toLowerCase();
            return value === "qualified" || value === "proposal";
          }).length;
          const won = leads.filter((lead) => String(lead.status || "").toLowerCase() === "won").length;
          const winRate = total > 0 ? Math.round((won / total) * 100) : 0;
          if (statTotal) { statTotal.textContent = String(total); }
          if (statQualified) { statQualified.textContent = String(qualified); }
          if (statWon) { statWon.textContent = String(won); }
          if (statWinRate) { statWinRate.textContent = `${winRate}%`; }
        }

        function getFilteredLeads() {
          const query = sanitize(searchInput?.value).toLowerCase();
          const selectedStatus = sanitize(filterInput?.value).toLowerCase();
          return leads.filter((lead) => {
            const text = `${lead.name} ${lead.company} ${lead.email} ${lead.next_step}`.toLowerCase();
            const matchesQuery = !query || text.includes(query);
            const matchesStatus = !selectedStatus || String(lead.status || "").toLowerCase() === selectedStatus;
            return matchesQuery && matchesStatus;
          });
        }

        function renderLeads() {
          if (!rows) { return; }
          const filtered = getFilteredLeads();
          rows.innerHTML = filtered.map((lead) => {
            const isSelected = String(lead.id) === selectedLeadId;
            const selectedStyle = isSelected
              ? ' style="background: color-mix(in oklab, var(--brandA) 12%, var(--panel) 88%);"'
              : "";
            return `<tr${selectedStyle}>
              <td><strong>${lead.name}</strong></td>
              <td>${lead.company}</td>
              <td>${lead.email}</td>
              <td><span class="badge ${getStatusClass(lead.status)}">${lead.status}</span></td>
              <td>${lead.next_step}</td>
              <td>${lead.updated}</td>
              <td><button type="button" class="btn secondary lead-select-btn" data-lead-id="${lead.id}">Select</button></td>
            </tr>`;
          }).join("");

          const selectButtons = Array.from(document.querySelectorAll(".lead-select-btn"));
          for (const button of selectButtons) {
            button.addEventListener("click", () => {
              selectedLeadId = String(button.getAttribute("data-lead-id") || "");
              renderLeads();
              if (statusText) { statusText.textContent = "Lead selected. Click Edit Selected to modify values."; }
            });
          }
          renderStats();
        }

        function setFormValues(lead) {
          const nameInput = document.getElementById("leadNameInput");
          const companyInput = document.getElementById("leadCompanyInput");
          const emailInput = document.getElementById("leadEmailInput");
          const statusInput = document.getElementById("leadStatusInput");
          const nextStepInput = document.getElementById("leadNextStepInput");
          if (nameInput) { nameInput.value = lead?.name || ""; }
          if (companyInput) { companyInput.value = lead?.company || ""; }
          if (emailInput) { emailInput.value = lead?.email || ""; }
          if (statusInput) { statusInput.value = lead?.status || "New"; }
          if (nextStepInput) { nextStepInput.value = lead?.next_step || ""; }
        }

        function clearLeadForm() {
          setFormValues({ name: "", company: "", email: "", status: "New", next_step: "" });
          editingLeadId = "";
        }

        function collectLeadFormValues() {
          return {
            name: sanitize(document.getElementById("leadNameInput")?.value),
            company: sanitize(document.getElementById("leadCompanyInput")?.value),
            email: sanitize(document.getElementById("leadEmailInput")?.value),
            status: sanitize(document.getElementById("leadStatusInput")?.value) || "New",
            next_step: sanitize(document.getElementById("leadNextStepInput")?.value),
          };
        }

        const saveBtn = document.getElementById("leadSaveBtn");
        if (saveBtn) {
          saveBtn.addEventListener("click", () => {
            const values = collectLeadFormValues();
            if (!values.name || !values.company) {
              if (statusText) { statusText.textContent = "Lead name and company are required."; }
              return;
            }
            const nowDate = new Date().toISOString().slice(0, 10);
            if (editingLeadId) {
              const target = leads.find((lead) => String(lead.id) === editingLeadId);
              if (target) {
                target.name = values.name;
                target.company = values.company;
                target.email = values.email;
                target.status = values.status;
                target.next_step = values.next_step;
                target.updated = nowDate;
                selectedLeadId = String(target.id);
                if (statusText) { statusText.textContent = `${target.name} updated.`; }
              }
            } else {
              const newLead = {
                id: `lead-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
                name: values.name,
                company: values.company,
                email: values.email,
                status: values.status,
                next_step: values.next_step,
                updated: nowDate,
              };
              leads.unshift(newLead);
              selectedLeadId = String(newLead.id);
              if (statusText) { statusText.textContent = `${newLead.name} created.`; }
            }
            editingLeadId = "";
            renderLeads();
          });
        }

        const createAnotherBtn = document.getElementById("leadCreateAnotherBtn");
        if (createAnotherBtn) {
          createAnotherBtn.addEventListener("click", () => {
            clearLeadForm();
            if (statusText) { statusText.textContent = "Ready to create another lead."; }
          });
        }

        const editBtn = document.getElementById("leadEditBtn");
        if (editBtn) {
          editBtn.addEventListener("click", () => {
            if (!selectedLeadId) {
              if (statusText) { statusText.textContent = "Select a lead first."; }
              return;
            }
            const target = leads.find((lead) => String(lead.id) === selectedLeadId);
            if (!target) {
              if (statusText) { statusText.textContent = "Selected lead is not available."; }
              return;
            }
            editingLeadId = String(target.id);
            setFormValues(target);
            if (statusText) { statusText.textContent = `Editing ${target.name}. Update fields and click Save Lead.`; }
          });
        }

        if (searchInput) {
          searchInput.addEventListener("input", renderLeads);
        }
        if (filterInput) {
          filterInput.addEventListener("change", renderLeads);
        }

        renderLeads();
        """
    ).strip()
    script = script_template.replace("__ROWS_JSON__", rows_json)
    return body, script


def _build_application_tracker_preview(spec: dict[str, Any]) -> tuple[str, str]:
    body = textwrap.dedent(
        """\
        <div class="stats-grid">
          <article class="stat-card">
            <p class="stat-label">Total Applications</p>
            <p id="appStatTotal" class="stat-value">0</p>
          </article>
          <article class="stat-card">
            <p class="stat-label">Interviews</p>
            <p id="appStatInterview" class="stat-value">0</p>
          </article>
          <article class="stat-card">
            <p class="stat-label">Offers</p>
            <p id="appStatOffer" class="stat-value">0</p>
          </article>
          <article class="stat-card">
            <p class="stat-label">Response Rate</p>
            <p id="appStatResponse" class="stat-value">0%</p>
          </article>
        </div>
        <div class="card">
          <div class="toolbar">
            <div>
              <h2 class="section-title">Application Tracker</h2>
              <p class="status">Store and manage job applications without login.</p>
            </div>
            <span class="chip">No Login Required</span>
          </div>
          <div class="row row-3" style="margin-top:12px;">
            <div>
              <label for="appCompanyInput">Company</label>
              <input id="appCompanyInput" class="input" placeholder="Acme Corp" />
            </div>
            <div>
              <label for="appRoleInput">Role</label>
              <input id="appRoleInput" class="input" placeholder="Backend Engineer" />
            </div>
            <div>
              <label for="appSourceInput">Source</label>
              <input id="appSourceInput" class="input" placeholder="LinkedIn, Referral, Career Site" />
            </div>
          </div>
          <div class="row" style="margin-top:12px;">
            <div>
              <label for="appStatusInput">Status</label>
              <select id="appStatusInput" class="select">
                <option value="Applied">Applied</option>
                <option value="Interview">Interview</option>
                <option value="Offer">Offer</option>
                <option value="Rejected">Rejected</option>
              </select>
            </div>
            <div>
              <label for="appDateInput">Date</label>
              <input id="appDateInput" class="input" type="date" />
            </div>
          </div>
          <div class="actions-row">
            <button id="appAddBtn" class="btn primary" type="button">Save Application</button>
            <button id="appClearBtn" class="btn secondary" type="button">Clear</button>
          </div>
          <p id="appStatusText" class="status">Live preview updates as you add and filter entries.</p>
        </div>
        <div class="card">
          <div class="toolbar">
            <h3 class="section-title">Application Pipeline</h3>
            <div class="toolbar-controls">
              <input id="appSearchInput" class="input" placeholder="Search company, role, or source..." />
              <select id="appFilterStatus" class="select">
                <option value="">All statuses</option>
                <option value="Applied">Applied</option>
                <option value="Interview">Interview</option>
                <option value="Offer">Offer</option>
                <option value="Rejected">Rejected</option>
              </select>
            </div>
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Company</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Date</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody id="appRows"></tbody>
            </table>
          </div>
        </div>
        """
    ).strip()
    initial_rows = [
        {
            "company": "Acme Corp",
            "role": "Software Engineer",
            "status": "Applied",
            "date": "2026-03-30",
            "source": "LinkedIn",
        },
        {
            "company": "Nimbus Labs",
            "role": "Backend Developer",
            "status": "Interview",
            "date": "2026-03-28",
            "source": "Referral",
        },
        {
            "company": "Vertex Cloud",
            "role": "Platform Engineer",
            "status": "Offer",
            "date": "2026-03-26",
            "source": "Career Site",
        },
    ]
    rows_json = json.dumps(initial_rows)
    script_template = textwrap.dedent(
        """\
        const applicationRows = __ROWS_JSON__;
        const rows = document.getElementById("appRows");
        const statusText = document.getElementById("appStatusText");
        const searchInput = document.getElementById("appSearchInput");
        const statusFilter = document.getElementById("appFilterStatus");
        const statTotal = document.getElementById("appStatTotal");
        const statInterview = document.getElementById("appStatInterview");
        const statOffer = document.getElementById("appStatOffer");
        const statResponse = document.getElementById("appStatResponse");

        function statusBadge(status) {
          const raw = String(status || "");
          const lowered = raw.toLowerCase();
          let cls = "applied";
          if (lowered.includes("interview")) {
            cls = "interview";
          } else if (lowered.includes("offer")) {
            cls = "offer";
          } else if (lowered.includes("reject")) {
            cls = "rejected";
          }
          return `<span class="badge ${cls}">${raw}</span>`;
        }

        function updateStats() {
          const total = applicationRows.length;
          const interviews = applicationRows.filter((item) => String(item.status || "").toLowerCase().includes("interview")).length;
          const offers = applicationRows.filter((item) => String(item.status || "").toLowerCase().includes("offer")).length;
          const responsive = applicationRows.filter((item) => {
            const lowered = String(item.status || "").toLowerCase();
            return lowered.includes("interview") || lowered.includes("offer") || lowered.includes("reject");
          }).length;
          const responseRate = total > 0 ? Math.round((responsive / total) * 100) : 0;
          if (statTotal) { statTotal.textContent = String(total); }
          if (statInterview) { statInterview.textContent = String(interviews); }
          if (statOffer) { statOffer.textContent = String(offers); }
          if (statResponse) { statResponse.textContent = `${responseRate}%`; }
        }

        function getFilteredRows() {
          const query = String(searchInput?.value || "").trim().toLowerCase();
          const selectedStatus = String(statusFilter?.value || "").trim().toLowerCase();
          return applicationRows.filter((item) => {
            const company = String(item.company || "").toLowerCase();
            const role = String(item.role || "").toLowerCase();
            const source = String(item.source || "").toLowerCase();
            const status = String(item.status || "").toLowerCase();
            const matchesQuery = !query || company.includes(query) || role.includes(query) || source.includes(query);
            const matchesStatus = !selectedStatus || status === selectedStatus;
            return matchesQuery && matchesStatus;
          });
        }

        function renderApplications() {
          if (!rows) { return; }
          const filteredRows = getFilteredRows();
          rows.innerHTML = filteredRows
            .map(
              (item) =>
                `<tr><td><strong>${item.company}</strong></td><td>${item.role}</td><td>${statusBadge(item.status)}</td><td>${item.date}</td><td>${item.source || "-"}</td></tr>`
            )
            .join("");
          updateStats();
          if (statusText) {
            const suffix = filteredRows.length === applicationRows.length ? "" : ` (filtered from ${applicationRows.length})`;
            statusText.textContent = `${filteredRows.length} application records shown${suffix}.`;
          }
        }

        renderApplications();

        const addBtn = document.getElementById("appAddBtn");
        if (addBtn) {
          addBtn.addEventListener("click", () => {
            const company = String(document.getElementById("appCompanyInput")?.value || "").trim();
            const role = String(document.getElementById("appRoleInput")?.value || "").trim();
            const source = String(document.getElementById("appSourceInput")?.value || "").trim();
            const status = String(document.getElementById("appStatusInput")?.value || "Applied");
            const date = String(document.getElementById("appDateInput")?.value || "").trim() || new Date().toISOString().slice(0, 10);
            if (!company || !role) {
              if (statusText) { statusText.textContent = "Company and role are required."; }
              return;
            }
            applicationRows.unshift({ company, role, source, status, date });
            renderApplications();
            if (statusText) { statusText.textContent = `${company} - ${role} saved.`; }
          });
        }

        const clearBtn = document.getElementById("appClearBtn");
        if (clearBtn) {
          clearBtn.addEventListener("click", () => {
            ["appCompanyInput", "appRoleInput", "appSourceInput", "appDateInput"].forEach((id) => {
              const input = document.getElementById(id);
              if (input) { input.value = ""; }
            });
            const statusInput = document.getElementById("appStatusInput");
            if (statusInput) { statusInput.value = "Applied"; }
            if (statusText) { statusText.textContent = "Form cleared."; }
          });
        }

        if (searchInput) {
          searchInput.addEventListener("input", renderApplications);
        }
        if (statusFilter) {
          statusFilter.addEventListener("change", renderApplications);
        }
        """
    ).strip()
    script = script_template.replace("__ROWS_JSON__", rows_json)
    return body, script


def _build_generic_preview(spec: dict[str, Any]) -> tuple[str, str]:
    prompt_text = _normalize_prompt(str(spec.get("last_prompt", "")))
    lowered = prompt_text.lower()

    workspace_title = "Generated Data Workspace"
    workspace_description = "Generated from your prompt and ready for iteration."
    field_labels = ["Name", "Category", "Notes"]
    status_options = ["New", "In Progress", "Done"]

    if "expense" in lowered or "budget" in lowered:
        workspace_title = "Expense Tracker"
        workspace_description = "Track expenses with category and payment details."
        field_labels = ["Expense", "Category", "Amount"]
        status_options = ["Planned", "Paid", "Reimbursed"]
    elif "inventory" in lowered or "stock" in lowered:
        workspace_title = "Inventory Manager"
        workspace_description = "Track items, stock levels, and supplier notes."
        field_labels = ["Item", "SKU", "Stock"]
        status_options = ["Available", "Low", "Out"]
    elif "lead" in lowered or "crm" in lowered or "customer" in lowered:
        workspace_title = "CRM Pipeline"
        workspace_description = "Capture leads and move them through pipeline stages."
        field_labels = ["Lead", "Company", "Next Step"]
        status_options = ["New", "Qualified", "Proposal", "Won"]
    elif "project" in lowered:
        workspace_title = "Project Tracker"
        workspace_description = "Manage project items, priorities, and progress."
        field_labels = ["Task", "Owner", "Priority"]
        status_options = ["Backlog", "In Progress", "Review", "Done"]
    elif "application" in lowered:
        workspace_title = "Application Data Workspace"
        workspace_description = "Store and refine application data without authentication."
        field_labels = ["Company", "Role", "Source"]
        status_options = ["Applied", "Interview", "Offer", "Rejected"]
    else:
        topic_match = re.search(r"(?:for|of|to|about)\s+([a-z][a-z0-9 \-]{2,36})", lowered)
        if topic_match:
            inferred_topic = str(topic_match.group(1) or "").strip(" .,-")
            if inferred_topic:
                workspace_title = f"{inferred_topic.title()} Workspace"

    safe_title = str(workspace_title).replace("<", "&lt;").replace(">", "&gt;")
    safe_description = str(workspace_description).replace("<", "&lt;").replace(">", "&gt;")
    headers = field_labels[:3]
    header_cells = "".join([f"<th>{label}</th>" for label in headers]) + "<th>Status</th><th>Updated</th>"
    input_cells = "".join(
        [
            (
                f'<div><label>{label}</label>'
                f'<input id="recordField{index}" class="input" placeholder="{label}" /></div>'
            )
            for index, label in enumerate(headers)
        ]
    )
    status_options_html = "".join([f'<option value="{label}">{label}</option>' for label in status_options])

    initial_rows = [
        {
            "f0": f"Sample {headers[0]}",
            "f1": f"Sample {headers[1]}",
            "f2": f"Sample {headers[2]}",
            "status": status_options[0],
            "updated": "2026-03-31",
        },
        {
            "f0": f"Second {headers[0]}",
            "f1": f"Second {headers[1]}",
            "f2": f"Second {headers[2]}",
            "status": status_options[min(1, len(status_options) - 1)],
            "updated": "2026-03-30",
        },
    ]
    rows_json = json.dumps(initial_rows)

    body = (
        '<div class="card">'
        f'<h2 style="margin:0 0 6px 0;">{safe_title}</h2>'
        f'<p style="margin:0 0 12px 0;color:var(--muted);">{safe_description}</p>'
        '<div class="row">'
        f"{input_cells}"
        "</div>"
        '<div class="row" style="margin-top:12px;">'
        f'<div><label>Status</label><select id="recordStatusInput" class="select">{status_options_html}</select></div>'
        '<div><label>Updated Date</label><input id="recordDateInput" class="input" type="date" /></div>'
        "</div>"
        '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:12px;">'
        '<button id="recordAddBtn" class="btn primary" type="button">Save Record</button>'
        '<button id="recordResetBtn" class="btn secondary" type="button">Reset Form</button>'
        "</div>"
        '<p id="recordStatusText" class="status">This workspace updates live from your prompt.</p>'
        "</div>"
        '<div class="card"><table><thead><tr>'
        f"{header_cells}"
        '</tr></thead><tbody id="recordRows"></tbody></table></div>'
    )
    script = (
        f"const records = {rows_json};"
        "const rows = document.getElementById('recordRows');"
        "const statusText = document.getElementById('recordStatusText');"
        "function renderRecords() {"
        "  if (!rows) { return; }"
        "  rows.innerHTML = records.map((item) => `<tr><td>${item.f0}</td><td>${item.f1}</td><td>${item.f2}</td><td>${item.status}</td><td>${item.updated}</td></tr>`).join('');"
        "}"
        "renderRecords();"
        "const addBtn = document.getElementById('recordAddBtn');"
        "if (addBtn) {"
        "  addBtn.addEventListener('click', () => {"
        "    const f0 = String(document.getElementById('recordField0')?.value || '').trim();"
        "    const f1 = String(document.getElementById('recordField1')?.value || '').trim();"
        "    const f2 = String(document.getElementById('recordField2')?.value || '').trim();"
        "    const status = String(document.getElementById('recordStatusInput')?.value || '').trim() || 'New';"
        "    const updated = String(document.getElementById('recordDateInput')?.value || '').trim() || new Date().toISOString().slice(0, 10);"
        "    if (!f0) {"
        "      if (statusText) { statusText.textContent = 'Enter the first field before saving.'; }"
        "      return;"
        "    }"
        "    records.unshift({ f0, f1, f2, status, updated });"
        "    renderRecords();"
        "    if (statusText) { statusText.textContent = `${f0} saved in preview state.`; }"
        "  });"
        "}"
        "const resetBtn = document.getElementById('recordResetBtn');"
        "if (resetBtn) {"
        "  resetBtn.addEventListener('click', () => {"
        "    ['recordField0', 'recordField1', 'recordField2', 'recordDateInput'].forEach((id) => {"
        "      const input = document.getElementById(id);"
        "      if (input) { input.value = ''; }"
        "    });"
        "    const statusInput = document.getElementById('recordStatusInput');"
        "    if (statusInput) { statusInput.value = statusInput.options[0]?.value || ''; }"
        "    if (statusText) { statusText.textContent = 'Form reset.'; }"
        "  });"
        "}"
    )
    return body, script


def _build_preview_html(spec: dict[str, Any]) -> str:
    kind = str(spec.get("kind", "web_app")).strip()
    if kind == "login_app":
        body, script = _build_login_preview(spec)
    elif kind == "crm_lead_tracker":
        body, script = _build_crm_lead_tracker_preview(spec)
    elif kind == "application_tracker":
        body, script = _build_application_tracker_preview(spec)
    elif kind == "job_dashboard":
        body, script = _build_job_dashboard_preview(spec)
    elif kind == "resume_tracker":
        body, script = _build_resume_tracker_preview(spec)
    else:
        body, script = _build_generic_preview(spec)
    return _wrap_preview_html(spec, body, script)


def _build_readme(spec: dict[str, Any]) -> str:
    features = "\n".join([f"- {label}" for label in spec.get("feature_labels", [])[:12]])
    stack = str(spec.get("stack", "HTML/CSS/JavaScript"))
    backend = "Yes" if bool(spec.get("backend_required")) else "No"
    database = str(spec.get("database", "")).strip() or "None"
    return textwrap.dedent(
        f"""\
        # {spec.get("title", "ZoSwi App")}

        Built with ZoSwi Instant App Builder.

        ## Stack
        - {stack}
        - Backend Required: {backend}
        - Database: {database}

        ## Included Features
        {features if features else "- Core UI shell"}

        ## Preview Note
        {"This project includes a preview-first frontend and backend scaffolding." if spec.get("preview_only") else "This preview is fully interactive."}
        """
    ).strip()


def _build_html_project_files(spec: dict[str, Any], preview_html: str) -> dict[str, str]:
    return {
        "README.md": _build_readme(spec),
        "app-spec.json": json.dumps(spec, indent=2),
        "index.html": preview_html,
    }


def _build_react_fastapi_project_files(spec: dict[str, Any], preview_html: str) -> dict[str, str]:
    title = str(spec.get("title", "ZoSwi App"))
    feature_lines = "\n".join([f"        <li>{label}</li>" for label in spec.get("feature_labels", [])[:10]])
    files = {
        "README.md": _build_readme(spec),
        "app-spec.json": json.dumps(spec, indent=2),
        "preview/index.html": preview_html,
        "frontend/package.json": json.dumps(
            {
                "name": "zoswi-generated-app",
                "private": True,
                "version": "1.0.0",
                "type": "module",
                "scripts": {"dev": "vite", "build": "vite build", "preview": "vite preview"},
                "dependencies": {"react": "^19.1.1", "react-dom": "^19.1.1"},
                "devDependencies": {"@vitejs/plugin-react": "^4.7.0", "vite": "^7.1.12"},
            },
            indent=2,
        ),
        "frontend/index.html": textwrap.dedent(
            """\
            <!doctype html>
            <html lang="en">
              <head>
                <meta charset="UTF-8" />
                <meta name="viewport" content="width=device-width, initial-scale=1.0" />
                <title>ZoSwi Generated App</title>
              </head>
              <body>
                <div id="root"></div>
                <script type="module" src="/src/main.jsx"></script>
              </body>
            </html>
            """
        ).strip(),
        "frontend/src/main.jsx": textwrap.dedent(
            """\
            import React from "react";
            import ReactDOM from "react-dom/client";
            import App from "./App";
            import "./styles.css";

            ReactDOM.createRoot(document.getElementById("root")).render(
              <React.StrictMode>
                <App />
              </React.StrictMode>
            );
            """
        ).strip(),
        "frontend/src/App.jsx": textwrap.dedent(
            f"""\
            export default function App() {{
              return (
                <main className="shell">
                  <header className="top">
                    <div>
                      <h1>{title}</h1>
                      <p>Built with ZoSwi</p>
                    </div>
                  </header>
                  <section className="card">
                    <h2>Included Features</h2>
                    <ul>
{feature_lines if feature_lines else "        <li>Core generated UI</li>"}
                    </ul>
                  </section>
                  <footer>Powered by ZoSwi</footer>
                </main>
              );
            }}
            """
        ).strip(),
        "frontend/src/styles.css": textwrap.dedent(
            """\
            :root {
              font-family: "Segoe UI", system-ui, sans-serif;
              color: #0f172a;
              background: #f4f8ff;
            }
            body {
              margin: 0;
              min-height: 100vh;
              background: radial-gradient(900px 400px at 10% -20%, rgba(14, 165, 233, 0.18), transparent 58%), #f4f8ff;
            }
            .shell {
              width: min(980px, 100%);
              margin: 2rem auto;
              border: 1px solid #dbeafe;
              border-radius: 16px;
              background: #ffffff;
              box-shadow: 0 16px 40px rgba(15, 23, 42, 0.12);
              overflow: hidden;
            }
            .top {
              border-bottom: 1px solid #dbeafe;
              padding: 1rem 1.25rem;
            }
            .top h1 {
              margin: 0;
              font-size: 1.4rem;
            }
            .top p {
              margin: 0.35rem 0 0 0;
              color: #475569;
              font-size: 0.9rem;
            }
            .card {
              padding: 1.25rem;
            }
            .card h2 {
              margin-top: 0;
            }
            footer {
              border-top: 1px solid #dbeafe;
              padding: 0.85rem 1.25rem;
              color: #64748b;
              text-align: right;
              font-size: 0.85rem;
            }
            """
        ).strip(),
        "backend/requirements.txt": "fastapi==0.116.1\nuvicorn[standard]==0.35.0\n",
        "backend/main.py": textwrap.dedent(
            f"""\
            from fastapi import FastAPI

            app = FastAPI(title="{title} API")

            @app.get("/health")
            async def health() -> dict[str, str]:
                return {{"status": "ok"}}

            @app.get("/api/spec")
            async def get_spec() -> dict:
                return {json.dumps(spec, indent=2)}
            """
        ).strip(),
        "backend/schema.sql": textwrap.dedent(
            """\
            -- Generated database starter schema
            create table if not exists app_users (
                id integer primary key autoincrement,
                email text not null unique,
                created_at text not null
            );
            """
        ).strip(),
    }
    return files


def _build_project_files(spec: dict[str, Any], preview_html: str) -> dict[str, str]:
    if str(spec.get("stack", "")).strip() == "React + FastAPI":
        return _build_react_fastapi_project_files(spec, preview_html)
    return _build_html_project_files(spec, preview_html)


def _build_zip_base64(files: dict[str, str]) -> str:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files.keys()):
            archive.writestr(path, str(files[path]))
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _build_change_ack(spec: dict[str, Any], mode: str) -> str:
    prompt_text = _normalize_prompt(str(spec.get("last_prompt", ""))).lower()
    if not prompt_text:
        return ""

    updates: list[str] = []
    if any(token in prompt_text for token in ("black", "black theme", "black color", "dark mode", "dark theme")):
        updates.append("Applied black/dark theme styling")
    if any(token in prompt_text for token in ("create another", "add another")):
        updates.append("Added Create Another action")
    if any(token in prompt_text for token in ("edit button", "edit selected", "edit the created", "update selected")):
        updates.append("Added Edit Selected action for updating existing records")
    if any(token in prompt_text for token in ("status filter", "status filters", "filter by status")):
        updates.append("Added status filtering controls")
    if any(token in prompt_text for token in ("crm", "lead tracker", "lead pipeline")) and mode == INTENT_BUILD:
        updates.append("Built CRM lead-tracker flow")

    if not updates:
        return ""
    return "Request matched: " + "; ".join(updates) + ". "


def _next_actions_for_spec(spec: dict[str, Any]) -> str:
    kind = str(spec.get("kind", "web_app")).strip()
    features = set(spec.get("features", []))

    actions: list[str] = ["make it better"]
    if "database" not in features:
        actions.append("connect a database")
    if "dark_mode" not in features:
        actions.append("add dark mode")

    if kind == "application_tracker":
        actions.extend(["add filters", "add CSV export", "add Kanban status board"])
    elif kind == "crm_lead_tracker":
        actions.extend(["add lead scoring", "add deal value field", "add notes timeline", "change theme to black"])
    elif kind == "job_dashboard":
        actions.extend(["add saved jobs", "add interview timeline"])
    elif kind in {"login_app", "resume_tracker"} and "google_login" not in features:
        actions.append("add Google login")
    elif kind == "admin_dashboard":
        actions.extend(["add role permissions", "add audit logs"])
    else:
        actions.extend(["add forms", "add backend API"])

    actions.extend(["show code", "download code", "run locally", "deploy", "commit to Git"])

    unique_actions: list[str] = []
    for action in actions:
        if action not in unique_actions:
            unique_actions.append(action)
    return ", ".join(unique_actions)


def _status_message_for_build(spec: dict[str, Any], mode: str) -> str:
    title = str(spec.get("title", "your app")).strip()
    feature_labels = spec.get("feature_labels", [])[:6]
    feature_text = ", ".join(feature_labels) if feature_labels else "core UI and flows"
    preview_line = (
        "Preview is ready in-page with realistic mock behavior. Backend/database scaffolding is included."
        if spec.get("preview_only")
        else "Preview is ready in-page with a full interactive canvas."
    )
    action_label = "updated" if mode == INTENT_EDIT else "building"
    next_actions = _next_actions_for_spec(spec)
    change_ack = _build_change_ack(spec, mode)
    return (
        f"ZoSwi is {action_label} {title}. "
        f"{change_ack}"
        f"{preview_line} "
        f"Included: {feature_text}, Built with ZoSwi branding. "
        f"You can now ask: {next_actions}."
    )


def _status_message_for_information_request(prompt: str) -> str:
    text = _normalize_prompt(prompt)
    if not text:
        return "I can answer information requests directly. Ask your question in plain English."
    return (
        f"You asked: \"{text}\". "
        "This is an information request, not an app-generation request. "
        "ZoSwi will answer this directly in Explain Mode, or build an app if you explicitly ask "
        "for one (for example: `build an immigration updates dashboard app`)."
    )


def _status_message_for_mode(mode: str, spec: dict[str, Any], prompt: str = "") -> str:
    if mode == INTENT_SHOW_CODE:
        return "Code view is available. You can inspect files or download the generated ZIP."
    if mode == INTENT_EXPORT_CODE:
        return "Export is ready. Use the download action to save the generated ZIP."
    if mode == INTENT_EXPLAIN:
        if _looks_like_information_request(prompt):
            return _status_message_for_information_request(prompt)
        return (
            f"Architecture: {spec.get('stack', 'HTML/CSS/JavaScript')} with preview-first generation. "
            "The app spec defines UI, logic, data/auth requirements, then code and preview are regenerated incrementally."
        )
    if mode == INTENT_LOCAL:
        if str(spec.get("stack", "")).strip() == "React + FastAPI":
            return (
                "Local Mode: run backend (`uvicorn main:app --reload`) and frontend (`npm install && npm run dev`). "
                "Set API base URL to your backend host, then open the frontend dev URL."
            )
        return "Local Mode: open `index.html` directly, or serve with a static server for production-like routing."
    if mode == INTENT_DEPLOY:
        if str(spec.get("stack", "")).strip() == "React + FastAPI":
            return (
                "Deploy Mode: deploy FastAPI backend and frontend separately. "
                "Set CORS and API base URL environment variables before production release."
            )
        return "Deploy Mode: deploy static assets to Vercel, Netlify, Cloudflare Pages, or S3 + CloudFront."
    if mode == INTENT_GIT:
        return (
            "Git Mode: initialize a repository, add generated files, commit with "
            "`feat: add ZoSwi instant builder generated app`, then push to your remote."
        )
    return "ZoSwi Instant App Builder is ready."


def generate_instant_builder_payload(
    prompt: str,
    current_spec: dict[str, Any] | None = None,
    current_files: dict[str, str] | None = None,
    current_preview_html: str | None = None,
) -> dict[str, Any]:
    clean_prompt = _normalize_prompt(prompt)
    spec_input = current_spec if isinstance(current_spec, dict) else {}
    files_input = current_files if isinstance(current_files, dict) else {}
    preview_input = str(current_preview_html or "")
    has_current = bool(spec_input.get("title"))
    intent = _detect_intent(clean_prompt, has_current)

    if intent == INTENT_NOOP:
        return {
            "mode": INTENT_NOOP,
            "status_text": "Describe the app you want to build, and ZoSwi will generate it with an in-page preview.",
            "spec": spec_input,
            "files": files_input,
            "preview_html": preview_input,
            "project_zip_base64": _build_zip_base64(files_input) if files_input else "",
        }

    if intent in {INTENT_BUILD, INTENT_EDIT}:
        spec = _build_spec(clean_prompt, spec_input, intent)
        preview_html = _build_preview_html(spec)
        files = _build_project_files(spec, preview_html)
        return {
            "mode": intent,
            "status_text": _status_message_for_build(spec, intent),
            "spec": spec,
            "files": files,
            "preview_html": preview_html,
            "project_zip_base64": _build_zip_base64(files),
        }

    if intent == INTENT_EXPLAIN and _looks_like_information_request(clean_prompt):
        return {
            "mode": intent,
            "status_text": _status_message_for_information_request(clean_prompt),
            "spec": spec_input,
            "files": files_input,
            "preview_html": preview_input,
            "project_zip_base64": _build_zip_base64(files_input) if files_input else "",
        }

    if not has_current:
        return {
            "mode": intent,
            "status_text": "Build an app first, then I can show code, export, or provide local/deploy/git guidance.",
            "spec": {},
            "files": {},
            "preview_html": "",
            "project_zip_base64": "",
        }

    return {
        "mode": intent,
        "status_text": _status_message_for_mode(intent, spec_input, clean_prompt),
        "spec": spec_input,
        "files": files_input,
        "preview_html": preview_input,
        "project_zip_base64": _build_zip_base64(files_input) if files_input else "",
    }
