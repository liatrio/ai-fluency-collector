from __future__ import annotations

import base64

import requests


class GitHubAuthError(Exception):
    pass


class GitHubAccessError(Exception):
    pass


class GitHubServerError(Exception):
    pass


def _check_server_error(resp: requests.Response, context: str = "") -> None:
    if 500 <= resp.status_code < 600:
        msg = f"GitHub server error ({resp.status_code})"
        if context:
            msg += f" while {context}"
        msg += ". Try again later."
        raise GitHubServerError(msg)


class GitHubClient:
    """Client for GitHub REST API v3."""

    BASE_URL = "https://api.github.com"

    def __init__(self, token: str) -> None:
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"
        self.session.headers["Accept"] = "application/vnd.github+json"
        self.session.headers["X-GitHub-Api-Version"] = "2022-11-28"

    def _url(self, path: str) -> str:
        return f"{self.BASE_URL}{path}"

    def _check_auth(self, resp: requests.Response, context: str) -> None:
        if resp.status_code == 401:
            raise GitHubAuthError(
                "GitHub authentication failed. "
                "Check that GITHUB_TOKEN is valid and has the required scopes."
            )
        if resp.status_code == 403:
            raise GitHubAccessError(
                f"Access denied while {context}. Check that GITHUB_TOKEN has the required scopes."
            )

    def validate_token(self) -> None:
        """Verify the token by calling GET /user."""
        try:
            resp = self.session.get(self._url("/user"))
        except (requests.ConnectionError, requests.Timeout) as e:
            raise GitHubAuthError(
                "Could not connect to api.github.com. Check your network connection."
            ) from e
        _check_server_error(resp, "validating token")
        if resp.status_code == 401:
            raise GitHubAuthError(
                "GitHub authentication failed. "
                "Check that GITHUB_TOKEN is valid and has the required scopes."
            )
        resp.raise_for_status()

    def get_file(self, owner: str, repo: str, path: str) -> dict | None:
        """Fetch file metadata + base64 content from the Contents API.

        Returns the response dict, or None if the file does not exist.
        """
        url = self._url(f"/repos/{owner}/{repo}/contents/{path}")
        resp = self.session.get(url)
        _check_server_error(resp, f"fetching '{path}' from {owner}/{repo}")
        self._check_auth(resp, f"fetching '{path}'")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        # Only return file objects, not directory listings
        if isinstance(data, dict) and data.get("type") == "file":
            return data
        return None

    def get_file_content(self, owner: str, repo: str, path: str) -> str | None:
        """Fetch and decode a file's text content. Returns None if not found."""
        data = self.get_file(owner, repo, path)
        if data is None:
            return None
        encoded = data.get("content", "")
        return base64.b64decode(encoded).decode("utf-8", errors="replace")

    def get_directory_listing(self, owner: str, repo: str, path: str) -> list[dict] | None:
        """List directory contents. Returns None if the path does not exist."""
        url = self._url(f"/repos/{owner}/{repo}/contents/{path}")
        resp = self.session.get(url)
        _check_server_error(resp, f"listing '{path}' in {owner}/{repo}")
        self._check_auth(resp, f"listing '{path}'")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        return None

    def get_workflow_files(self, owner: str, repo: str) -> list[str]:
        """Return decoded content of every file in .github/workflows/."""
        entries = self.get_directory_listing(owner, repo, ".github/workflows")
        if not entries:
            return []
        contents = []
        for entry in entries:
            if entry.get("type") == "file" and entry.get("name", "").endswith((".yml", ".yaml")):
                content = self.get_file_content(owner, repo, entry["path"])
                if content:
                    contents.append(content)
        return contents

    def search_pull_requests(self, query: str) -> list[dict]:
        """Search for pull requests using the Search Issues API.

        GitHub treats PRs as issues; filter by is:pr in query.
        Paginates automatically.
        """
        url = self._url("/search/issues")
        results: list[dict] = []
        page = 1
        while True:
            resp = self.session.get(
                url,
                params={"q": query, "per_page": 100, "page": page},
            )
            _check_server_error(resp, "searching pull requests")
            self._check_auth(resp, "searching pull requests")
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])
            results.extend(items)
            if len(results) >= data.get("total_count", 0) or not items:
                break
            page += 1
        return results

    def get_pr_reviews(self, owner: str, repo: str, number: int) -> list[dict]:
        """Get all reviews for a pull request."""
        url = self._url(f"/repos/{owner}/{repo}/pulls/{number}/reviews")
        results: list[dict] = []
        page = 1
        while True:
            resp = self.session.get(url, params={"per_page": 100, "page": page})
            _check_server_error(resp, f"fetching reviews for PR #{number}")
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            items = resp.json()
            if not items:
                break
            results.extend(items)
            page += 1
        return results

    def get_pr_review_comments(self, owner: str, repo: str, number: int) -> list[dict]:
        """Get all inline review comments for a pull request."""
        url = self._url(f"/repos/{owner}/{repo}/pulls/{number}/comments")
        results: list[dict] = []
        page = 1
        while True:
            resp = self.session.get(url, params={"per_page": 100, "page": page})
            _check_server_error(resp, f"fetching review comments for PR #{number}")
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            items = resp.json()
            if not items:
                break
            results.extend(items)
            page += 1
        return results

    def get_pr_files(self, owner: str, repo: str, number: int) -> list[dict]:
        """Get the list of files changed in a pull request."""
        url = self._url(f"/repos/{owner}/{repo}/pulls/{number}/files")
        results: list[dict] = []
        page = 1
        while True:
            resp = self.session.get(url, params={"per_page": 100, "page": page})
            _check_server_error(resp, f"fetching files for PR #{number}")
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            items = resp.json()
            if not items:
                break
            results.extend(items)
            page += 1
        return results

    def get_pr_commits(self, owner: str, repo: str, number: int) -> list[dict]:
        """Get all commits in a pull request."""
        url = self._url(f"/repos/{owner}/{repo}/pulls/{number}/commits")
        results: list[dict] = []
        page = 1
        while True:
            resp = self.session.get(url, params={"per_page": 100, "page": page})
            _check_server_error(resp, f"fetching commits for PR #{number}")
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            items = resp.json()
            if not items:
                break
            results.extend(items)
            page += 1
        return results
