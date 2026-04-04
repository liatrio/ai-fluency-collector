from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from ai_fluency_collector.github_client import GitHubClient

# AI co-author patterns — same as GitLab member scanner
_CLAUDE_PATTERN = re.compile(r"co-authored-by:.*claude", re.IGNORECASE)
_COPILOT_PATTERN = re.compile(r"co-authored-by:.*copilot", re.IGNORECASE)
_CURSOR_PATTERN = re.compile(r"co-authored-by:.*cursor", re.IGNORECASE)
# Agentic Claude patterns (Claude Code CLI) for im-supervised-agent
_CLAUDE_AGENT_PATTERN = re.compile(
    r"co-authored-by:.*claude.*code|generated with.*claude.*code",
    re.IGNORECASE,
)


def _period_to_date_range(period: str) -> tuple[str, str]:
    """Convert YYYY-WNN to (start, end) ISO 8601 date strings (Mon–Sun)."""
    year = int(period[:4])
    week = int(period[6:])
    start = date.fromisocalendar(year, week, 1)
    end = date.fromisocalendar(year, week, 7)
    return start.isoformat(), end.isoformat()


def _repo_and_number_from_pr(item: dict) -> tuple[str, str, int] | None:
    """Extract (owner, repo, number) from a GitHub search result item."""
    repo_url = item.get("repository_url", "")
    # https://api.github.com/repos/{owner}/{repo}
    parts = repo_url.rstrip("/").split("/")
    if len(parts) < 2:
        return None
    owner, repo = parts[-2], parts[-1]
    number = item.get("number")
    if not number:
        return None
    return owner, repo, number


@dataclass
class GitHubReviewMetrics:
    """Aggregated team-level GitHub PR review behavioral metrics."""

    lgtm_rate: float | None
    review_comment_depth: float | None
    ai_coauthor_rate: float | None
    ai_agent_coauthor_rate: float | None
    self_review_rate: float | None
    total_authored_prs: int
    evidence: dict[str, str] = field(default_factory=dict)
    per_repo: dict[str, dict] = field(default_factory=dict)
    """Per-repo PR review metrics for scoring_context."""
    tool_breakdown: dict[str, int] = field(default_factory=dict)
    """Per-tool PR counts: {tool_name: pr_count}"""


class GitHubReviewScanner:
    """Scans GitHub PR review patterns for a team over a survey period.

    Produces five team-level metrics (all rates are None if no PRs found):
    - LGTM-without-comment rate       → tg-code-review
    - Review comment depth             → cq-evaluation
    - AI co-author tag %               → im-chat
    - AI agent co-author tag %         → im-supervised-agent
    - Self-review rate                 → cq-refinement
    """

    def __init__(self, client: GitHubClient) -> None:
        self.client = client

    def scan(self, usernames: list[str], period: str) -> GitHubReviewMetrics:
        """Scan PR review behavior for a team over a survey period.

        Args:
            usernames: GitHub usernames (ephemeral — not stored).
            period: Survey period in YYYY-WNN format.

        Returns:
            GitHubReviewMetrics with aggregated team-level metrics.
        """
        start_date, end_date = _period_to_date_range(period)
        usernames_set = set(usernames)

        # Authored PR aggregates
        total_authored = 0
        lgtm_count = 0
        self_reviewed_count = 0
        ai_coauthor_count = 0
        ai_agent_count = 0
        tool_pr_counts: dict[str, int] = {}  # tool_name → PR count

        # Per-repo tracking
        repo_total: dict[str, int] = {}
        repo_ai: dict[str, int] = {}
        all_repos: set[str] = set()

        # Reviewer aggregates (comment depth)
        total_files_changed = 0
        files_with_comment = 0

        for username in usernames:
            # ── Authored PRs ──────────────────────────────────────────────────
            query = f"is:pr is:merged author:{username} merged:{start_date}..{end_date}"
            authored_prs = self.client.search_pull_requests(query)

            for pr in authored_prs:
                parsed = _repo_and_number_from_pr(pr)
                if not parsed:
                    continue
                owner, repo, number = parsed
                total_authored += 1
                repo_str = f"{owner}/{repo}"
                all_repos.add(repo_str)
                repo_total[repo_str] = repo_total.get(repo_str, 0) + 1
                author_login = pr.get("user", {}).get("login", username)

                # Inline review comments → LGTM detection
                comments = self.client.get_pr_review_comments(owner, repo, number)
                if not comments:
                    lgtm_count += 1

                # Reviews → first approval timestamp
                reviews = self.client.get_pr_reviews(owner, repo, number)
                approved_reviews = [r for r in reviews if r.get("state") == "APPROVED"]
                if approved_reviews:
                    first_approval_at = min(
                        r["submitted_at"] for r in approved_reviews if r.get("submitted_at")
                    )
                    # Self-review: author commented before first approval
                    author_comments_before = [
                        c
                        for c in comments
                        if c.get("user", {}).get("login") == author_login
                        and c.get("created_at", "") < first_approval_at
                    ]
                    if author_comments_before:
                        self_reviewed_count += 1

                # Commits → AI co-author detection
                commits = self.client.get_pr_commits(owner, repo, number)
                has_ai = False
                has_agent = False
                pr_tools: set[str] = set()
                for commit in commits:
                    message = commit.get("commit", {}).get("message", "")
                    if _CLAUDE_AGENT_PATTERN.search(message):
                        has_agent = True
                        has_ai = True
                        pr_tools.add("Claude Code")
                    elif _CLAUDE_PATTERN.search(message):
                        has_ai = True
                        pr_tools.add("Claude")
                    if _COPILOT_PATTERN.search(message):
                        has_ai = True
                        pr_tools.add("GitHub Copilot")
                    if _CURSOR_PATTERN.search(message):
                        has_ai = True
                        pr_tools.add("Cursor")
                if has_ai:
                    ai_coauthor_count += 1
                    repo_ai[repo_str] = repo_ai.get(repo_str, 0) + 1
                    for tool in pr_tools:
                        tool_pr_counts[tool] = tool_pr_counts.get(tool, 0) + 1
                if has_agent:
                    ai_agent_count += 1

            # ── Reviewed PRs (comment depth) ──────────────────────────────────
            reviewed_query = (
                f"is:pr is:merged reviewed-by:{username} merged:{start_date}..{end_date}"
            )
            reviewed_prs = self.client.search_pull_requests(reviewed_query)

            for pr in reviewed_prs:
                parsed = _repo_and_number_from_pr(pr)
                if not parsed:
                    continue
                owner, repo, number = parsed

                pr_files = self.client.get_pr_files(owner, repo, number)
                changed_files = {f["filename"] for f in pr_files if f.get("filename")}
                if not changed_files:
                    continue

                comments = self.client.get_pr_review_comments(owner, repo, number)
                commented_files = {
                    c["path"]
                    for c in comments
                    if c.get("user", {}).get("login") in usernames_set and c.get("path")
                }

                files_with_comment += len(changed_files & commented_files)
                total_files_changed += len(changed_files)

        # ── Compute rates ─────────────────────────────────────────────────────
        lgtm_rate = lgtm_count / total_authored if total_authored > 0 else None
        self_review_rate = self_reviewed_count / total_authored if total_authored > 0 else None
        ai_coauthor_rate = ai_coauthor_count / total_authored if total_authored > 0 else None
        ai_agent_rate = ai_agent_count / total_authored if total_authored > 0 else None
        review_depth = files_with_comment / total_files_changed if total_files_changed > 0 else None

        # ── Team-level evidence (no individual attribution) ───────────────────
        sorted_repos = sorted(all_repos)
        repo_suffix = ""
        if sorted_repos:
            repo_suffix = f" (across {', '.join(sorted_repos)})"

        evidence: dict[str, str] = {}
        if lgtm_rate is not None:
            evidence["lgtm_without_comment"] = (
                f"{lgtm_count}/{total_authored} team-authored PRs "
                f"approved without review comments{repo_suffix}"
            )
        if review_depth is not None:
            pct = round(review_depth * 100)
            evidence["review_comment_depth"] = (
                f"Team reviewers commented on {pct}% of changed files on average{repo_suffix}"
            )
        if ai_coauthor_rate is not None:
            pct = round(ai_coauthor_rate * 100)
            evidence["ai_coauthor_rate"] = (
                f"{pct}% of team-authored PRs contain AI co-author tags{repo_suffix}"
            )
        if ai_agent_rate is not None:
            pct = round(ai_agent_rate * 100)
            evidence["ai_agent_coauthor_rate"] = (
                f"{pct}% of team-authored PRs contain Claude Code "
                f"agentic co-author tags{repo_suffix}"
            )
        if self_review_rate is not None:
            pct = round(self_review_rate * 100)
            evidence["self_review_rate"] = (
                f"{pct}% of team-authored PRs included author self-review "
                f"before approval{repo_suffix}"
            )

        # ── Build per_repo metadata ──────────────────────────────────────────
        per_repo: dict[str, dict] = {}
        for repo_str in all_repos:
            per_repo[repo_str] = {
                "total": repo_total.get(repo_str, 0),
                "ai": repo_ai.get(repo_str, 0),
            }

        return GitHubReviewMetrics(
            lgtm_rate=lgtm_rate,
            review_comment_depth=review_depth,
            ai_coauthor_rate=ai_coauthor_rate,
            ai_agent_coauthor_rate=ai_agent_rate,
            self_review_rate=self_review_rate,
            total_authored_prs=total_authored,
            evidence=evidence,
            per_repo=per_repo,
            tool_breakdown=tool_pr_counts,
        )
