"""Projects, members and guidelines."""

from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import ProjectDep, StoreDep, UserDep, guard
from app.domain.entities import Clarification, Guideline, Member, Project, Role
from app.domain.permissions import Permission, permissions_for, validate_membership
from app.infra import repository as repo

router = APIRouter(prefix="/api/projects", tags=["projects"])


class CreateProject(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class InviteMember(BaseModel):
    email: str
    role: Role = Role.REVIEWER
    name: str = ""


class ProjectView(BaseModel):
    """A project as the caller sees it, including what they may do with it."""

    project: Project
    role: Role
    permissions: list[Permission]


def _view(project: Project, user_id: str) -> ProjectView:
    role = project.role_of(user_id)
    return ProjectView(
        project=project, role=role, permissions=sorted(permissions_for(role))
    )


@router.get("")
async def list_projects(store: StoreDep, user: UserDep) -> list[ProjectView]:
    projects = await repo.projects_for_user(store, user.id)
    return [_view(project, user.id) for project in projects]


@router.post("", status_code=201)
async def create_project(body: CreateProject, store: StoreDep, user: UserDep) -> ProjectView:
    """The creator becomes the Brand Owner — the one accountable member."""
    project = Project(
        id=uuid4().hex,
        name=body.name.strip(),
        members=[
            Member(user_id=user.id, email=user.email, name=user.name, role=Role.OWNER)
        ],
    )
    validate_membership(project)
    await repo.save(store, project)
    return _view(project, user.id)


@router.get("/{project_id}")
async def get_project(project: ProjectDep, user: UserDep) -> ProjectView:
    return _view(project, user.id)


@router.post("/{project_id}/members", status_code=201)
async def invite_member(
    body: InviteMember, project: ProjectDep, store: StoreDep, user: UserDep
) -> ProjectView:
    guard(project, user, Permission.MANAGE_MEMBERS)

    email = body.email.strip().lower()
    if any(member.email.lower() == email for member in project.members):
        raise HTTPException(409, "already a member")
    if body.role is Role.OWNER:
        raise HTTPException(400, "a project has exactly one owner; transfer instead")

    # The invitee's user id is their email until they first sign in, at which point
    # the OAuth callback reconciles it. Keeps invites possible before first login.
    project.members.append(
        Member(user_id=f"email:{email}", email=email, name=body.name, role=body.role)
    )
    validate_membership(project)
    await repo.save(store, project)
    return _view(project, user.id)


@router.delete("/{project_id}/members/{member_id}")
async def remove_member(
    member_id: str, project: ProjectDep, store: StoreDep, user: UserDep
) -> ProjectView:
    guard(project, user, Permission.MANAGE_MEMBERS)

    member = project.member(member_id)
    if member is None:
        raise HTTPException(404, "not a member")
    if member.role is Role.OWNER:
        raise HTTPException(400, "the owner cannot be removed")

    project.members = [m for m in project.members if m.user_id != member_id]
    validate_membership(project)
    await repo.save(store, project)
    return _view(project, user.id)


# --- guidelines -----------------------------------------------------------


class CreateGuideline(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    raw_text: str = Field(min_length=1)


class AnswerClarification(BaseModel):
    question: str
    answer: str = Field(min_length=1)


@router.get("/{project_id}/guidelines")
async def list_guidelines(project: ProjectDep, store: StoreDep) -> list[Guideline]:
    return await repo.find(store, Guideline, where={"project_id": project.id})


@router.post("/{project_id}/guidelines", status_code=201)
async def create_guideline(
    body: CreateGuideline, project: ProjectDep, store: StoreDep, user: UserDep
) -> Guideline:
    guard(project, user, Permission.EDIT_GUIDELINE)

    guideline = Guideline(
        id=uuid4().hex,
        project_id=project.id,
        name=body.name.strip(),
        raw_text=body.raw_text,
    )
    await repo.save(store, guideline)
    return guideline


@router.post("/{project_id}/guidelines/{guideline_id}/clarifications")
async def answer_clarification(
    guideline_id: str,
    body: AnswerClarification,
    project: ProjectDep,
    store: StoreDep,
    user: UserDep,
) -> Guideline:
    """Only the Brand Owner may answer grilling — otherwise the guideline has no
    authoritative voice (domain-model.md roles)."""
    guard(project, user, Permission.ANSWER_GRILLING)

    guideline = await repo.load(store, Guideline, guideline_id)
    if guideline is None or guideline.project_id != project.id:
        raise HTTPException(404, "guideline not found")

    guideline.clarifications.append(
        Clarification(question=body.question, answer=body.answer, answered_by=user.id)
    )
    from app.domain.entities import now

    guideline.updated_at = now()
    await repo.save(store, guideline)
    return guideline
