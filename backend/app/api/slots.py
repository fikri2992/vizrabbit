"""Slots: the project's work list, and the history tree behind each card."""

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile
from pydantic import BaseModel

from app.api.deps import BlobsDep, BusDep, ProjectDep, StoreDep, UserDep, guard
from app.domain.entities import ImageAsset, Project, Run, Slot
from app.domain.permissions import Permission
from app.domain.slots import SlotGroup, SlotState, slot_state
from app.infra import repository as repo
from app.services import runs as run_service
from app.services import slots as slot_service

router = APIRouter(prefix="/api/projects/{project_id}/slots", tags=["slots"])

ACCEPTED_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class VersionNode(BaseModel):
    """One node of the history tree: what it is, who put it there, how it went."""

    image: ImageAsset
    uploader_name: str
    open_defects: int
    original_url: str


class VariantView(BaseModel):
    variant: int
    versions: list[VersionNode]
    approved: bool = False
    #: The sibling that superseded this variant, if the slot has been completed.
    archived_by: int | None = None
    approved_by_name: str = ""


class SlotView(BaseModel):
    slot_id: str
    name: str
    state: SlotState
    #: True while this slot exists only as a read-time wrapper around legacy data.
    synthetic: bool
    variants: list[VariantView]


def _display_name(project: Project, user_id: str) -> str:
    member = project.member(user_id)
    if member is None:
        return "" if not user_id else "someone no longer on the project"
    return member.name or member.email


async def _view(
    store, blobs, project: Project, group: SlotGroup, name: str, counts: dict[str, int]
) -> SlotView:
    variants: list[VariantView] = []
    for chain in group.variants:
        nodes = [
            VersionNode(
                image=asset,
                uploader_name=_display_name(project, asset.uploaded_by),
                open_defects=counts.get(asset.id, 0),
                original_url=blobs.public_url(asset.original_path),
            )
            for asset in chain.versions
        ]
        approved = chain.approved_version
        variants.append(
            VariantView(
                variant=chain.variant,
                versions=nodes,
                approved=approved is not None,
                archived_by=group.archived_by(chain.variant),
                approved_by_name=(
                    _display_name(project, approved.approved_by or "") if approved else ""
                ),
            )
        )
    return SlotView(
        slot_id=group.slot_id,
        name=name,
        state=slot_state(group, counts),
        synthetic=group.synthetic,
        variants=variants,
    )


@router.get("")
async def list_slots(project: ProjectDep, store: StoreDep, blobs: BlobsDep) -> list[SlotView]:
    """The project's work list. Legacy images appear as one-variant slots."""
    groups = await slot_service.project_slots(store, project.id)
    counts = await slot_service.open_defect_counts(store, groups)
    names = {slot.id: slot.name for slot in await repo.slots_for_project(store, project.id)}
    return [
        await _view(
            store, blobs, project, group, names.get(group.slot_id) or _fallback_name(group), counts
        )
        for group in groups
    ]


def _fallback_name(group: SlotGroup) -> str:
    """A synthetic slot borrows the filename of the image it wraps."""
    return group.variants[0].root.filename


async def _require_group(store, project: Project, slot_id: str) -> SlotGroup:
    group = next(
        (g for g in await slot_service.project_slots(store, project.id) if g.slot_id == slot_id),
        None,
    )
    if group is None:
        raise HTTPException(404, "slot not found")
    return group


@router.post("/{slot_id}/variants", status_code=202)
async def add_variant(
    slot_id: str,
    project: ProjectDep,
    store: StoreDep,
    blobs: BlobsDep,
    bus: BusDep,
    user: UserDep,
    background: BackgroundTasks,
    file: UploadFile,
) -> ImageAsset:
    """Add a competing candidate to this slot. The agent reviews it on arrival."""
    guard(project, user, Permission.UPLOAD_IMAGES)
    await _require_group(store, project, slot_id)

    if file.content_type not in ACCEPTED_TYPES:
        raise HTTPException(415, f"unsupported type {file.content_type}")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "larger than 20MB")

    try:
        asset = await slot_service.add_variant(
            store, blobs, project, user, slot_id, file.filename or "variant.png", data
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    # Upload is the only review trigger (decision 15): a new variant is new work.
    run = await repo.load(store, Run, asset.run_id)
    if run is not None:
        background.add_task(
            run_service.review_one, store, blobs, bus, project, run, asset.id
        )
    return asset


@router.get("/{slot_id}/delete_preview")
async def delete_preview(
    slot_id: str, project: ProjectDep, store: StoreDep, user: UserDep
) -> dict[str, int]:
    guard(project, user, Permission.DELETE_IMAGE)
    group = await _require_group(store, project, slot_id)
    return await slot_service.delete_preview_for_slot(store, group)


@router.delete("/{slot_id}", status_code=204)
async def delete_slot(
    slot_id: str, project: ProjectDep, store: StoreDep, blobs: BlobsDep, user: UserDep
) -> None:
    """Owner removes the whole creative intent — every variant and its history."""
    guard(project, user, Permission.DELETE_IMAGE)
    try:
        await run_service.delete_slot(store, blobs, project, user, slot_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


class RenameSlot(BaseModel):
    name: str


@router.post("/{slot_id}/name")
async def rename_slot(
    slot_id: str, body: RenameSlot, project: ProjectDep, store: StoreDep, user: UserDep
) -> Slot:
    """Name the creative intent. A synthetic slot becomes a real one when named."""
    guard(project, user, Permission.UPLOAD_IMAGES)
    group = await _require_group(store, project, slot_id)

    slot = await repo.load(store, Slot, slot_id)
    if slot is None:
        slot = Slot(id=slot_id, project_id=project.id)
        # Naming a legacy slot is what finally writes it down; its variants have
        # pointed at this id all along, so they need to start saying so.
        for chain in group.variants:
            for asset in chain.versions:
                asset.slot_id = slot_id
                await repo.save(store, asset)

    slot.name = body.name.strip()
    await repo.save(store, slot)
    return slot
