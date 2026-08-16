"""Renaming and deleting a project.

Deletion crosses every collection, so the tests seed a project that actually has
one of everything and then assert the store is empty afterwards — a cascade is
only correct if nothing survives it, and "nothing" is the assertion.
"""

import base64
import io
import json

import itsdangerous
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.api.auth import SESSION_USER_KEY
from app.api.deps import get_blobs, get_store
from app.api.main import app
from app.config import settings
from app.domain.entities import (
    BrandProfile,
    Circle,
    Comment,
    DefectRecord,
    DismissalRecord,
    Guideline,
    ImageAsset,
    MemoryRule,
    Notification,
    NotificationKind,
    PaletteEntry,
    Project,
    ReviewThread,
    Run,
    Slot,
    User,
)
from app.domain.taxonomy import Category, Severity
from app.infra import repository as repo
from app.infra.storage import LocalBlobStore
from app.infra.store import InMemoryStore
from app.services import projects as project_service

OWNER = {"id": "u-owner", "email": "owner@acme.com", "name": "Ola Owner", "picture": ""}
DESIGNER = {"id": "u-designer", "email": "dee@acme.com", "name": "Dee Designer", "picture": ""}

#: Every collection a project can put rows in. The cascade must empty all of them.
PROJECT_COLLECTIONS = [
    (Slot, "slots"),
    (ImageAsset, "images"),
    (DefectRecord, "defects"),
    (DismissalRecord, "dismissals"),
    (ReviewThread, "threads"),
    (Comment, "comments"),
    (Guideline, "guidelines"),
    (MemoryRule, "memory_rules"),
    (BrandProfile, "brand_profiles"),
    (Run, "runs"),
    (Notification, "notifications"),
]


def session_cookie(user: dict) -> str:
    signer = itsdangerous.TimestampSigner(settings.session_secret)
    payload = base64.b64encode(json.dumps({SESSION_USER_KEY: user}).encode())
    return signer.sign(payload).decode()


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture
def blobs(tmp_path):
    return LocalBlobStore(tmp_path)


@pytest.fixture
def client(store, blobs):
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_blobs] = lambda: blobs
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def as_user(client: TestClient, user: dict) -> TestClient:
    client.cookies.set("session", session_cookie(user))
    return client


def png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 30, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def project(client):
    as_user(client, OWNER)
    project_id = client.post("/api/projects", json={"name": "Autumn campaign"}).json()["project"][
        "id"
    ]
    client.post(
        f"/api/projects/{project_id}/members",
        json={"email": DESIGNER["email"], "role": "reviewer"},
    )
    return project_id


async def seed_everything(store, blobs, project_id: str) -> None:
    """One row in every collection a project owns, plus a real blob."""
    await repo.save(store, Slot(id="s1", project_id=project_id, name="Hero"))
    await repo.save(store, Run(id="r1", project_id=project_id, started_by=OWNER["id"]))

    image = ImageAsset(
        id="i1", project_id=project_id, run_id="r1", filename="hero.png", slot_id="s1"
    )
    image.original_path = await blobs.write(f"{project_id}/i1/original.png", png_bytes())
    await repo.save(store, image)

    await repo.save(
        store,
        DefectRecord(
            id="d1",
            project_id=project_id,
            image_id="i1",
            pin=1,
            cells=["C4"],
            category=Category.ANATOMY,
            severity=Severity.BLOCKER,
            comment="Six fingers.",
            circle=Circle(cx=10, cy=10, radius=5),
        ),
    )
    await repo.save(
        store,
        DismissalRecord(
            id="x1",
            project_id=project_id,
            image_id="i1",
            cells=["A1"],
            hypothesis="maybe",
            reason="no",
            stage="inspector",
        ),
    )
    await repo.save(
        store,
        ReviewThread(
            id="t1", project_id=project_id, image_id="i1", pin=2, author_id=OWNER["id"]
        ),
    )
    for comment_id, parent in (("c1", "d1"), ("c2", "t1")):
        await repo.save(
            store,
            Comment(
                id=comment_id,
                project_id=project_id,
                defect_id=parent,
                author_id=OWNER["id"],
                body="noted",
            ),
        )
    await repo.save(
        store, Guideline(id="g1", project_id=project_id, name="Brand", raw_text="Be on brand.")
    )
    await repo.save(store, MemoryRule(id="m1", project_id=project_id, description="No stock art."))
    await repo.save(
        store,
        BrandProfile(
            id=f"brand-{project_id}",
            project_id=project_id,
            entries=[PaletteEntry(hex="#1d9e75")],
            confirmed_by=OWNER["id"],
        ),
    )
    await repo.save(
        store,
        Notification(
            id="n1",
            user_id=OWNER["id"],
            project_id=project_id,
            kind=NotificationKind.RUN_FINISHED,
            body="done",
        ),
    )


# --- rename ---------------------------------------------------------------


def test_the_owner_can_rename_a_project(client, project):
    as_user(client, OWNER)
    response = client.post(f"/api/projects/{project}/name", json={"name": "Winter campaign"})
    assert response.status_code == 200
    assert response.json()["project"]["name"] == "Winter campaign"

    assert client.get(f"/api/projects/{project}").json()["project"]["name"] == "Winter campaign"


def test_renaming_trims_surrounding_whitespace(client, project):
    as_user(client, OWNER)
    response = client.post(f"/api/projects/{project}/name", json={"name": "  Spring  "})
    assert response.json()["project"]["name"] == "Spring"


@pytest.mark.parametrize("name", ["", "   ", "x" * 121])
def test_an_unusable_name_is_refused(client, project, name):
    as_user(client, OWNER)
    assert client.post(f"/api/projects/{project}/name", json={"name": name}).status_code in (
        400,
        422,
    )


@pytest.mark.anyio
async def test_a_reviewer_cannot_rename_the_project(client, store, project):
    stored = await repo.load(store, Project, project)
    for member in stored.members:
        if member.email == DESIGNER["email"]:
            member.user_id = DESIGNER["id"]
    await repo.save(store, stored)

    as_user(client, DESIGNER)
    response = client.post(f"/api/projects/{project}/name", json={"name": "Mine now"})
    assert response.status_code == 403
    assert (await repo.load(store, Project, project)).name == "Autumn campaign"


# --- delete ---------------------------------------------------------------


@pytest.mark.anyio
async def test_the_preview_counts_pre_slot_images_as_the_slots_they_display_as(
    client, store, blobs, project
):
    """The modal must agree with the Slots tab, which shows legacy images as slots."""
    await seed_everything(store, blobs, project)
    await repo.save(
        store,
        ImageAsset(id="legacy", project_id=project, run_id="r1", filename="old.png"),
    )

    as_user(client, OWNER)
    preview = client.get(f"/api/projects/{project}/delete_preview").json()

    assert preview["images"] == 2
    assert preview["slots"] == 2, "the pre-slot image has no Slot row but does have a card"


@pytest.mark.anyio
async def test_the_preview_counts_what_deletion_would_destroy(client, store, blobs, project):
    await seed_everything(store, blobs, project)

    as_user(client, OWNER)
    preview = client.get(f"/api/projects/{project}/delete_preview").json()

    assert preview == {
        "slots": 1,
        "images": 1,
        "defects": 1,
        "threads": 1,
        "comments": 2,
        "dismissals": 1,
        "guidelines": 1,
        "memory_rules": 1,
        "members": 2,
    }


@pytest.mark.anyio
async def test_deleting_a_project_empties_every_collection_it_touched(
    client, store, blobs, project
):
    await seed_everything(store, blobs, project)

    as_user(client, OWNER)
    assert client.delete(f"/api/projects/{project}").status_code == 200

    for model, label in PROJECT_COLLECTIONS:
        survivors = await repo.find(store, model)
        assert survivors == [], f"{label} still holds {len(survivors)} row(s)"
    assert await repo.load(store, Project, project) is None


@pytest.mark.anyio
async def test_deleting_a_project_removes_its_blobs(client, store, blobs, project):
    await seed_everything(store, blobs, project)
    assert await blobs.exists(f"{project}/i1/original.png")

    as_user(client, OWNER)
    client.delete(f"/api/projects/{project}")

    assert not await blobs.exists(f"{project}/i1/original.png")


@pytest.mark.anyio
async def test_deletion_reports_what_it_removed(client, store, blobs, project):
    await seed_everything(store, blobs, project)
    as_user(client, OWNER)
    removed = client.delete(f"/api/projects/{project}").json()
    assert removed["images"] == 1
    assert removed["comments"] == 2


@pytest.mark.anyio
async def test_deleting_one_project_leaves_another_untouched(client, store, blobs, project):
    as_user(client, OWNER)
    other = client.post("/api/projects", json={"name": "Keep me"}).json()["project"]["id"]
    await seed_everything(store, blobs, project)
    await repo.save(store, Slot(id="s-other", project_id=other, name="Theirs"))

    client.delete(f"/api/projects/{project}")

    assert await repo.load(store, Project, other) is not None
    assert [slot.id for slot in await repo.slots_for_project(store, other)] == ["s-other"]


@pytest.mark.anyio
async def test_a_reviewer_cannot_delete_the_project(client, store, project):
    stored = await repo.load(store, Project, project)
    for member in stored.members:
        if member.email == DESIGNER["email"]:
            member.user_id = DESIGNER["id"]
    await repo.save(store, stored)

    as_user(client, DESIGNER)
    assert client.delete(f"/api/projects/{project}").status_code == 403
    assert await repo.load(store, Project, project) is not None


def test_a_stranger_cannot_even_see_the_delete_preview(client, project):
    as_user(client, {"id": "u-nobody", "email": "no@one.com", "name": "", "picture": ""})
    assert client.get(f"/api/projects/{project}/delete_preview").status_code in (403, 404)


@pytest.mark.anyio
async def test_the_service_refuses_deletion_by_a_non_owner_directly(store, blobs, project):
    stored = await repo.load(store, Project, project)
    with pytest.raises(PermissionError):
        await project_service.delete_project(
            store, blobs, stored, User(id="u-nobody", email="no@one.com")
        )
    assert await repo.load(store, Project, project) is not None


@pytest.mark.anyio
async def test_deleting_an_empty_project_works_and_counts_zero(client, store, project):
    as_user(client, OWNER)
    removed = client.delete(f"/api/projects/{project}").json()
    assert removed["images"] == 0
    assert removed["members"] == 2
    assert await repo.load(store, Project, project) is None


@pytest.mark.anyio
async def test_a_deleted_project_disappears_from_the_dashboard(client, store, blobs, project):
    await seed_everything(store, blobs, project)
    as_user(client, OWNER)
    client.delete(f"/api/projects/{project}")

    assert client.get("/api/projects").json() == []
    assert client.get(f"/api/projects/{project}").status_code == 404
