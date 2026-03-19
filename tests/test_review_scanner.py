from __future__ import annotations

import responses

from ai_fluency_collector.gitlab_client import GitLabClient
from ai_fluency_collector.scanners.review_scanner import (
    ReviewScanner,
    _period_to_date_range,
)

BASE = "https://gitlab.com/api/v4"
MR_SEARCH = f"{BASE}/merge_requests"


def _mr(iid: int, project_id: int = 1, author: str = "alice") -> dict:
    return {"iid": iid, "project_id": project_id, "author": {"username": author}}


def _register_authored_mrs(username: str, mrs: list[dict]) -> None:
    responses.add(responses.GET, MR_SEARCH, json=mrs, status=200)
    if mrs:
        # Second page stops pagination; not needed when first page is already empty
        responses.add(responses.GET, MR_SEARCH, json=[], status=200)


def _register_reviewed_mrs(username: str, mrs: list[dict]) -> None:
    responses.add(responses.GET, MR_SEARCH, json=mrs, status=200)
    if mrs:
        responses.add(responses.GET, MR_SEARCH, json=[], status=200)


def _register_commits(project_id: int, mr_iid: int, commits: list[dict] | None = None) -> None:
    responses.add(
        responses.GET,
        f"{BASE}/projects/{project_id}/merge_requests/{mr_iid}/commits",
        json=commits or [],
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE}/projects/{project_id}/merge_requests/{mr_iid}/commits",
        json=[],
        status=200,
    )


def _register_notes(project_id: int, mr_iid: int, notes: list[dict]) -> None:
    responses.add(
        responses.GET,
        f"{BASE}/projects/{project_id}/merge_requests/{mr_iid}/notes",
        json=notes,
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE}/projects/{project_id}/merge_requests/{mr_iid}/notes",
        json=[],
        status=200,
    )


def _register_diffs(project_id: int, mr_iid: int, diffs: list[dict]) -> None:
    responses.add(
        responses.GET,
        f"{BASE}/projects/{project_id}/merge_requests/{mr_iid}/diffs",
        json=diffs,
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE}/projects/{project_id}/merge_requests/{mr_iid}/diffs",
        json=[],
        status=200,
    )


def _register_discussions(project_id: int, mr_iid: int, discussions: list[dict]) -> None:
    responses.add(
        responses.GET,
        f"{BASE}/projects/{project_id}/merge_requests/{mr_iid}/discussions",
        json=discussions,
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE}/projects/{project_id}/merge_requests/{mr_iid}/discussions",
        json=[],
        status=200,
    )


# ── Period helper ────────────────────────────────────────────────────────────


def test_period_to_date_range_standard_week():
    start, end = _period_to_date_range("2026-W12")
    assert start == "2026-03-16"
    assert end == "2026-03-22"


def test_period_to_date_range_week_01():
    start, end = _period_to_date_range("2026-W01")
    assert start == "2025-12-29"
    assert end == "2026-01-04"


def test_period_to_date_range_week_53():
    # 2020 has 53 weeks
    start, end = _period_to_date_range("2020-W53")
    assert start == "2020-12-28"
    assert end == "2021-01-03"


# ── LGTM rate ────────────────────────────────────────────────────────────────


@responses.activate
def test_mr_with_no_comments_counts_as_lgtm():
    """MR with zero non-system notes increments LGTM count."""
    _register_authored_mrs("alice", [_mr(1)])
    _register_commits(1, 1)
    _register_notes(1, 1, [])  # no notes
    _register_reviewed_mrs("alice", [])

    client = GitLabClient("test-token")
    scanner = ReviewScanner(client)
    metrics = scanner.scan(["alice"], "2026-W12")

    assert metrics.total_authored_mrs == 1
    assert metrics.lgtm_rate == 1.0


@responses.activate
def test_mr_with_review_comment_does_not_count_as_lgtm():
    """MR with at least one non-system note is not an LGTM-without-comment."""
    _register_authored_mrs("alice", [_mr(1)])
    _register_commits(1, 1)
    _register_notes(
        1,
        1,
        [
            {
                "system": False,
                "body": "Nice work!",
                "author": {"username": "bob"},
                "created_at": "2026-03-16T10:00:00Z",
            }
        ],
    )
    _register_reviewed_mrs("alice", [])

    client = GitLabClient("test-token")
    scanner = ReviewScanner(client)
    metrics = scanner.scan(["alice"], "2026-W12")

    assert metrics.lgtm_rate == 0.0


@responses.activate
def test_system_notes_are_filtered_for_lgtm():
    """System notes (bot activity) are excluded from LGTM analysis."""
    _register_authored_mrs("alice", [_mr(1)])
    _register_commits(1, 1)
    _register_notes(
        1,
        1,
        [
            {
                "system": True,
                "body": "approved this merge request",
                "author": {"username": "bob"},
                "created_at": "2026-03-16T12:00:00Z",
            },
            {
                "system": True,
                "body": "added 1 commit",
                "author": {"username": "alice"},
                "created_at": "2026-03-16T09:00:00Z",
            },
        ],
    )
    _register_reviewed_mrs("alice", [])

    client = GitLabClient("test-token")
    scanner = ReviewScanner(client)
    metrics = scanner.scan(["alice"], "2026-W12")

    # Only system notes → treated as LGTM without comment
    assert metrics.lgtm_rate == 1.0


@responses.activate
def test_lgtm_rate_mixed_mrs():
    """LGTM rate computed correctly across multiple MRs."""
    _register_authored_mrs("alice", [_mr(1), _mr(2), _mr(3)])
    # MR 1: no comments → LGTM
    _register_commits(1, 1)
    _register_notes(1, 1, [])
    # MR 2: has comment → not LGTM
    _register_commits(1, 2)
    _register_notes(
        1,
        2,
        [
            {
                "system": False,
                "body": "LGTM after changes",
                "author": {"username": "bob"},
                "created_at": "2026-03-16T10:00:00Z",
            }
        ],
    )
    # MR 3: only system note → LGTM
    _register_commits(1, 3)
    _register_notes(
        1,
        3,
        [
            {
                "system": True,
                "body": "approved this merge request",
                "author": {"username": "carol"},
                "created_at": "2026-03-16T11:00:00Z",
            }
        ],
    )
    _register_reviewed_mrs("alice", [])

    client = GitLabClient("test-token")
    scanner = ReviewScanner(client)
    metrics = scanner.scan(["alice"], "2026-W12")

    assert metrics.total_authored_mrs == 3
    assert abs(metrics.lgtm_rate - 2 / 3) < 0.001


# ── Review comment depth ─────────────────────────────────────────────────────


@responses.activate
def test_review_depth_all_files_commented():
    """Review depth is 1.0 when team reviewer comments on every changed file."""
    _register_authored_mrs("bob", [])
    _register_reviewed_mrs(
        "bob",
        [{"iid": 10, "project_id": 2, "author": {"username": "alice"}}],
    )
    _register_diffs(2, 10, [{"new_path": "src/foo.py", "old_path": "src/foo.py"}])
    _register_discussions(
        2,
        10,
        [
            {
                "notes": [
                    {
                        "system": False,
                        "author": {"username": "bob"},
                        "position": {"new_path": "src/foo.py", "old_path": "src/foo.py"},
                        "created_at": "2026-03-16T10:00:00Z",
                    }
                ]
            }
        ],
    )

    client = GitLabClient("test-token")
    scanner = ReviewScanner(client)
    metrics = scanner.scan(["bob"], "2026-W12")

    assert metrics.review_comment_depth == 1.0


@responses.activate
def test_review_depth_no_comments():
    """Review depth is 0 when no team members commented on any files."""
    _register_authored_mrs("bob", [])
    _register_reviewed_mrs(
        "bob",
        [{"iid": 10, "project_id": 2, "author": {"username": "alice"}}],
    )
    _register_diffs(
        2,
        10,
        [
            {"new_path": "src/a.py", "old_path": "src/a.py"},
            {"new_path": "src/b.py", "old_path": "src/b.py"},
        ],
    )
    _register_discussions(2, 10, [])

    client = GitLabClient("test-token")
    scanner = ReviewScanner(client)
    metrics = scanner.scan(["bob"], "2026-W12")

    assert metrics.review_comment_depth == 0.0


@responses.activate
def test_review_depth_only_team_comments_count():
    """Discussion notes from non-team members do not count toward depth."""
    _register_authored_mrs("bob", [])
    _register_reviewed_mrs(
        "bob",
        [{"iid": 10, "project_id": 2, "author": {"username": "alice"}}],
    )
    _register_diffs(
        2,
        10,
        [
            {"new_path": "src/a.py", "old_path": "src/a.py"},
            {"new_path": "src/b.py", "old_path": "src/b.py"},
        ],
    )
    _register_discussions(
        2,
        10,
        [
            {
                "notes": [
                    {
                        "system": False,
                        # "outsider" is not in the team usernames list
                        "author": {"username": "outsider"},
                        "position": {"new_path": "src/a.py", "old_path": "src/a.py"},
                        "created_at": "2026-03-16T10:00:00Z",
                    }
                ]
            }
        ],
    )

    client = GitLabClient("test-token")
    scanner = ReviewScanner(client)
    metrics = scanner.scan(["bob"], "2026-W12")

    assert metrics.review_comment_depth == 0.0


@responses.activate
def test_review_depth_no_changed_files_skipped():
    """MRs with no changed files are skipped and do not affect depth."""
    _register_authored_mrs("bob", [])
    _register_reviewed_mrs(
        "bob",
        [{"iid": 10, "project_id": 2, "author": {"username": "alice"}}],
    )
    _register_diffs(2, 10, [])  # empty diff

    client = GitLabClient("test-token")
    scanner = ReviewScanner(client)
    metrics = scanner.scan(["bob"], "2026-W12")

    assert metrics.review_comment_depth is None


# ── Self-review rate ─────────────────────────────────────────────────────────


@responses.activate
def test_self_review_before_approval():
    """Author note before first approval is detected as self-review."""
    _register_authored_mrs("alice", [_mr(1)])
    _register_commits(1, 1)
    _register_notes(
        1,
        1,
        [
            {
                "system": False,
                "body": "I noticed this edge case...",
                "author": {"username": "alice"},
                "created_at": "2026-03-16T09:00:00Z",
            },
            {
                "system": True,
                "body": "approved this merge request",
                "author": {"username": "bob"},
                "created_at": "2026-03-16T12:00:00Z",
            },
        ],
    )
    _register_reviewed_mrs("alice", [])

    client = GitLabClient("test-token")
    scanner = ReviewScanner(client)
    metrics = scanner.scan(["alice"], "2026-W12")

    assert metrics.self_review_rate == 1.0


@responses.activate
def test_self_review_after_approval_does_not_count():
    """Author note after first approval is not counted as self-review."""
    _register_authored_mrs("alice", [_mr(1)])
    _register_commits(1, 1)
    _register_notes(
        1,
        1,
        [
            {
                "system": True,
                "body": "approved this merge request",
                "author": {"username": "bob"},
                "created_at": "2026-03-16T10:00:00Z",
            },
            {
                "system": False,
                "body": "Thanks for the review!",
                "author": {"username": "alice"},
                "created_at": "2026-03-16T11:00:00Z",  # after approval
            },
        ],
    )
    _register_reviewed_mrs("alice", [])

    client = GitLabClient("test-token")
    scanner = ReviewScanner(client)
    metrics = scanner.scan(["alice"], "2026-W12")

    assert metrics.self_review_rate == 0.0


@responses.activate
def test_no_approval_does_not_count_self_review():
    """MR without any approval system note is not eligible for self-review credit."""
    _register_authored_mrs("alice", [_mr(1)])
    _register_commits(1, 1)
    _register_notes(
        1,
        1,
        [
            {
                "system": False,
                "body": "I think we should handle nil here",
                "author": {"username": "alice"},
                "created_at": "2026-03-16T09:00:00Z",
            }
        ],
    )
    _register_reviewed_mrs("alice", [])

    client = GitLabClient("test-token")
    scanner = ReviewScanner(client)
    metrics = scanner.scan(["alice"], "2026-W12")

    assert metrics.self_review_rate == 0.0


# ── Empty period / no MRs ────────────────────────────────────────────────────


@responses.activate
def test_no_mrs_returns_none_rates():
    """When no MRs are found, all rate fields are None."""
    _register_authored_mrs("alice", [])
    _register_reviewed_mrs("alice", [])

    client = GitLabClient("test-token")
    scanner = ReviewScanner(client)
    metrics = scanner.scan(["alice"], "2026-W12")

    assert metrics.lgtm_rate is None
    assert metrics.review_comment_depth is None
    assert metrics.self_review_rate is None
    assert metrics.total_authored_mrs == 0


@responses.activate
def test_multiple_members_aggregated():
    """Metrics are aggregated team-wide across multiple members."""
    # alice: authored 1 MR with no comments (LGTM)
    _register_authored_mrs("alice", [_mr(1, project_id=1, author="alice")])
    _register_commits(1, 1)
    _register_notes(1, 1, [])
    _register_reviewed_mrs("alice", [])
    # bob: authored 1 MR with a comment (not LGTM)
    _register_authored_mrs("bob", [_mr(2, project_id=1, author="bob")])
    _register_commits(1, 2)
    _register_notes(
        1,
        2,
        [
            {
                "system": False,
                "body": "Consider refactoring",
                "author": {"username": "alice"},
                "created_at": "2026-03-16T10:00:00Z",
            }
        ],
    )
    _register_reviewed_mrs("bob", [])

    client = GitLabClient("test-token")
    scanner = ReviewScanner(client)
    metrics = scanner.scan(["alice", "bob"], "2026-W12")

    assert metrics.total_authored_mrs == 2
    assert metrics.lgtm_rate == 0.5  # 1/2 MRs had no comments
