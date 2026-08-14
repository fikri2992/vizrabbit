"""The event bus and blob storage — real queues, real files."""

import asyncio

import pytest

from app.infra.events import MAX_QUEUED_EVENTS, Event, EventBus
from app.infra.storage import ANNOTATED, GRIDDED, ORIGINAL, LocalBlobStore, blob_path

# --- blob paths -----------------------------------------------------------


def test_blob_paths_are_stable_and_inspectable():
    assert blob_path("p1", "i1", ORIGINAL) == "projects/p1/images/i1/original.png"
    assert blob_path("p1", "i1", GRIDDED) == "projects/p1/images/i1/gridded.png"
    assert blob_path("p1", "i1", ANNOTATED) == "projects/p1/images/i1/annotated.png"


def test_blob_paths_separate_projects_and_images():
    assert blob_path("p1", "i1", ORIGINAL) != blob_path("p2", "i1", ORIGINAL)
    assert blob_path("p1", "i1", ORIGINAL) != blob_path("p1", "i2", ORIGINAL)


def test_blob_path_honours_the_extension():
    assert blob_path("p", "i", ORIGINAL, "jpg").endswith("original.jpg")


# --- local blob store -----------------------------------------------------


@pytest.fixture
def blobs(tmp_path):
    return LocalBlobStore(tmp_path)


async def test_written_blobs_read_back_byte_identical(blobs):
    data = b"\x89PNG\r\n\x1a\n" + bytes(range(256))
    await blobs.write("projects/p/images/i/original.png", data)

    assert await blobs.read("projects/p/images/i/original.png") == data


async def test_write_creates_intermediate_directories(blobs):
    await blobs.write("deeply/nested/path/file.png", b"x")
    assert await blobs.exists("deeply/nested/path/file.png")


async def test_exists_is_false_before_writing(blobs):
    assert await blobs.exists("nothing/here.png") is False


async def test_writes_overwrite(blobs):
    await blobs.write("a.png", b"first")
    await blobs.write("a.png", b"second")
    assert await blobs.read("a.png") == b"second"


async def test_write_returns_the_path_for_storing_on_the_entity(blobs):
    assert await blobs.write("a/b.png", b"x") == "a/b.png"


def test_public_urls_route_through_the_api(blobs):
    assert blobs.public_url("projects/p/images/i/original.png").startswith("/api/blobs/")


# --- event bus ------------------------------------------------------------


async def test_a_subscriber_receives_published_events():
    bus = EventBus()
    queue = bus.subscribe("p1")

    await bus.publish(Event(stage="scan_started", project_id="p1", detail={"grid": "8x8"}))

    event = await asyncio.wait_for(queue.get(), timeout=1)
    assert event.stage == "scan_started"
    assert event.detail["grid"] == "8x8"


async def test_events_are_scoped_to_their_project():
    """One project's run must not leak into another project's feed."""
    bus = EventBus()
    mine, theirs = bus.subscribe("p1"), bus.subscribe("p2")

    await bus.publish(Event(stage="scan_started", project_id="p1"))

    assert mine.qsize() == 1
    assert theirs.qsize() == 0


async def test_every_subscriber_to_a_project_gets_the_event():
    bus = EventBus()
    first, second = bus.subscribe("p1"), bus.subscribe("p1")

    await bus.publish(Event(stage="annotating", project_id="p1"))

    assert first.qsize() == 1 and second.qsize() == 1


async def test_publishing_with_no_subscribers_is_harmless():
    await EventBus().publish(Event(stage="scan_started", project_id="p1"))


async def test_unsubscribing_stops_delivery():
    bus = EventBus()
    queue = bus.subscribe("p1")
    bus.unsubscribe("p1", queue)

    await bus.publish(Event(stage="scan_started", project_id="p1"))
    assert queue.qsize() == 0
    assert bus.subscriber_count("p1") == 0


async def test_unsubscribing_twice_is_harmless():
    bus = EventBus()
    queue = bus.subscribe("p1")
    bus.unsubscribe("p1", queue)
    bus.unsubscribe("p1", queue)


async def test_one_stalled_client_does_not_block_the_pipeline():
    """A browser that stops reading must never stall a run."""
    bus = EventBus()
    stalled = bus.subscribe("p1")

    for index in range(MAX_QUEUED_EVENTS + 50):
        await asyncio.wait_for(
            bus.publish(Event(stage="tick", project_id="p1", detail={"i": index})), timeout=1
        )

    assert stalled.qsize() == MAX_QUEUED_EVENTS


async def test_a_stalled_client_keeps_the_newest_events():
    """When dropping, keep what is current — the feed is a live view."""
    bus = EventBus()
    stalled = bus.subscribe("p1")

    total = MAX_QUEUED_EVENTS + 10
    for index in range(total):
        await bus.publish(Event(stage="tick", project_id="p1", detail={"i": index}))

    latest = None
    while not stalled.empty():
        latest = stalled.get_nowait()
    assert latest.detail["i"] == total - 1


async def test_a_stalled_client_does_not_starve_a_healthy_one():
    bus = EventBus()
    _stalled = bus.subscribe("p1")
    healthy = bus.subscribe("p1")

    for index in range(MAX_QUEUED_EVENTS + 20):
        await bus.publish(Event(stage="tick", project_id="p1", detail={"i": index}))
        healthy.get_nowait()

    assert healthy.qsize() == 0


def test_event_payload_carries_stage_run_and_timestamp():
    payload = Event(stage="annotated", project_id="p1", run_id="r1", detail={"pin": 2}).to_payload()

    assert payload["stage"] == "annotated"
    assert payload["run_id"] == "r1"
    assert payload["detail"]["pin"] == 2
    assert payload["at"]


def test_subscriber_count_tracks_connections():
    bus = EventBus()
    assert bus.subscriber_count("p1") == 0
    first = bus.subscribe("p1")
    bus.subscribe("p1")
    assert bus.subscriber_count("p1") == 2
    bus.unsubscribe("p1", first)
    assert bus.subscriber_count("p1") == 1
