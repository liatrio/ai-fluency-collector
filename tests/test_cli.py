from __future__ import annotations

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


def test_startup_banner(tmp_path, monkeypatch):
    monkeypatch.setenv("GITLAB_TOKEN", "test-token")
    config_path = _write_valid_config(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["--config", config_path, "--period", "2026-W12"])
    assert result.exit_code == 0
    assert "Test Team" in result.output
    assert "1" in result.output  # 1 project
    assert "2026-W12" in result.output
    assert "test-team-2026-W12.json" in result.output


def test_default_period_uses_current_week(tmp_path, monkeypatch):
    monkeypatch.setenv("GITLAB_TOKEN", "test-token")
    config_path = _write_valid_config(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["--config", config_path])
    assert result.exit_code == 0
    # Should contain a period in YYYY-WNN format
    assert "-W" in result.output
