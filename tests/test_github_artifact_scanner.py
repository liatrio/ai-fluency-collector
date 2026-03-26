from __future__ import annotations

import json

import responses

from ai_fluency_collector.github_client import GitHubClient
from ai_fluency_collector.scanners.github_artifact_scanner import GitHubArtifactScanner

BASE = "https://api.github.com"


def _contents_url(owner: str, repo: str, path: str) -> str:
    return f"{BASE}/repos/{owner}/{repo}/contents/{path}"


def _file_response(path: str, content: str) -> dict:
    import base64

    return {
        "type": "file",
        "path": path,
        "name": path.split("/")[-1],
        "content": base64.b64encode(content.encode()).decode() + "\n",
        "encoding": "base64",
    }


def _dir_response(entries: list[dict]) -> list[dict]:
    return entries


def _register_404(url: str) -> None:
    responses.add(responses.GET, url, json={"message": "Not Found"}, status=404)


def _register_file(owner: str, repo: str, path: str, content: str) -> None:
    responses.add(
        responses.GET,
        _contents_url(owner, repo, path),
        json=_file_response(path, content),
        status=200,
    )


def _register_missing(owner: str, repo: str, *paths: str) -> None:
    for path in paths:
        _register_404(_contents_url(owner, repo, path))


def _register_dir(owner: str, repo: str, path: str, entries: list[dict]) -> None:
    responses.add(
        responses.GET,
        _contents_url(owner, repo, path),
        json=entries,
        status=200,
    )


# ── cq-context (context files) ───────────────────────────────────────────────


@responses.activate
def test_claude_md_large_scores_100():
    """CLAUDE.md with >50 lines returns score 100 for cq-context."""
    content = "\n".join([f"line {i}" for i in range(60)])
    _register_file("org", "repo", "CLAUDE.md", content)
    # Other context file checks return 404
    _register_missing(
        "org",
        "repo",
        ".claude/CLAUDE.md",
        ".cursorrules",
        ".cursor/rules",
        ".github/copilot-instructions.md",
    )
    # Remaining artifact checks
    _register_missing("org", "repo", ".claude/settings.json")
    for path in ("prompts", ".prompts", ".claude/commands"):
        _register_404(_contents_url("org", "repo", path))
    _register_missing("org", "repo", ".mcp.json", "mcp.json")
    _register_404(_contents_url("org", "repo", "docs/adr"))
    _register_404(_contents_url("org", "repo", "docs"))
    _register_missing("org", "repo", "CONTRIBUTING.md")
    _register_404(_contents_url("org", "repo", ".github/workflows"))

    client = GitHubClient("test-token")
    scanner = GitHubArtifactScanner(client)
    scores = scanner.scan_repo("org", "repo")

    assert scores["cq-context"] == 100


@responses.activate
def test_cursorrules_short_scores_40():
    """Short .cursorrules (<10 lines) returns score 40."""
    _register_missing("org", "repo", "CLAUDE.md", ".claude/CLAUDE.md")
    _register_file("org", "repo", ".cursorrules", "line 1\nline 2")
    _register_missing("org", "repo", ".cursor/rules", ".github/copilot-instructions.md")
    _register_missing("org", "repo", ".claude/settings.json")
    for path in ("prompts", ".prompts", ".claude/commands"):
        _register_404(_contents_url("org", "repo", path))
    _register_missing("org", "repo", ".mcp.json", "mcp.json")
    _register_404(_contents_url("org", "repo", "docs/adr"))
    _register_404(_contents_url("org", "repo", "docs"))
    _register_missing("org", "repo", "CONTRIBUTING.md")
    _register_404(_contents_url("org", "repo", ".github/workflows"))

    client = GitHubClient("test-token")
    scanner = GitHubArtifactScanner(client)
    scores = scanner.scan_repo("org", "repo")

    assert scores["cq-context"] == 40


@responses.activate
def test_no_context_files_scores_0():
    """No context files returns 0 for cq-context."""
    for path in (
        "CLAUDE.md",
        ".claude/CLAUDE.md",
        ".cursorrules",
        ".cursor/rules",
        ".github/copilot-instructions.md",
    ):
        _register_missing("org", "repo", path)
    _register_missing("org", "repo", ".claude/settings.json")
    for path in ("prompts", ".prompts", ".claude/commands"):
        _register_404(_contents_url("org", "repo", path))
    _register_missing("org", "repo", ".mcp.json", "mcp.json")
    _register_404(_contents_url("org", "repo", "docs/adr"))
    _register_404(_contents_url("org", "repo", "docs"))
    _register_missing("org", "repo", "CONTRIBUTING.md")
    _register_404(_contents_url("org", "repo", ".github/workflows"))

    client = GitHubClient("test-token")
    scanner = GitHubArtifactScanner(client)
    scores = scanner.scan_repo("org", "repo")

    assert scores["cq-context"] == 0


# ── tg-permission-gated ──────────────────────────────────────────────────────


@responses.activate
def test_settings_with_permissions_scores_80():
    """settings.json with allowedTools key returns 80."""
    settings = json.dumps({"allowedTools": ["Bash", "Read"]})
    _register_missing(
        "org",
        "repo",
        "CLAUDE.md",
        ".claude/CLAUDE.md",
        ".cursorrules",
        ".cursor/rules",
        ".github/copilot-instructions.md",
    )
    _register_file("org", "repo", ".claude/settings.json", settings)
    for path in ("prompts", ".prompts", ".claude/commands"):
        _register_404(_contents_url("org", "repo", path))
    _register_missing("org", "repo", ".mcp.json", "mcp.json")
    _register_404(_contents_url("org", "repo", "docs/adr"))
    _register_404(_contents_url("org", "repo", "docs"))
    _register_missing("org", "repo", "CONTRIBUTING.md")
    _register_404(_contents_url("org", "repo", ".github/workflows"))

    client = GitHubClient("test-token")
    scanner = GitHubArtifactScanner(client)
    scores = scanner.scan_repo("org", "repo")

    assert scores["tg-permission-gated"] == 80


# ── ks-patterns (prompt directories) ─────────────────────────────────────────


@responses.activate
def test_prompts_dir_with_5_files_scores_75():
    """prompts/ with 5 files returns 75 for ks-patterns."""
    entries = [{"type": "file", "name": f"p{i}.md"} for i in range(5)]
    _register_missing(
        "org",
        "repo",
        "CLAUDE.md",
        ".claude/CLAUDE.md",
        ".cursorrules",
        ".cursor/rules",
        ".github/copilot-instructions.md",
    )
    _register_missing("org", "repo", ".claude/settings.json")
    _register_dir("org", "repo", "prompts", entries)
    _register_404(_contents_url("org", "repo", ".prompts"))
    _register_404(_contents_url("org", "repo", ".claude/commands"))
    _register_missing("org", "repo", ".mcp.json", "mcp.json")
    _register_404(_contents_url("org", "repo", "docs/adr"))
    _register_404(_contents_url("org", "repo", "docs"))
    _register_missing("org", "repo", "CONTRIBUTING.md")
    _register_404(_contents_url("org", "repo", ".github/workflows"))

    client = GitHubClient("test-token")
    scanner = GitHubArtifactScanner(client)
    scores = scanner.scan_repo("org", "repo")

    assert scores["ks-patterns"] == 75


# ── pm-advanced (MCP config) ─────────────────────────────────────────────────


@responses.activate
def test_mcp_json_with_multiple_servers_scores_100():
    """mcp.json with >1 server returns 100."""
    mcp = json.dumps({"mcpServers": {"fs": {}, "github": {}, "postgres": {}}})
    _register_missing(
        "org",
        "repo",
        "CLAUDE.md",
        ".claude/CLAUDE.md",
        ".cursorrules",
        ".cursor/rules",
        ".github/copilot-instructions.md",
    )
    _register_missing("org", "repo", ".claude/settings.json")
    for path in ("prompts", ".prompts", ".claude/commands"):
        _register_404(_contents_url("org", "repo", path))
    _register_missing("org", "repo", ".mcp.json")
    _register_file("org", "repo", "mcp.json", mcp)
    _register_404(_contents_url("org", "repo", "docs/adr"))
    _register_404(_contents_url("org", "repo", "docs"))
    _register_missing("org", "repo", "CONTRIBUTING.md")
    _register_404(_contents_url("org", "repo", ".github/workflows"))

    client = GitHubClient("test-token")
    scanner = GitHubArtifactScanner(client)
    scores = scanner.scan_repo("org", "repo")

    assert scores["pm-advanced"] == 100


# ── Multi-repo max aggregation ───────────────────────────────────────────────


@responses.activate
def test_multi_repo_max_aggregation():
    """scan_repos returns max score per skill across repos."""
    # Repo 1: no context files
    for path in (
        "CLAUDE.md",
        ".claude/CLAUDE.md",
        ".cursorrules",
        ".cursor/rules",
        ".github/copilot-instructions.md",
    ):
        _register_missing("org", "repo1", path)
    _register_missing("org", "repo1", ".claude/settings.json")
    for path in ("prompts", ".prompts", ".claude/commands"):
        _register_404(_contents_url("org", "repo1", path))
    _register_missing("org", "repo1", ".mcp.json", "mcp.json")
    _register_404(_contents_url("org", "repo1", "docs/adr"))
    _register_404(_contents_url("org", "repo1", "docs"))
    _register_missing("org", "repo1", "CONTRIBUTING.md")
    _register_404(_contents_url("org", "repo1", ".github/workflows"))

    # Repo 2: CLAUDE.md with >50 lines
    content = "\n".join([f"line {i}" for i in range(60)])
    _register_file("org", "repo2", "CLAUDE.md", content)
    _register_missing(
        "org",
        "repo2",
        ".claude/CLAUDE.md",
        ".cursorrules",
        ".cursor/rules",
        ".github/copilot-instructions.md",
    )
    _register_missing("org", "repo2", ".claude/settings.json")
    for path in ("prompts", ".prompts", ".claude/commands"):
        _register_404(_contents_url("org", "repo2", path))
    _register_missing("org", "repo2", ".mcp.json", "mcp.json")
    _register_404(_contents_url("org", "repo2", "docs/adr"))
    _register_404(_contents_url("org", "repo2", "docs"))
    _register_missing("org", "repo2", "CONTRIBUTING.md")
    _register_404(_contents_url("org", "repo2", ".github/workflows"))

    client = GitHubClient("test-token")
    scanner = GitHubArtifactScanner(client)
    signals = scanner.scan_repos(["org/repo1", "org/repo2"])

    cq_context = next((s for s in signals if s["skill_id"] == "cq-context"), None)
    assert cq_context is not None
    assert cq_context["score"] == 100  # max from repo2


@responses.activate
def test_all_missing_returns_no_signals():
    """Repo with no artifacts produces no signals."""
    for path in (
        "CLAUDE.md",
        ".claude/CLAUDE.md",
        ".cursorrules",
        ".cursor/rules",
        ".github/copilot-instructions.md",
    ):
        _register_missing("org", "empty", path)
    _register_missing("org", "empty", ".claude/settings.json")
    for path in ("prompts", ".prompts", ".claude/commands"):
        _register_404(_contents_url("org", "empty", path))
    _register_missing("org", "empty", ".mcp.json", "mcp.json")
    _register_404(_contents_url("org", "empty", "docs/adr"))
    _register_404(_contents_url("org", "empty", "docs"))
    _register_missing("org", "empty", "CONTRIBUTING.md")
    _register_404(_contents_url("org", "empty", ".github/workflows"))

    client = GitHubClient("test-token")
    scanner = GitHubArtifactScanner(client)
    signals = scanner.scan_repos(["org/empty"])

    assert signals == []


# ── Private repo 403 handling ─────────────────────────────────────────────


@responses.activate
def test_403_on_file_fetch_raises_access_error():
    """403 response when fetching a file raises GitHubAccessError."""
    from ai_fluency_collector.github_client import GitHubAccessError

    responses.add(
        responses.GET,
        _contents_url("org", "private", "CLAUDE.md"),
        json={"message": "Forbidden"},
        status=403,
    )

    client = GitHubClient("test-token")
    scanner = GitHubArtifactScanner(client)

    import pytest

    with pytest.raises(GitHubAccessError, match="Access denied"):
        scanner.scan_repo("org", "private")


@responses.activate
def test_403_on_directory_listing_raises_access_error():
    """403 response when listing a directory raises GitHubAccessError."""
    from ai_fluency_collector.github_client import GitHubAccessError

    # Context files all 404 to reach prompt dir check
    for path in (
        "CLAUDE.md",
        ".claude/CLAUDE.md",
        ".cursorrules",
        ".cursor/rules",
        ".github/copilot-instructions.md",
    ):
        _register_missing("org", "private", path)
    _register_missing("org", "private", ".claude/settings.json")
    # 403 on directory listing
    responses.add(
        responses.GET,
        _contents_url("org", "private", "prompts"),
        json={"message": "Forbidden"},
        status=403,
    )

    client = GitHubClient("test-token")
    scanner = GitHubArtifactScanner(client)

    import pytest

    with pytest.raises(GitHubAccessError, match="Access denied"):
        scanner.scan_repo("org", "private")
