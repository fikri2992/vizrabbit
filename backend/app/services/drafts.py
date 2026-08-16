"""Agent-drafted fixes: verdict → candidate branch (decision 21).

The drafting pass runs once per run, after every verdict has landed. It only
touches what is mechanical and reversible: defects in the category whitelist,
turned into ONE edit call per image, saved as an ordinary branch version whose
author is the agent. The tree is the license — nothing is overwritten, discard
is one click, and approval never leaves the human.

Creative categories never reach the editor. A slot whose owner discarded a
draft is out of the drafting business (``Slot.no_drafts``) until someone says
otherwise.
"""

import logging
from uuid import uuid4

from app.agents import editor
from app.domain.entities import DefectRecord, ImageAsset, ImageStatus, Project, Run, Slot, now
from app.domain.grid import Grid
from app.domain.lifecycle import Actor, DefectState, assert_transition
from app.domain.taxonomy import Category
from app.imaging.canvas import from_bytes, to_png_bytes
from app.imaging.grid_overlay import apply_grid
from app.infra import repository as repo
from app.infra.events import Event, EventBus
from app.infra.storage import GRIDDED, ORIGINAL, BlobStore, blob_path
from app.infra.store import Store
from app.services import recheck as recheck_service

logger = logging.getLogger(__name__)

#: The one identity the agent signs its versions with.
AGENT_USER_ID = "agent:qa"

#: What the editor is allowed to touch: AI-slop the edit model can repair
#: without a creative call. BRAND and MEMORY stay with humans — recolouring a
#: designed element or reinterpreting a project rule is not mechanical.
MECHANICAL: frozenset[Category] = frozenset({Category.ANATOMY, Category.ARTIFACT})


def is_draft(asset: ImageAsset) -> bool:
    return asset.uploaded_by == AGENT_USER_ID


async def draft_pass(
    store: Store, blobs: BlobStore, bus: EventBus, project: Project, run: Run
) -> list[ImageAsset]:
    """Draft a fix for each of the run's images that earns one. Never raises —
    a failed draft is a missing convenience, not a failed run."""
    drafts: list[ImageAsset] = []
    for image_id in run.image_ids:
        try:
            draft = await _draft_one(store, blobs, bus, project, image_id)
        except Exception:  # noqa: BLE001 — drafting must never take the run down
            logger.exception("draft pass failed for image %s", image_id)
            continue
        if draft is not None:
            drafts.append(draft)
    return drafts


async def _draft_one(
    store: Store, blobs: BlobStore, bus: EventBus, project: Project, image_id: str
) -> ImageAsset | None:
    original = await repo.load(store, ImageAsset, image_id)
    if original is None or original.status is not ImageStatus.DONE:
        return None

    if original.slot_id:
        slot = await repo.load(store, Slot, original.slot_id)
        if slot is not None and slot.no_drafts:
            return None  # this slot's owner said: propose, don't draft

    # Someone (or an earlier pass) already superseded this version — leave it be.
    siblings = await repo.find(store, ImageAsset, where={"run_id": original.run_id})
    if any(asset.supersedes_id == original.id for asset in siblings):
        return None

    defects = await repo.defects_for_image(store, original.id)
    # OPEN only, never needs_human_review: a question waiting on a person is not
    # the agent's to act on. And only the mechanical whitelist reaches the editor.
    targets = [
        d for d in defects if d.status is DefectState.OPEN and d.category in MECHANICAL
    ]
    if not targets:
        return None

    original_png = await blobs.read(original.original_path)
    edited = await editor.draft_fix(original_png, [d.comment for d in targets])
    if edited is None:
        return None

    image = from_bytes(edited)
    draft = ImageAsset(
        id=uuid4().hex,
        project_id=project.id,
        run_id=original.run_id,
        filename=original.filename,
        slot_id=original.slot_id,
        variant=original.variant,
        version=original.version + 1,
        uploaded_by=AGENT_USER_ID,
        supersedes_id=original.id,
        width=image.width,
        height=image.height,
        status=ImageStatus.QUEUED,
    )
    grid = Grid.for_image(image.width, image.height)
    draft.original_path = await blobs.write(
        blob_path(project.id, draft.id, ORIGINAL), to_png_bytes(image)
    )
    draft.gridded_path = await blobs.write(
        blob_path(project.id, draft.id, GRIDDED), to_png_bytes(apply_grid(image, grid))
    )
    await repo.save(store, draft)

    for defect in targets:
        assert_transition(defect.status, DefectState.FIX_SUBMITTED, Actor.AGENT)
        defect.status = DefectState.FIX_SUBMITTED
        defect.resolved_in_image_id = draft.id
        defect.updated_at = now()
        await repo.save(store, defect)

    await bus.publish(
        Event(
            stage="draft_created",
            project_id=project.id,
            run_id=original.run_id,
            detail={
                "image_id": draft.id,
                "supersedes": original.id,
                "filename": original.filename,
                "defects": len(targets),
                "note": (
                    f"drafted a fix for {len(targets)} mechanical defect(s) — "
                    "it is a branch, approving stays yours"
                ),
            },
        )
    )

    # The draft is a fix like any other: the same recheck judges it (gate 11).
    await recheck_service.run_recheck(store, blobs, bus, project, original, draft)
    return draft


async def discard_draft(
    store: Store, blobs: BlobStore, project: Project, draft: ImageAsset
) -> None:
    """Delete an agent draft and put the world back exactly as it was.

    Defects the draft claimed reopen (their fix is gone — the delete-image
    precedent: records tied to an image change with it), and the slot remembers
    to propose rather than draft from now on.
    """
    if not is_draft(draft):
        raise ValueError("only agent drafts can be discarded")
    everything = await repo.find(store, ImageAsset, where={"run_id": draft.run_id})
    if any(asset.supersedes_id == draft.id for asset in everything):
        raise ValueError("this draft already has versions built on it")

    claimed = await repo.find(
        store, DefectRecord, where={"resolved_in_image_id": draft.id}
    )
    for defect in claimed:
        defect.status = DefectState.OPEN
        defect.resolved_in_image_id = None
        defect.updated_at = now()
        await repo.save(store, defect)

    for path in (draft.original_path, draft.gridded_path, draft.annotated_path):
        if path:
            await blobs.delete(path)
    await repo.delete(store, ImageAsset, draft.id)

    if draft.slot_id:
        slot = await repo.load(store, Slot, draft.slot_id)
        if slot is None:
            slot = Slot(id=draft.slot_id, project_id=project.id)
        slot.no_drafts = True
        await repo.save(store, slot)
