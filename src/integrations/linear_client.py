"""
Linear Client for Sentience v3.0
Full-featured Linear integration with API key auth, issues, and projects.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class LinearPriority(Enum):
    """Issue priority levels."""
    URGENT = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4
    NONE = 0


class LinearIssueState(Enum):
    """Issue states (common ones)."""
    BACKLOG = "backlog"
    UNSTARTED = "unstarted"
    STARTED = "started"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass
class LinearTeam:
    """Linear team."""
    id: str
    name: str
    key: str
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    issue_count: int = 0

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "LinearTeam":
        """Create from API response."""
        return cls(
            id=data["id"],
            name=data["name"],
            key=data.get("key", ""),
            description=data.get("description"),
            icon=data.get("icon"),
            color=data.get("color"),
            issue_count=data.get("issueCount", 0),
        )


@dataclass
class LinearLabel:
    """Linear label."""
    id: str
    name: str
    color: Optional[str] = None
    parent: Optional[str] = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "LinearLabel":
        """Create from API response."""
        return cls(
            id=data["id"],
            name=data["name"],
            color=data.get("color"),
            parent=data.get("parent", {}).get("id") if data.get("parent") else None,
        )


@dataclass
class LinearProject:
    """Linear project."""
    id: str
    name: str
    description: Optional[str] = None
    status: Optional[str] = None
    progress: float = 0.0
    lead_id: Optional[str] = None
    team_id: Optional[str] = None
    start_date: Optional[datetime] = None
    target_date: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "LinearProject":
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
            name=data["name"],
            description=data.get("description"),
            status=data.get("status"),
            progress=data.get("progress", 0.0),
            lead_id=data.get("lead", {}).get("id") if data.get("lead") else None,
            team_id=data.get("team", {}).get("id") if data.get("team") else None,
            start_date=parse_date(data.get("startDate")),
            target_date=parse_date(data.get("targetDate")),
            created_at=parse_date(data.get("createdAt")),
            updated_at=parse_date(data.get("updatedAt")),
        )


@dataclass
class LinearUser:
    """Linear user."""
    id: str
    name: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "LinearUser":
        """Create from API response."""
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            display_name=data.get("displayName"),
            email=data.get("email"),
            avatar_url=data.get("avatarUrl"),
        )


@dataclass
class LinearState:
    """Linear workflow state."""
    id: str
    name: str
    type: str  # backlog, unstarted, started, completed, cancelled
    color: Optional[str] = None
    position: float = 0.0
    team_id: Optional[str] = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "LinearState":
        """Create from API response."""
        return cls(
            id=data["id"],
            name=data["name"],
            type=data.get("type", "backlog"),
            color=data.get("color"),
            position=data.get("position", 0.0),
            team_id=data.get("team", {}).get("id") if data.get("team") else None,
        )


@dataclass
class LinearIssue:
    """Linear issue."""
    id: str
    identifier: str  # e.g., "ENG-123"
    title: str
    description: Optional[str] = None
    priority: LinearPriority = LinearPriority.NONE
    status: Optional[str] = None  # State name
    state_id: Optional[str] = None
    assignee_id: Optional[str] = None
    assignee: Optional[LinearUser] = None
    creator_id: Optional[str] = None
    creator: Optional[LinearUser] = None
    team_id: Optional[str] = None
    team: Optional[LinearTeam] = None
    labels: list[LinearLabel] = field(default_factory=list)
    project_id: Optional[str] = None
    project: Optional[LinearProject] = None
    parent_id: Optional[str] = None
    estimate: Optional[int] = None
    due_date: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    url: Optional[str] = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "LinearIssue":
        """Create from API response."""
        def parse_date(date_str):
            if not date_str:
                return None
            try:
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except ValueError:
                return None

        priority = LinearPriority.NONE
        if "priority" in data and data["priority"] is not None:
            try:
                priority = LinearPriority(data["priority"])
            except ValueError:
                pass

        assignee = None
        if data.get("assignee"):
            assignee = LinearUser.from_api(data["assignee"])

        creator = None
        if data.get("creator"):
            creator = LinearUser.from_api(data["creator"])

        team = None
        if data.get("team"):
            team = LinearTeam.from_api(data["team"])

        labels = [
            LinearLabel.from_api(l) for l in data.get("labels", {}).get("nodes", [])
        ]

        project = None
        if data.get("project"):
            project = LinearProject.from_api(data["project"])

        state = None
        if data.get("state"):
            state = LinearState.from_api(data["state"])

        return cls(
            id=data["id"],
            identifier=data.get("identifier", ""),
            title=data.get("title", ""),
            description=data.get("description"),
            priority=priority,
            status=state.name if state else None,
            state_id=state.id if state else None,
            assignee_id=data.get("assignee", {}).get("id") if data.get("assignee") else None,
            assignee=assignee,
            creator_id=data.get("creator", {}).get("id") if data.get("creator") else None,
            creator=creator,
            team_id=data.get("team", {}).get("id") if data.get("team") else None,
            team=team,
            labels=labels,
            project_id=data.get("project", {}).get("id") if data.get("project") else None,
            project=project,
            parent_id=data.get("parent", {}).get("id") if data.get("parent") else None,
            estimate=data.get("estimate"),
            due_date=parse_date(data.get("dueDate")),
            created_at=parse_date(data.get("createdAt")),
            updated_at=parse_date(data.get("updatedAt")),
            completed_at=parse_date(data.get("completedAt")),
            url=data.get("url"),
        )


@dataclass
class LinearComment:
    """Linear comment."""
    id: str
    body: str
    issue_id: str
    user: Optional[LinearUser] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "LinearComment":
        """Create from API response."""
        def parse_date(date_str):
            if not date_str:
                return None
            try:
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except ValueError:
                return None

        user = None
        if data.get("user"):
            user = LinearUser.from_api(data["user"])

        return cls(
            id=data["id"],
            body=data.get("body", ""),
            issue_id=data.get("issue", {}).get("id", ""),
            user=user,
            created_at=parse_date(data.get("createdAt")),
            updated_at=parse_date(data.get("updatedAt")),
        )


class LinearClient:
    """
    Full-featured Linear client with:
    - API key authentication
    - Issue operations (CRUD)
    - Project management
    - Comments
    - GraphQL-based API
    """

    BASE_URL = "https://api.linear.app/graphql"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._http_client = httpx.AsyncClient(timeout=60.0)

    def _get_headers(self) -> dict[str, str]:
        """Get authenticated headers."""
        return {
            "Authorization": self.api_key,
            "Content-Type": "application/json",
        }

    async def _query(
        self,
        query: str,
        variables: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Execute a GraphQL query."""
        headers = self._get_headers()
        body = {"query": query}
        if variables:
            body["variables"] = variables

        response = await self._http_client.post(
            self.BASE_URL,
            headers=headers,
            json=body,
        )

        if response.status_code != 200:
            raise LinearError(f"Linear API error: {response.text}")

        data = response.json()

        if "errors" in data:
            error_msg = data["errors"][0].get("message", str(data["errors"]))
            raise LinearError(f"GraphQL error: {error_msg}")

        return data.get("data", {})

    # ==================== User Operations ====================

    async def get_viewer(self) -> LinearUser:
        """Get the current authenticated user."""
        query = """
        query Viewer {
            viewer {
                id
                name
                displayName
                email
                avatarUrl
            }
        }
        """
        data = await self._query(query)
        return LinearUser.from_api(data["viewer"])

    async def get_users(self, team_id: Optional[str] = None) -> list[LinearUser]:
        """Get all users or users in a team."""
        if team_id:
            query = """
            query TeamUsers($teamId: String!) {
                team(id: $teamId) {
                    members {
                        nodes {
                            id
                            name
                            displayName
                            email
                            avatarUrl
                        }
                    }
                }
            }
            """
            data = await self._query(query, {"teamId": team_id})
            return [LinearUser.from_api(u) for u in data.get("team", {}).get("members", {}).get("nodes", [])]
        else:
            query = """
            query Users {
                users {
                    nodes {
                        id
                        name
                        displayName
                        email
                        avatarUrl
                    }
                }
            }
            """
            data = await self._query(query)
            return [LinearUser.from_api(u) for u in data.get("users", {}).get("nodes", [])]

    # ==================== Team Operations ====================

    async def get_teams(self) -> list[LinearTeam]:
        """Get all teams."""
        query = """
        query Teams {
            teams {
                nodes {
                    id
                    name
                    key
                    description
                    icon
                    color
                    issueCount
                }
            }
        }
        """
        data = await self._query(query)
        return [LinearTeam.from_api(t) for t in data.get("teams", {}).get("nodes", [])]

    async def get_team(self, team_id: str) -> LinearTeam:
        """Get a specific team."""
        query = """
        query Team($teamId: String!) {
            team(id: $teamId) {
                id
                name
                key
                description
                icon
                color
                issueCount
            }
        }
        """
        data = await self._query(query, {"teamId": team_id})
        return LinearTeam.from_api(data["team"])

    # ==================== State Operations ====================

    async def get_team_states(self, team_id: str) -> list[LinearState]:
        """Get workflow states for a team."""
        query = """
        query TeamStates($teamId: String!) {
            team(id: $teamId) {
                states {
                    nodes {
                        id
                        name
                        type
                        color
                        position
                    }
                }
            }
        }
        """
        data = await self._query(query, {"teamId": team_id})
        states = data.get("team", {}).get("states", {}).get("nodes", [])
        for s in states:
            s["team"] = {"id": team_id}
        return [LinearState.from_api(s) for s in states]

    async def get_state_by_name(self, team_id: str, name: str) -> Optional[LinearState]:
        """Get a state by name within a team."""
        states = await self.get_team_states(team_id)
        for state in states:
            if state.name.lower() == name.lower():
                return state
        return None

    # ==================== Issue Operations ====================

    async def get_issue(self, issue_id: str) -> LinearIssue:
        """Get an issue by ID or identifier."""
        # Try as identifier first
        query = """
        query Issue($issueId: String!) {
            issue(id: $issueId) {
                id
                identifier
                title
                description
                priority
                state {
                    id
                    name
                    type
                    color
                }
                assignee {
                    id
                    name
                    displayName
                    email
                    avatarUrl
                }
                creator {
                    id
                    name
                    displayName
                    email
                    avatarUrl
                }
                team {
                    id
                    name
                    key
                }
                labels {
                    nodes {
                        id
                        name
                        color
                    }
                }
                project {
                    id
                    name
                    status
                }
                parent {
                    id
                }
                estimate
                dueDate
                createdAt
                updatedAt
                completedAt
                url
            }
        }
        """
        data = await self._query(query, {"issueId": issue_id})
        return LinearIssue.from_api(data["issue"])

    async def get_issues(
        self,
        team_id: Optional[str] = None,
        project_id: Optional[str] = None,
        assignee_id: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[LinearPriority] = None,
        label: Optional[str] = None,
        first: int = 50,
        after: Optional[str] = None,
        filter: Optional[dict[str, Any]] = None,
    ) -> tuple[list[LinearIssue], Optional[str]]:
        """
        Get issues with filters.
        Returns (issues, cursor for next page).
        """
        # Build filter
        issue_filter = {}
        if team_id:
            issue_filter["team"] = {"id": {"eq": team_id}}
        if project_id:
            issue_filter["project"] = {"id": {"eq": project_id}}
        if assignee_id:
            issue_filter["assignee"] = {"id": {"eq": assignee_id}}
        if status:
            issue_filter["state"] = {"name": {"eq": status}}
        if priority:
            issue_filter["priority"] = {"eq": priority.value}
        if label:
            issue_filter["labels"] = {"name": {"eq": label}}
        if filter:
            issue_filter.update(filter)

        filter_arg = ""
        if issue_filter:
            import json
            filter_arg = f', filter: {json.dumps(issue_filter)}'

        after_arg = f', after: "{after}"' if after else ""

        query = f"""
        query Issues($first: Int!) {{
            issues(first: $first{filter_arg}{after_arg}) {{
                nodes {{
                    id
                    identifier
                    title
                    description
                    priority
                    state {{
                        id
                        name
                        type
                        color
                    }}
                    assignee {{
                        id
                        name
                        displayName
                        email
                        avatarUrl
                    }}
                    creator {{
                        id
                        name
                        displayName
                        email
                        avatarUrl
                    }}
                    team {{
                        id
                        name
                        key
                    }}
                    labels {{
                        nodes {{
                            id
                            name
                            color
                        }}
                    }}
                    project {{
                        id
                        name
                        status
                    }}
                    estimate
                    dueDate
                    createdAt
                    updatedAt
                    completedAt
                    url
                }}
                pageInfo {{
                    hasNextPage
                    endCursor
                }}
            }}
        }}
        """

        data = await self._query(query, {"first": first})
        issues_data = data.get("issues", {})

        issues = [
            LinearIssue.from_api(i)
            for i in issues_data.get("nodes", [])
        ]

        page_info = issues_data.get("pageInfo", {})
        cursor = page_info.get("endCursor") if page_info.get("hasNextPage") else None

        return issues, cursor

    async def create_issue(
        self,
        title: str,
        team_id: str,
        description: Optional[str] = None,
        priority: Optional[LinearPriority] = None,
        assignee_id: Optional[str] = None,
        state_id: Optional[str] = None,
        label_ids: Optional[list[str]] = None,
        project_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        estimate: Optional[int] = None,
        due_date: Optional[str] = None,
    ) -> LinearIssue:
        """Create a new issue."""
        input_data = {
            "title": title,
            "teamId": team_id,
        }

        if description:
            input_data["description"] = description
        if priority:
            input_data["priority"] = priority.value
        if assignee_id:
            input_data["assigneeId"] = assignee_id
        if state_id:
            input_data["stateId"] = state_id
        if label_ids:
            input_data["labelIds"] = label_ids
        if project_id:
            input_data["projectId"] = project_id
        if parent_id:
            input_data["parentId"] = parent_id
        if estimate:
            input_data["estimate"] = estimate
        if due_date:
            input_data["dueDate"] = due_date

        query = """
        mutation CreateIssue($input: IssueCreateInput!) {
            issueCreate(input: $input) {
                success
                issue {
                    id
                    identifier
                    title
                    description
                    priority
                    state {
                        id
                        name
                        type
                        color
                    }
                    assignee {
                        id
                        name
                        displayName
                        email
                        avatarUrl
                    }
                    team {
                        id
                        name
                        key
                    }
                    labels {
                        nodes {
                            id
                            name
                            color
                        }
                    }
                    project {
                        id
                        name
                    }
                    estimate
                    dueDate
                    createdAt
                    url
                }
            }
        }
        """

        data = await self._query(query, {"input": input_data})
        result = data.get("issueCreate", {})

        if not result.get("success"):
            raise LinearError("Failed to create issue")

        issue = LinearIssue.from_api(result["issue"])
        logger.info(f"Created issue {issue.identifier}: {title}")
        return issue

    async def update_issue(
        self,
        issue_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        priority: Optional[LinearPriority] = None,
        assignee_id: Optional[str] = None,
        state_id: Optional[str] = None,
        label_ids: Optional[list[str]] = None,
        project_id: Optional[str] = None,
        estimate: Optional[int] = None,
        due_date: Optional[str] = None,
    ) -> LinearIssue:
        """Update an issue."""
        input_data = {}

        if title is not None:
            input_data["title"] = title
        if description is not None:
            input_data["description"] = description
        if priority is not None:
            input_data["priority"] = priority.value
        if assignee_id is not None:
            input_data["assigneeId"] = assignee_id
        if state_id is not None:
            input_data["stateId"] = state_id
        if label_ids is not None:
            input_data["labelIds"] = label_ids
        if project_id is not None:
            input_data["projectId"] = project_id
        if estimate is not None:
            input_data["estimate"] = estimate
        if due_date is not None:
            input_data["dueDate"] = due_date

        query = """
        mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
            issueUpdate(id: $id, input: $input) {
                success
                issue {
                    id
                    identifier
                    title
                    description
                    priority
                    state {
                        id
                        name
                        type
                        color
                    }
                    assignee {
                        id
                        name
                        displayName
                        email
                        avatarUrl
                    }
                    team {
                        id
                        name
                        key
                    }
                    labels {
                        nodes {
                            id
                            name
                            color
                        }}
                    project {
                        id
                        name
                    }
                    estimate
                    dueDate
                    updatedAt
                    url
                }
            }
        }
        """

        data = await self._query(query, {"id": issue_id, "input": input_data})
        result = data.get("issueUpdate", {})

        if not result.get("success"):
            raise LinearError("Failed to update issue")

        logger.info(f"Updated issue {issue_id}")
        return LinearIssue.from_api(result["issue"])

    async def delete_issue(self, issue_id: str) -> bool:
        """Delete an issue."""
        query = """
        mutation DeleteIssue($id: String!) {
            issueDelete(id: $id) {
                success
            }
        }
        """

        data = await self._query(query, {"id": issue_id})
        success = data.get("issueDelete", {}).get("success", False)

        if success:
            logger.info(f"Deleted issue {issue_id}")

        return success

    # ==================== Comment Operations ====================

    async def get_comments(self, issue_id: str) -> list[LinearComment]:
        """Get comments for an issue."""
        query = """
        query IssueComments($issueId: String!) {
            issue(id: $issueId) {
                comments {
                    nodes {
                        id
                        body
                        user {
                            id
                            name
                            displayName
                            email
                            avatarUrl
                        }
                        createdAt
                        updatedAt
                    }
                }
            }
        }
        """

        data = await self._query(query, {"issueId": issue_id})
        comments_data = data.get("issue", {}).get("comments", {}).get("nodes", [])

        comments = []
        for c in comments_data:
            c["issue"] = {"id": issue_id}
            comments.append(LinearComment.from_api(c))

        return comments

    async def create_comment(
        self,
        issue_id: str,
        body: str,
    ) -> LinearComment:
        """Create a comment on an issue."""
        query = """
        mutation CreateComment($input: CommentCreateInput!) {
            commentCreate(input: $input) {
                success
                comment {
                    id
                    body
                    user {
                        id
                        name
                        displayName
                        email
                        avatarUrl
                    }
                    issue {
                        id
                    }
                    createdAt
                }
            }
        }
        """

        data = await self._query(query, {"input": {"issueId": issue_id, "body": body}})
        result = data.get("commentCreate", {})

        if not result.get("success"):
            raise LinearError("Failed to create comment")

        comment = LinearComment.from_api(result["comment"])
        logger.info(f"Created comment {comment.id} on issue {issue_id}")
        return comment

    async def update_comment(
        self,
        comment_id: str,
        body: str,
    ) -> LinearComment:
        """Update a comment."""
        query = """
        mutation UpdateComment($id: String!, $input: CommentUpdateInput!) {
            commentUpdate(id: $id, input: $input) {
                success
                comment {
                    id
                    body
                    user {
                        id
                        name
                        displayName
                        email
                        avatarUrl
                    }
                    issue {
                        id
                    }
                    updatedAt
                }
            }
        }
        """

        data = await self._query(query, {"id": comment_id, "input": {"body": body}})
        result = data.get("commentUpdate", {})

        if not result.get("success"):
            raise LinearError("Failed to update comment")

        return LinearComment.from_api(result["comment"])

    async def delete_comment(self, comment_id: str) -> bool:
        """Delete a comment."""
        query = """
        mutation DeleteComment($id: String!) {
            commentDelete(id: $id) {
                success
            }
        }
        """

        data = await self._query(query, {"id": comment_id})
        return data.get("commentDelete", {}).get("success", False)

    # ==================== Project Operations ====================

    async def get_projects(self, team_id: Optional[str] = None) -> list[LinearProject]:
        """Get all projects or projects for a team."""
        if team_id:
            query = """
            query TeamProjects($teamId: String!) {
                team(id: $teamId) {
                    projects {
                        nodes {
                            id
                            name
                            description
                            status
                            progress
                            lead {
                                id
                            }
                            team {
                                id
                            }
                            startDate
                            targetDate
                            createdAt
                            updatedAt
                        }
                    }
                }
            }
            """
            data = await self._query(query, {"teamId": team_id})
            projects = data.get("team", {}).get("projects", {}).get("nodes", [])
        else:
            query = """
            query Projects {
                projects {
                    nodes {
                        id
                        name
                        description
                        status
                        progress
                        lead {
                            id
                        }
                        team {
                            id
                        }
                        startDate
                        targetDate
                        createdAt
                        updatedAt
                    }
                }
            }
            """
            data = await self._query(query)
            projects = data.get("projects", {}).get("nodes", [])

        return [LinearProject.from_api(p) for p in projects]

    async def get_project(self, project_id: str) -> LinearProject:
        """Get a specific project."""
        query = """
        query Project($projectId: String!) {
            project(id: $projectId) {
                id
                name
                description
                status
                progress
                lead {
                    id
                }
                team {
                    id
                }
                startDate
                targetDate
                createdAt
                updatedAt
            }
        }
        """

        data = await self._query(query, {"projectId": project_id})
        return LinearProject.from_api(data["project"])

    async def create_project(
        self,
        name: str,
        team_id: str,
        description: Optional[str] = None,
        lead_id: Optional[str] = None,
        start_date: Optional[str] = None,
        target_date: Optional[str] = None,
    ) -> LinearProject:
        """Create a new project."""
        input_data = {
            "name": name,
            "teamIds": [team_id],
        }

        if description:
            input_data["description"] = description
        if lead_id:
            input_data["leadId"] = lead_id
        if start_date:
            input_data["startDate"] = start_date
        if target_date:
            input_data["targetDate"] = target_date

        query = """
        mutation CreateProject($input: ProjectCreateInput!) {
            projectCreate(input: $input) {
                success
                project {
                    id
                    name
                    description
                    status
                    progress
                    lead {
                        id
                    }
                    team {
                        id
                    }
                    startDate
                    targetDate
                    createdAt
                }
            }
        }
        """

        data = await self._query(query, {"input": input_data})
        result = data.get("projectCreate", {})

        if not result.get("success"):
            raise LinearError("Failed to create project")

        project = LinearProject.from_api(result["project"])
        logger.info(f"Created project {project.id}: {name}")
        return project

    async def update_project(
        self,
        project_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        lead_id: Optional[str] = None,
        start_date: Optional[str] = None,
        target_date: Optional[str] = None,
    ) -> LinearProject:
        """Update a project."""
        input_data = {}

        if name is not None:
            input_data["name"] = name
        if description is not None:
            input_data["description"] = description
        if lead_id is not None:
            input_data["leadId"] = lead_id
        if start_date is not None:
            input_data["startDate"] = start_date
        if target_date is not None:
            input_data["targetDate"] = target_date

        query = """
        mutation UpdateProject($id: String!, $input: ProjectUpdateInput!) {
            projectUpdate(id: $id, input: $input) {
                success
                project {
                    id
                    name
                    description
                    status
                    progress
                    lead {
                        id
                    }
                    team {
                        id
                    }
                    startDate
                    targetDate
                    updatedAt
                }
            }
        }
        """

        data = await self._query(query, {"id": project_id, "input": input_data})
        result = data.get("projectUpdate", {})

        if not result.get("success"):
            raise LinearError("Failed to update project")

        return LinearProject.from_api(result["project"])

    # ==================== Label Operations ====================

    async def get_labels(self, team_id: Optional[str] = None) -> list[LinearLabel]:
        """Get labels (optionally for a team)."""
        if team_id:
            query = """
            query TeamLabels($teamId: String!) {
                team(id: $teamId) {
                    labels {
                        nodes {
                            id
                            name
                            color
                            parent {
                                id
                            }
                        }
                    }
                }
            }
            """
            data = await self._query(query, {"teamId": team_id})
            labels = data.get("team", {}).get("labels", {}).get("nodes", [])
        else:
            query = """
            query Labels {
                issueLabels {
                    nodes {
                        id
                        name
                        color
                        parent {
                            id
                        }
                    }
                }
            }
            """
            data = await self._query(query)
            labels = data.get("issueLabels", {}).get("nodes", [])

        return [LinearLabel.from_api(l) for l in labels]

    async def create_label(
        self,
        name: str,
        team_id: str,
        color: Optional[str] = None,
        parent_id: Optional[str] = None,
    ) -> LinearLabel:
        """Create a label."""
        input_data = {
            "name": name,
            "teamId": team_id,
        }

        if color:
            input_data["color"] = color
        if parent_id:
            input_data["parentId"] = parent_id

        query = """
        mutation CreateLabel($input: IssueLabelCreateInput!) {
            issueLabelCreate(input: $input) {
                success
                issueLabel {
                    id
                    name
                    color
                    parent {
                        id
                    }
                }
            }
        }
        """

        data = await self._query(query, {"input": input_data})
        result = data.get("issueLabelCreate", {})

        if not result.get("success"):
            raise LinearError("Failed to create label")

        label = LinearLabel.from_api(result["issueLabel"])
        logger.info(f"Created label {label.id}: {name}")
        return label

    async def close(self) -> None:
        """Close HTTP client."""
        await self._http_client.aclose()

    async def __aenter__(self) -> "LinearClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()


class LinearError(Exception):
    """Linear API error."""
    pass
