"""Contract tests for the Store interface, and typed persistence on top of it.

Every test here runs against a real store with real read-back assertions. When a
Firestore emulator is available (``FIRESTORE_EMULATOR_HOST`` set), the same suite
runs against FirestoreStore too, so the two implementations cannot silently diverge.
"""

import os

import pytest

from app.domain.entities import (
    Circle,
    Comment,
    DefectRecord,
    Guideline,
    ImageAsset,
    Member,
    MemoryRule,
    Notification,
    NotificationKind,
    Project,
    Role,
    Run,
    RunStatus,
)
from app.domain.lifecycle import DefectState
from app.domain.taxonomy import Category, Severity
from app.infra import repository as repo
from app.infra.repository import UnknownEntity
from app.infra.store import InMemoryStore, Store


def _stores():
    """Every store implementation available in this environment."""
    options = [pytest.param(InMemoryStore, id="in_memory")]
    if os.getenv("FIRESTORE_EMULATOR_HOST"):
        from app.infra.store import FirestoreStore

        options.append(pytest.param(FirestoreStore, id="firestore_emulator"))
    return options


@pytest.fixture(params=_stores())
def store(request):
    return request.param()


def make_project(project_id="p1", owner="owner") -> Project:
    return Project(
        id=project_id,
        name="Autumn campaign",
        members=[
            Member(user_id=owner, email="owner@acme.com", role=Role.OWNER),
            Member(user_id="designer", email="d@acme.com", role=Role.REVIEWER),
        ],
    )


def make_defect(defect_id="d1", image_id="i1", pin=1) -> DefectRecord:
    return DefectRecord(
        id=defect_id,
        project_id="p1",
        image_id=image_id,
        pin=pin,
        cells=["C4"],
        category=Category.ANATOMY,
        severity=Severity.BLOCKER,
        comment="six fingers",
        rule_ref="ANAT-01",
        circle=Circle(cx=100, cy=100, radius=40),
    )


# --- raw store contract ---------------------------------------------------


async def test_put_then_get_round_trips(store: Store):
    await store.put("things", "a", {"id": "a", "value": 1})
    assert await store.get("things", "a") == {"id": "a", "value": 1}


async def test_get_of_a_missing_document_is_none(store: Store):
    assert await store.get("things", "nope") is None


async def test_put_overwrites(store: Store):
    await store.put("things", "a", {"id": "a", "value": 1})
    await store.put("things", "a", {"id": "a", "value": 2})
    assert (await store.get("things", "a"))["value"] == 2


async def test_delete_removes(store: Store):
    await store.put("things", "a", {"id": "a"})
    await store.delete("things", "a")
    assert await store.get("things", "a") is None


async def test_deleting_a_missing_document_is_not_an_error(store: Store):
    await store.delete("things", "never-existed")


async def test_collections_are_isolated(store: Store):
    await store.put("one", "a", {"id": "a", "from": "one"})
    await store.put("two", "a", {"id": "a", "from": "two"})
    assert (await store.get("one", "a"))["from"] == "one"
    assert (await store.get("two", "a"))["from"] == "two"


async def test_query_without_filters_returns_everything(store: Store):
    await store.put("things", "a", {"id": "a"})
    await store.put("things", "b", {"id": "b"})
    assert len(await store.query("things")) == 2


async def test_query_filters_by_equality(store: Store):
    await store.put("things", "a", {"id": "a", "kind": "x"})
    await store.put("things", "b", {"id": "b", "kind": "y"})
    found = await store.query("things", where={"kind": "x"})
    assert [d["id"] for d in found] == ["a"]


async def test_query_ands_multiple_filters(store: Store):
    await store.put("things", "a", {"id": "a", "kind": "x", "live": True})
    await store.put("things", "b", {"id": "b", "kind": "x", "live": False})
    found = await store.query("things", where={"kind": "x", "live": True})
    assert [d["id"] for d in found] == ["a"]


async def test_query_orders_and_can_reverse(store: Store):
    for doc_id, rank in [("a", "3"), ("b", "1"), ("c", "2")]:
        await store.put("things", doc_id, {"id": doc_id, "rank": rank})

    ascending = await store.query("things", order_by="rank")
    assert [d["id"] for d in ascending] == ["b", "c", "a"]

    descending = await store.query("things", order_by="rank", descending=True)
    assert [d["id"] for d in descending] == ["a", "c", "b"]


async def test_query_limit(store: Store):
    for doc_id in "abcde":
        await store.put("things", doc_id, {"id": doc_id})
    assert len(await store.query("things", limit=2)) == 2


async def test_query_of_an_empty_collection_is_empty(store: Store):
    assert await store.query("nothing_here") == []


async def test_stored_documents_are_isolated_from_caller_mutations(store: Store):
    """Holding a reference must not let a caller edit stored state."""
    payload = {"id": "a", "nested": {"value": 1}}
    await store.put("things", "a", payload)
    payload["nested"]["value"] = 999

    assert (await store.get("things", "a"))["nested"]["value"] == 1


async def test_returned_documents_are_isolated_too(store: Store):
    await store.put("things", "a", {"id": "a", "nested": {"value": 1}})
    fetched = await store.get("things", "a")
    fetched["nested"]["value"] = 999

    assert (await store.get("things", "a"))["nested"]["value"] == 1


# --- typed persistence ----------------------------------------------------


async def test_entities_round_trip_with_their_types(store: Store):
    project = make_project()
    await repo.save(store, project)

    loaded = await repo.load(store, Project, "p1")
    assert loaded == project
    assert loaded.owner.user_id == "owner"
    assert loaded.role_of("designer") is Role.REVIEWER


async def test_loading_a_missing_entity_is_none(store: Store):
    assert await repo.load(store, Project, "nope") is None


async def test_enums_and_datetimes_survive_the_round_trip(store: Store):
    defect = make_defect()
    await repo.save(store, defect)

    loaded = await repo.load(store, DefectRecord, "d1")
    assert loaded.severity is Severity.BLOCKER
    assert loaded.category is Category.ANATOMY
    assert loaded.status is DefectState.OPEN
    assert loaded.created_at == defect.created_at


async def test_saving_without_an_id_is_rejected(store: Store):
    with pytest.raises(ValueError, match="no id"):
        await repo.save(store, Project(id="", name="x"))


async def test_each_entity_type_has_its_own_collection(store: Store):
    await repo.save(store, make_project())
    await repo.save(store, make_defect(defect_id="p1"))  # same id, different type

    assert (await repo.load(store, Project, "p1")).name == "Autumn campaign"
    assert (await repo.load(store, DefectRecord, "p1")).comment == "six fingers"


def test_unregistered_types_are_rejected():
    class Stray(Guideline):
        pass

    with pytest.raises(UnknownEntity):
        repo.collection_for(Stray)


# --- the queries the API asks ---------------------------------------------


async def test_projects_for_user_covers_every_role(store: Store):
    await repo.save(store, make_project("p1"))
    await repo.save(store, make_project("p2", owner="someone-else"))

    assert {p.id for p in await repo.projects_for_user(store, "owner")} == {"p1"}
    assert {p.id for p in await repo.projects_for_user(store, "designer")} == {"p1", "p2"}
    assert await repo.projects_for_user(store, "stranger") == []


async def test_defects_are_returned_in_pin_order(store: Store):
    for pin in (3, 1, 2):
        await repo.save(store, make_defect(defect_id=f"d{pin}", pin=pin))

    assert [d.pin for d in await repo.defects_for_image(store, "i1")] == [1, 2, 3]


async def test_defects_are_scoped_to_their_image(store: Store):
    await repo.save(store, make_defect("d1", image_id="i1"))
    await repo.save(store, make_defect("d2", image_id="i2"))

    assert [d.id for d in await repo.defects_for_image(store, "i1")] == ["d1"]


async def test_only_active_guidelines_are_returned(store: Store):
    await repo.save(store, Guideline(id="g1", project_id="p1", name="brand", raw_text="x"))
    await repo.save(
        store, Guideline(id="g2", project_id="p1", name="old", raw_text="y", active=False)
    )

    assert [g.id for g in await repo.active_guidelines(store, "p1")] == ["g1"]


async def test_unapproved_memory_rules_never_reach_the_scanner(store: Store):
    """A proposed rule is inactive until the Owner approves it."""
    await repo.save(store, MemoryRule(id="m1", project_id="p1", description="proposed"))
    await repo.save(
        store, MemoryRule(id="m2", project_id="p1", description="approved", active=True)
    )

    assert [m.id for m in await repo.active_memory_rules(store, "p1")] == ["m2"]


async def test_comments_come_back_in_thread_order(store: Store):
    from datetime import UTC, datetime, timedelta

    base = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
    for index in (2, 0, 1):
        await repo.save(
            store,
            Comment(
                id=f"c{index}",
                project_id="p1",
                defect_id="d1",
                author_id="u",
                body=f"comment {index}",
                created_at=base + timedelta(minutes=index),
            ),
        )

    assert [c.id for c in await repo.comments_for_defect(store, "d1")] == ["c0", "c1", "c2"]


async def test_unread_notifications_are_newest_first(store: Store):
    from datetime import UTC, datetime, timedelta

    base = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
    for index in range(3):
        await repo.save(
            store,
            Notification(
                id=f"n{index}",
                user_id="owner",
                project_id="p1",
                kind=NotificationKind.MENTION,
                body="x",
                created_at=base + timedelta(minutes=index),
            ),
        )
    await repo.save(
        store,
        Notification(
            id="read",
            user_id="owner",
            project_id="p1",
            kind=NotificationKind.MENTION,
            body="x",
            read=True,
        ),
    )

    unread = await repo.unread_notifications(store, "owner")
    assert [n.id for n in unread] == ["n2", "n1", "n0"]


async def test_images_are_listed_per_run_in_upload_order(store: Store):
    from datetime import UTC, datetime, timedelta

    base = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
    for index in range(3):
        await repo.save(
            store,
            ImageAsset(
                id=f"i{index}",
                project_id="p1",
                run_id="r1",
                filename=f"{index}.png",
                created_at=base + timedelta(seconds=index),
            ),
        )
    await repo.save(
        store, ImageAsset(id="other", project_id="p1", run_id="r2", filename="x.png")
    )

    assert [i.id for i in await repo.images_for_run(store, "r1")] == ["i0", "i1", "i2"]


async def test_runs_track_their_status(store: Store):
    run = Run(id="r1", project_id="p1", started_by="owner")
    await repo.save(store, run)

    run.status = RunStatus.DONE
    await repo.save(store, run)

    assert (await repo.load(store, Run, "r1")).status is RunStatus.DONE
