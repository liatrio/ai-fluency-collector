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
    """Breakdown correctly describes projects across feature and default branches."""
    results = [
        {"claude-md": FEATURE_BRANCH_WEIGHT},
        {"claude-md": DEFAULT_BRANCH_WEIGHT},
        {"claude-md": 0.0},
    ]
    signals = calculate_scores(results, ARTIFACT_SKILL_MAPPINGS)
    cq = next(s for s in signals if s["skill_id"] == "cq-context")
    breakdown = cq["scoring_context"]["breakdown"]
    assert "1/3 on feature branches" in breakdown
    assert "1/3 on default branch" in breakdown


# ── calculate_member_scores ───────────────────────────────────────────────────


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
