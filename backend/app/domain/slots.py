"""Slots, variants and version chains — the shape of the work, derived not stored.

The only things persisted about grouping are ``ImageAsset.slot_id`` and
``ImageAsset.variant``. Everything a reviewer reads off a slot card — which
variant won, which are archived, whether the slot is complete — is computed here
from the images themselves (domain-model.md decision 14). That is what makes
approval reversible and makes pre-slot data readable with no migration step.

Pure: no I/O, no repository, no model calls.
"""

from collections.abc import Iterable, Mapping
from enum import StrEnum

from pydantic import BaseModel, Field

from app.domain.entities import ImageAsset, ImageStatus


class SlotState(StrEnum):
    """The slot card's headline — the best any of its variants has managed."""

    IN_REVIEW = "in_review"
    READY_TO_PICK = "ready_to_pick"
    COMPLETE = "complete"


class VariantChain(BaseModel):
    """One competing candidate: its ordinal and its version tree.

    ``versions`` is the tree in depth-first order, root first — parents always
    precede their children, so linear chains read exactly as they used to.
    Branching lives entirely in each asset's ``supersedes_id``.
    """

    slot_id: str
    variant: int
    versions: list[ImageAsset] = Field(default_factory=list)

    @property
    def root(self) -> ImageAsset:
        return self.versions[0]

    @property
    def leaves(self) -> list[ImageAsset]:
        """Versions nothing has fixed yet — the live ends of every branch."""
        superseded = {asset.supersedes_id for asset in self.versions if asset.supersedes_id}
        return [asset for asset in self.versions if asset.id not in superseded]

    @property
    def tip(self) -> ImageAsset:
        """The version that currently represents this variant: the newest leaf."""
        return max(self.leaves, key=lambda asset: (asset.created_at, asset.id))

    @property
    def approved_version(self) -> ImageAsset | None:
        return next((asset for asset in self.versions if asset.is_approved), None)

    @property
    def is_approved(self) -> bool:
        return self.approved_version is not None


class SlotGroup(BaseModel):
    """A slot and the variants competing inside it, ordinal order."""

    slot_id: str
    variants: list[VariantChain] = Field(default_factory=list)
    #: True when this slot exists only as a wrapper around pre-slot data.
    synthetic: bool = False

    @property
    def winner(self) -> VariantChain | None:
        """The approved variant, if the Owner has picked one. At most one exists."""
        return next((chain for chain in self.variants if chain.is_approved), None)

    @property
    def is_complete(self) -> bool:
        return self.winner is not None

    def archived_by(self, variant: int) -> int | None:
        """The ordinal of the sibling that superseded ``variant``, or None.

        Archived is a relationship, not a flag: it holds exactly while some *other*
        variant is approved, so approving a different one reverses it for free.
        """
        winner = self.winner
        if winner is None or winner.variant == variant:
            return None
        return winner.variant

    def chain(self, variant: int) -> VariantChain | None:
        return next((c for c in self.variants if c.variant == variant), None)

    @property
    def next_variant(self) -> int:
        """The ordinal a newly added competing candidate would take."""
        return max((chain.variant for chain in self.variants), default=0) + 1


def build_chains(images: Iterable[ImageAsset]) -> list[VariantChain]:
    """Link images into version trees by ``supersedes_id``, oldest root first.

    The root carries the authoritative ``slot_id``/``variant``: a fix inherits them,
    and during the legacy read-path a root may predate slots entirely. Children of
    the same version are siblings — a branch — and are walked oldest first, so the
    depth-first flattening is deterministic.
    """
    assets = list(images)
    by_id = {asset.id: asset for asset in assets}
    children: dict[str, list[ImageAsset]] = {}
    for asset in sorted(assets, key=lambda a: (a.created_at, a.id)):
        if asset.supersedes_id and asset.supersedes_id in by_id:
            children.setdefault(asset.supersedes_id, []).append(asset)

    chains: list[VariantChain] = []
    for asset in sorted(assets, key=lambda a: (a.created_at, a.id)):
        if asset.supersedes_id and asset.supersedes_id in by_id:
            continue  # not a root; it will be walked from its own root

        versions: list[ImageAsset] = []
        seen: set[str] = set()
        stack = [asset]
        while stack:
            node = stack.pop()
            if node.id in seen:
                continue  # a supersedes cycle in bad data must not hang the read path
            seen.add(node.id)
            versions.append(node)
            # Reversed, so the oldest child comes off the stack first (depth-first).
            stack.extend(reversed(children.get(node.id, [])))
        chains.append(
            VariantChain(
                slot_id=asset.slot_id or asset.id,
                variant=asset.variant,
                versions=versions,
            )
        )
    return chains


def group_into_slots(images: Iterable[ImageAsset]) -> list[SlotGroup]:
    """Every slot in the given images, oldest slot first, variants in ordinal order.

    Pre-slot images fall into a synthetic slot keyed by their own root id, so a
    legacy project reads as one single-variant slot per image with zero writes.
    """
    grouped: dict[str, list[VariantChain]] = {}
    for chain in build_chains(images):
        grouped.setdefault(chain.slot_id, []).append(chain)

    groups = [
        SlotGroup(
            slot_id=slot_id,
            variants=sorted(chains, key=lambda c: (c.variant, c.root.created_at)),
            synthetic=not chains[0].root.slot_id,
        )
        for slot_id, chains in grouped.items()
    ]
    return sorted(groups, key=lambda g: (g.variants[0].root.created_at, g.slot_id))


def slot_state(group: SlotGroup, open_defects: Mapping[str, int]) -> SlotState:
    """Headline state: the best state any live variant has reached.

    ``open_defects`` maps image id to its count of defects still needing someone —
    the caller owns that query; this stays pure.
    """
    if group.is_complete:
        return SlotState.COMPLETE
    ready = any(
        leaf.status is ImageStatus.DONE and not open_defects.get(leaf.id, 0)
        for chain in group.variants
        for leaf in chain.leaves
    )
    return SlotState.READY_TO_PICK if ready else SlotState.IN_REVIEW
