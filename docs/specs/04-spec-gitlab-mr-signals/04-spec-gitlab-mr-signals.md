# 04-spec-gitlab-mr-signals

## Introduction / Overview

This spec adds two new behavioral signals collected from the GitLab MR API: **PR size** (median lines changed per AI-attributed MR) and **coding time** (median hours from first commit to MR open on AI-attributed MRs). Both signals are scoped to MRs with AI co-author tags; if no tagged MRs exist in the period the signals are omitted. They are emitted under the new source `gitlab-mr`.

## Goals

1. Emit a `pr_size` signal for `im-supervised-agent` reflecting how well teams decompose AI-assisted work.
2. Emit a `coding_time` signal for `im-inline-editing` and `im-supervised-agent` reflecting AI implementation speed.
3. Introduce `gitlab-mr` as a valid source_id in the output schema and CLAUDE.md.
4. Keep `changes_count` collection free of extra API calls by reusing the MR list already fetched.
5. Keep coding time free of extra API calls by reusing `get_mr_commits()` results already fetched for co-author detection.

## User Stories

- As a collector operator, I want PR size data for AI-attributed MRs so that I can see whether engineers are decomposing AI-assisted work into tight, reviewable chunks.
- As a collector operator, I want coding time data for AI-attributed MRs so that I can see whether AI tooling is accelerating implementation cycles over time.

## Demoable Units of Work

### Unit 1: PR Size Signal

**Purpose:** Fetch `changes_count` from merged MRs within the survey period, compute median for AI-attributed MRs only, and emit a scored signal.

**Functional Requirements:**

- The system shall scan merged MRs for all configured team members within the survey period (reusing `search_merge_requests` from the existing client).
- The system shall identify AI-attributed MRs using the same `MR_AI_COAUTHOR_PATTERNS` already defined in `gitlab_review_scanner.py` (check commits fetched via `get_mr_commits()`).
- The system shall collect `changes_count` from each MR object. When `changes_count` is `None`, not a number, or the string `"too many changes"`, the MR shall be excluded from the median calculation.
- The system shall compute the median `changes_count` across all AI-attributed MRs. If no AI-attributed MRs exist in the period, no `pr_size` signal shall be emitted.
- The system shall score the signal using the following rubric:

  | Median lines changed | Score |
  |---|---|
  | < 200 | 100 |
  | 200 – 399 | 80 |
  | 400 – 799 | 60 |
  | 800 – 1499 | 35 |
  | ≥ 1500 | 10 |

- The system shall emit the signal with `skill_id: "im-supervised-agent"` under `source_id: "gitlab-mr"`.
- The evidence string shall follow the format: `"PR size (AI-attributed): Xh median lines changed (N=Y MRs)"`

**Proof Artifacts:**

- Test: `tests/test_mr_scanner.py` passes — verifies median calculation, `changes_count` edge cases (None, "too many changes"), and score rubric mapping.
- CLI: `afc scan --config team.yaml` JSON output contains a `sources` entry with `"source_id": "gitlab-mr"` and a signal with `"skill_id": "im-supervised-agent"`.

---

### Unit 2: Coding Time Signal

**Purpose:** For each AI-attributed MR, compute elapsed hours from the earliest commit on the MR (`get_mr_commits()` reused from co-author detection) to `created_at` on the MR object, then emit a scored signal.

**Functional Requirements:**

- The system shall derive coding time per MR as: `mr.created_at – min(commit.created_at for commits in mr_commits)`, expressed in hours.
- The system shall use the commits already fetched via `get_mr_commits()` during co-author detection — no additional API calls are needed.
- If an MR has no commits (empty list), that MR shall be excluded from the coding time calculation.
- The system shall compute the median coding time across all AI-attributed MRs. If no AI-attributed MRs exist, no `coding_time` signal shall be emitted.
- The system shall score the signal using the following rubric:

  | Median coding time | Score |
  |---|---|
  | < 2 hours | 100 |
  | 2 – 7 hours | 85 |
  | 8 – 23 hours | 65 |
  | 24 – 71 hours (1–3 days) | 40 |
  | ≥ 72 hours (> 3 days) | 15 |

- The system shall emit two signals for coding time: `skill_id: "im-inline-editing"` and `skill_id: "im-supervised-agent"`, both under `source_id: "gitlab-mr"`.
- The evidence string shall follow the format: `"Coding time (AI-attributed): Xh median first commit to MR open (N=Y MRs)"`

**Proof Artifacts:**

- Test: `tests/test_mr_scanner.py` passes — verifies coding time derivation, zero-commit MR exclusion, and score rubric mapping.
- CLI: `afc scan --config team.yaml` JSON output contains `"source_id": "gitlab-mr"` signals for both `im-inline-editing` and `im-supervised-agent`.

---

### Unit 3: Schema and Documentation Updates

**Purpose:** Register `gitlab-mr` as a valid source_id and keep all documentation in sync.

**Functional Requirements:**

- The system shall accept `gitlab-mr` as a valid `source_id` in `output.py::build_output()`.
- `CLAUDE.md` shall list `gitlab-mr` alongside the other five valid `source_id` values.
- `docs/scoring.md` shall document the new `gitlab-mr` source with both signal rubrics.

**Proof Artifacts:**

- File: `src/ai_fluency_collector/output.py` contains `"gitlab-mr"` as a source_id keyword.
- File: `CLAUDE.md` lists `gitlab-mr` in the Key Constraints section.
- File: `docs/scoring.md` contains rubric tables for `pr_size` and `coding_time`.

---

## Non-Goals (Out of Scope)

- Scanning non-AI-attributed MRs for PR size or coding time (skip signal instead of fall back).
- Computing per-member breakdowns (team-level aggregates only, matching existing scanner patterns).
- Trend/delta scoring across periods (single-period snapshot, same as other signals).
- GitHub equivalent of this scanner (separate issue if needed).

## Design Considerations

No UI changes. All output is JSON consumed by ai-fluency import.

## Repository Standards

- New scanner class in `src/ai_fluency_collector/scanners/gitlab_mr_scanner.py`, following the `ReviewScanner` pattern (dataclass metrics, separate scoring module).
- Scoring mappings added to `gitlab_scoring.py` as `MR_SIZE_SKILL_MAPPINGS` and `MR_CODING_TIME_SKILL_MAPPINGS` with declarative `score_fn` lambdas.
- New `calculate_mr_signals()` function in `gitlab_scoring.py` following the shape of `calculate_review_scores()`.
- CLI wired in `cli.py`: scanner instantiated alongside `ReviewScanner`, results passed to `build_output()` as `mr_signals=`.
- All new code follows Python 3.10+ type hint syntax; tests follow existing `pytest` patterns in `tests/`.

## Technical Considerations

- `changes_count` in the GitLab MR list response is a string (may be `None` or `"too many changes"`) — parse defensively with `int()` wrapped in try/except.
- Commits are fetched via `get_mr_commits()` which is already called by the review scanner on authored MRs. The new `MRScanner` either calls this method independently or is designed to share results with `ReviewScanner` (acceptable to call independently for simplicity).
- Median is computed using `statistics.median()` (stdlib, no new deps).
- If only one MR qualifies, median equals that single value — acceptable.
- The `MRScanner.scan()` signature mirrors `ReviewScanner.scan(usernames, period)`.

## Security Considerations

- No new token scopes required beyond existing `read_api`.
- No individual attribution in output — all signals are team-level aggregates.

## Success Metrics

- `afc scan` on a team with AI-attributed MRs produces a `gitlab-mr` source block in output JSON.
- All new tests pass (`pytest tests/test_mr_scanner.py`).
- `docs/scoring.md` rubrics match `gitlab_scoring.py` mappings exactly.

## Open Questions

- No open questions at this time.
