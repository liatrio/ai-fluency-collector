# T02 Proof Summary

**Task:** Add missing_signals to calculate_member_scores() for member activity

## Proof Artifacts

| File | Type | Status | Description |
|---|---|---|---|
| T02-01-test.txt | test | PASS | scoring_context tests (20 passed, 2 new) |
| T02-02-test-full-suite.txt | test | PASS | Full test suite (230 passed, 0 failures) |

## Evidence

- `missing_signals` added to `calculate_member_scores()` in `gitlab_scoring.py` — computed from `pattern_member_counts` dict using `dict.fromkeys()` for deduplication
- Field included only when at least one co-author pattern ID had zero member matches
- 2 new tests added to `tests/test_scoring_context.py`:
  - `test_member_missing_signals_partial` — verifies absent co-author pattern IDs appear in list
  - `test_member_missing_signals_omitted_when_all_found` — verifies field omitted when all patterns found
- All 230 tests pass, 0 regressions
