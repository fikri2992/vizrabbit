"""Renaming a project, and destroying one.

Deletion is the only operation in the codebase that crosses every collection, so
it is written as one explicit sweep rather than assembled from the per-image and
per-slot deletes. Those exist to keep a project tidy; this one ends the project,
and a cascade that quietly missed a collection would leave orphaned rows nobody
can reach or clean up.

The preview and the delete walk the same ground in the same order, so what the
Owner is shown is what actually goes.
"""

from app.domain.entities import (
    BrandProfile,
    Comment,
    DefectRecord,
    DismissalRecord,
    Guideline,
    ImageAsset,
    MemoryRule,
    Notification,
    Project,
    ReviewThread,
    Run,
    Slot,
    User,
)
from app.domain.permissions import Permission, require
from app.domain.slots import group_into_slots
from app.infra import repository as repo
from app.infra.storage import BlobStore
from app.infra.store import Store

MAX_NAME = 120


async def rename(store: Store, project: Project, user: User, name: str) -> Project:
    require(project, user.id, Permission.RENAME_PROJECT)

    cleaned = name.strip()
    if not cleaned:
        raise ValueError("a project needs a name")
    if len(cleaned) > MAX_NAME:
        raise ValueError(f"a project name is at most {MAX_NAME} characters")

    project.name = cleaned
    await repo.save(store, project)
    return project


async def delete_preview(store: Store, project: Project) -> dict[str, int]:
    """Everything deleting this project would destroy, counted before it happens."""
    images = await repo.images_for_project(store, project.id)

    defects = comments = dismissals = threads = 0
    for image in images:
        for defect in await repo.defects_for_image(store, image.id):
            defects += 1
            comments += len(await repo.comments_for_defect(store, defect.id))
        for thread in await repo.threads_for_image(store, image.id):
            threads += 1
            comments += len(await repo.comments_for_defect(store, thread.id))
        dismissals += len(await repo.dismissals_for_image(store, image.id))

    return {
        # Grouped rather than counting stored Slot rows: a pre-slot image has no
        # row but does have a card, and the modal must match the Slots tab the
        # Owner is looking at.
        "slots": len(group_into_slots(images)),
        "images": len(images),
        "defects": defects,
        "threads": threads,
        "comments": comments,
        "dismissals": dismissals,
        "guidelines": len(await repo.find(store, Guideline, where={"project_id": project.id})),
        "memory_rules": len(await repo.find(store, MemoryRule, where={"project_id": project.id})),
        "members": len(project.members),
    }


async def delete_project(
    store: Store, blobs: BlobStore, project: Project, user: User
) -> dict[str, int]:
    """Remove the project and every record and blob belonging to it.

    Returns the same shape as the preview, describing what was actually removed —
    the two can differ if a run landed between the Owner reading the modal and
    confirming it, and the caller would rather know.
    """
    require(project, user.id, Permission.DELETE_PROJECT)

    removed = await delete_preview(store, project)

    for image in await repo.images_for_project(store, project.id):
        for defect in await repo.defects_for_image(store, image.id):
            for comment in await repo.comments_for_defect(store, defect.id):
                await repo.delete(store, Comment, comment.id)
            await repo.delete(store, DefectRecord, defect.id)
        for thread in await repo.threads_for_image(store, image.id):
            for comment in await repo.comments_for_defect(store, thread.id):
                await repo.delete(store, Comment, comment.id)
            await repo.delete(store, ReviewThread, thread.id)
        for dismissal in await repo.dismissals_for_image(store, image.id):
            await repo.delete(store, DismissalRecord, dismissal.id)
        for path in (image.original_path, image.gridded_path, image.annotated_path):
            if path:
                await blobs.delete(path)
        await repo.delete(store, ImageAsset, image.id)

    for slot in await repo.slots_for_project(store, project.id):
        await repo.delete(store, Slot, slot.id)
    for run in await repo.find(store, Run, where={"project_id": project.id}):
        await repo.delete(store, Run, run.id)
    for guideline in await repo.find(store, Guideline, where={"project_id": project.id}):
        await repo.delete(store, Guideline, guideline.id)
    for rule in await repo.find(store, MemoryRule, where={"project_id": project.id}):
        await repo.delete(store, MemoryRule, rule.id)
    for profile in await repo.find(store, BrandProfile, where={"project_id": project.id}):
        await repo.delete(store, BrandProfile, profile.id)

    # Notifications point at a project that will not exist; a link to nothing is
    # worse than no notification.
    for notification in await repo.find(store, Notification, where={"project_id": project.id}):
        await repo.delete(store, Notification, notification.id)

    await repo.delete(store, Project, project.id)
    return removed
