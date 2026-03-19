from __future__ import annotations

import json
from pathlib import Path


def build_output(
    team_code: str,
    survey_period: str,
    artifact_signals: list[dict],
    ci_signals: list[dict],
    member_signals: list[dict] | None = None,
    review_signals: list[dict] | None = None,
) -> dict:
    """Build the output dict matching the ai-fluency import schema.

    Omits any source that produced zero signals.
    """
    sources = []

    if artifact_signals:
        sources.append(
            {
                "source_id": "gitlab-repo-artifacts",
                "signals": artifact_signals,
            }
        )

    if ci_signals:
        sources.append(
            {
                "source_id": "gitlab-ci-config",
                "signals": ci_signals,
            }
        )

    if member_signals:
        sources.append(
            {
                "source_id": "gitlab-member-activity",
                "signals": member_signals,
            }
        )

    if review_signals:
        sources.append(
            {
                "source_id": "gitlab-review-signals",
                "signals": review_signals,
            }
        )

    return {
        "team_code": team_code,
        "survey_period": survey_period,
        "sources": sources,
    }


def write_output(data: dict, team_code: str, survey_period: str) -> str:
    """Write the output JSON to {team_code}-{survey_period}.json.

    Returns the file path.
    """
    filename = f"{team_code}-{survey_period}.json"
    path = Path.cwd() / filename
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    return str(path)
