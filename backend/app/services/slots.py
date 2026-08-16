"""Reading slots off stored images, and adding a competing variant to one.

The grouping itself is pure (``domain/slots.py``); this module is the seam that
feeds it images and the open-defect counts it needs, and the one place a new
variant is created.
"""

from uuid import uuid4

from app.domain.entities import (
    ImageAsset,
    ImageStatus,
    Project,
    Slot,
    User,
    now,
)
from app.domain.lifecycle import DefectState
from app.domain.marks import DefectSignal
from app.domain.permissions import Permission, require
from app.domain.slots import SlotGroup, SlotState, group_into_slots, slot_state
from app.imaging.canvas import from_bytes, to_png_bytes
from app.infra import repository as repo
from app.infra.storage import ORIGINAL, BlobStore, blob_path
from app.infra.store import Store

#: Defect states that still want a human or an agent — what "open" means on a card.
NEEDS_ATTENTION = frozenset({DefectState.OPEN, DefectState.NEEDS_HUMAN_REVIEW})


def new_id() -> str:
    return uuid4().hex


async def project_slots(store: Store, project_id: str) -> list[SlotGroup]:
    """Every slot in the project, legacy images wrapped as they are read."""
    return group_into_slots(await repo.images_for_project(store, project_id))


async def slot_containing(store: Store, image: ImageAsset) -> SlotGroup | None:
    """The slot this image belongs to, including its sibling variants.

    Reads the whole project rather than querying by ``slot_id`` because pre-slot
    images have none, and one read path for both keeps the legacy case honest.
    """
    slot_id = image.slot_id
    for group in await project_slots(store, image.project_id):
        if group.slot_id == slot_id or any(
            any(version.id == image.id for version in chain.versions) for chain in group.variants
        ):
            return group
    return None


async def defect_signals(store: Store, groups: list[SlotGroup]) -> dict[str, DefectSignal]:
    """Per-tip facts the derived marks need: open count, questions, oldest open.

    One walk over the same defects ``open_defect_counts`` reads, so marks cost no
    extra queries. Archived variants included; excluding them is the caller's job.
    """
    signals: dict[str, DefectSignal] = {}
    for group in groups:
        for chain in group.variants:
            tip = chain.tip
            defects = await repo.defects_for_image(store, tip.id)
            open_defects = [d for d in defects if d.status in NEEDS_ATTENTION]
            signals[tip.id] = DefectSignal(
                open_count=len(open_defects),
                question_count=sum(
                    1 for d in open_defects if d.status is DefectState.NEEDS_HUMAN_REVIEW
                ),
                oldest_open=min((d.created_at for d in open_defects), default=None),
            )
    return signals


async def open_defect_counts(store: Store, groups: list[SlotGroup]) -> dict[str, int]:
    """Per-image count of defects still needing someone — archived variants included."""
    signals = await defect_signals(store, groups)
    return {image_id: signal.open_count for image_id, signal in signals.items()}


async def states_for(store: Store, groups: list[SlotGroup]) -> dict[str, SlotState]:
    counts = await open_defect_counts(store, groups)
    return {group.slot_id: slot_state(group, counts) for group in groups}


async def needs_attention(store: Store, project_id: str) -> int:
    """Slots waiting on a human. Complete slots and archived variants do not count."""
    groups = await project_slots(store, project_id)
    counts = await open_defect_counts(store, groups)
    waiting = 0
    for group in groups:
        if group.is_complete:
            continue
        if any(
            counts.get(chain.tip.id, 0) and group.archived_by(chain.variant) is None
            for chain in group.variants
        ):
            waiting += 1
    return waiting


async def create_slot(store: Store, project_id: str, name: str) -> Slot:
    slot = Slot(id=new_id(), project_id=project_id, name=name)
    await repo.save(store, slot)
    return slot


async def add_variant(
    store: Store,
    blobs: BlobStore,
    project: Project,
    user: User,
    slot_id: str,
    filename: str,
    data: bytes,
) -> ImageAsset:
    """Add a competing candidate to an existing slot.

    This is the escape hatch the linear-chain rule depends on: when a fix would
    fork a version chain, it becomes a new variant here instead.
    """
    require(project, user.id, Permission.UPLOAD_IMAGES)

    existing = await repo.images_for_project(store, project.id)
    group = next((g for g in group_into_slots(existing) if g.slot_id == slot_id), None)
    if group is None:
        raise ValueError("slot not found in this project")

    image = from_bytes(data)
    asset = ImageAsset(
        id=new_id(),
        project_id=project.id,
        run_id=group.variants[0].root.run_id,
        filename=filename,
        slot_id=slot_id,
        variant=group.next_variant,
        uploaded_by=user.id,
        width=image.width,
        height=image.height,
        status=ImageStatus.QUEUED,
    )
    asset.original_path = await blobs.write(
        blob_path(project.id, asset.id, ORIGINAL), to_png_bytes(image)
    )
    await repo.save(store, asset)
    return asset


async def apply_approval(
    store: Store, group: SlotGroup, target: ImageAsset, user_id: str
) -> ImageAsset:
    """Make ``target`` the slot's single approved version, and return it.

    Approval is the *only* stored part of completion; archiving is derived from it
    (decision 14). So picking a different winner means clearing the old approval —
    which is exactly what makes the choice reversible, and why there is nothing
    else to undo.
    """
    for chain in group.variants:
        for asset in chain.versions:
            if asset.id != target.id and asset.is_approved:
                asset.approved_by = None
                asset.approved_at = None
                await repo.save(store, asset)

    target.approved_by = user_id
    target.approved_at = now()
    await repo.save(store, target)
    return target


async def delete_preview_for_slot(store: Store, group: SlotGroup) -> dict[str, int]:
    """What deleting a whole slot would destroy — every variant, every version."""
    totals = {"variants": len(group.variants), "versions": 0, "defects": 0, "comments": 0}
    for chain in group.variants:
        totals["versions"] += len(chain.versions)
        for asset in chain.versions:
            for defect in await repo.defects_for_image(store, asset.id):
                totals["defects"] += 1
                totals["comments"] += len(await repo.comments_for_defect(store, defect.id))
    return totals


__all__ = [
    "add_variant",
    "apply_approval",
    "create_slot",
    "defect_signals",
    "delete_preview_for_slot",
    "needs_attention",
    "open_defect_counts",
    "project_slots",
    "slot_containing",
    "states_for",
]
