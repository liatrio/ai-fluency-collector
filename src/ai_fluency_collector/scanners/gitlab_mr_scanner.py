from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime

from ai_fluency_collector.gitlab_client import GitLabClient
from ai_fluency_collector.scanners.gitlab_review_scanner import (
    MR_AI_COAUTHOR_PATTERNS,
    _period_to_date_range,
)


def _parse_iso(dt_str: str) -> datetime:
    """Parse an ISO 8601 datetime string to a timezone-aware datetime."""
    # GitLab returns strings like "2026-01-15T10:23:00.000Z"
    return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))


def _parse_changes_count(raw: object) -> int | None:
    """Parse the changes_count field from a GitLab MR object.

    Returns None if the value is missing, non-numeric, or the sentinel
    string "too many changes" that GitLab emits for very large diffs.
    """
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


@dataclass
class MRMetrics:
    """Aggregated team-level MR size and coding time metrics."""

    pr_size_median: float | None
    pr_size_mr_count: int
    evidence: dict[str, str] = field(default_factory=dict)


class MRScanner:
    """Scans GitLab MR size signals for AI-attributed MRs over a survey period.

    Produces one team-level metric:
    - pr_size_median: median lines changed across AI-attributed merged MRs.

    MRs with no AI co-author tags are excluded. If no AI-attributed MRs
    exist in the period, pr_size_median is None and no signal is emitted.
    """

    def __init__(self, client: GitLabClient) -> None:
        self.client = client

    def scan(self, usernames: list[str], period: str) -> MRMetrics:
        """Scan MR size signals for a team over a survey period.

        Args:
            usernames: GitLab usernames to scan.
            period: Survey period in YYYY-WNN format.

        Returns:
            MRMetrics with aggregated team-level metrics.
        """
        start_date, end_date = _period_to_date_range(period)

        pr_sizes: list[int] = []

        for username in usernames:
            authored_mrs = self.client.search_merge_requests(
                author_username=username,
                state="merged",
                updated_after=start_date,
                updated_before=end_date,
            )

            for mr in authored_mrs:
                project_id = mr["project_id"]
                mr_iid = mr["iid"]

                # Determine AI attribution via commit co-author tags
                commits = self.client.get_mr_commits(project_id, mr_iid)
                is_ai_attributed = False
                for commit in commits:
                    message = commit.get("message", "") or commit.get("title", "")
                    for pat in MR_AI_COAUTHOR_PATTERNS:
                        if pat["pattern"].search(message):
                            is_ai_attributed = True
                            break
                    if is_ai_attributed:
                        break

                if not is_ai_attributed:
                    continue

                # Collect PR size
                size = _parse_changes_count(mr.get("changes_count"))
                if size is not None:
                    pr_sizes.append(size)

        # Compute median
        pr_size_median: float | None = None
        if pr_sizes:
            pr_size_median = statistics.median(pr_sizes)

        # Build evidence
        evidence: dict[str, str] = {}
        if pr_size_median is not None:
            evidence["pr_size"] = (
                f"PR size (AI-attributed): {round(pr_size_median)} median lines changed "
                f"(N={len(pr_sizes)} MRs)"
            )

        return MRMetrics(
            pr_size_median=pr_size_median,
            pr_size_mr_count=len(pr_sizes),
            evidence=evidence,
        )
