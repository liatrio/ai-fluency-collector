# 04-questions-1-gitlab-mr-signals

Round 1 clarifying questions for spec 04.

## Q1 — source_id

The issue specifies `source_id: "gitlab-mr"` but CLAUDE.md lists only six valid source_ids
(none of which is `gitlab-mr`). Options:
- Add `gitlab-mr` as a new valid source_id (requires updating output.py, CLAUDE.md, and docs/scoring.md)
- Fold into existing `gitlab-review-signals` (already queries MR commits; avoids schema change)

## Q2 — AI-attribution fallback

For PR size and coding time, the issue says to scope to AI-attributed MRs "where possible."
If a team has zero AI co-author tags in the period, should we:
- Skip the signal entirely (return no score)
- Fall back to computing median across ALL merged MRs
- Emit a partial score based on overall MR size (with different evidence wording)

## Q3 — Coding time definition

The issue says "first commit on branch → MR open date" as the coding time proxy.
Fetching first commit requires an extra API call per MR (GET /projects/:id/repository/commits?ref_name=<branch>).
Should we:
- Use this definition (accurate, more API calls — one commits list per MR)
- Use MR created_at → merged_at as a simpler proxy (already in MR object, zero extra calls)
- Make it configurable

## Q4 — Scoring rubrics

The issue gives one threshold: "healthy = median < 400 lines for AI-attributed MRs."
Should we define a full rubric now (e.g., bands like < 200 = 100, 200–400 = 75, etc.),
or leave the rubric as an open question to finalize during implementation?
