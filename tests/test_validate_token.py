from __future__ import annotations

import pytest
import responses

from ai_fluency_collector.gitlab_client import GitLabAuthError, GitLabClient

BASE = "https://gitlab.example.com/api/v4"


@responses.activate
def test_validate_token_success_on_user():
    """Token validated via /user on first try."""
    responses.add(responses.GET, f"{BASE}/user", json={"id": 1}, status=200)
    client = GitLabClient("test-token", base_url="https://gitlab.example.com")
    client.validate_token()  # should not raise


@responses.activate
def test_validate_token_fallback_to_version():
    """When /user returns 404, falls back to /version."""
    responses.add(responses.GET, f"{BASE}/user", json={}, status=404)
    responses.add(responses.GET, f"{BASE}/version", json={"version": "16.0"}, status=200)
    client = GitLabClient("test-token", base_url="https://gitlab.example.com")
    client.validate_token()  # should not raise


@responses.activate
def test_validate_token_all_endpoints_404():
    """When all endpoints return 404, raises GitLabAuthError."""
    responses.add(responses.GET, f"{BASE}/user", json={}, status=404)
    responses.add(responses.GET, f"{BASE}/version", json={}, status=404)
    client = GitLabClient("test-token", base_url="https://gitlab.example.com")
    with pytest.raises(GitLabAuthError, match="not reachable"):
        client.validate_token()


@responses.activate
def test_validate_token_401_on_user():
    """401 on /user raises immediately without trying fallback."""
    responses.add(responses.GET, f"{BASE}/user", json={}, status=401)
    client = GitLabClient("test-token", base_url="https://gitlab.example.com")
    with pytest.raises(GitLabAuthError, match="authentication failed"):
        client.validate_token()


@responses.activate
def test_validate_token_401_on_version_fallback():
    """404 on /user, then 401 on /version raises auth error."""
    responses.add(responses.GET, f"{BASE}/user", json={}, status=404)
    responses.add(responses.GET, f"{BASE}/version", json={}, status=401)
    client = GitLabClient("test-token", base_url="https://gitlab.example.com")
    with pytest.raises(GitLabAuthError, match="authentication failed"):
        client.validate_token()
