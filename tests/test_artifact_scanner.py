from __future__ import annotations

from datetime import date

import pytest
import responses

from ai_fluency_collector.gitlab_client import GitLabAccessError, GitLabClient
from ai_fluency_collector.scanners.gitlab_artifact_scanner import (
    ARTIFACT_DEFINITIONS,
    DEFAULT_BRANCH_WEIGHT,
    FEATURE_BRANCH_WEIGHT,
    ArtifactScanner,
)

BASE = "https://gitlab.com/api/v4"
PROJECT = "my-group/my-project"
ENCODED_PROJECT = "my-group%2Fmy-project"

TODAY = date.today().isoformat()

# A single default branch that is active (committed today)
SINGLE_DEFAULT_BRANCH = [
    {
        "name": "main",
        "default": True,
        "commit": {"committed_date": f"{TODAY}T00:00:00.000+00:00"},
    }
]


def _branches_url() -> str:
    return f"{BASE}/projects/{ENCODED_PROJECT}/repository/branches"


def _file_url(file_path: str) -> str:
    from urllib.parse import quote

    encoded_file = quote(file_path, safe="")
    return f"{BASE}/projects/{ENCODED_PROJECT}/repository/files/{encoded_file}"


def _tree_url() -> str:
    return f"{BASE}/projects/{ENCODED_PROJECT}/repository/tree"


def _register_branches(branches: list[dict]) -> None:
    responses.add(responses.GET, _branches_url(), json=branches, status=200)
    responses.add(responses.GET, _branches_url(), json=[], status=200)


def _register_all_artifacts_missing() -> None:
    """Register 404/empty for all artifact checks."""
    for defn in ARTIFACT_DEFINITIONS:
        for check_type, check_path in defn["checks"]:
            if check_type == "file":
                responses.add(responses.HEAD, _file_url(check_path), status=404)
            elif check_type == "dir":
                responses.add(responses.GET, _tree_url(), json=[], status=200)


@responses.activate
def test_all_artifacts_detected_default_branch():
    """All 8 artifact types detected on the default branch."""
    _register_branches(SINGLE_DEFAULT_BRANCH)

    for path in [
        "CLAUDE.md",
        ".claude/settings.json",
        ".mcp.json",
        ".cursorrules",
        ".github/copilot-instructions.md",
        "AGENTS.md",
        ".aider.conf.yml",
    ]:
        responses.add(responses.HEAD, _file_url(path), status=200)

    responses.add(responses.GET, _tree_url(), json=[{"name": "prompt1.md"}], status=200)

    client = GitLabClient("test-token")
    scanner = ArtifactScanner(client)
    result = scanner.scan_project(PROJECT)

    assert len(result) == 8
    for artifact_id, weight in result.items():
        assert weight == DEFAULT_BRANCH_WEIGHT, f"{artifact_id}: expected {DEFAULT_BRANCH_WEIGHT}"


@responses.activate
def test_no_artifacts_found():
    """All artifacts absent returns 0.0 weight."""
    _register_branches(SINGLE_DEFAULT_BRANCH)
    _register_all_artifacts_missing()

    client = GitLabClient("test-token")
    scanner = ArtifactScanner(client)
    result = scanner.scan_project(PROJECT)

    assert len(result) == 8
    for artifact_id, weight in result.items():
        assert weight == 0.0, f"Expected {artifact_id} to be 0.0"


@responses.activate
def test_feature_branch_artifact_higher_weight():
    """Artifact on feature branch gets higher weight than default branch."""
    branches = [
        {
            "name": "main",
            "default": True,
            "commit": {"committed_date": f"{TODAY}T00:00:00.000+00:00"},
        },
        {
            "name": "feat/add-claude",
            "default": False,
            "commit": {"committed_date": f"{TODAY}T00:00:00.000+00:00"},
        },
    ]
    _register_branches(branches)

    # CLAUDE.md NOT on main (first branch scanned), but YES on feature branch
    # The scanner scans default branch first, then feature branch
    # Main: 404, Feature: 200
    responses.add(responses.HEAD, _file_url("CLAUDE.md"), status=404)
    responses.add(responses.HEAD, _file_url("CLAUDE.md"), status=200)

    # All other artifacts missing on both branches
    for defn in ARTIFACT_DEFINITIONS:
        if defn["id"] == "claude-md":
            continue
        for check_type, check_path in defn["checks"]:
            if check_type == "file":
                # 404 for both branches
                responses.add(responses.HEAD, _file_url(check_path), status=404)
                responses.add(responses.HEAD, _file_url(check_path), status=404)
            elif check_type == "dir":
                responses.add(responses.GET, _tree_url(), json=[], status=200)
                responses.add(responses.GET, _tree_url(), json=[], status=200)

    client = GitLabClient("test-token")
    scanner = ArtifactScanner(client)
    result = scanner.scan_project(PROJECT)

    assert result["claude-md"] == FEATURE_BRANCH_WEIGHT


@responses.activate
def test_artifact_on_both_branches_takes_highest():
    """Artifact on both default and feature branch takes the higher weight."""
    branches = [
        {
            "name": "main",
            "default": True,
            "commit": {"committed_date": f"{TODAY}T00:00:00.000+00:00"},
        },
        {
            "name": "feat/stuff",
            "default": False,
            "commit": {"committed_date": f"{TODAY}T00:00:00.000+00:00"},
        },
    ]
    _register_branches(branches)

    # CLAUDE.md found on both branches
    responses.add(responses.HEAD, _file_url("CLAUDE.md"), status=200)  # main
    responses.add(responses.HEAD, _file_url("CLAUDE.md"), status=200)  # feature

    # Other artifacts missing on both branches
    for defn in ARTIFACT_DEFINITIONS:
        if defn["id"] == "claude-md":
            continue
        for check_type, check_path in defn["checks"]:
            if check_type == "file":
                responses.add(responses.HEAD, _file_url(check_path), status=404)
                responses.add(responses.HEAD, _file_url(check_path), status=404)
            elif check_type == "dir":
                responses.add(responses.GET, _tree_url(), json=[], status=200)
                responses.add(responses.GET, _tree_url(), json=[], status=200)

    client = GitLabClient("test-token")
    scanner = ArtifactScanner(client)
    result = scanner.scan_project(PROJECT)

    # Feature branch weight (0.8) > default (0.5), so should be 0.8
    assert result["claude-md"] == FEATURE_BRANCH_WEIGHT


@responses.activate
def test_stale_branch_excluded():
    """Branch with old commit date is excluded from scanning."""
    branches = [
        {
            "name": "main",
            "default": True,
            "commit": {"committed_date": f"{TODAY}T00:00:00.000+00:00"},
        },
        {
            "name": "old-branch",
            "default": False,
            "commit": {"committed_date": "2020-01-01T00:00:00.000+00:00"},
        },
    ]
    _register_branches(branches)

    # CLAUDE.md only exists (would only be on old-branch if it were scanned)
    # But old-branch should be excluded, so only main is scanned
    responses.add(responses.HEAD, _file_url("CLAUDE.md"), status=404)  # main only

    for defn in ARTIFACT_DEFINITIONS:
        if defn["id"] == "claude-md":
            continue
        for check_type, check_path in defn["checks"]:
            if check_type == "file":
                responses.add(responses.HEAD, _file_url(check_path), status=404)
            elif check_type == "dir":
                responses.add(responses.GET, _tree_url(), json=[], status=200)

    client = GitLabClient("test-token")
    scanner = ArtifactScanner(client)
    result = scanner.scan_project(PROJECT)

    assert result["claude-md"] == 0.0


@responses.activate
def test_or_logic_mcp_json_fallback():
    """mcp.json detected when .mcp.json is absent."""
    _register_branches(SINGLE_DEFAULT_BRANCH)

    responses.add(responses.HEAD, _file_url(".mcp.json"), status=404)
    responses.add(responses.HEAD, _file_url("mcp.json"), status=200)

    for defn in ARTIFACT_DEFINITIONS:
        if defn["id"] == "mcp-json":
            continue
        for check_type, check_path in defn["checks"]:
            if check_type == "file":
                responses.add(responses.HEAD, _file_url(check_path), status=404)
            elif check_type == "dir":
                responses.add(responses.GET, _tree_url(), json=[], status=200)

    client = GitLabClient("test-token")
    scanner = ArtifactScanner(client)
    result = scanner.scan_project(PROJECT)
    assert result["mcp-json"] == DEFAULT_BRANCH_WEIGHT


@responses.activate
def test_project_access_error_403():
    """403 response raises GitLabAccessError."""
    _register_branches(SINGLE_DEFAULT_BRANCH)
    responses.add(responses.HEAD, _file_url("CLAUDE.md"), status=403)

    client = GitLabClient("test-token")
    scanner = ArtifactScanner(client)
    with pytest.raises(GitLabAccessError, match="Access denied"):
        scanner.scan_project(PROJECT)


@responses.activate
def test_no_active_branches_falls_back_to_head():
    """When branches exist but none are active, falls back to scanning HEAD."""
    # Return branches with old dates
    _register_branches(
        [
            {
                "name": "main",
                "default": True,
                "commit": {"committed_date": "2020-01-01T00:00:00.000+00:00"},
            }
        ]
    )
    _register_all_artifacts_missing()

    client = GitLabClient("test-token")
    scanner = ArtifactScanner(client)
    result = scanner.scan_project(PROJECT)

    for weight in result.values():
        assert weight == 0.0


@responses.activate
def test_project_not_found_raises_error():
    """404 on branches raises GitLabAccessError with helpful message."""
    responses.add(responses.GET, _branches_url(), status=404)

    client = GitLabClient("test-token")
    scanner = ArtifactScanner(client)
    with pytest.raises(GitLabAccessError, match="not found"):
        scanner.scan_project(PROJECT)
