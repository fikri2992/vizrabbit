"""Defect lifecycle state machine.

    open -> fix_submitted -> agent_rechecking -> verified_resolved

Invariants (domain-model.md decision 12):
  * Only the AGENT may reach ``verified_resolved``. Humans cannot mark a defect resolved.
  * Only the OWNER may ``dismiss`` (false positive) or ``override_approve`` (rationale logged).
  * Viewers may never transition anything (they read and comment only).

Pure logic, zero I/O — see AGENTS.md.
"""

from enum import StrEnum


class DefectState(StrEnum):
    OPEN = "open"
    NEEDS_HUMAN_REVIEW = "needs_human_review"  # annotation loop maxed out
    FIX_SUBMITTED = "fix_submitted"
    AGENT_RECHECKING = "agent_rechecking"
    VERIFIED_RESOLVED = "verified_resolved"
    DISMISSED = "dismissed"
    OVERRIDE_APPROVED = "override_approved"


class Actor(StrEnum):
    OWNER = "owner"
    REVIEWER = "reviewer"
    VIEWER = "viewer"
    AGENT = "agent"


#: States the pipeline can produce, and from which human action is expected.
ACTIONABLE_STATES: frozenset[DefectState] = frozenset(
    {DefectState.OPEN, DefectState.NEEDS_HUMAN_REVIEW}
)

#: No transitions leave these.
TERMINAL_STATES: frozenset[DefectState] = frozenset(
    {DefectState.VERIFIED_RESOLVED, DefectState.DISMISSED, DefectState.OVERRIDE_APPROVED}
)

#: (from_state, to_state) -> actors permitted to make that move.
TRANSITIONS: dict[tuple[DefectState, DefectState], frozenset[Actor]] = {
    # A fix is submitted by uploading a new image version.
    (DefectState.OPEN, DefectState.FIX_SUBMITTED): frozenset({Actor.OWNER, Actor.REVIEWER}),
    (DefectState.NEEDS_HUMAN_REVIEW, DefectState.FIX_SUBMITTED): frozenset(
        {Actor.OWNER, Actor.REVIEWER}
    ),
    # The agent picks the fix up and re-checks it.
    (DefectState.FIX_SUBMITTED, DefectState.AGENT_RECHECKING): frozenset({Actor.AGENT}),
    # Re-check outcome: closed, or bounced back as still-present.
    (DefectState.AGENT_RECHECKING, DefectState.VERIFIED_RESOLVED): frozenset({Actor.AGENT}),
    (DefectState.AGENT_RECHECKING, DefectState.OPEN): frozenset({Actor.AGENT}),
    # Owner-only escape hatches.
    (DefectState.OPEN, DefectState.DISMISSED): frozenset({Actor.OWNER}),
    (DefectState.NEEDS_HUMAN_REVIEW, DefectState.DISMISSED): frozenset({Actor.OWNER}),
    (DefectState.OPEN, DefectState.OVERRIDE_APPROVED): frozenset({Actor.OWNER}),
    (DefectState.NEEDS_HUMAN_REVIEW, DefectState.OVERRIDE_APPROVED): frozenset({Actor.OWNER}),
}

#: Transitions that must carry a written rationale.
REQUIRES_RATIONALE: frozenset[tuple[DefectState, DefectState]] = frozenset(
    {
        (DefectState.OPEN, DefectState.OVERRIDE_APPROVED),
        (DefectState.NEEDS_HUMAN_REVIEW, DefectState.OVERRIDE_APPROVED),
    }
)


class TransitionError(Exception):
    """Raised when a lifecycle move is not permitted."""


def can_transition(state: DefectState, to: DefectState, actor: Actor) -> bool:
    return actor in TRANSITIONS.get((state, to), frozenset())


def assert_transition(
    state: DefectState, to: DefectState, actor: Actor, rationale: str | None = None
) -> None:
    """Raise ``TransitionError`` unless this move is legal and complete."""
    allowed = TRANSITIONS.get((state, to))
    if allowed is None:
        raise TransitionError(f"no path from {state} to {to}")
    if actor not in allowed:
        raise TransitionError(f"{actor} may not move {state} -> {to}")
    if (state, to) in REQUIRES_RATIONALE and not (rationale or "").strip():
        raise TransitionError(f"{state} -> {to} requires a rationale")


def allowed_transitions(state: DefectState, actor: Actor) -> frozenset[DefectState]:
    """Every state ``actor`` can move ``state`` to — drives the UI's action buttons."""
    return frozenset(
        to for (frm, to), actors in TRANSITIONS.items() if frm == state and actor in actors
    )
