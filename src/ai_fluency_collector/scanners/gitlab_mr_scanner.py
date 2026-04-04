from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime

from ai_fluency_collector.gitlab_client import GitLabClient
from ai_fluency_collector.scanners.gitlab_review_scanner import (
    MR_AI_COAUTHOR_PATTERNS,
    _period_to_date_range,
    _project_name_from_mr,
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


def _coding_time_hours(mr: dict, commits: list[dict]) -> float | None:
    """Compute coding time in hours for a single MR.

    Coding time = mr.created_at - min(commit.created_at for commits in MR).

    Returns None if commits is empty or timestamps cannot be parsed.
    """
    if not commits:
        return None
    mr_created_str = mr.get("created_at")
    if not mr_created_str:
        return None
    try:
        mr_created = _parse_iso(mr_created_str)
        commit_times = []
        for commit in commits:
            ts = commit.get("created_at")
            if ts:
                commit_times.append(_parse_iso(ts))
        if not commit_times:
            return None
        first_commit = min(commit_times)
        delta = mr_created - first_commit
        hours = delta.total_seconds() / 3600
        # Guard against clock skew / negative values
        return max(0.0, hours)
    except (ValueError, TypeError):
        return None


@dataclass
class MRMetrics:
    """Aggregated team-level MR size and coding time metrics."""

    pr_size_median: float | None
    pr_size_mr_count: int
    coding_time_median: float | None
    coding_time_mr_count: int
    evidence: dict[str, str] = field(default_factory=dict)
    per_repo: dict[str, dict] = field(default_factory=dict)
    """Per-repo MR size/coding time data for scoring_context."""


class MRScanner:
    """Scans GitLab MR size and coding time signals for AI-attributed MRs.

    Produces two team-level metrics:
    - pr_size_median: median lines changed across AI-attributed merged MRs.
    - coding_time_median: median hours from first commit to MR open for
      AI-attributed merged MRs.

    MRs with no AI co-author tags are excluded from both metrics. Commits
    fetched for co-author detection are reused for coding time — no extra
    API calls needed.
    """

    def __init__(self, client: GitLabClient) -> None:
        self.client = client

    def scan(self, usernames: list[str], period: str) -> MRMetrics:
        """Scan MR size and coding time signals for a team over a survey period.

        Args:
            usernames: GitLab usernames to scan.
            period: Survey period in YYYY-WNN format.

        Returns:
            MRMetrics with aggregated team-level metrics.
        """
        start_date, end_date = _period_to_date_range(period)

        pr_sizes: list[int] = []
        coding_times: list[float] = []
        # Per-repo tracking
        repo_pr_sizes: dict[str, list[int]] = {}
        repo_coding_times: dict[str, list[float]] = {}
        all_repos: set[str] = set()

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

                # Fetch commits once — reused for both attribution and coding time
                commits = self.client.get_mr_commits(project_id, mr_iid)

                # Determine AI attribution via commit co-author tags
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

                repo_name = _project_name_from_mr(mr)
                all_repos.add(repo_name)

                # Collect PR size
                size = _parse_changes_count(mr.get("changes_count"))
                if size is not None:
                    pr_sizes.append(size)
                    repo_pr_sizes.setdefault(repo_name, []).append(size)

                # Collect coding time (reuses commits already fetched above)
                ct = _coding_time_hours(mr, commits)
                if ct is not None:
                    coding_times.append(ct)
                    repo_coding_times.setdefault(repo_name, []).append(ct)

        # Compute medians
        pr_size_median: float | None = statistics.median(pr_sizes) if pr_sizes else None
        coding_time_median: float | None = statistics.median(coding_times) if coding_times else None

        # Short repo names for evidence (no URLs)
        short_repos = sorted(all_repos)
        repo_suffix = ""
        if short_repos:
            short_names = [r.rsplit("/", 1)[-1] if "/" in r else r for r in short_repos]
            repo_suffix = f" across {', '.join(short_names)}"

        # Build evidence
        evidence: dict[str, str] = {}
        if pr_size_median is not None:
            evidence["pr_size_median"] = (
                f"PR size (AI-attributed): {round(pr_size_median)} median lines changed "
                f"(N={len(pr_sizes)} MRs{repo_suffix})"
            )
        if coding_time_median is not None:
            evidence["coding_time_median"] = (
                f"Coding time (AI-attributed): {round(coding_time_median, 1)}h median "
                f"first commit to MR open (N={len(coding_times)} MRs{repo_suffix})"
            )

        # Build per_repo metadata
        per_repo: dict[str, dict] = {}
        for repo_name in all_repos:
            sizes = repo_pr_sizes.get(repo_name, [])
            times = repo_coding_times.get(repo_name, [])
            entry: dict = {"count": len(sizes)}
            if sizes:
                entry["median_lines"] = round(statistics.median(sizes))
            if times:
                entry["median_hours"] = round(statistics.median(times), 1)
            per_repo[repo_name] = entry

        return MRMetrics(
            pr_size_median=pr_size_median,
            pr_size_mr_count=len(pr_sizes),
            coding_time_median=coding_time_median,
            coding_time_mr_count=len(coding_times),
            evidence=evidence,
            per_repo=per_repo,
        )
