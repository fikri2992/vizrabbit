"""Animate an approved still into a motion variant (decision 24).

The airlock applies to what the agent makes as much as to what people bring:
the Veo output lands as an ordinary agent-authored variant of the same slot
and gets the full video review pass. It is never approved, exported or
privileged by construction — it competes like any other variant.

Split in two because Veo is minutes-slow: ``resolve_animation`` validates
synchronously so the API can refuse with a real status code, and
``run_animation`` does the slow work in the background, reporting through the
activity feed like everything else.
"""

import logging

from app.agents import animator
from app.domain.entities import ImageAsset, Project, Run, Slot, User
from app.domain.permissions import Permission, require
from app.infra import repository as repo
from app.infra.events import Event, EventBus
from app.infra.storage import BlobStore
from app.infra.store import Store
from app.services import runs as run_service
from app.services import slots as slot_service
from app.services.drafts import AGENT_USER_ID

logger = logging.getLogger(__name__)


async def resolve_animation(
    store: Store, project: Project, user: User, slot_id: str, brief: str
) -> ImageAsset:
    """Validate and return the approved asset the animation will start from.

    Raises so the API can answer before any model budget is spent; everything
    after this point is background work.
    """
    require(project, user.id, Permission.ANIMATE_APPROVED)
    if not brief.strip():
        raise ValueError("the motion brief cannot be empty")

    groups = await slot_service.project_slots(store, project.id)
    group = next((g for g in groups if g.slot_id == slot_id), None)
    if group is None:
        raise LookupError("slot not found in this project")
    winner = group.winner
    if winner is None or winner.approved_version is None:
        raise ValueError("only a completed slot can be animated — approve a variant first")
    approved = winner.approved_version
    if approved.kind == "video":
        raise ValueError("this slot's approved asset is already a video")
    return approved


async def run_animation(
    store: Store,
    blobs: BlobStore,
    bus: EventBus,
    project: Project,
    user: User,
    slot_id: str,
    approved: ImageAsset,
    brief: str,
    placement: str = "",
) -> Run | None:
    """The slow half: Veo call, then the ordinary upload path end to end.

    Never raises — this runs detached from any request, so failures become
    feed events rather than stack traces nobody sees.
    """
    slot = await repo.load(store, Slot, slot_id)
    label = (slot.name if slot else "") or approved.filename.rsplit(".", 1)[0]

    await bus.publish(
        Event(
            stage="animation_started",
            project_id=project.id,
            detail={
                "slot_id": slot_id,
                "note": f"animating “{label}” from its approved still — this takes a few minutes",
            },
        )
    )
    try:
        mp4 = await animator.animate(await blobs.read(approved.original_path), brief)
    except Exception:  # noqa: BLE001 — background work reports, never raises
        logger.exception("animation failed for slot %s", slot_id)
        mp4 = None
    if mp4 is None or not run_service.is_video(mp4):
        await bus.publish(
            Event(
                stage="animation_failed",
                project_id=project.id,
                detail={
                    "slot_id": slot_id,
                    "note": f"the video model produced nothing usable for “{label}”",
                },
            )
        )
        return None

    run = await run_service.create_run(
        store,
        blobs,
        project,
        user,
        [(f"{label}-motion.mp4", mp4)],
        group_into=slot_id,
        placement=placement,
        author=AGENT_USER_ID,
    )
    await bus.publish(
        Event(
            stage="animation_created",
            project_id=project.id,
            run_id=run.id,
            detail={
                "slot_id": slot_id,
                "image_id": run.image_ids[0],
                "note": (
                    f"animated “{label}” from its approved still — "
                    "a new variant, it goes through review like anything else"
                ),
            },
        )
    )
    await run_service.execute_run(store, blobs, bus, project, run)
    return run
