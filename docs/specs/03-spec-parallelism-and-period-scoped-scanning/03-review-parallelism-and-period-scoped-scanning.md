# Code Review Report

**Reviewed**: 2026-03-23T00:00:00Z
**Branch**: perf/issue-21-parallelism-and-period-scoped-scanning
**Base**: main
**Commits**: 3 commits, 5 source files changed
**Overall**: CHANGES REQUESTED

## Summary

- **Blocking Issues**: 1 (A: 1 correctness, B: 0 security, C: 0 spec compliance)
- **Advisory Notes**: 3
- **Files Reviewed**: 5 / 5 non-test changed files
- **FIX Tasks Created**: FIX-REVIEW #7

## Blocking Issues

### [ISSUE-1] Category A: requests.Session shared across threads is not thread-safe

- **File**: `src/ai_fluency_collector/gitlab_client.py:77-78`
- **Severity**: Blocking
- **Description**: All parallel workers share a single `GitLabClient` instance backed by one `requests.Session`. The `requests` library officially documents `Session` objects as not thread-safe. Concurrent GETs from `ThreadPoolExecutor` workers can race on the session's internal state (cookies, header prep, connection pool state). The spec itself explicitly identified this as a risk requiring verification before merging.
- **Fix**: Replace `self.session = requests.Session()` with a `threading.local()`-backed property that creates one session per thread. No callers need changing — all `self.session.get(...)` references work unchanged.
- **Task**: FIX-REVIEW #7

## Advisory Notes

### [NOTE-1] Category D: "Scanning pipelines for X..." message printed after parallel work completes

- **File**: `src/ai_fluency_collector/cli.py` (pipeline scan loop, post-executor)
- **Description**: The progress message `click.echo(f"  Scanning pipelines for {project}...")` is now printed after the parallel scan has already completed. Users see output that implies work is starting when it's already done.
- **Suggestion**: Either remove per-project messages from parallel loops (print a single "Scanning N projects in parallel..." before the executor), or accept as low-priority UX debt.

### [NOTE-2] Category D: `_scan_coverage_pair` closure captures loop variable by reference

- **File**: `src/ai_fluency_collector/cli.py` (coverage scan, week loop)
- **Description**: A closure defined inside the week loop that captures `week`, `prior_week` by reference is fragile — if the loop runs multiple iterations rapidly, closures could capture stale values. Currently safe since weeks are processed sequentially, but the pattern is error-prone.
- **Suggestion**: Pass `week` and `prior_week` as default arguments to the closure, or extract to a module-level helper.

### [NOTE-3] Category D: Verbose branch-detail output lost in artifact scan

- **File**: `src/ai_fluency_collector/cli.py` (artifact scan, `--verbose` block)
- **Description**: The `--verbose` mode previously showed which branches were active per project. This diagnostic output was removed as part of the parallel refactor. Useful for debugging branch-weight issues.
- **Suggestion**: Consider logging active branch details post-scan using the result dict, rather than pre-fetching separately.

## Files Reviewed

| File | Status | Issues |
|---|---|---|
| `src/ai_fluency_collector/gitlab_client.py` | Modified | 1 blocking |
| `src/ai_fluency_collector/cli.py` | Modified | 3 advisory |
| `src/ai_fluency_collector/scanners/gitlab_artifact_scanner.py` | Modified | Clean |
| `src/ai_fluency_collector/scanners/gitlab_ci_scanner.py` | Modified | Clean |
| `src/ai_fluency_collector/scanners/gitlab_member_scanner.py` | Modified | Clean |
| `tests/` | Modified | (not reviewed — test code) |

## Checklist

- [x] No hardcoded credentials or secrets
- [x] Error handling at system boundaries (`_GITLAB_ERRORS` / `ClickException` preserved)
- [x] Input validation not applicable (internal API calls only)
- [x] Changes match spec requirements (period-scoped dates, parallelism, get_jobs cap)
- [x] Follows repository patterns and conventions (stdlib only, ruff clean, Python 3.10+)
- [ ] Thread safety verified — **BLOCKED** on FIX #7
- [x] No performance regressions for sequential path (defaults preserved)
