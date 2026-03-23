from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from ai_fluency_collector.gitlab_client import GitLabClient

# AI co-author patterns detected in MR commit messages.
# agentic=True → also counted toward im-supervised-agent (agentic tools only).
MR_AI_COAUTHOR_PATTERNS: list[dict] = [
    {
        "id": "claude",
        "name": "Claude",
        "pattern": re.compile(r"co-authored-by:.*claude", re.IGNORECASE),
        "agentic": True,
    },
    {
        "id": "copilot",
        "name": "GitHub Copilot",
        "pattern": re.compile(r"co-authored-by:.*copilot", re.IGNORECASE),
        "agentic": False,
    },
    {
        "id": "cursor",
        "name": "Cursor",
        "pattern": re.compile(r"co-authored-by:.*cursor", re.IGNORECASE),
        "agentic": True,
    },
    {
        "id": "duo",
        "name": "GitLab Duo",
        "pattern": re.compile(r"co-authored-by:.*duo", re.IGNORECASE),
        "agentic": False,
    },
]


def _period_to_date_range(period: str) -> tuple[str, str]:
    """Convert YYYY-WNN to (start_date, end_date) as ISO 8601 strings.

    Start is Monday, end is Sunday of the given ISO week.
    """
    year = int(period[:4])
    week = int(period[6:])
    start = date.fromisocalendar(year, week, 1)
    end = date.fromisocalendar(year, week, 7)
    return start.isoformat(), end.isoformat()


@dataclass
class ReviewMetrics:
    """Aggregated team-level MR review behavioral metrics."""

    lgtm_rate: float | None
    review_comment_depth: float | None
    self_review_rate: float | None
    total_authored_mrs: int
    mr_ai_coauthor_rate: float | None = None
    mr_agentic_coauthor_rate: float | None = None
    evidence: dict[str, str] = field(default_factory=dict)


class ReviewScanner:
    """Scans GitLab MR review patterns for a team over a survey period.

    Produces three team-level metrics:
    - LGTM-without-comment rate: % of authored MRs approved with zero non-system notes
    - Review comment depth: avg ratio of files with team discussion threads to total changed files
    - Self-review rate: % of authored MRs where author commented before first approval
    """

    def __init__(self, client: GitLabClient) -> None:
        self.client = client

    def scan(self, usernames: list[str], period: str) -> ReviewMetrics:
        """Scan MR review behavioral patterns for a team over a survey period.

        Args:
            usernames: GitLab usernames to scan.
            period: Survey period in YYYY-WNN format.

        Returns:
            ReviewMetrics with aggregated team-level metrics. Rate fields are None
            if no MRs were found for that metric.
        """
        start_date, end_date = _period_to_date_range(period)
        usernames_set = set(usernames)

        # Authored MR aggregates (LGTM rate + self-review rate + co-author tags)
        total_authored = 0
        lgtm_count = 0
        self_reviewed_count = 0
        mrs_with_any_ai_tag = 0
        mrs_with_agentic_tag = 0
        # Counts MRs (not commits) that had at least one commit with each tool's tag
        tool_mr_counts: dict[str, int] = {p["id"]: 0 for p in MR_AI_COAUTHOR_PATTERNS}

        # Reviewer aggregates (comment depth)
        total_files_changed = 0
        files_with_discussion = 0

        for username in usernames:
            # ── Authored MRs ────────────────────────────────────────────────
            authored_mrs = self.client.search_merge_requests(
                author_username=username,
                state="merged",
                updated_after=start_date,
                updated_before=end_date,
            )

            for mr in authored_mrs:
                total_authored += 1
                project_id = mr["project_id"]
                mr_iid = mr["iid"]

                # AI co-author tag detection in MR commits
                commits = self.client.get_mr_commits(project_id, mr_iid)
                mr_has_any_ai = False
                mr_has_agentic = False
                mr_tools_seen: set[str] = set()
                for commit in commits:
                    message = commit.get("message", "") or commit.get("title", "")
                    for pat in MR_AI_COAUTHOR_PATTERNS:
                        if pat["pattern"].search(message):
                            mr_tools_seen.add(pat["id"])
                            mr_has_any_ai = True
                            if pat["agentic"]:
                                mr_has_agentic = True
                for tool_id in mr_tools_seen:
                    tool_mr_counts[tool_id] += 1
                if mr_has_any_ai:
                    mrs_with_any_ai_tag += 1
                if mr_has_agentic:
                    mrs_with_agentic_tag += 1

                notes = self.client.get_mr_notes(project_id, mr_iid)
                non_system_notes = [n for n in notes if not n.get("system", False)]

                # LGTM rate: zero non-system notes on this MR
                if not non_system_notes:
                    lgtm_count += 1

                # Self-review: author left a note before the first approval.
                # Approvals show up as system notes with body "approved this merge request".
                approval_system_notes = [
                    n
                    for n in notes
                    if n.get("system", False) and "approved this merge request" in n.get("body", "")
                ]
                if approval_system_notes:
                    first_approval_at = min(n["created_at"] for n in approval_system_notes)
                    author_early_notes = [
                        n
                        for n in non_system_notes
                        if n.get("author", {}).get("username") == username
                        and n.get("created_at", "") < first_approval_at
                    ]
                    if author_early_notes:
                        self_reviewed_count += 1

            # ── Reviewed MRs ─────────────────────────────────────────────────
            reviewed_mrs = self.client.search_merge_requests(
                reviewer_username=username,
                state="merged",
                updated_after=start_date,
                updated_before=end_date,
            )

            for mr in reviewed_mrs:
                project_id = mr["project_id"]
                mr_iid = mr["iid"]

                diffs = self.client.get_mr_diffs(project_id, mr_iid)
                changed_files: set[str] = set()
                for d in diffs:
                    if d.get("new_path"):
                        changed_files.add(d["new_path"])
                    if d.get("old_path") and d.get("old_path") != d.get("new_path"):
                        changed_files.add(d["old_path"])

                if not changed_files:
                    continue

                discussions = self.client.get_mr_discussions(project_id, mr_iid)
                discussed_files: set[str] = set()
                for disc in discussions:
                    for note in disc.get("notes", []):
                        if (
                            not note.get("system", False)
                            and note.get("author", {}).get("username") in usernames_set
                        ):
                            pos = note.get("position") or {}
                            for path_key in ("new_path", "old_path"):
                                if pos.get(path_key):
                                    discussed_files.add(pos[path_key])

                files_with_discussion += len(changed_files & discussed_files)
                total_files_changed += len(changed_files)

        # ── Compute rates ────────────────────────────────────────────────────
        lgtm_rate = lgtm_count / total_authored if total_authored > 0 else None
        self_review_rate = self_reviewed_count / total_authored if total_authored > 0 else None
        review_depth = (
            files_with_discussion / total_files_changed if total_files_changed > 0 else None
        )
        mr_ai_coauthor_rate = mrs_with_any_ai_tag / total_authored if total_authored > 0 else None
        mr_agentic_coauthor_rate = (
            mrs_with_agentic_tag / total_authored if total_authored > 0 else None
        )

        # ── Build team-level evidence strings (no individual attribution) ────
        evidence: dict[str, str] = {}
        if lgtm_rate is not None:
            evidence["lgtm_without_comment"] = (
                f"{lgtm_count}/{total_authored} team-authored MRs approved without review comments"
            )
        if review_depth is not None:
            pct = round(review_depth * 100)
            evidence["review_comment_depth"] = (
                f"Team reviewers commented on {pct}% of changed files on average"
            )
        if self_review_rate is not None:
            pct = round(self_review_rate * 100)
            evidence["self_review_rate"] = (
                f"{pct}% of team-authored MRs included author self-review before approval"
            )
        if mr_ai_coauthor_rate is not None:
            overall_pct = round(mr_ai_coauthor_rate * 100)
            tool_parts = [
                f"{p['name']}: {round(tool_mr_counts[p['id']] / total_authored * 100)}%"
                for p in MR_AI_COAUTHOR_PATTERNS
                if tool_mr_counts[p["id"]] > 0
            ]
            breakdown = f" ({', '.join(tool_parts)})" if tool_parts else ""
            evidence["mr_ai_coauthor_rate"] = (
                f"{overall_pct}% of team-authored merged MRs have AI co-author tags{breakdown}"
            )
            evidence["mr_agentic_coauthor_rate"] = evidence["mr_ai_coauthor_rate"]

        return ReviewMetrics(
            lgtm_rate=lgtm_rate,
            review_comment_depth=review_depth,
            self_review_rate=self_review_rate,
            total_authored_mrs=total_authored,
            mr_ai_coauthor_rate=mr_ai_coauthor_rate,
            mr_agentic_coauthor_rate=mr_agentic_coauthor_rate,
            evidence=evidence,
        )
