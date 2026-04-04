"""Shared utilities for scanner modules."""

from __future__ import annotations

from datetime import date


def period_to_date_range(period: str) -> tuple[str, str]:
    """Convert YYYY-WNN to (start_date, end_date) as ISO 8601 strings.

    Start is Monday, end is Sunday of the given ISO week.
    """
    year = int(period[:4])
    week = int(period[6:])
    start = date.fromisocalendar(year, week, 1)
    end = date.fromisocalendar(year, week, 7)
    return start.isoformat(), end.isoformat()


def project_name_from_mr(mr: dict) -> str:
    """Extract project path from MR data (no URLs in output).

    Tries references.full first (e.g. "group/project!123"), then
    falls back to extracting path components from web_url.
    """
    refs = mr.get("references", {})
    full_ref = refs.get("full", "")
    if full_ref and "!" in full_ref:
        return full_ref.rsplit("!", 1)[0]
    # Fallback: extract full path from web_url (never expose the URL itself)
    web_url = mr.get("web_url", "")
    if web_url:
        # https://gitlab.com/group/subgroup/project/-/merge_requests/123
        from urllib.parse import urlparse

        path = urlparse(web_url).path.lstrip("/")
        if "/-/" in path:
            return path.split("/-/", 1)[0]
    return str(mr.get("project_id", "unknown"))


def short_name(project_path: str) -> str:
    """Extract the short project name from a full path.

    Example: 'group/subgroup/repo' → 'repo'
    """
    return project_path.rsplit("/", 1)[-1] if "/" in project_path else project_path
