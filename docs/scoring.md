# Scoring Documentation

This document describes every artifact and CI pattern the collector detects, which skill IDs each maps to, the weights assigned, the scoring formula, and how to modify the scoring configuration.

## Repo Artifact Mappings

| Artifact ID | Files/Directories Checked | Skill ID | Weight |
|---|---|---|---|
| `claude-md` | `CLAUDE.md` | `cq-context` | 0.5 |
| `claude-md` | `CLAUDE.md` | `im-autocomplete` | 0.3 |
| `claude-settings` | `.claude/settings.json` | `tg-permission-gated` | 1.0 |
| `mcp-json` | `.mcp.json` or `mcp.json` | `im-chat` | 0.5 |
| `mcp-json` | `.mcp.json` or `mcp.json` | `pm-core` | 0.5 |
| `prompts-dir` | `prompts/` directory | `ks-patterns` | 0.7 |
| `prompts-dir` | `prompts/` directory | `cq-delegation` | 0.5 |
| `cursor` | `.cursorrules` or `.cursor/` | `im-autocomplete` | 0.3 |
| `cursor` | `.cursorrules` or `.cursor/` | `im-inline-edit` | 0.5 |
| `copilot-instructions` | `.github/copilot-instructions.md` | `im-autocomplete` | 0.3 |
| `agents` | `AGENTS.md` or `.agents/` | `im-supervised-agent` | 0.5 |
| `agents` | `AGENTS.md` or `.agents/` | `im-cli-agent` | 0.5 |
| `aider` | `.aider.conf.yml`, `.aider.model.settings.yml`, or `.aiderignore` | `im-chat` | 0.5 |

## CI Pattern Mappings

| Pattern ID | What It Detects | Skill ID | Weight |
|---|---|---|---|
| `sast-dast` | SAST/DAST scanner stages, GitLab Security templates | `sdlc-security` | 0.4 |
| `sast-dast` | (same) | `tg-security-gates` | 0.5 |
| `secret-detection` | Secret detection jobs, GitLab Secret-Detection template | `sdlc-security` | 0.3 |
| `ai-code-review` | AI-assisted code review (GitLab Duo, third-party tools) | `tg-code-review` | 1.0 |
| `ai-test-generation` | AI-powered test generation stages | `sdlc-testing` | 1.0 |
| `dependency-scanning` | Dependency scanning jobs, GitLab template | `sdlc-security` | 0.3 |
| `code-coverage` | Coverage key or coverage_report in artifacts | `pm-measurement` | 1.0 |
| `deployment-gates` | Deploy stages with environment and rules | `sdlc-deployment` | 0.5 |
| `deployment-gates` | (same) | `tg-supervised-auto` | 0.5 |

## CI Pipeline Metrics

Computed from GitLab pipeline history for the survey period. Scores are team-level with no individual attribution.

| Metric Key | What It Measures | Skill ID | Score Formula |
|---|---|---|---|
| `pipeline_pass_rate` | % of commits whose first CI pipeline run succeeded (first-attempt pass rate) | `pm-core` | `rate × 100` |
| `pipeline_pass_rate` | (same) | `tg-code-review` | `rate × 100` |

**Aggregation**: Mean first-attempt pass rate across all team projects that have pipeline data for the period. Projects with no pipelines are excluded from the mean.

**Evidence format**: "78% of pipelines passed on first attempt (N=47 pipelines)"

Mappings live in `src/ai_fluency_collector/scoring.py` as `CI_PIPELINE_SKILL_MAPPINGS`.

## Member Activity Mappings

| Pattern ID | What It Detects | Skill ID | Weight |
|---|---|---|---|
| `coauthor-claude` | Co-Authored-By: Claude in commit messages | `im-cli-agent` | 0.5 |
| `coauthor-claude` | (same) | `im-chat` | 0.5 |
| `coauthor-copilot` | Co-Authored-By: GitHub Copilot in commit messages | `im-autocomplete` | 0.5 |
| `coauthor-cursor` | Co-Authored-By: Cursor in commit messages | `im-autocomplete` | 0.3 |
| `coauthor-cursor` | (same) | `im-inline-edit` | 0.3 |

Member activity scores are based on the percentage of team members who have AI co-authored commits.

## MR Review Behavioral Mappings

Computed from aggregated merge request data for the survey period. Scores are derived from team-level metrics with no individual attribution.

| Metric Key | What It Measures | Skill ID | Score Formula |
|---|---|---|---|
| `lgtm_without_comment` | % of team-authored MRs approved with zero non-system review notes | `tg-code-review` | `100 - (rate × 100)` (lower LGTM rate = higher score) |
| `review_comment_depth` | Avg ratio of files with team reviewer discussion threads to total changed files | `cq-evaluation` | `ratio × 100` |
| `self_review_rate` | % of team-authored MRs where author commented before first approval | `cq-refinement` | `rate × 100` |

System notes (bot comments, status changes, label additions) are excluded from all analysis. Only `system: false` notes count as review activity. For example, if 3 out of 5 members have Claude co-authored commits, the weight contribution is scaled by 3/5 = 60%.

## Branch Scanning

The collector scans all **active branches** (branches with a commit within the last 90 days). Stale branches are excluded to avoid false signals from abandoned work.

Artifacts and CI patterns are weighted by branch type:

| Branch Type | Weight | Rationale |
|---|---|---|
| Default branch (e.g., `main`) | 0.5 | Artifact may have been added long ago and could be stale |
| Active feature branch | 0.8 | Indicates current, active AI tool adoption |

For each artifact/pattern per project, the **highest weight** across all active branches is used. For example, if `CLAUDE.md` exists on both `main` (0.5) and `feat/add-ai` (0.8), the weight is 0.8.

## Scoring Formula

For each skill, the score is calculated as:

```
per_project_score = min(100, (sum of (mapping_weight × branch_weight) for found artifacts) / (sum of all mapping weights for that skill) × 100)
final_score = round(average of per_project_score across all team projects)
```

When scan results use boolean values (True/False), True is treated as weight 1.0 for backwards compatibility.

### Worked Example

**Setup**: A team has 4 projects. The skill `im-autocomplete` has three contributing mappings:
- `claude-md` → weight 0.3
- `cursor` → weight 0.3
- `copilot-instructions` → weight 0.3

Total weight for `im-autocomplete` = 0.3 + 0.3 + 0.3 = 0.9

**Project results**:
| Project | CLAUDE.md | .cursorrules | copilot-instructions.md |
|---|---|---|---|
| project-1 | Yes | Yes | No |
| project-2 | Yes | No | No |
| project-3 | Yes | Yes | Yes |
| project-4 | No | No | No |

**Per-project scores**:
- Project 1: min(100, (0.3 + 0.3) / 0.9 × 100) = min(100, 66.7) = 66.7
- Project 2: min(100, 0.3 / 0.9 × 100) = min(100, 33.3) = 33.3
- Project 3: min(100, (0.3 + 0.3 + 0.3) / 0.9 × 100) = min(100, 100) = 100
- Project 4: min(100, 0 / 0.9 × 100) = 0

**Final score**: round((66.7 + 33.3 + 100 + 0) / 4) = round(50) = **50**

**Evidence**: "CLAUDE.md found in 3/4 projects; .cursorrules or .cursor/ found in 2/4 projects; .github/copilot-instructions.md found in 1/4 projects"

### Worked Example: Member Activity

**Setup**: A team has 3 members. The skill `im-cli-agent` has one contributing mapping:
- `coauthor-claude` → weight 0.5

**Member results**:
| Member | Claude co-authored commits |
|---|---|
| alice | 12 commits |
| bob | 0 commits |
| carol | 5 commits |

2 out of 3 members have Claude co-authored commits. The weight contribution is 0.5 × (2/3) = 0.333.

**Score**: round(min(100, 0.333 / 0.5 × 100)) = round(66.7) = **67**

**Evidence**: "Co-authored commits with Claude by 2/3 members (17 commits)"

## GitHub Artifact Scoring

GitHub artifact scoring uses a **tiered approach** rather than binary presence. Scores are determined by depth of adoption (line count, file count, server count) and aggregated with **MAX across repos** — the highest-scoring repo's value is used for the team.

| Skill | What It Checks | Score Logic |
|---|---|---|
| `cq-context` | `CLAUDE.md`, `.cursorrules`, `.github/copilot-instructions.md` | Line count: <10 → 40, 10–50 → 70, >50 → 100 |
| `tg-permission-gated` | `.claude/settings.json` | File present with permission keys → 80; bare file → 40 |
| `ks-patterns` | `prompts/`, `.prompts/`, `.claude/commands/` | File count: 0 → 0, <3 → 50, 3–10 → 75, >10 → 100 |
| `pm-advanced` | `.mcp.json`, `mcp.json` (parsed for `mcpServers`) | Unparseable → 70, 1 server → 70, >1 server → 100 |
| `ks-documentation` | `docs/adr/` (AI ADRs), `docs/` (AI docs), `CONTRIBUTING.md` | AI ADRs → 80, AI docs → 70, CONTRIBUTING → 60 |
| `tg-security-gates` | `.github/workflows/` (CodeQL, Snyk, Semgrep, etc.) | 2+ scanners → 80, 1 scanner → 60, none → 0 |
| `sdlc-testing` | `.github/workflows/` (Diffblue, CodiumAI, Claude test patterns) | Any AI test pattern → 70, none → 0 |
| `ks-workflows` | `.github/workflows/` (Claude, Copilot, Cursor, Duo, CodeRabbit) | Any AI tool pattern → 80, none → 0 |

The scoring logic lives in `src/ai_fluency_collector/scanners/github_artifact_scanner.py`.

## GitHub PR Review Behavioral Mappings

Computed from GitHub PR data for the survey period. Scores are team-level with no individual attribution.

| Metric Key | What It Measures | Skill ID | Score Formula |
|---|---|---|---|
| `lgtm_without_comment` | % of authored PRs approved with zero inline review comments | `tg-code-review` | `100 - (rate × 100)` (lower LGTM rate = more review activity = higher score) |
| `review_comment_depth` | Avg ratio of files with inline comments to total changed files | `cq-evaluation` | `ratio × 100` |
| `ai_coauthor_rate` | % of authored PRs with any AI co-author tag | `im-chat` | `rate × 100` |
| `ai_agent_coauthor_rate` | % of authored PRs with Claude Code CLI co-author tag | `im-supervised-agent` | `rate × 100` |
| `self_review_rate` | % of PRs where author commented before first approval | `cq-refinement` | `rate × 100` |

AI co-author patterns detected: `co-authored-by:.*claude`, `co-authored-by:.*copilot`, `co-authored-by:.*cursor`, `co-authored-by:.*claude.*code|generated with.*claude.*code`.

Mappings live in `src/ai_fluency_collector/github_scoring.py` as `GITHUB_REVIEW_SKILL_MAPPINGS`.

## Modifying Weights and Mappings

All GitLab mappings live in `src/ai_fluency_collector/scoring.py`. GitHub review mappings live in `src/ai_fluency_collector/github_scoring.py`. GitHub artifact scoring logic is in `src/ai_fluency_collector/scanners/github_artifact_scanner.py`.

GitLab data structures:

- `ARTIFACT_SKILL_MAPPINGS` — repo artifact → skill mappings
- `CI_SKILL_MAPPINGS` — CI pattern → skill mappings
- `MEMBER_SKILL_MAPPINGS` — member activity → skill mappings

### To change a weight

Find the mapping entry and update its `weight` value:

```python
# Before
{"artifact_id": "claude-md", "skill_id": "cq-context", "weight": 0.5},
# After
{"artifact_id": "claude-md", "skill_id": "cq-context", "weight": 0.8},
```

### To add a new mapping for an existing artifact

Add a new dict to the appropriate list:

```python
ARTIFACT_SKILL_MAPPINGS: list[dict] = [
    # ... existing entries ...
    {"artifact_id": "claude-md", "skill_id": "new-skill-id", "weight": 0.4},
]
```

### To add a new artifact type

1. Add the artifact definition to `ARTIFACT_DEFINITIONS` in `src/ai_fluency_collector/scanners/artifact_scanner.py`:
   ```python
   {
       "id": "new-artifact",
       "name": "New Artifact",
       "checks": [("file", "path/to/file")],
   }
   ```
2. Add mapping entries to `ARTIFACT_SKILL_MAPPINGS` in `scoring.py`
3. Update this document to reflect the new mappings

### To add a new CI pattern

1. Add detection logic in `src/ai_fluency_collector/scanners/ci_scanner.py`
2. Add the pattern ID to `CI_PATTERN_IDS`
3. Add mapping entries to `CI_SKILL_MAPPINGS` in `scoring.py`
4. Update this document to reflect the new mappings

### To add a new co-author pattern

1. Add a pattern definition to `AI_COAUTHOR_PATTERNS` in `src/ai_fluency_collector/scanners/member_scanner.py`:
   ```python
   {
       "id": "coauthor-new-tool",
       "name": "New Tool",
       "pattern": re.compile(r"co-authored-by:.*new.?tool", re.IGNORECASE),
   }
   ```
2. Add mapping entries to `MEMBER_SKILL_MAPPINGS` in `scoring.py`
3. Update this document to reflect the new mappings

### To add a new review metric

1. Add metric computation to `ReviewScanner.scan()` in `src/ai_fluency_collector/scanners/review_scanner.py`
2. Populate `metrics.evidence[new_metric_key]` with a team-level evidence string
3. Add a mapping entry to `REVIEW_SKILL_MAPPINGS` in `scoring.py`:
   ```python
   "new_metric_key": [
       {"skill_id": "target-skill-id", "score_fn": lambda rate: round(rate * 100)},
   ],
   ```
4. Update this document

**Important**: Keep this document in sync with the code. If mappings change, update this document in the same commit.
