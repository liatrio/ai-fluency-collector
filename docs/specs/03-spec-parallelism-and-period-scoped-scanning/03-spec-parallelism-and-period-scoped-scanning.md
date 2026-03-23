# 03-spec-parallelism-and-period-scoped-scanning

## Introduction/Overview

A 2-week GitLab scan currently takes ~58 minutes because all project and member scans run sequentially and the member scanner fetches 90 days of commit history regardless of the actual survey period. This spec adds `ThreadPoolExecutor`-based parallelism to project and member scanning, fixes the member scanner to use the period start date as the commit history cutoff, fixes artifact/CI scanners to use the period end date as the active-branch reference, and caps `get_jobs()` pagination to bound coverage fetch time.

## Goals

1. Reduce typical 2-week scan time significantly by parallelising per-project and per-member API calls.
2. Eliminate the 90-day over-fetch in the member scanner — only fetch commits since the period start date.
3. Fix artifact and CI scanners to evaluate branch activity relative to the period end date, not today.
4. Cap `get_jobs()` to a maximum of 5 pages (500 jobs) to bound coverage scan time on large projects.
5. Maintain all existing tests and preserve the same output format and error-handling behaviour.

## User Stories

- As a team lead running a 2-week scan, I want it to complete in under 15 minutes so that I can iterate quickly during a fluency review session.
- As a user scanning a historical period (e.g. `2026-W01`), I want the active-branch cutoff and commit lookback to reflect the survey period, not today, so that I get accurate results for that time window.

## Demoable Units of Work

### Unit 1: Period-scoped dates for member scanner and active-branch cutoff

**Purpose:** Replace today-relative date references with period-derived dates, fixing correctness for historical scans and reducing over-fetching in the member scanner.

**Functional Requirements:**

- The system shall accept a `since_date: str` parameter on `MemberScanner.__init__()` (replacing the `lookback_days: int` parameter), and use it directly as the commit history cutoff passed to `get_project_commits()`.
- The system shall pass the Monday of the earliest scan week (period start) as `since_date` when constructing `MemberScanner` in `cli.py`.
- The system shall accept a `reference_date: date` parameter on `_get_active_branches()` (replacing the internal `date.today()` call), and compute the active-branch cutoff as `reference_date - timedelta(days=active_days)`.
- The system shall pass the Sunday of the latest scan week (period end) as `reference_date` when calling `_get_active_branches()` via `ArtifactScanner` and `CIScanner` in `cli.py`.
- The system shall expose `reference_date` from `ArtifactScanner.scan_project()` and `CIScanner.scan_project()` through to `_get_active_branches()` so `cli.py` can supply it.

**Proof Artifacts:**

- Test: `tests/test_member_scanner.py` — new test verifying `MemberScanner` passes `since_date` to `get_project_commits()`, not a today-relative value.
- Test: `tests/test_artifact_scanner.py` — new test verifying `_get_active_branches()` uses `reference_date` instead of `date.today()`.

---

### Unit 2: Parallelise per-project scanning with ThreadPoolExecutor

**Purpose:** Run artifact, CI, pipeline, and coverage scans for all projects concurrently instead of sequentially.

**Functional Requirements:**

- The system shall use `concurrent.futures.ThreadPoolExecutor(max_workers=8)` to parallelise the artifact scan loop over `team.projects` in `cli.py`.
- The system shall use `ThreadPoolExecutor(max_workers=8)` to parallelise the CI scan loop over `team.projects` in `cli.py`.
- The system shall use `ThreadPoolExecutor(max_workers=8)` to parallelise the per-week pipeline scan loop over `team.projects` in `cli.py`.
- The system shall use `ThreadPoolExecutor(max_workers=8)` to parallelise the per-week coverage scan loop over `team.projects` in `cli.py`.
- The system shall preserve the original result ordering (results collected in the same order as `team.projects`) using `executor.map()` or equivalent.
- The system shall fail fast: if any project scan raises a `_GITLAB_ERRORS` exception, the exception shall propagate and terminate the scan with a `ClickException`, matching current behaviour.
- The system shall not use parallelism for the per-week review scanner (small sequential operation over MRs, not project-scoped).

**Proof Artifacts:**

- Test: `tests/test_cli.py` — new test verifying that `ThreadPoolExecutor` is invoked (or that all projects are scanned) when multiple projects are configured.
- CLI: `afc scan --config team.yaml --from 2026-03-01 --to 2026-03-14` completes without error and produces output files, demonstrating parallelism does not break the scan.

---

### Unit 3: Parallelise member scanning and cap get_jobs() pagination

**Purpose:** Run per-member scans concurrently and bound the `get_jobs()` fetch to at most 5 pages.

**Functional Requirements:**

- The system shall use `ThreadPoolExecutor(max_workers=8)` inside `MemberScanner.scan_all_members()` to scan all members concurrently.
- The system shall preserve result ordering (one `MemberResult` per username, in the same order as the input list).
- The system shall fail fast on `GitLabUserNotFoundError` or other unrecoverable errors, matching current behaviour.
- The system shall add a `max_pages: int = 5` parameter to `GitLabClient.get_jobs()` and stop pagination after `max_pages` pages (returning the jobs collected so far).

**Proof Artifacts:**

- Test: `tests/test_member_scanner.py` — new test verifying that `scan_all_members()` calls `scan_member()` for each username (parallelism is an implementation detail; correctness is verified by output).
- Test: `tests/test_gitlab_client.py` or `tests/test_ci_scanner.py` — new test verifying `get_jobs()` stops after `max_pages` pages and returns partial results.

---

## Non-Goals (Out of Scope)

- Parallelising the GitHub scanner (`github-scan` command) — not part of this issue.
- Adding a `--workers` CLI flag to configure thread count — fixed default of 8 is sufficient.
- Async/await refactoring — `ThreadPoolExecutor` with the existing synchronous `requests` client is the intended approach.
- Capping pagination on endpoints other than `get_jobs()` — only `get_jobs()` is identified as over-fetching.
- Per-week parallelism across multiple weeks — weeks still run sequentially; only within-week project scanning is parallelised.

## Design Considerations

No CLI interface changes. All parallelism is internal to the scanner and CLI implementation layers. Output format is unchanged.

## Repository Standards

- `ThreadPoolExecutor` imported from `concurrent.futures` (stdlib — no new dependencies).
- All new parameters use Python 3.10+ type hint syntax.
- Existing error handling patterns (`_GITLAB_ERRORS` tuple, `click.ClickException`) must be preserved.
- `docs/scoring.md` not affected — no scoring changes.
- New tests follow the existing mock-heavy pattern in `tests/test_member_scanner.py` and `tests/test_artifact_scanner.py`.

## Technical Considerations

- **Thread safety**: `GitLabClient` uses `requests.Session` internally. Sessions are not thread-safe. Each parallel worker should use the same client instance only if the session is not shared between threads, OR the client should be instantiated per-thread. Review `GitLabClient` session usage before parallelising — if `requests.Session` is per-instance and workers share one client, this needs a lock or per-thread client. The simplest safe approach is to call `executor.map(scanner.scan_project, team.projects)` where `scan_project` does not mutate shared state.
- **Period date helpers**: A new helper `_period_to_monday(period: str) -> date` (period start) and reuse of the existing `_prior_iso_week` / date arithmetic for period end (Sunday = Monday + 6 days) should be added to `cli.py`.
- **`MemberScanner` API change**: The `lookback_days` parameter is removed. Any existing tests that construct `MemberScanner(client, projects, lookback_days=N)` must be updated to pass `since_date` directly.
- **`_get_active_branches` signature change**: Currently a module-level function in `gitlab_artifact_scanner.py`. Adding `reference_date` as a parameter with a default of `date.today()` maintains backward compatibility for tests that call it without the argument.

## Security Considerations

No new network endpoints, credentials, or user-controlled inputs introduced. Thread count (8) is a hardcoded internal constant with no attack surface.

## Success Metrics

- A 2-week GitLab scan with 5 projects and 10 members completes in under 15 minutes (target from issue).
- All 230 existing tests continue to pass.
- `get_jobs()` test confirms pagination stops at page 5 even when more pages are available.

## Open Questions

No open questions at this time.
