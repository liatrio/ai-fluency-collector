# AI Fluency Collector

A CLI tool that scans GitLab and GitHub repositories and team member activity for evidence of AI adoption, producing a JSON file compatible with the [ai-fluency](https://github.com/liatrio/ai-fluency) application's import format.

## What It Does

The collector gathers objective, measurable AI adoption signals from two scan modes:

**GitLab (`afc scan`)**:
1. **Repo Artifacts** — Detects AI tool configuration files in your team's GitLab projects
2. **CI Patterns** — Analyzes `.gitlab-ci.yml` for security, AI, and deployment pipeline patterns
3. **Member Activity** — Discovers AI co-authored commits across all repos your team members touch
4. **MR Review Signals** — Measures team review behavior (LGTM rate, review depth, self-review rate)

**GitHub (`afc github-scan`)**:
1. **Repo Artifacts** — Detects AI tool configuration files with tiered scoring (depth of adoption matters)
2. **PR Review Signals** — Measures review behavior and AI co-author rates across team PRs

It produces a single JSON file with weighted skill scores that can be imported directly into the ai-fluency application.

## Prerequisites

- Python 3.10+
- A GitLab personal access token with `read_api` scope (for `afc scan`)
- A GitHub personal access token with `repo` and `read:user` scopes (for `afc github-scan`)

## Installation

### Recommended: pipx (isolated install, no venv needed)

First, install pipx if you don't have it:

```bash
# macOS
brew install pipx

# Linux / other
pip3 install --user pipx
pipx ensurepath
```

Then install the collector:

```bash
git clone git@github.com:liatrio/ai-fluency-collector.git
cd ai-fluency-collector
pipx install .
```

This installs `afc` (and `ai-fluency-collector`) globally in an isolated environment — no venv activation needed.

### Alternative: pip with venv

```bash
git clone git@github.com:liatrio/ai-fluency-collector.git
cd ai-fluency-collector
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Quick Start

### GitLab

#### 1. Create a GitLab token

Generate a [personal access token](https://gitlab.com/-/user_settings/personal_access_tokens) with the `read_api` scope and export it:

```bash
export GITLAB_TOKEN="glpat-your-token-here"
```

#### 2. Create a team config

```bash
cp config.example.yaml my-team.yaml
```

Edit `my-team.yaml`:

```yaml
team:
  name: "Platform Engineering"
  code: "platform-eng"

  members:
    - "alice.smith"
    - "bob.jones"
    - "carol.williams"

  projects:
    - "my-org/backend-api"
    - "my-org/frontend-app"
    - "my-org/infra/terraform"
```

#### 3. Run the collector

```bash
afc scan --config my-team.yaml
```

This scans each project for artifacts, parses CI configs, discovers member repo activity, and writes `platform-eng-2026-W12.json`.

---

### GitHub

#### 1. Create a GitHub token

Generate a [personal access token](https://github.com/settings/tokens) with `repo` and `read:user` scopes and export it:

```bash
export GITHUB_TOKEN="ghp_your-token-here"
```

#### 2. Add GitHub repos to your config

```yaml
team:
  name: "Platform Engineering"
  code: "platform-eng"

  members:
    - "alice-smith"
    - "bob-jones"

  github_repos:
    - "my-org/backend-api"
    - "my-org/frontend-app"
```

#### 3. Run the GitHub scan

```bash
afc github-scan --config my-team.yaml
```

This scans each repo for AI tool artifacts (with tiered scoring) and analyzes PR review behavior, writing `platform-eng-2026-W12.json`.

---

### 4. Import the output

Upload the generated JSON file to the ai-fluency application's Import page.

## CLI Options

### `afc scan` (GitLab)

```
afc scan --config <path> [--period <YYYY-WNN>] [--gitlab-url <URL>] [--validate] [--usernames <list>]
```

| Flag | Required | Description |
|---|---|---|
| `--config` | Yes | Path to team configuration YAML file |
| `--period` | No | Survey period override (defaults to current ISO week) |
| `--gitlab-url` | No | GitLab instance URL (overrides `gitlab_url` in config) |
| `--validate` | No | Test connection, list accessible projects, and exit without scanning |
| `--usernames` | No | Comma-separated GitLab usernames (overrides `members` in config) |
| `--from` / `--to` | No | Date range for multi-week scanning (YYYY-MM-DD) |

### `afc github-scan` (GitHub)

```
afc github-scan --config <path> [--period <YYYY-WNN>] [--usernames <list>]
```

| Flag | Required | Description |
|---|---|---|
| `--config` | Yes | Path to team configuration YAML file |
| `--period` | No | Survey period override (defaults to current ISO week) |
| `--usernames` | No | Comma-separated GitHub usernames (overrides `members` in config) |

## Config File Reference

| Field | Required | Description |
|---|---|---|
| `team.name` | Yes | Display name for the team |
| `team.code` | Yes | Short identifier used in output filenames |
| `team.members` | Yes | List of GitLab or GitHub usernames |
| `team.projects` | No* | List of GitLab project paths (`namespace/project` format) |
| `team.github_repos` | No* | List of GitHub repos (`owner/repo` format) |
| `team.gitlab_url` | No | GitLab instance URL (defaults to `https://gitlab.com`) |
| `team.ci_signals` | No | Custom CI job name overrides (GitLab only) |
| `team.scan_from` / `team.scan_to` | No | Date range for multi-week scanning, YYYY-MM-DD (GitLab only) |

*At least one of `projects` or `github_repos` must be present.

## Signal Sources

### GitLab Signal Sources

#### Repo Artifacts

The collector checks all active branches (commits within last 90 days) for these files and directories. Artifacts found on feature branches are weighted higher (0.8) than those on the default branch (0.5), since feature branch presence indicates active AI tool adoption:

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

#### CI Patterns

The collector parses `.gitlab-ci.yml` across all active branches (including `include` template directives) for:

| Pattern | What It Indicates |
|---|---|
| SAST/DAST stages | Security scanning adoption |
| Secret detection jobs | Secret management practices |
| AI code review jobs | AI-assisted code review (GitLab Duo, etc.) |
| AI test generation stages | AI-powered testing |
| Dependency scanning | Supply chain security |
| Code coverage reporting | Measurement practices |
| Deployment with environment gates | Automated deployment controls |

#### Member Activity

For each team member, the collector:

1. Looks up their GitLab user profile
2. Discovers projects they own and projects they've pushed to
3. Searches their commits for AI co-author patterns:
   - `Co-Authored-By: Claude`
   - `Co-Authored-By: GitHub Copilot`
   - `Co-Authored-By: Cursor`

This catches AI usage in repos not explicitly listed in your config.

---

### GitHub Signal Sources

#### Repo Artifacts

The collector checks each listed GitHub repo for AI tool artifacts using **tiered scoring** — the score reflects depth of adoption (e.g., a well-populated `prompts/` directory scores higher than one with a single file):

| Artifact | What It Indicates |
|---|---|
| `CLAUDE.md` | Claude Code context file (scored by line count) |
| `.claude/settings.json` | Claude Code permission settings |
| `.mcp.json` or `mcp.json` | MCP server configuration (scored by number of servers) |
| `prompts/`, `.prompts/`, `.claude/commands/` | Shared prompt templates (scored by file count) |
| `.cursorrules` | Cursor AI configuration |
| `.github/copilot-instructions.md` | GitHub Copilot configuration |
| `.github/workflows/` | Scanned for security scanners, AI test generation, and AI tool patterns |
| `docs/adr/`, `docs/`, `CONTRIBUTING.md` | Scanned for AI-related documentation |

Scores are aggregated with MAX across repos — if any repo has a given artifact, the team gets credit.

#### PR Review Signals

For each team member, the collector scans GitHub PRs authored during the survey period and computes team-level metrics:

| Metric | What It Measures |
|---|---|
| LGTM rate | % of PRs approved with zero inline review comments |
| Review comment depth | Avg ratio of files with inline comments to total changed files |
| AI co-author rate | % of PRs with any AI co-author tag (Claude, Copilot, Cursor) |
| AI agent co-author rate | % of PRs with Claude Code CLI co-author tag |
| Self-review rate | % of PRs where author commented before first approval |

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
    },
    {
      "source_id": "gitlab-review-signals",
      "signals": [...]
    },
    {
      "source_id": "github-repo-artifacts",
      "signals": [...]
    },
    {
      "source_id": "github-review-signals",
      "signals": [...]
    }
  ]
}
```

Sources with no signals are omitted from the output. A single output file may include both GitLab and GitHub sources if both are configured.

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
# Install with dev dependencies (use a venv for development)
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
| Token invalid | `GitLab authentication failed at {url}. Check that GITLAB_TOKEN is valid and has read_api scope.` |
| Connection failed | `Could not connect to {url}. Check the gitlab_url in your config.` |
| Invalid period | `Invalid period format: {value}. Expected YYYY-WNN (e.g. 2026-W12)` |
| Project inaccessible | `Access denied to project '{path}'. Check that the token has access to this project.` |
| Member not found | `GitLab user '{username}' not found. Check the username in your config.` |
| GitHub token not set | `GITHUB_TOKEN environment variable is not set.` |
| GitHub token invalid | `GitHub authentication failed. Check that GITHUB_TOKEN is valid.` |
| No github_repos configured | `No github_repos configured. Add repos under team.github_repos in your config.` |

## Limitations

- GitLab: supports GitLab.com and self-hosted instances (set `gitlab_url` in config)
- GitHub: supports GitHub.com only (no GitHub Enterprise)
- One team per config file — run multiple times for multiple teams
- Produces a JSON file for manual import — no automatic upload
