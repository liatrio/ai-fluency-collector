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


# Member activity → skill mappings
# Score based on percentage of members showing AI co-author activity
MEMBER_SKILL_MAPPINGS: list[dict] = [
    {"artifact_id": "coauthor-claude", "skill_id": "im-cli-agent", "weight": 0.5},
    {"artifact_id": "coauthor-claude", "skill_id": "im-chat", "weight": 0.5},
    {"artifact_id": "coauthor-copilot", "skill_id": "im-autocomplete", "weight": 0.5},
    {"artifact_id": "coauthor-cursor", "skill_id": "im-autocomplete", "weight": 0.3},
    {"artifact_id": "coauthor-cursor", "skill_id": "im-inline-edit", "weight": 0.3},
]


def calculate_member_scores(
    member_results: list,
    mappings: list[dict],
) -> list[dict]:
    """Calculate skill scores from member activity scan results.

    Score is based on the percentage of members who have any co-author
    commits for each pattern. E.g., if 3/5 members have Claude co-author
    commits, the score for Claude-related skills is 60.

    Args:
        member_results: List of MemberResult objects.
        mappings: List of mapping dicts with artifact_id, skill_id, weight.

    Returns:
        List of {skill_id, score, evidence} dicts.
    """
    if not member_results:
        return []

    num_members = len(member_results)

    # Count how many members have each pattern
    pattern_member_counts: dict[str, int] = defaultdict(int)
    pattern_total_commits: dict[str, int] = defaultdict(int)
    for result in member_results:
        for pattern_id, count in result.ai_coauthor_counts.items():
            if count > 0:
                pattern_member_counts[pattern_id] += 1
                pattern_total_commits[pattern_id] += count

    # Group mappings by skill_id
    skill_mappings: dict[str, list[dict]] = defaultdict(list)
    for m in mappings:
        skill_mappings[m["skill_id"]].append(m)

    signals: list[dict] = []

    for skill_id, skill_maps in skill_mappings.items():
        found_weight = 0.0
        total_weight = 0.0
        evidence_parts = []

        for m in skill_maps:
            aid = m["artifact_id"]
            total_weight += m["weight"]
            member_count = pattern_member_counts.get(aid, 0)
            if member_count > 0:
                # Weight by proportion of members with this pattern
                found_weight += m["weight"] * (member_count / num_members)
                commits = pattern_total_commits.get(aid, 0)
                # Get pattern display name
                from ai_fluency_collector.scanners.member_scanner import (
                    AI_COAUTHOR_PATTERNS,
                )

                name = aid
                for p in AI_COAUTHOR_PATTERNS:
                    if p["id"] == aid:
                        name = p["name"]
                        break
                evidence_parts.append(
                    f"Co-authored commits with {name} "
                    f"by {member_count}/{num_members} members "
                    f"({commits} commits)"
                )

        if total_weight > 0:
            score = round(min(100.0, (found_weight / total_weight) * 100.0))
        else:
            score = 0

        if score <= 0:
            continue

        evidence = "; ".join(evidence_parts) if evidence_parts else "detected"
        signals.append({"skill_id": skill_id, "score": score, "evidence": evidence})

    return signals


def _get_artifact_name(artifact_id: str) -> str:
    """Look up the human-readable artifact name."""
    from ai_fluency_collector.scanners.artifact_scanner import ARTIFACT_DEFINITIONS

    for defn in ARTIFACT_DEFINITIONS:
        if defn["id"] == artifact_id:
            return defn["name"]
    return artifact_id


def calculate_scores(
    scan_results: list[dict[str, bool | float]],
    mappings: list[dict],
    artifact_names: dict[str, str] | None = None,
) -> list[dict]:
    """Calculate weighted skill scores from scan results across multiple projects.

    Args:
        scan_results: List of per-project dicts {artifact_id: bool_or_float}.
            Values can be bool (True/False) or float (0.0 = not found,
            0.5 = default branch, 0.8 = feature branch). Float values
            scale the mapping weight by the branch weight.
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
                value = project_result.get(m["artifact_id"], False)
                if isinstance(value, (int, float)) and value > 0:
                    # Float: scale mapping weight by branch weight
                    found_weight += m["weight"] * value
                    artifact_counts[m["artifact_id"]] += 1
                elif value is True:
                    # Bool True: full mapping weight (backwards compat)
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
