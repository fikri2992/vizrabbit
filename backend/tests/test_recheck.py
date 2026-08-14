"""Submitting a fix and the version chain.

The agent's verdict itself needs a live model, so ``run_recheck`` is exercised by
scripts/check_recheck.py rather than mocked here. What is covered: who may submit a
fix, which defects it sweeps up, and that nothing is closed by the act of uploading.
"""

import io

import pytest
from PIL import Image

from app.domain.entities import (
    Circle,
    DefectRecord,
    ImageAsset,
    Member,
    Project,
    Role,
    User,
)
from app.domain.lifecycle import DefectState
from app.domain.permissions import PermissionError_
from app.domain.taxonomy import Category, Severity
from app.infra import repository as repo
from app.infra.storage import LocalBlobStore
from app.infra.store import InMemoryStore
from app.services import recheck as service

OWNER = User(id="u-owner", email="owner@acme.com", name="Ola")
DESIGNER = User(id="u-designer", email="dee@acme.com", name="Dee")
SALES = User(id="u-sales", email="sam@acme.com", name="Sam")


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture
def blobs(tmp_path):
    return LocalBlobStore(tmp_path)


@pytest.fixture
def project():
    return Project(
        id="p1",
        name="Autumn campaign",
        members=[
            Member(user_id=OWNER.id, email=OWNER.email, role=Role.OWNER),
            Member(user_id=DESIGNER.id, email=DESIGNER.email, role=Role.REVIEWER),
            Member(user_id=SALES.id, email=SALES.email, role=Role.VIEWER),
        ],
    )


def png(size=(400, 400), color=(180, 40, 40)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
async def original(store, blobs, project):
    asset = ImageAsset(
        id="i1", project_id=project.id, run_id="r1", filename="hero.png", width=400, height=400
    )
    asset.original_path = await blobs.write("projects/p1/images/i1/original.png", png())
    await repo.save(store, asset)
    return asset


async def add_defect(store, image_id="i1", defect_id="d1", pin=1, status=DefectState.OPEN):
    defect = DefectRecord(
        id=defect_id,
        project_id="p1",
        image_id=image_id,
        pin=pin,
        cells=["C4"],
        category=Category.ANATOMY,
        severity=Severity.BLOCKER,
        comment="six fingers",
        circle=Circle(cx=100, cy=100, radius=40),
        status=status,
    )
    await repo.save(store, defect)
    return defect


# --- who may submit -------------------------------------------------------


async def test_a_reviewer_may_submit_a_fix(store, blobs, project, original):
    version, _ = await service.submit_fix(
        store, blobs, project, original, DESIGNER, "hero_v2.png", png()
    )
    assert version.version == 2


async def test_the_owner_may_submit_a_fix(store, blobs, project, original):
    version, _ = await service.submit_fix(
        store, blobs, project, original, OWNER, "hero_v2.png", png()
    )
    assert version.version == 2


async def test_a_viewer_may_not_submit_a_fix(store, blobs, project, original):
    with pytest.raises(PermissionError_):
        await service.submit_fix(store, blobs, project, original, SALES, "hero_v2.png", png())


# --- the new version ------------------------------------------------------


async def test_the_new_version_links_back_to_what_it_replaces(store, blobs, project, original):
    version, _ = await service.submit_fix(
        store, blobs, project, original, DESIGNER, "hero_v2.png", png()
    )
    assert version.supersedes_id == original.id
    assert version.run_id == original.run_id
    assert version.project_id == project.id


async def test_the_new_version_is_persisted_with_its_renders(store, blobs, project, original):
    version, _ = await service.submit_fix(
        store, blobs, project, original, DESIGNER, "hero_v2.png", png(size=(640, 480))
    )

    stored = await repo.load(store, ImageAsset, version.id)
    assert (stored.width, stored.height) == (640, 480)
    assert await blobs.exists(stored.original_path)
    assert await blobs.exists(stored.gridded_path)


async def test_versions_keep_incrementing(store, blobs, project, original):
    v2, _ = await service.submit_fix(store, blobs, project, original, DESIGNER, "v2.png", png())
    v3, _ = await service.submit_fix(store, blobs, project, v2, DESIGNER, "v3.png", png())
    assert [v2.version, v3.version] == [2, 3]


async def test_a_missing_filename_falls_back_to_the_original(store, blobs, project, original):
    version, _ = await service.submit_fix(store, blobs, project, original, DESIGNER, "", png())
    assert version.filename == "hero.png"


# --- which defects are swept up ------------------------------------------


async def test_open_defects_move_to_fix_submitted(store, blobs, project, original):
    await add_defect(store, defect_id="d1", pin=1)
    await add_defect(store, defect_id="d2", pin=2, status=DefectState.NEEDS_HUMAN_REVIEW)

    _, submitted = await service.submit_fix(
        store, blobs, project, original, DESIGNER, "v2.png", png()
    )

    assert {d.id for d in submitted} == {"d1", "d2"}
    for defect_id in ("d1", "d2"):
        assert (await repo.load(store, DefectRecord, defect_id)).status is DefectState.FIX_SUBMITTED


async def test_closed_defects_are_left_alone(store, blobs, project, original):
    await add_defect(store, defect_id="d1", pin=1, status=DefectState.DISMISSED)
    await add_defect(store, defect_id="d2", pin=2, status=DefectState.VERIFIED_RESOLVED)
    await add_defect(store, defect_id="d3", pin=3, status=DefectState.OVERRIDE_APPROVED)

    _, submitted = await service.submit_fix(
        store, blobs, project, original, DESIGNER, "v2.png", png()
    )

    assert submitted == []
    assert (await repo.load(store, DefectRecord, "d1")).status is DefectState.DISMISSED
    assert (await repo.load(store, DefectRecord, "d2")).status is DefectState.VERIFIED_RESOLVED


async def test_submitting_a_fix_resolves_nothing_by_itself(store, blobs, project, original):
    """Uploading is a claim, not a verdict. Only the agent closes a defect."""
    await add_defect(store, defect_id="d1")

    _, submitted = await service.submit_fix(
        store, blobs, project, original, DESIGNER, "v2.png", png()
    )

    assert all(d.status is not DefectState.VERIFIED_RESOLVED for d in submitted)
    assert (await repo.load(store, DefectRecord, "d1")).status is DefectState.FIX_SUBMITTED


async def test_defects_on_other_images_are_untouched(store, blobs, project, original):
    await add_defect(store, image_id="other", defect_id="d-other")

    await service.submit_fix(store, blobs, project, original, DESIGNER, "v2.png", png())

    assert (await repo.load(store, DefectRecord, "d-other")).status is DefectState.OPEN


async def test_a_fix_with_no_open_defects_is_still_a_valid_version(store, blobs, project, original):
    version, submitted = await service.submit_fix(
        store, blobs, project, original, DESIGNER, "v2.png", png()
    )
    assert submitted == []
    assert version.version == 2


# --- version history ------------------------------------------------------


async def test_history_of_a_single_version_is_just_itself(store, project, original):
    assert [a.id for a in await service.version_history(store, original)] == [original.id]


async def test_history_reads_oldest_first_from_any_point_in_the_chain(
    store, blobs, project, original
):
    v2, _ = await service.submit_fix(store, blobs, project, original, DESIGNER, "v2.png", png())
    v3, _ = await service.submit_fix(store, blobs, project, v2, DESIGNER, "v3.png", png())

    expected = [original.id, v2.id, v3.id]
    assert [a.id for a in await service.version_history(store, v3)] == expected
    assert [a.id for a in await service.version_history(store, original)] == expected
    assert [a.id for a in await service.version_history(store, v2)] == expected


async def test_fix_submitted_is_not_reachable_without_a_version(store, project):
    """Otherwise a defect waits forever for a re-check with nothing to check."""
    from app.services.review import transition_defect

    defect = await add_defect(store)
    with pytest.raises(ValueError, match="submit a fixed version"):
        await transition_defect(store, project, defect, DESIGNER, DefectState.FIX_SUBMITTED)

    assert (await repo.load(store, DefectRecord, "d1")).status is DefectState.OPEN


async def test_history_does_not_mix_in_other_assets(store, blobs, project, original):
    await repo.save(
        store,
        ImageAsset(id="unrelated", project_id="p1", run_id="r1", filename="other.png"),
    )
    v2, _ = await service.submit_fix(store, blobs, project, original, DESIGNER, "v2.png", png())

    assert [a.id for a in await service.version_history(store, v2)] == [original.id, v2.id]
