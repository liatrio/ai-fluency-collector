from __future__ import annotations

import pytest
import responses

from ai_fluency_collector.gitlab_client import GitLabClient
from ai_fluency_collector.scanners.review_scanner import ReviewScanner
from ai_fluency_collector.scoring import MR_COAUTHOR_SKILL_MAPPINGS, calculate_mr_coauthor_scores

BASE = "https://gitlab.com/api/v4"
MR_SEARCH = f"{BASE}/merge_requests"
PERIOD = "2026-W12"
PROJECT_ID = 42


def _mr(iid: int, project_id: int = PROJECT_ID) -> dict:
    return {"iid": iid, "project_id": project_id, "author": {"username": "alice"}}


def _commits_url(project_id: int, mr_iid: int) -> str:
    return f"{BASE}/projects/{project_id}/merge_requests/{mr_iid}/commits"


def _notes_url(project_id: int, mr_iid: int) -> str:
    return f"{BASE}/projects/{project_id}/merge_requests/{mr_iid}/notes"


def _diffs_url(project_id: int, mr_iid: int) -> str:
    return f"{BASE}/projects/{project_id}/merge_requests/{mr_iid}/diffs"


def _discussions_url(project_id: int, mr_iid: int) -> str:
    return f"{BASE}/projects/{project_id}/merge_requests/{mr_iid}/discussions"


def _register_authored_mrs(mrs: list[dict]) -> None:
    responses.add(responses.GET, MR_SEARCH, json=mrs, status=200)
    responses.add(responses.GET, MR_SEARCH, json=[], status=200)


def _register_no_reviewed_mrs() -> None:
    responses.add(responses.GET, MR_SEARCH, json=[], status=200)


def _register_commits(project_id: int, mr_iid: int, commits: list[dict]) -> None:
    responses.add(responses.GET, _commits_url(project_id, mr_iid), json=commits, status=200)
    responses.add(responses.GET, _commits_url(project_id, mr_iid), json=[], status=200)


def _register_notes(project_id: int, mr_iid: int) -> None:
    responses.add(responses.GET, _notes_url(project_id, mr_iid), json=[], status=200)
    responses.add(responses.GET, _notes_url(project_id, mr_iid), json=[], status=200)


def _commit(message: str) -> dict:
    return {"id": "abc123", "message": message, "title": message.splitlines()[0]}


# ── ReviewScanner co-author detection ─────────────────────────────────────────


@responses.activate
def test_mr_with_claude_tag():
    """MR with Claude co-author → mr_ai_coauthor_rate=1.0, mr_agentic_coauthor_rate=1.0."""
    _register_authored_mrs([_mr(1)])
    _register_commits(
        PROJECT_ID, 1, [_commit("fix thing\n\nCo-Authored-By: Claude <claude@anthropic.com>")]
    )
    _register_notes(PROJECT_ID, 1)
    _register_no_reviewed_mrs()

    client = GitLabClient("test-token")
    scanner = ReviewScanner(client)
    metrics = scanner.scan(["alice"], PERIOD)

    assert metrics.mr_ai_coauthor_rate == 1.0
    assert metrics.mr_agentic_coauthor_rate == 1.0
    assert metrics.total_authored_mrs == 1


@responses.activate
def test_mr_with_copilot_tag_not_agentic():
    """MR with Copilot tag → ai_coauthor_rate=1.0 but agentic_rate=0.0."""
    _register_authored_mrs([_mr(1)])
    _register_commits(
        PROJECT_ID, 1, [_commit("fix\n\nCo-Authored-By: GitHub Copilot <copilot@github.com>")]
    )
    _register_notes(PROJECT_ID, 1)
    _register_no_reviewed_mrs()

    client = GitLabClient("test-token")
    scanner = ReviewScanner(client)
    metrics = scanner.scan(["alice"], PERIOD)

    assert metrics.mr_ai_coauthor_rate == 1.0
    assert metrics.mr_agentic_coauthor_rate == 0.0


@responses.activate
def test_mr_with_cursor_tag_is_agentic():
    """MR with Cursor tag → both rates = 1.0."""
    _register_authored_mrs([_mr(1)])
    _register_commits(PROJECT_ID, 1, [_commit("feat\n\nCo-Authored-By: Cursor <cursor@cursor.sh>")])
    _register_notes(PROJECT_ID, 1)
    _register_no_reviewed_mrs()

    client = GitLabClient("test-token")
    scanner = ReviewScanner(client)
    metrics = scanner.scan(["alice"], PERIOD)

    assert metrics.mr_ai_coauthor_rate == 1.0
    assert metrics.mr_agentic_coauthor_rate == 1.0


@responses.activate
def test_mr_without_ai_tags():
    """MR with no AI co-author tags → both rates = 0.0."""
    _register_authored_mrs([_mr(1)])
    _register_commits(PROJECT_ID, 1, [_commit("regular commit message")])
    _register_notes(PROJECT_ID, 1)
    _register_no_reviewed_mrs()

    client = GitLabClient("test-token")
    scanner = ReviewScanner(client)
    metrics = scanner.scan(["alice"], PERIOD)

    assert metrics.mr_ai_coauthor_rate == 0.0
    assert metrics.mr_agentic_coauthor_rate == 0.0


@responses.activate
def test_no_mrs_in_period():
    """No authored MRs → rates are None."""
    _register_authored_mrs([])
    _register_no_reviewed_mrs()

    client = GitLabClient("test-token")
    scanner = ReviewScanner(client)
    metrics = scanner.scan(["alice"], PERIOD)

    assert metrics.mr_ai_coauthor_rate is None
    assert metrics.mr_agentic_coauthor_rate is None
    assert metrics.total_authored_mrs == 0


@responses.activate
def test_mixed_tools_partial_rate():
    """3 MRs: 2 have AI tags (1 Claude, 1 Copilot), 1 has none → ai_rate=2/3, agentic=1/3."""
    _register_authored_mrs([_mr(1), _mr(2), _mr(3)])

    _register_commits(PROJECT_ID, 1, [_commit("fix\n\nCo-Authored-By: Claude <noreply@anthropic>")])
    _register_commits(
        PROJECT_ID, 2, [_commit("feat\n\nCo-Authored-By: GitHub Copilot <copilot@github>")]
    )
    _register_commits(PROJECT_ID, 3, [_commit("chore: update deps")])

    for iid in [1, 2, 3]:
        _register_notes(PROJECT_ID, iid)

    _register_no_reviewed_mrs()

    client = GitLabClient("test-token")
    scanner = ReviewScanner(client)
    metrics = scanner.scan(["alice"], PERIOD)

    assert metrics.mr_ai_coauthor_rate == pytest.approx(2 / 3)
    assert metrics.mr_agentic_coauthor_rate == pytest.approx(1 / 3)


@responses.activate
def test_tag_detection_case_insensitive():
    """Co-author tag detection is case-insensitive."""
    _register_authored_mrs([_mr(1)])
    _register_commits(PROJECT_ID, 1, [_commit("fix\n\nco-authored-by: CLAUDE <claude@ai>")])
    _register_notes(PROJECT_ID, 1)
    _register_no_reviewed_mrs()

    client = GitLabClient("test-token")
    scanner = ReviewScanner(client)
    metrics = scanner.scan(["alice"], PERIOD)

    assert metrics.mr_ai_coauthor_rate == 1.0


@responses.activate
def test_evidence_includes_per_tool_breakdown():
    """Evidence string includes overall rate and per-tool breakdown."""
    _register_authored_mrs([_mr(1)])
    _register_commits(PROJECT_ID, 1, [_commit("fix\n\nCo-Authored-By: Claude <noreply>")])
    _register_notes(PROJECT_ID, 1)
    _register_no_reviewed_mrs()

    client = GitLabClient("test-token")
    scanner = ReviewScanner(client)
    metrics = scanner.scan(["alice"], PERIOD)

    evidence = metrics.evidence.get("mr_ai_coauthor_rate", "")
    assert "100%" in evidence
    assert "Claude" in evidence
    assert "username" not in evidence.lower()  # no individual attribution


# ── calculate_mr_coauthor_scores tests ────────────────────────────────────────


def _metrics(ai_rate, agentic_rate, total=5):
    from ai_fluency_collector.scanners.review_scanner import ReviewMetrics

    return ReviewMetrics(
        lgtm_rate=None,
        review_comment_depth=None,
        self_review_rate=None,
        total_authored_mrs=total,
        mr_ai_coauthor_rate=ai_rate,
        mr_agentic_coauthor_rate=agentic_rate,
        evidence={
            "mr_ai_coauthor_rate": "34% of team-authored merged MRs have AI co-author tags",
            "mr_agentic_coauthor_rate": "34% of team-authored merged MRs have AI co-author tags",
        },
    )



def test_scoring_im_chat_from_ai_coauthor_rate():
    """im-chat score reflects overall AI co-author rate."""
    m = _metrics(ai_rate=0.34, agentic_rate=0.22)
    signals = calculate_mr_coauthor_scores(m, MR_COAUTHOR_SKILL_MAPPINGS)
    skill_scores = {s["skill_id"]: s["score"] for s in signals}
    assert skill_scores["im-chat"] == 34


def test_scoring_im_supervised_agent_from_agentic_rate():
    """im-supervised-agent score reflects agentic co-author rate only."""
    m = _metrics(ai_rate=0.34, agentic_rate=0.22)
    signals = calculate_mr_coauthor_scores(m, MR_COAUTHOR_SKILL_MAPPINGS)
    skill_scores = {s["skill_id"]: s["score"] for s in signals}
    assert skill_scores["im-supervised-agent"] == 22


def test_scoring_zero_rates_no_signals():
    """Zero rates produce no signals."""
    m = _metrics(ai_rate=0.0, agentic_rate=0.0)
    signals = calculate_mr_coauthor_scores(m, MR_COAUTHOR_SKILL_MAPPINGS)
    assert signals == []


def test_scoring_none_rates_no_signals():
    """None rates (no MRs) produce no signals."""
    m = _metrics(ai_rate=None, agentic_rate=None, total=0)
    signals = calculate_mr_coauthor_scores(m, MR_COAUTHOR_SKILL_MAPPINGS)
    assert signals == []


def test_scoring_none_metrics_no_signals():
    """None metrics object → empty list."""
    signals = calculate_mr_coauthor_scores(None, MR_COAUTHOR_SKILL_MAPPINGS)
    assert signals == []
