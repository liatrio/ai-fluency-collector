from __future__ import annotations

import responses

from ai_fluency_collector.gitlab_client import GitLabClient
from ai_fluency_collector.gitlab_scoring import (
    MR_SIZE_SKILL_MAPPINGS,
    _pr_size_score,
    calculate_mr_size_scores,
)
from ai_fluency_collector.scanners.gitlab_mr_scanner import (
    MRScanner,
    _parse_changes_count,
)

BASE = "https://gitlab.com/api/v4"
MR_SEARCH = f"{BASE}/merge_requests"
PERIOD = "2026-W12"
PROJECT_ID = 42


# ── helpers ───────────────────────────────────────────────────────────────────


def _mr(iid: int, changes_count: object = 150, project_id: int = PROJECT_ID) -> dict:
    return {
        "iid": iid,
        "project_id": project_id,
        "changes_count": changes_count,
        "author": {"username": "alice"},
    }


def _commits_url(project_id: int, mr_iid: int) -> str:
    return f"{BASE}/projects/{project_id}/merge_requests/{mr_iid}/commits"


def _commit(message: str, created_at: str = "2026-03-17T09:00:00.000Z") -> dict:
    return {
        "id": "abc123",
        "message": message,
        "title": message.splitlines()[0],
        "created_at": created_at,
    }


def _ai_commit(created_at: str = "2026-03-17T09:00:00.000Z") -> dict:
    return _commit("fix thing\n\nCo-Authored-By: Claude <claude@anthropic.com>", created_at)


def _plain_commit(created_at: str = "2026-03-17T09:00:00.000Z") -> dict:
    return _commit("chore: update deps", created_at)


def _register_authored_mrs(mrs: list[dict]) -> None:
    responses.add(responses.GET, MR_SEARCH, json=mrs, status=200)
    responses.add(responses.GET, MR_SEARCH, json=[], status=200)


def _register_commits(project_id: int, mr_iid: int, commits: list[dict]) -> None:
    responses.add(responses.GET, _commits_url(project_id, mr_iid), json=commits, status=200)
    responses.add(responses.GET, _commits_url(project_id, mr_iid), json=[], status=200)


# ── _parse_changes_count ──────────────────────────────────────────────────────


def test_parse_changes_count_int():
    assert _parse_changes_count(42) == 42


def test_parse_changes_count_string_number():
    assert _parse_changes_count("150") == 150


def test_parse_changes_count_none():
    assert _parse_changes_count(None) is None


def test_parse_changes_count_too_many_changes():
    assert _parse_changes_count("too many changes") is None


def test_parse_changes_count_empty_string():
    assert _parse_changes_count("") is None


def test_parse_changes_count_float_string():
    # GitLab shouldn't return floats but be defensive
    assert _parse_changes_count("3.5") is None


# ── _pr_size_score rubric ─────────────────────────────────────────────────────


def test_pr_size_score_under_200():
    assert _pr_size_score(0) == 100
    assert _pr_size_score(100) == 100
    assert _pr_size_score(199) == 100


def test_pr_size_score_200_to_399():
    assert _pr_size_score(200) == 80
    assert _pr_size_score(300) == 80
    assert _pr_size_score(399) == 80


def test_pr_size_score_400_to_799():
    assert _pr_size_score(400) == 60
    assert _pr_size_score(600) == 60
    assert _pr_size_score(799) == 60


def test_pr_size_score_800_to_1499():
    assert _pr_size_score(800) == 35
    assert _pr_size_score(1200) == 35
    assert _pr_size_score(1499) == 35


def test_pr_size_score_1500_and_above():
    assert _pr_size_score(1500) == 10
    assert _pr_size_score(5000) == 10


# ── MRScanner.scan ────────────────────────────────────────────────────────────


@responses.activate
def test_scan_ai_attributed_mr_emits_pr_size():
    """AI-attributed MR → pr_size_median set from changes_count."""
    _register_authored_mrs([_mr(1, changes_count=200)])
    _register_commits(PROJECT_ID, 1, [_ai_commit()])

    client = GitLabClient("test-token")
    metrics = MRScanner(client).scan(["alice"], PERIOD)

    assert metrics.pr_size_median == 200
    assert metrics.pr_size_mr_count == 1
    assert "pr_size" in metrics.evidence


@responses.activate
def test_scan_non_ai_mr_excluded():
    """MR with no AI co-author tags → pr_size_median is None."""
    _register_authored_mrs([_mr(1, changes_count=300)])
    _register_commits(PROJECT_ID, 1, [_plain_commit()])

    client = GitLabClient("test-token")
    metrics = MRScanner(client).scan(["alice"], PERIOD)

    assert metrics.pr_size_median is None
    assert metrics.pr_size_mr_count == 0


@responses.activate
def test_scan_no_mrs_in_period():
    """No authored MRs → pr_size_median is None."""
    _register_authored_mrs([])

    client = GitLabClient("test-token")
    metrics = MRScanner(client).scan(["alice"], PERIOD)

    assert metrics.pr_size_median is None
    assert metrics.pr_size_mr_count == 0


@responses.activate
def test_scan_ignores_mr_with_invalid_changes_count():
    """MR with 'too many changes' in changes_count is excluded from median."""
    _register_authored_mrs([
        _mr(1, changes_count="too many changes"),
        _mr(2, changes_count=100),
    ])
    _register_commits(PROJECT_ID, 1, [_ai_commit()])
    _register_commits(PROJECT_ID, 2, [_ai_commit()])

    client = GitLabClient("test-token")
    metrics = MRScanner(client).scan(["alice"], PERIOD)

    # Only MR 2 contributes
    assert metrics.pr_size_median == 100
    assert metrics.pr_size_mr_count == 1


@responses.activate
def test_scan_ignores_mr_with_none_changes_count():
    """MR with None changes_count is excluded from median."""
    _register_authored_mrs([_mr(1, changes_count=None)])
    _register_commits(PROJECT_ID, 1, [_ai_commit()])

    client = GitLabClient("test-token")
    metrics = MRScanner(client).scan(["alice"], PERIOD)

    assert metrics.pr_size_median is None
    assert metrics.pr_size_mr_count == 0


@responses.activate
def test_scan_median_of_multiple_mrs():
    """Median is computed correctly across multiple AI-attributed MRs."""
    _register_authored_mrs([
        _mr(1, changes_count=100),
        _mr(2, changes_count=300),
        _mr(3, changes_count=500),
    ])
    _register_commits(PROJECT_ID, 1, [_ai_commit()])
    _register_commits(PROJECT_ID, 2, [_ai_commit()])
    _register_commits(PROJECT_ID, 3, [_ai_commit()])

    client = GitLabClient("test-token")
    metrics = MRScanner(client).scan(["alice"], PERIOD)

    assert metrics.pr_size_median == 300
    assert metrics.pr_size_mr_count == 3


@responses.activate
def test_scan_mixed_ai_and_non_ai_mrs():
    """Only AI-attributed MRs contribute to the median."""
    _register_authored_mrs([
        _mr(1, changes_count=100),   # AI-attributed
        _mr(2, changes_count=9000),  # NOT AI-attributed
    ])
    _register_commits(PROJECT_ID, 1, [_ai_commit()])
    _register_commits(PROJECT_ID, 2, [_plain_commit()])

    client = GitLabClient("test-token")
    metrics = MRScanner(client).scan(["alice"], PERIOD)

    # Large non-AI MR should not pollute the median
    assert metrics.pr_size_median == 100
    assert metrics.pr_size_mr_count == 1


@responses.activate
def test_scan_evidence_format():
    """Evidence string follows the specified format."""
    _register_authored_mrs([_mr(1, changes_count=250)])
    _register_commits(PROJECT_ID, 1, [_ai_commit()])

    client = GitLabClient("test-token")
    metrics = MRScanner(client).scan(["alice"], PERIOD)

    evidence = metrics.evidence["pr_size"]
    assert "PR size (AI-attributed)" in evidence
    assert "250" in evidence
    assert "N=1 MRs" in evidence


# ── calculate_mr_size_scores ──────────────────────────────────────────────────


def _mr_metrics(pr_size_median: float | None, count: int = 3):
    from ai_fluency_collector.scanners.gitlab_mr_scanner import MRMetrics
    evidence = {}
    if pr_size_median is not None:
        evidence["pr_size_median"] = (
            f"PR size (AI-attributed): {round(pr_size_median)} median lines changed (N={count} MRs)"
        )
    return MRMetrics(
        pr_size_median=pr_size_median,
        pr_size_mr_count=count,
        evidence=evidence,
    )


def test_calculate_scores_emits_im_supervised_agent():
    """pr_size_median → im-supervised-agent signal."""
    metrics = _mr_metrics(150.0)
    signals = calculate_mr_size_scores(metrics, MR_SIZE_SKILL_MAPPINGS)
    skill_ids = {s["skill_id"] for s in signals}
    assert "im-supervised-agent" in skill_ids


def test_calculate_scores_correct_score_for_small_pr():
    """Median < 200 lines → score 100."""
    metrics = _mr_metrics(150.0)
    signals = calculate_mr_size_scores(metrics, MR_SIZE_SKILL_MAPPINGS)
    scores = {s["skill_id"]: s["score"] for s in signals}
    assert scores["im-supervised-agent"] == 100


def test_calculate_scores_correct_score_for_large_pr():
    """Median >= 1500 lines → score 10."""
    metrics = _mr_metrics(2000.0)
    signals = calculate_mr_size_scores(metrics, MR_SIZE_SKILL_MAPPINGS)
    scores = {s["skill_id"]: s["score"] for s in signals}
    assert scores["im-supervised-agent"] == 10


def test_calculate_scores_none_median_no_signals():
    """None pr_size_median → no signals emitted."""
    metrics = _mr_metrics(None, count=0)
    signals = calculate_mr_size_scores(metrics, MR_SIZE_SKILL_MAPPINGS)
    assert signals == []


def test_calculate_scores_none_metrics_no_signals():
    """None metrics object → no signals."""
    signals = calculate_mr_size_scores(None, MR_SIZE_SKILL_MAPPINGS)
    assert signals == []


def test_calculate_scores_evidence_in_signal():
    """Evidence string is propagated to signal."""
    metrics = _mr_metrics(300.0)
    signals = calculate_mr_size_scores(metrics, MR_SIZE_SKILL_MAPPINGS)
    assert any("PR size" in s["evidence"] for s in signals)
