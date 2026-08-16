"""Phase 14: voice on question threads — the tool list is the whole authority.

The Live model can record an answer or move through the queue, nothing else,
and the browser executes tools through the ordinary answer endpoint with the
user's own session — so a spoken answer is byte-identical to a clicked one by
construction (same endpoint, covered by test_questions.py). What is left to
assert here: the tool surface stays that small, and the session endpoint's
guards.
"""

import base64
import io
import json

import itsdangerous
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.agents import voice
from app.api.auth import SESSION_USER_KEY
from app.api.deps import get_blobs, get_store
from app.api.main import app
from app.config import settings
from app.domain.entities import Circle, DefectRecord, Project, User
from app.domain.lifecycle import DefectState
from app.domain.taxonomy import Category, Severity
from app.infra import repository as repo
from app.infra.storage import LocalBlobStore
from app.infra.store import InMemoryStore
from app.services import runs as run_service

OWNER = {"id": "u-owner", "email": "owner@acme.com", "name": "Ola Owner", "picture": ""}


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
        test_client.cookies.set("session", session_cookie(OWNER))
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def project(client):
    return client.post("/api/projects", json={"name": "Autumn"}).json()["project"]["id"]


def png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (320, 320), (200, 30, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


async def image_with(store, blobs, project_id, *states) -> str:
    project = await repo.load(store, Project, project_id)
    run = await run_service.create_run(
        store, blobs, project, User(**OWNER), [("hero.png", png_bytes())]
    )
    image_id = run.image_ids[0]
    for index, state in enumerate(states, start=1):
        await repo.save(
            store,
            DefectRecord(
                id=f"d{index}",
                project_id=project_id,
                image_id=image_id,
                pin=index,
                cells=["C4"],
                category=Category.BRAND,
                severity=Severity.WARNING,
                comment=f"question {index}",
                circle=Circle(cx=100, cy=100, radius=40),
                status=state,
            ),
        )
    return image_id


# --- the gate: the tool surface -----------------------------------------------


def test_the_tool_list_is_exactly_the_two_moves_the_buttons_offer():
    names = {tool["name"] for tool in voice.TOOL_DECLARATIONS}
    assert names == {"answer_question", "next_question", "previous_question"}


def test_answer_question_carries_no_state_argument():
    """The model says confirmed yes/no; it never names a lifecycle state."""
    answer = next(t for t in voice.TOOL_DECLARATIONS if t["name"] == "answer_question")
    assert set(answer["parameters"]["properties"]) == {"defect_id", "confirmed"}
    assert answer["parameters"]["required"] == ["defect_id", "confirmed"]


def test_no_declaration_mentions_any_other_lifecycle_move():
    text = json.dumps(voice.TOOL_DECLARATIONS).lower()
    for forbidden in ("approve", "dismiss", "override", "resolve", "delete", "severity"):
        assert forbidden not in text, f"the tool surface leaks '{forbidden}'"


def test_question_lines_carry_id_and_the_code_stamped_comment():
    defect = DefectRecord(
        id="d-q",
        project_id="p",
        image_id="i",
        pin=1,
        cells=["C4"],
        category=Category.BRAND,
        severity=Severity.WARNING,
        comment="ΔE2000 13.4 from #1c1e2a (ink), which allows 4.0",
        circle=Circle(cx=1, cy=1, radius=1),
        status=DefectState.NEEDS_HUMAN_REVIEW,
    )
    lines = voice.question_lines([defect])
    assert "d-q" in lines and "ΔE2000 13.4" in lines


# --- the session endpoint's guards --------------------------------------------


@pytest.mark.anyio
async def test_no_questions_means_no_session(client, store, blobs, project):
    image_id = await image_with(store, blobs, project, DefectState.OPEN)
    response = client.post(f"/api/projects/{project}/images/{image_id}/voice/session")
    assert response.status_code == 409


@pytest.mark.anyio
async def test_without_credentials_voice_degrades_with_503(
    client, store, blobs, project, monkeypatch
):
    image_id = await image_with(store, blobs, project, DefectState.NEEDS_HUMAN_REVIEW)
    monkeypatch.setattr(settings, "google_api_key", "")
    monkeypatch.setattr(settings, "use_vertex_ai", False)
    response = client.post(f"/api/projects/{project}/images/{image_id}/voice/session")
    assert response.status_code == 503


@pytest.mark.anyio
async def test_with_credentials_the_session_carries_the_queue_in_order(
    client, store, blobs, project, monkeypatch
):
    image_id = await image_with(
        store,
        blobs,
        project,
        DefectState.NEEDS_HUMAN_REVIEW,
        DefectState.OPEN,
        DefectState.NEEDS_HUMAN_REVIEW,
    )
    monkeypatch.setattr(settings, "google_api_key", "test-key")

    async def recorded_mint(questions):
        assert [q.id for q in questions] == ["d1", "d3"], "open questions only, in order"
        return "auth_tokens/fake"

    monkeypatch.setattr(voice, "mint_session_token", recorded_mint)
    response = client.post(f"/api/projects/{project}/images/{image_id}/voice/session")
    assert response.status_code == 200
    body = response.json()
    assert body["token"] == "auth_tokens/fake"
    assert body["model"] == settings.model_live
    assert body["question_ids"] == ["d1", "d3"]
