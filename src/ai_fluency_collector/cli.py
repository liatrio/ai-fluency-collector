from __future__ import annotations

import os
import re
from datetime import date

import click
import yaml

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
    # Auto-add https:// if missing
    if not effective_gitlab_url.startswith(("http://", "https://")):
        effective_gitlab_url = f"https://{effective_gitlab_url}"
    effective_gitlab_url = effective_gitlab_url.rstrip("/")

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
            except (GitLabAccessError, GitLabAuthError, GitLabServerError) as e:
                click.echo(f"  {project}: ERROR - {e}")
        click.echo()
        click.echo("Validation complete.")
        return

    # 7. Print startup banner
    output_file = f"{team.code}-{period}.json"
    click.echo(AFC_BANNER)
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
    ci_scanner = CIScanner(client, ci_signals=team.ci_signals)
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
        except (GitLabAccessError, GitLabAuthError, GitLabServerError) as e:
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
