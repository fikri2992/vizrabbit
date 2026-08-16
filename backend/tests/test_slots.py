"""Pure slot/variant logic: grouping, derived archiving, headline state.

Real inputs, asserted outputs, zero mocks — ``domain/slots.py`` touches nothing
but the entities handed to it.
"""

from datetime import UTC, datetime, timedelta

from app.domain.entities import ImageAsset, ImageStatus
from app.domain.slots import (
    SlotState,
    build_chains,
    group_into_slots,
    slot_state,
)

BASE = datetime(2026, 8, 16, 9, 0, tzinfo=UTC)


def image(
    image_id: str,
    *,
    slot_id: str = "",
    variant: int = 1,
    version: int = 1,
    supersedes: str | None = None,
    minutes: int = 0,
    approved: str | None = None,
    status: ImageStatus = ImageStatus.DONE,
) -> ImageAsset:
    return ImageAsset(
        id=image_id,
        project_id="p1",
        run_id="r1",
        filename=f"{image_id}.png",
        slot_id=slot_id,
        variant=variant,
        version=version,
        supersedes_id=supersedes,
        status=status,
        approved_by=approved,
        created_at=BASE + timedelta(minutes=minutes),
    )


# --- chains ---------------------------------------------------------------


def test_a_fix_extends_its_variants_chain_rather_than_starting_one():
    chains = build_chains(
        [
            image("a", slot_id="s1", minutes=0),
            image("b", slot_id="s1", version=2, supersedes="a", minutes=5),
            image("c", slot_id="s1", version=3, supersedes="b", minutes=9),
        ]
    )
    assert len(chains) == 1
    assert [asset.id for asset in chains[0].versions] == ["a", "b", "c"]
    assert chains[0].tip.id == "c"
    assert chains[0].root.id == "a"


def test_the_root_carries_the_grouping_even_when_a_fix_disagrees():
    """The root is authoritative: a mislabelled fix cannot re-home a chain."""
    chains = build_chains(
        [
            image("a", slot_id="s1", variant=2, minutes=0),
            image("b", slot_id="s9", variant=7, version=2, supersedes="a", minutes=3),
        ]
    )
    assert chains[0].slot_id == "s1"
    assert chains[0].variant == 2


def test_a_dangling_supersedes_id_still_yields_a_chain():
    """A fix whose parent was deleted is a root, not a lost image."""
    chains = build_chains([image("b", slot_id="s1", version=2, supersedes="gone")])
    assert [c.tip.id for c in chains] == ["b"]


def test_a_cyclic_supersedes_pair_terminates():
    a = image("a", slot_id="s1", supersedes="b", minutes=0)
    b = image("b", slot_id="s1", supersedes="a", minutes=1)
    chains = build_chains([a, b])
    assert sum(len(chain.versions) for chain in chains) <= 2


# --- grouping -------------------------------------------------------------


def test_three_variants_of_one_slot_group_into_one_slot_in_ordinal_order():
    groups = group_into_slots(
        [
            image("c", slot_id="s1", variant=3, minutes=2),
            image("a", slot_id="s1", variant=1, minutes=0),
            image("b", slot_id="s1", variant=2, minutes=1),
        ]
    )
    assert len(groups) == 1
    assert [chain.variant for chain in groups[0].variants] == [1, 2, 3]
    assert groups[0].synthetic is False


def test_separate_slots_stay_separate():
    groups = group_into_slots(
        [image("a", slot_id="s1", minutes=0), image("b", slot_id="s2", minutes=1)]
    )
    assert [group.slot_id for group in groups] == ["s1", "s2"]


def test_legacy_images_each_wrap_in_their_own_synthetic_slot():
    """Gate 6: a pre-slot project reads with every image visible, zero writes."""
    groups = group_into_slots(
        [image("a", minutes=0), image("b", minutes=1), image("c", minutes=2)]
    )
    assert [group.slot_id for group in groups] == ["a", "b", "c"]
    assert all(group.synthetic for group in groups)
    assert all(len(group.variants) == 1 for group in groups)


def test_a_legacy_version_chain_wraps_as_one_slot_not_one_per_version():
    groups = group_into_slots(
        [image("a", minutes=0), image("b", version=2, supersedes="a", minutes=4)]
    )
    assert len(groups) == 1
    assert groups[0].slot_id == "a"
    assert [asset.id for asset in groups[0].variants[0].versions] == ["a", "b"]


def test_next_variant_follows_the_highest_ordinal():
    group = group_into_slots(
        [image("a", slot_id="s1", variant=1), image("b", slot_id="s1", variant=4)]
    )[0]
    assert group.next_variant == 5


# --- derived archiving ----------------------------------------------------


def test_no_approval_means_nothing_is_archived():
    group = group_into_slots(
        [image("a", slot_id="s1", variant=1), image("b", slot_id="s1", variant=2)]
    )[0]
    assert group.is_complete is False
    assert group.archived_by(1) is None
    assert group.archived_by(2) is None


def test_approving_one_variant_completes_the_slot_and_archives_its_siblings():
    group = group_into_slots(
        [
            image("a", slot_id="s1", variant=1),
            image("b", slot_id="s1", variant=2, approved="u-owner"),
            image("c", slot_id="s1", variant=3),
        ]
    )[0]
    assert group.is_complete
    assert group.winner.variant == 2
    assert group.archived_by(2) is None  # the winner is not archived by itself
    assert group.archived_by(1) == 2
    assert group.archived_by(3) == 2


def test_approval_on_an_earlier_version_still_wins_the_variant():
    group = group_into_slots(
        [
            image("a", slot_id="s1", variant=1, approved="u-owner", minutes=0),
            image("b", slot_id="s1", variant=1, version=2, supersedes="a", minutes=3),
            image("c", slot_id="s1", variant=2, minutes=1),
        ]
    )[0]
    assert group.winner.variant == 1
    assert group.archived_by(2) == 1


# --- headline state -------------------------------------------------------


def test_a_completed_slot_reads_complete_whatever_its_siblings_show():
    group = group_into_slots(
        [
            image("a", slot_id="s1", variant=1),
            image("b", slot_id="s1", variant=2, approved="u-owner"),
        ]
    )[0]
    assert slot_state(group, {"a": 4, "b": 0}) is SlotState.COMPLETE


def test_a_clean_finished_variant_makes_the_slot_ready_to_pick():
    group = group_into_slots(
        [image("a", slot_id="s1", variant=1), image("b", slot_id="s1", variant=2)]
    )[0]
    assert slot_state(group, {"a": 3, "b": 0}) is SlotState.READY_TO_PICK


def test_open_defects_everywhere_leave_the_slot_in_review():
    group = group_into_slots(
        [image("a", slot_id="s1", variant=1), image("b", slot_id="s1", variant=2)]
    )[0]
    assert slot_state(group, {"a": 3, "b": 1}) is SlotState.IN_REVIEW


def test_an_unfinished_variant_is_not_ready_to_pick_even_with_no_defects():
    group = group_into_slots([image("a", slot_id="s1", status=ImageStatus.SCANNING)])[0]
    assert slot_state(group, {}) is SlotState.IN_REVIEW


def test_state_reads_the_tip_not_a_superseded_version():
    """A cleaned-up v2 decides the slot, not the v1 that was full of defects."""
    group = group_into_slots(
        [
            image("a", slot_id="s1", minutes=0),
            image("b", slot_id="s1", version=2, supersedes="a", minutes=5),
        ]
    )[0]
    assert slot_state(group, {"a": 9, "b": 0}) is SlotState.READY_TO_PICK


# --- branching ------------------------------------------------------------


def test_two_fixes_of_the_same_version_are_sibling_branches_of_one_chain():
    chains = build_chains(
        [
            image("a", slot_id="s1", minutes=0),
            image("b", slot_id="s1", version=2, supersedes="a", minutes=5),
            image("c", slot_id="s1", version=2, supersedes="a", minutes=9),
        ]
    )
    assert len(chains) == 1
    # Depth-first, siblings oldest first: parents always precede children.
    assert [asset.id for asset in chains[0].versions] == ["a", "b", "c"]
    assert {leaf.id for leaf in chains[0].leaves} == {"b", "c"}
    assert chains[0].tip.id == "c"  # the newest leaf speaks for the variant


def test_depth_first_order_keeps_a_branchs_descendants_together():
    chains = build_chains(
        [
            image("a", slot_id="s1", minutes=0),
            image("b", slot_id="s1", version=2, supersedes="a", minutes=5),
            image("c", slot_id="s1", version=2, supersedes="a", minutes=9),
            image("b2", slot_id="s1", version=3, supersedes="b", minutes=12),
        ]
    )
    assert [asset.id for asset in chains[0].versions] == ["a", "b", "b2", "c"]


def test_any_clean_leaf_makes_a_branched_slot_ready_to_pick():
    group = group_into_slots(
        [
            image("a", slot_id="s1", minutes=0),
            image("b", slot_id="s1", version=2, supersedes="a", minutes=5),
            image("c", slot_id="s1", version=2, supersedes="a", minutes=9),
        ]
    )[0]
    # The newer branch is still dirty, but its clean sibling is pickable.
    assert slot_state(group, {"a": 4, "b": 0, "c": 2}) is SlotState.READY_TO_PICK
    assert slot_state(group, {"a": 4, "b": 3, "c": 2}) is SlotState.IN_REVIEW
