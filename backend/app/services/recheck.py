"""Submitting a fix, and the agent deciding whether it worked.

This is the only path to ``verified_resolved`` — no human can mark a defect fixed
(domain-model.md decision 12). A reviewer uploads a new version of the image; every
outstanding defect moves to ``fix_submitted``; the agent then re-checks each one
against the new version and either closes it or sends it back to ``open``.
"""

from uuid import uuid4

from app.agents.pipeline import recheck_defect
from app.domain.entities import (
    DefectRecord,
    ImageAsset,
    ImageStatus,
    NotificationKind,
    Project,
    User,
    now,
)
from app.domain.grid import Grid
from app.domain.lifecycle import DefectState, assert_transition
from app.domain.permissions import Permission, require
from app.domain.slots import successor_of
from app.imaging.canvas import from_bytes, to_png_bytes
from app.imaging.grid_overlay import apply_grid
from app.infra import repository as repo
from app.infra.events import Event, EventBus
from app.infra.storage import GRIDDED, ORIGINAL, BlobStore, blob_path
from app.infra.store import Store
from app.services.review import notify

#: States a defect can be in and still be worth re-checking.
AWAITING_FIX = frozenset({DefectState.OPEN, DefectState.NEEDS_HUMAN_REVIEW})


class ForkedChain(ValueError):
    """Raised when a fix would branch a version chain. The answer is a new variant."""


def new_id() -> str:
    return uuid4().hex


async def submit_fix(
    store: Store,
    blobs: BlobStore,
    project: Project,
    original: ImageAsset,
    user: User,
    filename: str,
    data: bytes,
) -> tuple[ImageAsset, list[DefectRecord]]:
    """Register a new version of an image and mark its open defects as fixed.

    Returns the new version and the defects now awaiting the agent's verdict.
    """
    require(project, user.id, Permission.SUBMIT_FIX)

    # Version chains are strictly linear: a second fix of the same version would
    # fork it, and a fork is what variants are for (domain-model.md decision 13).
    siblings = await repo.images_for_project(store, project.id)
    already = successor_of(siblings, original)
    if already is not None:
        raise ForkedChain(
            f"v{already.version} already fixes this version — "
            "add a competing variant to the slot instead of forking the chain"
        )

    image = from_bytes(data)
    version = ImageAsset(
        id=new_id(),
        project_id=project.id,
        run_id=original.run_id,
        filename=filename or original.filename,
        slot_id=original.slot_id,
        variant=original.variant,
        version=original.version + 1,
        uploaded_by=user.id,
        supersedes_id=original.id,
        width=image.width,
        height=image.height,
        status=ImageStatus.QUEUED,
    )
    grid = Grid.for_image(image.width, image.height)
    version.original_path = await blobs.write(
        blob_path(project.id, version.id, ORIGINAL), to_png_bytes(image)
    )
    version.gridded_path = await blobs.write(
        blob_path(project.id, version.id, GRIDDED), to_png_bytes(apply_grid(image, grid))
    )
    await repo.save(store, version)

    submitted: list[DefectRecord] = []
    for defect in await repo.defects_for_image(store, original.id):
        if defect.status not in AWAITING_FIX:
            continue
        assert_transition(
            defect.status, DefectState.FIX_SUBMITTED, project.role_of(user.id).as_actor()
        )
        defect.status = DefectState.FIX_SUBMITTED
        defect.resolved_in_image_id = version.id
        defect.updated_at = now()
        await repo.save(store, defect)
        submitted.append(defect)

    return version, submitted


async def run_recheck(
    store: Store,
    blobs: BlobStore,
    bus: EventBus,
    project: Project,
    original: ImageAsset,
    version: ImageAsset,
) -> list[DefectRecord]:
    """Re-check every submitted defect against the new version.

    Each verdict is the agent's alone: closed, or returned to ``open`` with the
    reason recorded so the designer knows what is still wrong.
    """
    before = from_bytes(await blobs.read(original.original_path))
    after = from_bytes(await blobs.read(version.original_path))
    before_grid = Grid.for_image(before.width, before.height)
    after_grid = Grid.for_image(after.width, after.height)

    version.status = ImageStatus.REVIEWING
    await repo.save(store, version)

    async def publish(stage: str, **detail) -> None:
        await bus.publish(
            Event(
                stage=stage,
                project_id=project.id,
                run_id=version.run_id,
                detail={**detail, "image_id": version.id, "filename": version.filename},
            )
        )

    pending = [
        defect
        for defect in await repo.defects_for_image(store, original.id)
        if defect.status is DefectState.FIX_SUBMITTED
    ]
    await publish("recheck_started", defects=len(pending))

    outcomes: list[DefectRecord] = []
    for defect in pending:
        defect.status = DefectState.AGENT_RECHECKING
        await repo.save(store, defect)

        try:
            verdict = await recheck_defect(
                before,
                after,
                defect.cells,
                defect.comment,
                before_grid=before_grid,
                after_grid=after_grid,
            )
        except Exception as exc:  # noqa: BLE001 — a failed check must not close a defect
            defect.status = DefectState.OPEN
            defect.resolved_in_image_id = None
            await repo.save(store, defect)
            await publish("recheck_failed", pin=defect.pin, error=str(exc))
            outcomes.append(defect)
            continue

        if verdict.resolved:
            defect.status = DefectState.VERIFIED_RESOLVED
            defect.resolved_in_image_id = version.id
        else:
            defect.status = DefectState.OPEN
            defect.resolved_in_image_id = None

        defect.updated_at = now()
        await repo.save(store, defect)
        outcomes.append(defect)

        await publish(
            "rechecked",
            pin=defect.pin,
            resolved=verdict.resolved,
            reason=verdict.reason,
            note=verdict.note,
        )

    version.status = ImageStatus.DONE
    await repo.save(store, version)

    closed = sum(1 for d in outcomes if d.status is DefectState.VERIFIED_RESOLVED)
    await publish("recheck_finished", closed=closed, still_open=len(outcomes) - closed)

    owner = project.owner
    if owner and closed:
        await notify(
            store,
            owner.user_id,
            project.id,
            NotificationKind.DEFECT_RESOLVED,
            f"{closed} defect(s) verified as fixed on {version.filename}",
            link=f"/projects/{project.id}/images/{version.id}",
        )

    return outcomes


async def version_history(store: Store, image: ImageAsset) -> list[ImageAsset]:
    """Every version of this asset, oldest first."""
    everything = await repo.find(store, ImageAsset, where={"run_id": image.run_id})
    by_id = {asset.id: asset for asset in everything}

    root = image
    while root.supersedes_id and root.supersedes_id in by_id:
        root = by_id[root.supersedes_id]

    chain = [root]
    while True:
        following = next(
            (asset for asset in everything if asset.supersedes_id == chain[-1].id), None
        )
        if following is None:
            return chain
        chain.append(following)
