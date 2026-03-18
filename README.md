# AI Fluency Collector

A CLI tool that scans GitLab repositories and team member activity for evidence of AI adoption, producing a JSON file compatible with the [ai-fluency](https://github.com/liatrio/ai-fluency) application's import format.

## What It Does

The collector gathers objective, measurable AI adoption signals from three sources:

1. **Repo Artifacts** — Detects AI tool configuration files in your team's GitLab projects
2. **CI Patterns** — Analyzes `.gitlab-ci.yml` for security, AI, and deployment pipeline patterns
3. **Member Activity** — Discovers AI co-authored commits across all repos your team members touch

It produces a single JSON file with weighted skill scores that can be imported directly into the ai-fluency application.

## Prerequisites

- Python 3.10+
- A GitLab.com personal access token with `read_api` scope

## Installation

```bash
git clone git@github.com:liatrio/ai-fluency-collector.git
cd ai-fluency-collector
pip install -e .
```

## Quick Start

### 1. Create a GitLab token

Generate a [personal access token](https://gitlab.com/-/user_settings/personal_access_tokens) with the `read_api` scope and export it:

```bash
export GITLAB_TOKEN="glpat-your-token-here"
```

### 2. Create a team config

Copy the example config and fill in your team details:

```bash
cp config.example.yaml my-team.yaml
```

Edit `my-team.yaml`:

```yaml
team:
  name: "Platform Engineering"
  code: "platform-eng"

  # GitLab usernames — used to discover AI activity across all repos
  members:
    - "alice.smith"
    - "bob.jones"
    - "carol.williams"

  # GitLab project paths to scan for artifacts and CI patterns
  projects:
    - "my-org/backend-api"
    - "my-org/frontend-app"
    - "my-org/infra/terraform"
```

### 3. Run the collector

```bash
ai-fluency-collector --config my-team.yaml
```

This will:
- Scan each project for AI tool artifacts (CLAUDE.md, .cursorrules, .mcp.json, etc.)
- Parse `.gitlab-ci.yml` files for security and AI pipeline patterns
- Discover repos each member owns or contributes to
- Search member commits for AI co-author patterns (Claude, Copilot, Cursor)
- Write a JSON file: `platform-eng-2026-W12.json`

### 4. Import the output

Upload the generated JSON file to the ai-fluency application's Import page.

## CLI Options

```
ai-fluency-collector --config <path> [--period <YYYY-WNN>]
```

| Flag | Required | Description |
|---|---|---|
| `--config` | Yes | Path to team configuration YAML file |
| `--period` | No | Survey period override (defaults to current ISO week) |

## Config File Reference

| Field | Required | Description |
|---|---|---|
| `team.name` | Yes | Display name for the team |
| `team.code` | Yes | Short identifier used in output filenames |
| `team.members` | Yes | List of GitLab usernames |
| `team.projects` | Yes | List of GitLab project paths (`namespace/project` format) |

## Signal Sources

### Repo Artifacts

The collector checks each project's default branch for these files and directories:

| Artifact | What It Indicates |
|---|---|
| `CLAUDE.md` | Claude Code context file |
| `.claude/settings.json` | Claude Code permission settings |
| `.mcp.json` or `mcp.json` | MCP server configuration |
| `prompts/` directory | Shared prompt templates |
| `.cursorrules` or `.cursor/` | Cursor AI configuration |
| `.github/copilot-instructions.md` | GitHub Copilot configuration |
| `AGENTS.md` or `.agents/` | Agent configuration |
| `.aider.conf.yml`, `.aider.model.settings.yml`, `.aiderignore` | Aider configuration |

### CI Patterns

The collector parses `.gitlab-ci.yml` (including `include` template directives) for:

| Pattern | What It Indicates |
|---|---|
| SAST/DAST stages | Security scanning adoption |
| Secret detection jobs | Secret management practices |
| AI code review jobs | AI-assisted code review (GitLab Duo, etc.) |
| AI test generation stages | AI-powered testing |
| Dependency scanning | Supply chain security |
| Code coverage reporting | Measurement practices |
| Deployment with environment gates | Automated deployment controls |

### Member Activity

For each team member, the collector:

1. Looks up their GitLab user profile
2. Discovers projects they own and projects they've pushed to
3. Searches their commits for AI co-author patterns:
   - `Co-Authored-By: Claude`
   - `Co-Authored-By: GitHub Copilot`
   - `Co-Authored-By: Cursor`

This catches AI usage in repos not explicitly listed in your config.

## Output Format

The output JSON follows the ai-fluency import schema:

```json
{
  "team_code": "platform-eng",
  "survey_period": "2026-W12",
  "sources": [
    {
      "source_id": "gitlab-repo-artifacts",
      "signals": [
        {
          "skill_id": "cq-context",
          "score": 75,
          "evidence": "CLAUDE.md found in 3/4 projects"
        }
      ]
    },
    {
      "source_id": "gitlab-ci-config",
      "signals": [...]
    },
    {
      "source_id": "gitlab-member-activity",
      "signals": [...]
    }
  ]
}
```

Sources with no signals are omitted from the output.

## Scoring

Scores are weighted (0-100) per skill. Multiple artifacts contributing to the same skill produce higher scores than a single artifact. Scores are averaged across all team projects (for repo artifacts and CI patterns) or based on the percentage of members with activity (for member signals).

For full details on every mapping, weight, formula, and instructions for customization, see [docs/scoring.md](docs/scoring.md).

## Example Output

```
AI Fluency Collector
  Team:     Platform Engineering
  Members:  3
  Projects: 4
  Period:   2026-W12
  Output:   platform-eng-2026-W12.json

Scanning for repo artifacts...
  my-org/backend-api: CLAUDE.md, .mcp.json or mcp.json, prompts/ directory
  my-org/frontend-app: .cursorrules or .cursor/
  my-org/infra/terraform: no artifacts found
  my-org/shared-libs: CLAUDE.md
  → 5 artifact signals detected

Scanning CI configurations...
  my-org/backend-api: sast-dast, secret-detection, code-coverage, deployment-gates
  my-org/frontend-app: code-coverage
  my-org/infra/terraform: no CI patterns found
  my-org/shared-libs: sast-dast
  → 4 CI signals detected

Scanning member activity...
  alice.smith: 3 repos discovered, coauthor-claude: 12
  bob.jones: 1 repos discovered, no AI co-author commits
  carol.williams: 5 repos discovered, coauthor-claude: 8, coauthor-copilot: 3
  → 3 member activity signals detected

Summary
  File:    /home/user/platform-eng-2026-W12.json
  Sources: 3
  Signals: 12
  Team:    platform-eng
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run a single test file
pytest tests/test_member_scanner.py

# Lint and format
ruff check .
ruff format .
```

## Error Handling

The collector validates all preconditions before making any API calls and provides clear error messages:

| Situation | Error Message |
|---|---|
| Config file missing | `Config file not found: {path}. Create one from config.example.yaml` |
| Invalid YAML | `Failed to parse {path}: {details}` |
| Missing required field | `Missing required field: team.code` |
| Token not set | `GITLAB_TOKEN environment variable is not set. Export a token with read_api scope.` |
| Token invalid | `GitLab authentication failed. Check that GITLAB_TOKEN is valid and has read_api scope.` |
| Invalid period | `Invalid period format: {value}. Expected YYYY-WNN (e.g. 2026-W12)` |
| Project inaccessible | `Access denied to project '{path}'. Check that the token has access to this project.` |
| Member not found | `GitLab user '{username}' not found. Check the username in your config.` |

## Limitations

- GitLab.com (SaaS) only — self-hosted GitLab is not supported
- Scans the default branch only, not feature branches
- One team per config file — run multiple times for multiple teams
- Produces a JSON file for manual import — no automatic upload
