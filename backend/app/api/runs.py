"""Batch upload, the live activity stream, and serving stored images."""

import asyncio
import json

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from app.api.deps import BlobsDep, BusDep, ProjectDep, StoreDep, UserDep, guard
from app.domain.entities import DefectRecord, ImageAsset, Run
from app.domain.permissions import Permission
from app.infra import repository as repo
from app.services import recheck as recheck_service
from app.services import runs as run_service

router = APIRouter(prefix="/api", tags=["runs"])

ACCEPTED_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

#: Comment interval that keeps proxies from closing an idle SSE connection.
HEARTBEAT_SECONDS = 20


class ImageView(BaseModel):
    image: ImageAsset
    defects: list[DefectRecord]
    original_url: str
    annotated_url: str | None = None
    gridded_url: str | None = None


@router.post("/projects/{project_id}/runs", status_code=202)
async def start_run(
    project: ProjectDep,
    store: StoreDep,
    blobs: BlobsDep,
    bus: BusDep,
    user: UserDep,
    background: BackgroundTasks,
    files: list[UploadFile],
) -> Run:
    """Accept a batch and start processing it. Returns immediately; watch /events."""
    guard(project, user, Permission.UPLOAD_IMAGES)
    if not files:
        raise HTTPException(400, "no files uploaded")

    uploads: list[tuple[str, bytes]] = []
    for upload in files:
        if upload.content_type not in ACCEPTED_TYPES:
            raise HTTPException(415, f"{upload.filename}: unsupported type {upload.content_type}")
        data = await upload.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"{upload.filename} is larger than 20MB")
        uploads.append((upload.filename or "upload.png", data))

    run = await run_service.create_run(store, blobs, project, user, uploads)
    background.add_task(run_service.execute_run, store, blobs, bus, project, run)
    return run


@router.get("/projects/{project_id}/runs")
async def list_runs(project: ProjectDep, store: StoreDep) -> list[Run]:
    return await repo.find(
        store, Run, where={"project_id": project.id}, order_by="created_at", descending=True
    )


@router.get("/projects/{project_id}/runs/{run_id}")
async def get_run(run_id: str, project: ProjectDep, store: StoreDep) -> Run:
    run = await repo.load(store, Run, run_id)
    if run is None or run.project_id != project.id:
        raise HTTPException(404, "run not found")
    return run


@router.get("/projects/{project_id}/images")
async def list_images(
    project: ProjectDep, store: StoreDep, blobs: BlobsDep, run_id: str | None = None
) -> list[ImageView]:
    where = {"project_id": project.id} | ({"run_id": run_id} if run_id else {})
    images = await repo.find(store, ImageAsset, where=where, order_by="created_at")
    return [await _image_view(store, blobs, image) for image in images]


@router.get("/projects/{project_id}/images/{image_id}")
async def get_image(
    image_id: str, project: ProjectDep, store: StoreDep, blobs: BlobsDep
) -> ImageView:
    image = await repo.load(store, ImageAsset, image_id)
    if image is None or image.project_id != project.id:
        raise HTTPException(404, "image not found")
    return await _image_view(store, blobs, image)


async def _image_view(store, blobs, image: ImageAsset) -> ImageView:
    return ImageView(
        image=image,
        defects=await repo.defects_for_image(store, image.id),
        original_url=blobs.public_url(image.original_path),
        annotated_url=blobs.public_url(image.annotated_path) if image.annotated_path else None,
        gridded_url=blobs.public_url(image.gridded_path) if image.gridded_path else None,
    )


class FixSubmitted(BaseModel):
    version: ImageAsset
    #: Defects now awaiting the agent's verdict. Nobody closed them by hand.
    submitted: list[DefectRecord]


@router.post("/projects/{project_id}/images/{image_id}/versions", status_code=202)
async def submit_fix(
    image_id: str,
    project: ProjectDep,
    store: StoreDep,
    blobs: BlobsDep,
    bus: BusDep,
    user: UserDep,
    background: BackgroundTasks,
    file: UploadFile,
) -> FixSubmitted:
    """Upload a fixed version. The agent re-checks it and decides what is resolved."""
    guard(project, user, Permission.SUBMIT_FIX)

    original = await repo.load(store, ImageAsset, image_id)
    if original is None or original.project_id != project.id:
        raise HTTPException(404, "image not found")
    if file.content_type not in ACCEPTED_TYPES:
        raise HTTPException(415, f"unsupported type {file.content_type}")

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "larger than 20MB")

    version, submitted = await recheck_service.submit_fix(
        store, blobs, project, original, user, file.filename or original.filename, data
    )
    background.add_task(
        recheck_service.run_recheck, store, blobs, bus, project, original, version
    )
    return FixSubmitted(version=version, submitted=submitted)


@router.get("/projects/{project_id}/images/{image_id}/versions")
async def list_versions(
    image_id: str, project: ProjectDep, store: StoreDep
) -> list[ImageAsset]:
    image = await repo.load(store, ImageAsset, image_id)
    if image is None or image.project_id != project.id:
        raise HTTPException(404, "image not found")
    return await recheck_service.version_history(store, image)


# --- live activity feed ---------------------------------------------------


@router.get("/projects/{project_id}/events")
async def stream_events(request: Request, project: ProjectDep, bus: BusDep) -> StreamingResponse:
    """Server-sent events: the agent narrating its own work."""
    queue = bus.subscribe(project.id)

    async def generator():
        try:
            yield ": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield f"data: {json.dumps(event.to_payload())}\n\n"
        finally:
            bus.unsubscribe(project.id, queue)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # stop nginx-style proxies buffering the stream
        },
    )


# --- stored images --------------------------------------------------------


@router.get("/blobs/{path:path}")
async def get_blob(path: str, blobs: BlobsDep, user: UserDep) -> Response:
    """Serve a stored image. Signed-in members only — assets are not public."""
    if ".." in path:
        raise HTTPException(400, "invalid path")
    if not await blobs.exists(path):
        raise HTTPException(404, "not found")

    data = await blobs.read(path)
    return Response(
        content=data,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=3600"},
    )
