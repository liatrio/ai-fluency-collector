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

## Scoring Formula

For each skill, the score is calculated as:

```
per_project_score = min(100, (sum of weights for found artifacts) / (sum of all weights for that skill) × 100)
final_score = round(average of per_project_score across all team projects)
```

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

## Modifying Weights and Mappings

All mappings live in `src/ai_fluency_collector/scoring.py` as two data structures:

- `ARTIFACT_SKILL_MAPPINGS` — repo artifact → skill mappings
- `CI_SKILL_MAPPINGS` — CI pattern → skill mappings

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

**Important**: Keep this document in sync with the code. If mappings change, update this document in the same commit.
