"""Brand profile through the API, and the confirmation gate the pipeline honours.

Real store, real HTTP, real images. The extraction endpoint calls a model, so it
is exercised only on its rejection paths; what extraction *produces* is measured
by scripts/check_brand_extraction.py against a real guideline.
"""

import base64
import io
import json

import itsdangerous
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.agents.pipeline import measure_palette
from app.api.auth import SESSION_USER_KEY
from app.api.deps import get_blobs, get_store
from app.api.main import app
from app.config import settings
from app.domain.brand import PALETTE_RULE
from app.domain.entities import BrandProfile, PaletteEntry, Project, User
from app.domain.grid import Grid
from app.infra import repository as repo
from app.infra.storage import LocalBlobStore
from app.infra.store import InMemoryStore
from app.services import brand as brand_service

OWNER = {"id": "u-owner", "email": "owner@acme.com", "name": "Ola Owner", "picture": ""}
DESIGNER = {"id": "u-designer", "email": "dee@acme.com", "name": "Dee Designer", "picture": ""}

BRAND_TEAL = "#1d9e75"
OFF_ORANGE = "#d85a30"


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


@pytest.fixture
def project(client, store):
    as_user(client, OWNER)
    project_id = client.post("/api/projects", json={"name": "Autumn campaign"}).json()["project"][
        "id"
    ]
    client.post(
        f"/api/projects/{project_id}/members",
        json={"email": DESIGNER["email"], "role": "reviewer"},
    )
    return project_id


async def link_designer(store, project_id):
    stored = await repo.load(store, Project, project_id)
    for member in stored.members:
        if member.email == DESIGNER["email"]:
            member.user_id = DESIGNER["id"]
    await repo.save(store, stored)


def violating_image() -> tuple[Image.Image, Grid]:
    """On-brand field with one off-palette designed block planted in cell C4."""
    image = Image.new("RGB", (800, 800), (29, 158, 117))
    grid = Grid.for_image(800, 800)
    ImageDraw.Draw(image).rectangle(grid.cell_bounds("C4").as_tuple(), fill=(216, 90, 48))
    return image, grid


# --- the confirmation gate, end to end ------------------------------------


@pytest.mark.anyio
async def test_an_unconfirmed_profile_produces_no_measurements_at_all(store, project):
    """Gate 7, asserted: extraction alone must never generate brand defects."""
    await brand_service.propose(
        store, project, [PaletteEntry(hex=BRAND_TEAL, role="primary")], source="guideline.pdf"
    )
    profile = await brand_service.load(store, project)
    image, grid = violating_image()

    assert profile.proposed
    assert profile.entries == []
    assert await brand_service.load_active(store, project) is None
    assert measure_palette(image, grid, profile) == []


@pytest.mark.anyio
async def test_confirming_the_same_palette_makes_the_violation_measurable(
    client, store, project
):
    as_user(client, OWNER)
    response = client.post(
        f"/api/projects/{project}/brand/confirm",
        json={"entries": [{"hex": BRAND_TEAL, "role": "primary", "tolerance": 3.0}]},
    )
    assert response.status_code == 200
    assert response.json()["active"] is True

    profile = await brand_service.load_active(store, project)
    image, grid = violating_image()
    offences = measure_palette(image, grid, profile)

    assert [offence.cells for offence in offences] == [["C4"]]
    assert offences[0].hex == OFF_ORANGE
    assert offences[0].delta_e > 10
    assert PALETTE_RULE in offences[0].describe() or "ΔE2000" in offences[0].describe()


@pytest.mark.anyio
async def test_withdrawing_stops_enforcement_but_keeps_the_colours(client, store, project):
    as_user(client, OWNER)
    client.post(
        f"/api/projects/{project}/brand/confirm",
        json={"entries": [{"hex": BRAND_TEAL, "role": "primary", "tolerance": 3.0}]},
    )
    withdrawn = client.post(f"/api/projects/{project}/brand/withdraw").json()

    assert withdrawn["active"] is False
    assert [entry["hex"] for entry in withdrawn["profile"]["proposed"]] == [BRAND_TEAL]

    image, grid = violating_image()
    assert measure_palette(image, grid, await brand_service.load(store, project)) == []


# --- who may confirm ------------------------------------------------------


@pytest.mark.anyio
async def test_only_the_owner_may_confirm_a_palette(client, store, project):
    await link_designer(store, project)
    as_user(client, DESIGNER)
    response = client.post(
        f"/api/projects/{project}/brand/confirm",
        json={"entries": [{"hex": BRAND_TEAL}]},
    )
    assert response.status_code == 403


@pytest.mark.anyio
async def test_a_stranger_cannot_read_the_profile(client, project):
    as_user(client, {"id": "u-nobody", "email": "no@one.com", "name": "", "picture": ""})
    assert client.get(f"/api/projects/{project}/brand").status_code in (403, 404)


# --- what confirmation accepts --------------------------------------------


@pytest.mark.anyio
async def test_an_empty_palette_is_refused(client, project):
    as_user(client, OWNER)
    response = client.post(f"/api/projects/{project}/brand/confirm", json={"entries": []})
    assert response.status_code == 400


@pytest.mark.anyio
async def test_unparseable_colours_are_dropped_and_the_rest_kept(client, project):
    as_user(client, OWNER)
    response = client.post(
        f"/api/projects/{project}/brand/confirm",
        json={
            "entries": [
                {"hex": "not a colour"},
                {"hex": "#1D9E75", "role": "primary"},
                {"hex": "#1d9e75", "role": "duplicate"},
            ]
        },
    )
    entries = response.json()["profile"]["entries"]
    assert [entry["hex"] for entry in entries] == [BRAND_TEAL]
    assert entries[0]["role"] == "primary"


@pytest.mark.anyio
async def test_a_palette_of_only_junk_is_refused_rather_than_confirmed_empty(client, project):
    as_user(client, OWNER)
    response = client.post(
        f"/api/projects/{project}/brand/confirm", json={"entries": [{"hex": "puce"}]}
    )
    assert response.status_code == 400


@pytest.mark.anyio
async def test_reading_a_profile_before_one_exists_gives_an_inactive_shell(client, project):
    as_user(client, OWNER)
    view = client.get(f"/api/projects/{project}/brand").json()
    assert view["active"] is False
    assert view["profile"]["entries"] == []


# --- extraction rejection paths -------------------------------------------


@pytest.mark.anyio
async def test_extraction_needs_something_to_read(client, project):
    as_user(client, OWNER)
    assert client.post(f"/api/projects/{project}/brand/extract").status_code == 400


@pytest.mark.anyio
async def test_extraction_refuses_a_file_that_is_not_a_pdf(client, project):
    as_user(client, OWNER)
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10)).save(buffer, format="PNG")
    response = client.post(
        f"/api/projects/{project}/brand/extract",
        files={"file": ("palette.png", buffer.getvalue(), "image/png")},
    )
    assert response.status_code == 415


@pytest.mark.anyio
async def test_extraction_refuses_an_unknown_guideline(client, project):
    as_user(client, OWNER)
    response = client.post(
        f"/api/projects/{project}/brand/extract", params={"guideline_id": "nope"}
    )
    assert response.status_code == 404


# --- persistence ----------------------------------------------------------


@pytest.mark.anyio
async def test_one_profile_per_project_however_often_it_is_confirmed(client, store, project):
    as_user(client, OWNER)
    for role in ("primary", "secondary"):
        client.post(
            f"/api/projects/{project}/brand/confirm",
            json={"entries": [{"hex": BRAND_TEAL, "role": role}]},
        )

    stored = await repo.find(store, BrandProfile, where={"project_id": project})
    assert len(stored) == 1
    assert stored[0].entries[0].role == "secondary"
    assert stored[0].confirmed_by == OWNER["id"]


@pytest.mark.anyio
async def test_confirmation_records_who_signed_it_off(client, store, project):
    as_user(client, OWNER)
    client.post(
        f"/api/projects/{project}/brand/confirm", json={"entries": [{"hex": BRAND_TEAL}]}
    )
    profile = await brand_service.load(store, project)
    assert profile.confirmed_by == OWNER["id"]
    assert profile.confirmed_at is not None


@pytest.mark.anyio
async def test_the_service_refuses_a_confirmation_from_a_non_owner_directly(store, project):
    stored = await repo.load(store, Project, project)
    with pytest.raises(PermissionError):
        await brand_service.confirm(
            store,
            stored,
            User(id="u-nobody", email="no@one.com"),
            [PaletteEntry(hex=BRAND_TEAL)],
        )
