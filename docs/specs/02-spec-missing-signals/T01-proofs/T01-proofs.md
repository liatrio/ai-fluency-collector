# T01 Proof Summary

**Task:** Add missing_signals to calculate_scores() for GitLab artifacts and CI patterns

## Proof Artifacts

| File | Type | Status | Description |
|---|---|---|---|
| T01-01-test.txt | test | PASS | scoring_context tests (18 passed, 3 new) |
| T01-02-test-full-suite.txt | test | PASS | Full test suite (228 passed, 0 failures) |

## Evidence

- `missing_signals` added to `calculate_scores()` in `gitlab_scoring.py` — computed from `artifact_counts` dict after the per-project loop using `dict.fromkeys()` for deduplication
- Field is only included when at least one contributing artifact ID was absent from all projects
- 3 new tests added to `tests/test_scoring_context.py`:
  - `test_artifact_missing_signals_partial` — verifies absent artifact IDs appear in list
  - `test_artifact_missing_signals_omitted_when_all_found` — verifies field omitted when all present
  - `test_ci_missing_signals` — verifies CI pattern variant works correctly
- `docs/scoring.md` updated with `missing_signals` field documentation
- All 228 tests pass, 0 regressions
