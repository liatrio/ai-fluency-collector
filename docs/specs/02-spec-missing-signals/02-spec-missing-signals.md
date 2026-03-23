# 02-spec-missing-signals

## Introduction/Overview

This feature adds a `missing_signals` field to the `scoring_context` object emitted by artifact-based scoring functions. When one or more artifact or co-author pattern IDs that map to a skill are absent from all scanned projects or members, those IDs are listed so the UI can surface actionable suggestions like "Adding `.cursorrules` could raise this score toward 100."

## Goals

1. Surface which artifact and co-author signal IDs map to a skill but were not detected, per signal entry.
2. Omit the field entirely when all contributing signals were found (no noise when the team is fully covered).
3. Cover GitLab artifact signals (`gitlab-repo-artifacts`), CI pattern signals (`gitlab-ci-config`), and member activity signals (`gitlab-member-activity`).
4. Make no changes to rate-based, delta-based, pipeline, coverage, or review signals where the concept does not apply.
5. Remain purely additive — no existing fields modified, no schema breakage.

## User Stories

- As a team lead reviewing an AI fluency score, I want to know which specific tools or patterns my team is missing so that I can take targeted action to raise the score.
- As a UI developer consuming the JSON output, I want a structured list of missing signal IDs so that I can render "You could improve this score by adding X" suggestions without parsing prose.

## Demoable Units of Work

### Unit 1: missing_signals in calculate_scores() (GitLab artifacts and CI patterns)

**Purpose:** Extend the shared `calculate_scores()` function to include `missing_signals` in the `scoring_context` of each emitted signal, listing artifact IDs that map to the skill but were absent from all scanned projects.

**Functional Requirements:**

- The system shall compute `missing_signals` as the list of artifact IDs (from the skill's mapping entries) where `artifact_counts[artifact_id] == 0` across all scanned projects.
- The system shall include `missing_signals` in `scoring_context` only when at least one contributing artifact ID was not found (i.e., the list is non-empty).
- The system shall omit `missing_signals` from `scoring_context` when all contributing artifact IDs were present in at least one project.
- The system shall not modify the `breakdown`, `max_from_this_signal`, `score`, or `evidence` fields.
- The system shall apply this behaviour to both `ARTIFACT_SKILL_MAPPINGS` and `CI_SKILL_MAPPINGS` callers, as both use `calculate_scores()`.

**Proof Artifacts:**

- Test: `tests/test_scoring_context.py` — new test `test_artifact_missing_signals_partial` passes, asserting that when only one of two contributing artifacts is found, `missing_signals` lists the absent artifact ID.
- Test: `tests/test_scoring_context.py` — new test `test_artifact_missing_signals_omitted_when_all_found` passes, asserting that `missing_signals` is absent from `scoring_context` when all contributing artifact IDs are present.
- Test: `tests/test_scoring_context.py` — new test `test_ci_missing_signals` passes for a CI skill with a missing CI pattern ID.

---

### Unit 2: missing_signals in calculate_member_scores()

**Purpose:** Extend `calculate_member_scores()` to list co-author pattern IDs that map to a skill but were triggered by zero members.

**Functional Requirements:**

- The system shall compute `missing_signals` as the list of co-author pattern IDs (from the skill's mapping entries) where `pattern_member_counts[artifact_id] == 0`.
- The system shall include `missing_signals` in `scoring_context` only when at least one contributing pattern was not found (i.e., the list is non-empty).
- The system shall omit `missing_signals` from `scoring_context` when all contributing patterns had at least one member match.
- The system shall not modify `breakdown`, `max_from_this_signal`, `score`, or `evidence`.

**Proof Artifacts:**

- Test: `tests/test_scoring_context.py` — new test `test_member_missing_signals_partial` passes, asserting that when only one co-author pattern is found for a multi-pattern skill, the absent pattern ID appears in `missing_signals`.
- Test: `tests/test_scoring_context.py` — new test `test_member_missing_signals_omitted_when_all_found` passes, asserting that `missing_signals` is absent when all contributing patterns are found.

---

## Non-Goals (Out of Scope)

- GitHub artifact signals (`github-repo-artifacts`) — the GitHub artifact scanner aggregates at skill level, not artifact level; adding `missing_signals` there requires a separate refactor.
- Rate-based signals: pipeline pass rate, coverage delta, GitLab review metrics, MR co-author rates, GitHub review metrics — the concept of a "missing signal" does not translate to these continuous metrics.
- Changing existing field names or values in `scoring_context`.
- UI rendering changes — this spec ends at the JSON output layer.

## Design Considerations

No UI changes in this repo. The `missing_signals` field is consumed by the ai-fluency app; this spec only covers the collector output.

## Repository Standards

- All new logic added to `gitlab_scoring.py` following existing patterns in `calculate_scores()` and `calculate_member_scores()`.
- New tests added to `tests/test_scoring_context.py` following the existing fixture + assertion style in that file.
- `docs/scoring.md` must be updated to document the new `missing_signals` field per the CLAUDE.md constraint that it stays in sync with scoring data structures.
- Ruff-formatted, Python 3.10+ syntax.

## Technical Considerations

- In `calculate_scores()`, `missing_signals` can be computed after the per-project loop using the already-tracked `artifact_counts` dict: `[m["artifact_id"] for m in skill_maps if artifact_counts[m["artifact_id"]] == 0]`.
- Deduplication: the same artifact ID can appear in multiple mapping entries for the same skill (e.g. if weights differ). The `missing_signals` list should contain each artifact ID at most once; use a dict-ordered set comprehension or `list(dict.fromkeys(...))`.
- In `calculate_member_scores()`, `missing_signals` uses the already-tracked `pattern_member_counts` dict: `[m["artifact_id"] for m in skill_maps if pattern_member_counts.get(m["artifact_id"], 0) == 0]`.
- Only signals with `score > 0` are emitted; `missing_signals` applies within those emitted signals only.

## Security Considerations

No secrets, tokens, or user-controlled data flow through the `missing_signals` computation — values are drawn from the static mapping data structures.

## Success Metrics

- All existing tests continue to pass (zero regressions).
- Five new tests added, all passing.
- `docs/scoring.md` updated to document `missing_signals`.
- JSON output for a team with partial artifact coverage includes `missing_signals` on the relevant signal entries.

## Open Questions

No open questions at this time.
