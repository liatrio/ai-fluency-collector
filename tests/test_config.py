from __future__ import annotations

import pytest
import yaml

from ai_fluency_collector.config import TeamConfig, load_config


@pytest.fixture()
def valid_config(tmp_path):
    config = {
        "team": {
            "name": "Test Team",
            "code": "test-team",
            "members": ["alice.smith", "bob.jones"],
            "projects": ["group/project-one", "group/project-two"],
        }
    }
    path = tmp_path / "team.yaml"
    path.write_text(yaml.dump(config))
    return str(path)


def test_load_valid_config(valid_config):
    team = load_config(valid_config)
    assert isinstance(team, TeamConfig)
    assert team.name == "Test Team"
    assert team.code == "test-team"
    assert team.members == ["alice.smith", "bob.jones"]
    assert team.projects == ["group/project-one", "group/project-two"]
    assert team.gitlab_url == "https://gitlab.com"


def test_gitlab_url_from_config(tmp_path):
    config = {
        "team": {
            "name": "Test Team",
            "code": "test-team",
            "gitlab_url": "https://gitlab.example.com",
            "members": ["alice.smith"],
            "projects": ["group/project-one"],
        }
    }
    path = tmp_path / "team.yaml"
    path.write_text(yaml.dump(config))
    team = load_config(str(path))
    assert team.gitlab_url == "https://gitlab.example.com"


def test_gitlab_url_defaults_when_missing(tmp_path):
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
    team = load_config(str(path))
    assert team.gitlab_url == "https://gitlab.com"


def test_missing_file():
    with pytest.raises(FileNotFoundError, match="Config file not found"):
        load_config("/nonexistent/path.yaml")


def test_invalid_yaml(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(":\n  - :\n  bad: [")
    with pytest.raises(ValueError, match="Failed to parse"):
        load_config(str(path))


def test_missing_team_key(tmp_path):
    path = tmp_path / "no-team.yaml"
    path.write_text(yaml.dump({"other": "data"}))
    with pytest.raises(ValueError, match="Missing required field: team"):
        load_config(str(path))


def test_missing_team_code(tmp_path):
    config = {"team": {"name": "T", "members": ["u"], "projects": ["a/b"]}}
    path = tmp_path / "no-code.yaml"
    path.write_text(yaml.dump(config))
    with pytest.raises(ValueError, match="team.code"):
        load_config(str(path))


def test_missing_team_name(tmp_path):
    config = {"team": {"code": "t", "members": ["u"], "projects": ["a/b"]}}
    path = tmp_path / "no-name.yaml"
    path.write_text(yaml.dump(config))
    with pytest.raises(ValueError, match="team.name"):
        load_config(str(path))


def test_missing_team_members_is_allowed(tmp_path):
    """members field is optional; omitting it yields an empty list."""
    config = {"team": {"name": "T", "code": "t", "projects": ["a/b"]}}
    path = tmp_path / "no-members.yaml"
    path.write_text(yaml.dump(config))
    result = load_config(str(path))
    assert result.members == []


def test_empty_members_list_is_allowed(tmp_path):
    """An empty members list is valid; username source is resolved in cli.py."""
    config = {"team": {"name": "T", "code": "t", "members": [], "projects": ["a/b"]}}
    path = tmp_path / "empty-members.yaml"
    path.write_text(yaml.dump(config))
    result = load_config(str(path))
    assert result.members == []


def test_scan_from_to_loaded_from_config(tmp_path):
    config = {
        "team": {
            "name": "T",
            "code": "t",
            "members": ["u"],
            "projects": ["a/b"],
            "scan_from": "2026-01-01",
            "scan_to": "2026-03-19",
        }
    }
    path = tmp_path / "with-dates.yaml"
    path.write_text(yaml.dump(config))
    result = load_config(str(path))
    assert result.scan_from == "2026-01-01"
    assert result.scan_to == "2026-03-19"


def test_scan_from_to_absent_by_default(valid_config):
    result = load_config(valid_config)
    assert result.scan_from is None
    assert result.scan_to is None


def test_scan_from_invalid_format(tmp_path):
    config = {
        "team": {
            "name": "T",
            "code": "t",
            "projects": ["a/b"],
            "scan_from": "01/01/2026",
            "scan_to": "2026-03-19",
        }
    }
    path = tmp_path / "bad-from.yaml"
    path.write_text(yaml.dump(config))
    with pytest.raises(ValueError, match="scan_from must be in YYYY-MM-DD"):
        load_config(str(path))


def test_scan_from_without_scan_to_errors(tmp_path):
    config = {
        "team": {
            "name": "T",
            "code": "t",
            "projects": ["a/b"],
            "scan_from": "2026-01-01",
        }
    }
    path = tmp_path / "from-only.yaml"
    path.write_text(yaml.dump(config))
    with pytest.raises(ValueError, match="scan_from and team.scan_to must both be set"):
        load_config(str(path))


def test_missing_team_projects_is_allowed(tmp_path):
    """projects is optional; omitting it yields an empty list (validated at scan time)."""
    config = {"team": {"name": "T", "code": "t", "members": ["u"]}}
    path = tmp_path / "no-projects.yaml"
    path.write_text(yaml.dump(config))
    result = load_config(str(path))
    assert result.projects == []


def test_empty_projects_list_is_allowed(tmp_path):
    """An empty projects list is valid for GitHub-only teams."""
    config = {"team": {"name": "T", "code": "t", "members": ["u"], "projects": []}}
    path = tmp_path / "empty-projects.yaml"
    path.write_text(yaml.dump(config))
    result = load_config(str(path))
    assert result.projects == []
