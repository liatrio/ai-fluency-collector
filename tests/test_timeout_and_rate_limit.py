from __future__ import annotations

import threading

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


# ── get_jobs() pagination cap tests ──────────────────────────────────────────


@responses.activate
def test_get_jobs_stops_after_max_pages():
    """get_jobs() stops fetching after max_pages pages and returns partial results."""
    jobs_url = f"{BASE}/projects/my-group%2Fmy-project/jobs"
    # Register 3 pages of 1 job each, plus a 4th that should never be fetched
    for i in range(1, 5):
        responses.add(
            responses.GET,
            jobs_url,
            json=[{"id": i, "name": f"job-{i}"}],
            status=200,
        )
    # Empty page to signal natural end (should not be reached when max_pages=3)
    responses.add(responses.GET, jobs_url, json=[], status=200)

    client = GitLabClient("test-token")
    results = client.get_jobs("my-group/my-project", max_pages=3)

    assert len(results) == 3
    assert results[0]["id"] == 1
    assert results[2]["id"] == 3


@responses.activate
def test_get_jobs_default_max_pages_is_five():
    """get_jobs() default max_pages stops after 5 pages even with more available."""
    jobs_url = f"{BASE}/projects/my-group%2Fmy-project/jobs"
    # Register 7 pages of 1 job each
    for i in range(1, 8):
        responses.add(
            responses.GET,
            jobs_url,
            json=[{"id": i, "name": f"job-{i}"}],
            status=200,
        )

    client = GitLabClient("test-token")
    results = client.get_jobs("my-group/my-project")

    assert len(results) == 5


# ── Thread-safety tests ───────────────────────────────────────────────────────


def test_each_thread_gets_its_own_session():
    """GitLabClient.session returns a distinct object in each thread."""
    client = GitLabClient("test-token")
    sessions: list = []
    lock = threading.Lock()

    def capture_session() -> None:
        # Keep a live reference so the object is not garbage-collected
        # before all threads have reported (which would allow id() reuse).
        sess = client.session
        with lock:
            sessions.append(sess)

    threads = [threading.Thread(target=capture_session) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # All 4 thread-local sessions must be distinct objects
    assert len(set(id(s) for s in sessions)) == 4


def test_main_thread_session_is_stable():
    """Accessing session twice from the same thread returns the same object."""
    client = GitLabClient("test-token")
    assert client.session is client.session


def test_thread_session_carries_auth_token():
    """Each per-thread session has the PRIVATE-TOKEN header set correctly."""
    client = GitLabClient("my-secret-token")
    results: list[str] = []

    def capture_token() -> None:
        results.append(client.session.headers.get("PRIVATE-TOKEN", ""))

    t = threading.Thread(target=capture_token)
    t.start()
    t.join()

    assert results[0] == "my-secret-token"
