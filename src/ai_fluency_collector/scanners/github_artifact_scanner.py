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

    def scan_repo(self, owner: str, repo: str) -> dict[str, int]:
        """Scan a single repo and return {skill_id: score} (0-100 each)."""
        scores: dict[str, int] = {}

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

        all_repo_scores: list[tuple[str, dict[str, int]]] = []
        for repo_str in repos:
            owner, repo = repo_str.split("/", 1)
            repo_scores = self.scan_repo(owner, repo)
            all_repo_scores.append((repo_str, repo_scores))

        # Aggregate: max per skill across repos
        skill_max: dict[str, int] = {}
        skill_repos: dict[str, list[str]] = {}  # which repos contributed

        for repo_str, scores in all_repo_scores:
            for skill_id, score in scores.items():
                if score > skill_max.get(skill_id, 0):
                    skill_max[skill_id] = score
                if score > 0:
                    skill_repos.setdefault(skill_id, []).append(repo_str)

        signals = []
        num_repos = len(repos)
        for skill_id, score in skill_max.items():
            if score <= 0:
                continue
            found_in = skill_repos.get(skill_id, [])
            evidence = f"Found in {len(found_in)}/{num_repos} repos: {', '.join(found_in)}"
            signals.append({"skill_id": skill_id, "score": score, "evidence": evidence})

        return signals

    # ── Per-skill scoring helpers ────────────────────────────────────────────

    def _score_context_files(self, owner: str, repo: str) -> int:
        """cq-context: CLAUDE.md, .cursorrules, .github/copilot-instructions.md."""
        candidates = [
            "CLAUDE.md",
            ".claude/CLAUDE.md",
            ".cursorrules",
            ".cursor/rules",
            ".github/copilot-instructions.md",
        ]
        best = 0
        for path in candidates:
            content = self.client.get_file_content(owner, repo, path)
            if content is not None:
                best = max(best, _line_count_score(content))
        return best

    def _score_permission_gated(self, owner: str, repo: str) -> int:
        """tg-permission-gated: .claude/settings.json with permission config."""
        content = self.client.get_file_content(owner, repo, ".claude/settings.json")
        if content is None:
            return 0
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return 0
        # Look for permission-gating keys
        for key in ("permissions", "allowedTools", "blockedTools", "allow", "deny"):
            val = data.get(key)
            if val and (isinstance(val, list) and len(val) > 0 or isinstance(val, dict)):
                return 80
        # Present but no restrictions configured
        return 40

    def _score_prompt_dirs(self, owner: str, repo: str) -> int:
        """ks-patterns: prompts/ or .claude/commands/ directory."""
        best = 0
        for path in ("prompts", ".prompts", ".claude/commands"):
            listing = self.client.get_directory_listing(owner, repo, path)
            if listing is not None:
                file_count = sum(1 for e in listing if e.get("type") == "file")
                best = max(best, _file_count_score(file_count))
        return best

    def _score_mcp_config(self, owner: str, repo: str) -> int:
        """pm-advanced: .mcp.json or mcp.json with server definitions."""
        for path in (".mcp.json", "mcp.json"):
            content = self.client.get_file_content(owner, repo, path)
            if content is None:
                continue
            try:
                data = json.loads(content)
            except (json.JSONDecodeError, ValueError):
                return 70  # present but unparseable — still counts
            servers = data.get("mcpServers") or data.get("servers") or {}
            if isinstance(servers, dict) and len(servers) > 1:
                return 100
            return 70
        return 0

    def _score_ai_documentation(self, owner: str, repo: str) -> int:
        """ks-documentation: AI ADRs, AI usage guides, CONTRIBUTING.md mentions."""
        best = 0

        # Check docs/adr/ for AI-related ADRs
        adr_listing = self.client.get_directory_listing(owner, repo, "docs/adr")
        if adr_listing is not None:
            ai_adrs = [
                e
                for e in adr_listing
                if e.get("type") == "file" and _AI_DOC_KEYWORDS.search(e.get("name", ""))
            ]
            if ai_adrs:
                best = max(best, 80)

        # Check docs/ for AI-named files
        docs_listing = self.client.get_directory_listing(owner, repo, "docs")
        if docs_listing is not None:
            ai_docs = [
                e
                for e in docs_listing
                if e.get("type") == "file" and _AI_DOC_KEYWORDS.search(e.get("name", ""))
            ]
            if ai_docs:
                best = max(best, 70)

        # CONTRIBUTING.md AI mentions
        contributing = self.client.get_file_content(owner, repo, "CONTRIBUTING.md")
        if contributing and _AI_DOC_KEYWORDS.search(contributing):
            best = max(best, 60)

        return best

    def _score_workflows(self, owner: str, repo: str) -> dict[str, int]:
        """tg-security-gates, sdlc-testing, ks-workflows from GitHub Actions."""
        workflow_contents = self.client.get_workflow_files(owner, repo)
        if not workflow_contents:
            return {"tg-security-gates": 0, "sdlc-testing": 0, "ks-workflows": 0}

        combined = "\n".join(workflow_contents)

        # Security gates
        security_matches = set(m.group(0).lower() for m in _SECURITY_SCANNERS.finditer(combined))
        if len(security_matches) >= 2:
            security_score = 80
        elif security_matches:
            security_score = 60
        else:
            security_score = 0

        # AI testing
        testing_score = 70 if _AI_TEST_PATTERNS.search(combined) else 0

        # AI agent workflows
        workflow_score = 80 if _AI_WORKFLOW_PATTERNS.search(combined) else 0

        return {
            "tg-security-gates": security_score,
            "sdlc-testing": testing_score,
            "ks-workflows": workflow_score,
        }
