"""Review threads: a human draws on the frame, comments, and can pull the agent in.

The frame.io interaction adapted to an agentic reviewer. Creating a thread is a
COMMENT-level act; asking the agent to inspect the drawn region spends model
budget and is ASK_AGENT (reviewer and owner). A confirmed inspection becomes a
real defect that keeps the thread's pin, so the canvas numbering stays one story.
"""

from uuid import uuid4

from app.agents.pipeline import inspect
from app.agents.schemas import Suspect
from app.domain.annotations import Shape, shapes_to_cells
from app.domain.entities import (
    Circle,
    Comment,
    DefectRecord,
    ImageAsset,
    Project,
    Region,
    ReviewThread,
    ThreadAgentState,
    User,
)
from app.domain.grid import Grid
from app.domain.permissions import Permission, require
from app.domain.taxonomy import Category, Severity
from app.infra import repository as repo
from app.infra.events import Event, EventBus
from app.infra.storage import BlobStore
from app.infra.store import Store
from app.services.runs import assemble_guidelines


def new_id() -> str:
    return uuid4().hex


async def next_pin(store: Store, image_id: str) -> int:
    """One pin sequence across defects and human threads for an image."""
    defects = await repo.defects_for_image(store, image_id)
    threads = await repo.threads_for_image(store, image_id)
    taken = [d.pin for d in defects] + [t.pin for t in threads]
    return max(taken, default=0) + 1


async def create_thread(
    store: Store,
    project: Project,
    image: ImageAsset,
    user: User,
    body: str,
    shapes: list[Shape],
) -> tuple[ReviewThread, Comment]:
    """Anchor a comment to a drawn region. Every comment is anchored — no floaters."""
    require(project, user.id, Permission.COMMENT)
    if not body.strip():
        raise ValueError("a comment needs a body")
    if not shapes:
        raise ValueError("draw on the image first — every comment anchors to a region")

    thread = ReviewThread(
        id=new_id(),
        project_id=project.id,
        image_id=image.id,
        pin=await next_pin(store, image.id),
        author_id=user.id,
        author_name=user.name or user.email,
        shapes=shapes,
    )
    await repo.save(store, thread)

    comment = Comment(
        id=new_id(),
        project_id=project.id,
        defect_id=thread.id,
        author_id=user.id,
        author_name=user.name or user.email,
        body=body.strip(),
    )
    await repo.save(store, comment)
    return thread, comment


async def reply(
    store: Store, project: Project, thread: ReviewThread, user: User, body: str
) -> Comment:
    require(project, user.id, Permission.COMMENT)
    if not body.strip():
        raise ValueError("a comment needs a body")

    comment = Comment(
        id=new_id(),
        project_id=project.id,
        defect_id=thread.id,
        author_id=user.id,
        author_name=user.name or user.email,
        body=body.strip(),
    )
    await repo.save(store, comment)
    return comment


async def resolve(
    store: Store, project: Project, thread: ReviewThread, user: User, resolved: bool
) -> ReviewThread:
    """Human threads are conversation, not lifecycle: participants close their own.

    A thread that produced a confirmed defect is different — that defect lives in
    the defect lifecycle and only closes through re-check or the owner.
    """
    require(project, user.id, Permission.COMMENT)
    thread.resolved = resolved
    await repo.save(store, thread)
    return thread


async def ask_agent(
    store: Store,
    blobs: BlobStore,
    bus: EventBus,
    project: Project,
    image: ImageAsset,
    thread: ReviewThread,
    user: User,
    question: str,
) -> None:
    """Run the Inspector on the drawn region and reply in the thread.

    The same precision stage the pipeline uses, pointed at a human-chosen crop
    with the human's question as the hypothesis. If it confirms a defect, a real
    DefectRecord is created carrying the thread's pin.
    """
    require(project, user.id, Permission.ASK_AGENT)

    from app.imaging.canvas import from_bytes

    full = from_bytes(await blobs.read(image.original_path))
    grid = Grid.for_image(full.width, full.height)
    cells = shapes_to_cells(thread.shapes, grid)

    async def publish(stage: str, **detail) -> None:
        await bus.publish(
            Event(
                stage=stage,
                project_id=project.id,
                run_id=image.run_id,
                detail={**detail, "image_id": image.id, "thread_id": thread.id, "pin": thread.pin},
            )
        )

    thread.agent_state = ThreadAgentState.INSPECTING
    await repo.save(store, thread)
    await publish("thread_inspecting", cells=cells)

    try:
        guidelines = await assemble_guidelines(store, project.id)
        verdict = await inspect(
            full,
            grid,
            Suspect(
                cells=cells,
                category=Category.ARTIFACT,
                hypothesis=question or "The reviewer flagged this region — check it closely.",
                confidence=0.5,
            ),
            guidelines,
        )
    except Exception as exc:
        thread.agent_state = ThreadAgentState.FAILED
        await repo.save(store, thread)
        await repo.save(
            store,
            Comment(
                id=new_id(),
                project_id=project.id,
                defect_id=thread.id,
                author_id="agent",
                author_name="QA agent",
                is_agent=True,
                body=f"I couldn't complete the inspection: {str(exc)[:160]}",
            ),
        )
        await publish("thread_inspect_failed", error=str(exc)[:160])
        return

    if verdict.confirmed:
        severity = verdict.severity or Severity.WARNING
        defect_cells = verdict.cells or cells
        cx, cy, radius = grid.circle_for(defect_cells)
        span = grid.span_bounds(defect_cells)
        defect = DefectRecord(
            id=new_id(),
            project_id=project.id,
            image_id=image.id,
            pin=thread.pin,
            cells=defect_cells,
            category=verdict.category or Category.ARTIFACT,
            severity=severity,
            comment=verdict.comment or verdict.reason,
            circle=Circle(cx=cx, cy=cy, radius=radius),
            region=Region(
                left=span.left, top=span.top, width=span.width, height=span.height
            ),
        )
        await repo.save(store, defect)
        thread.defect_id = defect.id
        body = (
            f"Confirmed — {verdict.comment or verdict.reason} "
            f"Logged as a {severity.value} defect."
        )
    else:
        body = f"I looked closely and don't see a defect here: {verdict.reason}"

    thread.agent_state = ThreadAgentState.ANSWERED
    await repo.save(store, thread)
    await repo.save(
        store,
        Comment(
            id=new_id(),
            project_id=project.id,
            defect_id=thread.id,
            author_id="agent",
            author_name="QA agent",
            is_agent=True,
            body=body,
        ),
    )
    await publish("thread_answered", confirmed=verdict.confirmed)
