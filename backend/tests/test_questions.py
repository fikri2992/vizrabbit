"""Question threads (decision 19 glossary): either answer teaches, none block.

Pure domain + real store; no model calls anywhere on these paths.
"""


import pytest

from app.agents.pipeline import Defect as PipelineDefect
from app.agents.pipeline import Dismissal, ImageReport
from app.domain.brand import (
    MeasuredColour,
    PaletteOffence,
    attach_measurement,
    evaluate,
    parse_measurement,
)
from app.domain.entities import (
    BrandProfile,
    Circle,
    DefectRecord,
    ImageAsset,
    ImageStatus,
    Member,
    PaletteEntry,
    Project,
    Role,
    User,
)
from app.domain.lifecycle import DefectState
from app.domain.permissions import PermissionError_
from app.domain.taxonomy import Category, Severity
from app.imaging.annotate import Annotation
from app.infra import repository as repo
from app.infra.storage import LocalBlobStore
from app.infra.store import InMemoryStore
from app.services import review as review_service
from app.services.brand import profile_id
from app.services.runs import judgment_notes

OWNER = User(id="u-owner", email="owner@acme.com", name="Ola Owner")
REVIEWER = User(id="u-rev", email="dee@acme.com", name="Dee Designer")


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture
def project():
    return Project(
        id="p1",
        name="Autumn",
        members=[
            Member(user_id=OWNER.id, email=OWNER.email, role=Role.OWNER),
            Member(user_id=REVIEWER.id, email=REVIEWER.email, role=Role.REVIEWER),
        ],
    )


def offence(delta_e=5.2, hex_value="#3aad88", nearest="#2aa47d", tolerance=3.0):
    return PaletteOffence(
        cells=["C4"],
        hex=hex_value,
        coverage=0.4,
        nearest_hex=nearest,
        nearest_role="accent teal",
        delta_e=delta_e,
        tolerance=tolerance,
    )


async def seed_question(store, *, rule_ref="", comment="odd texture on the left hand"):
    defect = DefectRecord(
        id="q1",
        project_id="p1",
        image_id="img1",
        pin=1,
        cells=["C4"],
        category=Category.BRAND if rule_ref else Category.ANATOMY,
        severity=Severity.WARNING,
        comment=comment,
        rule_ref=rule_ref,
        circle=Circle(cx=10, cy=10, radius=5),
        status=DefectState.NEEDS_HUMAN_REVIEW,
    )
    await repo.save(store, defect)
    return defect


# --- the measurement round-trip --------------------------------------------


def test_parse_measurement_inverts_describe():
    stamped, _ = attach_measurement("Panel colour looks off.", "", True, [offence()])
    measurement = parse_measurement(stamped)
    assert measurement is not None
    assert measurement.hex == "#3aad88"
    assert measurement.nearest_hex == "#2aa47d"
    assert measurement.delta_e == 5.2


def test_parse_measurement_refuses_prose_without_a_stamp():
    assert parse_measurement("the model thinks the teal is wrong, ΔE vibes") is None


# --- answering --------------------------------------------------------------


@pytest.mark.anyio
async def test_confirming_a_question_makes_it_an_ordinary_open_defect(store, project):
    defect = await seed_question(store)
    updated, adjustment = await review_service.answer_question(
        store, project, defect, REVIEWER, confirmed=True
    )
    assert updated.status is DefectState.OPEN
    assert adjustment == ""


@pytest.mark.anyio
async def test_only_the_owner_can_answer_not_a_problem(store, project):
    """"Not a problem" is a dismissal, and dismissal stays owner-only."""
    defect = await seed_question(store)
    with pytest.raises(PermissionError_):
        await review_service.answer_question(store, project, defect, REVIEWER, confirmed=False)


@pytest.mark.anyio
async def test_a_palette_answer_widens_the_tolerance_and_the_rerun_stops_asking(store, project):
    """Gate 12: either answer teaches — this one teaches the palette."""
    profile = BrandProfile(
        id=profile_id("p1"),
        project_id="p1",
        entries=[PaletteEntry(hex="#2aa47d", role="accent teal", tolerance=3.0)],
        confirmed_by=OWNER.id,
    )
    await repo.save(store, profile)

    stamped, rule_ref = attach_measurement("CTA teal looks off.", "", True, [offence()])
    defect = await seed_question(store, rule_ref=rule_ref, comment=stamped)

    updated, adjustment = await review_service.answer_question(
        store, project, defect, OWNER, confirmed=False
    )
    assert updated.status is DefectState.DISMISSED
    assert "widened to ΔE 5.2" in adjustment

    stored = await repo.load(store, BrandProfile, profile_id("p1"))
    assert stored.entries[0].tolerance == pytest.approx(5.2)
    # The same measurement against the taught profile: silence.
    rerun = evaluate([MeasuredColour(cells=["C4"], hex="#3aad88", coverage=0.4)], stored)
    assert rerun == []


@pytest.mark.anyio
async def test_a_non_palette_dismissal_touches_no_profile(store, project):
    profile = BrandProfile(
        id=profile_id("p1"),
        project_id="p1",
        entries=[PaletteEntry(hex="#2aa47d", tolerance=3.0)],
        confirmed_by=OWNER.id,
    )
    await repo.save(store, profile)
    defect = await seed_question(store)  # anatomy question, no rule_ref

    _, adjustment = await review_service.answer_question(
        store, project, defect, OWNER, confirmed=False
    )
    assert adjustment == ""
    stored = await repo.load(store, BrandProfile, profile_id("p1"))
    assert stored.entries[0].tolerance == 3.0


@pytest.mark.anyio
async def test_an_open_defect_is_not_a_question(store, project):
    defect = await seed_question(store)
    defect.status = DefectState.OPEN
    with pytest.raises(ValueError, match="question"):
        await review_service.answer_question(store, project, defect, OWNER, confirmed=True)


# --- an ignored question never blocks (gate 12) ------------------------------


@pytest.mark.anyio
async def test_an_unanswered_question_does_not_block_approval(store, project, tmp_path):
    blobs = LocalBlobStore(tmp_path)
    del blobs  # approval never touches blobs; fixture parity only
    image = ImageAsset(
        id="img1",
        project_id="p1",
        run_id="r1",
        filename="hero.png",
        slot_id="s1",
        status=ImageStatus.DONE,
        width=320,
        height=320,
    )
    await repo.save(store, image)
    await seed_question(store)  # needs_human_review on this image

    approved = await review_service.approve_image(store, project, image, OWNER)
    assert approved.approved_by == OWNER.id


@pytest.mark.anyio
async def test_an_open_defect_still_blocks_approval(store, project):
    image = ImageAsset(
        id="img1", project_id="p1", run_id="r1", filename="hero.png",
        slot_id="s1", status=ImageStatus.DONE, width=320, height=320,
    )
    await repo.save(store, image)
    defect = await seed_question(store)
    defect.status = DefectState.OPEN
    await repo.save(store, defect)

    with pytest.raises(ValueError, match="still open"):
        await review_service.approve_image(store, project, image, OWNER)


# --- the judgment voice ------------------------------------------------------


def _pipeline_defect(pin, verified):
    return PipelineDefect(
        pin=pin,
        cells=["B2"],
        category=Category.ANATOMY,
        severity=Severity.WARNING,
        comment="x",
        rule_ref="",
        annotation=Annotation(pin=pin, cx=5, cy=5, radius=3, severity=Severity.WARNING),
        circle_iterations=3,
        circle_verified=verified,
    )


def test_judgment_notes_narrate_dismissals_and_questions():
    report = ImageReport(
        defects=[_pipeline_defect(1, verified=True), _pipeline_defect(2, verified=False)],
        dismissals=[
            Dismissal(["A1"], "possible extra finger", "it is a shadow", "inspector"),
        ],
    )
    notes = judgment_notes(report)
    assert notes[0] == "considered 'possible extra finger' at A1 — not a defect: it is a shadow"
    assert any("queued it as a question instead of flagging it" in note for note in notes)
    assert not any("pin 1" in note for note in notes)  # confident findings need no narration


def test_judgment_notes_cap_the_dump():
    report = ImageReport(
        dismissals=[Dismissal(["A1"], f"h{i}", "r", "inspector") for i in range(6)]
    )
    notes = judgment_notes(report)
    assert len(notes) == 4
    assert notes[-1] == "…and let 3 more suspicion(s) go the same way"


def test_judgment_notes_are_silent_on_a_silent_report():
    assert judgment_notes(ImageReport()) == []
