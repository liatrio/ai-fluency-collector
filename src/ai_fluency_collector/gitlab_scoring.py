from __future__ import annotations

from collections import defaultdict

# Declarative mapping: artifact_id → skill_id with weight.
# To adjust scoring, edit this data structure only — no scanner or output code changes needed.
ARTIFACT_SKILL_MAPPINGS: list[dict] = [
    {"artifact_id": "claude-md", "skill_id": "cq-context", "weight": 0.5},
    {"artifact_id": "claude-md", "skill_id": "im-autocomplete", "weight": 0.3},
    {"artifact_id": "claude-settings", "skill_id": "tg-permission-gated", "weight": 1.0},
    {"artifact_id": "mcp-json", "skill_id": "im-chat", "weight": 0.5},
    {"artifact_id": "mcp-json", "skill_id": "pm-core", "weight": 0.5},
    {"artifact_id": "prompts-dir", "skill_id": "ks-patterns", "weight": 0.7},
    {"artifact_id": "prompts-dir", "skill_id": "cq-delegation", "weight": 0.5},
    {"artifact_id": "cursor", "skill_id": "im-autocomplete", "weight": 0.3},
    {"artifact_id": "cursor", "skill_id": "im-inline-edit", "weight": 0.5},
    {"artifact_id": "copilot-instructions", "skill_id": "im-autocomplete", "weight": 0.3},
    {"artifact_id": "agents", "skill_id": "im-supervised-agent", "weight": 0.5},
    {"artifact_id": "agents", "skill_id": "im-cli-agent", "weight": 0.5},
    {"artifact_id": "aider", "skill_id": "im-chat", "weight": 0.5},
]

# CI pattern → skill mappings
CI_SKILL_MAPPINGS: list[dict] = [
    {"artifact_id": "sast-dast", "skill_id": "sdlc-security", "weight": 0.4},
    {"artifact_id": "sast-dast", "skill_id": "tg-security-gates", "weight": 0.5},
    {"artifact_id": "secret-detection", "skill_id": "sdlc-security", "weight": 0.3},
    {"artifact_id": "ai-code-review", "skill_id": "tg-code-review", "weight": 1.0},
    {"artifact_id": "ai-test-generation", "skill_id": "sdlc-testing", "weight": 1.0},
    {"artifact_id": "dependency-scanning", "skill_id": "sdlc-security", "weight": 0.3},
    {"artifact_id": "code-coverage", "skill_id": "pm-measurement", "weight": 1.0},
    {"artifact_id": "deployment-gates", "skill_id": "sdlc-deployment", "weight": 0.5},
    {"artifact_id": "deployment-gates", "skill_id": "tg-supervised-auto", "weight": 0.5},
]


# CI execution verification → skill mappings.
# Maps the same pattern IDs as CI_SKILL_MAPPINGS, but scores based on whether
# configured jobs actually ran and passed (not just present in YAML).
# score_fn takes execution_rate (float 0.0–1.0) and returns an int score 0–100.
CI_EXECUTION_SKILL_MAPPINGS: dict[str, list[dict]] = {
    "sast-dast": [
        {"skill_id": "sdlc-security", "score_fn": lambda rate: round(rate * 100)},
        {"skill_id": "tg-security-gates", "score_fn": lambda rate: round(rate * 100)},
    ],
    "secret-detection": [
        {"skill_id": "sdlc-security", "score_fn": lambda rate: round(rate * 100)},
    ],
    "ai-code-review": [
        {"skill_id": "tg-code-review", "score_fn": lambda rate: round(rate * 100)},
    ],
    "ai-test-generation": [
        {"skill_id": "sdlc-testing", "score_fn": lambda rate: round(rate * 100)},
    ],
    "dependency-scanning": [
        {"skill_id": "sdlc-security", "score_fn": lambda rate: round(rate * 100)},
    ],
}


# CI pipeline pass rate → skill mappings.
# score_fn takes the mean first-attempt pass rate (float 0.0–1.0) and returns an int score 0–100.
CI_PIPELINE_SKILL_MAPPINGS: dict[str, list[dict]] = {
    "pipeline_pass_rate": [
        {"skill_id": "pm-core", "score_fn": lambda rate: round(rate * 100)},
        {"skill_id": "tg-code-review", "score_fn": lambda rate: round(rate * 100)},
    ],
}

# Review behavioral metrics → skill mappings.
# score_fn takes the computed metric rate (float 0.0–1.0) and returns an int score 0–100.
REVIEW_SKILL_MAPPINGS: dict[str, list[dict]] = {
    "lgtm_without_comment": [
        {"skill_id": "tg-code-review", "score_fn": lambda rate: round(100 - (rate * 100))},
    ],
    "review_comment_depth": [
        {"skill_id": "cq-evaluation", "score_fn": lambda ratio: round(ratio * 100)},
    ],
    "self_review_rate": [
        {"skill_id": "cq-refinement", "score_fn": lambda rate: round(rate * 100)},
    ],
}

# Coverage delta → skill mappings.
# score_fn takes coverage delta (float, can be None) and returns an int score 0–100.
# Formula: clamp(round(50 + delta * 10), 0, 100). No delta → score based on absolute coverage.
COVERAGE_SKILL_MAPPINGS: list[dict] = [
    {"skill_id": "pm-core"},
    {"skill_id": "cq-evaluation"},
]

# MR co-author tag → skill mappings (period-specific, source: gitlab-member-activity).
# score_fn takes the team-level MR rate (float 0.0–1.0) and returns an int score 0–100.
MR_COAUTHOR_SKILL_MAPPINGS: dict[str, list[dict]] = {
    "mr_ai_coauthor_rate": [
        {"skill_id": "im-chat", "score_fn": lambda rate: round(rate * 100)},
    ],
    "mr_agentic_coauthor_rate": [
        {"skill_id": "im-supervised-agent", "score_fn": lambda rate: round(rate * 100)},
    ],
}


# MR size → skill mappings (source: gitlab-mr).
# score_fn takes the median lines changed (int) and returns an int score 0–100.
def _pr_size_score(median_lines: float) -> int:
    if median_lines < 200:
        return 100
    if median_lines < 400:
        return 80
    if median_lines < 800:
        return 60
    if median_lines < 1500:
        return 35
    return 10


MR_SIZE_SKILL_MAPPINGS: dict[str, list[dict]] = {
    "pr_size_median": [
        {"skill_id": "im-supervised-agent", "score_fn": _pr_size_score},
    ],
}


# MR coding time → skill mappings (source: gitlab-mr).
# score_fn takes the median hours (float) and returns an int score 0–100.
def _coding_time_score(median_hours: float) -> int:
    if median_hours < 2:
        return 100
    if median_hours < 8:
        return 85
    if median_hours < 24:
        return 65
    if median_hours < 72:
        return 40
    return 15


MR_CODING_TIME_SKILL_MAPPINGS: dict[str, list[dict]] = {
    "coding_time_median": [
        {"skill_id": "im-inline-edit", "score_fn": _coding_time_score},
        {"skill_id": "im-supervised-agent", "score_fn": _coding_time_score},
    ],
}


def calculate_mr_signals(metrics, size_mappings: dict, coding_time_mappings: dict) -> list[dict]:
    """Calculate all gitlab-mr skill scores from MRMetrics.

    Args:
        metrics: MRMetrics object from MRScanner.scan().
        size_mappings: MR_SIZE_SKILL_MAPPINGS dict.
        coding_time_mappings: MR_CODING_TIME_SKILL_MAPPINGS dict.

    Returns:
        Combined list of {skill_id, score, evidence} dicts for all MR signals.
    """
    if metrics is None:
        return []

    all_mappings = {**size_mappings, **coding_time_mappings}
    metric_values = {
        "pr_size_median": metrics.pr_size_median,
        "coding_time_median": metrics.coding_time_median,
    }

    per_repo = getattr(metrics, "per_repo", None)

    signals: list[dict] = []
    for metric_key, skill_maps in all_mappings.items():
        value = metric_values.get(metric_key)
        if value is None:
            continue
        for m in skill_maps:
            score = m["score_fn"](value)
            if score <= 0:
                continue
            evidence = metrics.evidence.get(metric_key, "detected")
            ctx = _rate_context(evidence)
            if per_repo:
                ctx["per_repo"] = per_repo
            signals.append(
                {
                    "skill_id": m["skill_id"],
                    "score": score,
                    "evidence": evidence,
                    "scoring_context": ctx,
                }
            )

    return signals


# Keep backward-compatible alias used by CLI (T01 wired this name)
def calculate_mr_size_scores(metrics, mappings: dict) -> list[dict]:
    """Calculate skill scores from MR size metrics only.

    Args:
        metrics: MRMetrics object from MRScanner.scan().
        mappings: MR_SIZE_SKILL_MAPPINGS dict.

    Returns:
        List of {skill_id, score, evidence} dicts. Empty if no AI-attributed MRs found.
    """
    if metrics is None or metrics.pr_size_median is None:
        return []

    per_repo = getattr(metrics, "per_repo", None)

    signals: list[dict] = []
    for metric_key, skill_maps in mappings.items():
        value = getattr(metrics, metric_key, None)
        if value is None:
            continue
        for m in skill_maps:
            score = m["score_fn"](value)
            if score <= 0:
                continue
            evidence = metrics.evidence.get(metric_key, "detected")
            ctx = _rate_context(evidence)
            if per_repo:
                ctx["per_repo"] = per_repo
            signals.append(
                {
                    "skill_id": m["skill_id"],
                    "score": score,
                    "evidence": evidence,
                    "scoring_context": ctx,
                }
            )

    return signals


# Member activity → skill mappings
# Score based on percentage of members showing AI co-author activity
MEMBER_SKILL_MAPPINGS: list[dict] = [
    {"artifact_id": "coauthor-claude", "skill_id": "im-cli-agent", "weight": 0.5},
    {"artifact_id": "coauthor-claude", "skill_id": "im-chat", "weight": 0.5},
    {"artifact_id": "coauthor-copilot", "skill_id": "im-autocomplete", "weight": 0.5},
    {"artifact_id": "coauthor-cursor", "skill_id": "im-autocomplete", "weight": 0.3},
    {"artifact_id": "coauthor-cursor", "skill_id": "im-inline-edit", "weight": 0.3},
]


def _artifact_breakdown(
    name: str,
    feat: int,
    dflt: int,
    missing: int,
    num_projects: int,
    default_projects: list[str] | None = None,
    feature_projects: list[str] | None = None,
    missing_projects: list[str] | None = None,
    branch_names: dict[str, str] | None = None,
    branch_counts: dict[str, int] | None = None,
) -> str:
    """Build a human-readable breakdown sentence for an artifact signal.

    Args:
        name: Display name of the artifact (e.g. "CLAUDE.md").
        feat: Number of projects where it was found on a feature branch only.
        dflt: Number of projects where it was found on the default branch.
        missing: Number of projects where it was not found at all.
        num_projects: Total number of team projects.
        default_projects: Project names where artifact was found on default branch.
        feature_projects: Project names where artifact was found on feature branch only.
        missing_projects: Project names where artifact was not found.
        branch_names: Optional {project_path: branch_name} for actual branch names.
    """
    total_found = feat + dflt

    # Build project name lists for evidence
    def _proj_list(projects: list[str] | None) -> str:
        if not projects:
            return ""
        return ", ".join(_short_name(p) for p in projects)

    def _proj_with_branch(p: str, branch_type: str) -> str:
        """Format project name with branch info, using actual name if available."""
        short = _short_name(p)
        count = branch_counts.get(p, 0) if branch_counts else 0
        if branch_names and p in branch_names:
            bname = branch_names[p]
            if count > 1:
                return f"{short} ({count} branches, e.g. {bname})"
            return f"{short} ({bname})"
        return f"{short} ({branch_type})"

    if total_found == num_projects:
        # Found everywhere
        if dflt == num_projects:
            proj_detail = ""
            if default_projects:
                proj_detail = f": {_proj_list(default_projects)}"
            return (
                f"{name} found in all {num_projects} projects on the default branch{proj_detail}."
            )
        if feat == num_projects:
            proj_detail = ""
            if feature_projects:
                parts = [_proj_with_branch(p, "feature") for p in feature_projects]
                proj_detail = f": {', '.join(parts)}"
            return (
                f"{name} found in all {num_projects} projects{proj_detail}, "
                f"but only on feature branches. "
                f"Move to the default branch for a higher score."
            )
        # Mixed: some default, some feature-only
        dflt_detail = ""
        feat_detail = ""
        if default_projects:
            parts = [_proj_with_branch(p, "default") for p in default_projects]
            dflt_detail = f" ({', '.join(parts)})"
        if feature_projects:
            parts = [_proj_with_branch(p, "feature") for p in feature_projects]
            feat_detail = f" ({', '.join(parts)})"
        return (
            f"{name} found in all {num_projects} projects — "
            f"{dflt} on the default branch{dflt_detail}, "
            f"{feat} on feature branches only{feat_detail}. "
            f"Move the remaining {feat} to the default branch for a higher score."
        )
    else:
        # Not found in all projects
        hint_parts = []
        if missing > 0:
            hint_parts.append(f"add to the remaining {missing} project{'s' if missing > 1 else ''}")
        if feat > 0:
            hint_parts.append("move to the default branch")
        hint = " and ".join(hint_parts)

        location = ""
        if feat > 0 and dflt > 0:
            location = f" ({dflt} on default branch, {feat} on feature branches only)"
        elif feat > 0:
            location = " (feature branch only)"

        # Add project names to found/missing detail
        found_detail = ""
        missing_detail = ""
        if default_projects or feature_projects:
            found_names = []
            if default_projects:
                found_names.extend(_proj_with_branch(p, "default branch") for p in default_projects)
            if feature_projects:
                found_names.extend(
                    _proj_with_branch(p, "feature branch only") for p in feature_projects
                )
            found_detail = f": {', '.join(found_names)}"
        if missing_projects:
            missing_detail = f" Missing from: {_proj_list(missing_projects)}."

        # Skip aggregate location when found_detail already has per-project branch info
        effective_location = "" if found_detail else location

        return (
            f"{name} found in {total_found} of {num_projects} projects"
            f"{found_detail}{effective_location}."
            f"{missing_detail}"
            f"{' To improve: ' + hint + '.' if hint else ''}"
        ).strip()


def _short_name(project_path: str) -> str:
    """Extract the short project name from a full path (e.g. 'group/subgroup/repo' → 'repo')."""
    return project_path.rsplit("/", 1)[-1] if "/" in project_path else project_path


def _rate_context(breakdown: str) -> dict:
    """Build a scoring_context for rate-based signals (no weight cap, max=100)."""
    return {"breakdown": breakdown, "max_from_this_signal": 100}


def calculate_coverage_scores(
    current_results: list,
    prior_results: list | None,
    mappings: list[dict],
    project_names: list[str] | None = None,
) -> list[dict]:
    """Calculate skill scores from per-project coverage data across two periods.

    Computes mean coverage for each period across projects that have data,
    derives a delta, and applies the delta formula:
        score = clamp(round(50 + delta * 10), 0, 100)

    When no prior period data is available, falls back to absolute coverage:
        score = clamp(round(coverage), 0, 100)

    Projects with no coverage jobs are excluded from both means.

    Args:
        current_results: List of CoverageResult for the current period.
        prior_results: List of CoverageResult for the prior period, or None.
        mappings: COVERAGE_SKILL_MAPPINGS list.
        project_names: Optional list of project paths, aligned with current_results.

    Returns:
        List of {skill_id, score, evidence} dicts. Empty if no coverage data.
    """
    current_with_data = [(i, r) for i, r in enumerate(current_results) if r.coverage is not None]
    if not current_with_data:
        return []

    mean_current = sum(r.coverage for _, r in current_with_data) / len(current_with_data)
    num_projects = len(current_with_data)

    # Compute delta if prior data available
    delta: float | None = None
    if prior_results:
        prior_with_data = [r for r in prior_results if r.coverage is not None]
        if prior_with_data:
            mean_prior = sum(r.coverage for r in prior_with_data) / len(prior_with_data)
            delta = mean_current - mean_prior

    # Include project names in evidence
    proj_detail = ""
    if project_names:
        active_names = [
            _short_name(project_names[i]) for i, _ in current_with_data if i < len(project_names)
        ]
        if active_names:
            proj_detail = f": {', '.join(active_names)}"

    # Score formula
    if delta is not None:
        score = max(0, min(100, round(50 + delta * 10)))
        delta_str = f"{'+' if delta >= 0 else ''}{delta:.1f}%"
        evidence = (
            f"Test coverage: {mean_current:.0f}% "
            f"({delta_str} from prior period, N={num_projects} projects{proj_detail})"
        )
    else:
        score = max(0, min(100, round(mean_current)))
        evidence = f"Test coverage: {mean_current:.0f}% (N={num_projects} projects{proj_detail})"

    if score <= 0:
        return []

    # Build per_project scoring_context
    per_project: dict[str, dict] = {}
    if project_names:
        for i, r in current_with_data:
            if i < len(project_names):
                entry: dict = {"coverage_pct": round(r.coverage, 1)}
                job_names = getattr(r, "job_names", [])
                if job_names:
                    entry["jobs"] = job_names
                per_project[project_names[i]] = entry

    signals = []
    for m in mappings:
        ctx = _rate_context(evidence)
        if per_project:
            ctx["per_project"] = per_project
        signals.append(
            {
                "skill_id": m["skill_id"],
                "score": score,
                "evidence": evidence,
                "scoring_context": ctx,
            }
        )
    return signals


def calculate_pipeline_scores(
    project_results: list,
    mappings: dict[str, list[dict]],
    project_names: list[str] | None = None,
) -> list[dict]:
    """Calculate skill scores from per-project pipeline pass rate data.

    Aggregates across projects using mean first-attempt pass rate.
    Projects with no pipelines in the period are excluded from the mean.

    Args:
        project_results: List of PipelinePassResult objects (from CIScanner).
        mappings: CI_PIPELINE_SKILL_MAPPINGS dict.
        project_names: Optional list of project paths, aligned with project_results.

    Returns:
        List of {skill_id, score, evidence} dicts. Empty if no pipelines found.
    """
    projects_with_data = [(i, r) for i, r in enumerate(project_results) if r.total_count > 0]
    if not projects_with_data:
        return []

    mean_rate = sum(r.pass_count / r.total_count for _, r in projects_with_data) / len(
        projects_with_data
    )
    total_pipelines = sum(r.total_count for _, r in projects_with_data)
    pct = round(mean_rate * 100)

    proj_detail = ""
    if project_names:
        active_names = [
            _short_name(project_names[i]) for i, _ in projects_with_data if i < len(project_names)
        ]
        if active_names:
            proj_detail = f" across {', '.join(active_names)}"

    evidence = (
        f"{pct}% of pipelines passed on first attempt (N={total_pipelines} pipelines{proj_detail})"
    )

    per_project: dict[str, dict] = {}
    if project_names:
        for i, r in enumerate(project_results):
            if i < len(project_names) and r.total_count > 0:
                rate = round(r.pass_count / r.total_count * 100)
                per_project[project_names[i]] = {
                    "total": r.total_count,
                    "passed": r.pass_count,
                    "pass_rate_pct": rate,
                }

    signals: list[dict] = []
    for skill_maps in mappings.values():
        for m in skill_maps:
            score = m["score_fn"](mean_rate)
            if score <= 0:
                continue
            ctx = _rate_context(evidence)
            if per_project:
                ctx["per_project"] = per_project
            signals.append(
                {
                    "skill_id": m["skill_id"],
                    "score": score,
                    "evidence": evidence,
                    "scoring_context": ctx,
                }
            )

    return signals


def calculate_ci_execution_scores(
    execution_results: list,
    mappings: dict[str, list[dict]],
    project_names: list[str] | None = None,
) -> list[dict]:
    """Calculate skill scores from CI execution verification data.

    For each configured CI pattern, computes the execution pass rate across
    projects and maps it to skill scores. Only patterns that were configured
    (detected in YAML) and have execution data are scored.

    Args:
        execution_results: List of CIExecutionResult objects (from CIScanner).
        mappings: CI_EXECUTION_SKILL_MAPPINGS dict.
        project_names: Optional list of project paths, aligned with execution_results.

    Returns:
        List of {skill_id, score, evidence} dicts. Empty if no execution data.
    """
    if not execution_results:
        return []

    # Aggregate per-pattern stats across projects and track which projects ran each pattern
    aggregated: dict[str, list[int]] = {}  # pid -> [passed, ran, checked]
    pattern_projects: dict[str, list[str]] = {}  # pid -> project names with executions
    pattern_failed_jobs: dict[str, list[str]] = {}  # pid -> failed job names
    for idx, result in enumerate(execution_results):
        proj_name = project_names[idx] if project_names and idx < len(project_names) else None
        for pid, (passed, ran, checked) in result.pattern_stats.items():
            if pid not in aggregated:
                aggregated[pid] = [0, 0, 0]
            aggregated[pid][0] += passed
            aggregated[pid][1] += ran
            aggregated[pid][2] += checked
            if proj_name and ran > 0:
                pattern_projects.setdefault(pid, []).append(proj_name)
        # Collect failed job names
        for pid, jobs in getattr(result, "failed_jobs", {}).items():
            pattern_failed_jobs.setdefault(pid, []).extend(jobs)

    if not aggregated:
        return []

    # Track best score per skill_id to avoid duplicates
    best_per_skill: dict[str, dict] = {}

    for pid, counts in aggregated.items():
        passed, ran, checked = counts
        if checked == 0:
            continue

        skill_maps = mappings.get(pid, [])
        if not skill_maps:
            continue

        execution_rate = ran / checked
        pass_rate = passed / ran if ran > 0 else 0.0

        proj_detail = ""
        if pattern_projects.get(pid):
            proj_detail = f" in {', '.join(_short_name(p) for p in pattern_projects[pid])}"

        if ran == 0:
            evidence = f"{pid}: configured but not executed in {checked} pipelines checked"
        else:
            evidence = (
                f"{pid}: ran in {ran}/{checked} pipelines, "
                f"{passed}/{ran} passed ({round(pass_rate * 100)}% pass rate)"
                f"{proj_detail}"
            )

        # Deduplicate failed job names for this pattern
        failed = sorted(set(pattern_failed_jobs.get(pid, [])))

        for m in skill_maps:
            score = m["score_fn"](execution_rate * pass_rate)
            if score <= 0:
                continue
            skill_id = m["skill_id"]
            ctx = _rate_context(evidence)
            if failed:
                ctx["failed_jobs"] = failed
            entry = {
                "skill_id": skill_id,
                "score": score,
                "evidence": evidence,
                "scoring_context": ctx,
            }
            if skill_id not in best_per_skill or score > best_per_skill[skill_id]["score"]:
                best_per_skill[skill_id] = entry

    return list(best_per_skill.values())


def calculate_mr_coauthor_scores(metrics, mappings: dict) -> list[dict]:
    """Calculate skill scores from MR co-author tag metrics.

    Args:
        metrics: ReviewMetrics object from ReviewScanner.scan().
        mappings: MR_COAUTHOR_SKILL_MAPPINGS dict.

    Returns:
        List of {skill_id, score, evidence} dicts. Only scores > 0 are included.
    """
    if metrics is None:
        return []

    metric_values = {
        "mr_ai_coauthor_rate": metrics.mr_ai_coauthor_rate,
        "mr_agentic_coauthor_rate": metrics.mr_agentic_coauthor_rate,
    }

    per_project = getattr(metrics, "per_project", None)
    tool_breakdown = getattr(metrics, "tool_breakdown", None)

    signals: list[dict] = []
    for metric_key, skill_maps in mappings.items():
        value = metric_values.get(metric_key)
        if value is None:
            continue
        for m in skill_maps:
            score = m["score_fn"](value)
            if score <= 0:
                continue
            evidence = metrics.evidence.get(metric_key, "detected")
            ctx = _rate_context(evidence)
            if per_project:
                ctx["per_project"] = per_project
            if tool_breakdown:
                ctx["tool_breakdown"] = tool_breakdown
            signals.append(
                {
                    "skill_id": m["skill_id"],
                    "score": score,
                    "evidence": evidence,
                    "scoring_context": ctx,
                }
            )

    return signals


def calculate_review_scores(metrics, mappings: dict) -> list[dict]:
    """Calculate skill scores from MR review behavioral metrics.

    Args:
        metrics: ReviewMetrics object from ReviewScanner.scan().
        mappings: REVIEW_SKILL_MAPPINGS dict mapping metric keys to skill maps.

    Returns:
        List of {skill_id, score, evidence} dicts. Only scores > 0 are included.
    """
    if metrics is None:
        return []

    metric_values = {
        "lgtm_without_comment": metrics.lgtm_rate,
        "review_comment_depth": metrics.review_comment_depth,
        "self_review_rate": metrics.self_review_rate,
    }

    per_project = getattr(metrics, "per_project", None)

    signals: list[dict] = []
    for metric_key, skill_maps in mappings.items():
        value = metric_values.get(metric_key)
        if value is None:
            continue
        for m in skill_maps:
            score = m["score_fn"](value)
            if score <= 0:
                continue
            evidence = metrics.evidence.get(metric_key, "detected")
            ctx = _rate_context(evidence)
            if per_project:
                ctx["per_project"] = per_project
            signals.append(
                {
                    "skill_id": m["skill_id"],
                    "score": score,
                    "evidence": evidence,
                    "scoring_context": ctx,
                }
            )

    return signals


def calculate_member_scores(
    member_results: list,
    mappings: list[dict],
) -> list[dict]:
    """Calculate skill scores from member activity scan results.

    Score is based on the percentage of members who have any co-author
    commits for each pattern. E.g., if 3/5 members have Claude co-author
    commits, the score for Claude-related skills is 60.

    Args:
        member_results: List of MemberResult objects.
        mappings: List of mapping dicts with artifact_id, skill_id, weight.

    Returns:
        List of {skill_id, score, evidence} dicts.
    """
    if not member_results:
        return []

    num_members = len(member_results)

    # Count how many members have each pattern
    pattern_member_counts: dict[str, int] = defaultdict(int)
    pattern_total_commits: dict[str, int] = defaultdict(int)
    # Aggregate per-repo commit counts across all members (team-level only, no usernames)
    repo_commit_counts: dict[str, int] = defaultdict(int)
    for result in member_results:
        for pattern_id, count in result.ai_coauthor_counts.items():
            if count > 0:
                pattern_member_counts[pattern_id] += 1
                pattern_total_commits[pattern_id] += count
        for repo_name, counts in getattr(result, "repo_coauthor_counts", {}).items():
            for count in counts.values():
                repo_commit_counts[repo_name] += count

    # Build repos_with_activity sorted by commit count desc
    repos_with_activity = sorted(repo_commit_counts.keys(), key=lambda r: -repo_commit_counts[r])

    # Group mappings by skill_id
    skill_mappings: dict[str, list[dict]] = defaultdict(list)
    for m in mappings:
        skill_mappings[m["skill_id"]].append(m)

    signals: list[dict] = []

    for skill_id, skill_maps in skill_mappings.items():
        found_weight = 0.0
        total_weight = 0.0
        evidence_parts = []

        for m in skill_maps:
            aid = m["artifact_id"]
            total_weight += m["weight"]
            member_count = pattern_member_counts.get(aid, 0)
            if member_count > 0:
                # Weight by proportion of members with this pattern
                found_weight += m["weight"] * (member_count / num_members)
                commits = pattern_total_commits.get(aid, 0)
                # Get pattern display name
                from ai_fluency_collector.scanners.gitlab_member_scanner import (
                    AI_COAUTHOR_PATTERNS,
                )

                name = aid
                for p in AI_COAUTHOR_PATTERNS:
                    if p["id"] == aid:
                        name = p["name"]
                        break

                # Include repo names in evidence
                repo_detail = ""
                if repos_with_activity:
                    short_names = [_short_name(r) for r in repos_with_activity]
                    repo_detail = f" across {', '.join(short_names)}"

                evidence_parts.append(
                    f"Co-authored commits with {name} "
                    f"by {member_count}/{num_members} members "
                    f"({commits} commits{repo_detail})"
                )

        if total_weight > 0:
            score = round(min(100.0, (found_weight / total_weight) * 100.0))
        else:
            score = 0

        if score <= 0:
            continue

        evidence = "; ".join(evidence_parts) if evidence_parts else "detected"

        # scoring_context: what score if all members had each found pattern?
        max_found_weight = sum(
            m["weight"] for m in skill_maps if pattern_member_counts.get(m["artifact_id"], 0) > 0
        )
        max_signal = (
            round(min(100.0, (max_found_weight / total_weight) * 100.0)) if total_weight > 0 else 0
        )
        breakdown = evidence  # member fraction already described in evidence
        missing_signals = list(
            dict.fromkeys(
                m["artifact_id"]
                for m in skill_maps
                if pattern_member_counts.get(m["artifact_id"], 0) == 0
            )
        )
        ctx: dict = {"breakdown": breakdown, "max_from_this_signal": max_signal}
        if missing_signals:
            ctx["missing_signals"] = missing_signals
        if repos_with_activity:
            ctx["repos_with_activity"] = repos_with_activity
            ctx["total_commits"] = sum(repo_commit_counts.values())
            ctx["members_with_activity"] = sum(1 for r in member_results if r.ai_coauthor_counts)
            ctx["total_members"] = num_members
        signals.append(
            {
                "skill_id": skill_id,
                "score": score,
                "evidence": evidence,
                "scoring_context": ctx,
            }
        )

    return signals


def _get_artifact_name(artifact_id: str) -> str:
    """Look up the human-readable artifact name."""
    from ai_fluency_collector.scanners.gitlab_artifact_scanner import ARTIFACT_DEFINITIONS

    for defn in ARTIFACT_DEFINITIONS:
        if defn["id"] == artifact_id:
            return defn["name"]
    return artifact_id


def calculate_scores(
    scan_results: list[dict[str, bool | float]],
    mappings: list[dict],
    artifact_names: dict[str, str] | None = None,
    project_names: list[str] | None = None,
) -> list[dict]:
    """Calculate weighted skill scores from scan results across multiple projects.

    Args:
        scan_results: List of per-project dicts {artifact_id: bool_or_float}.
            Values can be bool (True/False) or float (0.0 = not found,
            0.5 = default branch, 0.8 = feature branch). Float values
            scale the mapping weight by the branch weight.
        mappings: List of mapping dicts with artifact_id, skill_id, weight.
        artifact_names: Optional dict of {artifact_id: display_name} for evidence.
        project_names: Optional list of project paths, aligned with scan_results.

    Returns:
        List of {skill_id, score, evidence} dicts. Only skills with score > 0 are included.
    """
    if not scan_results:
        return []

    num_projects = len(scan_results)

    # Group mappings by skill_id
    skill_mappings: dict[str, list[dict]] = defaultdict(list)
    for m in mappings:
        skill_mappings[m["skill_id"]].append(m)

    from ai_fluency_collector.scanners.gitlab_artifact_scanner import (
        DEFAULT_BRANCH_WEIGHT,
        FEATURE_BRANCH_WEIGHT,
    )

    signals: list[dict] = []

    for skill_id, skill_maps in skill_mappings.items():
        total_weight = sum(m["weight"] for m in skill_maps)

        # Per-project scores and artifact tracking
        project_scores: list[float] = []
        artifact_counts: dict[str, int] = defaultdict(int)
        feature_counts: dict[str, int] = defaultdict(int)
        default_counts: dict[str, int] = defaultdict(int)
        # Track which projects have each artifact on which branch type
        artifact_default_projects: dict[str, list[str]] = defaultdict(list)
        artifact_feature_projects: dict[str, list[str]] = defaultdict(list)
        artifact_missing_projects: dict[str, list[str]] = defaultdict(list)
        # Track actual branch names and counts per project per artifact
        artifact_branch_names: dict[str, dict[str, str]] = defaultdict(dict)
        artifact_branch_counts: dict[str, dict[str, int]] = defaultdict(dict)
        artifact_all_branches: dict[str, dict[str, list[str]]] = defaultdict(dict)

        for idx, project_result in enumerate(scan_results):
            proj_name = project_names[idx] if project_names and idx < len(project_names) else None
            found_weight = 0.0
            for m in skill_maps:
                aid = m["artifact_id"]
                raw = project_result.get(aid, False)
                # Support both old format (float/bool) and new format (dict)
                if isinstance(raw, dict):
                    value = raw.get("weight", 0.0)
                    branch_name = raw.get("branch")
                    branch_count = raw.get("branch_count", 1 if branch_name else 0)
                    all_branches = raw.get("branches", [])
                else:
                    value = raw
                    branch_name = None
                    branch_count = 0
                    all_branches = []
                if isinstance(value, (int, float)) and value > 0:
                    found_weight += m["weight"] * value
                    artifact_counts[aid] += 1
                    if value >= FEATURE_BRANCH_WEIGHT:
                        feature_counts[aid] += 1
                        if proj_name:
                            artifact_feature_projects[aid].append(proj_name)
                            if branch_name:
                                artifact_branch_names[aid][proj_name] = branch_name
                            if branch_count:
                                artifact_branch_counts[aid][proj_name] = branch_count
                            if all_branches:
                                artifact_all_branches[aid][proj_name] = all_branches
                    elif value >= DEFAULT_BRANCH_WEIGHT:
                        default_counts[aid] += 1
                        if proj_name:
                            artifact_default_projects[aid].append(proj_name)
                            if branch_name:
                                artifact_branch_names[aid][proj_name] = branch_name
                            if branch_count:
                                artifact_branch_counts[aid][proj_name] = branch_count
                            if all_branches:
                                artifact_all_branches[aid][proj_name] = all_branches
                elif value is True:
                    found_weight += m["weight"]
                    artifact_counts[aid] += 1
                    feature_counts[aid] += 1  # bool True = best branch
                    if proj_name:
                        artifact_feature_projects[aid].append(proj_name)
                else:
                    if proj_name:
                        artifact_missing_projects[aid].append(proj_name)
            if total_weight > 0:
                project_scores.append(min(100.0, (found_weight / total_weight) * 100.0))
            else:
                project_scores.append(0.0)

        avg_score = sum(project_scores) / num_projects if project_scores else 0.0
        score = round(avg_score)

        if score <= 0:
            continue

        # Evidence: artifact presence counts with project names
        evidence_parts = []
        for m in skill_maps:
            aid = m["artifact_id"]
            if artifact_counts[aid] > 0:
                name = artifact_names.get(aid, aid) if artifact_names else _get_artifact_name(aid)
                count = artifact_counts[aid]
                found_projects = artifact_default_projects[aid] + artifact_feature_projects[aid]
                if found_projects:
                    proj_names_str = ", ".join(_short_name(p) for p in found_projects)
                    evidence_parts.append(
                        f"{name} found in {count}/{num_projects} projects: {proj_names_str}"
                    )
                else:
                    evidence_parts.append(f"{name} found in {count}/{num_projects} projects")
        evidence = "; ".join(evidence_parts) if evidence_parts else "detected"

        # scoring_context: human-readable explanation of current state and how to improve
        breakdown_parts = []
        per_project: dict[str, dict] = {}
        for m in skill_maps:
            aid = m["artifact_id"]
            feat = feature_counts[aid]
            dflt = default_counts[aid]
            total_found = feat + dflt
            if total_found == 0:
                continue
            name = artifact_names.get(aid, aid) if artifact_names else _get_artifact_name(aid)
            missing = num_projects - total_found
            breakdown_parts.append(
                _artifact_breakdown(
                    name,
                    feat,
                    dflt,
                    missing,
                    num_projects,
                    default_projects=artifact_default_projects.get(aid),
                    feature_projects=artifact_feature_projects.get(aid),
                    missing_projects=artifact_missing_projects.get(aid),
                    branch_names=artifact_branch_names.get(aid),
                    branch_counts=artifact_branch_counts.get(aid),
                )
            )

            # Build per_project data for this artifact
            if project_names:
                bnames = artifact_branch_names.get(aid, {})
                bcounts = artifact_branch_counts.get(aid, {})
                all_br = artifact_all_branches.get(aid, {})
                for p in artifact_default_projects.get(aid, []):
                    per_project.setdefault(p, {})["found"] = True
                    per_project[p]["branch"] = "default"
                    per_project[p]["weight"] = DEFAULT_BRANCH_WEIGHT
                    if p in bnames:
                        per_project[p]["branch_name"] = bnames[p]
                    if p in bcounts:
                        per_project[p]["branch_count"] = bcounts[p]
                    if p in all_br:
                        per_project[p]["branches"] = all_br[p]
                for p in artifact_feature_projects.get(aid, []):
                    per_project.setdefault(p, {})["found"] = True
                    per_project[p]["branch"] = "feature"
                    per_project[p]["weight"] = FEATURE_BRANCH_WEIGHT
                    if p in bnames:
                        per_project[p]["branch_name"] = bnames[p]
                    if p in bcounts:
                        per_project[p]["branch_count"] = bcounts[p]
                    if p in all_br:
                        per_project[p]["branches"] = all_br[p]
                for p in artifact_missing_projects.get(aid, []):
                    per_project.setdefault(p, {})["found"] = False

        breakdown = " ".join(breakdown_parts) if breakdown_parts else evidence

        max_found_weight = 0.0
        for m in skill_maps:
            aid = m["artifact_id"]

            def _extract_weight(raw):
                if isinstance(raw, dict):
                    return float(raw.get("weight", 0))
                return float(raw) if raw else 0.0

            best = max((_extract_weight(r.get(aid, 0)) for r in scan_results), default=0.0)
            if best > 0:
                max_found_weight += m["weight"] * best
        max_signal = (
            round(min(100.0, max_found_weight / total_weight * 100.0)) if total_weight > 0 else 0
        )

        missing_signals = list(
            dict.fromkeys(
                m["artifact_id"] for m in skill_maps if artifact_counts[m["artifact_id"]] == 0
            )
        )
        ctx: dict = {"breakdown": breakdown, "max_from_this_signal": max_signal}
        if missing_signals:
            ctx["missing_signals"] = missing_signals
        if per_project:
            ctx["per_project"] = per_project
        signals.append(
            {
                "skill_id": skill_id,
                "score": score,
                "evidence": evidence,
                "scoring_context": ctx,
            }
        )

    return signals
