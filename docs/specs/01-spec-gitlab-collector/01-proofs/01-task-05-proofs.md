# Task 5.0 Proof Artifacts — Config Update, Member Activity Scanner, and Integration

## Config Changes

- `team.members` is now required (non-empty list of GitLab usernames)
- `config.example.yaml` updated with GitLab usernames and descriptive comments

## Test Results

### `pytest tests/test_config.py -v` (updated)
```
test_load_valid_config PASSED
test_missing_file PASSED
test_invalid_yaml PASSED
test_missing_team_key PASSED
test_missing_team_code PASSED
test_missing_team_name PASSED
test_missing_team_members PASSED       (NEW)
test_empty_members_list PASSED         (NEW)
test_missing_team_projects PASSED
test_empty_projects_list PASSED

10 passed
```

### `pytest tests/test_member_scanner.py -v`
```
test_member_lookup_by_username PASSED
test_member_not_found_raises_error PASSED
test_discover_owned_projects PASSED
test_discover_pushed_projects PASSED
test_team_projects_excluded PASSED
test_deduplication_owned_and_pushed PASSED
test_detect_claude_coauthor PASSED
test_detect_copilot_coauthor PASSED
test_detect_cursor_coauthor PASSED
test_no_activity_returns_empty PASSED
test_scan_all_members PASSED

11 passed
```

### `pytest tests/test_output.py -v` (updated)
```
test_build_output_both_sources PASSED
test_build_output_artifact_only PASSED
test_build_output_ci_only PASSED
test_build_output_empty_sources PASSED
test_source_id_values_all_three PASSED       (NEW)
test_member_activity_source_included PASSED  (NEW)
test_member_activity_source_omitted_when_empty PASSED (NEW)
test_write_output_creates_file PASSED
test_write_output_indentation PASSED
test_schema_structure PASSED

10 passed
```

## Member Scanner Coverage

- User lookup by GitLab username (Users API)
- Project discovery: owned projects (User Projects API) + pushed events (Events API)
- Team project exclusion (avoids double-counting)
- Deduplication of projects found via multiple sources
- Co-author detection: Claude, GitHub Copilot, Cursor (case-insensitive)
- Graceful handling of members with no activity (score 0, no error)
- User not found raises descriptive error

## Full Test Suite
```
69 passed in 0.27s
```

## Lint/Format
```
ruff check . → All checks passed!
ruff format --check . → 18 files already formatted
```

## Scoring Documentation
`docs/scoring.md` updated with:
- Member activity mappings table (5 entries)
- Member scoring formula explanation
- Worked example with 3 members and Claude co-authored commits
- Instructions for adding new co-author patterns
