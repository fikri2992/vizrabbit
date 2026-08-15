"""Review threads API: anchored comments, replies, resolve, ask-agent."""

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import BlobsDep, BusDep, ProjectDep, StoreDep, UserDep
from app.domain.annotations import Shape
from app.domain.entities import Comment, ImageAsset, Project, ReviewThread
from app.domain.permissions import PermissionError_
from app.infra import repository as repo
from app.services import threads as service

router = APIRouter(prefix="/api/projects/{project_id}", tags=["threads"])


class CreateThread(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    shapes: list[Shape] = Field(min_length=1, max_length=20)
    ask_agent: bool = False


class Reply(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class Resolve(BaseModel):
    resolved: bool


class ThreadView(BaseModel):
    thread: ReviewThread
    comments: list[Comment]


async def _image(store, project: Project, image_id: str) -> ImageAsset:
    image = await repo.load(store, ImageAsset, image_id)
    if image is None or image.project_id != project.id:
        raise HTTPException(404, "image not found")
    return image


async def _thread(store, project: Project, thread_id: str) -> ReviewThread:
    thread = await repo.load(store, ReviewThread, thread_id)
    if thread is None or thread.project_id != project.id:
        raise HTTPException(404, "thread not found")
    return thread


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError_):
        return HTTPException(403, str(exc))
    return HTTPException(400, str(exc))


@router.get("/images/{image_id}/threads")
async def list_threads(image_id: str, project: ProjectDep, store: StoreDep) -> list[ThreadView]:
    await _image(store, project, image_id)
    threads = await repo.threads_for_image(store, image_id)
    return [
        ThreadView(thread=thread, comments=await repo.comments_for_defect(store, thread.id))
        for thread in threads
    ]


@router.post("/images/{image_id}/threads", status_code=201)
async def create_thread(
    image_id: str,
    payload: CreateThread,
    project: ProjectDep,
    store: StoreDep,
    blobs: BlobsDep,
    bus: BusDep,
    user: UserDep,
    background: BackgroundTasks,
) -> ThreadView:
    """Draw, comment, optionally hand the region to the agent."""
    image = await _image(store, project, image_id)
    try:
        thread, comment = await service.create_thread(
            store, project, image, user, payload.body, payload.shapes
        )
        if payload.ask_agent:
            # Permission checked now so the caller gets the 403, not a background log.
            from app.domain.permissions import Permission, require

            require(project, user.id, Permission.ASK_AGENT)
            background.add_task(
                service.ask_agent, store, blobs, bus, project, image, thread, user, payload.body
            )
    except (PermissionError_, ValueError) as exc:
        raise _translate(exc) from exc

    return ThreadView(thread=thread, comments=[comment])


@router.post("/threads/{thread_id}/comments", status_code=201)
async def reply(
    thread_id: str, payload: Reply, project: ProjectDep, store: StoreDep, user: UserDep
) -> Comment:
    thread = await _thread(store, project, thread_id)
    try:
        return await service.reply(store, project, thread, user, payload.body)
    except (PermissionError_, ValueError) as exc:
        raise _translate(exc) from exc


@router.post("/threads/{thread_id}/resolve")
async def resolve(
    thread_id: str, payload: Resolve, project: ProjectDep, store: StoreDep, user: UserDep
) -> ReviewThread:
    thread = await _thread(store, project, thread_id)
    try:
        return await service.resolve(store, project, thread, user, payload.resolved)
    except PermissionError_ as exc:
        raise _translate(exc) from exc
