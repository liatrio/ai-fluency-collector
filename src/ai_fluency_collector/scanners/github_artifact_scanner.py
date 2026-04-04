from __future__ import annotations

import json
import re

from ai_fluency_collector.github_client import GitHubClient

# Security scanner patterns in workflow files
_SECURITY_SCANNERS = re.compile(
    r"codeql|snyk|semgrep|trivy|sonarqube|gitleaks|dependabot|bandit|trufflehog",
    re.IGNORECASE,
)

# AI tool invocation patterns in workflow files
_AI_WORKFLOW_PATTERNS = re.compile(
    r"claude|anthropic|copilot|cursor|duo|coderabbit|codium|diffblue",
    re.IGNORECASE,
)

# AI test generation patterns in workflow files
_AI_TEST_PATTERNS = re.compile(
    r"ai.?test|test.?gen|diffblue|codium|copilot.*test|claude.*test",
    re.IGNORECASE,
)

# AI keywords for documentation checks
_AI_DOC_KEYWORDS = re.compile(
    r"\bai\b|llm|copilot|claude|cursor|chatgpt|gpt|gemini",
    re.IGNORECASE,
)


def _line_count_score(content: str) -> int:
    """Tiered score based on line count: <10→40, 10-50→70, >50→100."""
    lines = len([ln for ln in content.splitlines() if ln.strip()])
    if lines < 10:
        return 40
    if lines <= 50:
        return 70
    return 100


def _file_count_score(count: int) -> int:
    """Tiered score based on file count: 0→0, <3→50, 3-10→75, >10→100."""
    if count == 0:
        return 0
    if count < 3:
        return 50
    if count <= 10:
        return 75
    return 100


class GitHubArtifactScanner:
    """Checks GitHub repos for AI tool artifacts and produces per-skill scores.

    Scores (0-100) are computed per repo using tiered logic based on file
    presence, content quality (line count, file count, structure).
    Multi-repo aggregation uses MAX — if any repo has the artifact, the team
    gets credit.
    """

    def __init__(self, client: GitHubClient) -> None:
        self.client = client

    def scan_repo(self, owner: str, repo: str) -> dict[str, dict]:
        """Scan a single repo and return {skill_id: {"score": int, "detail": str}}.

        The detail field contains a human-readable description of what was found
        (e.g., "CLAUDE.md, 85 lines") for richer evidence output.
        """
        scores: dict[str, dict] = {}

        scores["cq-context"] = self._score_context_files(owner, repo)
        scores["tg-permission-gated"] = self._score_permission_gated(owner, repo)
        scores["ks-patterns"] = self._score_prompt_dirs(owner, repo)
        scores["pm-advanced"] = self._score_mcp_config(owner, repo)
        scores["ks-documentation"] = self._score_ai_documentation(owner, repo)

        workflow_scores = self._score_workflows(owner, repo)
        scores.update(workflow_scores)

        return scores

    def scan_repos(self, repos: list[str]) -> list[dict]:
        """Scan all repos and return skill signals using max aggregation.

        Args:
            repos: List of "owner/repo" strings.

        Returns:
            List of {skill_id, score, evidence} dicts (score > 0 only).
        """
        if not repos:
            return []

        all_repo_scores: list[tuple[str, dict[str, dict]]] = []
        for repo_str in repos:
            owner, repo = repo_str.split("/", 1)
            repo_scores = self.scan_repo(owner, repo)
            all_repo_scores.append((repo_str, repo_scores))

        # Aggregate: max per skill across repos
        skill_max: dict[str, int] = {}
        skill_repos: dict[str, list[str]] = {}  # which repos contributed
        skill_repo_details: dict[str, dict[str, str]] = {}  # skill → {repo: detail}

        for repo_str, scores in all_repo_scores:
            for skill_id, info in scores.items():
                s = info["score"] if isinstance(info, dict) else info
                detail = info.get("detail", "") if isinstance(info, dict) else ""
                if s > skill_max.get(skill_id, 0):
                    skill_max[skill_id] = s
                if s > 0:
                    skill_repos.setdefault(skill_id, []).append(repo_str)
                    if detail:
                        skill_repo_details.setdefault(skill_id, {})[repo_str] = detail

        signals = []
        num_repos = len(repos)
        for skill_id, score in skill_max.items():
            if score <= 0:
                continue
            found_in = skill_repos.get(skill_id, [])
            missing = [r for r in repos if r not in found_in]
            details = skill_repo_details.get(skill_id, {})

            # Build evidence with file details where available
            repo_parts = []
            for r in found_in:
                if r in details:
                    repo_parts.append(f"{r} ({details[r]})")
                else:
                    repo_parts.append(r)
            evidence = f"Found in {len(found_in)}/{num_repos} repos: {', '.join(repo_parts)}"
            if missing:
                evidence += f". Missing: {', '.join(missing)}"
            breakdown = (
                f"{evidence}; tiered score {score} "
                f"(depth-based: higher scores reflect richer content or more files)"
            )

            # Build per_repo scoring_context
            per_repo: dict[str, dict] = {}
            for repo_str, scores in all_repo_scores:
                info = scores.get(skill_id, {})
                repo_score = info["score"] if isinstance(info, dict) else (info or 0)
                repo_detail = info.get("detail", "") if isinstance(info, dict) else ""
                entry: dict = {
                    "found": repo_score > 0,
                    "score": repo_score,
                }
                if repo_detail:
                    entry["detail"] = repo_detail
                per_repo[repo_str] = entry

            signals.append(
                {
                    "skill_id": skill_id,
                    "score": score,
                    "evidence": evidence,
                    "scoring_context": {
                        "breakdown": breakdown,
                        "max_from_this_signal": 100,
                        "per_repo": per_repo,
                    },
                }
            )

        return signals

    # ── Per-skill scoring helpers ────────────────────────────────────────────

    def _score_context_files(self, owner: str, repo: str) -> dict:
        """cq-context: CLAUDE.md, .cursorrules, .github/copilot-instructions.md."""
        candidates = [
            "CLAUDE.md",
            ".claude/CLAUDE.md",
            ".cursorrules",
            ".cursor/rules",
            ".github/copilot-instructions.md",
        ]
        best = 0
        best_path = ""
        best_lines = 0
        for path in candidates:
            content = self.client.get_file_content(owner, repo, path)
            if content is not None:
                score = _line_count_score(content)
                if score > best:
                    best = score
                    best_path = path
                    best_lines = len([ln for ln in content.splitlines() if ln.strip()])
        detail = f"{best_path}, {best_lines} lines" if best_path else ""
        return {"score": best, "detail": detail}

    def _score_permission_gated(self, owner: str, repo: str) -> dict:
        """tg-permission-gated: .claude/settings.json with permission config."""
        content = self.client.get_file_content(owner, repo, ".claude/settings.json")
        if content is None:
            return {"score": 0, "detail": ""}
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return {"score": 0, "detail": ""}
        # Look for permission-gating keys
        for key in ("permissions", "allowedTools", "blockedTools", "allow", "deny"):
            val = data.get(key)
            if val and (isinstance(val, list) and len(val) > 0 or isinstance(val, dict)):
                return {"score": 80, "detail": f".claude/settings.json with {key}"}
        # Present but no restrictions configured
        return {"score": 40, "detail": ".claude/settings.json (no restrictions)"}

    def _score_prompt_dirs(self, owner: str, repo: str) -> dict:
        """ks-patterns: prompts/ or .claude/commands/ directory."""
        best = 0
        best_path = ""
        best_count = 0
        for path in ("prompts", ".prompts", ".claude/commands"):
            listing = self.client.get_directory_listing(owner, repo, path)
            if listing is not None:
                file_count = sum(1 for e in listing if e.get("type") == "file")
                score = _file_count_score(file_count)
                if score > best:
                    best = score
                    best_path = path
                    best_count = file_count
        detail = f"{best_path}/, {best_count} files" if best_path else ""
        return {"score": best, "detail": detail}

    def _score_mcp_config(self, owner: str, repo: str) -> dict:
        """pm-advanced: MCP config files, custom MCP server dirs, settings.json mcpServers."""
        best = 0
        best_detail = ""

        # Check .mcp.json / mcp.json
        for path in (".mcp.json", "mcp.json"):
            content = self.client.get_file_content(owner, repo, path)
            if content is None:
                continue
            try:
                data = json.loads(content)
            except (json.JSONDecodeError, ValueError):
                best = max(best, 70)
                best_detail = path
                break
            servers = data.get("mcpServers") or data.get("servers") or {}
            if isinstance(servers, dict) and len(servers) > 1:
                return {"score": 100, "detail": f"{path}, {len(servers)} servers"}
            best = max(best, 70)
            best_detail = path
            break

        # Check custom MCP server directories (src/mcp/, mcp-servers/)
        for dir_path in ("src/mcp", "mcp-servers"):
            listing = self.client.get_directory_listing(owner, repo, dir_path)
            if listing is not None:
                return {"score": 100, "detail": f"{dir_path}/ directory"}

        # Check .claude/settings.json for mcpServers key
        if best < 100:
            settings = self.client.get_file_content(owner, repo, ".claude/settings.json")
            if settings:
                try:
                    data = json.loads(settings)
                    mcp_servers = data.get("mcpServers") or {}
                    if isinstance(mcp_servers, dict) and mcp_servers:
                        if len(mcp_servers) > 1:
                            return {
                                "score": 100,
                                "detail": f"settings.json, {len(mcp_servers)} MCP servers",
                            }
                        best = max(best, 70)
                        best_detail = best_detail or "settings.json mcpServers"
                except (json.JSONDecodeError, ValueError):
                    pass

        return {"score": best, "detail": best_detail}

    def _score_ai_documentation(self, owner: str, repo: str) -> dict:
        """ks-documentation: AI ADRs, AI usage guides, CONTRIBUTING.md mentions."""
        best = 0
        best_detail = ""

        # Check docs/adr/ or docs/decisions/ for AI-related ADRs
        for adr_path in ("docs/adr", "docs/decisions"):
            adr_listing = self.client.get_directory_listing(owner, repo, adr_path)
            if adr_listing is not None:
                ai_adrs = [
                    e
                    for e in adr_listing
                    if e.get("type") == "file" and _AI_DOC_KEYWORDS.search(e.get("name", ""))
                ]
                if ai_adrs:
                    best = max(best, 80)
                    names = [e.get("name", "") for e in ai_adrs[:3]]
                    best_detail = f"{adr_path}/: {', '.join(names)}"
                    break

        # Check docs/ for AI-named files
        docs_listing = self.client.get_directory_listing(owner, repo, "docs")
        if docs_listing is not None:
            ai_docs = [
                e
                for e in docs_listing
                if e.get("type") == "file" and _AI_DOC_KEYWORDS.search(e.get("name", ""))
            ]
            if ai_docs and best < 70:
                best = 70
                names = [e.get("name", "") for e in ai_docs[:3]]
                best_detail = f"docs/: {', '.join(names)}"

        # CONTRIBUTING.md AI mentions
        contributing = self.client.get_file_content(owner, repo, "CONTRIBUTING.md")
        if contributing and _AI_DOC_KEYWORDS.search(contributing) and best < 60:
            best = 60
            best_detail = "CONTRIBUTING.md with AI mentions"

        return {"score": best, "detail": best_detail}

    def _score_workflows(self, owner: str, repo: str) -> dict[str, dict]:
        """tg-security-gates, sdlc-testing, ks-workflows from multiple sources."""
        workflow_contents = self.client.get_workflow_files(owner, repo)
        combined = "\n".join(workflow_contents) if workflow_contents else ""

        # ── tg-security-gates: workflows + pre-commit hooks ──────────────────
        security_matches = set(m.group(0).lower() for m in _SECURITY_SCANNERS.finditer(combined))

        # Also check .pre-commit-config.yaml and .githooks/ for security patterns
        precommit = self.client.get_file_content(owner, repo, ".pre-commit-config.yaml")
        if precommit:
            security_matches |= set(
                m.group(0).lower() for m in _SECURITY_SCANNERS.finditer(precommit)
            )
        githooks = self.client.get_directory_listing(owner, repo, ".githooks")
        if githooks:
            for entry in githooks:
                if entry.get("type") == "file":
                    hook_content = self.client.get_file_content(owner, repo, entry.get("path", ""))
                    if hook_content:
                        security_matches |= set(
                            m.group(0).lower() for m in _SECURITY_SCANNERS.finditer(hook_content)
                        )

        if len(security_matches) >= 2:
            security_score = 80
        elif security_matches:
            security_score = 60
        else:
            security_score = 0
        security_detail = ", ".join(sorted(security_matches)) if security_matches else ""

        # ── sdlc-testing: AI test patterns in workflows ──────────────────────
        testing_score = 70 if combined and _AI_TEST_PATTERNS.search(combined) else 0

        # ── ks-workflows: AI agent invocations in workflows, scripts, .claude/ ─
        workflow_score = 0
        workflow_detail = ""
        if combined and _AI_WORKFLOW_PATTERNS.search(combined):
            workflow_score = 80
            workflow_detail = "workflow files"

        # Check Makefile and scripts/ for AI tool orchestration
        if workflow_score < 80:
            makefile = self.client.get_file_content(owner, repo, "Makefile")
            if makefile and _AI_WORKFLOW_PATTERNS.search(makefile):
                workflow_score = max(workflow_score, 80)
                workflow_detail = "Makefile"
            scripts = self.client.get_directory_listing(owner, repo, "scripts")
            if scripts and workflow_score < 80:
                for entry in scripts:
                    if entry.get("type") == "file":
                        content = self.client.get_file_content(owner, repo, entry.get("path", ""))
                        if content and _AI_WORKFLOW_PATTERNS.search(content):
                            workflow_score = max(workflow_score, 80)
                            workflow_detail = f"scripts/{entry.get('name', '')}"
                            break

        # Check .claude/ for hooks/automation config
        if workflow_score < 80:
            claude_settings = self.client.get_file_content(owner, repo, ".claude/settings.json")
            if claude_settings:
                try:
                    data = json.loads(claude_settings)
                    if data.get("hooks") or data.get("commands"):
                        workflow_score = max(workflow_score, 70)
                        workflow_detail = ".claude/settings.json hooks"
                except (json.JSONDecodeError, ValueError):
                    pass

        return {
            "tg-security-gates": {"score": security_score, "detail": security_detail},
            "sdlc-testing": {"score": testing_score, "detail": ""},
            "ks-workflows": {"score": workflow_score, "detail": workflow_detail},
        }
