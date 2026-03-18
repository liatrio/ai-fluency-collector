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
            "members": ["Alice"],
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
    assert team.members == ["Alice"]
    assert team.projects == ["group/project-one", "group/project-two"]


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
    config = {"team": {"name": "T", "projects": ["a/b"]}}
    path = tmp_path / "no-code.yaml"
    path.write_text(yaml.dump(config))
    with pytest.raises(ValueError, match="team.code"):
        load_config(str(path))


def test_missing_team_name(tmp_path):
    config = {"team": {"code": "t", "projects": ["a/b"]}}
    path = tmp_path / "no-name.yaml"
    path.write_text(yaml.dump(config))
    with pytest.raises(ValueError, match="team.name"):
        load_config(str(path))


def test_missing_team_projects(tmp_path):
    config = {"team": {"name": "T", "code": "t"}}
    path = tmp_path / "no-projects.yaml"
    path.write_text(yaml.dump(config))
    with pytest.raises(ValueError, match="team.projects"):
        load_config(str(path))


def test_empty_projects_list(tmp_path):
    config = {"team": {"name": "T", "code": "t", "projects": []}}
    path = tmp_path / "empty-projects.yaml"
    path.write_text(yaml.dump(config))
    with pytest.raises(ValueError, match="non-empty list"):
        load_config(str(path))


def test_members_defaults_to_empty(tmp_path):
    config = {"team": {"name": "T", "code": "t", "projects": ["a/b"]}}
    path = tmp_path / "no-members.yaml"
    path.write_text(yaml.dump(config))
    team = load_config(str(path))
    assert team.members == []
