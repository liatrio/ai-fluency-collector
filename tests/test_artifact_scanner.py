from __future__ import annotations

import pytest
import responses

from ai_fluency_collector.gitlab_client import GitLabAccessError, GitLabClient
from ai_fluency_collector.scanners.artifact_scanner import ARTIFACT_DEFINITIONS, ArtifactScanner

BASE = "https://gitlab.com/api/v4"
PROJECT = "my-group/my-project"
ENCODED_PROJECT = "my-group%2Fmy-project"


def _file_url(file_path: str) -> str:
    from urllib.parse import quote

    encoded_file = quote(file_path, safe="")
    return f"{BASE}/projects/{ENCODED_PROJECT}/repository/files/{encoded_file}"


def _tree_url() -> str:
    return f"{BASE}/projects/{ENCODED_PROJECT}/repository/tree"


@responses.activate
def test_all_artifacts_detected():
    """All 8 artifact types detected when present."""
    # Files: HEAD requests
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

    # Directory: prompts/
    responses.add(
        responses.GET,
        _tree_url(),
        json=[{"name": "prompt1.md"}],
        status=200,
    )

    # The OR-logic artifacts may also check alternatives; register 404 for unchecked paths
    # mcp.json (second option, won't be reached since .mcp.json returns 200)
    # .cursor/ dir (won't be reached since .cursorrules returns 200)
    # .agents/ dir (won't be reached since AGENTS.md returns 200)
    # .aider.model.settings.yml, .aiderignore (won't be reached since .aider.conf.yml returns 200)

    client = GitLabClient("test-token")
    scanner = ArtifactScanner(client)
    result = scanner.scan_project(PROJECT)

    assert len(result) == 8
    for artifact_id, found in result.items():
        assert found is True, f"Expected {artifact_id} to be True"


@responses.activate
def test_no_artifacts_found():
    """All artifacts absent when files don't exist."""
    # Register 404 for all possible file checks
    for defn in ARTIFACT_DEFINITIONS:
        for check_type, check_path in defn["checks"]:
            if check_type == "file":
                responses.add(responses.HEAD, _file_url(check_path), status=404)
            elif check_type == "dir":
                responses.add(responses.GET, _tree_url(), json=[], status=200)

    client = GitLabClient("test-token")
    scanner = ArtifactScanner(client)
    result = scanner.scan_project(PROJECT)

    assert len(result) == 8
    for artifact_id, found in result.items():
        assert found is False, f"Expected {artifact_id} to be False"


@responses.activate
def test_or_logic_mcp_json_fallback():
    """mcp.json detected when .mcp.json is absent."""
    # .mcp.json → 404
    responses.add(responses.HEAD, _file_url(".mcp.json"), status=404)
    # mcp.json → 200
    responses.add(responses.HEAD, _file_url("mcp.json"), status=200)

    # Register 404 for everything else
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
    assert result["mcp-json"] is True


@responses.activate
def test_or_logic_cursor_directory():
    """.cursor/ directory detected when .cursorrules is absent."""
    responses.add(responses.HEAD, _file_url(".cursorrules"), status=404)
    # .cursor/ dir check via tree API — register for prompts first (404), then .cursor (found)
    # prompts check comes first in ARTIFACT_DEFINITIONS
    responses.add(responses.GET, _tree_url(), json=[], status=200)  # prompts/
    responses.add(responses.GET, _tree_url(), json=[{"name": "rules"}], status=200)  # .cursor/

    # Register 404 for remaining file checks
    for defn in ARTIFACT_DEFINITIONS:
        if defn["id"] in ("cursor", "prompts-dir"):
            continue
        for check_type, check_path in defn["checks"]:
            if check_type == "file":
                responses.add(responses.HEAD, _file_url(check_path), status=404)
            elif check_type == "dir":
                responses.add(responses.GET, _tree_url(), json=[], status=200)

    client = GitLabClient("test-token")
    scanner = ArtifactScanner(client)
    result = scanner.scan_project(PROJECT)
    assert result["cursor"] is True


@responses.activate
def test_project_access_error_403():
    """403 response raises GitLabAccessError."""
    responses.add(responses.HEAD, _file_url("CLAUDE.md"), status=403)

    client = GitLabClient("test-token")
    scanner = ArtifactScanner(client)
    with pytest.raises(GitLabAccessError, match="Access denied"):
        scanner.scan_project(PROJECT)


@responses.activate
def test_project_not_found_404_on_tree():
    """404 on tree API returns False (not an error)."""
    # All file checks 404
    for defn in ARTIFACT_DEFINITIONS:
        for check_type, check_path in defn["checks"]:
            if check_type == "file":
                responses.add(responses.HEAD, _file_url(check_path), status=404)
            elif check_type == "dir":
                responses.add(responses.GET, _tree_url(), json=[], status=404)

    client = GitLabClient("test-token")
    scanner = ArtifactScanner(client)
    result = scanner.scan_project(PROJECT)
    # All should be False, no error raised
    for found in result.values():
        assert found is False
