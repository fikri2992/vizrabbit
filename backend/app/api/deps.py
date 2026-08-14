"""FastAPI dependencies: storage, current user, project access.

Implementation choice is by configuration, not by environment guessing scattered
through the code: give it a GCP project and it uses Firestore and GCS; otherwise it
runs entirely locally so a developer can work without cloud credentials.
"""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Path, Request

from app.api.auth import SESSION_USER_KEY
from app.config import settings
from app.domain.entities import Project, User
from app.domain.permissions import Permission, PermissionError_, require
from app.infra import repository as repo
from app.infra.events import EventBus, bus
from app.infra.storage import BlobStore, GcsBlobStore, LocalBlobStore
from app.infra.store import FirestoreStore, InMemoryStore, Store


@lru_cache(maxsize=1)
def get_store() -> Store:
    if settings.gcp_project:
        return FirestoreStore()
    return InMemoryStore()


@lru_cache(maxsize=1)
def get_blobs() -> BlobStore:
    if settings.gcs_bucket:
        return GcsBlobStore()
    return LocalBlobStore()


def get_bus() -> EventBus:
    return bus


def current_user(request: Request) -> User:
    session_user = request.session.get(SESSION_USER_KEY)
    if not session_user:
        raise HTTPException(401, "not signed in")
    return User(**session_user)


StoreDep = Annotated[Store, Depends(get_store)]
BlobsDep = Annotated[BlobStore, Depends(get_blobs)]
BusDep = Annotated[EventBus, Depends(get_bus)]
UserDep = Annotated[User, Depends(current_user)]


async def project_for_member(
    project_id: Annotated[str, Path()], store: StoreDep, user: UserDep
) -> Project:
    """Load a project the caller is actually a member of.

    404 rather than 403 for non-members: whether a project exists is itself
    information a stranger should not get.
    """
    project = await repo.load(store, Project, project_id)
    if project is None or project.member(user.id) is None:
        raise HTTPException(404, "project not found")
    return project


ProjectDep = Annotated[Project, Depends(project_for_member)]


def guard(project: Project, user: User, permission: Permission) -> None:
    """Translate a domain permission failure into an HTTP 403."""
    try:
        require(project, user.id, permission)
    except PermissionError_ as exc:
        raise HTTPException(403, str(exc)) from exc
