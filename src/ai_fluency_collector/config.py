from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class TeamConfig:
    name: str
    code: str
    members: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    gitlab_url: str = "https://gitlab.com"
    ci_signals: dict[str, list[str]] = field(default_factory=dict)


def load_config(path: str) -> TeamConfig:
    """Load and validate a team configuration YAML file.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If required fields are missing or invalid.
    """
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {path}. Create one from config.example.yaml"
        )

    try:
        with open(config_path) as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Failed to parse {path}: {e}") from e

    if not isinstance(raw, dict) or "team" not in raw:
        raise ValueError("Missing required field: team")

    team = raw["team"]
    if not isinstance(team, dict):
        raise ValueError("Missing required field: team (must be a mapping)")

    missing = []
    if not team.get("name"):
        missing.append("team.name")
    if not team.get("code"):
        missing.append("team.code")
    if "members" not in team:
        missing.append("team.members")
    if "projects" not in team:
        missing.append("team.projects")

    if missing:
        raise ValueError(f"Missing required field: {', '.join(missing)}")

    members = team["members"]
    if not isinstance(members, list) or len(members) == 0:
        raise ValueError("team.members must be a non-empty list of GitLab usernames")

    projects = team["projects"]
    if not isinstance(projects, list) or len(projects) == 0:
        raise ValueError("team.projects must be a non-empty list")

    gitlab_url = team.get("gitlab_url", "https://gitlab.com")
    if not isinstance(gitlab_url, str) or not gitlab_url:
        raise ValueError("team.gitlab_url must be a non-empty string")

    ci_signals: dict[str, list[str]] = {}
    raw_signals = team.get("ci_signals")
    if raw_signals is not None:
        if not isinstance(raw_signals, dict):
            raise ValueError("team.ci_signals must be a mapping")
        for key, val in raw_signals.items():
            if not isinstance(val, list):
                raise ValueError(f"team.ci_signals.{key} must be a list of strings")
            ci_signals[key] = [str(v) for v in val]

    return TeamConfig(
        name=team["name"],
        code=team["code"],
        members=members,
        projects=projects,
        gitlab_url=gitlab_url,
        ci_signals=ci_signals,
    )
