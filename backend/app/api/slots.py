"""Slots: the project's work list, and the history tree behind each card."""

from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile
from pydantic import BaseModel

from app.api.deps import BlobsDep, BusDep, ProjectDep, StoreDep, UserDep, guard
from app.domain.entities import ImageAsset, MarkDismissal, Project, Run, Slot, now
from app.domain.marks import marks_for, parse_aspect
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


class MarkView(BaseModel):
    kind: str
    label: str
    detail: str
    key: str


class SlotView(BaseModel):
    slot_id: str
    name: str
    state: SlotState
    #: True while this slot exists only as a read-time wrapper around legacy data.
    synthetic: bool
    #: The definition of done, empty unless someone set one (decision 19 glossary).
    spec: list[str] = []
    due_at: datetime | None = None
    #: Derived attention marks (decision 20), already filtered by this user's dismissals.
    marks: list[MarkView] = []
    variants: list[VariantView]


def _display_name(project: Project, user_id: str) -> str:
    if user_id.startswith("agent:"):
        return "QA agent"
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
async def list_slots(
    project: ProjectDep, store: StoreDep, blobs: BlobsDep, user: UserDep
) -> list[SlotView]:
    """The project's work list. Legacy images appear as one-variant slots.

    Marks are computed here on every read (decision 20) and filtered by the
    reading user's dismissals — nothing about them is ever stored.
    """
    groups = await slot_service.project_slots(store, project.id)
    signals = await slot_service.defect_signals(store, groups)
    counts = {image_id: signal.open_count for image_id, signal in signals.items()}
    stored = {slot.id: slot for slot in await repo.slots_for_project(store, project.id)}
    dismissed = await repo.dismissed_mark_keys(store, project.id, user.id)

    views = []
    for group in groups:
        slot = stored.get(group.slot_id)
        state = slot_state(group, counts)
        marks = [
            m
            for m in marks_for(group, slot, state, signals, now())
            if m.key not in dismissed
        ]
        view = await _view(
            store, blobs, project, group,
            (slot.name if slot else "") or _fallback_name(group), counts,
        )
        view.spec = slot.spec if slot else []
        view.due_at = slot.due_at if slot else None
        view.marks = [
            MarkView(kind=m.kind, label=m.label, detail=m.detail, key=m.key) for m in marks
        ]
        views.append(view)
    return views


class SetSpec(BaseModel):
    spec: list[str]
    due_at: datetime | None = None


@router.post("/{slot_id}/spec")
async def set_spec(
    slot_id: str, body: SetSpec, project: ProjectDep, store: StoreDep, user: UserDep
) -> Slot:
    """Confirm the slot's definition of done. Humans confirm specs — always."""
    guard(project, user, Permission.UPLOAD_IMAGES)
    group = await _require_group(store, project, slot_id)

    cleaned = [entry.strip() for entry in body.spec if entry.strip()]
    for entry in cleaned:
        if parse_aspect(entry) is None:
            raise HTTPException(400, f"'{entry}' is not an aspect like 16:9")

    slot = await repo.load(store, Slot, slot_id)
    if slot is None:
        # Like naming: giving a legacy slot a spec is what finally writes it down.
        slot = Slot(id=slot_id, project_id=project.id)
        for chain in group.variants:
            for asset in chain.versions:
                asset.slot_id = slot_id
                await repo.save(store, asset)

    slot.spec = cleaned
    slot.due_at = body.due_at
    await repo.save(store, slot)
    return slot


class DismissMark(BaseModel):
    key: str


@router.post("/marks/dismiss", status_code=204)
async def dismiss_mark(
    body: DismissMark, project: ProjectDep, store: StoreDep, user: UserDep
) -> None:
    """Store the one storable fact about a mark: this user said stop."""
    await repo.save(
        store,
        MarkDismissal(
            id=uuid4().hex, project_id=project.id, user_id=user.id, key=body.key.strip()
        ),
    )


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
