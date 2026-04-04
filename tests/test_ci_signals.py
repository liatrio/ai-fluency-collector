from __future__ import annotations

from datetime import date
from urllib.parse import quote

import pytest
import responses
import yaml

from ai_fluency_collector.config import TeamConfig, load_config
from ai_fluency_collector.gitlab_client import GitLabClient
from ai_fluency_collector.scanners.gitlab_artifact_scanner import DEFAULT_BRANCH_WEIGHT
from ai_fluency_collector.scanners.gitlab_ci_scanner import CIScanner

BASE = "https://gitlab.com/api/v4"
PROJECT = "my-group/my-project"
ENCODED_PROJECT = quote(PROJECT, safe="")
TODAY = date.today().isoformat()

SINGLE_DEFAULT_BRANCH = [
    {
        "name": "main",
        "default": True,
        "commit": {"committed_date": f"{TODAY}T00:00:00.000+00:00"},
    }
]


# --- Config parsing tests ---


def test_ci_signals_parsed_from_config(tmp_path):
    config = {
        "team": {
            "name": "Test Team",
            "code": "test-team",
            "members": ["alice"],
            "projects": ["group/project"],
            "ci_signals": {
                "ai-code-review": ["ai-review/.ai-code-review.yml"],
                "deployment-gates": ["deploy_staging"],
            },
        }
    }
    path = tmp_path / "team.yaml"
    path.write_text(yaml.dump(config))
    team = load_config(str(path))
    assert team.ci_signals == {
        "ai-code-review": ["ai-review/.ai-code-review.yml"],
        "deployment-gates": ["deploy_staging"],
    }


def test_ci_signals_defaults_to_empty(tmp_path):
    config = {
        "team": {
            "name": "Test Team",
            "code": "test-team",
            "members": ["alice"],
            "projects": ["group/project"],
        }
    }
    path = tmp_path / "team.yaml"
    path.write_text(yaml.dump(config))
    team = load_config(str(path))
    assert team.ci_signals == {}


def test_ci_signals_invalid_type(tmp_path):
    config = {
        "team": {
            "name": "Test Team",
            "code": "test-team",
            "members": ["alice"],
            "projects": ["group/project"],
            "ci_signals": "not-a-dict",
        }
    }
    path = tmp_path / "team.yaml"
    path.write_text(yaml.dump(config))
    with pytest.raises(ValueError, match="ci_signals must be a mapping"):
        load_config(str(path))


def test_ci_signals_invalid_value_type(tmp_path):
    config = {
        "team": {
            "name": "Test Team",
            "code": "test-team",
            "members": ["alice"],
            "projects": ["group/project"],
            "ci_signals": {"ai-code-review": "not-a-list"},
        }
    }
    path = tmp_path / "team.yaml"
    path.write_text(yaml.dump(config))
    with pytest.raises(ValueError, match="ci_signals.ai-code-review must be a list"):
        load_config(str(path))


def test_team_config_dataclass_has_ci_signals():
    team = TeamConfig(name="T", code="t", members=["u"], projects=["p"])
    assert team.ci_signals == {}


# --- CI Scanner with ci_signals tests ---


def _branches_url() -> str:
    return f"{BASE}/projects/{ENCODED_PROJECT}/repository/branches"


def _raw_file_url() -> str:
    encoded_file = quote(".gitlab-ci.yml", safe="")
    return f"{BASE}/projects/{ENCODED_PROJECT}/repository/files/{encoded_file}/raw"


def _register_branches(branches: list[dict]) -> None:
    responses.add(responses.GET, _branches_url(), json=branches, status=200)
    responses.add(responses.GET, _branches_url(), json=[], status=200)


def _register_ci_content(ci_yaml: str) -> None:
    responses.add(responses.GET, _raw_file_url(), body=ci_yaml, status=200)


@responses.activate
def test_ci_signals_detect_job_by_name():
    """User-declared ci_signal matches a job name via substring."""
    _register_branches(SINGLE_DEFAULT_BRANCH)
    ci = yaml.dump(
        {
            "stages": ["build"],
            "my-custom-ai-review-job": {"stage": "build", "script": ["echo hi"]},
        }
    )
    _register_ci_content(ci)

    client = GitLabClient("test-token")
    scanner = CIScanner(
        client,
        ci_signals={"ai-code-review": ["ai-review"]},
    )
    result = scanner.scan_project(PROJECT)
    assert result["ai-code-review"]["weight"] == DEFAULT_BRANCH_WEIGHT


@responses.activate
def test_ci_signals_detect_template_path():
    """User-declared ci_signal matches a template/include path via substring."""
    _register_branches(SINGLE_DEFAULT_BRANCH)
    ci = yaml.dump(
        {
            "include": [
                {
                    "project": "platform/templates",
                    "file": "ai-review/.ai-code-review.yml",
                }
            ],
        }
    )
    _register_ci_content(ci)

    client = GitLabClient("test-token")
    scanner = CIScanner(
        client,
        ci_signals={"ai-code-review": ["ai-review/.ai-code-review.yml"]},
    )
    result = scanner.scan_project(PROJECT)
    assert result["ai-code-review"]["weight"] == DEFAULT_BRANCH_WEIGHT


@responses.activate
def test_ci_signals_no_match():
    """User-declared ci_signal that doesn't match anything stays false."""
    _register_branches(SINGLE_DEFAULT_BRANCH)
    ci = yaml.dump(
        {
            "stages": ["test"],
            "unit-tests": {"stage": "test", "script": ["pytest"]},
        }
    )
    _register_ci_content(ci)

    client = GitLabClient("test-token")
    scanner = CIScanner(
        client,
        ci_signals={"ai-code-review": ["ai-review"]},
    )
    result = scanner.scan_project(PROJECT)
    assert result["ai-code-review"]["weight"] == 0.0


@responses.activate
def test_ci_signals_combined_with_auto_detection():
    """Auto-detection and user ci_signals work together (OR logic)."""
    _register_branches(SINGLE_DEFAULT_BRANCH)
    # This CI file has SAST template (auto-detected) but nothing for ai-code-review
    # The user signal for ai-code-review matches the custom job name
    ci = yaml.dump(
        {
            "include": [{"template": "Security/SAST.gitlab-ci.yml"}],
            "stages": ["test"],
            "custom-ai-review": {"stage": "test", "script": ["review"]},
        }
    )
    _register_ci_content(ci)

    client = GitLabClient("test-token")
    scanner = CIScanner(
        client,
        ci_signals={"ai-code-review": ["custom-ai-review"]},
    )
    result = scanner.scan_project(PROJECT)
    # SAST detected by auto-detection
    assert result["sast-dast"]["weight"] == DEFAULT_BRANCH_WEIGHT
    # AI code review detected by user signal (substring match on job name)
    assert result["ai-code-review"]["weight"] == DEFAULT_BRANCH_WEIGHT


@responses.activate
def test_ci_signals_deployment_gates_by_job_name():
    """User-declared deployment-gates signal matches job name."""
    _register_branches(SINGLE_DEFAULT_BRANCH)
    ci = yaml.dump(
        {
            "stages": ["release"],
            "deploy_staging": {"stage": "release", "script": ["deploy.sh"]},
        }
    )
    _register_ci_content(ci)

    client = GitLabClient("test-token")
    scanner = CIScanner(
        client,
        ci_signals={"deployment-gates": ["deploy_staging"]},
    )
    result = scanner.scan_project(PROJECT)
    assert result["deployment-gates"]["weight"] == DEFAULT_BRANCH_WEIGHT


@responses.activate
def test_ci_signals_without_ci_signals_param():
    """CIScanner without ci_signals param works same as before."""
    _register_branches(SINGLE_DEFAULT_BRANCH)
    ci = yaml.dump(
        {
            "include": [{"template": "Security/SAST.gitlab-ci.yml"}],
        }
    )
    _register_ci_content(ci)

    client = GitLabClient("test-token")
    scanner = CIScanner(client)
    result = scanner.scan_project(PROJECT)
    assert result["sast-dast"]["weight"] == DEFAULT_BRANCH_WEIGHT
    assert result["ai-code-review"]["weight"] == 0.0
