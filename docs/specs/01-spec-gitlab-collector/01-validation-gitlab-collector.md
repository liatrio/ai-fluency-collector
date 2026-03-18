# 01-validation-gitlab-collector

## 1) Executive Summary

- **Overall:** **PASS** (no gates tripped)
- **Implementation Ready:** **Yes** — all functional requirements verified across 5 units, 69 tests passing, lint clean, all proof artifacts present
- **Key metrics:** 100% Requirements Verified (41/41 FRs), 100% Proof Artifacts Working (5/5 tasks), 24 relevant files changed as expected + 2 justified additions (CLAUDE.md, .gitignore)

## 2) Coverage Matrix

### Functional Requirements — Unit 1: Project Scaffolding and Config Parsing

| Requirement | Status | Evidence |
|---|---|---|
| Installable via `pip install -e .` | Verified | `01-task-01-proofs.md`: CLI help output after install; commit `1e1050a` |
| CLI accepts `--config` and `--period` flags | Verified | `ai-fluency-collector --help` shows both flags |
| Default period = current ISO week (YYYY-WNN) | Verified | `test_default_period_uses_current_week` passes |
| Parses YAML config, validates required fields (name, code, members, projects) | Verified | `test_config.py`: 10 tests covering all validation paths |
| Reads `GITLAB_TOKEN` from env var | Verified | `test_missing_gitlab_token` passes |
| Clear error: config file not found | Verified | CLI: "Config file not found: nonexistent.yaml. Create one from config.example.yaml" |
| Clear error: invalid YAML syntax | Verified | `test_invalid_yaml` passes with "Failed to parse" |
| Clear error: missing required fields | Verified | `test_missing_team_code`, `test_missing_team_name`, `test_missing_team_members`, `test_missing_team_projects` pass |
| Clear error: GITLAB_TOKEN not set | Verified | CLI: "GITLAB_TOKEN environment variable is not set. Export a token with read_api scope." |
| Clear error: GITLAB_TOKEN invalid (401) | Verified | `test_invalid_gitlab_token` passes |
| Clear error: invalid period format | Verified | CLI: "Invalid period format: bad. Expected YYYY-WNN (e.g. 2026-W12)" |
| Validates all preconditions before API calls | Verified | `cli.py` validates in order: config → period → token → API check |
| Startup banner with team name, member count, project count, period, output path | Verified | `test_startup_banner` passes |
| `config.example.yaml` with comments | Verified | File exists with documented fields including GitLab usernames |

### Functional Requirements — Unit 2: GitLab Repo Artifact Scanner

| Requirement | Status | Evidence |
|---|---|---|
| Uses GitLab REST API v4 for file/directory checks | Verified | `gitlab_client.py` uses `/api/v4/projects/.../repository/files` and `/tree` |
| Detects all 8 artifact types (A–H) | Verified | `test_all_artifacts_detected` passes; `ARTIFACT_DEFINITIONS` covers all 8 |
| Fails entire run on inaccessible project (404/403) | Verified | `test_project_access_error_403` passes |
| Weighted skill scores (0–100) per skill | Verified | `test_scoring.py`: 8 tests including multi-artifact boost and averaging |
| Evidence string per signal | Verified | `test_evidence_string_with_counts` passes |

### Functional Requirements — Unit 3: GitLab CI Config Scanner

| Requirement | Status | Evidence |
|---|---|---|
| Fetches `.gitlab-ci.yml` via GitLab API | Verified | `ci_scanner.py` uses `client.get_file_content(project, ".gitlab-ci.yml")` |
| Detects all 7 CI patterns (A–G) | Verified | `test_ci_scanner.py`: 15 tests for each pattern type |
| Parses `include` directives (string, template, list) | Verified | `test_dast_via_include_string`, `test_sast_via_template_include`, `test_include_list_of_strings` |
| Skips gracefully when no `.gitlab-ci.yml` | Verified | `test_no_ci_file_returns_all_false` passes |
| Weighted skill scores per CI skill | Verified | `CI_SKILL_MAPPINGS` in `scoring.py` with 9 entries |
| Evidence string per CI signal | Verified | Shared evidence generation in `calculate_scores()` |

### Functional Requirements — Unit 4: JSON Output and End-to-End Flow

| Requirement | Status | Evidence |
|---|---|---|
| Merges signals from all sources into single output | Verified | `test_build_output_both_sources`, `test_source_id_values_all_three` pass |
| Output JSON matches ai-fluency import schema | Verified | `test_schema_structure` validates keys |
| `source_id` values exactly `gitlab-repo-artifacts`, `gitlab-ci-config`, `gitlab-member-activity` | Verified | `test_source_id_values_all_three` passes |
| Omit empty source blocks | Verified | `test_build_output_empty_sources`, `test_member_activity_source_omitted_when_empty` pass |
| Writes to `{team_code}-{survey_period}.json` | Verified | `test_write_output_creates_file` passes |
| Prints summary (file path, sources, signals, team code) | Verified | `cli.py:183-188` prints Summary block |
| `docs/scoring.md` documents all mappings, weights, formula, modification guide | Verified | File exists with artifact, CI, and member activity sections |

### Functional Requirements — Unit 5: GitLab Member Activity Scanner

| Requirement | Status | Evidence |
|---|---|---|
| Config `team.members` contains GitLab usernames | Verified | `config.py` requires non-empty members list; `test_load_valid_config` uses usernames |
| Validate member usernames exist on GitLab | Verified | `test_member_not_found_raises_error` raises `GitLabUserNotFoundError` |
| Discover owned projects via Users Projects API | Verified | `test_discover_owned_projects` passes with mocked API |
| Discover pushed projects via Events API | Verified | `test_discover_pushed_projects` passes with mocked API |
| Deduplicate and exclude `team.projects` | Verified | `test_team_projects_excluded`, `test_deduplication_owned_and_pushed` pass |
| Detect Co-Authored-By: Claude (case-insensitive) | Verified | `test_detect_claude_coauthor` passes |
| Detect Co-Authored-By: GitHub Copilot (case-insensitive) | Verified | `test_detect_copilot_coauthor` passes |
| Detect Co-Authored-By: Cursor (case-insensitive) | Verified | `test_detect_cursor_coauthor` passes |
| Members with no activity return empty (no error) | Verified | `test_no_activity_returns_empty` passes |
| Not run full artifact/CI scan on discovered repos | Verified | `member_scanner.py` only calls `get_project_commits`, not file/tree APIs |
| Weighted skill scores based on member co-author activity | Verified | `MEMBER_SKILL_MAPPINGS` + `calculate_member_scores` in `scoring.py` |
| Evidence string per member signal | Verified | Evidence format: "Co-authored commits with {tool} by X/Y members (N commits)" |

### Repository Standards

| Standard Area | Status | Evidence |
|---|---|---|
| Project structure: `src/ai_fluency_collector/` | Verified | Package with `cli.py`, `config.py`, `scanners/`, `scoring.py`, `output.py` |
| Package manager: pip + requirements.txt | Verified | `requirements.txt` and `requirements-dev.txt` present |
| CLI framework: click | Verified | `cli.py` uses `@click.command()`, `@click.option()` |
| Testing: pytest with mocked HTTP | Verified | `responses` library used; `pytest` configured in `pyproject.toml` |
| Python version: 3.10+ | Verified | `pyproject.toml`: `requires-python = ">=3.10"` |
| Code style: ruff | Verified | `ruff check .` and `ruff format --check .` pass clean |
| Entry point: console_scripts | Verified | `pyproject.toml`: `ai-fluency-collector = "ai_fluency_collector.cli:main"` |

### Proof Artifacts

| Task | Proof Artifact | Status | Verification |
|---|---|---|---|
| 1.0 | CLI: `--help` output | Verified | Shows --config and --period flags |
| 1.0 | CLI: missing config error | Verified | "Config file not found...config.example.yaml" |
| 1.0 | CLI: missing GITLAB_TOKEN error | Verified | "GITLAB_TOKEN environment variable is not set" |
| 1.0 | CLI: invalid period error | Verified | "Invalid period format...Expected YYYY-WNN" |
| 1.0 | CLI: startup banner | Verified | Shows team name, member count, project count, period, output path |
| 1.0 | Test: `test_config.py` + `test_cli.py` | Verified | 19 tests pass |
| 2.0 | Test: `test_artifact_scanner.py` + `test_scoring.py` | Verified | 14 tests pass |
| 2.0 | Test: multi-artifact scores higher | Verified | `test_full_mappings_multi_project` confirms |
| 3.0 | Test: `test_ci_scanner.py` all 7 patterns | Verified | 15 tests pass |
| 3.0 | Test: missing CI YAML → score 0 | Verified | `test_no_ci_file_returns_all_false` passes |
| 4.0 | Test: `test_output.py` schema + file write | Verified | 10 tests pass |
| 4.0 | Doc: `docs/scoring.md` | Verified | File exists with all 3 source mappings |
| 5.0 | Test: `test_config.py` members validation | Verified | `test_missing_team_members`, `test_empty_members_list` pass |
| 5.0 | Test: `test_member_scanner.py` | Verified | 11 tests pass covering discovery + co-author detection |
| 5.0 | Test: `test_output.py` third source | Verified | `test_source_id_values_all_three`, `test_member_activity_source_included` pass |
| 5.0 | Doc: `docs/scoring.md` member mappings | Verified | Member activity section with mappings, worked example, modification guide |

## 3) Validation Issues

No issues found. All gates pass:

- **GATE A:** No CRITICAL or HIGH issues → **PASS**
- **GATE B:** Coverage Matrix has no Unknown entries → **PASS**
- **GATE C:** All Proof Artifacts accessible and functional → **PASS**
- **GATE D:** All changed files in Relevant Files list or justified (CLAUDE.md, .gitignore are standard project files) → **PASS**
- **GATE E:** Implementation follows repository standards from spec → **PASS**
- **GATE F:** No credentials in proof artifacts → **PASS**

## 4) Evidence Appendix

### Git Commits
| Commit | Task | Files Changed |
|---|---|---|
| `1e1050a` | T1.0 Scaffolding | 15 files: pyproject.toml, requirements, .gitignore, config.example.yaml, cli.py, config.py, tests |
| `605886e` | T2.0 Artifact Scanner | 9 files: gitlab_client.py, artifact_scanner.py, scoring.py, cli.py, tests |
| `7644b3c` | T3.0 CI Scanner | 7 files: ci_scanner.py, scoring.py, cli.py, tests |
| `ea2cd47` | T4.0 JSON Output | 7 files: output.py, cli.py, scoring.py, docs/scoring.md, tests |
| `a04d206` | Spec update for Unit 5 | 2 files: spec, tasks |
| `bf07050` | T5.0 Member Activity Scanner | 15 files: member_scanner.py, gitlab_client.py, scoring.py, cli.py, config.py, output.py, tests, docs |

### Test Suite
```
69 passed in 0.24s
```
- test_config.py: 10 tests
- test_cli.py: 9 tests
- test_artifact_scanner.py: 6 tests
- test_scoring.py: 8 tests
- test_ci_scanner.py: 15 tests
- test_member_scanner.py: 11 tests
- test_output.py: 10 tests

### Quality Gates
```
ruff check . → All checks passed!
ruff format --check . → 18 files already formatted
```

### CLI Verification
```
$ ai-fluency-collector --help → exit 0, shows --config and --period
$ ai-fluency-collector --config nonexistent.yaml → exit 1, "Config file not found"
$ ai-fluency-collector --config team.yaml (no GITLAB_TOKEN) → exit 1, "GITLAB_TOKEN...not set"
$ ai-fluency-collector --config team.yaml --period bad → exit 2, "Invalid period format"
```

### Security Scan
Grep for credentials in proof artifacts: **No matches found**

---

**Validation Completed:** 2026-03-18
**Validation Performed By:** Claude Opus 4.6 (1M context)
