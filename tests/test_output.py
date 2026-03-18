from __future__ import annotations

import json

from ai_fluency_collector.output import build_output, write_output


def test_build_output_both_sources():
    """Both sources included when both have signals."""
    artifact_signals = [{"skill_id": "cq-context", "score": 75, "evidence": "found"}]
    ci_signals = [{"skill_id": "sdlc-security", "score": 50, "evidence": "sast"}]
    data = build_output("my-team", "2026-W12", artifact_signals, ci_signals)

    assert data["team_code"] == "my-team"
    assert data["survey_period"] == "2026-W12"
    assert len(data["sources"]) == 2
    assert data["sources"][0]["source_id"] == "gitlab-repo-artifacts"
    assert data["sources"][1]["source_id"] == "gitlab-ci-config"


def test_build_output_artifact_only():
    """Only artifact source included when CI has no signals."""
    artifact_signals = [{"skill_id": "cq-context", "score": 75, "evidence": "found"}]
    data = build_output("my-team", "2026-W12", artifact_signals, [])

    assert len(data["sources"]) == 1
    assert data["sources"][0]["source_id"] == "gitlab-repo-artifacts"


def test_build_output_ci_only():
    """Only CI source included when artifacts have no signals."""
    ci_signals = [{"skill_id": "sdlc-security", "score": 50, "evidence": "sast"}]
    data = build_output("my-team", "2026-W12", [], ci_signals)

    assert len(data["sources"]) == 1
    assert data["sources"][0]["source_id"] == "gitlab-ci-config"


def test_build_output_empty_sources():
    """No sources when neither scanner produced signals."""
    data = build_output("my-team", "2026-W12", [], [])
    assert data["sources"] == []


def test_source_id_values():
    """source_id values are exactly as specified."""
    artifact_signals = [{"skill_id": "x", "score": 1, "evidence": "y"}]
    ci_signals = [{"skill_id": "x", "score": 1, "evidence": "y"}]
    data = build_output("t", "2026-W01", artifact_signals, ci_signals)
    source_ids = [s["source_id"] for s in data["sources"]]
    assert source_ids == ["gitlab-repo-artifacts", "gitlab-ci-config"]


def test_write_output_creates_file(tmp_path, monkeypatch):
    """write_output creates a JSON file with correct name and content."""
    monkeypatch.chdir(tmp_path)
    data = {
        "team_code": "test-team",
        "survey_period": "2026-W12",
        "sources": [
            {
                "source_id": "gitlab-repo-artifacts",
                "signals": [{"skill_id": "cq-context", "score": 75, "evidence": "found"}],
            }
        ],
    }
    path = write_output(data, "test-team", "2026-W12")
    assert path.endswith("test-team-2026-W12.json")

    with open(path) as f:
        written = json.load(f)
    assert written == data


def test_write_output_indentation(tmp_path, monkeypatch):
    """Output JSON uses 2-space indentation."""
    monkeypatch.chdir(tmp_path)
    data = {"team_code": "t", "survey_period": "2026-W01", "sources": []}
    path = write_output(data, "t", "2026-W01")
    with open(path) as f:
        content = f.read()
    # 2-space indent means keys inside the object are indented by 2 spaces
    assert '  "team_code"' in content


def test_schema_structure():
    """Output matches expected schema shape."""
    artifact_signals = [
        {"skill_id": "cq-context", "score": 75, "evidence": "CLAUDE.md found in 3/4 projects"}
    ]
    ci_signals = [{"skill_id": "sdlc-security", "score": 60, "evidence": "SAST in 2/4 projects"}]
    data = build_output("acme", "2026-W12", artifact_signals, ci_signals)

    # Top-level keys
    assert set(data.keys()) == {"team_code", "survey_period", "sources"}

    # Source structure
    for source in data["sources"]:
        assert set(source.keys()) == {"source_id", "signals"}
        for signal in source["signals"]:
            assert set(signal.keys()) == {"skill_id", "score", "evidence"}
            assert isinstance(signal["score"], int)
