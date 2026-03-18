# Task 1.0 Proof Artifacts — Project Scaffolding, CLI Entrypoint, and Config Parsing

## CLI Output

### `ai-fluency-collector --help`
```
Usage: ai-fluency-collector [OPTIONS]

  Scan GitLab repositories for AI adoption signals.

Options:
  --config TEXT  Path to team configuration YAML file.  [required]
  --period TEXT  Survey period in YYYY-WNN format (defaults to current ISO
                 week).
  --help         Show this message and exit.
```

### `ai-fluency-collector --config nonexistent.yaml`
```
Error: Config file not found: nonexistent.yaml. Create one from config.example.yaml
```

### `ai-fluency-collector --config team.yaml` (missing GITLAB_TOKEN)
```
Error: GITLAB_TOKEN environment variable is not set. Export a token with read_api scope.
```

### `ai-fluency-collector --config team.yaml --period bad`
```
Error: Invalid value: Invalid period format: bad. Expected YYYY-WNN (e.g. 2026-W12)
```

### `ai-fluency-collector --config config.example.yaml --period 2026-W12` (valid setup)
```
AI Fluency Collector
  Team:     My Team
  Projects: 3
  Period:   2026-W12
  Output:   my-team-2026-W12.json
```

## Test Results

### `pytest tests/test_config.py tests/test_cli.py -v`
```
tests/test_config.py::test_load_valid_config PASSED
tests/test_config.py::test_missing_file PASSED
tests/test_config.py::test_invalid_yaml PASSED
tests/test_config.py::test_missing_team_key PASSED
tests/test_config.py::test_missing_team_code PASSED
tests/test_config.py::test_missing_team_name PASSED
tests/test_config.py::test_missing_team_projects PASSED
tests/test_config.py::test_empty_projects_list PASSED
tests/test_config.py::test_members_defaults_to_empty PASSED
tests/test_cli.py::test_help_output PASSED
tests/test_cli.py::test_missing_config_file PASSED
tests/test_cli.py::test_missing_gitlab_token PASSED
tests/test_cli.py::test_invalid_period_format PASSED
tests/test_cli.py::test_invalid_period_week_zero PASSED
tests/test_cli.py::test_startup_banner PASSED
tests/test_cli.py::test_default_period_uses_current_week PASSED

16 passed in 0.06s
```

## Verification

- All 16 tests pass covering config parsing, validation, and CLI error handling
- `ruff check .` passes with no errors
- `ruff format --check .` passes with no reformatting needed
- CLI is installable via `pip install -e .` and invocable as `ai-fluency-collector`
