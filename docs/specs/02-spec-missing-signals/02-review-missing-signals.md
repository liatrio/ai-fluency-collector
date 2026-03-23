# Code Review Report

**Reviewed**: 2026-03-23T00:00:00Z
**Branch**: feat/issue-15-missing-signals
**Base**: main
**Commits**: 2 commits, 2 source files changed
**Overall**: APPROVED

## Summary

- **Blocking Issues**: 0
- **Advisory Notes**: 1
- **Files Reviewed**: 2 / 2 non-test changed files
- **FIX Tasks Created**: none

## Blocking Issues

None.

## Advisory Notes

### [NOTE-1] Category D: Bare `dict` type annotation

- **File**: `src/ai_fluency_collector/gitlab_scoring.py:426, 558`
- **Description**: `ctx: dict = {...}` uses the unparameterized `dict` type. Since this codebase uses Python 3.10+ syntax throughout, `dict[str, Any]` or `dict[str, object]` would be more precise. Not a blocking issue since the variable is purely local and ruff does not flag it.
- **Suggestion**: Could be tightened to `ctx: dict[str, object]` in a follow-up, but not worth a separate commit.

## Files Reviewed

| File | Status | Issues |
|---|---|---|
| `src/ai_fluency_collector/gitlab_scoring.py` | Modified | 0 blocking, 1 advisory |
| `docs/scoring.md` | Modified | Clean |
| `tests/test_scoring_context.py` | Modified | (not reviewed — test code) |
| `docs/specs/02-spec-missing-signals/T01-proofs/` | New | (not reviewed — proof artifacts) |
| `docs/specs/02-spec-missing-signals/T02-proofs/` | New | (not reviewed — proof artifacts) |

## Checklist

- [x] No hardcoded credentials or secrets
- [x] Error handling at system boundaries (defaultdict.get() used safely)
- [x] Input validation not applicable (values come from static mappings only)
- [x] Changes match spec requirements (missing_signals on artifact, CI, member signals; omitted from rate/review)
- [x] Follows repository patterns and conventions (same dict.fromkeys pattern, ctx construction matches existing style)
- [x] No obvious performance regressions (linear scan of skill_maps, same O(n) as existing scoring loop)
- [x] Non-goals respected — GitHub artifacts, pipeline, coverage, review signals untouched
- [x] docs/scoring.md updated in same commit as code change (per CLAUDE.md constraint)
- [x] Additive only — no existing fields modified

## Correctness Notes

- `dict.fromkeys()` correctly deduplicates when the same `artifact_id` appears in multiple mapping entries for a skill.
- `missing_signals` is computed after the `score <= 0: continue` guard, so it only appears on emitted signals.
- `pattern_member_counts.get(aid, 0)` is safe even though `pattern_member_counts` is a `defaultdict(int)` — redundant but harmless.
- `artifact_counts[aid] == 0` in `calculate_scores()` is safe — `artifact_counts` is a `defaultdict(int)` so absent keys return 0 naturally.
