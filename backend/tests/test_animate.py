"""Phase 15 (decision 24): generated media re-enters review through the front door.

Real store, real blobs, real HTTP; the Veo call is the one thing recorded — it
needs credentials and minutes. Everything downstream of the model runs for
real, including video ingest against real ffmpeg where marked.
"""

import base64
import io
import json
import shutil
import subprocess

import itsdangerous
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.agents import animator, editor
from app.api.auth import SESSION_USER_KEY
from app.api.deps import get_blobs, get_store
from app.api.main import app
from app.config import settings
from app.domain.entities import Circle, DefectRecord, ImageAsset, ImageStatus, Project, Run, User
from app.domain.taxonomy import Category, Severity
from app.infra import repository as repo
from app.infra.events import EventBus
from app.infra.storage import LocalBlobStore
from app.infra.store import InMemoryStore
from app.services import animate as animate_service
from app.services import drafts as draft_service
from app.services import export as export_service
from app.services import review as review_service
from app.services import runs as run_service
from app.services import slots as slot_service

OWNER = {"id": "u-owner", "email": "owner@acme.com", "name": "Ola Owner", "picture": ""}
DESIGNER = {"id": "u-designer", "email": "dee@acme.com", "name": "Dee Designer", "picture": ""}

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg not installed",
)


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


def png_bytes(color=(200, 30, 30), size=(320, 320)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def project(client):
    as_user(client, OWNER)
    project_id = client.post("/api/projects", json={"name": "Autumn campaign"}).json()[
        "project"
    ]["id"]
    client.post(
        f"/api/projects/{project_id}/members",
        json={"email": DESIGNER["email"], "role": "reviewer"},
    )
    return project_id


@pytest.fixture(scope="module")
def clip(tmp_path_factory) -> bytes:
    """What the recorded Veo returns: a real 2s mp4, so ingest runs for real."""
    path = tmp_path_factory.mktemp("veo") / "motion.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=green:s=320x568:d=2:r=12",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-pix_fmt", "yuv420p", "-shortest", str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path.read_bytes()


async def stored_project(store, project_id) -> Project:
    return await repo.load(store, Project, project_id)


async def approved_slot(store, blobs, project_id) -> str:
    """One slot, one variant, reviewed clean and approved — animatable."""
    run = await run_service.create_run(
        store,
        blobs,
        await stored_project(store, project_id),
        User(**OWNER),
        [("hero.png", png_bytes())],
    )
    asset = await repo.load(store, ImageAsset, run.image_ids[0])
    asset.status = ImageStatus.DONE
    await repo.save(store, asset)
    await review_service.approve_image(
        store, await stored_project(store, project_id), asset, User(**OWNER)
    )
    return asset.slot_id


def drain(queue) -> list:
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    return events


# --- the gatekeeping half: who may ask, and of what -------------------------


@pytest.mark.anyio
async def test_animate_is_owner_only(client, store, project):
    proj = await repo.load(store, Project, project)
    for member in proj.members:  # invites hold placeholder ids until first sign-in
        if member.email == DESIGNER["email"]:
            member.user_id = DESIGNER["id"]
    await repo.save(store, proj)

    as_user(client, DESIGNER)
    response = client.post(
        f"/api/projects/{project}/slots/whatever/animate", json={"brief": "slow zoom"}
    )
    assert response.status_code == 403


def test_an_unknown_slot_is_404(client, project):
    as_user(client, OWNER)
    response = client.post(
        f"/api/projects/{project}/slots/s-nope/animate", json={"brief": "slow zoom"}
    )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_only_a_completed_slot_can_be_animated(client, store, blobs, project):
    run = await run_service.create_run(
        store,
        blobs,
        await stored_project(store, project),
        User(**OWNER),
        [("hero.png", png_bytes())],
    )
    asset = await repo.load(store, ImageAsset, run.image_ids[0])

    as_user(client, OWNER)
    response = client.post(
        f"/api/projects/{project}/slots/{asset.slot_id}/animate",
        json={"brief": "slow zoom"},
    )
    assert response.status_code == 409
    assert "approve" in response.json()["detail"]


@pytest.mark.anyio
async def test_an_empty_brief_is_refused(client, store, blobs, project):
    slot_id = await approved_slot(store, blobs, project)
    as_user(client, OWNER)
    response = client.post(
        f"/api/projects/{project}/slots/{slot_id}/animate", json={"brief": "   "}
    )
    assert response.status_code == 409


# --- the background half: what the generation does to the world -------------


@pytest.mark.anyio
async def test_a_failed_generation_reports_and_changes_nothing(
    store, blobs, project, monkeypatch
):
    slot_id = await approved_slot(store, blobs, project)
    approved = (await repo.find(store, ImageAsset, where={"slot_id": slot_id}))[0]

    async def no_video(png, brief):
        return None

    monkeypatch.setattr(animator, "animate", no_video)
    bus = EventBus()
    queue = bus.subscribe(project)

    result = await animate_service.run_animation(
        store, blobs, bus, await stored_project(store, project), User(**OWNER),
        slot_id, approved, "slow zoom",
    )

    assert result is None
    stages = [event.stage for event in drain(queue)]
    assert stages == ["animation_started", "animation_failed"]
    assets = await repo.find(store, ImageAsset, where={"slot_id": slot_id})
    assert len(assets) == 1, "a failed generation leaves no orphan asset"


@needs_ffmpeg
@pytest.mark.anyio
async def test_the_animation_lands_as_an_ordinary_agent_variant(
    client, store, blobs, project, clip, monkeypatch
):
    slot_id = await approved_slot(store, blobs, project)

    async def recorded_veo(png, brief):
        assert brief == "slow zoom on the product"
        return clip

    reviewed: list[str] = []

    async def recorded_review(store_, blobs_, bus_, project_, run_):
        reviewed.append(run_.id)
        return run_

    monkeypatch.setattr(animator, "animate", recorded_veo)
    monkeypatch.setattr(run_service, "execute_run", recorded_review)

    as_user(client, OWNER)
    response = client.post(
        f"/api/projects/{project}/slots/{slot_id}/animate",
        json={"brief": "slow zoom on the product", "placement": "tiktok"},
    )
    assert response.status_code == 202

    assets = await repo.find(store, ImageAsset, where={"slot_id": slot_id})
    generated = next(a for a in assets if a.kind == "video")
    assert generated.uploaded_by == draft_service.AGENT_USER_ID
    assert generated.variant == 2 and generated.version == 1
    assert generated.video_path and generated.original_path, "mp4 stored, poster rendered"

    run = await repo.load(store, Run, generated.run_id)
    assert run.placement == "tiktok"
    assert reviewed == [run.id], "the generated variant gets the full review pass"

    # Every existing read path treats it as an ordinary variant.
    group = next(
        g for g in await slot_service.project_slots(store, project) if g.slot_id == slot_id
    )
    assert [chain.variant for chain in group.variants] == [1, 2]
    assert group.winner.variant == 1, "generating never moves the approval"


@needs_ffmpeg
@pytest.mark.anyio
async def test_export_never_contains_the_unapproved_animation(
    client, store, blobs, project, clip, monkeypatch
):
    slot_id = await approved_slot(store, blobs, project)
    approved = (await repo.find(store, ImageAsset, where={"slot_id": slot_id}))[0]

    async def recorded_veo(png, brief):
        return clip

    async def recorded_review(*args):
        return None

    monkeypatch.setattr(animator, "animate", recorded_veo)
    monkeypatch.setattr(run_service, "execute_run", recorded_review)
    as_user(client, OWNER)
    client.post(
        f"/api/projects/{project}/slots/{slot_id}/animate", json={"brief": "slow zoom"}
    )

    chosen = await export_service.approved_assets(store, project)
    assert [asset.id for _, asset in chosen] == [approved.id]


# --- decision 23 guard the animation exposed: drafts never touch footage ----


@pytest.mark.anyio
async def test_the_editor_never_drafts_on_a_video(store, blobs, project, monkeypatch):
    """A PNG branch on a video would claim to fix defects that live in footage."""
    asset = ImageAsset(
        id="i-vid",
        project_id=project,
        run_id="r-vid",
        filename="spot.mp4",
        kind="video",
        status=ImageStatus.DONE,
        uploaded_by=OWNER["id"],
    )
    await repo.save(store, asset)
    await repo.save(
        store,
        DefectRecord(
            id="d-vid",
            project_id=project,
            image_id="i-vid",
            pin=1,
            cells=["C4"],
            category=Category.ARTIFACT,
            severity=Severity.BLOCKER,
            comment="warped hand at 0:02",
            circle=Circle(cx=100, cy=100, radius=40),
        ),
    )

    async def must_not_edit(png, instructions):
        raise AssertionError("the editor was asked to draft on a video")

    monkeypatch.setattr(editor, "draft_fix", must_not_edit)
    run = Run(id="r-vid", project_id=project, started_by=OWNER["id"], image_ids=["i-vid"])
    drafts = await draft_service.draft_pass(
        store, blobs, EventBus(), await stored_project(store, project), run
    )
    assert drafts == []
