"""Running a batch: persist the uploads, drive the pipeline, stream the progress.

The pipeline itself knows nothing about Firestore, GCS or SSE. This module is the
seam: it feeds the pipeline images, turns its progress hook into bus events, and
writes what comes back.
"""

import asyncio
from uuid import uuid4

from PIL import Image

from app.agents import prompts
from app.agents.pipeline import ImageReport, process_image
from app.domain.entities import (
    Circle,
    Comment,
    DefectRecord,
    DismissalRecord,
    ImageAsset,
    ImageStatus,
    NotificationKind,
    Project,
    Region,
    ReviewThread,
    Run,
    RunStatus,
    User,
    now,
)
from app.domain.grid import Grid
from app.domain.lifecycle import DefectState
from app.domain.permissions import Permission, require
from app.imaging.canvas import from_bytes, to_png_bytes
from app.imaging.grid_overlay import apply_grid
from app.infra import repository as repo
from app.infra.events import Event, EventBus
from app.infra.storage import ANNOTATED, GRIDDED, ORIGINAL, BlobStore, blob_path
from app.infra.store import Store
from app.services.review import notify


def new_id() -> str:
    return uuid4().hex


async def delete_preview(store: Store, image: ImageAsset) -> dict[str, int]:
    """What deleting this image would destroy — shown before the owner confirms."""
    from app.services.recheck import version_history

    lineage = await version_history(store, image)
    defects = comments = dismissals = threads = 0
    for asset in lineage:
        for defect in await repo.defects_for_image(store, asset.id):
            defects += 1
            comments += len(await repo.comments_for_defect(store, defect.id))
        for thread in await repo.threads_for_image(store, asset.id):
            threads += 1
            comments += len(await repo.comments_for_defect(store, thread.id))
        dismissals += len(await repo.dismissals_for_image(store, asset.id))
    return {
        "versions": len(lineage),
        "defects": defects,
        "threads": threads,
        "comments": comments,
        "dismissals": dismissals,
    }


async def delete_image(
    store: Store, blobs: BlobStore, project: Project, user: User, image: ImageAsset
) -> list[str]:
    """Owner removes an upload: the whole version lineage and every record on it.

    This is the one place records die with their image — dismissals and comments
    are never deleted while the image they belong to exists.
    """
    from app.services.recheck import version_history

    require(project, user.id, Permission.DELETE_IMAGE)

    lineage = await version_history(store, image)
    for asset in lineage:
        for defect in await repo.defects_for_image(store, asset.id):
            for comment in await repo.comments_for_defect(store, defect.id):
                await repo.delete(store, Comment, comment.id)
            await repo.delete(store, DefectRecord, defect.id)
        for thread in await repo.threads_for_image(store, asset.id):
            for comment in await repo.comments_for_defect(store, thread.id):
                await repo.delete(store, Comment, comment.id)
            await repo.delete(store, ReviewThread, thread.id)
        for dismissal in await repo.dismissals_for_image(store, asset.id):
            await repo.delete(store, DismissalRecord, dismissal.id)
        for path in (asset.original_path, asset.gridded_path, asset.annotated_path):
            if path:
                await blobs.delete(path)
        await repo.delete(store, ImageAsset, asset.id)
    return [asset.id for asset in lineage]


async def assemble_guidelines(store: Store, project_id: str) -> str:
    """Built-in slop rules, then the project's own guidelines, then memory rules.

    Guidelines are never compiled — the raw text and its clarifications go to the
    model as written (domain-model.md decision 3).
    """
    sections = [prompts.built_in_guideline()]

    for guideline in await repo.active_guidelines(store, project_id):
        sections.append(f"# Project guideline: {guideline.name}\n\n{guideline.as_prompt()}")

    rules = await repo.active_memory_rules(store, project_id)
    if rules:
        listed = "\n".join(f"- `MEM-{rule.id[:6]}` {rule.description}" for rule in rules)
        sections.append(
            "# Memory rules\n\n"
            "Defects this team has promoted to standing checks. Treat them as seriously "
            "as the built-in rules and cite the rule id.\n\n" + listed
        )

    return "\n\n---\n\n".join(sections)


async def create_run(
    store: Store,
    blobs: BlobStore,
    project: Project,
    user: User,
    uploads: list[tuple[str, bytes]],
) -> Run:
    """Persist an upload batch and return the queued run."""
    require(project, user.id, Permission.UPLOAD_IMAGES)
    if not uploads:
        raise ValueError("a run needs at least one image")

    run = Run(id=new_id(), project_id=project.id, started_by=user.id)

    for filename, data in uploads:
        image = from_bytes(data)
        asset = ImageAsset(
            id=new_id(),
            project_id=project.id,
            run_id=run.id,
            filename=filename,
            width=image.width,
            height=image.height,
        )
        asset.original_path = await blobs.write(
            blob_path(project.id, asset.id, ORIGINAL), to_png_bytes(image)
        )
        await repo.save(store, asset)
        run.image_ids.append(asset.id)

    await repo.save(store, run)
    return run


async def execute_run(
    store: Store, blobs: BlobStore, bus: EventBus, project: Project, run: Run
) -> Run:
    """Process every image in the run, streaming progress as it goes."""
    run.status = RunStatus.RUNNING
    await repo.save(store, run)
    await bus.publish(
        Event(
            stage="run_started",
            project_id=project.id,
            run_id=run.id,
            detail={"images": len(run.image_ids)},
        )
    )

    guidelines = await assemble_guidelines(store, project.id)
    semaphore = asyncio.Semaphore(_concurrency())

    async def one(image_id: str) -> None:
        async with semaphore:
            await _process_one(store, blobs, bus, project, run, image_id, guidelines)

    results = await asyncio.gather(
        *(one(image_id) for image_id in run.image_ids), return_exceptions=True
    )

    failures = [r for r in results if isinstance(r, BaseException)]
    run.status = RunStatus.FAILED if len(failures) == len(run.image_ids) else RunStatus.DONE
    run.finished_at = now()
    await repo.save(store, run)

    await bus.publish(
        Event(
            stage="run_finished",
            project_id=project.id,
            run_id=run.id,
            detail={"status": run.status.value, "failed": len(failures)},
        )
    )
    await notify(
        store,
        run.started_by,
        project.id,
        NotificationKind.RUN_FINISHED,
        f"Run finished: {len(run.image_ids)} image(s) reviewed",
        link=f"/projects/{project.id}/runs/{run.id}",
    )
    return run


def _concurrency() -> int:
    from app.config import settings

    return settings.max_concurrent_images


async def _process_one(
    store: Store,
    blobs: BlobStore,
    bus: EventBus,
    project: Project,
    run: Run,
    image_id: str,
    guidelines: str,
) -> None:
    asset = await repo.load(store, ImageAsset, image_id)
    if asset is None:
        return

    async def publish(stage: str, detail: dict) -> None:
        await bus.publish(
            Event(
                stage=stage,
                project_id=project.id,
                run_id=run.id,
                detail={**detail, "image_id": image_id, "filename": asset.filename},
            )
        )

    asset.status = ImageStatus.SCANNING
    await repo.save(store, asset)

    try:
        image = from_bytes(await blobs.read(asset.original_path))
        grid = Grid.for_image(image.width, image.height)

        asset.gridded_path = await blobs.write(
            blob_path(project.id, asset.id, GRIDDED), to_png_bytes(apply_grid(image, grid))
        )

        report = await process_image(image, guidelines, on_progress=publish, grid=grid)
        await _persist_report(store, blobs, project, asset, image, report)

        asset.status = ImageStatus.DONE
        await repo.save(store, asset)
        await publish(
            "image_finished",
            {"defects": len(report.defects), "dismissed": len(report.dismissals)},
        )
    except Exception as exc:
        asset.status = ImageStatus.FAILED
        await repo.save(store, asset)
        await publish("image_failed", {"error": str(exc)})
        raise


async def _persist_report(
    store: Store,
    blobs: BlobStore,
    project: Project,
    asset: ImageAsset,
    image: Image.Image,
    report: ImageReport,
) -> None:
    from app.imaging.annotate import draw_annotations

    grid = Grid.for_image(image.width, image.height)
    for defect in report.defects:
        span = grid.span_bounds(defect.cells)
        await repo.save(
            store,
            DefectRecord(
                id=new_id(),
                project_id=project.id,
                image_id=asset.id,
                pin=defect.pin,
                cells=defect.cells,
                category=defect.category,
                severity=defect.severity,
                comment=defect.comment,
                rule_ref=defect.rule_ref,
                circle=Circle(
                    cx=defect.annotation.cx,
                    cy=defect.annotation.cy,
                    radius=defect.annotation.radius,
                ),
                region=Region(
                    left=span.left, top=span.top, width=span.width, height=span.height
                ),
                circle_iterations=defect.circle_iterations,
                circle_verified=defect.circle_verified,
                status=(
                    DefectState.NEEDS_HUMAN_REVIEW
                    if defect.needs_human_review
                    else DefectState.OPEN
                ),
            ),
        )

    # Golden rule 3: dismissals are logged, never deleted.
    for dismissal in report.dismissals:
        await repo.save(
            store,
            DismissalRecord(
                id=new_id(),
                project_id=project.id,
                image_id=asset.id,
                cells=dismissal.cells,
                hypothesis=dismissal.hypothesis,
                reason=dismissal.reason,
                stage=dismissal.stage,
            ),
        )

    if report.defects:
        annotated = draw_annotations(image, [d.annotation for d in report.defects])
        asset.annotated_path = await blobs.write(
            blob_path(project.id, asset.id, ANNOTATED), to_png_bytes(annotated)
        )
