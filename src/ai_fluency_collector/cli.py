from __future__ import annotations

import os
import re
from datetime import date

import click

from ai_fluency_collector.config import load_config
from ai_fluency_collector.gitlab_client import (
    GitLabAccessError,
    GitLabAuthError,
    GitLabClient,
    GitLabServerError,
    GitLabUserNotFoundError,
)
from ai_fluency_collector.output import build_output, write_output
from ai_fluency_collector.scanners.artifact_scanner import ARTIFACT_DEFINITIONS, ArtifactScanner
from ai_fluency_collector.scanners.ci_scanner import CI_PATTERN_IDS, CIScanner
from ai_fluency_collector.scanners.member_scanner import MemberScanner
from ai_fluency_collector.scoring import (
    ARTIFACT_SKILL_MAPPINGS,
    CI_SKILL_MAPPINGS,
    MEMBER_SKILL_MAPPINGS,
    calculate_member_scores,
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
@click.option(
    "--gitlab-url",
    default=None,
    help="GitLab instance URL (overrides config value; defaults to https://gitlab.com).",
)
@click.option(
    "--validate",
    is_flag=True,
    default=False,
    help="Test the connection, list accessible projects, and exit without scanning.",
)
@click.option(
    "--verbose",
    is_flag=True,
    default=False,
    help="Show detailed debug output during scanning.",
)
def main(
    config_path: str,
    period: str | None,
    gitlab_url: str | None,
    validate: bool,
    verbose: bool,
) -> None:
    """Scan GitLab repositories for AI adoption signals."""
    # 1. Load and validate config
    try:
        team = load_config(config_path)
    except FileNotFoundError as e:
        raise click.ClickException(str(e)) from e
    except ValueError as e:
        raise click.ClickException(str(e)) from e

    # 2. Resolve gitlab_url: CLI flag overrides config value
    effective_gitlab_url = gitlab_url if gitlab_url is not None else team.gitlab_url

    # 3. Validate period
    if period is None:
        period = current_iso_week()
    else:
        validate_period(period)

    # 4. Check GITLAB_TOKEN
    token = os.environ.get("GITLAB_TOKEN")
    if not token:
        raise click.ClickException(
            "GITLAB_TOKEN environment variable is not set. Export a token with read_api scope."
        )

    # 5. Validate token against GitLab API
    client = GitLabClient(token, base_url=effective_gitlab_url)
    try:
        client.validate_token()
    except (GitLabAuthError, GitLabServerError) as e:
        raise click.ClickException(str(e)) from e

    # 6. --validate mode: test connection, list projects, and exit
    if validate:
        click.echo("AI Fluency Collector — Validation Mode")
        click.echo(f"  GitLab:   {effective_gitlab_url}")
        click.echo(f"  Team:     {team.name}")
        click.echo("  Token:    valid")
        click.echo()
        click.echo("Checking project access...")
        for project in team.projects:
            try:
                client.get_branches(project)
                click.echo(f"  {project}: accessible")
            except (GitLabAccessError, GitLabAuthError, GitLabServerError) as e:
                click.echo(f"  {project}: ERROR - {e}")
        click.echo()
        click.echo("Validation complete.")
        return

    # 7. Print startup banner
    output_file = f"{team.code}-{period}.json"
    click.echo("AI Fluency Collector")
    click.echo(f"  GitLab:   {effective_gitlab_url}")
    click.echo(f"  Team:     {team.name}")
    click.echo(f"  Members:  {len(team.members)}")
    click.echo(f"  Projects: {len(team.projects)}")
    click.echo(f"  Period:   {period}")
    click.echo(f"  Output:   {output_file}")
    click.echo()

    # 8. Scan for repo artifacts
    click.echo("Scanning for repo artifacts...")
    scanner = ArtifactScanner(client)
    all_artifact_results: list[dict[str, bool]] = []

    for project in team.projects:
        if verbose:
            from ai_fluency_collector.scanners.artifact_scanner import (
                _get_active_branches,
            )

            branches = _get_active_branches(client, project)
            click.echo(f"    [{project}] {len(branches)} active branches found")
            for b in branches:
                click.echo(f"      {b['name']} (weight={b['weight']})")
            if not branches:
                click.echo("      (falling back to HEAD)")

        try:
            result = scanner.scan_project(project)
        except (GitLabAccessError, GitLabAuthError, GitLabServerError) as e:
            raise click.ClickException(str(e)) from e

        if verbose:
            for aid, weight in result.items():
                if weight > 0:
                    click.echo(f"      found {aid} (weight={weight})")

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
        except (GitLabAccessError, GitLabAuthError, GitLabServerError) as e:
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

    # 10. Scan member activity
    click.echo("Scanning member activity...")
    member_scanner = MemberScanner(client, team.projects)
    try:
        member_results = member_scanner.scan_all_members(team.members)
    except (GitLabUserNotFoundError, GitLabServerError) as e:
        raise click.ClickException(str(e)) from e

    for result in member_results:
        if result.ai_coauthor_counts:
            patterns = ", ".join(f"{k}: {v}" for k, v in result.ai_coauthor_counts.items())
            click.echo(
                f"  {result.username}: {result.repos_discovered} repos discovered, {patterns}"
            )
        else:
            click.echo(
                f"  {result.username}: {result.repos_discovered} repos discovered, "
                f"no AI co-author commits"
            )

    # 11. Calculate member activity scores
    member_signals = calculate_member_scores(member_results, MEMBER_SKILL_MAPPINGS)
    click.echo(f"  → {len(member_signals)} member activity signals detected")
    click.echo()

    # 12. Build and write output JSON
    data = build_output(team.code, period, artifact_signals, ci_signals, member_signals)
    output_path = write_output(data, team.code, period)

    # 13. Print summary
    total_signals = len(artifact_signals) + len(ci_signals) + len(member_signals)
    num_sources = len(data["sources"])
    click.echo("Summary")
    click.echo(f"  File:    {output_path}")
    click.echo(f"  Sources: {num_sources}")
    click.echo(f"  Signals: {total_signals}")
    click.echo(f"  Team:    {team.code}")
