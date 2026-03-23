from __future__ import annotations

from urllib.parse import quote

import responses

from ai_fluency_collector.gitlab_client import GitLabClient
from ai_fluency_collector.gitlab_scoring import COVERAGE_SKILL_MAPPINGS, calculate_coverage_scores
from ai_fluency_collector.scanners.gitlab_ci_scanner import CIScanner, CoverageResult

BASE = "https://gitlab.com/api/v4"
PROJECT = "my-group/my-project"
ENCODED_PROJECT = quote(PROJECT, safe="")
PERIOD = "2026-W12"


def _jobs_url() -> str:
    return f"{BASE}/projects/{ENCODED_PROJECT}/jobs"


def _register_jobs(jobs: list[dict]) -> None:
    responses.add(responses.GET, _jobs_url(), json=jobs, status=200)
    responses.add(responses.GET, _jobs_url(), json=[], status=200)


def _job(coverage: float | None, name: str = "test") -> dict:
    return {"id": 1, "name": name, "status": "success", "coverage": coverage}


# ── scan_coverage tests ────────────────────────────────────────────────────────


@responses.activate
def test_scan_coverage_returns_mean_of_jobs():
    """Mean coverage is averaged across all jobs with non-null coverage."""
    _register_jobs([_job(70.0), _job(80.0), _job(90.0)])
    client = GitLabClient("test-token")
    scanner = CIScanner(client)
    result = scanner.scan_coverage(PROJECT, PERIOD)
    assert result.coverage == 80.0


@responses.activate
def test_scan_coverage_skips_null_coverage():
    """Jobs with null coverage are excluded from the mean."""
    _register_jobs([_job(60.0), _job(None), _job(80.0)])
    client = GitLabClient("test-token")
    scanner = CIScanner(client)
    result = scanner.scan_coverage(PROJECT, PERIOD)
    assert result.coverage == 70.0


@responses.activate
def test_scan_coverage_no_coverage_jobs():
    """No jobs with coverage data → CoverageResult.coverage is None."""
    _register_jobs([_job(None), _job(None)])
    client = GitLabClient("test-token")
    scanner = CIScanner(client)
    result = scanner.scan_coverage(PROJECT, PERIOD)
    assert result.coverage is None


@responses.activate
def test_scan_coverage_empty_jobs():
    """No successful jobs at all → coverage is None."""
    _register_jobs([])
    client = GitLabClient("test-token")
    scanner = CIScanner(client)
    result = scanner.scan_coverage(PROJECT, PERIOD)
    assert result.coverage is None


# ── calculate_coverage_scores tests ───────────────────────────────────────────


def _result(coverage: float | None) -> CoverageResult:
    return CoverageResult(coverage=coverage)


def test_improving_coverage_scores_above_50():
    """Positive delta → score above 50."""
    current = [_result(77.0)]
    prior = [_result(74.0)]  # delta = +3%
    signals = calculate_coverage_scores(current, prior, COVERAGE_SKILL_MAPPINGS)
    scores = {s["skill_id"]: s["score"] for s in signals}
    assert scores["pm-core"] == 80  # 50 + 3*10 = 80
    assert scores["cq-evaluation"] == 80


def test_declining_coverage_scores_below_50():
    """Negative delta → score below 50."""
    current = [_result(70.0)]
    prior = [_result(74.0)]  # delta = -4%
    signals = calculate_coverage_scores(current, prior, COVERAGE_SKILL_MAPPINGS)
    scores = {s["skill_id"]: s["score"] for s in signals}
    assert scores["pm-core"] == 10  # 50 + (-4)*10 = 10
    assert scores["cq-evaluation"] == 10


def test_no_change_scores_50():
    """Zero delta → score 50."""
    current = [_result(75.0)]
    prior = [_result(75.0)]
    signals = calculate_coverage_scores(current, prior, COVERAGE_SKILL_MAPPINGS)
    scores = {s["skill_id"]: s["score"] for s in signals}
    assert scores["pm-core"] == 50
    assert scores["cq-evaluation"] == 50


def test_no_prior_period_falls_back_to_absolute():
    """No prior data → score is absolute coverage clamped to 0–100."""
    current = [_result(74.0)]
    signals = calculate_coverage_scores(current, None, COVERAGE_SKILL_MAPPINGS)
    scores = {s["skill_id"]: s["score"] for s in signals}
    assert scores["pm-core"] == 74
    assert scores["cq-evaluation"] == 74


def test_no_coverage_jobs_returns_empty():
    """All projects with no coverage data → no signals."""
    current = [_result(None), _result(None)]
    signals = calculate_coverage_scores(current, None, COVERAGE_SKILL_MAPPINGS)
    assert signals == []


def test_delta_clamped_at_100():
    """Very large positive delta is clamped to 100."""
    current = [_result(90.0)]
    prior = [_result(75.0)]  # delta = +15% → 50 + 150 = 200 → clamped to 100
    signals = calculate_coverage_scores(current, prior, COVERAGE_SKILL_MAPPINGS)
    assert signals[0]["score"] == 100


def test_delta_clamped_at_0():
    """Very large negative delta is clamped to 0 → no signals emitted."""
    current = [_result(60.0)]
    prior = [_result(75.0)]  # delta = -15% → 50 - 150 = -100 → clamped to 0
    signals = calculate_coverage_scores(current, prior, COVERAGE_SKILL_MAPPINGS)
    assert signals == []


def test_multi_project_mean_coverage():
    """Coverage delta is the mean across all projects with data."""
    # project A: 80% now, 70% before → delta +10
    # project B: 60% now, 70% before → delta -10
    # mean delta = 0 → score 50
    current = [_result(80.0), _result(60.0)]
    prior = [_result(70.0), _result(70.0)]
    signals = calculate_coverage_scores(current, prior, COVERAGE_SKILL_MAPPINGS)
    assert signals[0]["score"] == 50


def test_projects_without_prior_data_excluded_from_prior_mean():
    """Projects with no prior coverage data are excluded from the prior mean."""
    current = [_result(80.0), _result(70.0)]
    prior = [_result(70.0), _result(None)]  # second project excluded from prior
    # current mean = 75, prior mean = 70 (only first project), delta = +5
    signals = calculate_coverage_scores(current, prior, COVERAGE_SKILL_MAPPINGS)
    assert signals[0]["score"] == 100  # 50 + 5*10 = 100


def test_evidence_includes_coverage_and_delta():
    """Evidence string contains absolute coverage, delta, and project count."""
    current = [_result(77.0)]
    prior = [_result(74.0)]
    signals = calculate_coverage_scores(current, prior, COVERAGE_SKILL_MAPPINGS)
    evidence = signals[0]["evidence"]
    assert "77%" in evidence
    assert "+3.0%" in evidence
    assert "N=1" in evidence


def test_evidence_no_prior_omits_delta():
    """Without prior data, evidence string has no delta."""
    current = [_result(74.0)]
    signals = calculate_coverage_scores(current, None, COVERAGE_SKILL_MAPPINGS)
    evidence = signals[0]["evidence"]
    assert "74%" in evidence
    assert "prior" not in evidence
