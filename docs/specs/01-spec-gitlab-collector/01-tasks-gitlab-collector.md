# 01-tasks-gitlab-collector

## Tasks

### [ ] 1.0 Project Scaffolding, CLI Entrypoint, and Config Parsing

Set up the Python project structure, CLI with click, YAML config parsing with validation, and comprehensive error handling for all user-facing failure modes. After this task, the tool is installable, invocable, and provides clear guidance when preconditions aren't met.

#### 1.0 Proof Artifact(s)

- CLI: `ai-fluency-collector --help` output demonstrates the tool is installed and shows `--config` and `--period` flags
- CLI: `ai-fluency-collector --config nonexistent.yaml` demonstrates file-not-found error with guidance to create from `config.example.yaml`
- CLI: `ai-fluency-collector --config team.yaml` with missing `GITLAB_TOKEN` demonstrates clear error with fix instructions
- CLI: `ai-fluency-collector --config team.yaml --period bad` demonstrates period format validation error
- CLI: `ai-fluency-collector --config team.yaml` with valid config and token demonstrates startup banner (team name, project count, period, output path)
- Test: `pytest tests/test_config.py tests/test_cli.py` passes, demonstrating config parsing, validation, and error message coverage

#### 1.0 Tasks

TBD

### [ ] 2.0 GitLab Repo Artifact Scanner with Scoring Mappings

Implement the GitLab API client and artifact scanner that checks each project for AI adoption files/directories. Define the declarative scoring mapping data structure (artifact-to-skill with weights) and the scoring engine that consumes scanner results. This task establishes the scoring architecture that will be reused by the CI scanner.

#### 2.0 Proof Artifact(s)

- CLI: `ai-fluency-collector --config team.yaml` run against real GitLab projects prints artifact detection results per project
- Test: `pytest tests/test_artifact_scanner.py tests/test_scoring.py` passes with mocked GitLab API responses, demonstrating all 8 artifact types detected and weighted scoring logic
- Test: Scoring test demonstrates that a project with multiple artifacts (CLAUDE.md + prompts/ + .mcp.json) scores higher than one with only CLAUDE.md

#### 2.0 Tasks

TBD

### [ ] 3.0 GitLab CI Config Scanner

Implement the CI config scanner that fetches and parses `.gitlab-ci.yml` from each project, detects security/AI/deployment patterns including `include` template directives, and feeds results into the shared scoring engine.

#### 3.0 Proof Artifact(s)

- CLI: `ai-fluency-collector --config team.yaml` run against projects with CI configs prints detected CI patterns
- Test: `pytest tests/test_ci_scanner.py` passes with mocked `.gitlab-ci.yml` content, demonstrating all 7 CI pattern types including template includes
- Test: Projects without `.gitlab-ci.yml` produce score 0 with no error

#### 3.0 Tasks

TBD

### [ ] 4.0 JSON Output, Scoring Documentation, and End-to-End Flow

Combine signals from both scanners into the final JSON output file matching the ai-fluency import schema. Write `docs/scoring.md` documenting every mapping, weight, formula, and modification instructions. Verify the full end-to-end flow produces an importable file.

#### 4.0 Proof Artifact(s)

- CLI: Full end-to-end run produces `{team_code}-{survey_period}.json` and prints summary (file path, source count, signal count, team code)
- Test: `pytest tests/test_output.py` passes, demonstrating JSON structure matches ai-fluency schema, empty sources are omitted, and file is written correctly
- Doc: `docs/scoring.md` exists and documents all artifact/CI mappings, weights, formula with worked example, and modification instructions
- Import: Output JSON file is successfully imported via the ai-fluency Import page without modification
