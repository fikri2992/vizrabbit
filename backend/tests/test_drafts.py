"""Agent-drafted fixes: the whitelist boundary, authorship, discard, and cost.

Real store, real blob store, real domain logic. The two model calls — the
editor and the recheck — are recorded fakes, because gate 11 is about *when*
they fire and what gets persisted, which the recorders make assertable.
"""

import io
from datetime import UTC, datetime

import pytest
from PIL import Image

from app.agents import editor
from app.domain.entities import (
    Circle,
    DefectRecord,
    ImageAsset,
    ImageStatus,
    Member,
    Project,
    Role,
    Run,
    Slot,
    User,
)
from app.domain.lifecycle import DefectState
from app.domain.slots import group_into_slots
from app.domain.taxonomy import Category, Severity
from app.infra import repository as repo
from app.infra.events import EventBus
from app.infra.storage import LocalBlobStore
from app.infra.store import InMemoryStore
from app.services import drafts as draft_service
from app.services import recheck as recheck_service
from app.services import slots as slot_service

OWNER = User(id="u-owner", email="owner@acme.com", name="Ola Owner")


def png_bytes(size=(320, 320), color=(120, 60, 40)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture
def blobs(tmp_path):
    return LocalBlobStore(tmp_path)


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def project():
    return Project(
        id="p1",
        name="Autumn",
        members=[Member(user_id=OWNER.id, email=OWNER.email, name=OWNER.name, role=Role.OWNER)],
    )


@pytest.fixture
def edits(monkeypatch):
    """The editor as a recorder: counts calls, returns a real PNG."""
    calls: list[list[str]] = []

    async def fake(original_png: bytes, instructions: list[str]) -> bytes:
        calls.append(instructions)
        return png_bytes(color=(20, 100, 60))

    monkeypatch.setattr(editor, "draft_fix", fake)
    return calls


@pytest.fixture
def rechecks(monkeypatch):
    """run_recheck as a recorder — the real one calls Gemini."""
    calls: list[tuple[str, str]] = []

    async def fake(store, blobs, bus, project, original, version):
        calls.append((original.id, version.id))
        version.status = ImageStatus.DONE
        await repo.save(store, version)
        return []

    monkeypatch.setattr(recheck_service, "run_recheck", fake)
    return calls


async def seed_image(store, blobs, project, *, image_id="img1", slot_id="s1") -> ImageAsset:
    asset = ImageAsset(
        id=image_id,
        project_id=project.id,
        run_id="r1",
        filename=f"{image_id}.png",
        slot_id=slot_id,
        uploaded_by=OWNER.id,
        width=320,
        height=320,
        status=ImageStatus.DONE,
    )
    asset.original_path = await blobs.write(
        f"projects/p1/images/{image_id}/original.png", png_bytes()
    )
    await repo.save(store, asset)
    await repo.save(store, Slot(id=slot_id, project_id=project.id, name="Hero"))
    return asset


async def seed_defect(store, image_id, *, defect_id, category, status=DefectState.OPEN):
    defect = DefectRecord(
        id=defect_id,
        project_id="p1",
        image_id=image_id,
        pin=1,
        cells=["D4"],
        category=category,
        severity=Severity.BLOCKER,
        comment=f"{category}: fix me",
        rule_ref="BRAND-PALETTE" if category is Category.BRAND else "",
        circle=Circle(cx=10, cy=10, radius=5),
        status=status,
        created_at=datetime(2026, 8, 20, tzinfo=UTC),
    )
    await repo.save(store, defect)
    return defect


def run_for(asset: ImageAsset) -> Run:
    return Run(
        id=asset.run_id, project_id=asset.project_id, started_by=OWNER.id, image_ids=[asset.id]
    )


# --- the whitelist boundary (gate 11) --------------------------------------


@pytest.mark.anyio
async def test_a_mechanical_defect_earns_a_draft_branch(
    store, blobs, bus, project, edits, rechecks
):
    asset = await seed_image(store, blobs, project)
    defect = await seed_defect(store, asset.id, defect_id="d1", category=Category.ARTIFACT)

    drafts = await draft_service.draft_pass(store, blobs, bus, project, run_for(asset))

    assert len(drafts) == 1
    draft = drafts[0]
    assert draft.uploaded_by == draft_service.AGENT_USER_ID
    assert draft.supersedes_id == asset.id
    assert draft.version == 2
    assert draft.original_path and draft.gridded_path

    stored = await repo.load(store, DefectRecord, defect.id)
    assert stored.status is DefectState.FIX_SUBMITTED
    assert stored.resolved_in_image_id == draft.id
    assert rechecks == [(asset.id, draft.id)]  # the same recheck judges the draft


@pytest.mark.anyio
async def test_creative_categories_never_reach_the_editor(
    store, blobs, bus, project, edits, rechecks
):
    asset = await seed_image(store, blobs, project)
    await seed_defect(store, asset.id, defect_id="d1", category=Category.BRAND)
    await seed_defect(store, asset.id, defect_id="d2", category=Category.MEMORY)

    drafts = await draft_service.draft_pass(store, blobs, bus, project, run_for(asset))

    assert drafts == []
    assert edits == []
    assert rechecks == []


@pytest.mark.anyio
async def test_a_mixed_image_drafts_only_its_mechanical_half(
    store, blobs, bus, project, edits, rechecks
):
    asset = await seed_image(store, blobs, project)
    await seed_defect(store, asset.id, defect_id="mech", category=Category.ANATOMY)
    brand = await seed_defect(store, asset.id, defect_id="crea", category=Category.BRAND)

    (draft,) = await draft_service.draft_pass(store, blobs, bus, project, run_for(asset))

    mech = await repo.load(store, DefectRecord, "mech")
    assert mech.status is DefectState.FIX_SUBMITTED
    assert mech.resolved_in_image_id == draft.id
    untouched = await repo.load(store, DefectRecord, brand.id)
    assert untouched.status is DefectState.OPEN  # the creative call stays with humans
    assert untouched.resolved_in_image_id is None


@pytest.mark.anyio
async def test_a_question_is_not_the_agents_to_act_on(store, blobs, bus, project, edits, rechecks):
    asset = await seed_image(store, blobs, project)
    await seed_defect(
        store, asset.id, defect_id="q1", category=Category.ARTIFACT,
        status=DefectState.NEEDS_HUMAN_REVIEW,
    )
    assert await draft_service.draft_pass(store, blobs, bus, project, run_for(asset)) == []
    assert edits == []


@pytest.mark.anyio
async def test_one_editor_call_per_image_however_many_defects(
    store, blobs, bus, project, edits, rechecks
):
    """Gate 11 cost cap: instructions aggregate, the call count does not."""
    asset = await seed_image(store, blobs, project)
    await seed_defect(store, asset.id, defect_id="d1", category=Category.ANATOMY)
    await seed_defect(store, asset.id, defect_id="d2", category=Category.ARTIFACT)

    await draft_service.draft_pass(store, blobs, bus, project, run_for(asset))

    assert len(edits) == 1
    assert len(edits[0]) == 2  # both defects in the one prompt


@pytest.mark.anyio
async def test_an_editor_that_returns_nothing_leaves_no_trace(
    store, blobs, bus, project, monkeypatch, rechecks
):
    async def nothing(original_png, instructions):
        return None

    monkeypatch.setattr(editor, "draft_fix", nothing)
    asset = await seed_image(store, blobs, project)
    defect = await seed_defect(store, asset.id, defect_id="d1", category=Category.ARTIFACT)

    assert await draft_service.draft_pass(store, blobs, bus, project, run_for(asset)) == []
    stored = await repo.load(store, DefectRecord, defect.id)
    assert stored.status is DefectState.OPEN
    assert (await repo.find(store, ImageAsset, where={"run_id": "r1"}))[0].id == asset.id


@pytest.mark.anyio
async def test_a_no_drafts_slot_is_left_alone(store, blobs, bus, project, edits, rechecks):
    asset = await seed_image(store, blobs, project)
    slot = await repo.load(store, Slot, "s1")
    slot.no_drafts = True
    await repo.save(store, slot)
    await seed_defect(store, asset.id, defect_id="d1", category=Category.ARTIFACT)

    assert await draft_service.draft_pass(store, blobs, bus, project, run_for(asset)) == []
    assert edits == []


# --- the draft is an ordinary version (gate 11) ----------------------------


@pytest.mark.anyio
async def test_a_draft_is_indistinguishable_to_every_read_path(
    store, blobs, bus, project, edits, rechecks
):
    asset = await seed_image(store, blobs, project)
    await seed_defect(store, asset.id, defect_id="d1", category=Category.ARTIFACT)
    (draft,) = await draft_service.draft_pass(store, blobs, bus, project, run_for(asset))

    everything = await repo.find(store, ImageAsset, where={"run_id": "r1"})
    (group,) = group_into_slots(everything)
    chain = group.variants[0]
    assert [a.id for a in chain.versions] == [asset.id, draft.id]
    assert chain.tip.id == draft.id

    # And the human can approve it like any other version.
    approved = await slot_service.apply_approval(store, group, chain.tip, OWNER.id)
    assert approved.approved_by == OWNER.id


# --- discard ----------------------------------------------------------------


@pytest.mark.anyio
async def test_discarding_a_draft_puts_the_world_back(store, blobs, bus, project, edits, rechecks):
    asset = await seed_image(store, blobs, project)
    defect = await seed_defect(store, asset.id, defect_id="d1", category=Category.ARTIFACT)
    (draft,) = await draft_service.draft_pass(store, blobs, bus, project, run_for(asset))

    await draft_service.discard_draft(store, blobs, project, draft)

    assert await repo.load(store, ImageAsset, draft.id) is None
    stored = await repo.load(store, DefectRecord, defect.id)
    assert stored.status is DefectState.OPEN
    assert stored.resolved_in_image_id is None
    slot = await repo.load(store, Slot, "s1")
    assert slot.no_drafts is True  # propose, don't draft, from now on

    # And the preference actually bites: a second pass drafts nothing.
    assert await draft_service.draft_pass(store, blobs, bus, project, run_for(asset)) == []


@pytest.mark.anyio
async def test_a_human_version_cannot_be_discarded(store, blobs, bus, project):
    asset = await seed_image(store, blobs, project)
    with pytest.raises(ValueError, match="agent drafts"):
        await draft_service.discard_draft(store, blobs, project, asset)
