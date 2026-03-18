from __future__ import annotations

from urllib.parse import quote

import responses
import yaml

from ai_fluency_collector.gitlab_client import GitLabClient
from ai_fluency_collector.scanners.ci_scanner import CI_PATTERN_IDS, CIScanner

BASE = "https://gitlab.com/api/v4"
PROJECT = "my-group/my-project"
ENCODED_PROJECT = quote(PROJECT, safe="")


def _raw_file_url() -> str:
    encoded_file = quote(".gitlab-ci.yml", safe="")
    return f"{BASE}/projects/{ENCODED_PROJECT}/repository/files/{encoded_file}/raw"


def _register_ci_content(ci_yaml: str) -> None:
    responses.add(responses.GET, _raw_file_url(), body=ci_yaml, status=200)


def _register_no_ci() -> None:
    responses.add(responses.GET, _raw_file_url(), status=404)


@responses.activate
def test_no_ci_file_returns_all_false():
    """Missing .gitlab-ci.yml produces all False with no error."""
    _register_no_ci()
    client = GitLabClient("test-token")
    scanner = CIScanner(client)
    result = scanner.scan_project(PROJECT)
    assert len(result) == len(CI_PATTERN_IDS)
    for pid in CI_PATTERN_IDS:
        assert result[pid] is False


@responses.activate
def test_sast_via_template_include():
    """SAST detected via include template directive."""
    ci = yaml.dump(
        {
            "include": [{"template": "Security/SAST.gitlab-ci.yml"}],
            "stages": ["test"],
        }
    )
    _register_ci_content(ci)
    client = GitLabClient("test-token")
    scanner = CIScanner(client)
    result = scanner.scan_project(PROJECT)
    assert result["sast-dast"] is True


@responses.activate
def test_sast_via_job_name():
    """SAST detected via job name containing 'sast'."""
    ci = yaml.dump(
        {
            "stages": ["test"],
            "sast-scan": {"stage": "test", "script": ["run-sast"]},
        }
    )
    _register_ci_content(ci)
    client = GitLabClient("test-token")
    scanner = CIScanner(client)
    result = scanner.scan_project(PROJECT)
    assert result["sast-dast"] is True


@responses.activate
def test_dast_via_include_string():
    """DAST detected via string include format."""
    ci = yaml.dump(
        {
            "include": "Security/DAST.gitlab-ci.yml",
            "stages": ["test"],
        }
    )
    _register_ci_content(ci)
    client = GitLabClient("test-token")
    scanner = CIScanner(client)
    result = scanner.scan_project(PROJECT)
    assert result["sast-dast"] is True


@responses.activate
def test_secret_detection_via_template():
    """Secret detection via template include."""
    ci = yaml.dump(
        {
            "include": [{"template": "Security/Secret-Detection.gitlab-ci.yml"}],
        }
    )
    _register_ci_content(ci)
    client = GitLabClient("test-token")
    scanner = CIScanner(client)
    result = scanner.scan_project(PROJECT)
    assert result["secret-detection"] is True


@responses.activate
def test_secret_detection_via_job_name():
    """Secret detection via job name."""
    ci = yaml.dump(
        {
            "secret-detection": {"script": ["detect-secrets"]},
        }
    )
    _register_ci_content(ci)
    client = GitLabClient("test-token")
    scanner = CIScanner(client)
    result = scanner.scan_project(PROJECT)
    assert result["secret-detection"] is True


@responses.activate
def test_ai_code_review():
    """AI code review detected via script content."""
    ci = yaml.dump(
        {
            "review": {"script": ["gitlab-duo review"]},
        }
    )
    _register_ci_content(ci)
    client = GitLabClient("test-token")
    scanner = CIScanner(client)
    result = scanner.scan_project(PROJECT)
    assert result["ai-code-review"] is True


@responses.activate
def test_ai_test_generation():
    """AI test generation detected via job name."""
    ci = yaml.dump(
        {
            "ai-test-gen": {"script": ["run-tests"]},
        }
    )
    _register_ci_content(ci)
    client = GitLabClient("test-token")
    scanner = CIScanner(client)
    result = scanner.scan_project(PROJECT)
    assert result["ai-test-generation"] is True


@responses.activate
def test_dependency_scanning_via_template():
    """Dependency scanning via template include."""
    ci = yaml.dump(
        {
            "include": [{"template": "Security/Dependency-Scanning.gitlab-ci.yml"}],
        }
    )
    _register_ci_content(ci)
    client = GitLabClient("test-token")
    scanner = CIScanner(client)
    result = scanner.scan_project(PROJECT)
    assert result["dependency-scanning"] is True


@responses.activate
def test_code_coverage_via_coverage_key():
    """Code coverage detected via coverage key in job."""
    ci = yaml.dump(
        {
            "test": {"script": ["pytest"], "coverage": "/TOTAL.*\\s+(\\d+%)$/"},
        }
    )
    _register_ci_content(ci)
    client = GitLabClient("test-token")
    scanner = CIScanner(client)
    result = scanner.scan_project(PROJECT)
    assert result["code-coverage"] is True


@responses.activate
def test_code_coverage_via_report():
    """Code coverage detected via artifacts.reports.coverage_report."""
    ci = yaml.dump(
        {
            "test": {
                "script": ["pytest"],
                "artifacts": {
                    "reports": {
                        "coverage_report": {
                            "coverage_format": "cobertura",
                            "path": "coverage.xml",
                        }
                    }
                },
            },
        }
    )
    _register_ci_content(ci)
    client = GitLabClient("test-token")
    scanner = CIScanner(client)
    result = scanner.scan_project(PROJECT)
    assert result["code-coverage"] is True


@responses.activate
def test_deployment_gates():
    """Deployment gates detected via deploy stage + environment."""
    ci = yaml.dump(
        {
            "stages": ["build", "deploy"],
            "deploy-prod": {
                "stage": "deploy",
                "script": ["deploy.sh"],
                "environment": {"name": "production"},
                "rules": [{"if": "$CI_COMMIT_BRANCH == 'main'"}],
            },
        }
    )
    _register_ci_content(ci)
    client = GitLabClient("test-token")
    scanner = CIScanner(client)
    result = scanner.scan_project(PROJECT)
    assert result["deployment-gates"] is True


@responses.activate
def test_multiple_patterns_in_one_file():
    """Multiple CI patterns detected in a single .gitlab-ci.yml."""
    ci = yaml.dump(
        {
            "include": [
                {"template": "Security/SAST.gitlab-ci.yml"},
                {"template": "Security/Secret-Detection.gitlab-ci.yml"},
            ],
            "stages": ["test", "deploy"],
            "test": {
                "script": ["pytest"],
                "coverage": "/\\d+%/",
            },
            "deploy-prod": {
                "stage": "deploy",
                "script": ["deploy.sh"],
                "environment": {"name": "production"},
            },
        }
    )
    _register_ci_content(ci)
    client = GitLabClient("test-token")
    scanner = CIScanner(client)
    result = scanner.scan_project(PROJECT)
    assert result["sast-dast"] is True
    assert result["secret-detection"] is True
    assert result["code-coverage"] is True
    assert result["deployment-gates"] is True


@responses.activate
def test_include_list_of_strings():
    """Include directives as a list of template strings."""
    ci = yaml.dump(
        {
            "include": [
                {"template": "Security/SAST.gitlab-ci.yml"},
                {"template": "Security/Dependency-Scanning.gitlab-ci.yml"},
            ],
        }
    )
    _register_ci_content(ci)
    client = GitLabClient("test-token")
    scanner = CIScanner(client)
    result = scanner.scan_project(PROJECT)
    assert result["sast-dast"] is True
    assert result["dependency-scanning"] is True


@responses.activate
def test_invalid_yaml_returns_all_false():
    """Invalid YAML content returns all False with no error."""
    responses.add(responses.GET, _raw_file_url(), body=":::invalid yaml{{{", status=200)
    client = GitLabClient("test-token")
    scanner = CIScanner(client)
    result = scanner.scan_project(PROJECT)
    for pid in CI_PATTERN_IDS:
        assert result[pid] is False
