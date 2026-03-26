from __future__ import annotations

import responses

from ai_fluency_collector.github_client import GitHubClient
from ai_fluency_collector.scanners.github_review_scanner import GitHubReviewScanner

BASE = "https://api.github.com"
SEARCH_URL = f"{BASE}/search/issues"


def _pr_item(number: int, owner: str = "org", repo: str = "repo", login: str = "alice") -> dict:
    return {
        "number": number,
        "user": {"login": login},
        "repository_url": f"{BASE}/repos/{owner}/{repo}",
        "pull_request": {"merged_at": "2026-03-16T12:00:00Z"},
    }


def _register_search(items: list[dict]) -> None:
    responses.add(
        responses.GET,
        SEARCH_URL,
        json={"total_count": len(items), "items": items},
        status=200,
    )


def _register_reviews(owner: str, repo: str, number: int, reviews: list[dict]) -> None:
    responses.add(
        responses.GET,
        f"{BASE}/repos/{owner}/{repo}/pulls/{number}/reviews",
        json=reviews,
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE}/repos/{owner}/{repo}/pulls/{number}/reviews",
        json=[],
        status=200,
    )


def _register_comments(owner: str, repo: str, number: int, comments: list[dict]) -> None:
    responses.add(
        responses.GET,
        f"{BASE}/repos/{owner}/{repo}/pulls/{number}/comments",
        json=comments,
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE}/repos/{owner}/{repo}/pulls/{number}/comments",
        json=[],
        status=200,
    )


def _register_files(owner: str, repo: str, number: int, files: list[dict]) -> None:
    responses.add(
        responses.GET,
        f"{BASE}/repos/{owner}/{repo}/pulls/{number}/files",
        json=files,
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE}/repos/{owner}/{repo}/pulls/{number}/files",
        json=[],
        status=200,
    )


def _register_commits(owner: str, repo: str, number: int, commits: list[dict]) -> None:
    responses.add(
        responses.GET,
        f"{BASE}/repos/{owner}/{repo}/pulls/{number}/commits",
        json=commits,
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE}/repos/{owner}/{repo}/pulls/{number}/commits",
        json=[],
        status=200,
    )


# ── LGTM rate ────────────────────────────────────────────────────────────────


@responses.activate
def test_pr_with_no_comments_is_lgtm():
    """PR with zero inline review comments counts as LGTM-without-comment."""
    _register_search([_pr_item(1)])  # authored
    _register_comments("org", "repo", 1, [])
    _register_reviews("org", "repo", 1, [])
    _register_commits("org", "repo", 1, [])
    _register_search([])  # reviewed

    client = GitHubClient("test-token")
    scanner = GitHubReviewScanner(client)
    metrics = scanner.scan(["alice"], "2026-W12")

    assert metrics.total_authored_prs == 1
    assert metrics.lgtm_rate == 1.0


@responses.activate
def test_pr_with_comments_is_not_lgtm():
    """PR with at least one inline comment is not counted as LGTM."""
    _register_search([_pr_item(1)])
    _register_comments(
        "org",
        "repo",
        1,
        [{"user": {"login": "bob"}, "path": "src/foo.py", "created_at": "2026-03-16T10:00:00Z"}],
    )
    _register_reviews("org", "repo", 1, [])
    _register_commits("org", "repo", 1, [])
    _register_search([])

    client = GitHubClient("test-token")
    scanner = GitHubReviewScanner(client)
    metrics = scanner.scan(["alice"], "2026-W12")

    assert metrics.lgtm_rate == 0.0


# ── Self-review rate ──────────────────────────────────────────────────────────


@responses.activate
def test_author_comment_before_approval_counts_as_self_review():
    """Author inline comment before first approval counts as self-review."""
    _register_search([_pr_item(1, login="alice")])
    _register_comments(
        "org",
        "repo",
        1,
        [
            {
                "user": {"login": "alice"},
                "path": "src/foo.py",
                "created_at": "2026-03-16T09:00:00Z",  # before approval
            }
        ],
    )
    _register_reviews(
        "org",
        "repo",
        1,
        [{"state": "APPROVED", "submitted_at": "2026-03-16T12:00:00Z", "user": {"login": "bob"}}],
    )
    _register_commits("org", "repo", 1, [])
    _register_search([])

    client = GitHubClient("test-token")
    scanner = GitHubReviewScanner(client)
    metrics = scanner.scan(["alice"], "2026-W12")

    assert metrics.self_review_rate == 1.0


@responses.activate
def test_author_comment_after_approval_does_not_count():
    """Author comment after first approval does not count as self-review."""
    _register_search([_pr_item(1, login="alice")])
    _register_comments(
        "org",
        "repo",
        1,
        [
            {
                "user": {"login": "alice"},
                "path": "src/foo.py",
                "created_at": "2026-03-16T13:00:00Z",  # after approval
            }
        ],
    )
    _register_reviews(
        "org",
        "repo",
        1,
        [{"state": "APPROVED", "submitted_at": "2026-03-16T12:00:00Z", "user": {"login": "bob"}}],
    )
    _register_commits("org", "repo", 1, [])
    _register_search([])

    client = GitHubClient("test-token")
    scanner = GitHubReviewScanner(client)
    metrics = scanner.scan(["alice"], "2026-W12")

    assert metrics.self_review_rate == 0.0


# ── AI co-author detection ────────────────────────────────────────────────────


@responses.activate
def test_copilot_coauthor_detected():
    """Co-authored-by: GitHub Copilot sets ai_coauthor_rate."""
    _register_search([_pr_item(1)])
    _register_comments("org", "repo", 1, [])
    _register_reviews("org", "repo", 1, [])
    _register_commits(
        "org",
        "repo",
        1,
        [
            {
                "commit": {
                    "message": "feat: thing\n\nCo-authored-by: GitHub Copilot <copilot@github.com>"
                }
            },  # noqa: E501
        ],
    )
    _register_search([])

    client = GitHubClient("test-token")
    scanner = GitHubReviewScanner(client)
    metrics = scanner.scan(["alice"], "2026-W12")

    assert metrics.ai_coauthor_rate == 1.0
    assert metrics.ai_agent_coauthor_rate == 0.0  # not a Claude Code agent tag


@responses.activate
def test_claude_code_agent_tag_sets_both_rates():
    """Claude Code agentic co-author tag sets both im-chat and im-supervised-agent."""
    _register_search([_pr_item(1)])
    _register_comments("org", "repo", 1, [])
    _register_reviews("org", "repo", 1, [])
    _register_commits(
        "org",
        "repo",
        1,
        [{"commit": {"message": "feat: x\n\nCo-authored-by: Claude Code <noreply@anthropic.com>"}}],
    )
    _register_search([])

    client = GitHubClient("test-token")
    scanner = GitHubReviewScanner(client)
    metrics = scanner.scan(["alice"], "2026-W12")

    assert metrics.ai_coauthor_rate == 1.0
    assert metrics.ai_agent_coauthor_rate == 1.0


# ── Review comment depth ──────────────────────────────────────────────────────


@responses.activate
def test_review_depth_all_files_commented():
    """Depth is 1.0 when team reviewer comments on every changed file."""
    _register_search([])  # no authored PRs
    _register_search([_pr_item(10, login="bob")])  # reviewed PRs
    _register_files("org", "repo", 10, [{"filename": "src/a.py"}, {"filename": "src/b.py"}])
    _register_comments(
        "org",
        "repo",
        10,
        [
            {"user": {"login": "alice"}, "path": "src/a.py", "created_at": "2026-03-16T10:00:00Z"},
            {"user": {"login": "alice"}, "path": "src/b.py", "created_at": "2026-03-16T10:05:00Z"},
        ],
    )

    client = GitHubClient("test-token")
    scanner = GitHubReviewScanner(client)
    metrics = scanner.scan(["alice"], "2026-W12")

    assert metrics.review_comment_depth == 1.0


@responses.activate
def test_review_depth_non_team_comments_excluded():
    """Comments from non-team members do not count toward depth."""
    _register_search([])
    _register_search([_pr_item(10, login="bob")])
    _register_files("org", "repo", 10, [{"filename": "src/a.py"}, {"filename": "src/b.py"}])
    _register_comments(
        "org",
        "repo",
        10,
        [
            # outsider — not in the team usernames list
            {
                "user": {"login": "outsider"},
                "path": "src/a.py",
                "created_at": "2026-03-16T10:00:00Z",
            },
        ],
    )

    client = GitHubClient("test-token")
    scanner = GitHubReviewScanner(client)
    metrics = scanner.scan(["alice"], "2026-W12")

    assert metrics.review_comment_depth == 0.0


# ── Empty period ──────────────────────────────────────────────────────────────


@responses.activate
def test_no_prs_returns_none_rates():
    """When no PRs are found all rate fields are None."""
    _register_search([])  # authored
    _register_search([])  # reviewed

    client = GitHubClient("test-token")
    scanner = GitHubReviewScanner(client)
    metrics = scanner.scan(["alice"], "2026-W12")

    assert metrics.total_authored_prs == 0
    assert metrics.lgtm_rate is None
    assert metrics.review_comment_depth is None
    assert metrics.ai_coauthor_rate is None
    assert metrics.self_review_rate is None


# ── Cross-repo PR scenarios ──────────────────────────────────────────────


@responses.activate
def test_authored_prs_across_multiple_repos():
    """Metrics aggregate correctly when authored PRs come from different repos."""
    _register_search(
        [
            _pr_item(1, owner="org", repo="frontend", login="alice"),
            _pr_item(5, owner="org", repo="backend", login="alice"),
        ]
    )
    # frontend PR #1: no comments (LGTM), no AI
    _register_comments("org", "frontend", 1, [])
    _register_reviews("org", "frontend", 1, [])
    _register_commits("org", "frontend", 1, [])
    # backend PR #5: has comments (not LGTM), has AI co-author
    _register_comments(
        "org",
        "backend",
        5,
        [{"user": {"login": "bob"}, "path": "src/main.py", "created_at": "2026-03-16T10:00:00Z"}],
    )
    _register_reviews("org", "backend", 5, [])
    _register_commits(
        "org",
        "backend",
        5,
        [
            {
                "commit": {
                    "message": ("feat: api\n\nCo-authored-by: GitHub Copilot <copilot@github.com>")
                }
            }
        ],
    )
    _register_search([])  # reviewed

    client = GitHubClient("test-token")
    scanner = GitHubReviewScanner(client)
    metrics = scanner.scan(["alice"], "2026-W12")

    assert metrics.total_authored_prs == 2
    assert metrics.lgtm_rate == 0.5  # 1 of 2 LGTM
    assert metrics.ai_coauthor_rate == 0.5  # 1 of 2 AI


@responses.activate
def test_reviewed_prs_across_multiple_repos():
    """Review comment depth aggregates file coverage across repos."""
    _register_search([])  # no authored PRs
    _register_search(
        [
            _pr_item(10, owner="org", repo="frontend", login="bob"),
            _pr_item(20, owner="org", repo="backend", login="carol"),
        ]
    )
    # frontend PR #10: 2 changed files, alice commented on 1
    _register_files("org", "frontend", 10, [{"filename": "src/a.tsx"}, {"filename": "src/b.tsx"}])
    _register_comments(
        "org",
        "frontend",
        10,
        [{"user": {"login": "alice"}, "path": "src/a.tsx", "created_at": "2026-03-16T10:00:00Z"}],
    )
    # backend PR #20: 1 changed file, alice commented on it
    _register_files("org", "backend", 20, [{"filename": "src/main.py"}])
    _register_comments(
        "org",
        "backend",
        20,
        [{"user": {"login": "alice"}, "path": "src/main.py", "created_at": "2026-03-16T11:00:00Z"}],
    )

    client = GitHubClient("test-token")
    scanner = GitHubReviewScanner(client)
    metrics = scanner.scan(["alice"], "2026-W12")

    # 2 of 3 total changed files have comments
    assert metrics.review_comment_depth == 2 / 3


# ── Empty period (scoring integration) ──────────────────────────────────


@responses.activate
def test_empty_period_produces_no_review_signals():
    """When no PRs exist, calculate_github_review_scores returns no signals."""
    from ai_fluency_collector.github_scoring import (
        GITHUB_REVIEW_SKILL_MAPPINGS,
        calculate_github_review_scores,
    )

    _register_search([])  # authored
    _register_search([])  # reviewed

    client = GitHubClient("test-token")
    scanner = GitHubReviewScanner(client)
    metrics = scanner.scan(["alice"], "2026-W12")
    signals = calculate_github_review_scores(metrics, GITHUB_REVIEW_SKILL_MAPPINGS)

    assert signals == []
