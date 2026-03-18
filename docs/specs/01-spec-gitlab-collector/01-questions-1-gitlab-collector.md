# 01 Questions Round 1 - GitLab Collector

Please answer each question below (select one or more options, or add your own notes). Feel free to add additional context under any question.

## 1. Repo Artifact Detection

Which files/directories should the collector look for to determine AI adoption? Here's what I'm thinking based on the skill tree. Check any you want to include, remove any that don't make sense, and add any I'm missing.

- [x] (A) `CLAUDE.md` - Context file for Claude Code (maps to: cq-context, im-autocomplete)
- [x] (B) `.claude/settings.json` - Claude Code permission settings (maps to: tg-permission-gated)
- [x] (C) `.mcp.json` or `mcp.json` - MCP server config (maps to: im-chat, pm-core)
- [x] (D) `prompts/` directory - Shared prompt templates (maps to: ks-patterns, cq-delegation)
- [x] (E) `.cursorrules` or `.cursor/` - Cursor AI config (maps to: im-autocomplete, im-inline-edit)
- [x] (F) `.github/copilot-instructions.md` - Copilot config (maps to: im-autocomplete)
- [x] (G) `AGENTS.md` or `.agents/` - Agent configuration (maps to: im-supervised-agent, im-cli-agent)
- [x] (H) `.aider*` files - Aider config (maps to: im-chat)
- [ ] (I) Other (describe)

## 2. CI Config Detection

Which CI patterns should the collector look for in `.gitlab-ci.yml`?

- [x] (A) SAST/DAST scanner stages (maps to: sdlc-security, tg-security-gates)
- [x] (B) Secret detection jobs (maps to: sdlc-security)
- [x] (C) AI-assisted code review jobs, e.g. GitLab Duo or third-party (maps to: tg-code-review)
- [x] (D) AI-powered test generation stages (maps to: sdlc-testing)
- [x] (E) Dependency scanning (maps to: sdlc-security)
- [x] (F) Code coverage reporting (maps to: pm-measurement)
- [x] (G) Deployment stages with automated gates (maps to: sdlc-deployment, tg-supervised-auto)
- [ ] (H) Other (describe)

## 3. Scoring Strategy

How should the collector calculate scores (0-100) for each skill?

- [ ] (A) **Binary per-repo, averaged across team repos**: Each repo gets 0 or 100 for a skill, team score is the percentage of repos that have it (e.g., 3/4 repos have CLAUDE.md = score 75)
- [x] (B) **Weighted presence**: Some artifacts are worth more than others within a skill (e.g., having both CLAUDE.md and .claude/settings.json scores higher for cq-context than just CLAUDE.md alone)
- [ ] (C) **Tiered scoring**: Score tiers based on depth (e.g., having CLAUDE.md = 40, CLAUDE.md + prompts/ = 70, CLAUDE.md + prompts/ + .mcp.json = 100)
- [ ] (D) Other (describe)

## 4. Config File Format

What format do you prefer for the team config file?

- [x] (A) YAML
- [ ] (B) TOML
- [ ] (C) JSON
- [ ] (D) No preference

## 5. Survey Period

How should the collector determine the survey period for the output?

- [ ] (A) Auto-calculate current ISO week (e.g., running today outputs `2026-W12`)
- [ ] (B) Require it as a CLI argument
- [x] (C) Both: auto-calculate by default, allow override via CLI flag
- [ ] (D) Other (describe)

## 6. Multiple Teams

Should the config support multiple teams in a single run?

- [x] (A) One config file per team, one run per team
- [ ] (B) One config file can define multiple teams, collector processes all and outputs one JSON per team
- [ ] (C) One config file with multiple teams, single combined output
- [ ] (D) Other (describe)

## 7. GitLab API Access

What GitLab setup should we target?

- [ ] (A) Self-hosted GitLab only
- [x] (B) GitLab.com (SaaS) only
- [ ] (C) Both, configurable via URL in config
- [ ] (D) Other (describe)

## 8. Error Handling

When the collector can't access a repo (permissions, doesn't exist), what should happen?

- [ ] (A) Skip it and include a warning in CLI output, still produce the JSON
- [x] (B) Fail the entire run
- [ ] (C) Skip it and include the error in the output JSON as a warnings field
- [ ] (D) Other (describe)

## 9. Python Project Standards

Any preferences for the Python project setup?

- [x] (A) **Package manager**: pip + requirements.txt / poetry / uv
- [x] (B) **Min Python version**: 3.10 / 3.11 / 3.12 / no preference
- [x] (C) **CLI framework**: click / argparse / typer / no preference
- [x] (D) **Testing**: pytest (assumed, any objections?)
- [ ] (E) Other (describe)
