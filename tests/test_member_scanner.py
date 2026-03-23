from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import responses

from ai_fluency_collector.gitlab_client import GitLabClient, GitLabUserNotFoundError
from ai_fluency_collector.scanners.gitlab_member_scanner import MemberScanner

BASE = "https://gitlab.com/api/v4"


def _register_user(username: str, user_id: int) -> None:
    responses.add(
        responses.GET,
        f"{BASE}/users",
        json=[{"id": user_id, "username": username}],
        status=200,
    )


def _register_user_not_found(username: str) -> None:
    responses.add(
        responses.GET,
        f"{BASE}/users",
        json=[],
        status=200,
    )


def _register_user_projects(user_id: int, projects: list[dict]) -> None:
    responses.add(
        responses.GET,
        f"{BASE}/users/{user_id}/projects",
        json=projects,
        status=200,
    )
    # Empty second page to stop pagination
    responses.add(
        responses.GET,
        f"{BASE}/users/{user_id}/projects",
        json=[],
        status=200,
    )


def _register_user_events(user_id: int, events: list[dict]) -> None:
    responses.add(
        responses.GET,
        f"{BASE}/users/{user_id}/events",
        json=events,
        status=200,
    )
    # Empty second page
    responses.add(
        responses.GET,
        f"{BASE}/users/{user_id}/events",
        json=[],
        status=200,
    )


def _register_commits(project_id: int, commits: list[dict]) -> None:
    responses.add(
        responses.GET,
        f"{BASE}/projects/{project_id}/repository/commits",
        json=commits,
        status=200,
    )
    # Empty second page
    responses.add(
        responses.GET,
        f"{BASE}/projects/{project_id}/repository/commits",
        json=[],
        status=200,
    )


@responses.activate
def test_member_lookup_by_username():
    """Member is looked up by GitLab username."""
    _register_user("alice", 101)
    _register_user_projects(101, [])
    _register_user_events(101, [])

    client = GitLabClient("test-token")
    scanner = MemberScanner(client, team_projects=[], since_date="2026-01-01")
    result = scanner.scan_member("alice")
    assert result.username == "alice"
    assert result.repos_discovered == 0
    assert result.ai_coauthor_counts == {}


@responses.activate
def test_member_not_found_raises_error():
    """Unknown username raises GitLabUserNotFoundError."""
    _register_user_not_found("unknown_user")

    client = GitLabClient("test-token")
    scanner = MemberScanner(client, team_projects=[], since_date="2026-01-01")
    with pytest.raises(GitLabUserNotFoundError, match="unknown_user"):
        scanner.scan_member("unknown_user")


@responses.activate
def test_discover_owned_projects():
    """Projects owned by the member are discovered."""
    _register_user("alice", 101)
    _register_user_projects(
        101,
        [
            {"id": 1, "path_with_namespace": "alice/personal-project"},
        ],
    )
    _register_user_events(101, [])
    _register_commits(1, [])

    client = GitLabClient("test-token")
    scanner = MemberScanner(client, team_projects=[], since_date="2026-01-01")
    result = scanner.scan_member("alice")
    assert result.repos_discovered == 1


@responses.activate
def test_discover_pushed_projects():
    """Projects the member pushed to are discovered via events."""
    _register_user("alice", 101)
    _register_user_projects(101, [])
    _register_user_events(
        101,
        [
            {
                "action_name": "pushed to",
                "project": {"id": 2, "path_with_namespace": "other/repo"},
            }
        ],
    )
    _register_commits(2, [])

    client = GitLabClient("test-token")
    scanner = MemberScanner(client, team_projects=[], since_date="2026-01-01")
    result = scanner.scan_member("alice")
    assert result.repos_discovered == 1


@responses.activate
def test_team_projects_excluded():
    """Projects already in team.projects are excluded from discovery."""
    _register_user("alice", 101)
    _register_user_projects(
        101,
        [
            {"id": 1, "path_with_namespace": "team/listed-project"},
            {"id": 2, "path_with_namespace": "alice/personal"},
        ],
    )
    _register_user_events(101, [])
    _register_commits(2, [])

    client = GitLabClient("test-token")
    scanner = MemberScanner(client, team_projects=["team/listed-project"], since_date="2026-01-01")
    result = scanner.scan_member("alice")
    assert result.repos_discovered == 1  # Only personal, not team project


@responses.activate
def test_deduplication_owned_and_pushed():
    """Same project found via owned and events is counted once."""
    _register_user("alice", 101)
    _register_user_projects(
        101,
        [{"id": 1, "path_with_namespace": "alice/project"}],
    )
    _register_user_events(
        101,
        [
            {
                "action_name": "pushed to",
                "project": {"id": 1, "path_with_namespace": "alice/project"},
            }
        ],
    )
    _register_commits(1, [])

    client = GitLabClient("test-token")
    scanner = MemberScanner(client, team_projects=[], since_date="2026-01-01")
    result = scanner.scan_member("alice")
    assert result.repos_discovered == 1


@responses.activate
def test_detect_claude_coauthor():
    """Co-Authored-By: Claude detected in commits."""
    _register_user("alice", 101)
    _register_user_projects(101, [{"id": 1, "path_with_namespace": "alice/project"}])
    _register_user_events(101, [])
    _register_commits(
        1,
        [
            {"message": "feat: add feature\n\nCo-Authored-By: Claude <noreply@anthropic.com>"},
            {"message": "fix: typo"},
        ],
    )

    client = GitLabClient("test-token")
    scanner = MemberScanner(client, team_projects=[], since_date="2026-01-01")
    result = scanner.scan_member("alice")
    assert result.ai_coauthor_counts.get("coauthor-claude") == 1


@responses.activate
def test_detect_copilot_coauthor():
    """Co-authored-by: GitHub Copilot detected (case-insensitive)."""
    _register_user("bob", 102)
    _register_user_projects(102, [{"id": 2, "path_with_namespace": "bob/repo"}])
    _register_user_events(102, [])
    _register_commits(
        2,
        [
            {"message": "feat: stuff\n\nco-authored-by: GitHub Copilot"},
        ],
    )

    client = GitLabClient("test-token")
    scanner = MemberScanner(client, team_projects=[], since_date="2026-01-01")
    result = scanner.scan_member("bob")
    assert result.ai_coauthor_counts.get("coauthor-copilot") == 1


@responses.activate
def test_detect_cursor_coauthor():
    """Co-Authored-By: Cursor detected."""
    _register_user("carol", 103)
    _register_user_projects(103, [{"id": 3, "path_with_namespace": "carol/repo"}])
    _register_user_events(103, [])
    _register_commits(
        3,
        [
            {"message": "refactor: cleanup\n\nCo-authored-by: Cursor Tab <cursor@cursor.com>"},
        ],
    )

    client = GitLabClient("test-token")
    scanner = MemberScanner(client, team_projects=[], since_date="2026-01-01")
    result = scanner.scan_member("carol")
    assert result.ai_coauthor_counts.get("coauthor-cursor") == 1


@responses.activate
def test_no_activity_returns_empty():
    """Member with no owned projects and no events returns empty results."""
    _register_user("quiet", 104)
    _register_user_projects(104, [])
    _register_user_events(104, [])

    client = GitLabClient("test-token")
    scanner = MemberScanner(client, team_projects=[], since_date="2026-01-01")
    result = scanner.scan_member("quiet")
    assert result.repos_discovered == 0
    assert result.ai_coauthor_counts == {}


@responses.activate
def test_scan_all_members():
    """scan_all_members processes multiple members."""
    # Alice
    _register_user("alice", 101)
    _register_user_projects(101, [])
    _register_user_events(101, [])
    # Bob
    _register_user("bob", 102)
    _register_user_projects(102, [])
    _register_user_events(102, [])

    client = GitLabClient("test-token")
    scanner = MemberScanner(client, team_projects=[], since_date="2026-01-01")
    results = scanner.scan_all_members(["alice", "bob"])
    assert len(results) == 2
    assert results[0].username == "alice"
    assert results[1].username == "bob"


def test_since_date_passed_directly_to_get_project_commits():
    """MemberScanner passes since_date directly to get_project_commits(), not today-relative."""
    mock_client = MagicMock()
    mock_client.get_user.return_value = {"id": 101}
    mock_client.get_user_projects.return_value = [{"id": 1, "path_with_namespace": "alice/proj"}]
    mock_client.get_user_events.return_value = []
    mock_client.get_project_commits.return_value = []

    since = "2026-01-06"
    scanner = MemberScanner(mock_client, team_projects=[], since_date=since)
    scanner.scan_member("alice")

    mock_client.get_project_commits.assert_called_once_with(1, author="alice", since=since)
