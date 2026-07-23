# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Fluency Collector is a Python CLI tool that scans GitLab and GitHub repositories and team member activity for evidence of AI adoption, outputting a JSON file compatible with the ai-fluency application's import format. It has two scan modes:

- **GitLab (`afc scan`)**: repo artifact detection (CLAUDE.md, .mcp.json, .cursorrules, etc.), CI pipeline patterns (SAST, secret detection, AI code review), member activity scanning (AI co-authored commits across all repos members touch), and MR review behavioral metrics.
- **GitHub (`afc github-scan`)**: repo artifact detection with tiered scoring, and PR review behavioral metrics including AI co-author rates.

## Build & Run Commands

```bash
pip install -e .                                      # Install in dev mode
afc scan --config team.yaml                           # GitLab scan
afc scan --config team.yaml --period 2026-W12         # Override period
afc github-scan --config team.yaml                    # GitHub scan
```

## Testing

```bash
pytest                          # Run all tests
pytest tests/test_config.py     # Run a single test file
pytest -k test_name             # Run a single test by name
```

## Linting

```bash
ruff check .                    # Lint
ruff format .                   # Format
```

## Architecture

- **Package**: `src/ai_fluency_collector/`
- **CLI framework**: click, entrypoint defined via `pyproject.toml` console_scripts
- **Config**: YAML config files define a team (name, code, members as GitLab/GitHub usernames). `members` is required. `projects` (GitLab paths) and `github_repos` (`owner/repo` strings) are each optional but at least one must be present. GitLab token: `GITLAB_TOKEN` env var; GitHub token: `GITHUB_TOKEN` env var.
- **Scanners** (`scanners/`): Five scanners across two platforms:
  - `gitlab_artifact_scanner.py`: checks listed GitLab repos across all active branches for AI tool files/directories. Feature branch artifacts (weight 0.8) score higher than default branch (0.5).
  - `gitlab_ci_scanner.py`: parses `.gitlab-ci.yml` across all active branches for security/AI/deployment patterns including `include` template directives. Same branch weighting.
  - `gitlab_member_scanner.py`: discovers repos each member owns or pushes to (via Users/Events APIs), then scans commits for AI co-author patterns (Claude, Copilot, Cursor). Only commit-level signals on discovered repos — no full artifact/CI scan.
  - `github_artifact_scanner.py`: checks listed GitHub repos for AI tool files/directories using **tiered scoring** (score varies by line count / file count, not binary presence). Aggregates with MAX across repos.
  - `github_review_scanner.py`: scans GitHub PRs for the survey period for behavioral metrics: LGTM rate, review comment depth, AI co-author rate, AI agent co-author rate, self-review rate.
  - `gitlab_mr_scanner.py`: scans merged MRs for AI-attributed MRs (via commit co-author tags), computes median PR size (`changes_count`) and median coding time (first commit → MR open, in hours). Reuses commits already fetched for co-author detection — no extra API calls. Only AI-attributed MRs are included; no signal if none found.
- **Scoring**: Two modules:
  - `gitlab_scoring.py`: Declarative mapping data structures: `ARTIFACT_SKILL_MAPPINGS`, `CI_SKILL_MAPPINGS`, `MEMBER_SKILL_MAPPINGS`, `REVIEW_SKILL_MAPPINGS`, `MR_COAUTHOR_SKILL_MAPPINGS`, `MR_SIZE_SKILL_MAPPINGS`, `MR_CODING_TIME_SKILL_MAPPINGS`.
  - `github_scoring.py`: `GITHUB_REVIEW_SKILL_MAPPINGS` for GitHub PR metrics and `calculate_github_review_scores()`.
- **Output** (`output.py`): Merges signals into JSON matching the ai-fluency import schema: `{ team_code, survey_period, sources: [{ source_id, signals: [{ skill_id, score, evidence }] }] }`

## Key Constraints

- Python 3.10+ (modern type hint syntax)
- Supports GitLab.com and self-hosted GitLab instances (`gitlab_url` in config); supports GitHub.com only for GitHub scanning
- Active branches = commits within 90 days (GitLab only; GitHub scanning is not branch-scoped)
- `source_id` values must be exactly: `gitlab-repo-artifacts`, `gitlab-ci-config`, `gitlab-member-activity`, `gitlab-review-signals`, `gitlab-mr`, `github-repo-artifacts`, `github-review-signals`
- Skill IDs must exactly match the skill tree in `ai-fluency/app/src/types/quantitative.ts`
- `docs/scoring.md` must stay in sync with the scoring data structures in `gitlab_scoring.py` and `github_scoring.py`
- Output JSON files and team config YAML files should be gitignored
