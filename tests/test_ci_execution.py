from __future__ import annotations

from urllib.parse import quote

import responses

from ai_fluency_collector.gitlab_client import GitLabClient
from ai_fluency_collector.gitlab_scoring import (
    CI_EXECUTION_SKILL_MAPPINGS,
    calculate_ci_execution_scores,
)
from ai_fluency_collector.scanners.gitlab_ci_scanner import CIExecutionResult, CIScanner

BASE = "https://gitlab.com/api/v4"
PROJECT = "my-group/my-project"
ENCODED_PROJECT = quote(PROJECT, safe="")
PERIOD = "2026-W12"  # 2026-03-16 to 2026-03-22


def _pipelines_url() -> str:
    return f"{BASE}/projects/{ENCODED_PROJECT}/pipelines"


def _jobs_url(pipeline_id: int) -> str:
    return f"{BASE}/projects/{ENCODED_PROJECT}/pipelines/{pipeline_id}/jobs"


def _make_pipeline(id: int, status: str = "success") -> dict:
    return {"id": id, "sha": f"sha{id}", "status": status, "created_at": "2026-03-17T10:00:00Z"}


def _make_job(name: str, status: str = "success") -> dict:
    return {"name": name, "stage": "test", "status": status, "duration": 60}


# ── scan_ci_execution tests ──────────────────────────────────────────────────


@responses.activate
def test_execution_all_patterns_running_and_passing():
    """Configured SAST and AI review jobs run and pass in all pipelines."""
    pipelines = [_make_pipeline(1), _make_pipeline(2)]
    responses.add(responses.GET, _pipelines_url(), json=pipelines, status=200)
    responses.add(responses.GET, _pipelines_url(), json=[], status=200)

    for pid in [1, 2]:
        jobs = [
            _make_job("sast-scan", "success"),
            _make_job("ai-review-check", "success"),
            _make_job("build", "success"),
        ]
        responses.add(responses.GET, _jobs_url(pid), json=jobs, status=200)
        responses.add(responses.GET, _jobs_url(pid), json=[], status=200)

    client = GitLabClient("test-token")
    scanner = CIScanner(client)
    configured = {"sast-dast": 0.8, "ai-code-review": 0.5, "secret-detection": 0.0}
    result = scanner.scan_ci_execution(PROJECT, PERIOD, configured)

    # SAST ran and passed in both pipelines
    assert result.pattern_stats["sast-dast"] == (2, 2, 2)
    # AI review ran and passed in both pipelines
    assert result.pattern_stats["ai-code-review"] == (2, 2, 2)
    # secret-detection was not configured (weight 0), so not checked
    assert "secret-detection" not in result.pattern_stats


@responses.activate
def test_execution_configured_but_not_running():
    """SAST configured in YAML but no matching jobs found in pipelines."""
    pipelines = [_make_pipeline(1)]
    responses.add(responses.GET, _pipelines_url(), json=pipelines, status=200)
    responses.add(responses.GET, _pipelines_url(), json=[], status=200)

    jobs = [_make_job("build", "success"), _make_job("test", "success")]
    responses.add(responses.GET, _jobs_url(1), json=jobs, status=200)
    responses.add(responses.GET, _jobs_url(1), json=[], status=200)

    client = GitLabClient("test-token")
    scanner = CIScanner(client)
    configured = {"sast-dast": 0.5}
    result = scanner.scan_ci_execution(PROJECT, PERIOD, configured)

    assert result.pattern_stats["sast-dast"] == (0, 0, 1)


@responses.activate
def test_execution_running_but_failing():
    """AI review job runs but fails in both pipelines."""
    pipelines = [_make_pipeline(1), _make_pipeline(2)]
    responses.add(responses.GET, _pipelines_url(), json=pipelines, status=200)
    responses.add(responses.GET, _pipelines_url(), json=[], status=200)

    for pid in [1, 2]:
        jobs = [_make_job("ai-review", "failed")]
        responses.add(responses.GET, _jobs_url(pid), json=jobs, status=200)
        responses.add(responses.GET, _jobs_url(pid), json=[], status=200)

    client = GitLabClient("test-token")
    scanner = CIScanner(client)
    configured = {"ai-code-review": 0.8}
    result = scanner.scan_ci_execution(PROJECT, PERIOD, configured)

    # Ran in 2 pipelines, passed in 0
    assert result.pattern_stats["ai-code-review"] == (0, 2, 2)


@responses.activate
def test_execution_no_pipelines_in_period():
    """No pipelines found for the period → empty stats."""
    responses.add(responses.GET, _pipelines_url(), json=[], status=200)

    client = GitLabClient("test-token")
    scanner = CIScanner(client)
    configured = {"sast-dast": 0.8}
    result = scanner.scan_ci_execution(PROJECT, PERIOD, configured)

    assert result.pattern_stats == {}


@responses.activate
def test_execution_no_configured_patterns():
    """No patterns configured (all weights 0) → empty stats, no API calls."""
    client = GitLabClient("test-token")
    scanner = CIScanner(client)
    configured = {"sast-dast": 0.0, "ai-code-review": 0.0}
    result = scanner.scan_ci_execution(PROJECT, PERIOD, configured)

    assert result.pattern_stats == {}


@responses.activate
def test_execution_mixed_results():
    """SAST passes in 1 of 2 pipelines, AI review runs but fails in both."""
    pipelines = [_make_pipeline(1), _make_pipeline(2)]
    responses.add(responses.GET, _pipelines_url(), json=pipelines, status=200)
    responses.add(responses.GET, _pipelines_url(), json=[], status=200)

    # Pipeline 1: SAST passes, AI review fails
    jobs1 = [_make_job("sast-check", "success"), _make_job("duo-review", "failed")]
    responses.add(responses.GET, _jobs_url(2), json=jobs1, status=200)
    responses.add(responses.GET, _jobs_url(2), json=[], status=200)

    # Pipeline 2: SAST fails, AI review fails
    jobs2 = [_make_job("sast-check", "failed"), _make_job("duo-review", "failed")]
    responses.add(responses.GET, _jobs_url(1), json=jobs2, status=200)
    responses.add(responses.GET, _jobs_url(1), json=[], status=200)

    client = GitLabClient("test-token")
    scanner = CIScanner(client)
    configured = {"sast-dast": 0.8, "ai-code-review": 0.5}
    result = scanner.scan_ci_execution(PROJECT, PERIOD, configured)

    assert result.pattern_stats["sast-dast"] == (1, 2, 2)
    assert result.pattern_stats["ai-code-review"] == (0, 2, 2)


# ── calculate_ci_execution_scores tests ──────────────────────────────────────


def test_scoring_all_passing():
    """All patterns running and passing → high scores."""
    results = [
        CIExecutionResult(
            pattern_stats={
                "sast-dast": (5, 5, 5),
                "ai-code-review": (5, 5, 5),
            }
        )
    ]
    signals = calculate_ci_execution_scores(results, CI_EXECUTION_SKILL_MAPPINGS)

    skill_scores = {s["skill_id"]: s["score"] for s in signals}
    assert skill_scores["sdlc-security"] == 100
    assert skill_scores["tg-security-gates"] == 100
    assert skill_scores["tg-code-review"] == 100


def test_scoring_configured_but_not_running():
    """Pattern configured but never ran → score 0, no signal emitted."""
    results = [CIExecutionResult(pattern_stats={"sast-dast": (0, 0, 5)})]
    signals = calculate_ci_execution_scores(results, CI_EXECUTION_SKILL_MAPPINGS)

    assert signals == []


def test_scoring_running_but_failing():
    """Pattern runs but always fails → score 0."""
    results = [CIExecutionResult(pattern_stats={"ai-code-review": (0, 5, 5)})]
    signals = calculate_ci_execution_scores(results, CI_EXECUTION_SKILL_MAPPINGS)

    assert signals == []


def test_scoring_partial_execution():
    """Pattern runs in 3/5 pipelines, passes 2/3 → execution_rate * pass_rate."""
    results = [CIExecutionResult(pattern_stats={"sast-dast": (2, 3, 5)})]
    signals = calculate_ci_execution_scores(results, CI_EXECUTION_SKILL_MAPPINGS)

    # execution_rate = 3/5 = 0.6, pass_rate = 2/3 = 0.667
    # combined = 0.6 * 0.667 = 0.4 → score = 40
    skill_scores = {s["skill_id"]: s["score"] for s in signals}
    assert skill_scores["sdlc-security"] == 40
    assert skill_scores["tg-security-gates"] == 40


def test_scoring_aggregates_across_projects():
    """Stats from multiple projects are aggregated."""
    results = [
        CIExecutionResult(pattern_stats={"sast-dast": (3, 3, 3)}),
        CIExecutionResult(pattern_stats={"sast-dast": (2, 5, 5)}),
    ]
    signals = calculate_ci_execution_scores(results, CI_EXECUTION_SKILL_MAPPINGS)

    # Aggregated: passed=5, ran=8, checked=8
    # execution_rate = 8/8 = 1.0, pass_rate = 5/8 = 0.625
    # combined = 0.625 → score = round(62.5) = 62
    skill_scores = {s["skill_id"]: s["score"] for s in signals}
    assert skill_scores["sdlc-security"] == 62


def test_scoring_empty_results():
    """No execution results → no signals."""
    assert calculate_ci_execution_scores([], CI_EXECUTION_SKILL_MAPPINGS) == []


def test_scoring_evidence_for_not_running():
    """Evidence text describes configured-but-not-running state."""
    results = [CIExecutionResult(pattern_stats={"sast-dast": (0, 0, 5)})]
    signals = calculate_ci_execution_scores(results, CI_EXECUTION_SKILL_MAPPINGS)
    # Score is 0, so no signals emitted
    assert signals == []


def test_scoring_evidence_for_running():
    """Evidence text includes run/pass counts."""
    results = [CIExecutionResult(pattern_stats={"ai-code-review": (3, 5, 5)})]
    signals = calculate_ci_execution_scores(results, CI_EXECUTION_SKILL_MAPPINGS)

    assert len(signals) == 1
    assert "ran in 5/5 pipelines" in signals[0]["evidence"]
    assert "3/5 passed" in signals[0]["evidence"]


def test_scoring_best_score_per_skill():
    """When multiple patterns map to the same skill, keep the best score."""
    results = [
        CIExecutionResult(
            pattern_stats={
                "sast-dast": (5, 5, 5),  # sdlc-security → 100
                "secret-detection": (1, 5, 5),  # sdlc-security → 20
            }
        )
    ]
    signals = calculate_ci_execution_scores(results, CI_EXECUTION_SKILL_MAPPINGS)

    sdlc_signals = [s for s in signals if s["skill_id"] == "sdlc-security"]
    assert len(sdlc_signals) == 1
    assert sdlc_signals[0]["score"] == 100
