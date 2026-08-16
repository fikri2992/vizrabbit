"""Derived attention marks — the agenda that is never stored (decision 20).

A mark is what a card chip or the project page's quiet line says: "missing
9:16", "ready to pick", "stalled 4 days", "2 questions". All of it is computed
here from the slot's own state, the same way archived is derived from approval
(decision 14): recomputed on every read, so it can never go stale, and the only
stored fact anywhere is a user's dismissal.

Pure: no I/O, no repository, no clock reads — ``now`` comes in as an argument.
"""

from datetime import datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel

from app.domain.entities import Slot
from app.domain.slots import SlotGroup, SlotState

#: How far a variant's aspect may sit from a spec aspect and still satisfy it.
#: 2% relative: 1080×1920 passes "9:16", a 4:5 crop does not.
ASPECT_TOLERANCE = 0.02

#: An open defect older than this with no fix in flight reads as stalled.
STALL_AFTER = timedelta(days=3)


class MarkKind(StrEnum):
    MISSING = "missing"
    PICKABLE = "pickable"
    STALLED = "stalled"
    QUESTION = "question"


class Mark(BaseModel):
    kind: MarkKind
    slot_id: str
    label: str
    #: The "because:" line — a mark must cite its gap (decision 20).
    detail: str

    @property
    def key(self) -> str:
        """Stable identity, what a dismissal stores: same gap ⇒ same key."""
        return f"{self.slot_id}:{self.kind}:{self.label}"


class DefectSignal(BaseModel):
    """Per-image facts the marks need, gathered by the caller (this stays pure)."""

    open_count: int = 0
    question_count: int = 0
    oldest_open: datetime | None = None


def parse_aspect(text: str) -> float | None:
    """"16:9" → 16/9. None for anything that is not W:H with positive numbers."""
    left, colon, right = text.partition(":")
    if not colon:
        return None
    try:
        width, height = float(left), float(right)
    except ValueError:
        return None
    if width <= 0 or height <= 0:
        return None
    return width / height


def satisfies(aspect_text: str, group: SlotGroup) -> bool:
    """Does any variant's root match this spec aspect within tolerance?

    The root, not the tip: the deliverable's shape is set at upload, and a fix
    inherits it — a crop drastic enough to change aspect is a new variant.
    """
    target = parse_aspect(aspect_text)
    if target is None:
        return False
    for chain in group.variants:
        root = chain.root
        if not root.width or not root.height:
            continue
        if abs(root.width / root.height - target) <= target * ASPECT_TOLERANCE:
            return True
    return False


def marks_for(
    group: SlotGroup,
    slot: Slot | None,
    state: SlotState,
    signals: dict[str, DefectSignal],
    at: datetime,
) -> list[Mark]:
    """Every mark this slot earns right now. Order: what blocks first.

    ``signals`` is keyed by image id and only consulted for live variants —
    archived work is nobody's problem, exactly as with open-defect counts.
    """
    marks: list[Mark] = []
    live_tips = [
        chain.tip for chain in group.variants if group.archived_by(chain.variant) is None
    ]

    if slot is not None and not group.is_complete:
        for aspect in slot.spec:
            if not satisfies(aspect, group):
                due = f" — due {slot.due_at:%d %b}" if slot.due_at else ""
                marks.append(
                    Mark(
                        kind=MarkKind.MISSING,
                        slot_id=group.slot_id,
                        label=aspect,
                        detail=f"spec wants {' · '.join(slot.spec)}{due}",
                    )
                )

    stalled = [
        (tip, signal.oldest_open)
        for tip in live_tips
        if (signal := signals.get(tip.id)) and signal.open_count and signal.oldest_open
    ]
    if stalled and not group.is_complete:
        oldest = min(age for _, age in stalled)
        waited = at - oldest
        if waited >= STALL_AFTER:
            days = waited.days
            marks.append(
                Mark(
                    kind=MarkKind.STALLED,
                    slot_id=group.slot_id,
                    label=f"{days}d",
                    detail=f"oldest open defect has waited {days} days with no fix",
                )
            )

    questions = sum(signals.get(tip.id, DefectSignal()).question_count for tip in live_tips)
    if questions:
        marks.append(
            Mark(
                kind=MarkKind.QUESTION,
                slot_id=group.slot_id,
                label=str(questions),
                detail=f"{questions} check(s) the agent wants your eyes on",
            )
        )

    if state is SlotState.READY_TO_PICK:
        marks.append(
            Mark(
                kind=MarkKind.PICKABLE,
                slot_id=group.slot_id,
                label="pick",
                detail="a clean finished version is waiting on your approval",
            )
        )

    return marks
