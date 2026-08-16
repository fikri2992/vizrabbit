"""Slot behaviour end to end: grouping at upload, the linear-chain guard,
approval completing a slot, and pre-slot data reading with no migration.

Real store, real blob store, real HTTP where the path allows it. The pipeline
itself calls Gemini, so uploads that need images reviewed drive the service
directly and set the resulting status by hand — the same trick the existing
integration suite uses.
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
from app.domain.entities import Circle, DefectRecord, ImageAsset, ImageStatus, Project, User
from app.domain.lifecycle import DefectState
from app.domain.slots import SlotState, slot_state
from app.domain.taxonomy import Category, Severity
from app.infra import repository as repo
from app.infra.storage import LocalBlobStore
from app.infra.store import InMemoryStore
from app.services import recheck as recheck_service
from app.services import review as review_service
from app.services import runs as run_service
from app.services import slots as slot_service

OWNER = {"id": "u-owner", "email": "owner@acme.com", "name": "Ola Owner", "picture": ""}
DESIGNER = {"id": "u-designer", "email": "dee@acme.com", "name": "Dee Designer", "picture": ""}


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
    project_id = client.post("/api/projects", json={"name": "Autumn campaign"}).json()["project"][
        "id"
    ]
    client.post(
        f"/api/projects/{project_id}/members",
        json={"email": DESIGNER["email"], "role": "reviewer"},
    )
    return project_id


async def stored_project(store, project_id) -> Project:
    return await repo.load(store, Project, project_id)


async def link_real_members(store, project_id):
    """Invites store `email:` placeholder ids until first sign-in; give them real ids."""
    project = await repo.load(store, Project, project_id)
    for member in project.members:
        if member.email == DESIGNER["email"]:
            member.user_id = DESIGNER["id"]
    await repo.save(store, project)


async def upload(store, blobs, project_id, names, group_into=None, user=OWNER):
    """Persist a batch the way the endpoint does, without running the pipeline."""
    uploads = [(name, png_bytes()) for name in names]
    return await run_service.create_run(
        store, blobs, await stored_project(store, project_id), User(**user), uploads, group_into
    )


async def finish(store, image_id):
    """Mark an image as reviewed and clean, so approval is legal."""
    asset = await repo.load(store, ImageAsset, image_id)
    asset.status = ImageStatus.DONE
    await repo.save(store, asset)
    return asset


async def seed_defect(store, project_id, image_id, defect_id="d1", state=DefectState.OPEN):
    defect = DefectRecord(
        id=defect_id,
        project_id=project_id,
        image_id=image_id,
        pin=1,
        cells=["C4"],
        category=Category.ANATOMY,
        severity=Severity.BLOCKER,
        comment="Six fingers on the left hand.",
        rule_ref="ANAT-01",
        circle=Circle(cx=100, cy=100, radius=40),
        status=state,
    )
    await repo.save(store, defect)
    return defect


# --- grouping at upload ---------------------------------------------------


@pytest.mark.anyio
async def test_a_plain_batch_gives_every_file_its_own_slot(store, blobs, project):
    """The default costs the uploader nothing and matches pre-slot behaviour."""
    await upload(store, blobs, project, ["hero.png", "tile.png", "banner.png"])

    groups = await slot_service.project_slots(store, project)
    assert len(groups) == 3
    assert all(len(group.variants) == 1 for group in groups)
    assert all(not group.synthetic for group in groups)


@pytest.mark.anyio
async def test_grouping_a_batch_makes_it_one_slots_competing_variants(store, blobs, project):
    await upload(store, blobs, project, ["a.png", "b.png", "c.png"], group_into="new")

    groups = await slot_service.project_slots(store, project)
    assert len(groups) == 1
    assert [chain.variant for chain in groups[0].variants] == [1, 2, 3]


@pytest.mark.anyio
async def test_a_new_slot_is_named_after_the_file_that_opened_it(store, blobs, project):
    await upload(store, blobs, project, ["hero-banner.png"])
    slot = (await repo.slots_for_project(store, project))[0]
    assert slot.name == "hero-banner"


@pytest.mark.anyio
async def test_uploading_into_an_existing_slot_appends_further_variants(store, blobs, project):
    await upload(store, blobs, project, ["a.png", "b.png"], group_into="new")
    slot_id = (await slot_service.project_slots(store, project))[0].slot_id

    await upload(store, blobs, project, ["c.png"], group_into=slot_id)

    group = (await slot_service.project_slots(store, project))[0]
    assert [chain.variant for chain in group.variants] == [1, 2, 3]
    assert group.variants[2].root.filename == "c.png"


@pytest.mark.anyio
async def test_uploading_into_an_unknown_slot_is_refused(store, blobs, project):
    with pytest.raises(ValueError, match="slot not found"):
        await upload(store, blobs, project, ["a.png"], group_into="nope")


@pytest.mark.anyio
async def test_every_variant_in_a_batch_is_queued_for_review(store, blobs, project):
    """Decision 15: upload is the trigger, and it fires per variant, not per slot."""
    run = await upload(store, blobs, project, ["a.png", "b.png", "c.png"], group_into="new")
    assert len(run.image_ids) == 3

    images = await repo.images_for_run(store, run.id)
    assert {image.status for image in images} == {ImageStatus.QUEUED}


# --- branching version trees (decision 13) --------------------------------


@pytest.mark.anyio
async def test_a_second_fix_of_the_same_version_branches_the_tree(store, blobs, project):
    run = await upload(store, blobs, project, ["hero.png"])
    original = (await repo.images_for_run(store, run.id))[0]
    owner = await stored_project(store, project)

    first, _ = await recheck_service.submit_fix(
        store, blobs, owner, original, User(**OWNER), "hero-v2.png", png_bytes()
    )
    second, _ = await recheck_service.submit_fix(
        store, blobs, owner, original, User(**OWNER), "hero-v2b.png", png_bytes()
    )

    # Both fixes point at the same parent and live in the same variant's tree.
    assert first.supersedes_id == original.id
    assert second.supersedes_id == original.id
    group = (await slot_service.project_slots(store, project))[0]
    chain = group.variants[0]
    assert {asset.id for asset in chain.versions} == {original.id, first.id, second.id}
    assert {leaf.id for leaf in chain.leaves} == {first.id, second.id}


@pytest.mark.anyio
async def test_the_branch_reaches_the_client_as_accepted_not_conflict(
    client, store, blobs, project
):
    """Regression: this exact request used to 409 with "add a variant instead"."""
    run = await upload(store, blobs, project, ["hero.png"])
    original = (await repo.images_for_run(store, run.id))[0]
    await recheck_service.submit_fix(
        store, blobs, await stored_project(store, project), original, User(**OWNER),
        "hero-v2.png", png_bytes(),
    )

    as_user(client, OWNER)
    response = client.post(
        f"/api/projects/{project}/images/{original.id}/versions",
        files={"file": ("hero-v2b.png", png_bytes(), "image/png")},
    )
    assert response.status_code == 202
    assert response.json()["version"]["supersedes_id"] == original.id


@pytest.mark.anyio
async def test_version_history_returns_the_whole_tree_not_one_walk(store, blobs, project):
    run = await upload(store, blobs, project, ["hero.png"])
    original = (await repo.images_for_run(store, run.id))[0]
    owner = await stored_project(store, project)
    first, _ = await recheck_service.submit_fix(
        store, blobs, owner, original, User(**OWNER), "hero-v2.png", png_bytes()
    )
    second, _ = await recheck_service.submit_fix(
        store, blobs, owner, original, User(**OWNER), "hero-v2b.png", png_bytes()
    )

    # Asked from either sibling, the answer is the same full tree, root first.
    for asked in (original, first, second):
        history = await recheck_service.version_history(store, asked)
        assert [asset.id for asset in history] == [original.id, first.id, second.id]


@pytest.mark.anyio
async def test_a_fix_stays_inside_its_own_variant(store, blobs, project):
    await upload(store, blobs, project, ["a.png", "b.png"], group_into="new")
    group = (await slot_service.project_slots(store, project))[0]
    second = group.variants[1].tip

    version, _ = await recheck_service.submit_fix(
        store, blobs, await stored_project(store, project), second, User(**OWNER),
        "b-v2.png", png_bytes(),
    )
    assert version.slot_id == second.slot_id
    assert version.variant == 2

    group = (await slot_service.project_slots(store, project))[0]
    assert [len(chain.versions) for chain in group.variants] == [1, 2]


# --- approval, completion, archiving --------------------------------------


@pytest.mark.anyio
async def test_approving_a_variant_completes_the_slot_and_archives_the_siblings(
    store, blobs, project
):
    await upload(store, blobs, project, ["a.png", "b.png", "c.png"], group_into="new")
    group = (await slot_service.project_slots(store, project))[0]
    winner = await finish(store, group.variants[1].tip.id)

    await review_service.approve_image(
        store, await stored_project(store, project), winner, User(**OWNER)
    )

    group = (await slot_service.project_slots(store, project))[0]
    assert group.is_complete
    assert group.winner.variant == 2
    assert group.archived_by(1) == 2
    assert group.archived_by(3) == 2
    counts = await slot_service.open_defect_counts(store, [group])
    assert slot_state(group, counts) is SlotState.COMPLETE


@pytest.mark.anyio
async def test_approving_another_variant_moves_the_approval_and_reverses_the_archive(
    store, blobs, project
):
    """Decision 14: the pick is reversible because archiving was never written down."""
    await upload(store, blobs, project, ["a.png", "b.png"], group_into="new")
    group = (await slot_service.project_slots(store, project))[0]
    first = await finish(store, group.variants[0].tip.id)
    second = await finish(store, group.variants[1].tip.id)
    owner = await stored_project(store, project)

    await review_service.approve_image(store, owner, first, User(**OWNER))
    await review_service.approve_image(store, owner, second, User(**OWNER))

    group = (await slot_service.project_slots(store, project))[0]
    assert group.winner.variant == 2
    assert group.archived_by(1) == 2
    assert group.archived_by(2) is None
    approved = [chain.variant for chain in group.variants if chain.is_approved]
    assert approved == [2], "a slot holds at most one approved variant"


@pytest.mark.anyio
async def test_archived_variants_do_not_keep_a_slot_in_the_attention_count(
    store, blobs, project
):
    await upload(store, blobs, project, ["a.png", "b.png"], group_into="new")
    group = (await slot_service.project_slots(store, project))[0]
    loser = group.variants[0].tip
    winner = await finish(store, group.variants[1].tip.id)
    await seed_defect(store, project, loser.id)

    assert await slot_service.needs_attention(store, project) == 1

    await review_service.approve_image(
        store, await stored_project(store, project), winner, User(**OWNER)
    )
    assert await slot_service.needs_attention(store, project) == 0


@pytest.mark.anyio
async def test_archiving_never_touches_the_losing_variants_verdicts(store, blobs, project):
    """An archived variant's findings stay true — nothing re-runs, nothing cancels."""
    await upload(store, blobs, project, ["a.png", "b.png"], group_into="new")
    group = (await slot_service.project_slots(store, project))[0]
    loser = await finish(store, group.variants[0].tip.id)
    winner = await finish(store, group.variants[1].tip.id)
    await seed_defect(store, project, loser.id)

    await review_service.approve_image(
        store, await stored_project(store, project), winner, User(**OWNER)
    )

    survived = await repo.defects_for_image(store, loser.id)
    assert [defect.status for defect in survived] == [DefectState.OPEN]
    assert (await repo.load(store, ImageAsset, loser.id)).status is ImageStatus.DONE


@pytest.mark.anyio
async def test_a_variant_with_open_defects_still_cannot_be_approved(store, blobs, project):
    await upload(store, blobs, project, ["a.png"], group_into="new")
    group = (await slot_service.project_slots(store, project))[0]
    only = await finish(store, group.variants[0].tip.id)
    await seed_defect(store, project, only.id)

    with pytest.raises(ValueError, match="still open"):
        await review_service.approve_image(
            store, await stored_project(store, project), only, User(**OWNER)
        )


# --- pre-slot data --------------------------------------------------------


@pytest.mark.anyio
async def test_a_legacy_project_lists_every_image_with_no_migration_step(
    client, store, blobs, project
):
    """Gate 6: images written before slots existed stay visible and reviewable."""
    for index in range(3):
        asset = ImageAsset(
            id=f"legacy-{index}",
            project_id=project,
            run_id="legacy-run",
            filename=f"legacy-{index}.png",
            status=ImageStatus.DONE,
        )
        asset.original_path = await blobs.write(f"{project}/{asset.id}/original.png", png_bytes())
        await repo.save(store, asset)

    as_user(client, OWNER)
    slots = client.get(f"/api/projects/{project}/slots").json()

    assert len(slots) == 3
    assert all(slot["synthetic"] for slot in slots)
    assert {slot["name"] for slot in slots} == {f"legacy-{i}.png" for i in range(3)}
    assert all(len(slot["variants"]) == 1 for slot in slots)
    # No writes: the slots collection is still empty.
    assert await repo.slots_for_project(store, project) == []


@pytest.mark.anyio
async def test_a_legacy_image_can_still_be_approved(store, blobs, project):
    asset = ImageAsset(
        id="legacy-1", project_id=project, run_id="legacy-run", filename="old.png",
        status=ImageStatus.DONE,
    )
    await repo.save(store, asset)

    approved = await review_service.approve_image(
        store, await stored_project(store, project), asset, User(**OWNER)
    )
    assert approved.approved_by == OWNER["id"]

    group = (await slot_service.project_slots(store, project))[0]
    assert group.is_complete


@pytest.mark.anyio
async def test_naming_a_legacy_slot_writes_it_down_for_good(client, store, blobs, project):
    asset = ImageAsset(
        id="legacy-1", project_id=project, run_id="legacy-run", filename="old.png",
        status=ImageStatus.DONE,
    )
    asset.original_path = await blobs.write(f"{project}/legacy-1/original.png", png_bytes())
    await repo.save(store, asset)

    as_user(client, OWNER)
    response = client.post(
        f"/api/projects/{project}/slots/legacy-1/name", json={"name": "Hero banner"}
    )
    assert response.status_code == 200

    slots = client.get(f"/api/projects/{project}/slots").json()
    assert slots[0]["name"] == "Hero banner"
    assert slots[0]["synthetic"] is False
    assert (await repo.load(store, ImageAsset, "legacy-1")).slot_id == "legacy-1"


# --- the slots endpoint ---------------------------------------------------


@pytest.mark.anyio
async def test_the_slot_view_carries_what_the_history_tree_draws(client, store, blobs, project):
    await upload(store, blobs, project, ["a.png", "b.png"], group_into="new")
    group = (await slot_service.project_slots(store, project))[0]
    winner = await finish(store, group.variants[1].tip.id)
    await review_service.approve_image(
        store, await stored_project(store, project), winner, User(**OWNER)
    )

    as_user(client, OWNER)
    slot = client.get(f"/api/projects/{project}/slots").json()[0]

    assert slot["state"] == "complete"
    loser, champion = slot["variants"]
    assert loser["archived_by"] == 2
    assert champion["archived_by"] is None
    assert champion["approved"] is True
    assert champion["approved_by_name"] == "Ola Owner"
    assert loser["versions"][0]["uploader_name"] == "Ola Owner"
    assert loser["versions"][0]["original_url"]


@pytest.mark.anyio
async def test_the_review_view_states_where_the_image_sits_in_its_slot(
    client, store, blobs, project
):
    await upload(store, blobs, project, ["a.png", "b.png", "c.png"], group_into="new")
    group = (await slot_service.project_slots(store, project))[0]
    middle = group.variants[1].tip

    as_user(client, OWNER)
    view = client.get(f"/api/projects/{project}/images/{middle.id}").json()

    assert view["slot"]["variant"] == 2
    assert view["slot"]["variant_count"] == 3
    assert view["slot"]["version"] == 1
    assert [sibling["variant"] for sibling in view["slot"]["siblings"]] == [1, 2, 3]


@pytest.mark.anyio
async def test_adding_a_variant_from_the_slot_card_extends_the_slot_and_triggers_review(
    client, store, blobs, project, monkeypatch
):
    """The pipeline is replaced by a recorder because reviewing calls Gemini.

    What is being asserted is the trigger itself (decision 15: upload is the only
    one), and the recorder is asked which image it was handed — not merely whether
    something was called.
    """
    reviewed: list[str] = []

    async def record(store_, blobs_, bus_, project_, run_, image_id):
        reviewed.append(image_id)

    monkeypatch.setattr(run_service, "review_one", record)

    await upload(store, blobs, project, ["a.png"], group_into="new")
    slot_id = (await slot_service.project_slots(store, project))[0].slot_id
    await link_real_members(store, project)

    as_user(client, DESIGNER)
    response = client.post(
        f"/api/projects/{project}/slots/{slot_id}/variants",
        files={"file": ("competitor.png", png_bytes(), "image/png")},
    )
    assert response.status_code == 202
    assert response.json()["variant"] == 2
    assert response.json()["uploaded_by"] == DESIGNER["id"]

    group = (await slot_service.project_slots(store, project))[0]
    assert len(group.variants) == 2
    assert reviewed == [group.variants[1].tip.id]


@pytest.mark.anyio
async def test_a_viewer_cannot_add_a_variant(client, store, blobs, project):
    await upload(store, blobs, project, ["a.png"], group_into="new")
    slot_id = (await slot_service.project_slots(store, project))[0].slot_id

    as_user(client, {"id": "u-sales", "email": "sam@acme.com", "name": "Sam", "picture": ""})
    response = client.post(
        f"/api/projects/{project}/slots/{slot_id}/variants",
        files={"file": ("x.png", png_bytes(), "image/png")},
    )
    assert response.status_code in (403, 404)


# --- deletion -------------------------------------------------------------


@pytest.mark.anyio
async def test_deleting_a_slot_removes_every_variant_and_its_versions(
    client, store, blobs, project
):
    await upload(store, blobs, project, ["a.png", "b.png"], group_into="new")
    group = (await slot_service.project_slots(store, project))[0]
    await recheck_service.submit_fix(
        store, blobs, await stored_project(store, project), group.variants[0].tip,
        User(**OWNER), "a-v2.png", png_bytes(),
    )
    slot_id = group.slot_id

    as_user(client, OWNER)
    preview = client.get(f"/api/projects/{project}/slots/{slot_id}/delete_preview").json()
    assert preview == {"variants": 2, "versions": 3, "defects": 0, "comments": 0}

    assert client.delete(f"/api/projects/{project}/slots/{slot_id}").status_code == 204
    assert await repo.images_for_project(store, project) == []
    assert await repo.slots_for_project(store, project) == []


@pytest.mark.anyio
async def test_deleting_the_last_variant_takes_the_empty_slot_with_it(store, blobs, project):
    await upload(store, blobs, project, ["a.png"], group_into="new")
    group = (await slot_service.project_slots(store, project))[0]

    await run_service.delete_image(
        store, blobs, await stored_project(store, project), User(**OWNER), group.variants[0].tip
    )
    assert await repo.slots_for_project(store, project) == []


@pytest.mark.anyio
async def test_deleting_one_variant_leaves_the_slot_and_its_siblings_standing(
    store, blobs, project
):
    await upload(store, blobs, project, ["a.png", "b.png"], group_into="new")
    group = (await slot_service.project_slots(store, project))[0]

    await run_service.delete_image(
        store, blobs, await stored_project(store, project), User(**OWNER), group.variants[0].tip
    )

    remaining = await slot_service.project_slots(store, project)
    assert len(remaining) == 1
    assert [chain.variant for chain in remaining[0].variants] == [2]
    assert len(await repo.slots_for_project(store, project)) == 1


# --- Phase 10: spec, derived marks, dismissals, placement -------------------


@pytest.mark.anyio
async def test_setting_a_spec_makes_the_missing_deliverable_a_mark(
    client, store, blobs, project
):
    run = await upload(store, blobs, project, ["hero.png"])  # 320x320 → 1:1
    await finish(store, run.image_ids[0])
    slot_id = (await slot_service.project_slots(store, project))[0].slot_id

    as_user(client, OWNER)
    response = client.post(
        f"/api/projects/{project}/slots/{slot_id}/spec", json={"spec": ["1:1", "9:16"]}
    )
    assert response.status_code == 200

    view = client.get(f"/api/projects/{project}/slots").json()[0]
    assert view["spec"] == ["1:1", "9:16"]
    missing = [m for m in view["marks"] if m["kind"] == "missing"]
    assert [m["label"] for m in missing] == ["9:16"]  # the 1:1 exists, the 9:16 does not


def test_a_nonsense_aspect_is_rejected(client, project):
    as_user(client, OWNER)
    response = client.post(
        f"/api/projects/{project}/slots/whatever/spec", json={"spec": ["banana"]}
    )
    assert response.status_code in (400, 404)  # slot lookup may refuse first; both refuse


@pytest.mark.anyio
async def test_dismissing_a_mark_hides_it_for_that_user_only(client, store, blobs, project):
    run = await upload(store, blobs, project, ["hero.png"])
    await finish(store, run.image_ids[0])
    slot_id = (await slot_service.project_slots(store, project))[0].slot_id
    await link_real_members(store, project)

    as_user(client, OWNER)
    client.post(f"/api/projects/{project}/slots/{slot_id}/spec", json={"spec": ["9:16"]})
    key = client.get(f"/api/projects/{project}/slots").json()[0]["marks"][0]["key"]

    assert client.post(
        f"/api/projects/{project}/slots/marks/dismiss", json={"key": key}
    ).status_code == 204

    owner_marks = client.get(f"/api/projects/{project}/slots").json()[0]["marks"]
    assert key not in [m["key"] for m in owner_marks]

    as_user(client, DESIGNER)
    designer_marks = client.get(f"/api/projects/{project}/slots").json()[0]["marks"]
    assert key in [m["key"] for m in designer_marks]  # dismissal is per person


@pytest.mark.anyio
async def test_a_specless_slot_reads_exactly_as_before(client, store, blobs, project):
    """Gate 10 regression: no spec ⇒ empty spec fields, no spec-born marks."""
    run = await upload(store, blobs, project, ["hero.png"])
    await finish(store, run.image_ids[0])

    as_user(client, OWNER)
    view = client.get(f"/api/projects/{project}/slots").json()[0]
    assert view["spec"] == []
    assert view["due_at"] is None
    # the only mark a clean spec-less slot can earn is "pickable" — derived from
    # state the card already shows, never from stored agenda
    assert [m["kind"] for m in view["marks"]] in ([], ["pickable"])
    assert {"slot_id", "name", "state", "synthetic", "variants"} <= set(view)


def test_placement_lands_on_the_run_document(client, project):
    as_user(client, OWNER)
    response = client.post(
        f"/api/projects/{project}/runs",
        files=[("files", ("a.png", png_bytes(), "image/png"))],
        data={"placement": "tiktok"},
    )
    assert response.status_code == 202
    assert response.json()["placement"] == "tiktok"


def test_omitted_placement_stays_empty(client, project):
    as_user(client, OWNER)
    response = client.post(
        f"/api/projects/{project}/runs",
        files=[("files", ("a.png", png_bytes(), "image/png"))],
    )
    assert response.json()["placement"] == ""
