from __future__ import annotations

from urllib.parse import quote

import requests


class GitLabAuthError(Exception):
    pass


class GitLabAccessError(Exception):
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

        Raises GitLabAuthError on 401.
        """
        resp = self.session.get(self._api_url("/user"))
        if resp.status_code == 401:
            raise GitLabAuthError(
                "GitLab authentication failed. "
                "Check that GITLAB_TOKEN is valid and has read_api scope."
            )
        resp.raise_for_status()

    def check_file_exists(self, project_path: str, file_path: str) -> bool:
        """Check if a file exists in a project's default branch.

        Uses HEAD on the Repository Files API.
        """
        encoded_project = self._encode_project(project_path)
        encoded_file = quote(file_path, safe="")
        url = self._api_url(f"/projects/{encoded_project}/repository/files/{encoded_file}")
        resp = self.session.head(url, params={"ref": "HEAD"})
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

    def check_directory_exists(self, project_path: str, dir_path: str) -> bool:
        """Check if a directory exists in a project using the Repository Tree API."""
        encoded_project = self._encode_project(project_path)
        url = self._api_url(f"/projects/{encoded_project}/repository/tree")
        resp = self.session.get(url, params={"path": dir_path, "ref": "HEAD", "per_page": 1})
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

    def get_file_content(self, project_path: str, file_path: str) -> str | None:
        """Fetch a file's content from a project's default branch.

        Returns None if the file does not exist.
        """
        encoded_project = self._encode_project(project_path)
        encoded_file = quote(file_path, safe="")
        url = self._api_url(f"/projects/{encoded_project}/repository/files/{encoded_file}/raw")
        resp = self.session.get(url, params={"ref": "HEAD"})
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
