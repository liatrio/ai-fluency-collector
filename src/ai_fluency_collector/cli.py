from __future__ import annotations

import os
import re
from datetime import date

import click

from ai_fluency_collector.config import load_config
from ai_fluency_collector.gitlab_client import GitLabAccessError, GitLabAuthError, GitLabClient
from ai_fluency_collector.output import build_output, write_output
from ai_fluency_collector.scanners.artifact_scanner import ARTIFACT_DEFINITIONS, ArtifactScanner
from ai_fluency_collector.scanners.ci_scanner import CI_PATTERN_IDS, CIScanner
from ai_fluency_collector.scoring import (
    ARTIFACT_SKILL_MAPPINGS,
    CI_SKILL_MAPPINGS,
    calculate_scores,
)

PERIOD_PATTERN = re.compile(r"^\d{4}-W(0[1-9]|[1-4]\d|5[0-3])$")


def current_iso_week() -> str:
    """Return the current ISO week as YYYY-WNN."""
    today = date.today()
    iso = today.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def validate_period(period: str) -> str:
    """Validate and return the period string in YYYY-WNN format."""
    if not PERIOD_PATTERN.match(period):
        raise click.BadParameter(
            f"Invalid period format: {period}. Expected YYYY-WNN (e.g. 2026-W12)"
        )
    return period


@click.command()
@click.option(
    "--config",
    "config_path",
    required=True,
    help="Path to team configuration YAML file.",
)
@click.option(
    "--period",
    default=None,
    help="Survey period in YYYY-WNN format (defaults to current ISO week).",
)
def main(config_path: str, period: str | None) -> None:
    """Scan GitLab repositories for AI adoption signals."""
    # 1. Load and validate config
    try:
        team = load_config(config_path)
    except FileNotFoundError as e:
        raise click.ClickException(str(e)) from e
    except ValueError as e:
        raise click.ClickException(str(e)) from e

    # 2. Validate period
    if period is None:
        period = current_iso_week()
    else:
        validate_period(period)

    # 3. Check GITLAB_TOKEN
    token = os.environ.get("GITLAB_TOKEN")
    if not token:
        raise click.ClickException(
            "GITLAB_TOKEN environment variable is not set. Export a token with read_api scope."
        )

    # 4. Validate token against GitLab API
    client = GitLabClient(token)
    try:
        client.validate_token()
    except GitLabAuthError as e:
        raise click.ClickException(str(e)) from e

    # 5. Print startup banner
    output_file = f"{team.code}-{period}.json"
    click.echo("AI Fluency Collector")
    click.echo(f"  Team:     {team.name}")
    click.echo(f"  Projects: {len(team.projects)}")
    click.echo(f"  Period:   {period}")
    click.echo(f"  Output:   {output_file}")
    click.echo()

    # 6. Scan for repo artifacts
    click.echo("Scanning for repo artifacts...")
    scanner = ArtifactScanner(client)
    all_artifact_results: list[dict[str, bool]] = []

    for project in team.projects:
        try:
            result = scanner.scan_project(project)
        except (GitLabAccessError, GitLabAuthError) as e:
            raise click.ClickException(str(e)) from e

        all_artifact_results.append(result)
        found = [aid for aid, present in result.items() if present]
        if found:
            names = []
            for aid in found:
                for defn in ARTIFACT_DEFINITIONS:
                    if defn["id"] == aid:
                        names.append(defn["name"])
                        break
            click.echo(f"  {project}: {', '.join(names)}")
        else:
            click.echo(f"  {project}: no artifacts found")

    # 7. Calculate artifact scores
    artifact_signals = calculate_scores(all_artifact_results, ARTIFACT_SKILL_MAPPINGS)
    click.echo(f"  → {len(artifact_signals)} artifact signals detected")
    click.echo()

    # 8. Scan for CI config patterns
    click.echo("Scanning CI configurations...")
    ci_scanner = CIScanner(client)
    all_ci_results: list[dict[str, bool]] = []

    for project in team.projects:
        try:
            result = ci_scanner.scan_project(project)
        except (GitLabAccessError, GitLabAuthError) as e:
            raise click.ClickException(str(e)) from e

        all_ci_results.append(result)
        found = [pid for pid in CI_PATTERN_IDS if result.get(pid, False)]
        if found:
            click.echo(f"  {project}: {', '.join(found)}")
        else:
            click.echo(f"  {project}: no CI patterns found")

    # 9. Calculate CI scores
    ci_signals = calculate_scores(all_ci_results, CI_SKILL_MAPPINGS)
    click.echo(f"  → {len(ci_signals)} CI signals detected")
    click.echo()

    # 10. Build and write output JSON
    data = build_output(team.code, period, artifact_signals, ci_signals)
    output_path = write_output(data, team.code, period)

    # 11. Print summary
    total_signals = len(artifact_signals) + len(ci_signals)
    num_sources = len(data["sources"])
    click.echo("Summary")
    click.echo(f"  File:    {output_path}")
    click.echo(f"  Sources: {num_sources}")
    click.echo(f"  Signals: {total_signals}")
    click.echo(f"  Team:    {team.code}")
