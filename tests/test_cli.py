from __future__ import annotations

from unittest.mock import MagicMock, patch

import yaml
from click.testing import CliRunner

from ai_fluency_collector.cli import main


def _write_valid_config(tmp_path):
    config = {
        "team": {
            "name": "Test Team",
            "code": "test-team",
            "projects": ["group/project-one"],
        }
    }
    path = tmp_path / "team.yaml"
    path.write_text(yaml.dump(config))
    return str(path)


def _mock_client_with_scanners():
    """Create a mock GitLabClient whose methods return values scanners can handle."""
    mock_cls = MagicMock()
    client = mock_cls.return_value
    # ArtifactScanner calls check_file_exists / check_directory_exists → return False
    client.check_file_exists.return_value = False
    client.check_directory_exists.return_value = False
    # CIScanner calls get_file_content → return None (no .gitlab-ci.yml)
    client.get_file_content.return_value = None
    return mock_cls


def test_help_output():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "--config" in result.output
    assert "--period" in result.output


def test_missing_config_file():
    runner = CliRunner()
    result = runner.invoke(main, ["--config", "nonexistent.yaml"])
    assert result.exit_code != 0
    assert "Config file not found" in result.output
    assert "config.example.yaml" in result.output


def test_missing_gitlab_token(tmp_path, monkeypatch):
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    config_path = _write_valid_config(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["--config", config_path])
    assert result.exit_code != 0
    assert "GITLAB_TOKEN" in result.output
    assert "read_api" in result.output


def test_invalid_period_format(tmp_path, monkeypatch):
    monkeypatch.setenv("GITLAB_TOKEN", "test-token")
    config_path = _write_valid_config(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["--config", config_path, "--period", "bad"])
    assert result.exit_code != 0
    assert "Invalid period format" in result.output
    assert "YYYY-WNN" in result.output


def test_invalid_period_week_zero(tmp_path, monkeypatch):
    monkeypatch.setenv("GITLAB_TOKEN", "test-token")
    config_path = _write_valid_config(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["--config", config_path, "--period", "2026-W00"])
    assert result.exit_code != 0
    assert "Invalid period format" in result.output


@patch("ai_fluency_collector.cli.GitLabClient")
def test_startup_banner(mock_client_cls, tmp_path, monkeypatch):
    monkeypatch.setenv("GITLAB_TOKEN", "test-token")
    client = mock_client_cls.return_value
    client.check_file_exists.return_value = False
    client.check_directory_exists.return_value = False
    client.get_file_content.return_value = None
    config_path = _write_valid_config(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["--config", config_path, "--period", "2026-W12"])
    assert result.exit_code == 0
    assert "Test Team" in result.output
    assert "1" in result.output  # 1 project
    assert "2026-W12" in result.output
    assert "test-team-2026-W12.json" in result.output
    client.validate_token.assert_called_once()


@patch("ai_fluency_collector.cli.GitLabClient")
def test_default_period_uses_current_week(mock_client_cls, tmp_path, monkeypatch):
    monkeypatch.setenv("GITLAB_TOKEN", "test-token")
    client = mock_client_cls.return_value
    client.check_file_exists.return_value = False
    client.check_directory_exists.return_value = False
    client.get_file_content.return_value = None
    config_path = _write_valid_config(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["--config", config_path])
    assert result.exit_code == 0
    assert "-W" in result.output


@patch("ai_fluency_collector.cli.GitLabClient")
def test_invalid_gitlab_token(mock_client_cls, tmp_path, monkeypatch):
    from ai_fluency_collector.gitlab_client import GitLabAuthError

    monkeypatch.setenv("GITLAB_TOKEN", "bad-token")
    mock_client_cls.return_value.validate_token.side_effect = GitLabAuthError(
        "GitLab authentication failed. Check that GITLAB_TOKEN is valid and has read_api scope."
    )
    config_path = _write_valid_config(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["--config", config_path, "--period", "2026-W12"])
    assert result.exit_code != 0
    assert "authentication failed" in result.output
