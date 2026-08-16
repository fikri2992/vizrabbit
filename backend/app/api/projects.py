"""Projects, members and guidelines."""

from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field

from app.agents.schemas import GuidelineGrilling, GuidelineQuestion
from app.api.deps import BlobsDep, ProjectDep, StoreDep, UserDep, guard
from app.domain.entities import BrandProfile, Guideline, Member, PaletteEntry, Project, Role
from app.domain.permissions import Permission, permissions_for, validate_membership
from app.imaging import documents
from app.infra import repository as repo
from app.services import brand as brand_service
from app.services import export as export_service
from app.services import guidelines as guideline_service
from app.services import projects as project_service

router = APIRouter(prefix="/api/projects", tags=["projects"])

#: Brand guidelines are design documents; they are much bigger than an asset.
MAX_DOCUMENT_BYTES = 25 * 1024 * 1024


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
    return ProjectView(project=project, role=role, permissions=sorted(permissions_for(role)))


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
        members=[Member(user_id=user.id, email=user.email, name=user.name, role=Role.OWNER)],
    )
    validate_membership(project)
    await repo.save(store, project)
    return _view(project, user.id)


@router.get("/{project_id}")
async def get_project(project: ProjectDep, user: UserDep) -> ProjectView:
    return _view(project, user.id)


class RenameProject(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@router.post("/{project_id}/name")
async def rename_project(
    body: RenameProject, project: ProjectDep, store: StoreDep, user: UserDep
) -> ProjectView:
    guard(project, user, Permission.RENAME_PROJECT)
    try:
        renamed = await project_service.rename(store, project, user, body.name)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _view(renamed, user.id)


@router.get("/{project_id}/export/approved")
async def export_approved(project: ProjectDep, store: StoreDep, blobs: BlobsDep) -> Response:
    """Phase 8: the winners as a zip — clean originals, latest approved versions."""
    if not await export_service.approved_assets(store, project.id):
        raise HTTPException(404, "nothing approved yet")
    payload = await export_service.build_zip(store, blobs, project.id)
    return Response(
        content=payload,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{project.name or "approved"}-approved.zip"'
            )
        },
    )


@router.get("/{project_id}/delete_preview")
async def project_delete_preview(
    project: ProjectDep, store: StoreDep, user: UserDep
) -> dict[str, int]:
    """What deleting this project would destroy — shown before the Owner confirms."""
    guard(project, user, Permission.DELETE_PROJECT)
    return await project_service.delete_preview(store, project)


@router.delete("/{project_id}")
async def delete_project(
    project: ProjectDep, store: StoreDep, blobs: BlobsDep, user: UserDep
) -> dict[str, int]:
    """Owner destroys the project: every slot, image, defect, thread and blob.

    Returns what was actually removed rather than 204, because the counts can
    differ from the preview if a run landed in between.
    """
    guard(project, user, Permission.DELETE_PROJECT)
    return await project_service.delete_project(store, blobs, project, user)


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


@router.post("/{project_id}/guidelines/{guideline_id}/grill")
async def grill_guideline(
    guideline_id: str, project: ProjectDep, store: StoreDep, user: UserDep
) -> GuidelineGrilling:
    """Ask the agent what this guideline leaves ambiguous.

    Owner-only, because only the owner can answer — offering the questions to
    anyone else would just produce unanswerable ones.
    """
    guard(project, user, Permission.ANSWER_GRILLING)

    guideline = await repo.load(store, Guideline, guideline_id)
    if guideline is None or guideline.project_id != project.id:
        raise HTTPException(404, "guideline not found")

    return await guideline_service.grill(guideline)


# --- brand profile --------------------------------------------------------


class PaletteInput(BaseModel):
    hex: str
    role: str = ""
    tolerance: float = Field(default=3.0, ge=0.0, le=100.0)


class ConfirmPalette(BaseModel):
    entries: list[PaletteInput]


class BrandView(BaseModel):
    """The profile plus the one fact the UI keeps having to ask: is it live?"""

    profile: BrandProfile
    active: bool
    #: Questions the extraction wants the Owner to settle before confirming.
    questions: list[GuidelineQuestion] = []


def _brand_view(profile: BrandProfile, questions=None) -> BrandView:
    return BrandView(profile=profile, active=profile.is_active, questions=questions or [])


@router.get("/{project_id}/brand")
async def get_brand_profile(project: ProjectDep, store: StoreDep) -> BrandView:
    return _brand_view(await brand_service.get_or_create(store, project.id))


@router.post("/{project_id}/brand/extract")
async def extract_brand_palette(
    project: ProjectDep,
    store: StoreDep,
    user: UserDep,
    guideline_id: str | None = None,
    file: UploadFile | None = None,
) -> BrandView:
    """Propose a palette from a stored guideline, an uploaded PDF, or both.

    Proposing changes nothing the pipeline enforces — only ``/brand/confirm`` does.
    """
    guard(project, user, Permission.EDIT_GUIDELINE)

    raw_text, name = "", ""
    if guideline_id:
        guideline = await repo.load(store, Guideline, guideline_id)
        if guideline is None or guideline.project_id != project.id:
            raise HTTPException(404, "guideline not found")
        raw_text, name = guideline.as_prompt(), guideline.name

    pdf: bytes | None = None
    if file is not None:
        pdf = await file.read()
        if len(pdf) > MAX_DOCUMENT_BYTES:
            raise HTTPException(413, "guideline PDF is larger than 25MB")
        if not documents.is_pdf(pdf):
            raise HTTPException(415, "only PDF guidelines can be read for a palette")
        name = name or (file.filename or "")

    if not raw_text and pdf is None:
        raise HTTPException(400, "give a guideline_id, a PDF, or both")

    extraction = await guideline_service.extract_palette(raw_text, pdf, name)
    profile = await brand_service.propose(
        store, project.id, guideline_service.as_entries(extraction), source=name or "guideline"
    )
    return _brand_view(profile, extraction.questions)


@router.post("/{project_id}/brand/confirm")
async def confirm_brand_palette(
    body: ConfirmPalette, project: ProjectDep, store: StoreDep, user: UserDep
) -> BrandView:
    """The Owner signs off the palette. This is the moment brand defects become possible."""
    guard(project, user, Permission.CONFIRM_BRAND_PROFILE)
    try:
        profile = await brand_service.confirm(
            store,
            project,
            user,
            [PaletteEntry(**entry.model_dump()) for entry in body.entries],
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _brand_view(profile)


@router.post("/{project_id}/brand/withdraw")
async def withdraw_brand_palette(
    project: ProjectDep, store: StoreDep, user: UserDep
) -> BrandView:
    """Stop enforcing the palette. The colours are kept as a proposal."""
    guard(project, user, Permission.CONFIRM_BRAND_PROFILE)
    return _brand_view(await brand_service.withdraw(store, project, user))


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

    try:
        return await guideline_service.answer(
            store, project, guideline, user, body.question, body.answer
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
