"""Typed persistence over the ``Store`` interface.

One generic save/load/find trio rather than a method per entity: the collection name
is derived from the model type, so adding an entity means one registry line, not a
new repository class. Everything is serialised as JSON-safe primitives so the same
documents round-trip through both store implementations identically.
"""

from typing import TypeVar

from pydantic import BaseModel

from app.domain.entities import (
    BrandProfile,
    Comment,
    DefectRecord,
    DismissalRecord,
    Guideline,
    ImageAsset,
    MemoryRule,
    Notification,
    Project,
    ReviewThread,
    Run,
    Slot,
    User,
)
from app.infra.store import Document, Store

T = TypeVar("T", bound=BaseModel)

COLLECTIONS: dict[type[BaseModel], str] = {
    User: "users",
    Project: "projects",
    Guideline: "guidelines",
    MemoryRule: "memory_rules",
    BrandProfile: "brand_profiles",
    Run: "runs",
    Slot: "slots",
    ImageAsset: "images",
    DefectRecord: "defects",
    DismissalRecord: "dismissals",
    Comment: "comments",
    Notification: "notifications",
    ReviewThread: "threads",
}


async def threads_for_image(store: Store, image_id: str) -> list["ReviewThread"]:
    return await find(store, ReviewThread, where={"image_id": image_id}, order_by="pin")


class UnknownEntity(TypeError):
    pass


def collection_for(model_type: type[BaseModel]) -> str:
    try:
        return COLLECTIONS[model_type]
    except KeyError as exc:
        raise UnknownEntity(f"{model_type.__name__} is not a stored entity") from exc


def to_document(model: BaseModel) -> Document:
    """JSON-safe primitives only — datetimes become sortable ISO strings."""
    return model.model_dump(mode="json")


async def save(store: Store, model: BaseModel) -> None:
    document = to_document(model)
    doc_id = document.get("id")
    if not doc_id:
        raise ValueError(f"{type(model).__name__} has no id")
    await store.put(collection_for(type(model)), doc_id, document)


async def save_all(store: Store, models: list[BaseModel]) -> None:
    for model in models:
        await save(store, model)


async def load[T: BaseModel](store: Store, model_type: type[T], doc_id: str) -> T | None:
    document = await store.get(collection_for(model_type), doc_id)
    return model_type.model_validate(document) if document else None


async def find[T: BaseModel](
    store: Store,
    model_type: type[T],
    where: Document | None = None,
    order_by: str | None = None,
    descending: bool = False,
    limit: int | None = None,
) -> list[T]:
    documents = await store.query(
        collection_for(model_type),
        where=where,
        order_by=order_by,
        descending=descending,
        limit=limit,
    )
    return [model_type.model_validate(document) for document in documents]


async def delete(store: Store, model_type: type[BaseModel], doc_id: str) -> None:
    await store.delete(collection_for(model_type), doc_id)


# --- queries the API actually asks ----------------------------------------


async def projects_for_user(store: Store, user_id: str) -> list[Project]:
    """Membership is nested, so filter in code — the alternative is a denormalised
    member_ids array that can drift out of step with ``members``."""
    everything = await find(store, Project, order_by="created_at", descending=True)
    return [project for project in everything if project.member(user_id)]


async def images_for_run(store: Store, run_id: str) -> list[ImageAsset]:
    return await find(store, ImageAsset, where={"run_id": run_id}, order_by="created_at")


async def images_for_project(store: Store, project_id: str) -> list[ImageAsset]:
    return await find(store, ImageAsset, where={"project_id": project_id}, order_by="created_at")


async def images_for_slot(store: Store, slot_id: str) -> list[ImageAsset]:
    return await find(store, ImageAsset, where={"slot_id": slot_id}, order_by="created_at")


async def slots_for_project(store: Store, project_id: str) -> list[Slot]:
    return await find(store, Slot, where={"project_id": project_id}, order_by="created_at")


async def defects_for_image(store: Store, image_id: str) -> list[DefectRecord]:
    return await find(store, DefectRecord, where={"image_id": image_id}, order_by="pin")


async def dismissals_for_image(store: Store, image_id: str) -> list[DismissalRecord]:
    return await find(store, DismissalRecord, where={"image_id": image_id}, order_by="created_at")


async def comments_for_defect(store: Store, defect_id: str) -> list[Comment]:
    return await find(store, Comment, where={"defect_id": defect_id}, order_by="created_at")


async def active_guidelines(store: Store, project_id: str) -> list[Guideline]:
    return await find(store, Guideline, where={"project_id": project_id, "active": True})


async def active_memory_rules(store: Store, project_id: str) -> list[MemoryRule]:
    """Only Owner-approved rules reach the Scanner."""
    return await find(store, MemoryRule, where={"project_id": project_id, "active": True})


async def unread_notifications(store: Store, user_id: str) -> list[Notification]:
    return await find(
        store,
        Notification,
        where={"user_id": user_id, "read": False},
        order_by="created_at",
        descending=True,
    )
