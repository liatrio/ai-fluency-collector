# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Fluency Collector is a Python CLI tool that scans GitLab repositories for evidence of AI adoption and outputs a JSON file compatible with the ai-fluency application's import format. It detects AI tool artifacts (CLAUDE.md, .mcp.json, .cursorrules, etc.) and CI pipeline patterns (SAST, secret detection, AI code review) across a team's repositories, calculates weighted skill scores, and produces importable JSON.

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
- **Config**: YAML config files define a team (name, code, members, project list). GitLab token comes from `GITLAB_TOKEN` env var.
- **Scanners** (`scanners/`): Two scanners produce boolean found/not-found results per artifact per project:
  - Artifact scanner: checks GitLab repos for AI tool files/directories via Repository Files and Tree APIs
  - CI scanner: parses `.gitlab-ci.yml` for security/AI/deployment patterns including `include` template directives
- **Scoring** (`scoring.py`): All artifact-to-skill mappings and weights live in a single declarative data structure, separate from scanner logic. Formula: `min(100, sum(found_weights) / sum(all_weights) * 100)`, averaged across team projects. Changes to weights or mappings should only require editing this data structure.
- **Output** (`output.py`): Merges signals into JSON matching the ai-fluency import schema: `{ team_code, survey_period, sources: [{ source_id, signals: [{ skill_id, score, evidence }] }] }`

## Key Constraints

- Python 3.10+ (modern type hint syntax)
- GitLab.com (SaaS) only, default branch only
- `source_id` values must be exactly `gitlab-repo-artifacts` and `gitlab-ci-config`
- Skill IDs must exactly match the skill tree in `ai-fluency/app/src/types/quantitative.ts`
- `docs/scoring.md` must stay in sync with the scoring data structure in code
- Output JSON files and team config YAML files should be gitignored
