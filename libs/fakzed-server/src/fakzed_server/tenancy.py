"""Multi-tenancy: user / organization / project three-level data model.

Tenant boundaries keep every registered agent, run, and API key scoped to a
project owned by an organization; users get access through membership records.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(BaseModel):
    """A platform user (identity holder for API keys)."""

    user_id: str = Field(default_factory=_new_id)
    name: str
    email: str | None = None
    created_at: datetime = Field(default_factory=_now)


class Organization(BaseModel):
    """An organization: a group of users with shared projects."""

    org_id: str = Field(default_factory=_new_id)
    name: str
    created_at: datetime = Field(default_factory=_now)


class Project(BaseModel):
    """A project: the tenant scope agents, runs, and sessions belong to."""

    project_id: str = Field(default_factory=_new_id)
    org_id: str
    name: str
    created_at: datetime = Field(default_factory=_now)


class Membership(BaseModel):
    """A user's membership in an organization."""

    user_id: str
    org_id: str
    role: str = "member"  # member | admin


class TenantStore(BaseModel):
    """In-memory tenant directory with create/list/join operations."""

    users: dict[str, User] = Field(default_factory=dict)
    orgs: dict[str, Organization] = Field(default_factory=dict)
    projects: dict[str, Project] = Field(default_factory=dict)
    memberships: list[Membership] = Field(default_factory=list)

    def create_user(self, name: str, *, email: str | None = None) -> User:
        user = User(name=name, email=email)
        self.users[user.user_id] = user
        return user

    def create_org(self, name: str, *, owner_id: str) -> Organization:
        org = Organization(name=name)
        self.orgs[org.org_id] = org
        self.memberships.append(Membership(user_id=owner_id, org_id=org.org_id, role="admin"))
        return org

    def create_project(self, org_id: str, name: str) -> Project:
        if org_id not in self.orgs:
            raise KeyError(f"unknown organization '{org_id}'")
        project = Project(org_id=org_id, name=name)
        self.projects[project.project_id] = project
        return project

    def add_member(self, org_id: str, user_id: str, role: str = "member") -> None:
        if org_id not in self.orgs:
            raise KeyError(f"unknown organization '{org_id}'")
        self.memberships.append(Membership(user_id=user_id, org_id=org_id, role=role))

    def projects_of(self, org_id: str) -> list[Project]:
        return [p for p in self.projects.values() if p.org_id == org_id]

    def orgs_of(self, user_id: str) -> list[Organization]:
        ids = {m.org_id for m in self.memberships if m.user_id == user_id}
        return [org for org in self.orgs.values() if org.org_id in ids]

    def role_in(self, user_id: str, org_id: str) -> str | None:
        for membership in self.memberships:
            if membership.user_id == user_id and membership.org_id == org_id:
                return membership.role
        return None
