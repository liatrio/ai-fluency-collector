# 01-spec-gitlab-collector

## Introduction/Overview

The AI Fluency Collector is a standalone Python CLI tool that scans GitLab repositories for evidence of AI adoption and outputs a JSON file compatible with the ai-fluency application's import format. It addresses the gap between subjective survey data (Formbricks) and objective, measurable signals by automatically detecting AI tool artifacts and CI pipeline patterns across a team's repositories.

The collector reads a YAML config file defining a team (name, code, members with GitLab usernames, project list), authenticates with GitLab.com via an environment variable token, scans each project for artifact presence and CI configuration patterns, discovers member AI activity across all repos they touch, calculates weighted skill scores, and writes a single JSON file ready for import.

## Goals

- Automate the collection of quantitative AI adoption signals from GitLab repositories
- Produce a JSON file that passes the ai-fluency import schema validation without manual editing
- Support three signal sources in the initial release: GitLab Repo Artifacts, GitLab CI Config, and GitLab Member Activity
- Use weighted scoring so that deeper adoption (multiple artifacts per skill) produces higher scores than surface-level presence
- Fail fast and clearly when a project is inaccessible so the operator knows exactly what to fix

## User Stories

- **As a team lead**, I want to run a single command against my team's GitLab projects and member handles so that I get an objective, data-backed view of our AI adoption without relying solely on self-reported surveys.
- **As a team lead**, I want to discover AI usage by my team members across repos I didn't explicitly list, so that I capture adoption signals that would otherwise be invisible.
- **As a platform engineer**, I want the collector to output a file I can directly upload to the ai-fluency import page so that I don't have to manually construct JSON.
- **As a consultant**, I want a simple YAML config per client team so that I can run the collector across multiple engagements without mixing data.

## Demoable Units of Work

### Unit 1: Project Scaffolding and Config Parsing

**Purpose:** Establish the Python project structure, CLI entrypoint, and YAML config parsing so the tool can be installed and invoked.

**Functional Requirements:**
- The system shall be installable via `pip install -e .` from the repo root
- The CLI shall accept a `--config` flag pointing to a YAML file and a `--period` flag to override the survey period
- The CLI shall default the survey period to the current ISO week (YYYY-WNN) when `--period` is not provided
- The system shall parse the YAML config and validate required fields: `team.name`, `team.code`, `team.members` (list of GitLab usernames, non-empty), `team.projects` (non-empty list)
- The system shall read the GitLab token from the `GITLAB_TOKEN` environment variable
- The CLI shall provide clear, actionable error messages for every failure mode a user is likely to encounter:
  - Config file does not exist: "Config file not found: {path}. Create one from config.example.yaml"
  - Config file has invalid YAML syntax: "Failed to parse {path}: {parse error details}"
  - Required config fields missing: "Missing required field: team.code" (list each missing field)
  - `GITLAB_TOKEN` not set: "GITLAB_TOKEN environment variable is not set. Export a token with read_api scope."
  - `GITLAB_TOKEN` is invalid (401 from API): "GitLab authentication failed. Check that GITLAB_TOKEN is valid and has read_api scope."
  - `--period` format is wrong: "Invalid period format: {value}. Expected YYYY-WNN (e.g. 2026-W12)"
- The CLI shall validate all preconditions (config, token, period format) before making any GitLab API calls
- The CLI shall display a startup banner summarizing what it will do: team name, number of projects, survey period, and output file path
- The system shall include a `config.example.yaml` in the repo root with comments explaining each field

**Proof Artifacts:**
- CLI: `ai-fluency-collector --help` output demonstrates the tool is installed and shows available flags
- CLI: `ai-fluency-collector --config nonexistent.yaml` demonstrates file-not-found error with guidance
- CLI: `ai-fluency-collector --config team.yaml` with missing `GITLAB_TOKEN` demonstrates clear error with fix instructions
- CLI: `ai-fluency-collector --config team.yaml` with valid setup demonstrates startup banner before scanning
- Test: `test_config.py` passes, demonstrating YAML parsing and validation
- Test: `test_cli.py` passes, demonstrating error messages for each failure mode

### Unit 2: GitLab Repo Artifact Scanner

**Purpose:** Connect to GitLab.com API and detect AI adoption artifacts in each project's file tree.

**Functional Requirements:**
- The system shall use the GitLab REST API (v4) to check for file/directory existence in each project listed in the config
- The system shall detect the following artifacts per project:
  - `CLAUDE.md` (maps to: cq-context, im-autocomplete)
  - `.claude/settings.json` (maps to: tg-permission-gated)
  - `.mcp.json` or `mcp.json` (maps to: im-chat, pm-core)
  - `prompts/` directory (maps to: ks-patterns, cq-delegation)
  - `.cursorrules` or `.cursor/` (maps to: im-autocomplete, im-inline-edit)
  - `.github/copilot-instructions.md` (maps to: im-autocomplete)
  - `AGENTS.md` or `.agents/` (maps to: im-supervised-agent, im-cli-agent)
  - `.aider.conf.yml`, `.aider.model.settings.yml`, or `.aiderignore` (maps to: im-chat)
- The system shall fail the entire run with a clear error if any project in the config is inaccessible (404, 403, or network error)
- The system shall calculate weighted skill scores (0-100) per skill across all team projects, where multiple contributing artifacts increase the score for that skill beyond what a single artifact would produce
- The system shall include an `evidence` string for each signal describing which artifacts were found and in how many projects (e.g., "CLAUDE.md found in 3/4 projects")

**Proof Artifacts:**
- CLI: `ai-fluency-collector --config team.yaml` run against real GitLab projects demonstrates artifact detection
- Test: `test_artifact_scanner.py` passes with mocked GitLab API responses, demonstrating detection logic and scoring

### Unit 3: GitLab CI Config Scanner

**Purpose:** Parse `.gitlab-ci.yml` from each project and detect CI pipeline patterns that indicate AI and security tool adoption.

**Functional Requirements:**
- The system shall fetch `.gitlab-ci.yml` from each project via the GitLab API
- The system shall detect the following CI patterns:
  - SAST/DAST scanner stages (maps to: sdlc-security, tg-security-gates)
  - Secret detection jobs (maps to: sdlc-security)
  - AI-assisted code review jobs such as GitLab Duo or third-party integrations (maps to: tg-code-review)
  - AI-powered test generation stages (maps to: sdlc-testing)
  - Dependency scanning jobs (maps to: sdlc-security)
  - Code coverage reporting (maps to: pm-measurement)
  - Deployment stages with automated gates or environment rules (maps to: sdlc-deployment, tg-supervised-auto)
- The system shall parse YAML `include` directives to detect GitLab CI templates (e.g., `Security/SAST.gitlab-ci.yml`)
- The system shall skip CI scanning gracefully (score 0, no error) for projects that have no `.gitlab-ci.yml`
- The system shall calculate weighted skill scores (0-100) per skill, where multiple related CI patterns increase the score
- The system shall include an `evidence` string for each signal (e.g., "SAST template included in 2/4 projects, secret-detection job in 3/4 projects")

**Proof Artifacts:**
- CLI: `ai-fluency-collector --config team.yaml` run against projects with CI configs demonstrates pattern detection
- Test: `test_ci_scanner.py` passes with mocked `.gitlab-ci.yml` content, demonstrating pattern matching and scoring

### Unit 4: JSON Output and End-to-End Flow

**Purpose:** Combine artifact and CI signals into a single JSON file matching the ai-fluency import schema.

**Functional Requirements:**
- The system shall merge signals from all sources (gitlab-repo-artifacts, gitlab-ci-config, gitlab-member-activity) into a single output file
- The output JSON shall conform to the ai-fluency import schema: `{ team_code, survey_period, sources: [{ source_id, signals: [{ skill_id, score, evidence }] }] }`
- The `source_id` values shall be exactly `gitlab-repo-artifacts`, `gitlab-ci-config`, and `gitlab-member-activity`
- The system shall only include sources that produced at least one signal (omit empty source blocks)
- The system shall write the output file to `{team_code}-{survey_period}.json` in the current working directory
- The system shall print a summary to stdout after writing: file path, number of sources, total signals, and team code
- The output JSON shall be importable into the ai-fluency application without modification
- The repository shall include a `docs/scoring.md` file that documents: (1) every artifact and CI pattern the collector detects, (2) which skill_id each maps to, (3) the weight assigned to each mapping, (4) the scoring formula with a worked example, and (5) instructions for how to modify weights or add new mappings
- The `docs/scoring.md` file shall be kept in sync with the scoring data structure in code; if the mapping changes, the docs must be updated in the same commit

**Proof Artifacts:**
- CLI: Full end-to-end run produces a valid JSON file and prints a summary
- Test: `test_output.py` passes, demonstrating JSON structure, schema conformance, and file writing
- Import: The output file is successfully imported via the ai-fluency Import page
- Doc: `docs/scoring.md` exists and accurately reflects the scoring mappings in code

### Unit 5: GitLab Member Activity Scanner

**Purpose:** Discover AI adoption signals across all repos team members touch, not just the explicitly listed projects, by scanning member activity for AI co-authored commits.

**Functional Requirements:**
- The config `team.members` field shall contain GitLab usernames (not display names)
- The system shall validate that each member username exists on GitLab.com via the Users API
- The system shall discover all projects each member owns via the Users Projects API
- The system shall discover all projects each member has recently pushed to via the Events API (push events)
- The system shall combine owned and active projects into a deduplicated set of "member repos" per team (excluding projects already in `team.projects` to avoid double-counting)
- The system shall search commit messages in member repos for AI co-author patterns:
  - `Co-Authored-By: Claude` (or `Co-authored-by:` case-insensitive)
  - `Co-Authored-By: GitHub Copilot`
  - `Co-Authored-By: Cursor`
- The system shall only scan commits authored by team members (filter by member username/email)
- The system shall scope commit scanning to a reasonable time window (e.g., last 90 days or configurable)
- The system shall calculate weighted skill scores based on the presence and frequency of AI co-authored commits across member repos
- The system shall include an `evidence` string for each signal (e.g., "Co-authored commits with Claude found for 3/5 members across 7 repos")
- The system shall NOT run full artifact or CI scans on discovered member repos (only commit-level signals)
- The system shall handle members with no public activity gracefully (score 0, no error)

**Proof Artifacts:**
- CLI: `ai-fluency-collector --config team.yaml` run with member usernames shows discovered repos and AI co-author signals
- Test: `test_member_scanner.py` passes with mocked GitLab API responses, demonstrating member repo discovery and co-author detection
- Test: Members with no activity produce score 0 with no error

## Non-Goals (Out of Scope)

1. **GitLab Duo Metrics**: Telemetry-based signals (code suggestion acceptance rates) require different API access and are deferred to a future release
2. **Self-hosted GitLab**: Only GitLab.com (SaaS) is supported initially
3. **Multiple teams per run**: Each config file defines one team; run the tool multiple times for multiple teams
4. **Automatic upload**: The tool produces a JSON file; uploading to the ai-fluency app is a manual step
5. **GitHub support**: This spec covers GitLab only; a GitHub collector would be a separate effort
6. **Branch scanning**: The collector scans the default branch only, not feature branches

## Design Considerations

No specific design requirements identified. This is a CLI tool with no UI. Output is JSON and stdout text.

## Repository Standards

This is a new repository. The following standards will be established:

- **Project structure**: `src/ai_fluency_collector/` package with `cli.py`, `config.py`, `scanners/`, `scoring.py`, `output.py`
- **Package manager**: pip + `requirements.txt` for runtime deps, `requirements-dev.txt` for test/lint deps
- **CLI framework**: click
- **Testing**: pytest with mocked HTTP responses (responses or pytest-httpx library)
- **Python version**: 3.10+ (for modern type hint syntax)
- **Code style**: ruff for linting and formatting
- **Entry point**: `ai-fluency-collector` CLI command via `pyproject.toml` console_scripts

## Technical Considerations

- **GitLab API**: Uses the [Repository Files API](https://docs.gitlab.com/ee/api/repository_files.html) for artifact checks and the [Repository Tree API](https://docs.gitlab.com/ee/api/repositories.html#list-repository-tree) for directory detection
- **Rate limiting**: GitLab.com has API rate limits (authenticated: 2000 req/min). For a typical team with 5-10 projects and ~15 file checks each, this is well within limits. No special rate limiting logic needed initially.
- **CI YAML parsing**: Use Python's `yaml.safe_load` to parse `.gitlab-ci.yml`. Handle `include` directives by checking for known template paths in the include list, not by fetching included files recursively.
- **Weighted scoring (must be easy to tune)**: The scoring logic is the part of the system most likely to change based on real-world feedback. All artifact-to-skill mappings and their weights must live in a single, declarative data structure (e.g., a Python dict or YAML file) that is separate from the scanning logic. Scanners produce boolean "found/not-found" results per artifact per project. The scoring module reads the mapping, combines the scanner results, and computes scores. This separation means adjusting which artifacts contribute to which skills, or changing a weight from 0.3 to 0.5, requires editing one data structure with zero changes to scanner or output code. The formula is: `min(100, sum(found_weights) / sum(all_weights) * 100)`, averaged across team projects.
- **Output schema**: Must match the Zod schema in `ai-fluency/app/src/types/quantitative.ts`. Skill IDs must be exact matches from the skill tree.
- **Member Activity API**: Uses the [Users API](https://docs.gitlab.com/ee/api/users.html) to look up members, the [User Projects API](https://docs.gitlab.com/ee/api/projects.html#list-user-projects) to find owned projects, the [Events API](https://docs.gitlab.com/ee/api/events.html#list-a-users-contribution-events) to find push events, and the [Commits API](https://docs.gitlab.com/ee/api/commits.html) to read commit messages for co-author patterns.
- **Rate limiting for member scanning**: Member activity scanning may require significantly more API calls than project scanning (events + commits for each discovered repo). For a team of 5 members with 10 repos each, this could be ~100+ API calls. Still within GitLab's 2000 req/min limit but worth monitoring.

## Security Considerations

- **GitLab token**: Read from `GITLAB_TOKEN` environment variable, never from config files. The token needs `read_api` scope at minimum.
- **No token in output**: The JSON output file must not contain the GitLab token or any credentials.
- **No token in logs**: CLI output and error messages must not print the token value.
- **.gitignore**: Output JSON files (`*-W*.json`) should be in `.gitignore` to prevent accidental commits of team data.
- **Config files**: Team config YAML files may contain project paths that reveal internal organization structure. Include `*.yaml` in `.gitignore` as a default, with a `config.example.yaml` checked in.

## Success Metrics

1. **Schema compatibility**: Output JSON passes ai-fluency Zod validation and imports successfully on the first attempt
2. **Artifact coverage**: Detects all 8 artifact types (A-H from requirements) across real GitLab projects
3. **CI pattern coverage**: Detects all 7 CI patterns (A-G from requirements) from real `.gitlab-ci.yml` files
4. **Scoring accuracy**: Weighted scores reflect actual adoption depth (a project with CLAUDE.md + prompts/ + .mcp.json scores higher than one with only CLAUDE.md)
5. **Execution time**: Completes scanning of 10 projects in under 30 seconds

## Open Questions

No open questions at this time.
