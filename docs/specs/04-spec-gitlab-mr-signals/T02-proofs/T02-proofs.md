# T02 Proof Summary

**Task:** Implement coding time signal for AI-attributed MRs
**Status:** COMPLETED
**Timestamp:** 2026-03-23

## Artifacts

| File | Type | Status |
|---|---|---|
| T02-01-test.txt | test | PASS |
| T02-02-cli.txt | cli | PASS |

## Summary

- 21 new tests added to `tests/test_mr_scanner.py` (46 total, all passing; 285 total suite)
- `_coding_time_hours()` added to `gitlab_mr_scanner.py` — computes hours from earliest commit to MR open, reusing commits already fetched, clamped to ≥ 0
- `MRMetrics` extended with `coding_time_median` and `coding_time_mr_count` fields
- `MRScanner.scan()` now computes both pr_size and coding_time in a single MR pass
- `_coding_time_score` rubric + `MR_CODING_TIME_SKILL_MAPPINGS` added to `gitlab_scoring.py`
- `calculate_mr_signals()` replaces `calculate_mr_size_scores()` in CLI — emits signals for im-supervised-agent (size), im-inline-editing (time), and im-supervised-agent (time)
- `calculate_mr_size_scores()` kept as a backward-compatible alias
