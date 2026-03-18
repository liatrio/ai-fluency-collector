from __future__ import annotations

from urllib.parse import quote

import requests


class GitLabAuthError(Exception):
    pass


class GitLabAccessError(Exception):
    pass


class GitLabUserNotFoundError(Exception):
    pass


class GitLabClient:
    """Client for GitLab REST API v4."""

    def __init__(self, token: str, base_url: str = "https://gitlab.com") -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers["PRIVATE-TOKEN"] = token

    def _api_url(self, path: str) -> str:
        return f"{self.base_url}/api/v4{path}"

    def _encode_project(self, project_path: str) -> str:
        return quote(project_path, safe="")

    def validate_token(self) -> None:
        """Verify the token is valid by calling GET /user.

        Raises GitLabAuthError on 401 or connection errors.
        """
        try:
            resp = self.session.get(self._api_url("/user"))
        except (requests.ConnectionError, requests.Timeout) as e:
            raise GitLabAuthError(
                f"Could not connect to {self.base_url}. Check the gitlab_url in your config."
            ) from e
        if resp.status_code == 401:
            raise GitLabAuthError(
                f"GitLab authentication failed at {self.base_url}. "
                "Check that GITLAB_TOKEN is valid and has read_api scope."
            )
        resp.raise_for_status()

    def check_file_exists(self, project_path: str, file_path: str, ref: str = "HEAD") -> bool:
        """Check if a file exists in a project on a given ref.

        Uses HEAD on the Repository Files API.
        """
        encoded_project = self._encode_project(project_path)
        encoded_file = quote(file_path, safe="")
        url = self._api_url(f"/projects/{encoded_project}/repository/files/{encoded_file}")
        resp = self.session.head(url, params={"ref": ref})
        if resp.status_code == 200:
            return True
        if resp.status_code == 404:
            return False
        if resp.status_code == 401:
            raise GitLabAuthError(
                "GitLab authentication failed. "
                "Check that GITLAB_TOKEN is valid and has read_api scope."
            )
        if resp.status_code == 403:
            raise GitLabAccessError(
                f"Access denied to project '{project_path}'. "
                "Check that the token has access to this project."
            )
        resp.raise_for_status()
        return False

    def check_directory_exists(self, project_path: str, dir_path: str, ref: str = "HEAD") -> bool:
        """Check if a directory exists in a project using the Repository Tree API."""
        encoded_project = self._encode_project(project_path)
        url = self._api_url(f"/projects/{encoded_project}/repository/tree")
        resp = self.session.get(url, params={"path": dir_path, "ref": ref, "per_page": 1})
        if resp.status_code == 200:
            items = resp.json()
            return len(items) > 0
        if resp.status_code == 404:
            return False
        if resp.status_code == 401:
            raise GitLabAuthError(
                "GitLab authentication failed. "
                "Check that GITLAB_TOKEN is valid and has read_api scope."
            )
        if resp.status_code == 403:
            raise GitLabAccessError(
                f"Access denied to project '{project_path}'. "
                "Check that the token has access to this project."
            )
        resp.raise_for_status()
        return False

    def get_file_content(self, project_path: str, file_path: str, ref: str = "HEAD") -> str | None:
        """Fetch a file's content from a project on a given ref.

        Returns None if the file does not exist.
        """
        encoded_project = self._encode_project(project_path)
        encoded_file = quote(file_path, safe="")
        url = self._api_url(f"/projects/{encoded_project}/repository/files/{encoded_file}/raw")
        resp = self.session.get(url, params={"ref": ref})
        if resp.status_code == 200:
            return resp.text
        if resp.status_code == 404:
            return None
        if resp.status_code == 401:
            raise GitLabAuthError(
                "GitLab authentication failed. "
                "Check that GITLAB_TOKEN is valid and has read_api scope."
            )
        if resp.status_code == 403:
            raise GitLabAccessError(
                f"Access denied to project '{project_path}'. "
                "Check that the token has access to this project."
            )
        resp.raise_for_status()
        return None

    def get_branches(self, project_path: str) -> list[dict]:
        """Get all branches for a project.

        Returns list of branch dicts with 'name', 'default', and
        'commit.committed_date' fields.
        """
        encoded_project = self._encode_project(project_path)
        url = self._api_url(f"/projects/{encoded_project}/repository/branches")
        results: list[dict] = []
        page = 1
        while True:
            resp = self.session.get(url, params={"per_page": 100, "page": page})
            if resp.status_code == 404:
                return []
            if resp.status_code == 401:
                raise GitLabAuthError(
                    "GitLab authentication failed. "
                    "Check that GITLAB_TOKEN is valid and has read_api scope."
                )
            if resp.status_code == 403:
                raise GitLabAccessError(
                    f"Access denied to project '{project_path}'. "
                    "Check that the token has access to this project."
                )
            resp.raise_for_status()
            items = resp.json()
            if not items:
                break
            results.extend(items)
            page += 1
        return results

    def get_user(self, username: str) -> dict:
        """Look up a GitLab user by username.

        Returns the user dict. Raises GitLabUserNotFoundError if not found.
        """
        url = self._api_url("/users")
        resp = self.session.get(url, params={"username": username})
        resp.raise_for_status()
        users = resp.json()
        if not users:
            raise GitLabUserNotFoundError(
                f"GitLab user '{username}' not found. Check the username in your config."
            )
        return users[0]

    def get_user_projects(self, user_id: int) -> list[dict]:
        """Get all projects owned by a user."""
        url = self._api_url(f"/users/{user_id}/projects")
        results: list[dict] = []
        page = 1
        while True:
            resp = self.session.get(url, params={"per_page": 100, "page": page, "owned": True})
            resp.raise_for_status()
            items = resp.json()
            if not items:
                break
            results.extend(items)
            page += 1
        return results

    def get_user_events(self, user_id: int, action: str = "pushed") -> list[dict]:
        """Get a user's contribution events filtered by action type."""
        url = self._api_url(f"/users/{user_id}/events")
        results: list[dict] = []
        page = 1
        while True:
            resp = self.session.get(
                url,
                params={"action": action, "per_page": 100, "page": page},
            )
            resp.raise_for_status()
            items = resp.json()
            if not items:
                break
            results.extend(items)
            page += 1
        return results

    def get_project_commits(
        self,
        project_id: int,
        author: str | None = None,
        since: str | None = None,
    ) -> list[dict]:
        """Get commits from a project, optionally filtered by author and date.

        Args:
            project_id: The numeric project ID.
            author: Filter commits by author username or email.
            since: ISO 8601 date string to filter commits after.
        """
        url = self._api_url(f"/projects/{project_id}/repository/commits")
        params: dict = {"per_page": 100}
        if author:
            params["author"] = author
        if since:
            params["since"] = since
        results: list[dict] = []
        page = 1
        while True:
            params["page"] = page
            resp = self.session.get(url, params=params)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            items = resp.json()
            if not items:
                break
            results.extend(items)
            page += 1
        return results
