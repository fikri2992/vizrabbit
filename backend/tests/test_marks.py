"""Derived marks: the agenda that is never stored.

Pure functions over real entities — the same discipline as test_slots.py.
Time never comes from a clock; it is an argument, so stall boundaries are exact.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.entities import ImageAsset, ImageStatus, Slot
from app.domain.marks import (
    DefectSignal,
    Mark,
    MarkKind,
    marks_for,
    parse_aspect,
    satisfies,
)
from app.domain.slots import SlotState, group_into_slots

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)


def image(image_id, *, width=1600, height=900, variant=1, approved=None, minutes=0):
    return ImageAsset(
        id=image_id,
        project_id="p1",
        run_id="r1",
        filename=f"{image_id}.png",
        slot_id="s1",
        variant=variant,
        width=width,
        height=height,
        status=ImageStatus.DONE,
        approved_by=approved,
        created_at=NOW + timedelta(minutes=minutes),
    )


def group_of(*images):
    return group_into_slots(list(images))[0]


def slot(spec=(), due=None):
    return Slot(id="s1", project_id="p1", spec=list(spec), due_at=due)


# --- aspect parsing and matching -------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("16:9", 16 / 9),
        ("9:16", 9 / 16),
        ("1:1", 1.0),
        ("21:9", 21 / 9),
        ("banana", None),
        ("16", None),
        ("0:9", None),
        ("16:-9", None),
        ("", None),
    ],
)
def test_parse_aspect(text, expected):
    assert parse_aspect(text) == expected


def test_a_variant_satisfies_its_aspect_within_two_percent():
    # 1080x1920 is exactly 9:16; 1080x1900 is ~1% off and still passes.
    assert satisfies("9:16", group_of(image("a", width=1080, height=1920)))
    assert satisfies("9:16", group_of(image("a", width=1080, height=1900)))


def test_a_different_shape_does_not_satisfy_the_spec():
    # 4:5 is nowhere near 9:16, and must not be counted as it.
    assert not satisfies("9:16", group_of(image("a", width=1080, height=1350)))


def test_matching_reads_the_root_not_the_tip():
    """A fix inherits the deliverable's shape; the root's aspect is the identity."""
    root = image("a", width=1600, height=900)
    fix = image("b", width=1080, height=1350, minutes=5)
    fix.supersedes_id = "a"
    fix.version = 2
    assert satisfies("16:9", group_of(root, fix))


def test_zero_sized_legacy_images_never_match():
    assert not satisfies("16:9", group_of(image("a", width=0, height=0)))


# --- the marks themselves ---------------------------------------------------


def test_a_spec_gap_yields_a_missing_mark_with_its_citation():
    group = group_of(image("a", width=1600, height=900))
    marks = marks_for(group, slot(["16:9", "9:16"]), SlotState.IN_REVIEW, {}, NOW)
    missing = [m for m in marks if m.kind is MarkKind.MISSING]
    assert [m.label for m in missing] == ["9:16"]
    assert "16:9 · 9:16" in missing[0].detail


def test_a_specless_slot_earns_no_missing_marks_ever():
    group = group_of(image("a"))
    assert marks_for(group, None, SlotState.IN_REVIEW, {}, NOW) == []
    assert marks_for(group, slot([]), SlotState.IN_REVIEW, {}, NOW) == []


def test_a_complete_slot_stops_asking_for_missing_deliverables():
    group = group_of(image("a", approved="u-owner"))
    marks = marks_for(group, slot(["9:16"]), SlotState.COMPLETE, {}, NOW)
    assert marks == []


def test_stall_fires_at_three_days_and_not_before():
    group = group_of(image("a"))
    fresh = {"a": DefectSignal(open_count=1, oldest_open=NOW - timedelta(days=2, hours=23))}
    stale = {"a": DefectSignal(open_count=1, oldest_open=NOW - timedelta(days=3))}
    assert marks_for(group, None, SlotState.IN_REVIEW, fresh, NOW) == []
    stalled = marks_for(group, None, SlotState.IN_REVIEW, stale, NOW)
    assert [m.kind for m in stalled] == [MarkKind.STALLED]
    assert "3 days" in stalled[0].detail


def test_an_archived_variants_stall_is_nobodys_problem():
    winner = image("a", variant=1, approved="u-owner")
    loser = image("b", variant=2, minutes=1)
    group = group_of(winner, loser)
    signals = {"b": DefectSignal(open_count=2, oldest_open=NOW - timedelta(days=10))}
    assert marks_for(group, None, SlotState.COMPLETE, signals, NOW) == []


def test_questions_sum_across_live_variants():
    group = group_of(image("a", variant=1), image("b", variant=2, minutes=1))
    signals = {
        "a": DefectSignal(open_count=1, question_count=1, oldest_open=NOW),
        "b": DefectSignal(open_count=2, question_count=2, oldest_open=NOW),
    }
    marks = marks_for(group, None, SlotState.IN_REVIEW, signals, NOW)
    question = next(m for m in marks if m.kind is MarkKind.QUESTION)
    assert question.label == "3"


def test_ready_to_pick_earns_the_pickable_mark():
    group = group_of(image("a"))
    marks = marks_for(group, None, SlotState.READY_TO_PICK, {}, NOW)
    assert [m.kind for m in marks] == [MarkKind.PICKABLE]


def test_mark_keys_are_stable_so_dismissals_stick():
    mark = Mark(kind=MarkKind.MISSING, slot_id="s1", label="9:16", detail="x")
    again = Mark(kind=MarkKind.MISSING, slot_id="s1", label="9:16", detail="different words")
    assert mark.key == again.key == "s1:missing:9:16"
