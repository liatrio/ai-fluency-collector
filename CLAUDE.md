# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Fluency Collector is a Python CLI tool that scans GitLab repositories and team member activity for evidence of AI adoption, outputting a JSON file compatible with the ai-fluency application's import format. It has three signal sources: repo artifact detection (CLAUDE.md, .mcp.json, .cursorrules, etc.), CI pipeline patterns (SAST, secret detection, AI code review), and member activity scanning (AI co-authored commits across all repos members touch).

## Build & Run Commands

```bash
pip install -e .                              # Install in dev mode
ai-fluency-collector --config team.yaml       # Run with config
ai-fluency-collector --config team.yaml --period 2026-W12  # Override period
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
- **Config**: YAML config files define a team (name, code, members as GitLab usernames, project list). GitLab token comes from `GITLAB_TOKEN` env var. Both `members` and `projects` are required non-empty lists.
- **Scanners** (`scanners/`): Three scanners:
  - Artifact scanner: checks listed GitLab repos for AI tool files/directories via Repository Files and Tree APIs
  - CI scanner: parses `.gitlab-ci.yml` for security/AI/deployment patterns including `include` template directives
  - Member scanner: discovers repos each member owns or pushes to (via Users/Events APIs), then scans commits for AI co-author patterns (Claude, Copilot, Cursor). Only commit-level signals on discovered repos — no full artifact/CI scan.
- **Scoring** (`scoring.py`): Three declarative mapping data structures (`ARTIFACT_SKILL_MAPPINGS`, `CI_SKILL_MAPPINGS`, `MEMBER_SKILL_MAPPINGS`), separate from scanner logic. Changes to weights or mappings should only require editing these data structures.
- **Output** (`output.py`): Merges signals into JSON matching the ai-fluency import schema: `{ team_code, survey_period, sources: [{ source_id, signals: [{ skill_id, score, evidence }] }] }`

## Key Constraints

- Python 3.10+ (modern type hint syntax)
- GitLab.com (SaaS) only, default branch only
- `source_id` values must be exactly `gitlab-repo-artifacts`, `gitlab-ci-config`, and `gitlab-member-activity`
- Skill IDs must exactly match the skill tree in `ai-fluency/app/src/types/quantitative.ts`
- `docs/scoring.md` must stay in sync with the scoring data structure in code
- Output JSON files and team config YAML files should be gitignored
