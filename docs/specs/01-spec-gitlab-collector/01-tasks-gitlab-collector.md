# 01-tasks-gitlab-collector

## Relevant Files

- `pyproject.toml` - Package metadata, dependencies, console_scripts entrypoint, ruff config
- `requirements.txt` - Runtime dependencies (click, pyyaml, requests)
- `requirements-dev.txt` - Dev/test dependencies (pytest, responses/pytest-httpx, ruff)
- `config.example.yaml` - Example team config with comments explaining each field
- `.gitignore` - Ignore output JSON, team YAML configs, venv, __pycache__
- `src/ai_fluency_collector/__init__.py` - Package init
- `src/ai_fluency_collector/cli.py` - Click CLI entrypoint with --config, --period flags and error handling
- `src/ai_fluency_collector/config.py` - YAML config parsing and validation
- `src/ai_fluency_collector/gitlab_client.py` - GitLab REST API v4 client (file existence, tree listing, file content)
- `src/ai_fluency_collector/scanners/__init__.py` - Scanners package init
- `src/ai_fluency_collector/scanners/artifact_scanner.py` - Repo artifact detection (8 artifact types)
- `src/ai_fluency_collector/scanners/ci_scanner.py` - CI config pattern detection (7 CI patterns)
- `src/ai_fluency_collector/scoring.py` - Declarative mapping data structure and scoring engine
- `src/ai_fluency_collector/output.py` - JSON output builder and file writer
- `tests/__init__.py` - Tests package init
- `tests/test_cli.py` - CLI error handling and flag tests
- `tests/test_config.py` - Config parsing and validation tests
- `tests/test_artifact_scanner.py` - Artifact detection tests with mocked GitLab API
- `tests/test_scoring.py` - Scoring engine tests (weighted calculation, multi-artifact boosting)
- `tests/test_ci_scanner.py` - CI pattern detection tests with mocked YAML content
- `tests/test_output.py` - JSON structure, schema conformance, and file writing tests
- `docs/scoring.md` - Scoring documentation: mappings, weights, formula, worked example, modification guide

### Notes

- Unit tests should be placed in the `tests/` directory at the project root.
- Use `pytest` for testing with `responses` library for mocking HTTP requests to the GitLab API.
- Follow ruff for linting and formatting.
- Python 3.10+ for modern type hint syntax (use `X | None` instead of `Optional[X]`).

## Tasks

### [x] 1.0 Project Scaffolding, CLI Entrypoint, and Config Parsing

Set up the Python project structure, CLI with click, YAML config parsing with validation, and comprehensive error handling for all user-facing failure modes. After this task, the tool is installable, invocable, and provides clear guidance when preconditions aren't met.

#### 1.0 Proof Artifact(s)

- CLI: `ai-fluency-collector --help` output demonstrates the tool is installed and shows `--config` and `--period` flags
- CLI: `ai-fluency-collector --config nonexistent.yaml` demonstrates file-not-found error with guidance to create from `config.example.yaml`
- CLI: `ai-fluency-collector --config team.yaml` with missing `GITLAB_TOKEN` demonstrates clear error with fix instructions
- CLI: `ai-fluency-collector --config team.yaml --period bad` demonstrates period format validation error
- CLI: `ai-fluency-collector --config team.yaml` with valid config and token demonstrates startup banner (team name, project count, period, output path)
- Test: `pytest tests/test_config.py tests/test_cli.py` passes, demonstrating config parsing, validation, and error message coverage

#### 1.0 Tasks

- [x] 1.1 Create `pyproject.toml` with package metadata, Python >=3.10 requirement, runtime dependencies (click, pyyaml, requests), dev dependencies section, console_scripts entrypoint (`ai-fluency-collector = "ai_fluency_collector.cli:main"`), and ruff configuration
- [x] 1.2 Create `requirements.txt` (click, pyyaml, requests) and `requirements-dev.txt` (pytest, responses, ruff)
- [x] 1.3 Create `.gitignore` with entries for: `*.yaml` (except `config.example.yaml`), `*-W*.json`, `__pycache__/`, `*.egg-info/`, `.venv/`, `dist/`, `.ruff_cache/`
- [x] 1.4 Create the `src/ai_fluency_collector/` package directory with `__init__.py` and `tests/__init__.py`
- [x] 1.5 Create `config.example.yaml` with commented example showing `team.name`, `team.code`, `team.members` (list), and `team.projects` (list of GitLab project paths)
- [x] 1.6 Implement `src/ai_fluency_collector/config.py`: a `load_config(path: str)` function that reads a YAML file, validates required fields (`team.name`, `team.code`, `team.projects` as non-empty list), and returns a typed dict or dataclass. Raise descriptive `ValueError` for each missing field and `FileNotFoundError` with guidance to create from `config.example.yaml`
- [x] 1.7 Implement `src/ai_fluency_collector/cli.py`: a click command `main()` with `--config` (required, path to YAML) and `--period` (optional, default to current ISO week as YYYY-WNN). Validate all preconditions in order: config file exists → config parses → period format valid → `GITLAB_TOKEN` env var set. Each failure prints a clear, actionable error message and exits non-zero. On success, print a startup banner: team name, project count, survey period, output file path
- [x] 1.8 Implement period validation: regex check for `YYYY-WNN` format (e.g., `2026-W12`). Default period calculation uses `datetime.date.today().isocalendar()` to produce current ISO week
- [x] 1.9 Write `tests/test_config.py`: test valid config parsing, missing file error message, invalid YAML error, missing `team.code`, missing `team.name`, missing `team.projects`, empty `team.projects` list
- [x] 1.10 Write `tests/test_cli.py`: test `--help` output contains both flags, test missing config file error, test missing `GITLAB_TOKEN` error, test invalid period format error, test startup banner with valid config (mock env var). Use click's `CliRunner` for invocation
- [x] 1.11 Verify `pip install -e .` succeeds and `ai-fluency-collector --help` works from the command line

### [x] 2.0 GitLab Repo Artifact Scanner with Scoring Mappings

Implement the GitLab API client and artifact scanner that checks each project for AI adoption files/directories. Define the declarative scoring mapping data structure (artifact-to-skill with weights) and the scoring engine that consumes scanner results. This task establishes the scoring architecture that will be reused by the CI scanner.

#### 2.0 Proof Artifact(s)

- CLI: `ai-fluency-collector --config team.yaml` run against real GitLab projects prints artifact detection results per project
- Test: `pytest tests/test_artifact_scanner.py tests/test_scoring.py` passes with mocked GitLab API responses, demonstrating all 8 artifact types detected and weighted scoring logic
- Test: Scoring test demonstrates that a project with multiple artifacts (CLAUDE.md + prompts/ + .mcp.json) scores higher than one with only CLAUDE.md

#### 2.0 Tasks

- [x] 2.1 Implement `src/ai_fluency_collector/gitlab_client.py`: a `GitLabClient` class that takes a token and base URL (default `https://gitlab.com`). Methods: `check_file_exists(project_path, file_path) -> bool` using Repository Files API HEAD request, `check_directory_exists(project_path, dir_path) -> bool` using Repository Tree API with `path` parameter, `get_file_content(project_path, file_path) -> str | None` for fetching file contents. Handle 404 → False, 401 → raise auth error, 403/network error → raise with project context
- [x] 2.2 Add token validation to CLI startup: after confirming `GITLAB_TOKEN` is set, make a test API call (e.g., `GET /api/v4/user`) to verify the token is valid. On 401, print: "GitLab authentication failed. Check that GITLAB_TOKEN is valid and has read_api scope."
- [x] 2.3 Implement `src/ai_fluency_collector/scanners/artifact_scanner.py`: an `ArtifactScanner` class that takes a `GitLabClient` and scans a project for all 8 artifact types. Return a dict of `{artifact_id: bool}` per project. Artifact checks: (A) `CLAUDE.md` file, (B) `.claude/settings.json` file, (C) `.mcp.json` OR `mcp.json` file, (D) `prompts/` directory, (E) `.cursorrules` file OR `.cursor/` directory, (F) `.github/copilot-instructions.md` file, (G) `AGENTS.md` file OR `.agents/` directory, (H) `.aider.conf.yml` OR `.aider.model.settings.yml` OR `.aiderignore` file
- [x] 2.4 Implement `src/ai_fluency_collector/scoring.py`: define the declarative `ARTIFACT_SKILL_MAPPINGS` data structure as a list of dicts, each with `artifact_id`, `skill_id`, and `weight` (float). Include all mappings from the spec (CLAUDE.md → cq-context, CLAUDE.md → im-autocomplete, etc.). Implement `calculate_scores(scan_results: list[dict], mappings: list[dict]) -> list[dict]` that computes per-skill scores using formula: `min(100, sum(found_weights) / sum(all_weights) * 100)` averaged across projects. Return list of `{skill_id, score, evidence}` dicts
- [x] 2.5 Generate the `evidence` string for each signal: describe which artifacts were found and in how many projects (e.g., "CLAUDE.md found in 3/4 projects, .claude/settings.json found in 1/4 projects")
- [x] 2.6 Wire artifact scanning into CLI: after startup banner, iterate over config projects, run artifact scanner on each, collect results, compute scores, and print per-project artifact detection summary to stdout. Fail the run with a clear error if any project is inaccessible (404, 403, or network error)
- [x] 2.7 Write `tests/test_artifact_scanner.py`: use `responses` library to mock GitLab API calls. Test: all 8 artifact types detected when present, artifacts correctly reported as absent when not found, OR-logic artifacts (e.g., `.mcp.json` OR `mcp.json`) detected with either variant, project access error (404/403) raises descriptive error
- [x] 2.8 Write `tests/test_scoring.py`: test single artifact → single skill scoring, multiple artifacts → same skill weighted scoring (verify score increases), scoring averaged across multiple projects, evidence string generation with correct counts, empty scan results produce no signals

### [ ] 3.0 GitLab CI Config Scanner

Implement the CI config scanner that fetches and parses `.gitlab-ci.yml` from each project, detects security/AI/deployment patterns including `include` template directives, and feeds results into the shared scoring engine.

#### 3.0 Proof Artifact(s)

- CLI: `ai-fluency-collector --config team.yaml` run against projects with CI configs prints detected CI patterns
- Test: `pytest tests/test_ci_scanner.py` passes with mocked `.gitlab-ci.yml` content, demonstrating all 7 CI pattern types including template includes
- Test: Projects without `.gitlab-ci.yml` produce score 0 with no error

#### 3.0 Tasks

- [ ] 3.1 Implement `src/ai_fluency_collector/scanners/ci_scanner.py`: a `CIScanner` class that takes a `GitLabClient`, fetches `.gitlab-ci.yml` via `get_file_content()`, parses with `yaml.safe_load`, and returns a dict of `{pattern_id: bool}` per project. If `.gitlab-ci.yml` doesn't exist, return all patterns as False (no error)
- [ ] 3.2 Implement CI pattern detection for all 7 types: (A) SAST/DAST — look for stage names or job names containing `sast`, `dast`, or `include` entries referencing `Security/SAST.gitlab-ci.yml` or `Security/DAST.gitlab-ci.yml`; (B) Secret detection — job names containing `secret` or includes referencing `Security/Secret-Detection.gitlab-ci.yml`; (C) AI code review — job names or scripts referencing `duo`, `ai-review`, or known third-party AI review tools; (D) AI test generation — job names or scripts referencing AI test generation tools; (E) Dependency scanning — includes referencing `Security/Dependency-Scanning.gitlab-ci.yml` or job names with `dependency`; (F) Code coverage — presence of `coverage` key in any job or `artifacts.reports.coverage_report`; (G) Deployment stages — stages named `deploy` or jobs with `environment` key combined with `rules` or `when` conditions
- [ ] 3.3 Implement `include` directive parsing: handle all GitLab include formats — string shorthand, `template:` key, `local:` key, and list of includes. Extract template paths and check against known GitLab CI template patterns
- [ ] 3.4 Add `CI_SKILL_MAPPINGS` to `scoring.py`: define the declarative mapping for CI patterns to skill IDs with weights. Pattern mappings: SAST/DAST → sdlc-security + tg-security-gates, secret detection → sdlc-security, AI code review → tg-code-review, AI test generation → sdlc-testing, dependency scanning → sdlc-security, code coverage → pm-measurement, deployment stages → sdlc-deployment + tg-supervised-auto
- [ ] 3.5 Wire CI scanning into CLI: after artifact scanning, run CI scanner on each project, compute CI scores using the shared scoring engine, and print per-project CI pattern detection summary to stdout
- [ ] 3.6 Write `tests/test_ci_scanner.py`: mock `.gitlab-ci.yml` content for each of the 7 pattern types. Test: each pattern detected individually, multiple patterns in one file, `include` template directives detected (string, `template:`, list formats), missing `.gitlab-ci.yml` returns all False with no error, invalid YAML gracefully handled

### [ ] 4.0 JSON Output, Scoring Documentation, and End-to-End Flow

Combine signals from both scanners into the final JSON output file matching the ai-fluency import schema. Write `docs/scoring.md` documenting every mapping, weight, formula, and modification instructions. Verify the full end-to-end flow produces an importable file.

#### 4.0 Proof Artifact(s)

- CLI: Full end-to-end run produces `{team_code}-{survey_period}.json` and prints summary (file path, source count, signal count, team code)
- Test: `pytest tests/test_output.py` passes, demonstrating JSON structure matches ai-fluency schema, empty sources are omitted, and file is written correctly
- Doc: `docs/scoring.md` exists and documents all artifact/CI mappings, weights, formula with worked example, and modification instructions
- Import: Output JSON file is successfully imported via the ai-fluency Import page without modification

#### 4.0 Tasks

- [ ] 4.1 Implement `src/ai_fluency_collector/output.py`: a `build_output(team_code, survey_period, artifact_signals, ci_signals) -> dict` function that merges signals into the schema: `{ team_code, survey_period, sources: [{ source_id, signals: [{ skill_id, score, evidence }] }] }`. Use `source_id` values `gitlab-repo-artifacts` and `gitlab-ci-config`. Omit any source that produced zero signals
- [ ] 4.2 Implement `write_output(data: dict, team_code: str, survey_period: str) -> str` that writes JSON to `{team_code}-{survey_period}.json` in the current working directory with 2-space indentation. Return the file path
- [ ] 4.3 Wire output into CLI: after both scanners complete, call `build_output` and `write_output`. Print a summary to stdout: output file path, number of sources included, total signal count, and team code
- [ ] 4.4 Write `tests/test_output.py`: test JSON structure matches expected schema, test `source_id` values are exact, test empty source is omitted, test file is written to correct path with correct content, test summary output format
- [ ] 4.5 Write `docs/scoring.md`: document (1) every artifact and CI pattern the collector detects with its pattern ID, (2) which `skill_id` each maps to, (3) the weight assigned to each mapping, (4) the scoring formula with a fully worked example showing real numbers, (5) step-by-step instructions for how to add new mappings or modify weights
- [ ] 4.6 End-to-end verification: run `ruff check .` and `ruff format --check .` to confirm no lint/format issues. Run `pytest` to confirm all tests pass. Run the CLI against a real or test GitLab project to verify the full flow produces valid JSON
