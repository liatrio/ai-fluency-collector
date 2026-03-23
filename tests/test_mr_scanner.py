from __future__ import annotations

import responses

from ai_fluency_collector.gitlab_client import GitLabClient
from ai_fluency_collector.gitlab_scoring import (
    MR_CODING_TIME_SKILL_MAPPINGS,
    MR_SIZE_SKILL_MAPPINGS,
    _coding_time_score,
    _pr_size_score,
    calculate_mr_signals,
    calculate_mr_size_scores,
)
from ai_fluency_collector.scanners.gitlab_mr_scanner import (
    MRScanner,
    _coding_time_hours,
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
    assert "pr_size_median" in metrics.evidence


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

    evidence = metrics.evidence["pr_size_median"]
    assert "PR size (AI-attributed)" in evidence
    assert "250" in evidence
    assert "N=1 MRs" in evidence


# ── _coding_time_hours ────────────────────────────────────────────────────────


def test_coding_time_hours_basic():
    """First commit 4 hours before MR open → 4.0h."""
    mr = {"created_at": "2026-03-17T13:00:00.000Z"}
    commits = [{"created_at": "2026-03-17T09:00:00.000Z"}]
    result = _coding_time_hours(mr, commits)
    assert result == 4.0


def test_coding_time_hours_uses_earliest_commit():
    """Multiple commits — uses earliest, not latest."""
    mr = {"created_at": "2026-03-17T13:00:00.000Z"}
    commits = [
        {"created_at": "2026-03-17T12:00:00.000Z"},  # 1h before MR
        {"created_at": "2026-03-17T09:00:00.000Z"},  # 4h before MR (earliest)
    ]
    result = _coding_time_hours(mr, commits)
    assert result == 4.0


def test_coding_time_hours_empty_commits():
    """No commits → None."""
    mr = {"created_at": "2026-03-17T13:00:00.000Z"}
    result = _coding_time_hours(mr, [])
    assert result is None


def test_coding_time_hours_no_mr_created_at():
    """MR missing created_at → None."""
    commits = [{"created_at": "2026-03-17T09:00:00.000Z"}]
    result = _coding_time_hours({}, commits)
    assert result is None


def test_coding_time_hours_commits_missing_created_at():
    """All commits missing created_at → None."""
    mr = {"created_at": "2026-03-17T13:00:00.000Z"}
    commits = [{"message": "fix"}]
    result = _coding_time_hours(mr, commits)
    assert result is None


def test_coding_time_hours_clock_skew_clamped():
    """Clock skew (commit after MR open) → clamped to 0.0, not negative."""
    mr = {"created_at": "2026-03-17T09:00:00.000Z"}
    commits = [{"created_at": "2026-03-17T10:00:00.000Z"}]  # commit AFTER MR open
    result = _coding_time_hours(mr, commits)
    assert result == 0.0


# ── _coding_time_score rubric ─────────────────────────────────────────────────


def test_coding_time_score_under_2h():
    assert _coding_time_score(0) == 100
    assert _coding_time_score(1) == 100
    assert _coding_time_score(1.9) == 100


def test_coding_time_score_2_to_7h():
    assert _coding_time_score(2) == 85
    assert _coding_time_score(5) == 85
    assert _coding_time_score(7.9) == 85


def test_coding_time_score_8_to_23h():
    assert _coding_time_score(8) == 65
    assert _coding_time_score(12) == 65
    assert _coding_time_score(23.9) == 65


def test_coding_time_score_1_to_3_days():
    assert _coding_time_score(24) == 40
    assert _coding_time_score(48) == 40
    assert _coding_time_score(71.9) == 40


def test_coding_time_score_over_3_days():
    assert _coding_time_score(72) == 15
    assert _coding_time_score(200) == 15


# ── MRScanner coding time integration ────────────────────────────────────────


def _mr_with_timestamps(iid: int, created_at: str, changes_count: object = 150) -> dict:
    return {
        "iid": iid,
        "project_id": PROJECT_ID,
        "changes_count": changes_count,
        "created_at": created_at,
        "author": {"username": "alice"},
    }


@responses.activate
def test_scan_coding_time_computed_for_ai_mr():
    """AI-attributed MR: coding time computed from first commit to MR open."""
    mr = _mr_with_timestamps(1, created_at="2026-03-17T13:00:00.000Z")
    _register_authored_mrs([mr])
    _register_commits(PROJECT_ID, 1, [
        _ai_commit(created_at="2026-03-17T09:00:00.000Z"),  # 4h before MR
    ])

    client = GitLabClient("test-token")
    metrics = MRScanner(client).scan(["alice"], PERIOD)

    assert metrics.coding_time_median == 4.0
    assert metrics.coding_time_mr_count == 1


@responses.activate
def test_scan_coding_time_none_for_zero_commit_mr():
    """AI-attributed MR with no commits → excluded from coding time."""
    mr = _mr_with_timestamps(1, created_at="2026-03-17T13:00:00.000Z", changes_count=100)
    _register_authored_mrs([mr])
    # Register empty commit list (first page empty → done)
    responses.add(responses.GET, f"{BASE}/projects/{PROJECT_ID}/merge_requests/1/commits",
                  json=[], status=200)

    client = GitLabClient("test-token")
    metrics = MRScanner(client).scan(["alice"], PERIOD)

    # No AI attribution → no coding time
    assert metrics.coding_time_median is None
    assert metrics.coding_time_mr_count == 0


@responses.activate
def test_scan_coding_time_evidence_format():
    """Evidence string follows the specified format."""
    mr = _mr_with_timestamps(1, created_at="2026-03-17T13:00:00.000Z")
    _register_authored_mrs([mr])
    _register_commits(PROJECT_ID, 1, [
        _ai_commit(created_at="2026-03-17T09:00:00.000Z"),
    ])

    client = GitLabClient("test-token")
    metrics = MRScanner(client).scan(["alice"], PERIOD)

    evidence = metrics.evidence["coding_time_median"]
    assert "Coding time (AI-attributed)" in evidence
    assert "first commit to MR open" in evidence
    assert "N=1 MRs" in evidence


# ── calculate_mr_signals ──────────────────────────────────────────────────────


def _mr_metrics(
    pr_size_median: float | None,
    coding_time_median: float | None = None,
    count: int = 3,
):
    from ai_fluency_collector.scanners.gitlab_mr_scanner import MRMetrics
    evidence = {}
    if pr_size_median is not None:
        evidence["pr_size_median"] = (
            f"PR size (AI-attributed): {round(pr_size_median)} median lines changed (N={count} MRs)"
        )
    if coding_time_median is not None:
        evidence["coding_time_median"] = (
            f"Coding time (AI-attributed): {coding_time_median}h median "
            f"first commit to MR open (N={count} MRs)"
        )
    return MRMetrics(
        pr_size_median=pr_size_median,
        pr_size_mr_count=count if pr_size_median is not None else 0,
        coding_time_median=coding_time_median,
        coding_time_mr_count=count if coding_time_median is not None else 0,
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


# ── calculate_mr_signals (combined) ───────────────────────────────────────────


def test_mr_signals_emits_both_coding_time_skills():
    """coding_time_median → im-inline-edit AND im-supervised-agent."""
    metrics = _mr_metrics(None, coding_time_median=5.0)
    signals = calculate_mr_signals(metrics, MR_SIZE_SKILL_MAPPINGS, MR_CODING_TIME_SKILL_MAPPINGS)
    skill_ids = {s["skill_id"] for s in signals}
    assert "im-inline-edit" in skill_ids
    assert "im-supervised-agent" in skill_ids


def test_mr_signals_correct_score_for_fast_coding():
    """Median < 2h → score 100 for both coding time skills."""
    metrics = _mr_metrics(None, coding_time_median=1.0)
    signals = calculate_mr_signals(metrics, MR_SIZE_SKILL_MAPPINGS, MR_CODING_TIME_SKILL_MAPPINGS)
    scores = {s["skill_id"]: s["score"] for s in signals}
    assert scores["im-inline-edit"] == 100
    assert scores["im-supervised-agent"] == 100


def test_mr_signals_correct_score_for_slow_coding():
    """Median >= 72h → score 15 for both coding time skills."""
    metrics = _mr_metrics(None, coding_time_median=100.0)
    signals = calculate_mr_signals(metrics, MR_SIZE_SKILL_MAPPINGS, MR_CODING_TIME_SKILL_MAPPINGS)
    scores = {s["skill_id"]: s["score"] for s in signals}
    assert scores["im-inline-edit"] == 15
    assert scores["im-supervised-agent"] == 15


def test_mr_signals_both_present_combines_signals():
    """Both pr_size and coding_time present → all three skill signals emitted."""
    metrics = _mr_metrics(150.0, coding_time_median=5.0)
    signals = calculate_mr_signals(metrics, MR_SIZE_SKILL_MAPPINGS, MR_CODING_TIME_SKILL_MAPPINGS)
    # im-supervised-agent appears from BOTH size and coding time — should appear at least once
    skill_ids = [s["skill_id"] for s in signals]
    assert "im-supervised-agent" in skill_ids
    assert "im-inline-edit" in skill_ids


def test_mr_signals_none_metrics_no_signals():
    """None metrics → empty list."""
    signals = calculate_mr_signals(None, MR_SIZE_SKILL_MAPPINGS, MR_CODING_TIME_SKILL_MAPPINGS)
    assert signals == []


def test_mr_signals_both_none_no_signals():
    """Both medians None → empty list."""
    metrics = _mr_metrics(None, coding_time_median=None, count=0)
    signals = calculate_mr_signals(metrics, MR_SIZE_SKILL_MAPPINGS, MR_CODING_TIME_SKILL_MAPPINGS)
    assert signals == []


def test_mr_signals_coding_time_evidence_propagated():
    """Coding time evidence string appears in signals."""
    metrics = _mr_metrics(None, coding_time_median=3.0)
    signals = calculate_mr_signals(metrics, MR_SIZE_SKILL_MAPPINGS, MR_CODING_TIME_SKILL_MAPPINGS)
    assert any("Coding time" in s["evidence"] for s in signals)
