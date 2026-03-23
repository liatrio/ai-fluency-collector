from __future__ import annotations

import responses
from requests.exceptions import Timeout

from ai_fluency_collector.gitlab_client import (
    GitLabClient,
    GitLabRateLimitError,
    GitLabTimeoutError,
)

BASE = "https://gitlab.com/api/v4"


# ── Timeout tests ─────────────────────────────────────────────────────────────


@responses.activate
def test_timeout_raises_gitlab_timeout_error():
    """A Timeout on any request raises GitLabTimeoutError with context."""
    responses.add(
        responses.GET,
        f"{BASE}/projects/my-group%2Fmy-project/repository/branches",
        body=Timeout(),
    )
    client = GitLabClient("test-token", timeout=30)
    try:
        client.get_branches("my-group/my-project")
        assert False, "Expected GitLabTimeoutError"
    except GitLabTimeoutError as e:
        assert "30s" in str(e)
        assert "listing branches" in str(e)


@responses.activate
def test_timeout_error_message_includes_advice():
    """Timeout error tells the user to check network or GitLab status."""
    responses.add(
        responses.GET,
        f"{BASE}/projects/my-group%2Fmy-project/jobs",
        body=Timeout(),
    )
    client = GitLabClient("test-token", timeout=30)
    try:
        client.get_jobs("my-group/my-project")
        assert False, "Expected GitLabTimeoutError"
    except GitLabTimeoutError as e:
        assert "network" in str(e).lower() or "gitlab instance" in str(e).lower()


# ── Rate limit tests ──────────────────────────────────────────────────────────


@responses.activate
def test_rate_limit_with_reset_header():
    """429 with RateLimit-Reset header raises GitLabRateLimitError with reset time."""
    responses.add(
        responses.GET,
        f"{BASE}/projects/my-group%2Fmy-project/repository/branches",
        status=429,
        headers={"RateLimit-Reset": "1800000000"},  # arbitrary future timestamp
    )
    client = GitLabClient("test-token")
    try:
        client.get_branches("my-group/my-project")
        assert False, "Expected GitLabRateLimitError"
    except GitLabRateLimitError as e:
        assert "rate limit" in str(e).lower()
        assert "UTC" in str(e)


@responses.activate
def test_rate_limit_without_reset_header():
    """429 with no reset header raises GitLabRateLimitError with generic message."""
    responses.add(
        responses.GET,
        f"{BASE}/projects/my-group%2Fmy-project/repository/branches",
        status=429,
    )
    client = GitLabClient("test-token")
    try:
        client.get_branches("my-group/my-project")
        assert False, "Expected GitLabRateLimitError"
    except GitLabRateLimitError as e:
        assert "rate limit" in str(e).lower()


@responses.activate
def test_rate_limit_on_paginated_endpoint():
    """429 mid-pagination also raises GitLabRateLimitError."""
    responses.add(
        responses.GET,
        f"{BASE}/merge_requests",
        status=429,
        headers={"RateLimit-Reset": "1800000000"},
    )
    client = GitLabClient("test-token")
    try:
        client.search_merge_requests(author_username="alice")
        assert False, "Expected GitLabRateLimitError"
    except GitLabRateLimitError:
        pass


# ── Default timeout is set ────────────────────────────────────────────────────


def test_default_timeout_is_configured():
    """GitLabClient uses DEFAULT_TIMEOUT when no timeout specified."""
    from ai_fluency_collector.gitlab_client import DEFAULT_TIMEOUT

    client = GitLabClient("test-token")
    assert client.timeout == DEFAULT_TIMEOUT
    assert DEFAULT_TIMEOUT > 0


def test_custom_timeout_respected():
    """GitLabClient stores the provided timeout value."""
    client = GitLabClient("test-token", timeout=60)
    assert client.timeout == 60
