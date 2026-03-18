from __future__ import annotations

from ai_fluency_collector.scoring import ARTIFACT_SKILL_MAPPINGS, calculate_scores


def test_single_artifact_single_skill():
    """One artifact contributing to one skill produces correct score."""
    mappings = [{"artifact_id": "claude-md", "skill_id": "cq-context", "weight": 1.0}]
    results = [{"claude-md": True}]
    signals = calculate_scores(results, mappings)
    assert len(signals) == 1
    assert signals[0]["skill_id"] == "cq-context"
    assert signals[0]["score"] == 100


def test_multiple_artifacts_same_skill_higher_score():
    """Multiple artifacts mapping to the same skill produce a higher score than one alone."""
    mappings = [
        {"artifact_id": "claude-md", "skill_id": "im-autocomplete", "weight": 0.3},
        {"artifact_id": "cursor", "skill_id": "im-autocomplete", "weight": 0.3},
        {"artifact_id": "copilot-instructions", "skill_id": "im-autocomplete", "weight": 0.3},
    ]

    # Only claude-md present
    one_artifact = [{"claude-md": True, "cursor": False, "copilot-instructions": False}]
    signals_one = calculate_scores(one_artifact, mappings)

    # claude-md + cursor + copilot-instructions present
    all_artifacts = [{"claude-md": True, "cursor": True, "copilot-instructions": True}]
    signals_all = calculate_scores(all_artifacts, mappings)

    score_one = signals_one[0]["score"]
    score_all = signals_all[0]["score"]
    assert score_all > score_one, f"Expected {score_all} > {score_one}"


def test_scoring_averaged_across_projects():
    """Scores are averaged across multiple projects."""
    mappings = [{"artifact_id": "claude-md", "skill_id": "cq-context", "weight": 1.0}]
    # Project 1: has it, Project 2: doesn't
    results = [{"claude-md": True}, {"claude-md": False}]
    signals = calculate_scores(results, mappings)
    assert len(signals) == 1
    assert signals[0]["score"] == 50


def test_evidence_string_with_counts():
    """Evidence string includes artifact name and project count."""
    mappings = [{"artifact_id": "claude-md", "skill_id": "cq-context", "weight": 1.0}]
    results = [{"claude-md": True}, {"claude-md": True}, {"claude-md": False}]
    signals = calculate_scores(results, mappings, artifact_names={"claude-md": "CLAUDE.md"})
    assert "CLAUDE.md found in 2/3 projects" in signals[0]["evidence"]


def test_empty_scan_results():
    """Empty scan results produce no signals."""
    signals = calculate_scores([], ARTIFACT_SKILL_MAPPINGS)
    assert signals == []


def test_no_artifacts_found_produces_no_signals():
    """When no artifacts are found, no signals are emitted."""
    results = [
        {
            "claude-md": False,
            "claude-settings": False,
            "mcp-json": False,
            "prompts-dir": False,
            "cursor": False,
            "copilot-instructions": False,
            "agents": False,
            "aider": False,
        }
    ]
    signals = calculate_scores(results, ARTIFACT_SKILL_MAPPINGS)
    assert signals == []


def test_full_mappings_multi_project():
    """Using real ARTIFACT_SKILL_MAPPINGS: project with more artifacts scores higher."""
    # Project with many artifacts
    rich = {
        "claude-md": True,
        "claude-settings": True,
        "mcp-json": True,
        "prompts-dir": True,
        "cursor": False,
        "copilot-instructions": False,
        "agents": False,
        "aider": False,
    }
    # Project with one artifact
    sparse = {
        "claude-md": True,
        "claude-settings": False,
        "mcp-json": False,
        "prompts-dir": False,
        "cursor": False,
        "copilot-instructions": False,
        "agents": False,
        "aider": False,
    }

    rich_signals = calculate_scores([rich], ARTIFACT_SKILL_MAPPINGS)
    sparse_signals = calculate_scores([sparse], ARTIFACT_SKILL_MAPPINGS)

    rich_total = sum(s["score"] for s in rich_signals)
    sparse_total = sum(s["score"] for s in sparse_signals)
    assert rich_total > sparse_total, f"Expected {rich_total} > {sparse_total}"


def test_score_capped_at_100():
    """Score cannot exceed 100 even with high weights."""
    mappings = [{"artifact_id": "a", "skill_id": "s", "weight": 50.0}]
    results = [{"a": True}]
    signals = calculate_scores(results, mappings)
    assert signals[0]["score"] == 100
