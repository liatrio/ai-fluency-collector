from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from ai_fluency_collector.gitlab_client import GitLabClient

# AI co-author patterns to detect in commit messages (case-insensitive)
AI_COAUTHOR_PATTERNS: list[dict] = [
    {
        "id": "coauthor-claude",
        "name": "Claude",
        "pattern": re.compile(r"co-authored-by:.*claude", re.IGNORECASE),
    },
    {
        "id": "coauthor-copilot",
        "name": "GitHub Copilot",
        "pattern": re.compile(r"co-authored-by:.*copilot", re.IGNORECASE),
    },
    {
        "id": "coauthor-cursor",
        "name": "Cursor",
        "pattern": re.compile(r"co-authored-by:.*cursor", re.IGNORECASE),
    },
]


@dataclass
class MemberResult:
    username: str
    repos_discovered: int = 0
    ai_coauthor_counts: dict[str, int] = field(default_factory=dict)


class MemberScanner:
    """Discovers member repos and scans commits for AI co-author patterns."""

    def __init__(
        self,
        client: GitLabClient,
        team_projects: list[str],
        lookback_days: int = 90,
    ) -> None:
        self.client = client
        self.team_project_paths = {p.lower() for p in team_projects}
        self.since_date = (date.today() - timedelta(days=lookback_days)).isoformat()

    def _discover_member_repos(self, user_id: int) -> list[dict]:
        """Discover repos a member owns or has pushed to, excluding team projects."""
        seen_ids: set[int] = set()
        repos: list[dict] = []

        # Owned projects
        for project in self.client.get_user_projects(user_id):
            pid = project["id"]
            path = project.get("path_with_namespace", "").lower()
            if pid not in seen_ids and path not in self.team_project_paths:
                seen_ids.add(pid)
                repos.append(project)

        # Projects from push events
        for event in self.client.get_user_events(user_id, action="pushed"):
            project = event.get("project")
            if not project:
                continue
            pid = project.get("id")
            if not pid or pid in seen_ids:
                continue
            path = project.get("path_with_namespace", "").lower()
            if path not in self.team_project_paths:
                seen_ids.add(pid)
                repos.append(project)

        return repos

    def _scan_commits_for_coauthors(self, project_id: int, username: str) -> dict[str, int]:
        """Search a project's commits by author for AI co-author patterns."""
        counts: dict[str, int] = {}
        commits = self.client.get_project_commits(
            project_id, author=username, since=self.since_date
        )
        for commit in commits:
            message = commit.get("message", "") or commit.get("title", "")
            for pattern_def in AI_COAUTHOR_PATTERNS:
                if pattern_def["pattern"].search(message):
                    pid = pattern_def["id"]
                    counts[pid] = counts.get(pid, 0) + 1
        return counts

    def scan_member(self, username: str) -> MemberResult:
        """Scan a single member's activity for AI co-author signals.

        Raises GitLabUserNotFoundError if the username is not found.
        """
        user = self.client.get_user(username)
        user_id = user["id"]

        repos = self._discover_member_repos(user_id)
        result = MemberResult(username=username, repos_discovered=len(repos))

        for repo in repos:
            counts = self._scan_commits_for_coauthors(repo["id"], username)
            for pattern_id, count in counts.items():
                result.ai_coauthor_counts[pattern_id] = (
                    result.ai_coauthor_counts.get(pattern_id, 0) + count
                )

        return result

    def scan_all_members(self, usernames: list[str]) -> list[MemberResult]:
        """Scan all team members. Raises on user not found."""
        results: list[MemberResult] = []
        for username in usernames:
            results.append(self.scan_member(username))
        return results
