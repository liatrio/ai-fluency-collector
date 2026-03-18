from __future__ import annotations

from collections import defaultdict

# Declarative mapping: artifact_id → skill_id with weight.
# To adjust scoring, edit this data structure only — no scanner or output code changes needed.
ARTIFACT_SKILL_MAPPINGS: list[dict] = [
    {"artifact_id": "claude-md", "skill_id": "cq-context", "weight": 0.5},
    {"artifact_id": "claude-md", "skill_id": "im-autocomplete", "weight": 0.3},
    {"artifact_id": "claude-settings", "skill_id": "tg-permission-gated", "weight": 1.0},
    {"artifact_id": "mcp-json", "skill_id": "im-chat", "weight": 0.5},
    {"artifact_id": "mcp-json", "skill_id": "pm-core", "weight": 0.5},
    {"artifact_id": "prompts-dir", "skill_id": "ks-patterns", "weight": 0.7},
    {"artifact_id": "prompts-dir", "skill_id": "cq-delegation", "weight": 0.5},
    {"artifact_id": "cursor", "skill_id": "im-autocomplete", "weight": 0.3},
    {"artifact_id": "cursor", "skill_id": "im-inline-edit", "weight": 0.5},
    {"artifact_id": "copilot-instructions", "skill_id": "im-autocomplete", "weight": 0.3},
    {"artifact_id": "agents", "skill_id": "im-supervised-agent", "weight": 0.5},
    {"artifact_id": "agents", "skill_id": "im-cli-agent", "weight": 0.5},
    {"artifact_id": "aider", "skill_id": "im-chat", "weight": 0.5},
]

# CI pattern → skill mappings
CI_SKILL_MAPPINGS: list[dict] = [
    {"artifact_id": "sast-dast", "skill_id": "sdlc-security", "weight": 0.4},
    {"artifact_id": "sast-dast", "skill_id": "tg-security-gates", "weight": 0.5},
    {"artifact_id": "secret-detection", "skill_id": "sdlc-security", "weight": 0.3},
    {"artifact_id": "ai-code-review", "skill_id": "tg-code-review", "weight": 1.0},
    {"artifact_id": "ai-test-generation", "skill_id": "sdlc-testing", "weight": 1.0},
    {"artifact_id": "dependency-scanning", "skill_id": "sdlc-security", "weight": 0.3},
    {"artifact_id": "code-coverage", "skill_id": "pm-measurement", "weight": 1.0},
    {"artifact_id": "deployment-gates", "skill_id": "sdlc-deployment", "weight": 0.5},
    {"artifact_id": "deployment-gates", "skill_id": "tg-supervised-auto", "weight": 0.5},
]


def _get_artifact_name(artifact_id: str) -> str:
    """Look up the human-readable artifact name."""
    from ai_fluency_collector.scanners.artifact_scanner import ARTIFACT_DEFINITIONS

    for defn in ARTIFACT_DEFINITIONS:
        if defn["id"] == artifact_id:
            return defn["name"]
    return artifact_id


def calculate_scores(
    scan_results: list[dict[str, bool]],
    mappings: list[dict],
    artifact_names: dict[str, str] | None = None,
) -> list[dict]:
    """Calculate weighted skill scores from scan results across multiple projects.

    Args:
        scan_results: List of per-project dicts {artifact_id: bool}.
        mappings: List of mapping dicts with artifact_id, skill_id, weight.
        artifact_names: Optional dict of {artifact_id: display_name} for evidence.

    Returns:
        List of {skill_id, score, evidence} dicts. Only skills with score > 0 are included.
    """
    if not scan_results:
        return []

    num_projects = len(scan_results)

    # Group mappings by skill_id
    skill_mappings: dict[str, list[dict]] = defaultdict(list)
    for m in mappings:
        skill_mappings[m["skill_id"]].append(m)

    signals: list[dict] = []

    for skill_id, skill_maps in skill_mappings.items():
        # For each project, compute the score contribution
        project_scores: list[float] = []
        # Track artifact presence across projects for evidence
        artifact_counts: dict[str, int] = defaultdict(int)

        for project_result in scan_results:
            found_weight = 0.0
            total_weight = 0.0
            for m in skill_maps:
                total_weight += m["weight"]
                if project_result.get(m["artifact_id"], False):
                    found_weight += m["weight"]
                    artifact_counts[m["artifact_id"]] += 1
            if total_weight > 0:
                project_scores.append(min(100.0, (found_weight / total_weight) * 100.0))
            else:
                project_scores.append(0.0)

        # Average across projects
        avg_score = sum(project_scores) / num_projects if project_scores else 0.0
        score = round(avg_score)

        if score <= 0:
            continue

        # Build evidence string
        evidence_parts = []
        for m in skill_maps:
            aid = m["artifact_id"]
            if artifact_counts[aid] > 0:
                if artifact_names:
                    name = artifact_names.get(aid, aid)
                else:
                    name = _get_artifact_name(aid)
                count = artifact_counts[aid]
                evidence_parts.append(f"{name} found in {count}/{num_projects} projects")

        evidence = "; ".join(evidence_parts) if evidence_parts else "detected"

        signals.append({"skill_id": skill_id, "score": score, "evidence": evidence})

    return signals
