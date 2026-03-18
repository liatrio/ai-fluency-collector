# Task 4.0 Proof Artifacts — JSON Output, Scoring Documentation, and End-to-End Flow

## Test Results

### `pytest tests/test_output.py -v`
```
tests/test_output.py::test_build_output_both_sources PASSED
tests/test_output.py::test_build_output_artifact_only PASSED
tests/test_output.py::test_build_output_ci_only PASSED
tests/test_output.py::test_build_output_empty_sources PASSED
tests/test_output.py::test_source_id_values PASSED
tests/test_output.py::test_write_output_creates_file PASSED
tests/test_output.py::test_write_output_indentation PASSED
tests/test_output.py::test_schema_structure PASSED

8 passed
```

## Output Schema Verification

Test `test_schema_structure` confirms the output matches:
```json
{
  "team_code": "string",
  "survey_period": "string",
  "sources": [
    {
      "source_id": "gitlab-repo-artifacts | gitlab-ci-config",
      "signals": [
        {
          "skill_id": "string",
          "score": "integer",
          "evidence": "string"
        }
      ]
    }
  ]
}
```

- `source_id` values verified as exactly `gitlab-repo-artifacts` and `gitlab-ci-config`
- Empty sources are omitted (test_build_output_empty_sources, test_build_output_artifact_only, test_build_output_ci_only)
- File written with 2-space indentation

## Scoring Documentation

`docs/scoring.md` created with:
1. All 13 artifact-to-skill mappings with weights
2. All 9 CI pattern-to-skill mappings with weights
3. Scoring formula: `min(100, found_weights/total_weights × 100)` averaged across projects
4. Fully worked example with 4 projects and `im-autocomplete` skill
5. Step-by-step instructions for modifying weights, adding artifacts, and adding CI patterns

## Full Test Suite
```
54 passed in 0.21s
```

## Lint/Format
```
ruff check . → All checks passed!
ruff format --check . → All already formatted
```

## CLI Summary Output

The CLI now prints a summary after writing:
```
Summary
  File:    /path/to/team-code-2026-W12.json
  Sources: 2
  Signals: 7
  Team:    team-code
```
