from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import click
import yaml

from ai_fluency_collector.config import load_config
from ai_fluency_collector.gitlab_client import (
    GitLabAccessError,
    GitLabAuthError,
    GitLabClient,
    GitLabRateLimitError,
    GitLabServerError,
    GitLabTimeoutError,
    GitLabUserNotFoundError,
)
from ai_fluency_collector.gitlab_scoring import (
    ARTIFACT_SKILL_MAPPINGS,
    CI_EXECUTION_SKILL_MAPPINGS,
    CI_PIPELINE_SKILL_MAPPINGS,
    CI_SKILL_MAPPINGS,
    COVERAGE_SKILL_MAPPINGS,
    MEMBER_SKILL_MAPPINGS,
    MR_COAUTHOR_SKILL_MAPPINGS,
    MR_CODING_TIME_SKILL_MAPPINGS,
    MR_SIZE_SKILL_MAPPINGS,
    REVIEW_SKILL_MAPPINGS,
    calculate_ci_execution_scores,
    calculate_coverage_scores,
    calculate_member_scores,
    calculate_mr_coauthor_scores,
    calculate_mr_signals,
    calculate_pipeline_scores,
    calculate_review_scores,
    calculate_scores,
)
from ai_fluency_collector.output import build_output, write_output
from ai_fluency_collector.scanners.gitlab_artifact_scanner import (
    ARTIFACT_DEFINITIONS,
    ArtifactScanner,
)
from ai_fluency_collector.scanners.gitlab_ci_scanner import CI_PATTERN_IDS, CIScanner
from ai_fluency_collector.scanners.gitlab_member_scanner import MemberScanner
from ai_fluency_collector.scanners.gitlab_mr_scanner import MRScanner
from ai_fluency_collector.scanners.gitlab_review_scanner import ReviewScanner

PERIOD_PATTERN = re.compile(r"^\d{4}-W(0[1-9]|[1-4]\d|5[0-3])$")

# Convenience tuple for catching all recoverable GitLab API errors in one except clause.
_GITLAB_ERRORS = (
    GitLabAccessError,
    GitLabAuthError,
    GitLabRateLimitError,
    GitLabServerError,
    GitLabTimeoutError,
)


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


def _parse_date(date_str: str) -> date:
    """Parse a YYYY-MM-DD string, raising BadParameter on bad input."""
    try:
        return date.fromisoformat(date_str)
    except ValueError:
        raise click.BadParameter(
            f"Invalid date format: {date_str}. Expected YYYY-MM-DD (e.g. 2026-01-01)"
        ) from None


def _dates_to_iso_weeks(from_str: str, to_str: str) -> list[str]:
    """Return every ISO week (YYYY-WNN) that overlaps the given date range, inclusive.

    Starts from the Monday of the week containing from_date and advances
    seven days at a time until past to_date.
    """
    from_date = _parse_date(from_str)
    to_date = _parse_date(to_str)
    if from_date > to_date:
        raise click.BadParameter("--from must be earlier than --to")
    # Snap to Monday of the first week so we don't skip a partial week
    from_iso = from_date.isocalendar()
    current = date.fromisocalendar(from_iso[0], from_iso[1], 1)
    weeks: list[str] = []
    while current <= to_date:
        iso = current.isocalendar()
        weeks.append(f"{iso[0]}-W{iso[1]:02d}")
        current += timedelta(days=7)
    return weeks


def _prior_iso_week(period: str) -> str:
    """Return the ISO week immediately before the given YYYY-WNN period."""
    year = int(period[:4])
    week = int(period[6:])
    monday = date.fromisocalendar(year, week, 1)
    prior_monday = monday - timedelta(days=7)
    iso = prior_monday.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _period_start_date(periods: list[str]) -> date:
    """Return the Monday of the earliest week in the periods list."""
    earliest = min(periods)
    year = int(earliest[:4])
    week = int(earliest[6:])
    return date.fromisocalendar(year, week, 1)


def _period_end_date(periods: list[str]) -> date:
    """Return the Sunday of the latest week in the periods list."""
    latest = max(periods)
    year = int(latest[:4])
    week = int(latest[6:])
    return date.fromisocalendar(year, week, 7)


def _slugify(text: str) -> str:
    """Convert text to a URL-friendly slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


AFC_BANNER = r"""
     ___       _______ ______
    /   \     |   ____/      |
   /  ^  \    |  |_  |  ,----'
  /  /_\  \   |   _] |  |
 /  _____  \  |  |   |  `----.
/__/     \__\ |__|    \______|
"""


@click.group()
def main():
    """AI Fluency Collector - Scan GitLab repositories for AI adoption signals."""


@main.command()
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
    "--from",
    "from_date",
    default=None,
    help="Range start date YYYY-MM-DD. Use with --to to scan multiple weeks.",
)
@click.option(
    "--to",
    "to_date",
    default=None,
    help="Range end date YYYY-MM-DD. Use with --from to scan multiple weeks.",
)
@click.option(
    "--usernames",
    default=None,
    help="Comma-separated GitLab usernames (overrides config members; also TEAM_USERNAMES env).",
)
@click.option(
    "--verbose",
    is_flag=True,
    default=False,
    help="Show detailed debug output during scanning.",
)
def scan(
    config_path: str,
    period: str | None,
    gitlab_url: str | None,
    validate: bool,
    from_date: str | None,
    to_date: str | None,
    usernames: str | None,
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

    # 2. Resolve effective team members (CLI flag → env var → config)
    if usernames:
        effective_members = [u.strip() for u in usernames.split(",") if u.strip()]
    else:
        env_usernames = os.environ.get("TEAM_USERNAMES", "")
        if env_usernames:
            effective_members = [u.strip() for u in env_usernames.split(",") if u.strip()]
        else:
            effective_members = team.members

    if not effective_members:
        raise click.ClickException(
            "No team members specified. "
            "Provide --usernames flag, TEAM_USERNAMES env var, or members in config file."
        )

    # 4. Resolve gitlab_url: CLI flag overrides config value
    effective_gitlab_url = gitlab_url if gitlab_url is not None else team.gitlab_url
    # Auto-add https:// if missing
    if not effective_gitlab_url.startswith(("http://", "https://")):
        effective_gitlab_url = f"https://{effective_gitlab_url}"
    effective_gitlab_url = effective_gitlab_url.rstrip("/")

    # 5. Resolve periods to scan
    # Precedence: CLI --from/--to → config scan_from/scan_to → CLI --period → current week
    if (from_date is None) != (to_date is None):
        raise click.ClickException("--from and --to must be used together.")

    effective_from = from_date or team.scan_from
    effective_to = to_date or team.scan_to

    if effective_from and period:
        raise click.ClickException("--from/--to and --period are mutually exclusive.")

    if effective_from:
        try:
            periods = _dates_to_iso_weeks(effective_from, effective_to)
        except click.BadParameter as e:
            raise click.ClickException(str(e)) from e
    else:
        if period is None:
            period = current_iso_week()
        else:
            validate_period(period)
        periods = [period]

    # 6. Check GITLAB_TOKEN
    token = os.environ.get("GITLAB_TOKEN")
    if not token:
        raise click.ClickException(
            "GITLAB_TOKEN environment variable is not set. Export a token with read_api scope."
        )

    # 7. Validate token against GitLab API
    client = GitLabClient(token, base_url=effective_gitlab_url)
    try:
        client.validate_token()
    except (GitLabAuthError, GitLabServerError) as e:
        raise click.ClickException(str(e)) from e

    # 8. --validate mode: test connection, list projects, and exit
    if validate:
        click.echo(AFC_BANNER)
        click.echo("Validation Mode")
        click.echo(f"  GitLab:   {effective_gitlab_url}")
        click.echo(f"  Team:     {team.name}")
        click.echo("  Token:    valid")
        click.echo()
        click.echo("Checking project access...")
        for project in team.projects:
            try:
                client.get_branches(project)
                click.echo(f"  {project}: accessible")
            except _GITLAB_ERRORS as e:
                click.echo(f"  {project}: ERROR - {e}")
        click.echo()
        click.echo("Validation complete.")
        return

    # 9. Print startup banner
    multi_week = len(periods) > 1
    if multi_week:
        period_display = f"{periods[0]} → {periods[-1]} ({len(periods)} weeks)"
        output_display = f"{team.code}-{periods[0]}.json … {team.code}-{periods[-1]}.json"
    else:
        period_display = periods[0]
        output_display = f"{team.code}-{periods[0]}.json"

    click.echo(AFC_BANNER)
    click.echo(f"  GitLab:   {effective_gitlab_url}")
    click.echo(f"  Team:     {team.name}")
    click.echo(f"  Members:  {len(effective_members)}")
    click.echo(f"  Projects: {len(team.projects)}")
    click.echo(f"  Period:   {period_display}")
    click.echo(f"  Output:   {output_display}")
    click.echo()

    # 10. Compute period-derived dates for scanners
    reference_date = _period_end_date(periods)
    since_date = _period_start_date(periods).isoformat()

    # 11. Scan for repo artifacts (period-scoped — active branches relative to period end)
    click.echo("Scanning for repo artifacts...")
    scanner = ArtifactScanner(client, reference_date=reference_date)
    all_artifact_results: list[dict[str, bool]] = []

    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            artifact_scan_results = list(executor.map(scanner.scan_project, team.projects))
    except _GITLAB_ERRORS as e:
        raise click.ClickException(str(e)) from e

    for project, result in zip(team.projects, artifact_scan_results):
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

    # 11. Calculate artifact scores
    artifact_signals = calculate_scores(all_artifact_results, ARTIFACT_SKILL_MAPPINGS)
    click.echo(f"  → {len(artifact_signals)} artifact signals detected")
    click.echo()

    # 12. Scan for CI config patterns (period-scoped — active branches relative to period end)
    click.echo("Scanning CI configurations...")
    ci_scanner = CIScanner(client, ci_signals=team.ci_signals, reference_date=reference_date)
    all_ci_results: list[dict[str, bool]] = []

    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            ci_scan_results = list(executor.map(ci_scanner.scan_project, team.projects))
    except _GITLAB_ERRORS as e:
        raise click.ClickException(str(e)) from e

    for project, result in zip(team.projects, ci_scan_results):
        all_ci_results.append(result)
        found = [pid for pid in CI_PATTERN_IDS if result.get(pid, False)]
        if found:
            click.echo(f"  {project}: {', '.join(found)}")
        else:
            click.echo(f"  {project}: no CI patterns found")

    # 13. Calculate CI scores
    ci_signals = calculate_scores(all_ci_results, CI_SKILL_MAPPINGS)
    click.echo(f"  → {len(ci_signals)} CI signals detected")
    click.echo()

    # 14. Scan member activity (period-scoped — commits since period start)
    click.echo("Scanning member activity...")
    member_scanner = MemberScanner(client, team.projects, since_date=since_date)
    try:
        member_results = member_scanner.scan_all_members(effective_members)
    except (GitLabUserNotFoundError, GitLabServerError) as e:
        raise click.ClickException(str(e)) from e

    total_repos = sum(r.repos_discovered for r in member_results)
    members_with_ai = sum(1 for r in member_results if r.ai_coauthor_counts)
    click.echo(f"  {total_repos} repos discovered across team")
    click.echo(f"  {members_with_ai}/{len(effective_members)} members with AI co-author commits")
    if verbose:
        pattern_totals: dict[str, int] = {}
        for result in member_results:
            for k, v in result.ai_coauthor_counts.items():
                pattern_totals[k] = pattern_totals.get(k, 0) + v
        for pattern, total in pattern_totals.items():
            click.echo(f"    {pattern}: {total} commits")

    # 15. Calculate member activity scores
    member_signals = calculate_member_scores(member_results, MEMBER_SKILL_MAPPINGS)
    click.echo(f"  → {len(member_signals)} member activity signals detected")
    click.echo()

    # 16–18. Per-week: pipeline pass rate + review signals → output file
    review_scanner = ReviewScanner(client)
    mr_scanner = MRScanner(client)
    output_paths: list[str] = []
    total_signals_all = len(artifact_signals) + len(ci_signals) + len(member_signals)

    for idx, week in enumerate(periods, 1):
        if multi_week:
            click.echo(f"Scanning week {week} ({idx}/{len(periods)})...")
        else:
            click.echo("Scanning pipeline pass rates and MR review patterns...")

        # Pipeline pass rate (period-specific CI signal)
        try:
            with ThreadPoolExecutor(max_workers=8) as executor:
                pipeline_results = list(
                    executor.map(
                        lambda p: ci_scanner.scan_pipeline_pass_rate(p, week), team.projects
                    )
                )
        except _GITLAB_ERRORS as e:
            raise click.ClickException(str(e)) from e
        for project in team.projects:
            click.echo(f"  Scanning pipelines for {project}...")
        pipeline_signals = calculate_pipeline_scores(pipeline_results, CI_PIPELINE_SKILL_MAPPINGS)
        total_pipelines = sum(r.total_count for r in pipeline_results)
        click.echo(f"  {total_pipelines} pipelines analyzed across projects")
        click.echo(f"  → {len(pipeline_signals)} pipeline signals detected")

        # Coverage delta (current period vs prior period)
        prior_week = _prior_iso_week(week)
        current_coverage = []
        prior_coverage = []

        def _scan_coverage_pair(project: str) -> tuple:
            return (
                ci_scanner.scan_coverage(project, week),
                ci_scanner.scan_coverage(project, prior_week),
            )

        try:
            with ThreadPoolExecutor(max_workers=8) as executor:
                coverage_pairs = list(executor.map(_scan_coverage_pair, team.projects))
        except _GITLAB_ERRORS as e:
            raise click.ClickException(str(e)) from e
        for project, (curr, prior) in zip(team.projects, coverage_pairs):
            click.echo(f"  Scanning coverage for {project}...")
            current_coverage.append(curr)
            prior_coverage.append(prior)
        coverage_signals = calculate_coverage_scores(
            current_coverage, prior_coverage, COVERAGE_SKILL_MAPPINGS
        )
        click.echo(f"  → {len(coverage_signals)} coverage signals detected")

        # CI execution verification (check if configured patterns actually ran)
        click.echo("  Checking CI job execution...")
        execution_results = []
        try:
            for project, ci_result in zip(team.projects, ci_scan_results):
                exec_result = ci_scanner.scan_ci_execution(project, week, ci_result)
                execution_results.append(exec_result)
        except _GITLAB_ERRORS as e:
            raise click.ClickException(str(e)) from e

        execution_signals = calculate_ci_execution_scores(
            execution_results, CI_EXECUTION_SKILL_MAPPINGS
        )
        configured_count = sum(len(r.pattern_stats) for r in execution_results)
        running_count = sum(
            1
            for r in execution_results
            for _pid, (passed, ran, checked) in r.pattern_stats.items()
            if ran > 0
        )
        if configured_count > 0:
            click.echo(
                f"  {running_count}/{configured_count} configured CI patterns verified as running"
            )
        click.echo(f"  → {len(execution_signals)} execution signals detected")

        week_ci_signals = ci_signals + pipeline_signals + coverage_signals + execution_signals

        review_metrics = review_scanner.scan(effective_members, week)
        review_signals = calculate_review_scores(review_metrics, REVIEW_SKILL_MAPPINGS)
        mr_coauthor_signals = calculate_mr_coauthor_scores(
            review_metrics, MR_COAUTHOR_SKILL_MAPPINGS
        )
        click.echo(f"  {review_metrics.total_authored_mrs} authored MRs analyzed")
        click.echo(f"  → {len(review_signals)} review signals detected")
        click.echo(f"  → {len(mr_coauthor_signals)} MR co-author signals detected")

        mr_metrics = mr_scanner.scan(effective_members, week)
        mr_signals = calculate_mr_signals(
            mr_metrics, MR_SIZE_SKILL_MAPPINGS, MR_CODING_TIME_SKILL_MAPPINGS
        )
        click.echo(f"  → {len(mr_signals)} MR signals detected")

        week_member_signals = member_signals + mr_coauthor_signals

        data = build_output(
            team.code,
            week,
            artifact_signals,
            week_ci_signals,
            week_member_signals,
            review_signals,
            mr_signals,
        )
        output_path = write_output(data, team.code, week)
        output_paths.append(output_path)
        click.echo(f"  ✓ {output_path}")
        click.echo()

    # 18. Summary
    click.echo("Summary")
    click.echo(f"  Team:    {team.code}")
    click.echo(f"  Weeks:   {len(periods)}")
    click.echo(f"  Files:   {len(output_paths)}")
    click.echo(f"  Signals: {total_signals_all} shared + review signals per week")


@main.command("github-scan")
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
    "--usernames",
    default=None,
    help="Comma-separated GitHub usernames for review signals (also TEAM_USERNAMES env).",
)
@click.option(
    "--verbose",
    is_flag=True,
    default=False,
    help="Show detailed debug output during scanning.",
)
def github_scan(
    config_path: str,
    period: str | None,
    usernames: str | None,
    verbose: bool,
) -> None:
    """Scan GitHub repositories for AI adoption signals."""
    from ai_fluency_collector.github_client import (
        GitHubAuthError,
        GitHubClient,
        GitHubServerError,
    )
    from ai_fluency_collector.github_scoring import (
        GITHUB_REVIEW_SKILL_MAPPINGS,
        calculate_github_review_scores,
    )
    from ai_fluency_collector.scanners.github_artifact_scanner import GitHubArtifactScanner
    from ai_fluency_collector.scanners.github_review_scanner import GitHubReviewScanner

    # 1. Load config
    try:
        team = load_config(config_path)
    except (FileNotFoundError, ValueError) as e:
        raise click.ClickException(str(e)) from e

    if not team.github_repos:
        raise click.ClickException(
            "No GitHub repos configured. Add github_repos to your config file."
        )

    # 2. Resolve usernames (CLI → env → config members)
    if usernames:
        effective_members = [u.strip() for u in usernames.split(",") if u.strip()]
    else:
        env_usernames = os.environ.get("TEAM_USERNAMES", "")
        effective_members = (
            [u.strip() for u in env_usernames.split(",") if u.strip()]
            if env_usernames
            else team.members
        )

    # 3. Validate period
    if period is None:
        period = current_iso_week()
    else:
        validate_period(period)

    # 4. Check GITHUB_TOKEN
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise click.ClickException(
            "GITHUB_TOKEN environment variable is not set. "
            "Export a token with repo and read:user scopes."
        )

    # 5. Validate token
    client = GitHubClient(token)
    try:
        client.validate_token()
    except (GitHubAuthError, GitHubServerError) as e:
        raise click.ClickException(str(e)) from e

    # 6. Print startup banner
    output_file = f"{team.code}-{period}.json"
    click.echo(AFC_BANNER)
    click.echo("  GitHub:   api.github.com")
    click.echo(f"  Team:     {team.name}")
    click.echo(f"  Repos:    {len(team.github_repos)}")
    click.echo(f"  Members:  {len(effective_members)}")
    click.echo(f"  Period:   {period}")
    click.echo(f"  Output:   {output_file}")
    click.echo()

    # 7. Scan repo artifacts
    click.echo("Scanning GitHub repo artifacts...")
    artifact_scanner = GitHubArtifactScanner(client)
    artifact_signals = artifact_scanner.scan_repos(team.github_repos)
    for repo in team.github_repos:
        click.echo(f"  {repo}: scanned")
    click.echo(f"  → {len(artifact_signals)} artifact signals detected")
    click.echo()

    # 8. Scan PR review behavioral signals
    review_signals: list[dict] = []
    if effective_members:
        click.echo("Scanning GitHub PR review patterns...")
        review_scanner = GitHubReviewScanner(client)
        review_metrics = review_scanner.scan(effective_members, period)
        review_signals = calculate_github_review_scores(
            review_metrics, GITHUB_REVIEW_SKILL_MAPPINGS
        )
        click.echo(f"  {review_metrics.total_authored_prs} authored PRs analyzed")
        click.echo(f"  → {len(review_signals)} review signals detected")
        click.echo()
    else:
        click.echo("Skipping PR review scan (no usernames provided).")
        click.echo()

    # 9. Build and write output JSON
    sources = []
    if artifact_signals:
        sources.append({"source_id": "github-repo-artifacts", "signals": artifact_signals})
    if review_signals:
        sources.append({"source_id": "github-review-signals", "signals": review_signals})

    data = {
        "team_code": team.code,
        "survey_period": period,
        "sources": sources,
    }
    output_path = write_output(data, team.code, period)

    # 10. Summary
    total_signals = len(artifact_signals) + len(review_signals)
    click.echo("Summary")
    click.echo(f"  File:    {output_path}")
    click.echo(f"  Sources: {len(sources)}")
    click.echo(f"  Signals: {total_signals}")
    click.echo(f"  Team:    {team.code}")


@main.command()
def init() -> None:
    """Interactive setup wizard to create a team config YAML file."""
    click.echo(AFC_BANNER)
    click.echo("Team Setup Wizard")
    click.echo()

    # Step 1: Basics
    click.echo("Step 1: Basics")
    while True:
        gitlab_url = click.prompt("GitLab URL", default="https://gitlab.com")
        # Auto-add https:// if missing
        if not gitlab_url.startswith("http://") and not gitlab_url.startswith("https://"):
            gitlab_url = f"https://{gitlab_url}"
            click.echo(f"  Using: {gitlab_url}")
        # Strip trailing slashes
        gitlab_url = gitlab_url.rstrip("/")
        break
    team_name = click.prompt("Team name")
    suggested_code = _slugify(team_name)
    team_code = click.prompt("Team code", default=suggested_code)
    click.echo()

    # Step 2: Token check
    click.echo("Step 2: Token check")
    token = os.environ.get("GITLAB_TOKEN")
    if not token:
        click.echo("Error: GITLAB_TOKEN environment variable is not set.")
        click.echo("Export a token with read_api scope and re-run.")
        raise SystemExit(1)

    client = GitLabClient(token, base_url=gitlab_url)
    try:
        client.validate_token()
    except (GitLabAuthError, GitLabServerError) as e:
        click.echo(f"Error: {e}")
        raise SystemExit(1) from e

    # Fetch username for display
    try:
        resp = client.session.get(client._api_url("/user"))
        user_data = resp.json()
        username = user_data.get("username", "unknown")
        click.echo(f"Connected as: {username}")
    except Exception:
        click.echo("Token valid.")
    click.echo()

    # Step 3: Members
    click.echo("Step 3: Team members")
    click.echo("Enter GitLab usernames one at a time (empty line to finish):")
    members: list[str] = []
    while True:
        member = click.prompt("  Username", default="", show_default=False)
        if not member:
            if not members:
                click.echo("  At least one member is required.")
                continue
            break
        try:
            client.get_user(member)
            members.append(member)
            click.echo(f"    Found: {member}")
        except GitLabUserNotFoundError:
            click.echo(f"    Error: User '{member}' not found. Try again.")
    click.echo()

    # Step 4: Projects
    click.echo("Step 4: Projects")
    click.echo("Enter project paths one at a time (empty line to finish):")
    projects: list[str] = []
    project_default_branches: dict[str, str] = {}
    while True:
        project = click.prompt("  Project path", default="", show_default=False)
        if not project:
            if not projects:
                click.echo("  At least one project is required.")
                continue
            break
        try:
            branches = client.get_branches(project)
            default_branch = "main"
            for b in branches:
                if b.get("default"):
                    default_branch = b["name"]
                    break
            projects.append(project)
            project_default_branches[project] = default_branch
            click.echo(f"    Found: {len(branches)} branches, default: {default_branch}")
        except _GITLAB_ERRORS as e:
            click.echo(
                f"    Error: {e} "
                "(path should match the URL after your GitLab domain, "
                "e.g. 'group/project' not 'gitlab.com/group/project')"
            )
    click.echo()

    # Step 5: CI Pattern Discovery
    click.echo("Step 5: CI pattern discovery")
    all_ci_items: list[dict[str, str]] = []

    for project in projects:
        default_branch = project_default_branches.get(project, "HEAD")
        click.echo(f"  Scanning {project}...")

        content = client.get_file_content(project, ".gitlab-ci.yml", ref=default_branch)
        if content is None:
            click.echo("    No .gitlab-ci.yml found.")
            continue

        try:
            ci_config = yaml.safe_load(content)
        except yaml.YAMLError:
            click.echo("    Could not parse .gitlab-ci.yml.")
            continue

        if not isinstance(ci_config, dict):
            click.echo("    Invalid .gitlab-ci.yml format.")
            continue

        # Extract includes and job names from root config
        _collect_ci_items(ci_config, all_ci_items, project)

        # Follow local includes
        includes = ci_config.get("include")
        local_paths: list[str] = []
        if isinstance(includes, list):
            for item in includes:
                if isinstance(item, dict) and "local" in item:
                    local_paths.append(item["local"])
        elif isinstance(includes, dict) and "local" in includes:
            local_paths.append(includes["local"])

        for local_path in local_paths:
            clean_path = local_path.lstrip("/")
            local_content = client.get_file_content(project, clean_path, ref=default_branch)
            if local_content is None:
                continue
            try:
                local_config = yaml.safe_load(local_content)
            except yaml.YAMLError:
                continue
            if isinstance(local_config, dict):
                _collect_ci_items(local_config, all_ci_items, project)

    ci_signals_config: dict[str, list[str]] = {}

    if all_ci_items:
        click.echo()
        click.echo("  Found CI items:")
        for i, item in enumerate(all_ci_items, 1):
            click.echo(f"    {i}. [{item['type']}] {item['value']}  ({item['project']})")
        click.echo()

        # Pre-scan for suggestions
        ai_suggested = _suggest_items(all_ci_items, "ai")
        sec_suggested = _suggest_items(all_ci_items, "security")
        deploy_suggested = _suggest_items(all_ci_items, "deployment")

        # Tag AI-related items
        ai_default = ",".join(str(i) for i in ai_suggested) if ai_suggested else "skip"
        if ai_suggested:
            click.echo(f"  Suggested AI-related: {ai_default}")
        ai_input = click.prompt(
            "  Which are AI-related? (comma-separated numbers, or 'skip')",
            default=ai_default,
        )
        ai_items = _parse_selection(ai_input, all_ci_items)
        if ai_items:
            ci_signals_config["ai-code-review"] = ai_items

        # Tag security-related items
        sec_default = ",".join(str(i) for i in sec_suggested) if sec_suggested else "skip"
        if sec_suggested:
            click.echo(f"  Suggested security-related: {sec_default}")
        sec_input = click.prompt(
            "  Which are security-related? (comma-separated numbers, or 'skip')",
            default=sec_default,
        )
        sec_items = _parse_selection(sec_input, all_ci_items)
        if sec_items:
            ci_signals_config["sast-dast"] = sec_items

        # Tag deployment gates
        deploy_default = ",".join(str(i) for i in deploy_suggested) if deploy_suggested else "skip"
        if deploy_suggested:
            click.echo(f"  Suggested deployment gates: {deploy_default}")
        deploy_input = click.prompt(
            "  Which are deployment gates? (comma-separated numbers, or 'skip')",
            default=deploy_default,
        )
        deploy_items = _parse_selection(deploy_input, all_ci_items)
        if deploy_items:
            ci_signals_config["deployment-gates"] = deploy_items
    else:
        click.echo("  No CI items found across projects.")

    click.echo()

    # Step 6: Write config
    default_filename = f"{team_code}.yaml"
    click.echo("Step 6: Write config")
    output_filename = click.prompt("Output filename", default=default_filename)

    config_data: dict = {
        "team": {
            "gitlab_url": gitlab_url,
            "name": team_name,
            "code": team_code,
            "members": members,
            "projects": projects,
        }
    }

    if ci_signals_config:
        config_data["team"]["ci_signals"] = ci_signals_config

    with open(output_filename, "w") as f:
        yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

    click.echo()
    click.echo(f"Config written to: {output_filename}")
    click.echo()
    click.echo("Summary:")
    click.echo(f"  Team:     {team_name} ({team_code})")
    click.echo(f"  GitLab:   {gitlab_url}")
    click.echo(f"  Members:  {len(members)}")
    click.echo(f"  Projects: {len(projects)}")
    if ci_signals_config:
        click.echo(f"  CI signals: {len(ci_signals_config)} categories")
    click.echo()
    click.echo(f"Run: afc scan --config {output_filename}")


def _collect_ci_items(
    ci_config: dict,
    items: list[dict[str, str]],
    project: str,
) -> None:
    """Extract include paths and job names from a CI config into items list."""
    # Extract includes
    includes = ci_config.get("include")
    if includes is not None:
        if isinstance(includes, str):
            items.append({"type": "include", "value": includes, "project": project})
        elif isinstance(includes, list):
            for inc in includes:
                if isinstance(inc, str):
                    items.append({"type": "include", "value": inc, "project": project})
                elif isinstance(inc, dict):
                    if "template" in inc:
                        items.append(
                            {"type": "template", "value": inc["template"], "project": project}
                        )
                    if "local" in inc:
                        items.append({"type": "local", "value": inc["local"], "project": project})
                    if "project" in inc and "file" in inc:
                        files = inc["file"]
                        if isinstance(files, str):
                            files = [files]
                        for f in files:
                            items.append(
                                {
                                    "type": "project",
                                    "value": f"{inc['project']}:{f}",
                                    "project": project,
                                }
                            )
        elif isinstance(includes, dict):
            if "template" in includes:
                items.append(
                    {"type": "template", "value": includes["template"], "project": project}
                )
            if "local" in includes:
                items.append({"type": "local", "value": includes["local"], "project": project})

    # Extract job names
    skip_keys = {"include", "stages", "variables", "default", "workflow", "image", "services"}
    for key in ci_config:
        if key not in skip_keys:
            items.append({"type": "job", "value": key, "project": project})


def _suggest_items(items: list[dict[str, str]], category: str) -> list[int]:
    """Pre-scan CI items and suggest indices (1-based) matching a category.

    Categories: "ai", "security", "deployment"
    """
    import re as _re

    patterns: dict[str, list[_re.Pattern]] = {
        "ai": [
            _re.compile(r"duo|ai.?review|codereview|coderabbit|copilot|claude", _re.IGNORECASE),
            _re.compile(r"ai.?test|test.?gen|diffblue|codium", _re.IGNORECASE),
        ],
        "security": [
            _re.compile(r"sast|dast|security|secret.?detect|dependency.?scan", _re.IGNORECASE),
        ],
        "deployment": [
            _re.compile(r"deploy|release|rollout", _re.IGNORECASE),
        ],
    }

    category_patterns = patterns.get(category, [])
    suggested: list[int] = []
    for i, item in enumerate(items, 1):
        value = item["value"]
        for pattern in category_patterns:
            if pattern.search(value):
                suggested.append(i)
                break
    return suggested


def _parse_selection(input_str: str, items: list[dict[str, str]]) -> list[str]:
    """Parse comma-separated numbers into a list of item values."""
    if input_str.strip().lower() == "skip" or not input_str.strip():
        return []
    result: list[str] = []
    for part in input_str.split(","):
        part = part.strip()
        if part.isdigit():
            idx = int(part) - 1
            if 0 <= idx < len(items):
                result.append(items[idx]["value"])
    return result
