"""Every query the app issues must be one Firestore can actually run.

Firestore refuses a query that combines an equality filter with an order_by on a
different field unless a composite index exists — and it does not create one on
demand, it fails the request. ``InMemoryStore`` happily serves those queries, so
the whole test suite stays green while production returns 500. That gap shipped
once; this closes it.

The store here is a real ``InMemoryStore`` that also records the shape of what it
was asked. Nothing is faked: the queries run and return real data, and the
recording is the only way to see a property that is invisible from the results.
"""

import json
from pathlib import Path

import pytest

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
)
from app.infra import repository as repo
from app.infra.store import InMemoryStore

INDEX_FILE = Path(__file__).resolve().parents[2] / "firestore.indexes.json"


class RecordingStore(InMemoryStore):
    """A real store that remembers the shape of each query it served."""

    def __init__(self) -> None:
        super().__init__()
        self.queries: list[dict] = []

    async def query(self, collection, where=None, order_by=None, descending=False, limit=None):
        self.queries.append(
            {"collection": collection, "where": dict(where or {}), "order_by": order_by}
        )
        return await super().query(collection, where, order_by, descending, limit)


def declared_indexes() -> list[dict]:
    return json.loads(INDEX_FILE.read_text())["indexes"]


def is_covered(query: dict, indexes: list[dict]) -> bool:
    """Does a declared composite index serve this equality-plus-order_by query?

    Firestore matches an index whose leading fields are the equality filters, in
    any order, followed by the ordered field.
    """
    filters = set(query["where"])
    for index in indexes:
        if index["collectionGroup"] != query["collection"]:
            continue
        paths = [field["fieldPath"] for field in index["fields"]]
        if paths and paths[-1] == query["order_by"] and set(paths[:-1]) == filters:
            return True
    return False


async def exercise_every_repository_query(store: RecordingStore) -> None:
    """Call every read helper the API layer uses, against an empty but real store."""
    await repo.projects_for_user(store, "u1")
    await repo.images_for_run(store, "r1")
    await repo.images_for_project(store, "p1")
    await repo.images_for_slot(store, "s1")
    await repo.slots_for_project(store, "p1")
    await repo.defects_for_image(store, "i1")
    await repo.dismissals_for_image(store, "i1")
    await repo.comments_for_defect(store, "d1")
    await repo.threads_for_image(store, "i1")
    await repo.active_guidelines(store, "p1")
    await repo.active_memory_rules(store, "p1")
    await repo.unread_notifications(store, "u1")

    # The reads the project cascade and the brand profile do directly.
    for model in (Run, Guideline, MemoryRule, BrandProfile, Notification):
        await repo.find(store, model, where={"project_id": "p1"})
    for model in (
        Project,
        Slot,
        ImageAsset,
        DefectRecord,
        DismissalRecord,
        ReviewThread,
        Comment,
    ):
        await repo.find(store, model)


@pytest.mark.anyio
async def test_every_filtered_and_ordered_query_has_an_index():
    store = RecordingStore()
    await exercise_every_repository_query(store)

    needs_index = [q for q in store.queries if q["where"] and q["order_by"]]
    assert needs_index, "the recorder saw nothing — the exercise list has gone stale"

    indexes = declared_indexes()
    missing = [q for q in needs_index if not is_covered(q, indexes)]

    assert missing == [], (
        "these queries combine a filter with an order_by but have no composite "
        "index, so Firestore will reject them in production even though the "
        f"in-memory store serves them: {missing}"
    )


@pytest.mark.anyio
async def test_the_slot_reads_added_in_phase_6_need_no_index():
    """Regression: these two 500'd against real Firestore on their first outing.

    Neither caller cares about ordering, so they filter only and sort in Python.
    Re-adding an order_by here is free locally and broken in production.
    """
    store = RecordingStore()
    await repo.slots_for_project(store, "p1")
    await repo.images_for_slot(store, "s1")

    assert [query["order_by"] for query in store.queries] == [None, None]


@pytest.mark.anyio
async def test_slots_still_come_back_oldest_first():
    """Dropping order_by must not drop the ordering callers rely on."""
    from datetime import UTC, datetime, timedelta

    store = RecordingStore()
    base = datetime(2026, 8, 16, tzinfo=UTC)
    for index, minutes in enumerate([30, 0, 15]):
        await repo.save(
            store,
            Slot(
                id=f"s{index}",
                project_id="p1",
                name=str(index),
                created_at=base + timedelta(minutes=minutes),
            ),
        )

    assert [slot.id for slot in await repo.slots_for_project(store, "p1")] == ["s1", "s2", "s0"]


def test_the_index_file_is_valid_json_with_the_expected_shape():
    document = json.loads(INDEX_FILE.read_text())
    assert isinstance(document["indexes"], list)
    for index in document["indexes"]:
        assert index["collectionGroup"]
        assert index["fields"]
