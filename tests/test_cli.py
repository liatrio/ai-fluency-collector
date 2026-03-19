from __future__ import annotations

from unittest.mock import patch

import yaml
from click.testing import CliRunner

from ai_fluency_collector.cli import main
from ai_fluency_collector.scanners.member_scanner import MemberResult


def _write_valid_config(tmp_path):
    config = {
        "team": {
            "name": "Test Team",
            "code": "test-team",
            "members": ["alice.smith"],
            "projects": ["group/project-one"],
        }
    }
    path = tmp_path / "team.yaml"
    path.write_text(yaml.dump(config))
    return str(path)


def _setup_mock_client(mock_client_cls):
    """Configure mock client for artifact and CI scanners."""
    client = mock_client_cls.return_value
    client.check_file_exists.return_value = False
    client.check_directory_exists.return_value = False
    client.get_file_content.return_value = None
    return client


def test_help_output():
    runner = CliRunner()
    result = runner.invoke(main, ["scan", "--help"])
    assert result.exit_code == 0
    assert "--config" in result.output
    assert "--period" in result.output


def test_group_help_output():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "scan" in result.output
    assert "init" in result.output


def test_missing_config_file():
    runner = CliRunner()
    result = runner.invoke(main, ["scan", "--config", "nonexistent.yaml"])
    assert result.exit_code != 0
    assert "Config file not found" in result.output
    assert "config.example.yaml" in result.output


def test_missing_gitlab_token(tmp_path, monkeypatch):
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    config_path = _write_valid_config(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["scan", "--config", config_path])
    assert result.exit_code != 0
    assert "GITLAB_TOKEN" in result.output
    assert "read_api" in result.output


def test_invalid_period_format(tmp_path, monkeypatch):
    monkeypatch.setenv("GITLAB_TOKEN", "test-token")
    config_path = _write_valid_config(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["scan", "--config", config_path, "--period", "bad"])
    assert result.exit_code != 0
    assert "Invalid period format" in result.output
    assert "YYYY-WNN" in result.output


def test_invalid_period_week_zero(tmp_path, monkeypatch):
    monkeypatch.setenv("GITLAB_TOKEN", "test-token")
    config_path = _write_valid_config(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["scan", "--config", config_path, "--period", "2026-W00"])
    assert result.exit_code != 0
    assert "Invalid period format" in result.output


@patch("ai_fluency_collector.cli.MemberScanner")
@patch("ai_fluency_collector.cli.GitLabClient")
def test_startup_banner(mock_client_cls, mock_member_cls, tmp_path, monkeypatch):
    monkeypatch.setenv("GITLAB_TOKEN", "test-token")
    _setup_mock_client(mock_client_cls)
    mock_member_cls.return_value.scan_all_members.return_value = [
        MemberResult(username="alice.smith")
    ]
    config_path = _write_valid_config(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["scan", "--config", config_path, "--period", "2026-W12"])
    assert result.exit_code == 0
    assert "Test Team" in result.output
    assert "2026-W12" in result.output
    assert "test-team-2026-W12.json" in result.output
    assert "Members:" in result.output or "1" in result.output


@patch("ai_fluency_collector.cli.MemberScanner")
@patch("ai_fluency_collector.cli.GitLabClient")
def test_default_period_uses_current_week(mock_client_cls, mock_member_cls, tmp_path, monkeypatch):
    monkeypatch.setenv("GITLAB_TOKEN", "test-token")
    _setup_mock_client(mock_client_cls)
    mock_member_cls.return_value.scan_all_members.return_value = [
        MemberResult(username="alice.smith")
    ]
    config_path = _write_valid_config(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["scan", "--config", config_path])
    assert result.exit_code == 0
    assert "-W" in result.output


@patch("ai_fluency_collector.cli.GitLabClient")
def test_invalid_gitlab_token(mock_client_cls, tmp_path, monkeypatch):
    from ai_fluency_collector.gitlab_client import GitLabAuthError

    monkeypatch.setenv("GITLAB_TOKEN", "bad-token")
    mock_client_cls.return_value.validate_token.side_effect = GitLabAuthError(
        "GitLab authentication failed at https://gitlab.com. "
        "Check that GITLAB_TOKEN is valid and has read_api scope."
    )
    config_path = _write_valid_config(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["scan", "--config", config_path, "--period", "2026-W12"])
    assert result.exit_code != 0
    assert "authentication failed" in result.output


@patch("ai_fluency_collector.cli.MemberScanner")
@patch("ai_fluency_collector.cli.GitLabClient")
def test_member_scanning_in_output(mock_client_cls, mock_member_cls, tmp_path, monkeypatch):
    monkeypatch.setenv("GITLAB_TOKEN", "test-token")
    _setup_mock_client(mock_client_cls)
    mock_member_cls.return_value.scan_all_members.return_value = [
        MemberResult(username="alice.smith")
    ]
    config_path = _write_valid_config(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["scan", "--config", config_path, "--period", "2026-W12"])
    assert result.exit_code == 0
    assert "Scanning member activity" in result.output
    assert "alice.smith" in result.output


@patch("ai_fluency_collector.cli.GitLabClient")
def test_validate_flag(mock_client_cls, tmp_path, monkeypatch):
    monkeypatch.setenv("GITLAB_TOKEN", "test-token")
    client = _setup_mock_client(mock_client_cls)
    client.get_branches.return_value = [{"name": "main"}]
    config_path = _write_valid_config(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["scan", "--config", config_path, "--validate"])
    assert result.exit_code == 0
    assert "Validation Mode" in result.output
    assert "Token:    valid" in result.output
    assert "group/project-one: accessible" in result.output
    assert "Validation complete" in result.output
    # Should NOT contain scanning output
    assert "Scanning for repo artifacts" not in result.output


def _write_config_with_gitlab_url(tmp_path, gitlab_url):
    config = {
        "team": {
            "name": "Test Team",
            "code": "test-team",
            "gitlab_url": gitlab_url,
            "members": ["alice.smith"],
            "projects": ["group/project-one"],
        }
    }
    path = tmp_path / "team.yaml"
    path.write_text(yaml.dump(config))
    return str(path)


@patch("ai_fluency_collector.cli.MemberScanner")
@patch("ai_fluency_collector.cli.GitLabClient")
def test_gitlab_url_from_config(mock_client_cls, mock_member_cls, tmp_path, monkeypatch):
    monkeypatch.setenv("GITLAB_TOKEN", "test-token")
    _setup_mock_client(mock_client_cls)
    mock_member_cls.return_value.scan_all_members.return_value = [
        MemberResult(username="alice.smith")
    ]
    config_path = _write_config_with_gitlab_url(tmp_path, "https://gitlab.example.com")
    runner = CliRunner()
    result = runner.invoke(main, ["scan", "--config", config_path, "--period", "2026-W12"])
    assert result.exit_code == 0
    # Client should be constructed with the config URL
    mock_client_cls.assert_called_once_with("test-token", base_url="https://gitlab.example.com")


@patch("ai_fluency_collector.cli.MemberScanner")
@patch("ai_fluency_collector.cli.GitLabClient")
def test_gitlab_url_cli_overrides_config(mock_client_cls, mock_member_cls, tmp_path, monkeypatch):
    monkeypatch.setenv("GITLAB_TOKEN", "test-token")
    _setup_mock_client(mock_client_cls)
    mock_member_cls.return_value.scan_all_members.return_value = [
        MemberResult(username="alice.smith")
    ]
    config_path = _write_config_with_gitlab_url(tmp_path, "https://gitlab.example.com")
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "scan",
            "--config",
            config_path,
            "--period",
            "2026-W12",
            "--gitlab-url",
            "https://custom.gl",
        ],
    )
    assert result.exit_code == 0
    # CLI flag should take precedence
    mock_client_cls.assert_called_once_with("test-token", base_url="https://custom.gl")
