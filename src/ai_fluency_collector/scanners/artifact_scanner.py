from __future__ import annotations

from ai_fluency_collector.gitlab_client import GitLabClient

# Each artifact has an ID, a human-readable name, and a list of checks.
# A check is either ("file", path) or ("dir", path).
# An artifact is considered present if ANY of its checks succeed (OR logic).
ARTIFACT_DEFINITIONS: list[dict] = [
    {
        "id": "claude-md",
        "name": "CLAUDE.md",
        "checks": [("file", "CLAUDE.md")],
    },
    {
        "id": "claude-settings",
        "name": ".claude/settings.json",
        "checks": [("file", ".claude/settings.json")],
    },
    {
        "id": "mcp-json",
        "name": ".mcp.json or mcp.json",
        "checks": [("file", ".mcp.json"), ("file", "mcp.json")],
    },
    {
        "id": "prompts-dir",
        "name": "prompts/ directory",
        "checks": [("dir", "prompts")],
    },
    {
        "id": "cursor",
        "name": ".cursorrules or .cursor/",
        "checks": [("file", ".cursorrules"), ("dir", ".cursor")],
    },
    {
        "id": "copilot-instructions",
        "name": ".github/copilot-instructions.md",
        "checks": [("file", ".github/copilot-instructions.md")],
    },
    {
        "id": "agents",
        "name": "AGENTS.md or .agents/",
        "checks": [("file", "AGENTS.md"), ("dir", ".agents")],
    },
    {
        "id": "aider",
        "name": "Aider config files",
        "checks": [
            ("file", ".aider.conf.yml"),
            ("file", ".aider.model.settings.yml"),
            ("file", ".aiderignore"),
        ],
    },
]


class ArtifactScanner:
    """Scans GitLab projects for AI adoption artifact files and directories."""

    def __init__(self, client: GitLabClient) -> None:
        self.client = client

    def scan_project(self, project_path: str) -> dict[str, bool]:
        """Scan a single project for all artifact types.

        Returns a dict of {artifact_id: found_bool}.
        Raises GitLabAccessError if the project is inaccessible.
        """
        results: dict[str, bool] = {}
        for artifact in ARTIFACT_DEFINITIONS:
            found = False
            for check_type, check_path in artifact["checks"]:
                if check_type == "file":
                    if self.client.check_file_exists(project_path, check_path):
                        found = True
                        break
                elif check_type == "dir":
                    if self.client.check_directory_exists(project_path, check_path):
                        found = True
                        break
            results[artifact["id"]] = found
        return results
