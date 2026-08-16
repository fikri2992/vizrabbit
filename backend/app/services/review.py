"""Review-screen behaviour: comments, defect transitions, memory promotion.

Every state change goes through the permission layer, so the Brand Owner's
accountability is enforced in one place rather than at each route.
"""

from uuid import uuid4

from app.domain.entities import (
    Comment,
    DefectRecord,
    ImageAsset,
    ImageStatus,
    MemoryRule,
    Notification,
    NotificationKind,
    Project,
    User,
    now,
)
from app.domain.lifecycle import DefectState
from app.domain.mentions import resolve_mentions
from app.domain.permissions import Permission, require, require_defect_move
from app.domain.taxonomy import Severity
from app.infra import repository as repo
from app.infra.store import Store


def new_id() -> str:
    return uuid4().hex


async def add_comment(
    store: Store, project: Project, defect: DefectRecord, author: User, body: str
) -> Comment:
    """Post a comment and notify anyone mentioned in it."""
    require(project, author.id, Permission.COMMENT)
    if not body.strip():
        raise ValueError("a comment needs a body")

    mentioned = [
        user_id for user_id in resolve_mentions(body, project.members) if user_id != author.id
    ]
    comment = Comment(
        id=new_id(),
        project_id=project.id,
        defect_id=defect.id,
        author_id=author.id,
        author_name=author.name or author.email,
        body=body.strip(),
        mentions=mentioned,
    )
    await repo.save(store, comment)

    for user_id in mentioned:
        await notify(
            store,
            user_id,
            project.id,
            NotificationKind.MENTION,
            f"{comment.author_name} mentioned you on pin {defect.pin}",
            link=f"/projects/{project.id}/images/{defect.image_id}?pin={defect.pin}",
        )
    return comment


async def transition_defect(
    store: Store,
    project: Project,
    defect: DefectRecord,
    user: User,
    to: DefectState,
    rationale: str = "",
) -> DefectRecord:
    """Move a defect, enforcing who may make this move and what it requires.

    ``fix_submitted`` is deliberately not reachable here: it must carry the version
    that claims to fix it, or the defect would sit waiting for a re-check that has
    nothing to check against. Upload a version instead.
    """
    if to is DefectState.FIX_SUBMITTED:
        raise ValueError(
            "submit a fixed version of the image instead — a fix must have an image to check"
        )
    require_defect_move(project, user.id, defect.status, to, rationale=rationale or None)

    defect.status = to
    defect.updated_at = now()
    if rationale:
        defect.rationale = rationale
    await repo.save(store, defect)
    return defect


async def override_severity(
    store: Store, project: Project, defect: DefectRecord, user: User, severity: Severity
) -> DefectRecord:
    require(project, user.id, Permission.OVERRIDE_SEVERITY)
    defect.severity = severity
    defect.updated_at = now()
    await repo.save(store, defect)
    return defect


async def approve_image(
    store: Store, project: Project, image: ImageAsset, user: User
) -> ImageAsset:
    """ "Approved" means the Brand Owner said so — nothing else sets this.

    Approval is per-variant and it completes the slot: the sibling variants become
    archived, which is derived from this one approval rather than written onto
    them (domain-model.md decision 14). Approving a different variant later just
    moves the approval, so the pick is reversible and nothing needs undoing.
    """
    from app.services import slots as slot_service

    require(project, user.id, Permission.APPROVE_IMAGE)

    if image.status is not ImageStatus.DONE:
        raise ValueError("the agent has not finished reviewing this image yet")

    outstanding = [
        defect
        for defect in await repo.defects_for_image(store, image.id)
        if defect.status in {DefectState.OPEN, DefectState.NEEDS_HUMAN_REVIEW}
    ]
    if outstanding:
        raise ValueError(
            f"{len(outstanding)} defect(s) still open — resolve, dismiss or override them first"
        )

    group = await slot_service.slot_containing(store, image)
    if group is None:  # no slot context at all: approve the lone image
        image.approved_by = user.id
        image.approved_at = now()
        await repo.save(store, image)
        return image

    return await slot_service.apply_approval(store, group, image, user.id)


async def propose_memory_rule(
    store: Store, project: Project, defect: DefectRecord, user: User, description: str
) -> MemoryRule:
    """Anyone on the team may propose; the rule stays inactive until the Owner approves."""
    require(project, user.id, Permission.PROPOSE_MEMORY_RULE)
    if not description.strip():
        raise ValueError("a memory rule needs a description")

    rule = MemoryRule(
        id=new_id(),
        project_id=project.id,
        description=description.strip(),
        source_defect_id=defect.id,
        proposed_by=user.id,
        active=False,
    )
    await repo.save(store, rule)

    owner = project.owner
    if owner and owner.user_id != user.id:
        await notify(
            store,
            owner.user_id,
            project.id,
            NotificationKind.MEMORY_PROPOSED,
            f"New memory rule proposed: {rule.description[:80]}",
            link=f"/projects/{project.id}/memory",
        )
    return rule


async def approve_memory_rule(
    store: Store, project: Project, rule: MemoryRule, user: User
) -> MemoryRule:
    require(project, user.id, Permission.APPROVE_MEMORY_RULE)
    rule.active = True
    rule.approved_by = user.id
    await repo.save(store, rule)
    return rule


async def find_colliding_rules(store: Store, project_id: str, description: str) -> list[MemoryRule]:
    """Existing active rules that share significant wording with a proposal.

    A cheap lexical overlap check, not a semantic one: its job is to decide whether
    the Owner should be *asked*, and a false alarm costs one question.
    """
    words = _significant_words(description)
    if not words:
        return []

    colliding = []
    for rule in await repo.active_memory_rules(store, project_id):
        existing = _significant_words(rule.description)
        if not existing:
            continue
        overlap = len(words & existing) / len(words | existing)
        if overlap >= 0.4:
            colliding.append(rule)
    return colliding


#: Words too common to signal that two rules overlap.
STOP_WORDS = frozenset(
    """
    a an and are as at be but by for from has have if in into is it its of on or
    that the their them then there these they this to was were will with not no
    do does should must always never check flag report image images
    """.split()  # noqa: SIM905 — a readable word list beats a 50-element literal
)


def _significant_words(text: str) -> set[str]:
    import re

    return {
        word
        for word in re.findall(r"[a-z]+", (text or "").lower())
        if len(word) > 2 and word not in STOP_WORDS
    }


async def notify(
    store: Store,
    user_id: str,
    project_id: str,
    kind: NotificationKind,
    body: str,
    link: str = "",
) -> Notification:
    notification = Notification(
        id=new_id(), user_id=user_id, project_id=project_id, kind=kind, body=body, link=link
    )
    await repo.save(store, notification)
    return notification


async def mark_notification_read(store: Store, notification: Notification) -> Notification:
    notification.read = True
    await repo.save(store, notification)
    return notification
