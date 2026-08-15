"""API integration tests: real HTTP requests, real persistence, real sessions.

Storage is the InMemoryStore and LocalBlobStore — both real implementations that
actually store and query, not mocks (AGENTS.md). Nothing here asserts that a
collaborator "was called".

The full run path is not exercised here because it calls Gemini; its persistence is
covered by driving the service directly, and its detection quality by the eval
harness. The endpoint's rejection paths are covered.
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
from app.domain.entities import DefectRecord, ImageAsset, ImageStatus, Project, User
from app.domain.lifecycle import DefectState
from app.domain.taxonomy import Category, Severity
from app.infra import repository as repo
from app.infra.storage import LocalBlobStore
from app.infra.store import InMemoryStore
from app.services import runs as run_service

OWNER = {"id": "u-owner", "email": "owner@acme.com", "name": "Ola Owner", "picture": ""}
DESIGNER = {"id": "u-designer", "email": "dee@acme.com", "name": "Dee Designer", "picture": ""}
SALES = {"id": "u-sales", "email": "sam@acme.com", "name": "Sam Sales", "picture": ""}


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


def png_bytes(color=(200, 30, 30), size=(400, 400)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def project(client):
    """A project owned by OWNER with DESIGNER as reviewer and SALES as viewer."""
    as_user(client, OWNER)
    response = client.post("/api/projects", json={"name": "Autumn campaign"})
    project_id = response.json()["project"]["id"]

    client.post(
        f"/api/projects/{project_id}/members",
        json={"email": DESIGNER["email"], "role": "reviewer"},
    )
    client.post(
        f"/api/projects/{project_id}/members", json={"email": SALES["email"], "role": "viewer"}
    )
    return project_id


async def seed_defect(store, project_id, defect_id="d1", image_id="i1", pin=1) -> DefectRecord:
    from app.domain.entities import Circle

    defect = DefectRecord(
        id=defect_id,
        project_id=project_id,
        image_id=image_id,
        pin=pin,
        cells=["C4"],
        category=Category.ANATOMY,
        severity=Severity.BLOCKER,
        comment="Six fingers on the left hand.",
        rule_ref="ANAT-01",
        circle=Circle(cx=100, cy=100, radius=40),
    )
    await repo.save(store, defect)
    return defect


async def link_real_members(store, project_id):
    """Invites store `email:` placeholder ids until first sign-in; give them real ids."""
    project = await repo.load(store, Project, project_id)
    for member in project.members:
        if member.email == DESIGNER["email"]:
            member.user_id = DESIGNER["id"]
        elif member.email == SALES["email"]:
            member.user_id = SALES["id"]
    await repo.save(store, project)


# --- auth gate ------------------------------------------------------------


def test_every_project_route_requires_a_session(client):
    assert client.get("/api/projects").status_code == 401
    assert client.post("/api/projects", json={"name": "x"}).status_code == 401
    assert client.get("/api/notifications").status_code == 401


# --- projects -------------------------------------------------------------


def test_creating_a_project_makes_the_creator_the_brand_owner(client):
    as_user(client, OWNER)
    response = client.post("/api/projects", json={"name": "Autumn campaign"})

    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "owner"
    assert body["project"]["members"][0]["user_id"] == OWNER["id"]
    assert "approve_image" in body["permissions"]


def test_a_created_project_is_persisted_and_listed(client):
    as_user(client, OWNER)
    client.post("/api/projects", json={"name": "Autumn campaign"})

    listed = client.get("/api/projects").json()
    assert [p["project"]["name"] for p in listed] == ["Autumn campaign"]


def test_projects_are_not_visible_to_non_members(client, project):
    as_user(client, {"id": "stranger", "email": "s@x.com", "name": "S", "picture": ""})
    assert client.get("/api/projects").json() == []
    assert client.get(f"/api/projects/{project}").status_code == 404


def test_a_blank_project_name_is_rejected(client):
    as_user(client, OWNER)
    assert client.post("/api/projects", json={"name": ""}).status_code == 422


# --- membership -----------------------------------------------------------


def test_the_owner_can_invite_members(client, project):
    as_user(client, OWNER)
    body = client.get(f"/api/projects/{project}").json()
    roles = {m["email"]: m["role"] for m in body["project"]["members"]}

    assert roles[DESIGNER["email"]] == "reviewer"
    assert roles[SALES["email"]] == "viewer"


@pytest.mark.anyio
async def test_a_reviewer_cannot_invite(client, project, store):
    await link_real_members(store, project)
    as_user(client, DESIGNER)

    response = client.post(
        f"/api/projects/{project}/members", json={"email": "new@acme.com", "role": "viewer"}
    )
    assert response.status_code == 403


def test_inviting_a_second_owner_is_refused(client, project):
    """Two accountable people is the same as none."""
    as_user(client, OWNER)
    response = client.post(
        f"/api/projects/{project}/members", json={"email": "other@acme.com", "role": "owner"}
    )
    assert response.status_code == 400


def test_inviting_the_same_person_twice_is_refused(client, project):
    as_user(client, OWNER)
    response = client.post(
        f"/api/projects/{project}/members", json={"email": DESIGNER["email"], "role": "viewer"}
    )
    assert response.status_code == 409


def test_the_owner_cannot_be_removed(client, project):
    as_user(client, OWNER)
    response = client.delete(f"/api/projects/{project}/members/{OWNER['id']}")
    assert response.status_code == 400


def test_removing_a_member_revokes_their_access(client, project, store):
    as_user(client, OWNER)
    member_id = f"email:{SALES['email']}"
    assert client.delete(f"/api/projects/{project}/members/{member_id}").status_code == 200

    remaining = client.get(f"/api/projects/{project}").json()["project"]["members"]
    assert SALES["email"] not in [m["email"] for m in remaining]


# --- guidelines -----------------------------------------------------------


def test_the_owner_can_add_a_guideline(client, project):
    as_user(client, OWNER)
    response = client.post(
        f"/api/projects/{project}/guidelines",
        json={"name": "Acme brand", "raw_text": "Logo must have clearspace."},
    )
    assert response.status_code == 201
    assert response.json()["active"] is True

    listed = client.get(f"/api/projects/{project}/guidelines").json()
    assert [g["name"] for g in listed] == ["Acme brand"]


@pytest.mark.anyio
async def test_a_reviewer_cannot_edit_guidelines(client, project, store):
    await link_real_members(store, project)
    as_user(client, DESIGNER)

    response = client.post(
        f"/api/projects/{project}/guidelines", json={"name": "x", "raw_text": "y"}
    )
    assert response.status_code == 403


def test_only_the_owner_answers_grilling(client, project, store):
    """Clarifications need one authoritative voice, or the guideline contradicts itself."""
    as_user(client, OWNER)
    guideline_id = client.post(
        f"/api/projects/{project}/guidelines",
        json={"name": "Acme brand", "raw_text": "Logo must be prominent."},
    ).json()["id"]

    response = client.post(
        f"/api/projects/{project}/guidelines/{guideline_id}/clarifications",
        json={"question": "How prominent?", "answer": "At least 15% of canvas width."},
    )
    assert response.status_code == 200
    assert response.json()["clarifications"][0]["answered_by"] == OWNER["id"]


@pytest.mark.anyio
async def test_a_reviewer_cannot_answer_grilling(client, project, store):
    as_user(client, OWNER)
    guideline_id = client.post(
        f"/api/projects/{project}/guidelines", json={"name": "b", "raw_text": "t"}
    ).json()["id"]

    await link_real_members(store, project)
    as_user(client, DESIGNER)
    response = client.post(
        f"/api/projects/{project}/guidelines/{guideline_id}/clarifications",
        json={"question": "q", "answer": "a"},
    )
    assert response.status_code == 403


@pytest.mark.anyio
async def test_clarifications_reach_the_scanner_verbatim(client, project, store):
    """Guidelines are never compiled — the raw text and answers go through as written."""
    as_user(client, OWNER)
    guideline_id = client.post(
        f"/api/projects/{project}/guidelines",
        json={"name": "Acme", "raw_text": "Logo must be prominent."},
    ).json()["id"]
    client.post(
        f"/api/projects/{project}/guidelines/{guideline_id}/clarifications",
        json={"question": "How prominent?", "answer": "15% of canvas width."},
    )

    assembled = await run_service.assemble_guidelines(store, project)
    assert "Logo must be prominent." in assembled
    assert "15% of canvas width." in assembled
    assert "ANAT-01" in assembled  # built-in rules are always active too


# --- defect threads -------------------------------------------------------


@pytest.mark.anyio
async def test_a_defect_thread_lists_comments_and_available_moves(client, project, store):
    await seed_defect(store, project)
    as_user(client, OWNER)

    body = client.get(f"/api/projects/{project}/defects/d1").json()
    assert body["defect"]["comment"].startswith("Six fingers")
    assert body["comments"] == []
    # fix_submitted is offered as its own upload control, not as a state to pick.
    assert set(body["available_transitions"]) == {"dismissed", "override_approved"}
    assert body["can_submit_fix"] is True


@pytest.mark.anyio
async def test_a_reviewer_sees_only_the_moves_they_may_make(client, project, store):
    await seed_defect(store, project)
    await link_real_members(store, project)
    as_user(client, DESIGNER)

    body = client.get(f"/api/projects/{project}/defects/d1").json()
    assert body["available_transitions"] == []
    assert body["can_submit_fix"] is True


@pytest.mark.anyio
async def test_a_viewer_gets_no_moves(client, project, store):
    await seed_defect(store, project)
    await link_real_members(store, project)
    as_user(client, SALES)

    assert client.get(f"/api/projects/{project}/defects/d1").json()["available_transitions"] == []


@pytest.mark.anyio
async def test_defects_from_another_project_are_not_reachable(client, project, store):
    await seed_defect(store, "some-other-project")
    as_user(client, OWNER)
    assert client.get(f"/api/projects/{project}/defects/d1").status_code == 404


# --- comments and mentions ------------------------------------------------


@pytest.mark.anyio
async def test_posting_a_comment_persists_it(client, project, store):
    await seed_defect(store, project)
    as_user(client, OWNER)

    response = client.post(
        f"/api/projects/{project}/defects/d1/comments", json={"body": "Fixed in v2?"}
    )
    assert response.status_code == 201

    thread = client.get(f"/api/projects/{project}/defects/d1").json()
    assert [c["body"] for c in thread["comments"]] == ["Fixed in v2?"]
    assert thread["comments"][0]["author_name"] == "Ola Owner"


@pytest.mark.anyio
async def test_a_viewer_may_comment(client, project, store):
    """Sales observes and discusses; it just cannot change anything."""
    await seed_defect(store, project)
    await link_real_members(store, project)
    as_user(client, SALES)

    response = client.post(
        f"/api/projects/{project}/defects/d1/comments", json={"body": "Client noticed this too"}
    )
    assert response.status_code == 201


@pytest.mark.anyio
async def test_a_mention_notifies_that_member(client, project, store):
    await seed_defect(store, project)
    await link_real_members(store, project)

    as_user(client, OWNER)
    client.post(
        f"/api/projects/{project}/defects/d1/comments",
        json={"body": "@dee can you regenerate this one?"},
    )

    as_user(client, DESIGNER)
    notifications = client.get("/api/notifications").json()
    assert len(notifications) == 1
    assert notifications[0]["kind"] == "mention"
    assert "pin 1" in notifications[0]["body"]


@pytest.mark.anyio
async def test_mentioning_yourself_does_not_notify_you(client, project, store):
    await seed_defect(store, project)
    as_user(client, OWNER)

    client.post(
        f"/api/projects/{project}/defects/d1/comments", json={"body": "note to self @owner"}
    )
    assert client.get("/api/notifications").json() == []


@pytest.mark.anyio
async def test_an_unknown_handle_notifies_nobody(client, project, store):
    await seed_defect(store, project)
    await link_real_members(store, project)

    as_user(client, OWNER)
    response = client.post(
        f"/api/projects/{project}/defects/d1/comments", json={"body": "@nobody look at this"}
    )
    assert response.status_code == 201
    assert response.json()["mentions"] == []


@pytest.mark.anyio
async def test_an_empty_comment_is_rejected(client, project, store):
    await seed_defect(store, project)
    as_user(client, OWNER)
    response = client.post(f"/api/projects/{project}/defects/d1/comments", json={"body": "   "})
    assert response.status_code == 400


@pytest.mark.anyio
async def test_notifications_can_be_marked_read(client, project, store):
    await seed_defect(store, project)
    await link_real_members(store, project)

    as_user(client, OWNER)
    client.post(f"/api/projects/{project}/defects/d1/comments", json={"body": "@dee look"})

    as_user(client, DESIGNER)
    notification_id = client.get("/api/notifications").json()[0]["id"]
    assert client.post(f"/api/notifications/{notification_id}/read").status_code == 200
    assert client.get("/api/notifications").json() == []


@pytest.mark.anyio
async def test_you_cannot_read_someone_elses_notification(client, project, store):
    await seed_defect(store, project)
    await link_real_members(store, project)

    as_user(client, OWNER)
    client.post(f"/api/projects/{project}/defects/d1/comments", json={"body": "@dee look"})

    as_user(client, DESIGNER)
    notification_id = client.get("/api/notifications").json()[0]["id"]

    as_user(client, SALES)
    assert client.post(f"/api/notifications/{notification_id}/read").status_code == 404


# --- lifecycle ------------------------------------------------------------


@pytest.mark.anyio
async def test_the_owner_can_dismiss_a_false_positive(client, project, store):
    await seed_defect(store, project)
    as_user(client, OWNER)

    response = client.post(
        f"/api/projects/{project}/defects/d1/transition", json={"to": "dismissed"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "dismissed"

    stored = await repo.load(store, DefectRecord, "d1")
    assert stored.status is DefectState.DISMISSED


@pytest.mark.anyio
async def test_a_reviewer_cannot_dismiss(client, project, store):
    await seed_defect(store, project)
    await link_real_members(store, project)
    as_user(client, DESIGNER)

    response = client.post(
        f"/api/projects/{project}/defects/d1/transition", json={"to": "dismissed"}
    )
    assert response.status_code == 403


@pytest.mark.anyio
async def test_nobody_can_mark_a_defect_resolved_by_hand(client, project, store):
    """Resolution is the agent's act after re-checking a fixed version."""
    await seed_defect(store, project)
    as_user(client, OWNER)

    response = client.post(
        f"/api/projects/{project}/defects/d1/transition", json={"to": "verified_resolved"}
    )
    assert response.status_code == 403


@pytest.mark.anyio
async def test_override_approval_requires_a_rationale(client, project, store):
    await seed_defect(store, project)
    as_user(client, OWNER)

    refused = client.post(
        f"/api/projects/{project}/defects/d1/transition", json={"to": "override_approved"}
    )
    assert refused.status_code == 403
    assert "rationale" in refused.json()["detail"]

    accepted = client.post(
        f"/api/projects/{project}/defects/d1/transition",
        json={"to": "override_approved", "rationale": "Client signed off on this crop."},
    )
    assert accepted.status_code == 200
    assert accepted.json()["rationale"] == "Client signed off on this crop."


@pytest.mark.anyio
async def test_a_fix_cannot_be_claimed_without_uploading_one(client, project, store):
    """fix_submitted must carry the version that claims to fix it."""
    await seed_defect(store, project)
    await link_real_members(store, project)
    as_user(client, DESIGNER)

    response = client.post(
        f"/api/projects/{project}/defects/d1/transition", json={"to": "fix_submitted"}
    )
    assert response.status_code == 400
    assert "submit a fixed version" in response.json()["detail"]


@pytest.mark.anyio
async def test_uploading_a_fixed_version_sweeps_up_the_open_defects(client, project, store, blobs):
    """Drives the service directly — the re-check itself needs a live model."""
    from app.services import recheck as recheck_service

    stored_project = await repo.load(store, Project, project)
    run = await run_service.create_run(
        store, blobs, stored_project, User(**OWNER), [("hero.png", png_bytes())]
    )
    image = (await repo.images_for_run(store, run.id))[0]
    await seed_defect(store, project, image_id=image.id)

    version, submitted = await recheck_service.submit_fix(
        store, blobs, stored_project, image, User(**OWNER), "hero_v2.png", png_bytes()
    )

    assert version.version == 2
    assert version.supersedes_id == image.id
    assert [d.id for d in submitted] == ["d1"]
    assert (await repo.load(store, DefectRecord, "d1")).status is DefectState.FIX_SUBMITTED


@pytest.mark.anyio
async def test_only_the_owner_changes_severity(client, project, store):
    await seed_defect(store, project)
    await link_real_members(store, project)

    as_user(client, DESIGNER)
    assert (
        client.post(
            f"/api/projects/{project}/defects/d1/severity", json={"severity": "nitpick"}
        ).status_code
        == 403
    )

    as_user(client, OWNER)
    response = client.post(
        f"/api/projects/{project}/defects/d1/severity", json={"severity": "nitpick"}
    )
    assert response.status_code == 200
    assert response.json()["severity"] == "nitpick"


# --- image approval -------------------------------------------------------


@pytest.mark.anyio
async def test_an_image_cannot_be_approved_with_defects_outstanding(client, project, store):
    await repo.save(
        store,
        ImageAsset(
            id="i1", project_id=project, run_id="r1", filename="hero.png",
            status=ImageStatus.DONE,
        ),
    )
    await seed_defect(store, project)
    as_user(client, OWNER)

    response = client.post(f"/api/projects/{project}/images/i1/approve")
    assert response.status_code == 400
    assert "still open" in response.json()["detail"]


@pytest.mark.anyio
async def test_an_image_is_approved_once_everything_is_closed(client, project, store):
    await repo.save(
        store,
        ImageAsset(
            id="i1", project_id=project, run_id="r1", filename="hero.png",
            status=ImageStatus.DONE,
        ),
    )
    await seed_defect(store, project)

    as_user(client, OWNER)
    client.post(f"/api/projects/{project}/defects/d1/transition", json={"to": "dismissed"})

    response = client.post(f"/api/projects/{project}/images/i1/approve")
    assert response.status_code == 200
    assert response.json()["approved_by"] == OWNER["id"]


@pytest.mark.anyio
async def test_a_reviewer_cannot_approve_an_image(client, project, store):
    await repo.save(
        store,
        ImageAsset(
            id="i1", project_id=project, run_id="r1", filename="hero.png",
            status=ImageStatus.DONE,
        ),
    )
    await link_real_members(store, project)
    as_user(client, DESIGNER)

    assert client.post(f"/api/projects/{project}/images/i1/approve").status_code == 403


# --- memory rules ---------------------------------------------------------


@pytest.mark.anyio
async def test_a_proposed_rule_is_inactive_until_the_owner_approves(client, project, store):
    await seed_defect(store, project)
    await link_real_members(store, project)

    as_user(client, DESIGNER)
    proposal = client.post(
        f"/api/projects/{project}/defects/d1/memory",
        json={"description": "Always check hands for extra fingers"},
    )
    assert proposal.status_code == 201
    rule = proposal.json()["rule"]
    assert rule["active"] is False

    # An unapproved rule must not reach the Scanner.
    assert "extra fingers" not in await run_service.assemble_guidelines(store, project)

    as_user(client, OWNER)
    approved = client.post(f"/api/projects/{project}/memory/{rule['id']}/approve")
    assert approved.status_code == 200
    assert approved.json()["active"] is True

    assembled = await run_service.assemble_guidelines(store, project)
    assert "extra fingers" in assembled
    assert "Memory rules" in assembled


@pytest.mark.anyio
async def test_proposing_a_rule_notifies_the_owner(client, project, store):
    await seed_defect(store, project)
    await link_real_members(store, project)

    as_user(client, DESIGNER)
    client.post(f"/api/projects/{project}/defects/d1/memory", json={"description": "Check hands"})

    as_user(client, OWNER)
    kinds = [n["kind"] for n in client.get("/api/notifications").json()]
    assert "memory_proposed" in kinds


@pytest.mark.anyio
async def test_a_reviewer_cannot_approve_a_rule(client, project, store):
    await seed_defect(store, project)
    await link_real_members(store, project)

    as_user(client, OWNER)
    rule_id = client.post(
        f"/api/projects/{project}/defects/d1/memory", json={"description": "Check hands"}
    ).json()["rule"]["id"]

    as_user(client, DESIGNER)
    assert client.post(f"/api/projects/{project}/memory/{rule_id}/approve").status_code == 403


@pytest.mark.anyio
async def test_an_overlapping_rule_is_surfaced_for_grilling(client, project, store):
    """The Owner is asked before two rules can contradict each other."""
    await seed_defect(store, project)
    as_user(client, OWNER)

    first = client.post(
        f"/api/projects/{project}/defects/d1/memory",
        json={"description": "Always check hands for extra fingers"},
    ).json()["rule"]
    client.post(f"/api/projects/{project}/memory/{first['id']}/approve")

    second = client.post(
        f"/api/projects/{project}/defects/d1/memory",
        json={"description": "Check hands for extra fingers carefully"},
    ).json()

    assert [c["id"] for c in second["collisions"]] == [first["id"]]


@pytest.mark.anyio
async def test_an_unrelated_rule_reports_no_collision(client, project, store):
    await seed_defect(store, project)
    as_user(client, OWNER)

    first = client.post(
        f"/api/projects/{project}/defects/d1/memory",
        json={"description": "Always check hands for extra fingers"},
    ).json()["rule"]
    client.post(f"/api/projects/{project}/memory/{first['id']}/approve")

    second = client.post(
        f"/api/projects/{project}/defects/d1/memory",
        json={"description": "Packaging text must be legible and correctly spelled"},
    ).json()

    assert second["collisions"] == []


# --- uploads --------------------------------------------------------------


def test_uploading_a_non_image_is_rejected(client, project):
    as_user(client, OWNER)
    response = client.post(
        f"/api/projects/{project}/runs",
        files=[("files", ("notes.txt", b"hello", "text/plain"))],
    )
    assert response.status_code == 415


@pytest.mark.anyio
async def test_a_viewer_cannot_upload(client, project, store):
    await link_real_members(store, project)
    as_user(client, SALES)

    response = client.post(
        f"/api/projects/{project}/runs",
        files=[("files", ("hero.png", png_bytes(), "image/png"))],
    )
    assert response.status_code == 403


@pytest.mark.anyio
async def test_creating_a_run_persists_every_image(client, project, store, blobs):
    """Drives the service directly — the pipeline itself needs a live model."""
    stored_project = await repo.load(store, Project, project)
    uploads = [(f"shot_{i}.png", png_bytes()) for i in range(5)]

    run = await run_service.create_run(store, blobs, stored_project, User(**OWNER), uploads)

    assert len(run.image_ids) == 5
    images = await repo.images_for_run(store, run.id)
    assert [i.filename for i in images] == [f"shot_{i}.png" for i in range(5)]
    assert all(i.width == 400 and i.height == 400 for i in images)

    # The originals are really on disk and really readable.
    for image in images:
        assert await blobs.exists(image.original_path)


@pytest.mark.anyio
async def test_an_empty_batch_is_refused(client, project, store, blobs):
    stored_project = await repo.load(store, Project, project)
    with pytest.raises(ValueError, match="at least one image"):
        await run_service.create_run(store, blobs, stored_project, User(**OWNER), [])


@pytest.mark.anyio
async def test_stored_images_are_served_back(client, project, store, blobs):
    stored_project = await repo.load(store, Project, project)
    run = await run_service.create_run(
        store, blobs, stored_project, User(**OWNER), [("hero.png", png_bytes())]
    )
    image = (await repo.images_for_run(store, run.id))[0]

    as_user(client, OWNER)
    response = client.get(f"/api/blobs/{image.original_path}")
    assert response.status_code == 200
    assert Image.open(io.BytesIO(response.content)).size == (400, 400)


def test_blobs_are_not_public(client):
    assert client.get("/api/blobs/projects/p/images/i/original.png").status_code == 401


def test_blob_paths_cannot_escape_the_store(client):
    as_user(client, OWNER)
    assert client.get("/api/blobs/../../../etc/passwd").status_code in (400, 404)


@pytest.mark.anyio
async def test_images_are_listed_with_their_defects(client, project, store, blobs):
    stored_project = await repo.load(store, Project, project)
    run = await run_service.create_run(
        store, blobs, stored_project, User(**OWNER), [("hero.png", png_bytes())]
    )
    image = (await repo.images_for_run(store, run.id))[0]
    await seed_defect(store, project, image_id=image.id)

    as_user(client, OWNER)
    listed = client.get(f"/api/projects/{project}/images").json()

    assert len(listed) == 1
    assert listed[0]["image"]["filename"] == "hero.png"
    assert len(listed[0]["defects"]) == 1
    assert listed[0]["original_url"].startswith("/api/blobs/")


# --- live feed ------------------------------------------------------------


def test_the_event_stream_is_closed_to_non_members(client, project):
    """Access control resolves before streaming begins, so this returns normally."""
    as_user(client, {"id": "stranger", "email": "s@x.com", "name": "S", "picture": ""})
    assert client.get(f"/api/projects/{project}/events").status_code == 404


# The stream's happy path is not tested through TestClient: the endpoint is an
# endless generator and TestClient never signals disconnect, so consuming it hangs
# rather than failing. Event delivery is covered by tests/test_events_and_storage.py
# against the real bus, and the HTTP stream end-to-end by scripts/check_sse.py
# against a real uvicorn server.


# --- image deletion -------------------------------------------------------


async def seed_image_lineage(store, blobs, project_id):
    """A two-version lineage with a defect, dismissal, thread, and real blobs."""
    from app.domain.annotations import Shape, ShapeKind
    from app.domain.entities import Comment, DismissalRecord, ReviewThread, Run

    await repo.save(
        store, Run(id="r1", project_id=project_id, started_by=OWNER["id"], image_ids=["i1"])
    )
    v1 = ImageAsset(
        id="i1", project_id=project_id, run_id="r1", filename="hero.png", width=400, height=400
    )
    v1.original_path = await blobs.write("p/i1/original.png", png_bytes())
    await repo.save(store, v1)
    v2 = ImageAsset(
        id="i2", project_id=project_id, run_id="r1", filename="hero.png",
        version=2, supersedes_id="i1", width=400, height=400,
    )
    v2.original_path = await blobs.write("p/i2/original.png", png_bytes((30, 200, 30)))
    await repo.save(store, v2)

    await seed_defect(store, project_id, image_id="i1")
    await repo.save(
        store,
        Comment(id="c1", project_id=project_id, defect_id="d1", author_id=OWNER["id"], body="hm"),
    )
    await repo.save(
        store,
        DismissalRecord(
            id="x1", project_id=project_id, image_id="i1",
            cells=["A1"], hypothesis="h", reason="fine", stage="inspector",
        ),
    )
    await repo.save(
        store,
        ReviewThread(
            id="t1", project_id=project_id, image_id="i2", pin=2, author_id=OWNER["id"],
            shapes=[Shape(kind=ShapeKind.RECT, points=[10, 10, 50, 50], color="#E24B4A")],
        ),
    )
    await repo.save(
        store,
        Comment(id="c2", project_id=project_id, defect_id="t1", author_id=OWNER["id"], body="?"),
    )


@pytest.mark.anyio
async def test_deleting_an_image_removes_its_whole_lineage_and_records(
    client, project, store, blobs
):
    from app.domain.entities import Comment, DismissalRecord, ReviewThread

    await seed_image_lineage(store, blobs, project)
    as_user(client, OWNER)

    assert client.delete(f"/api/projects/{project}/images/i2").status_code == 204

    assert await repo.load(store, ImageAsset, "i1") is None
    assert await repo.load(store, ImageAsset, "i2") is None
    assert await repo.load(store, DefectRecord, "d1") is None
    assert await repo.load(store, DismissalRecord, "x1") is None
    assert await repo.load(store, ReviewThread, "t1") is None
    assert await repo.load(store, Comment, "c1") is None
    assert await repo.load(store, Comment, "c2") is None
    assert await blobs.exists("p/i1/original.png") is False
    assert await blobs.exists("p/i2/original.png") is False
    assert client.get(f"/api/projects/{project}/images").json() == []


@pytest.mark.anyio
async def test_only_the_owner_may_delete_an_image(client, project, store, blobs):
    await seed_image_lineage(store, blobs, project)
    await link_real_members(store, project)

    as_user(client, DESIGNER)
    assert client.delete(f"/api/projects/{project}/images/i1").status_code == 403
    as_user(client, SALES)
    assert client.delete(f"/api/projects/{project}/images/i1").status_code == 403

    assert await repo.load(store, ImageAsset, "i1") is not None


def test_deleting_an_unknown_image_is_a_404(client, project):
    as_user(client, OWNER)
    assert client.delete(f"/api/projects/{project}/images/nope").status_code == 404


@pytest.mark.anyio
async def test_delete_preview_counts_what_would_die(client, project, store, blobs):
    await seed_image_lineage(store, blobs, project)
    as_user(client, OWNER)

    preview = client.get(f"/api/projects/{project}/images/i2/delete_preview").json()
    assert preview == {
        "versions": 2, "defects": 1, "threads": 1, "comments": 2, "dismissals": 1,
    }


@pytest.mark.anyio
async def test_an_image_cannot_be_approved_while_the_agent_is_still_working(
    client, project, store
):
    await repo.save(
        store,
        ImageAsset(
            id="i9", project_id=project, run_id="r1", filename="wip.png",
            status=ImageStatus.SCANNING,
        ),
    )
    as_user(client, OWNER)

    response = client.post(f"/api/projects/{project}/images/i9/approve")
    assert response.status_code == 400
    assert "not finished" in response.json()["detail"]
