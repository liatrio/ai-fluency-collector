# T01 Proof Summary

Task: Period-scoped dates for member scanner and active-branch cutoff
Status: COMPLETED

## Changes Implemented

1. **`gitlab_member_scanner.py`**: Replaced `lookback_days: int = 90` with `since_date: str` parameter
   on `MemberScanner.__init__()`. Removed `date.today() - timedelta(days=lookback_days)` computation.
   `since_date` is now stored and passed directly to `get_project_commits()`.

2. **`gitlab_artifact_scanner.py`**: Added `reference_date: date | None = None` parameter to
   `_get_active_branches()`. Computes cutoff as `reference_date - timedelta(days=active_days)` using
   the provided date (or `date.today()` if None). Added `reference_date` to `ArtifactScanner.__init__()`
   and threads it through `scan_project()`.

3. **`gitlab_ci_scanner.py`**: Added `reference_date: date | None = None` parameter to
   `CIScanner.__init__()` and threads it through `scan_project()` to `_get_active_branches()`.

4. **`cli.py`**: Added `_period_start_date(periods)` and `_period_end_date(periods)` helpers.
   Computes `reference_date` (Sunday of latest period week) and `since_date` (Monday of earliest
   period week, as ISO string). Passes them to `ArtifactScanner`, `CIScanner`, and `MemberScanner`.

5. **`tests/test_member_scanner.py`**: Updated all existing `MemberScanner` constructions to pass
   `since_date="2026-01-01"`. Added new test `test_since_date_passed_directly_to_get_project_commits`
   using MagicMock to verify `since_date` is passed verbatim to `get_project_commits()`.

6. **`tests/test_artifact_scanner.py`**: Added `_get_active_branches` to imports. Added new test
   `test_get_active_branches_uses_reference_date_not_today` that verifies a fixed `reference_date`
   determines the 90-day cutoff, not `date.today()`.

## Proof Artifacts

| File | Type | Status |
|------|------|--------|
| T01-01-test.txt | test (22 scanner tests) | PASS |
| T01-02-test.txt | test (232 full suite) | PASS |
| T01-03-test.txt | test (ruff lint) | PASS |
