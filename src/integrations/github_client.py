"""
GitHub Client for Sentience v3.0
Full-featured GitHub integration with OAuth, PAT, repos, PRs, and issues.
"""

import base64
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union

import httpx

from .oauth_manager import OAuthManager, OAuthProvider, OAuthError

logger = logging.getLogger(__name__)


GITHUB_SCOPES = [
    "repo",
    "repo:status",
    "repo_deployment",
    "public_repo",
    "repo:invite",
    "read:org",
    "write:org",
    "read:packages",
    "write:packages",
    "delete:packages",
    "workflow",
    "read:discussion",
    "write:discussion",
    "user",
    "user:email",
    "user:follow",
]


class GitHubState(Enum):
    """Issue/PR states."""
    OPEN = "open"
    CLOSED = "closed"
    ALL = "all"


class GitHubMergeState(Enum):
    """Merge states for PRs."""
    MERGE = "merge"
    SQUASH = "squash"
    REBASE = "rebase"


class GitHubSort(Enum):
    """Sort options."""
    CREATED = "created"
    UPDATED = "updated"
    COMMENTS = "comments"


class GitHubDirection(Enum):
    """Sort direction."""
    ASC = "asc"
    DESC = "desc"


@dataclass
class GitHubUser:
    """GitHub user."""
    id: int
    login: str
    avatar_url: str
    html_url: str
    name: Optional[str] = None
    email: Optional[str] = None
    bio: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    blog: Optional[str] = None
    twitter_username: Optional[str] = None
    public_repos: int = 0
    public_gists: int = 0
    followers: int = 0
    following: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    type: str = "User"
    site_admin: bool = False

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "GitHubUser":
        """Create from API response."""
        def parse_date(date_str):
            if not date_str:
                return None
            try:
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except ValueError:
                return None

        return cls(
            id=data["id"],
            login=data["login"],
            avatar_url=data.get("avatar_url", ""),
            html_url=data.get("html_url", ""),
            name=data.get("name"),
            email=data.get("email"),
            bio=data.get("bio"),
            company=data.get("company"),
            location=data.get("location"),
            blog=data.get("blog"),
            twitter_username=data.get("twitter_username"),
            public_repos=data.get("public_repos", 0),
            public_gists=data.get("public_gists", 0),
            followers=data.get("followers", 0),
            following=data.get("following", 0),
            created_at=parse_date(data.get("created_at")),
            updated_at=parse_date(data.get("updated_at")),
            type=data.get("type", "User"),
            site_admin=data.get("site_admin", False),
        )


@dataclass
class GitHubRepository:
    """GitHub repository."""
    id: int
    name: str
    full_name: str
    owner: GitHubUser
    html_url: str
    description: Optional[str] = None
    private: bool = False
    fork: bool = False
    language: Optional[str] = None
    stargazers_count: int = 0
    watchers_count: int = 0
    forks_count: int = 0
    open_issues_count: int = 0
    default_branch: str = "main"
    topics: list[str] = field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    pushed_at: Optional[datetime] = None
    size: int = 0
    archived: bool = False
    disabled: bool = False
    license: Optional[str] = None
    homepage: Optional[str] = None
    has_issues: bool = True
    has_projects: bool = True
    has_wiki: bool = True
    has_pages: bool = False

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "GitHubRepository":
        """Create from API response."""
        def parse_date(date_str):
            if not date_str:
                return None
            try:
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except ValueError:
                return None

        owner = GitHubUser.from_api(data["owner"])
        license_name = None
        if data.get("license"):
            license_name = data["license"].get("spdx_id") or data["license"].get("name")

        return cls(
            id=data["id"],
            name=data["name"],
            full_name=data["full_name"],
            owner=owner,
            html_url=data.get("html_url", ""),
            description=data.get("description"),
            private=data.get("private", False),
            fork=data.get("fork", False),
            language=data.get("language"),
            stargazers_count=data.get("stargazers_count", 0),
            watchers_count=data.get("watchers_count", 0),
            forks_count=data.get("forks_count", 0),
            open_issues_count=data.get("open_issues_count", 0),
            default_branch=data.get("default_branch", "main"),
            topics=data.get("topics", []),
            created_at=parse_date(data.get("created_at")),
            updated_at=parse_date(data.get("updated_at")),
            pushed_at=parse_date(data.get("pushed_at")),
            size=data.get("size", 0),
            archived=data.get("archived", False),
            disabled=data.get("disabled", False),
            license=license_name,
            homepage=data.get("homepage"),
            has_issues=data.get("has_issues", True),
            has_projects=data.get("has_projects", True),
            has_wiki=data.get("has_wiki", True),
            has_pages=data.get("has_pages", False),
        )


@dataclass
class GitHubIssue:
    """GitHub issue."""
    id: int
    number: int
    title: str
    state: GitHubState
    html_url: str
    user: Optional[GitHubUser] = None
    body: Optional[str] = None
    labels: list[str] = field(default_factory=list)
    assignees: list[GitHubUser] = field(default_factory=list)
    milestone: Optional[str] = None
    comments: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    closed_by: Optional[GitHubUser] = None
    pull_request: Optional[dict[str, Any]] = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "GitHubIssue":
        """Create from API response."""
        def parse_date(date_str):
            if not date_str:
                return None
            try:
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except ValueError:
                return None

        user = GitHubUser.from_api(data["user"]) if data.get("user") else None

        labels = [l.get("name", "") for l in data.get("labels", [])]
        assignees = [GitHubUser.from_api(a) for a in data.get("assignees", [])]

        closed_by = None
        if data.get("closed_by"):
            closed_by = GitHubUser.from_api(data["closed_by"])

        milestone = None
        if data.get("milestone"):
            milestone = data["milestone"].get("title")

        return cls(
            id=data["id"],
            number=data["number"],
            title=data.get("title", ""),
            state=GitHubState(data.get("state", "open")),
            html_url=data.get("html_url", ""),
            user=user,
            body=data.get("body"),
            labels=labels,
            assignees=assignees,
            milestone=milestone,
            comments=data.get("comments", 0),
            created_at=parse_date(data.get("created_at")),
            updated_at=parse_date(data.get("updated_at")),
            closed_at=parse_date(data.get("closed_at")),
            closed_by=closed_by,
            pull_request=data.get("pull_request"),
        )

    @property
    def is_pr(self) -> bool:
        """Check if this is a pull request."""
        return self.pull_request is not None


@dataclass
class GitHubPullRequest:
    """GitHub pull request."""
    id: int
    number: int
    title: str
    state: GitHubState
    html_url: str
    user: Optional[GitHubUser] = None
    body: Optional[str] = None
    labels: list[str] = field(default_factory=list)
    assignees: list[GitHubUser] = field(default_factory=list)
    head: dict[str, Any] = field(default_factory=dict)
    base: dict[str, Any] = field(default_factory=dict)
    merged: bool = False
    mergeable: Optional[bool] = None
    mergeable_state: Optional[str] = None
    merged_at: Optional[datetime] = None
    merged_by: Optional[GitHubUser] = None
    draft: bool = False
    comments: int = 0
    review_comments: int = 0
    commits: int = 0
    additions: int = 0
    deletions: int = 0
    changed_files: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "GitHubPullRequest":
        """Create from API response."""
        def parse_date(date_str):
            if not date_str:
                return None
            try:
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except ValueError:
                return None

        user = GitHubUser.from_api(data["user"]) if data.get("user") else None
        labels = [l.get("name", "") for l in data.get("labels", [])]
        assignees = [GitHubUser.from_api(a) for a in data.get("assignees", [])]

        merged_by = None
        if data.get("merged_by"):
            merged_by = GitHubUser.from_api(data["merged_by"])

        return cls(
            id=data["id"],
            number=data["number"],
            title=data.get("title", ""),
            state=GitHubState(data.get("state", "open")),
            html_url=data.get("html_url", ""),
            user=user,
            body=data.get("body"),
            labels=labels,
            assignees=assignees,
            head=data.get("head", {}),
            base=data.get("base", {}),
            merged=data.get("merged", False),
            mergeable=data.get("mergeable"),
            mergeable_state=data.get("mergeable_state"),
            merged_at=parse_date(data.get("merged_at")),
            merged_by=merged_by,
            draft=data.get("draft", False),
            comments=data.get("comments", 0),
            review_comments=data.get("review_comments", 0),
            commits=data.get("commits", 0),
            additions=data.get("additions", 0),
            deletions=data.get("deletions", 0),
            changed_files=data.get("changed_files", 0),
            created_at=parse_date(data.get("created_at")),
            updated_at=parse_date(data.get("updated_at")),
            closed_at=parse_date(data.get("closed_at")),
        )


@dataclass
class GitHubComment:
    """GitHub comment."""
    id: int
    body: str
    user: Optional[GitHubUser] = None
    html_url: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "GitHubComment":
        """Create from API response."""
        def parse_date(date_str):
            if not date_str:
                return None
            try:
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except ValueError:
                return None

        user = GitHubUser.from_api(data["user"]) if data.get("user") else None

        return cls(
            id=data["id"],
            body=data.get("body", ""),
            user=user,
            html_url=data.get("html_url"),
            created_at=parse_date(data.get("created_at")),
            updated_at=parse_date(data.get("updated_at")),
        )


@dataclass
class GitHubWorkflowRun:
    """GitHub Actions workflow run."""
    id: int
    name: str
    status: str
    conclusion: Optional[str] = None
    html_url: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    head_branch: Optional[str] = None
    head_sha: Optional[str] = None
    event: Optional[str] = None
    workflow_id: int = 0

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "GitHubWorkflowRun":
        """Create from API response."""
        def parse_date(date_str):
            if not date_str:
                return None
            try:
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except ValueError:
                return None

        return cls(
            id=data["id"],
            name=data.get("name", ""),
            status=data.get("status", ""),
            conclusion=data.get("conclusion"),
            html_url=data.get("html_url", ""),
            created_at=parse_date(data.get("created_at")),
            updated_at=parse_date(data.get("updated_at")),
            head_branch=data.get("head_branch"),
            head_sha=data.get("head_sha"),
            event=data.get("event"),
            workflow_id=data.get("workflow_id", 0),
        )


@dataclass
class GitHubContent:
    """GitHub file content."""
    name: str
    path: str
    sha: str
    type: str  # file, dir, symlink
    html_url: str
    download_url: Optional[str] = None
    content: Optional[str] = None  # Base64 encoded for files
    encoding: Optional[str] = None
    size: int = 0

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "GitHubContent":
        """Create from API response."""
        return cls(
            name=data.get("name", ""),
            path=data.get("path", ""),
            sha=data.get("sha", ""),
            type=data.get("type", "file"),
            html_url=data.get("html_url", ""),
            download_url=data.get("download_url"),
            content=data.get("content"),
            encoding=data.get("encoding"),
            size=data.get("size", 0),
        )

    def get_decoded_content(self) -> Optional[str]:
        """Decode base64 content."""
        if self.content and self.encoding == "base64":
            return base64.b64decode(self.content).decode("utf-8")
        return None


class GitHubClient:
    """
    Full-featured GitHub client with:
    - OAuth + PAT authentication
    - Repository operations
    - PR/Issue management
    - Actions triggers
    """

    BASE_URL = "https://api.github.com"

    def __init__(
        self,
        oauth_manager: Optional[OAuthManager] = None,
        personal_access_token: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        self.oauth_manager = oauth_manager
        self.personal_access_token = personal_access_token
        self.user_id = user_id
        self._http_client = httpx.AsyncClient(timeout=60.0)

    async def _get_headers(self) -> dict[str, str]:
        """Get authenticated headers."""
        if self.personal_access_token:
            token = self.personal_access_token
        elif self.oauth_manager:
            token_data = await self.oauth_manager.get_or_refresh_token(
                OAuthProvider.GITHUB, self.user_id
            )
            token = token_data.access_token
        else:
            raise GitHubError("No authentication configured")

        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> dict[str, Any]:
        """Make authenticated request to GitHub API."""
        headers = await self._get_headers()
        headers.update(kwargs.pop("headers", {}))
        url = f"{self.BASE_URL}{path}"

        response = await self._http_client.request(
            method, url, headers=headers, **kwargs
        )

        if response.status_code == 401:
            if self.oauth_manager:
                token_data = await self.oauth_manager.get_or_refresh_token(
                    OAuthProvider.GITHUB, self.user_id
                )
                headers["Authorization"] = f"Bearer {token_data.access_token}"
                response = await self._http_client.request(
                    method, url, headers=headers, **kwargs
                )

        if response.status_code == 204:
            return {}

        if response.status_code >= 400:
            try:
                error = response.json().get("message", response.text)
            except Exception:
                error = response.text
            raise GitHubError(f"GitHub API error: {error}")

        return response.json()

    # ==================== User Operations ====================

    async def get_user(self, username: Optional[str] = None) -> GitHubUser:
        """Get a user (or authenticated user if no username)."""
        if username:
            data = await self._request("GET", f"/users/{username}")
        else:
            data = await self._request("GET", "/user")
        return GitHubUser.from_api(data)

    async def get_user_repos(
        self,
        username: Optional[str] = None,
        type: str = "owner",
        sort: str = "created",
        per_page: int = 100,
    ) -> list[GitHubRepository]:
        """Get user repositories."""
        params = {"type": type, "sort": sort, "per_page": per_page}

        if username:
            data = await self._request("GET", f"/users/{username}/repos", params=params)
        else:
            data = await self._request("GET", "/user/repos", params=params)

        return [GitHubRepository.from_api(r) for r in data]

    # ==================== Repository Operations ====================

    async def get_repo(self, owner: str, repo: str) -> GitHubRepository:
        """Get a repository."""
        data = await self._request("GET", f"/repos/{owner}/{repo}")
        return GitHubRepository.from_api(data)

    async def list_repos(
        self,
        visibility: str = "all",
        affiliation: str = "owner,collaborator,organization_member",
        sort: str = "created",
        per_page: int = 100,
    ) -> list[GitHubRepository]:
        """List repositories for authenticated user."""
        data = await self._request(
            "GET",
            "/user/repos",
            params={"visibility": visibility, "affiliation": affiliation, "sort": sort, "per_page": per_page},
        )
        return [GitHubRepository.from_api(r) for r in data]

    async def create_repo(
        self,
        name: str,
        description: Optional[str] = None,
        private: bool = False,
        auto_init: bool = False,
        gitignore_template: Optional[str] = None,
        license_template: Optional[str] = None,
        homepage: Optional[str] = None,
        has_issues: bool = True,
        has_projects: bool = True,
        has_wiki: bool = True,
    ) -> GitHubRepository:
        """Create a new repository."""
        body = {
            "name": name,
            "private": private,
            "auto_init": auto_init,
            "has_issues": has_issues,
            "has_projects": has_projects,
            "has_wiki": has_wiki,
        }

        if description:
            body["description"] = description
        if gitignore_template:
            body["gitignore_template"] = gitignore_template
        if license_template:
            body["license_template"] = license_template
        if homepage:
            body["homepage"] = homepage

        data = await self._request("POST", "/user/repos", json=body)
        repo = GitHubRepository.from_api(data)
        logger.info(f"Created repository {repo.full_name}")
        return repo

    async def delete_repo(self, owner: str, repo: str) -> bool:
        """Delete a repository."""
        await self._request("DELETE", f"/repos/{owner}/{repo}")
        logger.info(f"Deleted repository {owner}/{repo}")
        return True

    async def fork_repo(
        self,
        owner: str,
        repo: str,
        organization: Optional[str] = None,
    ) -> GitHubRepository:
        """Fork a repository."""
        body = {}
        if organization:
            body["organization"] = organization

        data = await self._request("POST", f"/repos/{owner}/{repo}/forks", json=body if body else None)
        return GitHubRepository.from_api(data)

    # ==================== Content Operations ====================

    async def get_content(
        self,
        owner: str,
        repo: str,
        path: str = "",
        ref: Optional[str] = None,
    ) -> Union[GitHubContent, list[GitHubContent]]:
        """Get file or directory contents."""
        url = f"/repos/{owner}/{repo}/contents/{path}"
        params = {}
        if ref:
            params["ref"] = ref

        data = await self._request("GET", url, params=params)

        if isinstance(data, list):
            return [GitHubContent.from_api(c) for c in data]
        return GitHubContent.from_api(data)

    async def create_file(
        self,
        owner: str,
        repo: str,
        path: str,
        message: str,
        content: Union[str, bytes],
        branch: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a file in repository."""
        if isinstance(content, str):
            content = content.encode("utf-8")

        body = {
            "message": message,
            "content": base64.b64encode(content).decode("utf-8"),
        }

        if branch:
            body["branch"] = branch

        data = await self._request("PUT", f"/repos/{owner}/{repo}/contents/{path}", json=body)
        logger.info(f"Created file {path} in {owner}/{repo}")
        return data

    async def update_file(
        self,
        owner: str,
        repo: str,
        path: str,
        message: str,
        content: Union[str, bytes],
        sha: str,
        branch: Optional[str] = None,
    ) -> dict[str, Any]:
        """Update a file in repository."""
        if isinstance(content, str):
            content = content.encode("utf-8")

        body = {
            "message": message,
            "content": base64.b64encode(content).decode("utf-8"),
            "sha": sha,
        }

        if branch:
            body["branch"] = branch

        data = await self._request("PUT", f"/repos/{owner}/{repo}/contents/{path}", json=body)
        logger.info(f"Updated file {path} in {owner}/{repo}")
        return data

    async def delete_file(
        self,
        owner: str,
        repo: str,
        path: str,
        message: str,
        sha: str,
        branch: Optional[str] = None,
    ) -> dict[str, Any]:
        """Delete a file from repository."""
        body = {"message": message, "sha": sha}

        if branch:
            body["branch"] = branch

        data = await self._request("DELETE", f"/repos/{owner}/{repo}/contents/{path}", json=body)
        logger.info(f"Deleted file {path} from {owner}/{repo}")
        return data

    # ==================== Issue Operations ====================

    async def list_issues(
        self,
        owner: str,
        repo: str,
        state: GitHubState = GitHubState.OPEN,
        labels: Optional[list[str]] = None,
        sort: GitHubSort = GitHubSort.CREATED,
        direction: GitHubDirection = GitHubDirection.DESC,
        per_page: int = 100,
    ) -> list[GitHubIssue]:
        """List repository issues."""
        params = {
            "state": state.value,
            "sort": sort.value,
            "direction": direction.value,
            "per_page": per_page,
        }

        if labels:
            params["labels"] = ",".join(labels)

        data = await self._request("GET", f"/repos/{owner}/{repo}/issues", params=params)
        return [GitHubIssue.from_api(i) for i in data]

    async def get_issue(
        self,
        owner: str,
        repo: str,
        issue_number: int,
    ) -> GitHubIssue:
        """Get a specific issue."""
        data = await self._request("GET", f"/repos/{owner}/{repo}/issues/{issue_number}")
        return GitHubIssue.from_api(data)

    async def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: Optional[str] = None,
        labels: Optional[list[str]] = None,
        assignees: Optional[list[str]] = None,
        milestone: Optional[int] = None,
    ) -> GitHubIssue:
        """Create a new issue."""
        body_data = {"title": title}

        if body:
            body_data["body"] = body
        if labels:
            body_data["labels"] = labels
        if assignees:
            body_data["assignees"] = assignees
        if milestone:
            body_data["milestone"] = milestone

        data = await self._request("POST", f"/repos/{owner}/{repo}/issues", json=body_data)
        issue = GitHubIssue.from_api(data)
        logger.info(f"Created issue #{issue.number} in {owner}/{repo}")
        return issue

    async def update_issue(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        title: Optional[str] = None,
        body: Optional[str] = None,
        state: Optional[GitHubState] = None,
        labels: Optional[list[str]] = None,
        assignees: Optional[list[str]] = None,
        milestone: Optional[int] = None,
    ) -> GitHubIssue:
        """Update an issue."""
        body_data = {}

        if title is not None:
            body_data["title"] = title
        if body is not None:
            body_data["body"] = body
        if state is not None:
            body_data["state"] = state.value
        if labels is not None:
            body_data["labels"] = labels
        if assignees is not None:
            body_data["assignees"] = assignees
        if milestone is not None:
            body_data["milestone"] = milestone

        data = await self._request("PATCH", f"/repos/{owner}/{repo}/issues/{issue_number}", json=body_data)
        return GitHubIssue.from_api(data)

    async def close_issue(
        self,
        owner: str,
        repo: str,
        issue_number: int,
    ) -> GitHubIssue:
        """Close an issue."""
        return await self.update_issue(owner, repo, issue_number, state=GitHubState.CLOSED)

    async def reopen_issue(
        self,
        owner: str,
        repo: str,
        issue_number: int,
    ) -> GitHubIssue:
        """Reopen an issue."""
        return await self.update_issue(owner, repo, issue_number, state=GitHubState.OPEN)

    # ==================== Pull Request Operations ====================

    async def list_pull_requests(
        self,
        owner: str,
        repo: str,
        state: GitHubState = GitHubState.OPEN,
        head: Optional[str] = None,
        base: Optional[str] = None,
        sort: GitHubSort = GitHubSort.CREATED,
        direction: GitHubDirection = GitHubDirection.DESC,
        per_page: int = 100,
    ) -> list[GitHubPullRequest]:
        """List repository pull requests."""
        params = {
            "state": state.value,
            "sort": sort.value,
            "direction": direction.value,
            "per_page": per_page,
        }

        if head:
            params["head"] = head
        if base:
            params["base"] = base

        data = await self._request("GET", f"/repos/{owner}/{repo}/pulls", params=params)
        return [GitHubPullRequest.from_api(pr) for pr in data]

    async def get_pull_request(
        self,
        owner: str,
        repo: str,
        pull_number: int,
    ) -> GitHubPullRequest:
        """Get a specific pull request."""
        data = await self._request("GET", f"/repos/{owner}/{repo}/pulls/{pull_number}")
        return GitHubPullRequest.from_api(data)

    async def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        head: str,
        base: str,
        body: Optional[str] = None,
        draft: bool = False,
        maintainer_can_modify: bool = True,
    ) -> GitHubPullRequest:
        """Create a pull request."""
        body_data = {
            "title": title,
            "head": head,
            "base": base,
            "draft": draft,
            "maintainer_can_modify": maintainer_can_modify,
        }

        if body:
            body_data["body"] = body

        data = await self._request("POST", f"/repos/{owner}/{repo}/pulls", json=body_data)
        pr = GitHubPullRequest.from_api(data)
        logger.info(f"Created PR #{pr.number} in {owner}/{repo}")
        return pr

    async def update_pull_request(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        title: Optional[str] = None,
        body: Optional[str] = None,
        state: Optional[GitHubState] = None,
        base: Optional[str] = None,
    ) -> GitHubPullRequest:
        """Update a pull request."""
        body_data = {}

        if title is not None:
            body_data["title"] = title
        if body is not None:
            body_data["body"] = body
        if state is not None:
            body_data["state"] = state.value
        if base is not None:
            body_data["base"] = base

        data = await self._request("PATCH", f"/repos/{owner}/{repo}/pulls/{pull_number}", json=body_data)
        return GitHubPullRequest.from_api(data)

    async def merge_pull_request(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        commit_title: Optional[str] = None,
        commit_message: Optional[str] = None,
        merge_method: GitHubMergeState = GitHubMergeState.MERGE,
    ) -> dict[str, Any]:
        """Merge a pull request."""
        body = {"merge_method": merge_method.value}

        if commit_title:
            body["commit_title"] = commit_title
        if commit_message:
            body["commit_message"] = commit_message

        data = await self._request("PUT", f"/repos/{owner}/{repo}/pulls/{pull_number}/merge", json=body)
        logger.info(f"Merged PR #{pull_number} in {owner}/{repo}")
        return data

    async def close_pull_request(
        self,
        owner: str,
        repo: str,
        pull_number: int,
    ) -> GitHubPullRequest:
        """Close a pull request."""
        return await self.update_pull_request(owner, repo, pull_number, state=GitHubState.CLOSED)

    # ==================== Comment Operations ====================

    async def list_issue_comments(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        per_page: int = 100,
    ) -> list[GitHubComment]:
        """List comments on an issue."""
        data = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
            params={"per_page": per_page},
        )
        return [GitHubComment.from_api(c) for c in data]

    async def create_issue_comment(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        body: str,
    ) -> GitHubComment:
        """Create a comment on an issue."""
        data = await self._request(
            "POST",
            f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
            json={"body": body},
        )
        comment = GitHubComment.from_api(data)
        logger.info(f"Created comment on issue #{issue_number}")
        return comment

    async def update_issue_comment(
        self,
        owner: str,
        repo: str,
        comment_id: int,
        body: str,
    ) -> GitHubComment:
        """Update an issue comment."""
        data = await self._request(
            "PATCH",
            f"/repos/{owner}/{repo}/issues/comments/{comment_id}",
            json={"body": body},
        )
        return GitHubComment.from_api(data)

    async def delete_issue_comment(
        self,
        owner: str,
        repo: str,
        comment_id: int,
    ) -> bool:
        """Delete an issue comment."""
        await self._request("DELETE", f"/repos/{owner}/{repo}/issues/comments/{comment_id}")
        return True

    async def list_pr_comments(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        per_page: int = 100,
    ) -> list[GitHubComment]:
        """List review comments on a PR."""
        data = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/pulls/{pull_number}/comments",
            params={"per_page": per_page},
        )
        return [GitHubComment.from_api(c) for c in data]

    # ==================== Actions Operations ====================

    async def list_workflow_runs(
        self,
        owner: str,
        repo: str,
        branch: Optional[str] = None,
        event: Optional[str] = None,
        status: Optional[str] = None,
        per_page: int = 100,
    ) -> list[GitHubWorkflowRun]:
        """List workflow runs."""
        params = {"per_page": per_page}

        if branch:
            params["branch"] = branch
        if event:
            params["event"] = event
        if status:
            params["status"] = status

        data = await self._request("GET", f"/repos/{owner}/{repo}/actions/runs", params=params)
        return [GitHubWorkflowRun.from_api(r) for r in data.get("workflow_runs", [])]

    async def get_workflow_run(
        self,
        owner: str,
        repo: str,
        run_id: int,
    ) -> GitHubWorkflowRun:
        """Get a workflow run."""
        data = await self._request("GET", f"/repos/{owner}/{repo}/actions/runs/{run_id}")
        return GitHubWorkflowRun.from_api(data)

    async def cancel_workflow_run(
        self,
        owner: str,
        repo: str,
        run_id: int,
    ) -> bool:
        """Cancel a workflow run."""
        await self._request("POST", f"/repos/{owner}/{repo}/actions/runs/{run_id}/cancel")
        return True

    async def rerun_workflow(
        self,
        owner: str,
        repo: str,
        run_id: int,
    ) -> bool:
        """Re-run a workflow."""
        await self._request("POST", f"/repos/{owner}/{repo}/actions/runs/{run_id}/rerun")
        logger.info(f"Re-running workflow {run_id}")
        return True

    async def trigger_workflow(
        self,
        owner: str,
        repo: str,
        workflow_id: str,
        ref: str = "main",
        inputs: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Trigger a workflow dispatch event."""
        body = {"ref": ref}
        if inputs:
            body["inputs"] = inputs

        await self._request(
            "POST",
            f"/repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches",
            json=body,
        )
        logger.info(f"Triggered workflow {workflow_id}")
        return True

    # ==================== Branch Operations ====================

    async def list_branches(
        self,
        owner: str,
        repo: str,
        per_page: int = 100,
    ) -> list[dict[str, Any]]:
        """List branches."""
        data = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/branches",
            params={"per_page": per_page},
        )
        return data

    async def get_branch(
        self,
        owner: str,
        repo: str,
        branch: str,
    ) -> dict[str, Any]:
        """Get a branch."""
        return await self._request("GET", f"/repos/{owner}/{repo}/branches/{branch}")

    async def create_branch(
        self,
        owner: str,
        repo: str,
        ref: str,
        sha: str,
    ) -> dict[str, Any]:
        """Create a branch."""
        data = await self._request(
            "POST",
            f"/repos/{owner}/{repo}/git/refs",
            json={"ref": f"refs/heads/{ref}", "sha": sha},
        )
        logger.info(f"Created branch {ref} in {owner}/{repo}")
        return data

    async def delete_branch(
        self,
        owner: str,
        repo: str,
        branch: str,
    ) -> bool:
        """Delete a branch."""
        await self._request("DELETE", f"/repos/{owner}/{repo}/git/refs/heads/{branch}")
        logger.info(f"Deleted branch {branch} from {owner}/{repo}")
        return True

    async def close(self) -> None:
        """Close HTTP client."""
        await self._http_client.aclose()

    async def __aenter__(self) -> "GitHubClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()


class GitHubError(Exception):
    """GitHub API error."""
    pass
