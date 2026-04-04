"""Tests that scoring_context is present and correct on all signal types."""

from __future__ import annotations

from ai_fluency_collector.gitlab_scoring import (
    ARTIFACT_SKILL_MAPPINGS,
    CI_PIPELINE_SKILL_MAPPINGS,
    CI_SKILL_MAPPINGS,
    COVERAGE_SKILL_MAPPINGS,
    MEMBER_SKILL_MAPPINGS,
    MR_COAUTHOR_SKILL_MAPPINGS,
    REVIEW_SKILL_MAPPINGS,
    calculate_coverage_scores,
    calculate_member_scores,
    calculate_mr_coauthor_scores,
    calculate_pipeline_scores,
    calculate_review_scores,
    calculate_scores,
)
from ai_fluency_collector.scanners.gitlab_artifact_scanner import (
    DEFAULT_BRANCH_WEIGHT,
    FEATURE_BRANCH_WEIGHT,
)
from ai_fluency_collector.scanners.gitlab_ci_scanner import CoverageResult, PipelinePassResult

# ── calculate_scores (artifact / CI patterns) ─────────────────────────────────


def test_artifact_scoring_context_present():
    """Each artifact signal includes a scoring_context dict."""
    results = [{"claude-md": FEATURE_BRANCH_WEIGHT}]
    signals = calculate_scores(results, ARTIFACT_SKILL_MAPPINGS)
    for s in signals:
        assert "scoring_context" in s, f"Missing scoring_context on {s['skill_id']}"
        ctx = s["scoring_context"]
        assert "breakdown" in ctx
        assert "max_from_this_signal" in ctx


def test_artifact_scoring_context_feature_branch():
    """Breakdown mentions feature branch when artifact is on a feature branch."""
    results = [{"claude-md": FEATURE_BRANCH_WEIGHT}]
    signals = calculate_scores(results, ARTIFACT_SKILL_MAPPINGS)
    cq = next(s for s in signals if s["skill_id"] == "cq-context")
    assert "feature branch" in cq["scoring_context"]["breakdown"]


def test_artifact_scoring_context_default_branch():
    """Breakdown mentions default branch when artifact is on default branch."""
    results = [{"claude-md": DEFAULT_BRANCH_WEIGHT}]
    signals = calculate_scores(results, ARTIFACT_SKILL_MAPPINGS)
    cq = next(s for s in signals if s["skill_id"] == "cq-context")
    assert "default branch" in cq["scoring_context"]["breakdown"]


def test_artifact_scoring_context_max_from_signal_feature():
    """max_from_this_signal reflects feature branch weight cap (0.8 × mapping)."""
    # cq-context: only claude-md → weight 0.5, total_weight = 0.5
    # max = (0.5 * 0.8) / 0.5 * 100 = 80
    results = [{"claude-md": FEATURE_BRANCH_WEIGHT}]
    signals = calculate_scores(results, ARTIFACT_SKILL_MAPPINGS)
    cq = next(s for s in signals if s["skill_id"] == "cq-context")
    assert cq["scoring_context"]["max_from_this_signal"] == 80


def test_artifact_scoring_context_max_from_signal_default():
    """max_from_this_signal reflects default branch weight cap (0.5 × mapping)."""
    # cq-context: (0.5 * 0.5) / 0.5 * 100 = 50
    results = [{"claude-md": DEFAULT_BRANCH_WEIGHT}]
    signals = calculate_scores(results, ARTIFACT_SKILL_MAPPINGS)
    cq = next(s for s in signals if s["skill_id"] == "cq-context")
    assert cq["scoring_context"]["max_from_this_signal"] == 50


def test_ci_scoring_context_present():
    """CI pattern signals also carry scoring_context."""
    results = [{"ai-code-review": FEATURE_BRANCH_WEIGHT}]
    signals = calculate_scores(results, CI_SKILL_MAPPINGS)
    for s in signals:
        assert "scoring_context" in s


def test_mixed_branches_breakdown():
    """Breakdown uses plain language mentioning both branch types and missing projects."""
    results = [
        {"claude-md": FEATURE_BRANCH_WEIGHT},
        {"claude-md": DEFAULT_BRANCH_WEIGHT},
        {"claude-md": 0.0},
    ]
    signals = calculate_scores(results, ARTIFACT_SKILL_MAPPINGS)
    cq = next(s for s in signals if s["skill_id"] == "cq-context")
    breakdown = cq["scoring_context"]["breakdown"]
    assert "default branch" in breakdown
    assert "feature branch" in breakdown
    assert "2 of 3" in breakdown
    assert "weight:" not in breakdown  # no internal weight values


def test_artifact_missing_signals_partial():
    """missing_signals lists artifact IDs absent from all projects when some are missing."""
    # im-autocomplete maps to claude-md (0.3), cursor (0.3), copilot-instructions (0.3)
    # Only claude-md is present → cursor and copilot-instructions should be in missing_signals
    results = [{"claude-md": FEATURE_BRANCH_WEIGHT}]
    signals = calculate_scores(results, ARTIFACT_SKILL_MAPPINGS)
    autocomplete = next(s for s in signals if s["skill_id"] == "im-autocomplete")
    ctx = autocomplete["scoring_context"]
    assert "missing_signals" in ctx
    assert "cursor" in ctx["missing_signals"]
    assert "copilot-instructions" in ctx["missing_signals"]
    assert "claude-md" not in ctx["missing_signals"]


def test_artifact_missing_signals_omitted_when_all_found():
    """missing_signals is absent when all contributing artifacts are present."""
    # cq-context maps only to claude-md; if claude-md is found, no missing signals
    results = [{"claude-md": DEFAULT_BRANCH_WEIGHT}]
    signals = calculate_scores(results, ARTIFACT_SKILL_MAPPINGS)
    cq = next(s for s in signals if s["skill_id"] == "cq-context")
    assert "missing_signals" not in cq["scoring_context"]


def test_ci_missing_signals():
    """CI signals include missing_signals for CI pattern IDs absent from all projects."""
    # sdlc-security maps to sast-dast (0.4), secret-detection (0.3), dependency-scanning (0.3)
    # Only sast-dast present → missing_signals should list the two absent CI pattern IDs
    results = [{"sast-dast": FEATURE_BRANCH_WEIGHT}]
    signals = calculate_scores(results, CI_SKILL_MAPPINGS)
    sdlc = next(s for s in signals if s["skill_id"] == "sdlc-security")
    ctx = sdlc["scoring_context"]
    assert "missing_signals" in ctx
    assert "secret-detection" in ctx["missing_signals"]
    assert "dependency-scanning" in ctx["missing_signals"]
    assert "sast-dast" not in ctx["missing_signals"]


# ── calculate_member_scores ───────────────────────────────────────────────────


def test_member_missing_signals_partial():
    """missing_signals lists co-author pattern IDs with zero members when some are absent."""
    from ai_fluency_collector.scanners.gitlab_member_scanner import MemberResult

    # im-autocomplete maps to coauthor-copilot (0.5) and coauthor-cursor (0.3)
    # Only coauthor-copilot triggered → coauthor-cursor should appear in missing_signals
    results = [
        MemberResult("alice", repos_discovered=1, ai_coauthor_counts={"coauthor-copilot": 3}),
    ]
    signals = calculate_member_scores(results, MEMBER_SKILL_MAPPINGS)
    autocomplete = next(s for s in signals if s["skill_id"] == "im-autocomplete")
    ctx = autocomplete["scoring_context"]
    assert "missing_signals" in ctx
    assert "coauthor-cursor" in ctx["missing_signals"]
    assert "coauthor-copilot" not in ctx["missing_signals"]


def test_member_missing_signals_omitted_when_all_found():
    """missing_signals is absent when all contributing co-author patterns are found."""
    from ai_fluency_collector.scanners.gitlab_member_scanner import MemberResult

    # im-cli-agent maps only to coauthor-claude; if found, no missing signals
    results = [
        MemberResult("alice", repos_discovered=1, ai_coauthor_counts={"coauthor-claude": 5}),
    ]
    signals = calculate_member_scores(results, MEMBER_SKILL_MAPPINGS)
    cli = next(s for s in signals if s["skill_id"] == "im-cli-agent")
    assert "missing_signals" not in cli["scoring_context"]


def test_member_scoring_context_present():
    """Member activity signals include scoring_context."""
    from ai_fluency_collector.scanners.gitlab_member_scanner import MemberResult

    results = [
        MemberResult("alice", repos_discovered=1, ai_coauthor_counts={"coauthor-claude": 5}),
        MemberResult("bob", repos_discovered=1, ai_coauthor_counts={}),
    ]
    signals = calculate_member_scores(results, MEMBER_SKILL_MAPPINGS)
    for s in signals:
        assert "scoring_context" in s
        assert "breakdown" in s["scoring_context"]
        assert "max_from_this_signal" in s["scoring_context"]


def test_member_scoring_context_max_all_members():
    """max_from_this_signal = 100 when a single artifact maps to the skill with full weight."""
    from ai_fluency_collector.scanners.gitlab_member_scanner import MemberResult

    # im-cli-agent: only coauthor-claude → weight 0.5, total_weight = 0.5 → max = 100
    results = [MemberResult("alice", repos_discovered=1, ai_coauthor_counts={"coauthor-claude": 3})]
    signals = calculate_member_scores(results, MEMBER_SKILL_MAPPINGS)
    cli = next(s for s in signals if s["skill_id"] == "im-cli-agent")
    assert cli["scoring_context"]["max_from_this_signal"] == 100


# ── calculate_review_scores ───────────────────────────────────────────────────


def test_review_scoring_context_present():
    """Review signals include scoring_context with max=100."""
    from ai_fluency_collector.scanners.gitlab_review_scanner import ReviewMetrics

    metrics = ReviewMetrics(
        lgtm_rate=0.2,
        review_comment_depth=None,
        self_review_rate=None,
        total_authored_mrs=5,
        evidence={"lgtm_without_comment": "1/5 MRs had no review comments"},
    )
    signals = calculate_review_scores(metrics, REVIEW_SKILL_MAPPINGS)
    for s in signals:
        assert "scoring_context" in s
        assert s["scoring_context"]["max_from_this_signal"] == 100


# ── calculate_pipeline_scores ─────────────────────────────────────────────────


def test_pipeline_scoring_context_present():
    """Pipeline pass rate signals include scoring_context."""
    results = [PipelinePassResult(pass_count=8, total_count=10)]
    signals = calculate_pipeline_scores(results, CI_PIPELINE_SKILL_MAPPINGS)
    for s in signals:
        assert "scoring_context" in s
        assert s["scoring_context"]["max_from_this_signal"] == 100
        assert "first attempt" in s["scoring_context"]["breakdown"]


# ── calculate_coverage_scores ─────────────────────────────────────────────────


def test_coverage_scoring_context_present():
    """Coverage delta signals include scoring_context."""
    results = [CoverageResult(coverage=75.0)]
    prior = [CoverageResult(coverage=72.0)]
    signals = calculate_coverage_scores(results, prior, COVERAGE_SKILL_MAPPINGS)
    for s in signals:
        assert "scoring_context" in s
        assert s["scoring_context"]["max_from_this_signal"] == 100


# ── calculate_mr_coauthor_scores ──────────────────────────────────────────────


def test_mr_coauthor_scoring_context_present():
    """MR co-author signals include scoring_context."""
    from ai_fluency_collector.scanners.gitlab_review_scanner import ReviewMetrics

    metrics = ReviewMetrics(
        lgtm_rate=None,
        review_comment_depth=None,
        self_review_rate=None,
        total_authored_mrs=10,
        mr_ai_coauthor_rate=0.4,
        mr_agentic_coauthor_rate=0.2,
        evidence={
            "mr_ai_coauthor_rate": "40% of MRs have AI co-author tags",
            "mr_agentic_coauthor_rate": "40% of MRs have AI co-author tags",
        },
    )
    signals = calculate_mr_coauthor_scores(metrics, MR_COAUTHOR_SKILL_MAPPINGS)
    for s in signals:
        assert "scoring_context" in s
        assert s["scoring_context"]["max_from_this_signal"] == 100


# ── GitHub review scores ──────────────────────────────────────────────────────


def test_github_review_scoring_context_present():
    """GitHub review signals include scoring_context."""
    from ai_fluency_collector.github_scoring import (
        GITHUB_REVIEW_SKILL_MAPPINGS,
        calculate_github_review_scores,
    )
    from ai_fluency_collector.scanners.github_review_scanner import GitHubReviewMetrics

    metrics = GitHubReviewMetrics(
        lgtm_rate=0.3,
        review_comment_depth=0.5,
        ai_coauthor_rate=0.4,
        ai_agent_coauthor_rate=0.1,
        self_review_rate=0.2,
        total_authored_prs=20,
        evidence={
            "lgtm_without_comment": "6/20 PRs approved without comments",
            "review_comment_depth": "50% of files had comments",
            "ai_coauthor_rate": "40% of PRs had AI co-author tags",
            "ai_agent_coauthor_rate": "10% of PRs had Claude Code tags",
            "self_review_rate": "20% of PRs had author self-review",
        },
    )
    signals = calculate_github_review_scores(metrics, GITHUB_REVIEW_SKILL_MAPPINGS)
    for s in signals:
        assert "scoring_context" in s
        assert s["scoring_context"]["max_from_this_signal"] == 100


# ── GitHub artifact scores ────────────────────────────────────────────────────


def test_github_artifact_scoring_context_present():
    """GitHub artifact signals include scoring_context with tiered description."""
    from ai_fluency_collector.github_client import GitHubClient
    from ai_fluency_collector.scanners.github_artifact_scanner import GitHubArtifactScanner

    client = GitHubClient("test-token")
    scanner = GitHubArtifactScanner(client)
    # Patch scan_repo to return a known score without making HTTP calls
    scanner.scan_repo = lambda owner, repo: {"ks-patterns": 75}
    signals = scanner.scan_repos(["owner/repo"])

    assert len(signals) == 1
    s = signals[0]
    assert "scoring_context" in s
    ctx = s["scoring_context"]
    assert "breakdown" in ctx
    assert "max_from_this_signal" in ctx
    assert ctx["max_from_this_signal"] == 100
    assert "tiered" in ctx["breakdown"]


# ── Enhanced evidence with project names ─────────────────────────────────────


def test_artifact_evidence_includes_project_names():
    """Evidence includes short project names when project_names are provided."""
    results = [
        {"claude-md": FEATURE_BRANCH_WEIGHT},
        {"claude-md": DEFAULT_BRANCH_WEIGHT},
        {"claude-md": 0.0},
    ]
    project_names = ["group/platform-api", "group/frontend-app", "group/data-pipeline"]
    signals = calculate_scores(results, ARTIFACT_SKILL_MAPPINGS, project_names=project_names)
    cq = next(s for s in signals if s["skill_id"] == "cq-context")
    assert "platform-api" in cq["evidence"]
    assert "frontend-app" in cq["evidence"]
    # Missing project should not appear in evidence (only in breakdown)
    assert "group/" not in cq["evidence"]  # only short names


def test_artifact_per_project_in_scoring_context():
    """scoring_context includes per_project when project_names provided."""
    results = [
        {"claude-md": FEATURE_BRANCH_WEIGHT},
        {"claude-md": 0.0},
    ]
    project_names = ["group/platform-api", "group/data-pipeline"]
    signals = calculate_scores(results, ARTIFACT_SKILL_MAPPINGS, project_names=project_names)
    cq = next(s for s in signals if s["skill_id"] == "cq-context")
    ctx = cq["scoring_context"]
    assert "per_project" in ctx
    assert "group/platform-api" in ctx["per_project"]
    assert ctx["per_project"]["group/platform-api"]["found"] is True
    assert ctx["per_project"]["group/platform-api"]["branch"] == "feature"
    assert "group/data-pipeline" in ctx["per_project"]
    assert ctx["per_project"]["group/data-pipeline"]["found"] is False


def test_artifact_breakdown_includes_project_names():
    """Breakdown mentions specific project names."""
    results = [
        {"claude-md": DEFAULT_BRANCH_WEIGHT},
        {"claude-md": 0.0},
    ]
    project_names = ["group/platform-api", "group/data-pipeline"]
    signals = calculate_scores(results, ARTIFACT_SKILL_MAPPINGS, project_names=project_names)
    cq = next(s for s in signals if s["skill_id"] == "cq-context")
    breakdown = cq["scoring_context"]["breakdown"]
    assert "platform-api" in breakdown
    assert "data-pipeline" in breakdown


def test_artifact_no_per_project_without_names():
    """scoring_context omits per_project when project_names not provided."""
    results = [{"claude-md": FEATURE_BRANCH_WEIGHT}]
    signals = calculate_scores(results, ARTIFACT_SKILL_MAPPINGS)
    cq = next(s for s in signals if s["skill_id"] == "cq-context")
    assert "per_project" not in cq["scoring_context"]


def test_pipeline_evidence_includes_project_names():
    """Pipeline evidence includes project names."""
    results = [
        PipelinePassResult(pass_count=8, total_count=10),
        PipelinePassResult(pass_count=5, total_count=5),
    ]
    signals = calculate_pipeline_scores(
        results,
        CI_PIPELINE_SKILL_MAPPINGS,
        project_names=["group/platform-api", "group/frontend-app"],
    )
    assert len(signals) > 0
    assert "platform-api" in signals[0]["evidence"]
    assert "frontend-app" in signals[0]["evidence"]


def test_pipeline_per_project_in_scoring_context():
    """Pipeline scoring_context includes per_project."""
    results = [
        PipelinePassResult(pass_count=8, total_count=10),
        PipelinePassResult(pass_count=0, total_count=0),
    ]
    signals = calculate_pipeline_scores(
        results,
        CI_PIPELINE_SKILL_MAPPINGS,
        project_names=["group/platform-api", "group/data-pipeline"],
    )
    ctx = signals[0]["scoring_context"]
    assert "per_project" in ctx
    assert "group/platform-api" in ctx["per_project"]
    assert ctx["per_project"]["group/platform-api"]["total"] == 10
    # data-pipeline had 0 pipelines, should not appear in per_project
    assert "group/data-pipeline" not in ctx["per_project"]


def test_coverage_evidence_includes_project_names():
    """Coverage evidence includes project names."""
    results = [CoverageResult(coverage=75.0)]
    signals = calculate_coverage_scores(
        results,
        None,
        COVERAGE_SKILL_MAPPINGS,
        project_names=["group/platform-api"],
    )
    assert "platform-api" in signals[0]["evidence"]


def test_member_evidence_includes_repo_names():
    """Member evidence includes discovered repo names."""
    from ai_fluency_collector.scanners.gitlab_member_scanner import MemberResult

    results = [
        MemberResult(
            "alice",
            repos_discovered=2,
            ai_coauthor_counts={"coauthor-claude": 5},
            repo_coauthor_counts={
                "group/platform-api": {"coauthor-claude": 3},
                "group/frontend-app": {"coauthor-claude": 2},
            },
        ),
    ]
    signals = calculate_member_scores(results, MEMBER_SKILL_MAPPINGS)
    cli = next(s for s in signals if s["skill_id"] == "im-cli-agent")
    assert "platform-api" in cli["evidence"]
    assert "frontend-app" in cli["evidence"]
    ctx = cli["scoring_context"]
    assert "repos_with_activity" in ctx
    assert "total_commits" in ctx
    assert ctx["total_commits"] == 5
    assert ctx["members_with_activity"] == 1
    assert ctx["total_members"] == 1


def test_no_urls_in_evidence():
    """Security: evidence must not contain URLs to client systems."""
    results = [{"claude-md": FEATURE_BRANCH_WEIGHT}]
    project_names = ["group/platform-api"]
    signals = calculate_scores(results, ARTIFACT_SKILL_MAPPINGS, project_names=project_names)
    for s in signals:
        assert "https://" not in s["evidence"]
        assert "http://" not in s["evidence"]
        assert "gitlab.com" not in s["evidence"]
        ctx_str = str(s["scoring_context"])
        assert "https://" not in ctx_str
        assert "http://" not in ctx_str


def test_github_artifact_per_repo_in_scoring_context():
    """GitHub artifact scoring_context includes per_repo."""
    from ai_fluency_collector.github_client import GitHubClient
    from ai_fluency_collector.scanners.github_artifact_scanner import GitHubArtifactScanner

    client = GitHubClient("test-token")
    scanner = GitHubArtifactScanner(client)
    scanner.scan_repo = lambda owner, repo: {"ks-patterns": 75 if repo == "repo1" else 0}
    signals = scanner.scan_repos(["org/repo1", "org/repo2"])

    assert len(signals) == 1
    ctx = signals[0]["scoring_context"]
    assert "per_repo" in ctx
    assert ctx["per_repo"]["org/repo1"]["found"] is True
    assert ctx["per_repo"]["org/repo1"]["score"] == 75
    assert ctx["per_repo"]["org/repo2"]["found"] is False
    assert ctx["per_repo"]["org/repo2"]["score"] == 0


def test_github_artifact_evidence_includes_missing_repos():
    """GitHub artifact evidence includes missing repos."""
    from ai_fluency_collector.github_client import GitHubClient
    from ai_fluency_collector.scanners.github_artifact_scanner import GitHubArtifactScanner

    client = GitHubClient("test-token")
    scanner = GitHubArtifactScanner(client)
    scanner.scan_repo = lambda owner, repo: {"ks-patterns": 75 if repo == "repo1" else 0}
    signals = scanner.scan_repos(["org/repo1", "org/repo2"])

    assert "Missing: org/repo2" in signals[0]["evidence"]
