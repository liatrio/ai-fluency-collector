from __future__ import annotations

from urllib.parse import quote

import requests


class GitLabAuthError(Exception):
    pass


class GitLabAccessError(Exception):
    pass


class GitLabUserNotFoundError(Exception):
    pass


class GitLabServerError(Exception):
    pass


def _check_server_error(resp: requests.Response, context: str = "") -> None:
    """Raise GitLabServerError on 5xx responses."""
    if 500 <= resp.status_code < 600:
        msg = f"GitLab server error ({resp.status_code})"
        if context:
            msg += f" while {context}"
        msg += ". The GitLab instance may be down or experiencing issues. Try again later."
        raise GitLabServerError(msg)


class GitLabClient:
    """Client for GitLab REST API v4."""

    def __init__(self, token: str, base_url: str = "https://gitlab.com") -> None:
        if not base_url.startswith(("http://", "https://")):
            base_url = f"https://{base_url}"
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
        except (requests.ConnectionError, requests.Timeout, requests.exceptions.MissingSchema) as e:
            raise GitLabAuthError(
                f"Could not connect to {self.base_url}. Check the gitlab_url in your config."
            ) from e
        _check_server_error(resp, "validating token")
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
        _check_server_error(resp, f"checking file '{file_path}' in '{project_path}'")
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
        _check_server_error(resp, f"checking directory '{dir_path}' in '{project_path}'")
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
        _check_server_error(resp, f"fetching '{file_path}' from '{project_path}'")
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
        Raises GitLabAccessError if the project is not found.
        """
        encoded_project = self._encode_project(project_path)
        url = self._api_url(f"/projects/{encoded_project}/repository/branches")
        results: list[dict] = []
        page = 1
        while True:
            resp = self.session.get(url, params={"per_page": 100, "page": page})
            _check_server_error(resp, f"listing branches for '{project_path}'")
            if resp.status_code == 404:
                raise GitLabAccessError(
                    f"Project '{project_path}' not found. "
                    "Check the project path — it should match the URL after your GitLab domain "
                    "(e.g., 'eng/genomics/vms' not 'natera.com/eng/genomics/vms')."
                )
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
        _check_server_error(resp, f"looking up user '{username}'")
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
            _check_server_error(resp, "listing user projects")
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
            _check_server_error(resp, "listing user events")
            resp.raise_for_status()
            items = resp.json()
            if not items:
                break
            results.extend(items)
            page += 1
        return results

    def search_merge_requests(
        self,
        author_username: str | None = None,
        reviewer_username: str | None = None,
        state: str = "merged",
        updated_after: str | None = None,
        updated_before: str | None = None,
    ) -> list[dict]:
        """Search merge requests globally with scope=all.

        Args:
            author_username: Filter by MR author username.
            reviewer_username: Filter by reviewer username (GitLab 13.7+).
            state: MR state ('merged', 'opened', 'closed', 'all').
            updated_after: ISO date string to filter MRs updated after.
            updated_before: ISO date string to filter MRs updated before.
        """
        url = self._api_url("/merge_requests")
        params: dict = {"scope": "all", "state": state, "per_page": 100}
        if author_username:
            params["author_username"] = author_username
        if reviewer_username:
            params["reviewer_username"] = reviewer_username
        if updated_after:
            params["updated_after"] = updated_after
        if updated_before:
            params["updated_before"] = updated_before
        results: list[dict] = []
        page = 1
        while True:
            params["page"] = page
            resp = self.session.get(url, params=params)
            _check_server_error(resp, "searching merge requests")
            resp.raise_for_status()
            items = resp.json()
            if not items:
                break
            results.extend(items)
            page += 1
        return results

    def get_mr_commits(self, project_id: int, mr_iid: int) -> list[dict]:
        """Get all commits for a merge request."""
        url = self._api_url(f"/projects/{project_id}/merge_requests/{mr_iid}/commits")
        results: list[dict] = []
        page = 1
        while True:
            resp = self.session.get(url, params={"per_page": 100, "page": page})
            _check_server_error(resp, f"fetching commits for MR !{mr_iid}")
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            items = resp.json()
            if not items:
                break
            results.extend(items)
            page += 1
        return results

    def get_mr_notes(self, project_id: int, mr_iid: int) -> list[dict]:
        """Get all notes for a merge request. Caller filters system notes."""
        url = self._api_url(f"/projects/{project_id}/merge_requests/{mr_iid}/notes")
        results: list[dict] = []
        page = 1
        while True:
            resp = self.session.get(url, params={"per_page": 100, "page": page})
            _check_server_error(resp, f"fetching notes for MR !{mr_iid}")
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            items = resp.json()
            if not items:
                break
            results.extend(items)
            page += 1
        return results

    def get_mr_discussions(self, project_id: int, mr_iid: int) -> list[dict]:
        """Get all discussion threads for a merge request."""
        url = self._api_url(f"/projects/{project_id}/merge_requests/{mr_iid}/discussions")
        results: list[dict] = []
        page = 1
        while True:
            resp = self.session.get(url, params={"per_page": 100, "page": page})
            _check_server_error(resp, f"fetching discussions for MR !{mr_iid}")
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            items = resp.json()
            if not items:
                break
            results.extend(items)
            page += 1
        return results

    def get_mr_approvals(self, project_id: int, mr_iid: int) -> dict:
        """Get approval state for a merge request."""
        url = self._api_url(f"/projects/{project_id}/merge_requests/{mr_iid}/approvals")
        resp = self.session.get(url)
        _check_server_error(resp, f"fetching approvals for MR !{mr_iid}")
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        return resp.json()

    def get_mr_diffs(self, project_id: int, mr_iid: int) -> list[dict]:
        """Get changed files for a merge request."""
        url = self._api_url(f"/projects/{project_id}/merge_requests/{mr_iid}/diffs")
        results: list[dict] = []
        page = 1
        while True:
            resp = self.session.get(url, params={"per_page": 100, "page": page})
            _check_server_error(resp, f"fetching diffs for MR !{mr_iid}")
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            items = resp.json()
            if not items:
                break
            results.extend(items)
            page += 1
        return results

    def get_pipelines(
        self,
        project_path: str,
        updated_after: str | None = None,
        updated_before: str | None = None,
    ) -> list[dict]:
        """Get pipelines for a project, optionally filtered by date range.

        Returns list of pipeline dicts with 'id', 'sha', 'status', 'created_at'.
        """
        encoded_project = self._encode_project(project_path)
        url = self._api_url(f"/projects/{encoded_project}/pipelines")
        params: dict = {"per_page": 100}
        if updated_after:
            params["updated_after"] = updated_after
        if updated_before:
            params["updated_before"] = updated_before
        results: list[dict] = []
        page = 1
        while True:
            params["page"] = page
            resp = self.session.get(url, params=params)
            _check_server_error(resp, f"listing pipelines for '{project_path}'")
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
            _check_server_error(resp, "listing project commits")
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            items = resp.json()
            if not items:
                break
            results.extend(items)
            page += 1
        return results
