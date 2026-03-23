from __future__ import annotations

from datetime import date, timedelta

from ai_fluency_collector.gitlab_client import GitLabClient

# Branch type weights for artifact scoring
DEFAULT_BRANCH_WEIGHT = 0.5
FEATURE_BRANCH_WEIGHT = 0.8

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


def _get_active_branches(
    client: GitLabClient,
    project_path: str,
    active_days: int = 90,
    reference_date: date | None = None,
) -> list[dict]:
    """Get active branches with their type weight.

    Returns list of {"name": str, "weight": float} for branches
    with a commit within active_days of reference_date.
    If reference_date is None, defaults to date.today().
    """
    ref_date = reference_date if reference_date is not None else date.today()
    cutoff = ref_date - timedelta(days=active_days)
    cutoff_str = cutoff.isoformat()
    branches = client.get_branches(project_path)
    active: list[dict] = []

    for branch in branches:
        committed_date = branch.get("commit", {}).get("committed_date", "")
        # GitLab returns ISO 8601 dates like "2026-03-15T10:00:00.000+00:00"
        if committed_date and committed_date[:10] >= cutoff_str:
            is_default = branch.get("default", False)
            active.append(
                {
                    "name": branch["name"],
                    "weight": DEFAULT_BRANCH_WEIGHT if is_default else FEATURE_BRANCH_WEIGHT,
                }
            )

    return active


class ArtifactScanner:
    """Scans GitLab projects for AI adoption artifact files and directories."""

    def __init__(
        self,
        client: GitLabClient,
        active_days: int = 90,
        reference_date: date | None = None,
    ) -> None:
        self.client = client
        self.active_days = active_days
        self.reference_date = reference_date

    def _check_artifact_on_branch(self, project_path: str, artifact: dict, ref: str) -> bool:
        """Check if an artifact exists on a specific branch."""
        for check_type, check_path in artifact["checks"]:
            if check_type == "file":
                if self.client.check_file_exists(project_path, check_path, ref=ref):
                    return True
            elif check_type == "dir":
                if self.client.check_directory_exists(project_path, check_path, ref=ref):
                    return True
        return False

    def scan_project(self, project_path: str) -> dict[str, float]:
        """Scan a project across all active branches for artifact types.

        Returns a dict of {artifact_id: weight} where weight is the highest
        branch weight where the artifact was found (0.0 if not found).
        Default branch = 0.5, active feature branch = 0.8.

        Raises GitLabAccessError if the project is inaccessible.
        """
        active_branches = _get_active_branches(
            self.client, project_path, self.active_days, self.reference_date
        )

        # If no active branches found, fall back to scanning HEAD only
        if not active_branches:
            active_branches = [{"name": "HEAD", "weight": DEFAULT_BRANCH_WEIGHT}]

        results: dict[str, float] = {}
        for artifact in ARTIFACT_DEFINITIONS:
            best_weight = 0.0
            for branch in active_branches:
                if self._check_artifact_on_branch(project_path, artifact, branch["name"]):
                    best_weight = max(best_weight, branch["weight"])
                    # If we already found the max possible weight, stop early
                    if best_weight >= FEATURE_BRANCH_WEIGHT:
                        break
            results[artifact["id"]] = best_weight
        return results
