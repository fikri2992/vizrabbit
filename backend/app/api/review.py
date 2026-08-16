"""The review screen's API: defect threads, lifecycle moves, memory, notifications."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import ProjectDep, StoreDep, UserDep
from app.domain.entities import (
    Comment,
    DefectRecord,
    ImageAsset,
    MemoryRule,
    Notification,
    Project,
)
from app.domain.lifecycle import DefectState, allowed_transitions
from app.domain.permissions import PermissionError_
from app.domain.taxonomy import Severity
from app.infra import repository as repo
from app.services import review as service

router = APIRouter(prefix="/api/projects/{project_id}", tags=["review"])


class PostComment(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class MoveDefect(BaseModel):
    to: DefectState
    rationale: str = ""


class ChangeSeverity(BaseModel):
    severity: Severity


class ProposeRule(BaseModel):
    description: str = Field(min_length=1, max_length=500)


class DefectThread(BaseModel):
    defect: DefectRecord
    comments: list[Comment]
    #: What this caller may do next — the review screen renders exactly these.
    #: Excludes ``fix_submitted``, which is reached by uploading a version rather
    #: than by choosing a state, and is surfaced as its own control.
    available_transitions: list[DefectState]
    #: Whether this caller could fix it by submitting a new version.
    can_submit_fix: bool = False


class RuleProposal(BaseModel):
    rule: MemoryRule
    #: Active rules that overlap this one; the Owner is grilled before approving.
    collisions: list[MemoryRule] = []


async def _defect(store, project: Project, defect_id: str) -> DefectRecord:
    defect = await repo.load(store, DefectRecord, defect_id)
    if defect is None or defect.project_id != project.id:
        raise HTTPException(404, "defect not found")
    return defect


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError_):
        return HTTPException(403, str(exc))
    return HTTPException(400, str(exc))


@router.get("/defects/{defect_id}")
async def get_thread(
    defect_id: str, project: ProjectDep, store: StoreDep, user: UserDep
) -> DefectThread:
    defect = await _defect(store, project, defect_id)
    role = project.role_of(user.id)
    reachable = allowed_transitions(defect.status, role.as_actor())

    return DefectThread(
        defect=defect,
        comments=await repo.comments_for_defect(store, defect.id),
        available_transitions=sorted(reachable - {DefectState.FIX_SUBMITTED}),
        can_submit_fix=DefectState.FIX_SUBMITTED in reachable,
    )


@router.post("/defects/{defect_id}/comments", status_code=201)
async def post_comment(
    defect_id: str, body: PostComment, project: ProjectDep, store: StoreDep, user: UserDep
) -> Comment:
    defect = await _defect(store, project, defect_id)
    try:
        return await service.add_comment(store, project, defect, user, body.body)
    except (PermissionError_, ValueError) as exc:
        raise _translate(exc) from exc


@router.post("/defects/{defect_id}/transition")
async def move_defect(
    defect_id: str, body: MoveDefect, project: ProjectDep, store: StoreDep, user: UserDep
) -> DefectRecord:
    """Owners dismiss or override here. Nobody resolves — that is the agent's move."""
    defect = await _defect(store, project, defect_id)
    try:
        return await service.transition_defect(
            store, project, defect, user, body.to, body.rationale
        )
    except (PermissionError_, ValueError) as exc:
        raise _translate(exc) from exc


class AnswerQuestion(BaseModel):
    #: True = "it's real, keep it"; False = "not a problem" (dismiss + teach).
    confirmed: bool


class QuestionAnswered(BaseModel):
    defect: DefectRecord
    #: Human-readable note of any rule/tolerance change the answer caused.
    adjustment: str = ""


@router.post("/defects/{defect_id}/answer")
async def answer_question(
    defect_id: str, body: AnswerQuestion, project: ProjectDep, store: StoreDep, user: UserDep
) -> QuestionAnswered:
    """Answer a needs-human question. Either answer teaches (decision 19 glossary)."""
    defect = await _defect(store, project, defect_id)
    try:
        updated, adjustment = await service.answer_question(
            store, project, defect, user, body.confirmed
        )
    except (PermissionError_, ValueError) as exc:
        raise _translate(exc) from exc
    return QuestionAnswered(defect=updated, adjustment=adjustment)


@router.post("/defects/{defect_id}/severity")
async def change_severity(
    defect_id: str, body: ChangeSeverity, project: ProjectDep, store: StoreDep, user: UserDep
) -> DefectRecord:
    defect = await _defect(store, project, defect_id)
    try:
        return await service.override_severity(store, project, defect, user, body.severity)
    except PermissionError_ as exc:
        raise _translate(exc) from exc


@router.post("/defects/{defect_id}/memory", status_code=201)
async def propose_rule(
    defect_id: str, body: ProposeRule, project: ProjectDep, store: StoreDep, user: UserDep
) -> RuleProposal:
    """Promote a defect to a standing check. Inactive until the Owner approves."""
    defect = await _defect(store, project, defect_id)
    try:
        rule = await service.propose_memory_rule(store, project, defect, user, body.description)
    except (PermissionError_, ValueError) as exc:
        raise _translate(exc) from exc

    collisions = await service.find_colliding_rules(store, project.id, rule.description)
    return RuleProposal(rule=rule, collisions=collisions)


@router.get("/memory")
async def list_memory_rules(project: ProjectDep, store: StoreDep) -> list[MemoryRule]:
    return await repo.find(
        store, MemoryRule, where={"project_id": project.id}, order_by="created_at", descending=True
    )


@router.post("/memory/{rule_id}/approve")
async def approve_rule(
    rule_id: str, project: ProjectDep, store: StoreDep, user: UserDep
) -> MemoryRule:
    rule = await repo.load(store, MemoryRule, rule_id)
    if rule is None or rule.project_id != project.id:
        raise HTTPException(404, "rule not found")
    try:
        return await service.approve_memory_rule(store, project, rule, user)
    except PermissionError_ as exc:
        raise _translate(exc) from exc


@router.post("/images/{image_id}/approve")
async def approve_image(
    image_id: str, project: ProjectDep, store: StoreDep, user: UserDep
) -> ImageAsset:
    """ "Approved" means the Brand Owner said so, with nothing left outstanding."""
    image = await repo.load(store, ImageAsset, image_id)
    if image is None or image.project_id != project.id:
        raise HTTPException(404, "image not found")
    try:
        return await service.approve_image(store, project, image, user)
    except (PermissionError_, ValueError) as exc:
        raise _translate(exc) from exc


notifications_router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@notifications_router.get("")
async def list_notifications(store: StoreDep, user: UserDep) -> list[Notification]:
    return await repo.unread_notifications(store, user.id)


@notifications_router.post("/{notification_id}/read")
async def mark_read(notification_id: str, store: StoreDep, user: UserDep) -> Notification:
    notification = await repo.load(store, Notification, notification_id)
    if notification is None or notification.user_id != user.id:
        raise HTTPException(404, "notification not found")
    return await service.mark_notification_read(store, notification)
