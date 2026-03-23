from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

import yaml

from ai_fluency_collector.gitlab_client import GitLabClient

# CI pattern definitions with IDs matching CI_SKILL_MAPPINGS in scoring.py
CI_PATTERN_IDS = [
    "sast-dast",
    "secret-detection",
    "ai-code-review",
    "ai-test-generation",
    "dependency-scanning",
    "code-coverage",
    "deployment-gates",
]

# Known GitLab CI template paths for include detection
SAST_TEMPLATES = [
    "Security/SAST.gitlab-ci.yml",
    "Security/DAST.gitlab-ci.yml",
    "Jobs/SAST.gitlab-ci.yml",
    "Jobs/DAST.gitlab-ci.yml",
]
SECRET_TEMPLATES = [
    "Security/Secret-Detection.gitlab-ci.yml",
    "Jobs/Secret-Detection.gitlab-ci.yml",
]
DEPENDENCY_TEMPLATES = [
    "Security/Dependency-Scanning.gitlab-ci.yml",
    "Jobs/Dependency-Scanning.gitlab-ci.yml",
]

# Patterns for job/stage name matching
SAST_DAST_PATTERNS = re.compile(r"sast|dast", re.IGNORECASE)
SECRET_PATTERNS = re.compile(r"secret.?detect", re.IGNORECASE)
AI_REVIEW_PATTERNS = re.compile(r"duo|ai.?review|codereview.?ai|coderabbit", re.IGNORECASE)
AI_TEST_PATTERNS = re.compile(r"ai.?test|test.?gen|diffblue|codium", re.IGNORECASE)
DEPENDENCY_PATTERNS = re.compile(r"dependency.?scan", re.IGNORECASE)
DEPLOY_STAGE_PATTERNS = re.compile(r"deploy", re.IGNORECASE)


def _extract_includes(ci_config: dict) -> tuple[list[str], list[str]]:
    """Extract template, local, and project file paths from GitLab CI include directives.

    Returns (templates, local_paths). Templates includes both GitLab CI
    templates and file paths from project: includes (cross-project references).

    Handles all include formats:
    - String shorthand: include: 'template.yml'
    - Single dict: include: {template: 'path', local: 'path', project: ..., file: ...}
    - List of strings or dicts
    """
    includes = ci_config.get("include")
    if includes is None:
        return [], []

    templates: list[str] = []
    local_paths: list[str] = []

    def _process_include_dict(item: dict) -> None:
        if "template" in item:
            templates.append(item["template"])
        if "local" in item:
            local_paths.append(item["local"])
        # Cross-project includes: project: + file:
        # The file paths are useful for pattern matching (e.g., ai-review/*.yml)
        if "project" in item and "file" in item:
            files = item["file"]
            if isinstance(files, str):
                templates.append(files)
            elif isinstance(files, list):
                for f in files:
                    if isinstance(f, str):
                        templates.append(f)

    if isinstance(includes, str):
        templates.append(includes)
    elif isinstance(includes, dict):
        _process_include_dict(includes)
    elif isinstance(includes, list):
        for item in includes:
            if isinstance(item, str):
                templates.append(item)
            elif isinstance(item, dict):
                _process_include_dict(item)

    return templates, local_paths


def _has_template_match(templates: list[str], known_templates: list[str]) -> bool:
    """Check if any extracted template matches known template paths."""
    for tmpl in templates:
        for known in known_templates:
            if known in tmpl:
                return True
    return False


def _has_template_pattern(templates: list[str], pattern: re.Pattern) -> bool:
    """Check if any template path matches a regex pattern."""
    for tmpl in templates:
        if pattern.search(tmpl):
            return True
    return False


def _search_jobs(ci_config: dict, pattern: re.Pattern) -> bool:
    """Search job names and script contents for a regex pattern."""
    for key, value in ci_config.items():
        # Skip non-job keys
        if key in ("include", "stages", "variables", "default", "workflow", "image", "services"):
            continue
        # Check job name
        if pattern.search(key):
            return True
        # Check script contents
        if isinstance(value, dict):
            for script_key in ("script", "before_script", "after_script"):
                scripts = value.get(script_key, [])
                if isinstance(scripts, str):
                    scripts = [scripts]
                if isinstance(scripts, list):
                    for line in scripts:
                        if isinstance(line, str) and pattern.search(line):
                            return True
    return False


def _check_coverage(ci_config: dict) -> bool:
    """Check if any job defines coverage reporting."""
    for key, value in ci_config.items():
        if key in ("include", "stages", "variables", "default", "workflow", "image", "services"):
            continue
        if isinstance(value, dict):
            if "coverage" in value:
                return True
            artifacts = value.get("artifacts", {})
            if isinstance(artifacts, dict):
                reports = artifacts.get("reports", {})
                if isinstance(reports, dict) and "coverage_report" in reports:
                    return True
    return False


def _check_deployment_gates(ci_config: dict) -> bool:
    """Check for deployment stages with environment and gating rules."""
    # Check stages list for deploy
    stages = ci_config.get("stages", [])
    if isinstance(stages, list):
        for stage in stages:
            if isinstance(stage, str) and DEPLOY_STAGE_PATTERNS.search(stage):
                # Found a deploy stage, now check if any job uses environment + rules
                for key, value in ci_config.items():
                    if isinstance(value, dict) and "environment" in value:
                        if "rules" in value or "when" in value:
                            return True
                        return True  # environment alone counts

    # Also check job names for deploy pattern with environment
    for key, value in ci_config.items():
        if key in ("include", "stages", "variables", "default", "workflow", "image", "services"):
            continue
        if isinstance(value, dict):
            if DEPLOY_STAGE_PATTERNS.search(key) and "environment" in value:
                return True
            stage = value.get("stage", "")
            if isinstance(stage, str) and DEPLOY_STAGE_PATTERNS.search(stage):
                if "environment" in value:
                    return True

    return False


def _analyze_ci_config(ci_config: dict, templates: list[str]) -> dict[str, bool]:
    """Analyze a parsed CI config dict for known patterns."""
    return {
        "sast-dast": (
            _has_template_match(templates, SAST_TEMPLATES)
            or _search_jobs(ci_config, SAST_DAST_PATTERNS)
        ),
        "secret-detection": (
            _has_template_match(templates, SECRET_TEMPLATES)
            or _search_jobs(ci_config, SECRET_PATTERNS)
        ),
        "ai-code-review": (
            _search_jobs(ci_config, AI_REVIEW_PATTERNS)
            or _has_template_pattern(templates, AI_REVIEW_PATTERNS)
        ),
        "ai-test-generation": (
            _search_jobs(ci_config, AI_TEST_PATTERNS)
            or _has_template_pattern(templates, AI_TEST_PATTERNS)
        ),
        "dependency-scanning": (
            _has_template_match(templates, DEPENDENCY_TEMPLATES)
            or _search_jobs(ci_config, DEPENDENCY_PATTERNS)
        ),
        "code-coverage": _check_coverage(ci_config),
        "deployment-gates": _check_deployment_gates(ci_config),
    }


def _check_ci_signals(
    ci_config: dict,
    templates: list[str],
    ci_signals: dict[str, list[str]],
) -> dict[str, bool]:
    """Check user-declared ci_signals against job names and include paths.

    For each pattern type in ci_signals, check if ANY of the declared strings
    appear as a substring in any job name or any include/template path.
    Returns {pattern_id: True/False} only for pattern IDs present in ci_signals.
    """
    results: dict[str, bool] = {}

    # Collect all job names from the config
    skip_keys = (
        "include",
        "stages",
        "variables",
        "default",
        "workflow",
        "image",
        "services",
    )
    job_names: list[str] = []
    for key in ci_config:
        if key not in skip_keys:
            job_names.append(key)

    for pattern_id, signal_strings in ci_signals.items():
        found = False
        for signal in signal_strings:
            # Check against job names
            for job_name in job_names:
                if signal in job_name:
                    found = True
                    break
            if found:
                break
            # Check against template/include paths
            for tmpl in templates:
                if signal in tmpl:
                    found = True
                    break
            if found:
                break
        results[pattern_id] = found

    return results


@dataclass
class CoverageResult:
    """Mean coverage percentage for a single project over a period."""

    coverage: float | None  # None when no coverage jobs found
    project_count: int = 1  # always 1; aggregated by calculate_coverage_scores


@dataclass
class PipelinePassResult:
    """First-attempt pipeline pass counts for a single project."""

    pass_count: int
    total_count: int


def _period_to_date_range(period: str) -> tuple[str, str]:
    """Convert YYYY-WNN to (start_date, end_date) as ISO 8601 date strings."""
    year = int(period[:4])
    week = int(period[6:])
    start = date.fromisocalendar(year, week, 1)
    end = date.fromisocalendar(year, week, 7)
    return start.isoformat(), end.isoformat()


class CIScanner:
    """Scans GitLab projects for CI pipeline patterns in .gitlab-ci.yml."""

    def __init__(
        self,
        client: GitLabClient,
        active_days: int = 90,
        ci_signals: dict[str, list[str]] | None = None,
    ) -> None:
        self.client = client
        self.active_days = active_days
        self.ci_signals = ci_signals or {}

    def _parse_yaml(self, content: str) -> dict | None:
        """Parse YAML content, returning None on failure."""
        try:
            config = yaml.safe_load(content)
        except yaml.YAMLError:
            return None
        if not isinstance(config, dict):
            return None
        return config

    def _scan_branch(self, project_path: str, ref: str) -> dict[str, bool]:
        """Scan a single branch's .gitlab-ci.yml and local includes for CI patterns."""
        content = self.client.get_file_content(project_path, ".gitlab-ci.yml", ref=ref)
        if content is None:
            return {pid: False for pid in CI_PATTERN_IDS}

        ci_config = self._parse_yaml(content)
        if ci_config is None:
            return {pid: False for pid in CI_PATTERN_IDS}

        templates, local_paths = _extract_includes(ci_config)

        # Collect all templates across root and local includes for signal checking
        all_templates = list(templates)

        # Start with analysis of the root CI file
        results = _analyze_ci_config(ci_config, templates)

        # Fetch and scan local includes
        all_configs = [ci_config]
        for local_path in local_paths:
            # Strip leading slash if present
            clean_path = local_path.lstrip("/")
            local_content = self.client.get_file_content(project_path, clean_path, ref=ref)
            if local_content is None:
                continue
            local_config = self._parse_yaml(local_content)
            if local_config is None:
                continue

            all_configs.append(local_config)
            local_templates, _ = _extract_includes(local_config)
            all_templates.extend(local_templates)
            local_results = _analyze_ci_config(local_config, local_templates)

            # Merge: if any included file has a pattern, mark it as found
            for pid, found in local_results.items():
                if found:
                    results[pid] = True

        # Check user-declared ci_signals across all configs
        if self.ci_signals:
            for config in all_configs:
                signal_results = _check_ci_signals(config, all_templates, self.ci_signals)
                for pid, found in signal_results.items():
                    if found and pid in results:
                        results[pid] = True

        return results

    def scan_project(self, project_path: str) -> dict[str, float]:
        """Scan a project's .gitlab-ci.yml across all active branches.

        Returns dict of {pattern_id: weight} where weight is the highest
        branch weight where the pattern was found (0.0 if not found).
        Default branch = 0.5, active feature branch = 0.8.
        """
        from ai_fluency_collector.scanners.gitlab_artifact_scanner import (
            DEFAULT_BRANCH_WEIGHT,
            FEATURE_BRANCH_WEIGHT,
            _get_active_branches,
        )

        active_branches = _get_active_branches(self.client, project_path, self.active_days)

        if not active_branches:
            active_branches = [{"name": "HEAD", "weight": DEFAULT_BRANCH_WEIGHT}]

        results: dict[str, float] = {pid: 0.0 for pid in CI_PATTERN_IDS}

        for branch in active_branches:
            branch_results = self._scan_branch(project_path, branch["name"])
            for pid, found in branch_results.items():
                if found:
                    results[pid] = max(results[pid], branch["weight"])

            # If all patterns already at max weight, stop early
            if all(v >= FEATURE_BRANCH_WEIGHT for v in results.values()):
                break

        return results

    def scan_pipeline_pass_rate(self, project_path: str, period: str) -> PipelinePassResult:
        """Compute first-attempt pipeline pass rate for a project over a survey period.

        Groups pipelines by commit SHA and takes the first (lowest id) pipeline
        per SHA to determine whether that commit passed CI on first attempt.

        Args:
            project_path: GitLab project path (e.g. 'group/project').
            period: Survey period in YYYY-WNN format.

        Returns:
            PipelinePassResult with pass_count and total_count.
            total_count is 0 when no pipelines exist for the period.
        """
        start_date, end_date = _period_to_date_range(period)
        pipelines = self.client.get_pipelines(
            project_path, updated_after=start_date, updated_before=end_date
        )

        if not pipelines:
            return PipelinePassResult(pass_count=0, total_count=0)

        # Group by commit SHA, keep all pipelines per SHA
        sha_pipelines: dict[str, list[dict]] = {}
        for p in pipelines:
            sha = p.get("sha", "")
            if sha not in sha_pipelines:
                sha_pipelines[sha] = []
            sha_pipelines[sha].append(p)

        pass_count = 0
        total_count = 0
        for pipes in sha_pipelines.values():
            # Lowest id = earliest pipeline run for this commit
            first = min(pipes, key=lambda p: p.get("id", 0))
            total_count += 1
            if first.get("status") == "success":
                pass_count += 1

        return PipelinePassResult(pass_count=pass_count, total_count=total_count)

    def scan_coverage(self, project_path: str, period: str) -> CoverageResult:
        """Fetch mean test coverage for a project over a survey period.

        Queries successful CI jobs updated within the period and averages
        non-null coverage values reported by GitLab.

        Args:
            project_path: GitLab project path (e.g. 'group/project').
            period: Survey period in YYYY-WNN format.

        Returns:
            CoverageResult with mean coverage float, or None if no coverage jobs found.
        """
        start_date, _ = _period_to_date_range(period)
        jobs = self.client.get_jobs(project_path, scope="success", updated_after=start_date)

        coverage_values = [
            j["coverage"]
            for j in jobs
            if j.get("coverage") is not None
        ]

        if not coverage_values:
            return CoverageResult(coverage=None)

        mean_coverage = sum(coverage_values) / len(coverage_values)
        return CoverageResult(coverage=mean_coverage)
