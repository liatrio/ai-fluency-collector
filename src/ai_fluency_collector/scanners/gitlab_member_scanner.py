from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

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
    repo_coauthor_counts: dict[str, dict[str, int]] = field(default_factory=dict)
    """Per-repo AI coauthor commit counts: {repo_name: {pattern_id: count}}"""


class MemberScanner:
    """Discovers member repos and scans commits for AI co-author patterns."""

    def __init__(
        self,
        client: GitLabClient,
        team_projects: list[str],
        since_date: str,
    ) -> None:
        self.client = client
        self.team_project_paths = {p.lower() for p in team_projects}
        self.since_date = since_date

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
            if counts:
                repo_name = repo.get("path_with_namespace", repo.get("name", str(repo["id"])))
                result.repo_coauthor_counts[repo_name] = counts
            for pattern_id, count in counts.items():
                result.ai_coauthor_counts[pattern_id] = (
                    result.ai_coauthor_counts.get(pattern_id, 0) + count
                )

        return result

    def scan_all_members(self, usernames: list[str]) -> list[MemberResult]:
        """Scan all team members concurrently. Raises on user not found."""
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(self.scan_member, usernames))
        return results
