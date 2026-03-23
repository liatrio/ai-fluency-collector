from __future__ import annotations

from urllib.parse import quote

import responses

from ai_fluency_collector.gitlab_client import GitLabClient
from ai_fluency_collector.gitlab_scoring import (
    CI_PIPELINE_SKILL_MAPPINGS,
    calculate_pipeline_scores,
)
from ai_fluency_collector.scanners.gitlab_ci_scanner import CIScanner, PipelinePassResult

BASE = "https://gitlab.com/api/v4"
PROJECT = "my-group/my-project"
ENCODED_PROJECT = quote(PROJECT, safe="")
PERIOD = "2026-W12"  # 2026-03-16 to 2026-03-22


def _pipelines_url() -> str:
    return f"{BASE}/projects/{ENCODED_PROJECT}/pipelines"


def _register_pipelines(pipelines: list[dict], page2: list[dict] | None = None) -> None:
    responses.add(responses.GET, _pipelines_url(), json=pipelines, status=200)
    responses.add(responses.GET, _pipelines_url(), json=page2 or [], status=200)


def _make_pipeline(id: int, sha: str, status: str) -> dict:
    return {"id": id, "sha": sha, "status": status, "created_at": "2026-03-17T10:00:00Z"}


# ── scan_pipeline_pass_rate tests ──────────────────────────────────────────────


@responses.activate
def test_high_pass_rate():
    """4 of 5 unique SHAs pass on first attempt → pass_count=4, total=5."""
    pipelines = [
        _make_pipeline(1, "aaa", "success"),
        _make_pipeline(2, "bbb", "success"),
        _make_pipeline(3, "ccc", "success"),
        _make_pipeline(4, "ddd", "success"),
        _make_pipeline(5, "eee", "failed"),
    ]
    _register_pipelines(pipelines)
    client = GitLabClient("test-token")
    scanner = CIScanner(client)
    result = scanner.scan_pipeline_pass_rate(PROJECT, PERIOD)
    assert result.pass_count == 4
    assert result.total_count == 5


@responses.activate
def test_low_pass_rate():
    """1 of 5 unique SHAs pass on first attempt → pass_count=1, total=5."""
    pipelines = [
        _make_pipeline(1, "aaa", "failed"),
        _make_pipeline(2, "bbb", "failed"),
        _make_pipeline(3, "ccc", "failed"),
        _make_pipeline(4, "ddd", "failed"),
        _make_pipeline(5, "eee", "success"),
    ]
    _register_pipelines(pipelines)
    client = GitLabClient("test-token")
    scanner = CIScanner(client)
    result = scanner.scan_pipeline_pass_rate(PROJECT, PERIOD)
    assert result.pass_count == 1
    assert result.total_count == 5


@responses.activate
def test_no_pipelines_in_period():
    """No pipelines in period → total_count=0, pass_count=0."""
    _register_pipelines([])
    client = GitLabClient("test-token")
    scanner = CIScanner(client)
    result = scanner.scan_pipeline_pass_rate(PROJECT, PERIOD)
    assert result.pass_count == 0
    assert result.total_count == 0


@responses.activate
def test_groups_by_sha_first_attempt_counts():
    """Same SHA with 2 pipelines: first (id=10) failed, retry (id=20) succeeded → counts as fail."""
    pipelines = [
        _make_pipeline(20, "abc123", "success"),  # retry
        _make_pipeline(10, "abc123", "failed"),  # first attempt
    ]
    _register_pipelines(pipelines)
    client = GitLabClient("test-token")
    scanner = CIScanner(client)
    result = scanner.scan_pipeline_pass_rate(PROJECT, PERIOD)
    assert result.total_count == 1
    assert result.pass_count == 0  # first attempt failed


@responses.activate
def test_all_pass():
    """All unique SHAs pass → pass_count == total_count."""
    pipelines = [
        _make_pipeline(1, "sha1", "success"),
        _make_pipeline(2, "sha2", "success"),
        _make_pipeline(3, "sha3", "success"),
    ]
    _register_pipelines(pipelines)
    client = GitLabClient("test-token")
    scanner = CIScanner(client)
    result = scanner.scan_pipeline_pass_rate(PROJECT, PERIOD)
    assert result.pass_count == 3
    assert result.total_count == 3


# ── calculate_pipeline_scores tests ───────────────────────────────────────────


def test_calculate_pipeline_scores_high_pass_rate():
    """78% pass rate → score 78 for both pm-core and tg-code-review."""
    results = [PipelinePassResult(pass_count=47, total_count=60)]
    # 47/60 ≈ 0.783 → round(78.3) = 78
    signals = calculate_pipeline_scores(results, CI_PIPELINE_SKILL_MAPPINGS)
    skill_scores = {s["skill_id"]: s["score"] for s in signals}
    assert "pm-core" in skill_scores
    assert "tg-code-review" in skill_scores
    assert skill_scores["pm-core"] == round(47 / 60 * 100)
    assert skill_scores["tg-code-review"] == round(47 / 60 * 100)


def test_calculate_pipeline_scores_evidence_format():
    """Evidence string includes percentage and count."""
    results = [PipelinePassResult(pass_count=47, total_count=60)]
    signals = calculate_pipeline_scores(results, CI_PIPELINE_SKILL_MAPPINGS)
    evidence = signals[0]["evidence"]
    assert "47" in evidence or "78" in evidence  # either count or pct
    assert "60" in evidence  # total pipeline count
    assert "first attempt" in evidence


def test_calculate_pipeline_scores_no_pipelines():
    """Projects with no pipelines → empty signals."""
    results = [PipelinePassResult(pass_count=0, total_count=0)]
    signals = calculate_pipeline_scores(results, CI_PIPELINE_SKILL_MAPPINGS)
    assert signals == []


def test_calculate_pipeline_scores_multi_project_mean():
    """2 projects: 100% and 0% → mean 50% → score 50."""
    results = [
        PipelinePassResult(pass_count=5, total_count=5),
        PipelinePassResult(pass_count=0, total_count=5),
    ]
    signals = calculate_pipeline_scores(results, CI_PIPELINE_SKILL_MAPPINGS)
    skill_scores = {s["skill_id"]: s["score"] for s in signals}
    assert skill_scores["pm-core"] == 50
    assert skill_scores["tg-code-review"] == 50


def test_calculate_pipeline_scores_excludes_empty_projects():
    """Projects with no pipelines are excluded from the mean."""
    results = [
        PipelinePassResult(pass_count=8, total_count=10),  # 80%
        PipelinePassResult(pass_count=0, total_count=0),  # no data — excluded
    ]
    signals = calculate_pipeline_scores(results, CI_PIPELINE_SKILL_MAPPINGS)
    skill_scores = {s["skill_id"]: s["score"] for s in signals}
    # Mean of just 80% → score 80
    assert skill_scores["pm-core"] == 80


def test_calculate_pipeline_scores_zero_pass_rate():
    """0% pass rate → score 0, no signals emitted."""
    results = [PipelinePassResult(pass_count=0, total_count=10)]
    signals = calculate_pipeline_scores(results, CI_PIPELINE_SKILL_MAPPINGS)
    assert signals == []
