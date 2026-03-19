from __future__ import annotations

from unittest.mock import MagicMock, patch

import yaml
from click.testing import CliRunner

from ai_fluency_collector.cli import main
from ai_fluency_collector.gitlab_client import GitLabUserNotFoundError


def _mock_client():
    """Create a fully configured mock GitLabClient."""
    client = MagicMock()
    client._api_url.return_value = "https://gitlab.com/api/v4/user"
    resp = MagicMock()
    resp.json.return_value = {"username": "testuser"}
    client.session.get.return_value = resp
    client.get_user.return_value = {"username": "alice", "id": 1}
    client.get_branches.return_value = [
        {"name": "main", "default": True},
        {"name": "dev", "default": False},
    ]
    client.get_file_content.return_value = None
    return client


@patch("ai_fluency_collector.cli.GitLabClient")
def test_init_basic_flow(mock_client_cls, tmp_path, monkeypatch):
    """Test the full init wizard flow with minimal input."""
    monkeypatch.setenv("GITLAB_TOKEN", "test-token")
    monkeypatch.chdir(tmp_path)

    client = _mock_client()
    mock_client_cls.return_value = client

    # Simulate user input:
    # GitLab URL (accept default), team name, team code (accept default),
    # member "alice", empty to finish members,
    # project "group/proj", empty to finish projects,
    # output filename (accept default)
    user_input = (
        "\n".join(
            [
                "",  # GitLab URL: accept default
                "My Test Team",  # Team name
                "",  # Team code: accept default (my-test-team)
                "alice",  # Member 1
                "",  # Empty to finish members
                "group/proj",  # Project 1
                "",  # Empty to finish projects
                "",  # Output filename: accept default
            ]
        )
        + "\n"
    )

    runner = CliRunner()
    result = runner.invoke(main, ["init"], input=user_input)

    assert result.exit_code == 0, f"Exit code: {result.exit_code}\nOutput:\n{result.output}"
    assert "Team Setup Wizard" in result.output
    assert "Connected as: testuser" in result.output
    assert "Config written to:" in result.output
    assert "afc scan --config" in result.output

    # Verify the YAML file was written
    config_path = tmp_path / "my-test-team.yaml"
    assert config_path.exists()

    config = yaml.safe_load(config_path.read_text())
    assert config["team"]["name"] == "My Test Team"
    assert config["team"]["code"] == "my-test-team"
    assert config["team"]["members"] == ["alice"]
    assert config["team"]["projects"] == ["group/proj"]
    assert config["team"]["gitlab_url"] == "https://gitlab.com"


@patch("ai_fluency_collector.cli.GitLabClient")
def test_init_custom_gitlab_url(mock_client_cls, tmp_path, monkeypatch):
    """Test init with a custom GitLab URL."""
    monkeypatch.setenv("GITLAB_TOKEN", "test-token")
    monkeypatch.chdir(tmp_path)

    client = _mock_client()
    mock_client_cls.return_value = client

    user_input = (
        "\n".join(
            [
                "https://gitlab.example.com",  # Custom GitLab URL
                "My Team",
                "",  # Accept default code
                "bob",
                "",
                "org/repo",
                "",
                "",  # Accept default filename
            ]
        )
        + "\n"
    )

    runner = CliRunner()
    result = runner.invoke(main, ["init"], input=user_input)

    assert result.exit_code == 0, f"Output:\n{result.output}"
    mock_client_cls.assert_called_once_with("test-token", base_url="https://gitlab.example.com")


@patch("ai_fluency_collector.cli.GitLabClient")
def test_init_invalid_user_retry(mock_client_cls, tmp_path, monkeypatch):
    """Test that invalid usernames show error and allow retry."""
    monkeypatch.setenv("GITLAB_TOKEN", "test-token")
    monkeypatch.chdir(tmp_path)

    client = _mock_client()
    # First call: user not found, second call: found
    client.get_user.side_effect = [
        GitLabUserNotFoundError("User 'baduser' not found"),
        {"username": "gooduser", "id": 2},
    ]
    mock_client_cls.return_value = client

    user_input = (
        "\n".join(
            [
                "",  # GitLab URL
                "Team",
                "",  # Code
                "baduser",  # Invalid user
                "gooduser",  # Valid user
                "",  # Finish members
                "group/proj",
                "",
                "",  # Filename
            ]
        )
        + "\n"
    )

    runner = CliRunner()
    result = runner.invoke(main, ["init"], input=user_input)

    assert result.exit_code == 0, f"Output:\n{result.output}"
    assert "not found" in result.output
    assert "Found: gooduser" in result.output


@patch("ai_fluency_collector.cli.GitLabClient")
def test_init_invalid_project_retry(mock_client_cls, tmp_path, monkeypatch):
    """Test that invalid project paths show error and allow retry."""
    monkeypatch.setenv("GITLAB_TOKEN", "test-token")
    monkeypatch.chdir(tmp_path)

    from ai_fluency_collector.gitlab_client import GitLabAccessError

    client = _mock_client()
    client.get_branches.side_effect = [
        GitLabAccessError("Project 'bad/path' not found."),
        [{"name": "main", "default": True}],
    ]
    mock_client_cls.return_value = client

    user_input = (
        "\n".join(
            [
                "",
                "Team",
                "",
                "alice",
                "",
                "bad/path",  # Invalid project
                "good/path",  # Valid project
                "",
                "",
            ]
        )
        + "\n"
    )

    runner = CliRunner()
    result = runner.invoke(main, ["init"], input=user_input)

    assert result.exit_code == 0, f"Output:\n{result.output}"
    assert "not found" in result.output
    assert "1 branches" in result.output


@patch("ai_fluency_collector.cli.GitLabClient")
def test_init_no_token(mock_client_cls, tmp_path, monkeypatch):
    """Test init fails gracefully when GITLAB_TOKEN is not set."""
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)

    user_input = (
        "\n".join(
            [
                "",  # GitLab URL
                "Team",
                "",  # Code
            ]
        )
        + "\n"
    )

    runner = CliRunner()
    result = runner.invoke(main, ["init"], input=user_input)

    assert result.exit_code != 0
    assert "GITLAB_TOKEN" in result.output


@patch("ai_fluency_collector.cli.GitLabClient")
def test_init_ci_discovery_with_tagging(mock_client_cls, tmp_path, monkeypatch):
    """Test CI pattern discovery and tagging flow."""
    monkeypatch.setenv("GITLAB_TOKEN", "test-token")
    monkeypatch.chdir(tmp_path)

    client = _mock_client()

    ci_content = yaml.dump(
        {
            "include": [
                {"template": "Security/SAST.gitlab-ci.yml"},
                {
                    "project": "platform/templates",
                    "file": "ai-review/.ai-code-review.yml",
                },
            ],
            "stages": ["test", "deploy"],
            "unit-test": {"script": ["pytest"]},
            "deploy-staging": {
                "stage": "deploy",
                "script": ["deploy.sh"],
                "environment": {"name": "staging"},
            },
        }
    )
    client.get_file_content.return_value = ci_content

    mock_client_cls.return_value = client

    user_input = (
        "\n".join(
            [
                "",  # GitLab URL
                "My Team",
                "",  # Code
                "alice",
                "",  # Finish members
                "group/proj",
                "",  # Finish projects
                "2",  # AI-related: item 2 (project include)
                "1",  # Security-related: item 1 (SAST template)
                "4",  # Deployment gates: item 4 (deploy-staging job)
                "",  # Output filename
            ]
        )
        + "\n"
    )

    runner = CliRunner()
    result = runner.invoke(main, ["init"], input=user_input)

    assert result.exit_code == 0, f"Output:\n{result.output}"
    assert "CI items" in result.output

    config_path = tmp_path / "my-team.yaml"
    assert config_path.exists()

    config = yaml.safe_load(config_path.read_text())
    ci_signals = config["team"].get("ci_signals", {})
    assert "ai-code-review" in ci_signals
    assert "sast-dast" in ci_signals
    assert "deployment-gates" in ci_signals


@patch("ai_fluency_collector.cli.GitLabClient")
def test_init_ci_discovery_skip_all(mock_client_cls, tmp_path, monkeypatch):
    """Test skipping all CI signal tagging."""
    monkeypatch.setenv("GITLAB_TOKEN", "test-token")
    monkeypatch.chdir(tmp_path)

    client = _mock_client()

    ci_content = yaml.dump(
        {
            "stages": ["test"],
            "unit-test": {"script": ["pytest"]},
        }
    )
    client.get_file_content.return_value = ci_content

    mock_client_cls.return_value = client

    user_input = (
        "\n".join(
            [
                "",
                "My Team",
                "",
                "alice",
                "",
                "group/proj",
                "",
                "skip",  # AI: skip
                "skip",  # Security: skip
                "skip",  # Deploy: skip
                "",  # Filename
            ]
        )
        + "\n"
    )

    runner = CliRunner()
    result = runner.invoke(main, ["init"], input=user_input)

    assert result.exit_code == 0, f"Output:\n{result.output}"

    config_path = tmp_path / "my-team.yaml"
    config = yaml.safe_load(config_path.read_text())
    assert "ci_signals" not in config["team"]


@patch("ai_fluency_collector.cli.GitLabClient")
def test_init_no_ci_file(mock_client_cls, tmp_path, monkeypatch):
    """Test init when projects have no .gitlab-ci.yml."""
    monkeypatch.setenv("GITLAB_TOKEN", "test-token")
    monkeypatch.chdir(tmp_path)

    client = _mock_client()
    client.get_file_content.return_value = None
    mock_client_cls.return_value = client

    user_input = (
        "\n".join(
            [
                "",
                "My Team",
                "",
                "alice",
                "",
                "group/proj",
                "",
                "",  # Filename
            ]
        )
        + "\n"
    )

    runner = CliRunner()
    result = runner.invoke(main, ["init"], input=user_input)

    assert result.exit_code == 0, f"Output:\n{result.output}"
    assert "No CI items found" in result.output or "No .gitlab-ci.yml found" in result.output


@patch("ai_fluency_collector.cli.GitLabClient")
def test_init_custom_output_filename(mock_client_cls, tmp_path, monkeypatch):
    """Test init with a custom output filename."""
    monkeypatch.setenv("GITLAB_TOKEN", "test-token")
    monkeypatch.chdir(tmp_path)

    client = _mock_client()
    client.get_file_content.return_value = None
    mock_client_cls.return_value = client

    user_input = (
        "\n".join(
            [
                "",
                "My Team",
                "",
                "alice",
                "",
                "group/proj",
                "",
                "custom-config.yaml",  # Custom filename
            ]
        )
        + "\n"
    )

    runner = CliRunner()
    result = runner.invoke(main, ["init"], input=user_input)

    assert result.exit_code == 0, f"Output:\n{result.output}"
    assert "custom-config.yaml" in result.output
    assert (tmp_path / "custom-config.yaml").exists()
