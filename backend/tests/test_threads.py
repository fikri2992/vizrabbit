"""Review threads: anchoring, pin numbering, permissions, and the API surface.

The ask-agent inspection itself calls Gemini and is exercised by
scripts/check_ask_agent.py; here everything around it is covered with real
persistence and real requests.
"""

import pytest

from app.domain.annotations import Shape, ShapeKind
from app.domain.entities import (
    Circle,
    DefectRecord,
    ImageAsset,
    Member,
    Project,
    Role,
    ThreadAgentState,
    User,
)
from app.domain.permissions import PermissionError_
from app.domain.taxonomy import Category, Severity
from app.infra import repository as repo
from app.infra.store import InMemoryStore
from app.services import threads as service

OWNER = User(id="u-owner", email="owner@acme.com", name="Ola")
DESIGNER = User(id="u-designer", email="dee@acme.com", name="Dee")
SALES = User(id="u-sales", email="sam@acme.com", name="Sam")


@pytest.fixture
def store():
    return InMemoryStore()


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


@pytest.fixture
async def image(store):
    asset = ImageAsset(
        id="i1", project_id="p1", run_id="r1", filename="hero.png", width=800, height=800
    )
    await repo.save(store, asset)
    return asset


def a_circle():
    return [Shape(kind=ShapeKind.CIRCLE, points=[250, 350, 20])]


async def seed_defect(store, pin=1):
    await repo.save(
        store,
        DefectRecord(
            id=f"d{pin}",
            project_id="p1",
            image_id="i1",
            pin=pin,
            cells=["C4"],
            category=Category.ANATOMY,
            severity=Severity.BLOCKER,
            comment="six fingers",
            circle=Circle(cx=100, cy=100, radius=40),
        ),
    )


# --- creation -------------------------------------------------------------


async def test_a_thread_carries_its_drawing_and_first_comment(store, project, image):
    thread, comment = await service.create_thread(
        store, project, image, DESIGNER, "Is this reflection off?", a_circle()
    )

    stored = await repo.load(store, type(thread), thread.id)
    assert stored.shapes[0].kind is ShapeKind.CIRCLE
    assert stored.author_name == "Dee"
    assert comment.body == "Is this reflection off?"
    assert (await repo.comments_for_defect(store, thread.id))[0].body == comment.body


async def test_every_comment_is_anchored(store, project, image):
    with pytest.raises(ValueError, match="draw on the image"):
        await service.create_thread(store, project, image, DESIGNER, "floating comment", [])


async def test_a_blank_body_is_rejected(store, project, image):
    with pytest.raises(ValueError, match="body"):
        await service.create_thread(store, project, image, DESIGNER, "   ", a_circle())


async def test_viewers_can_annotate_too(store, project, image):
    """Sales can point at things — commenting is a viewer right; asking the agent is not."""
    thread, _ = await service.create_thread(
        store, project, image, SALES, "client saw this", a_circle()
    )
    assert thread.author_id == SALES.id


async def test_a_stranger_cannot(store, project, image):
    with pytest.raises(PermissionError_):
        await service.create_thread(
            store, project, image, User(id="x", email="x@x.com"), "hi", a_circle()
        )


# --- pin numbering --------------------------------------------------------


async def test_pins_continue_the_defect_sequence(store, project, image):
    await seed_defect(store, pin=1)
    await seed_defect(store, pin=2)

    thread, _ = await service.create_thread(store, project, image, DESIGNER, "look", a_circle())
    assert thread.pin == 3


async def test_pins_count_existing_threads_as_well(store, project, image):
    first, _ = await service.create_thread(store, project, image, DESIGNER, "one", a_circle())
    second, _ = await service.create_thread(store, project, image, DESIGNER, "two", a_circle())
    assert (first.pin, second.pin) == (1, 2)


async def test_a_fresh_image_starts_at_pin_one(store, project, image):
    thread, _ = await service.create_thread(store, project, image, DESIGNER, "first", a_circle())
    assert thread.pin == 1


# --- replies and resolve --------------------------------------------------


async def test_replies_append_in_order(store, project, image):
    thread, _ = await service.create_thread(store, project, image, DESIGNER, "start", a_circle())
    await service.reply(store, project, thread, OWNER, "agree")
    await service.reply(store, project, thread, SALES, "client too")

    bodies = [c.body for c in await repo.comments_for_defect(store, thread.id)]
    assert bodies == ["start", "agree", "client too"]


async def test_participants_can_resolve_and_reopen(store, project, image):
    thread, _ = await service.create_thread(store, project, image, DESIGNER, "start", a_circle())

    resolved = await service.resolve(store, project, thread, SALES, True)
    assert resolved.resolved is True

    reopened = await service.resolve(store, project, thread, DESIGNER, False)
    assert reopened.resolved is False


async def test_new_threads_have_no_agent_involvement(store, project, image):
    thread, _ = await service.create_thread(store, project, image, DESIGNER, "start", a_circle())
    assert thread.agent_state is ThreadAgentState.NONE
    assert thread.defect_id is None
