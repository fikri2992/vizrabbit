"""Exhaustive lifecycle matrix — every state x state x actor combination.

The allow-list below is written out independently of ``lifecycle.TRANSITIONS`` on purpose:
if it were derived from the implementation the test would be tautological. Changing the
state machine must mean changing both, deliberately.
"""

import itertools

import pytest

from app.domain.lifecycle import (
    TERMINAL_STATES,
    Actor,
    DefectState,
    TransitionError,
    allowed_transitions,
    assert_transition,
    can_transition,
)

S = DefectState
A = Actor

#: Independently specified: (from, to, actor) triples that MUST be permitted.
PERMITTED: set[tuple[S, S, A]] = {
    (S.OPEN, S.FIX_SUBMITTED, A.OWNER),
    (S.OPEN, S.FIX_SUBMITTED, A.REVIEWER),
    (S.NEEDS_HUMAN_REVIEW, S.FIX_SUBMITTED, A.OWNER),
    (S.NEEDS_HUMAN_REVIEW, S.FIX_SUBMITTED, A.REVIEWER),
    (S.FIX_SUBMITTED, S.AGENT_RECHECKING, A.AGENT),
    (S.AGENT_RECHECKING, S.VERIFIED_RESOLVED, A.AGENT),
    (S.AGENT_RECHECKING, S.OPEN, A.AGENT),
    (S.OPEN, S.DISMISSED, A.OWNER),
    (S.NEEDS_HUMAN_REVIEW, S.DISMISSED, A.OWNER),
    (S.OPEN, S.OVERRIDE_APPROVED, A.OWNER),
    (S.NEEDS_HUMAN_REVIEW, S.OVERRIDE_APPROVED, A.OWNER),
}

ALL_COMBOS = list(itertools.product(S, S, A))


def test_matrix_is_exhaustive():
    assert len(ALL_COMBOS) == len(S) * len(S) * len(A) == 7 * 7 * 4


@pytest.mark.parametrize(("frm", "to", "actor"), ALL_COMBOS)
def test_full_role_transition_matrix(frm: S, to: S, actor: A):
    expected = (frm, to, actor) in PERMITTED
    assert can_transition(frm, to, actor) is expected, f"{actor}: {frm} -> {to}"


# --- Invariants that must hold no matter how the table is edited ----------


def test_only_agent_can_verify_resolution():
    """The core agentic invariant: humans never mark a defect resolved."""
    for frm, actor in itertools.product(S, A):
        if can_transition(frm, S.VERIFIED_RESOLVED, actor):
            assert actor is A.AGENT


def test_only_owner_dismisses_or_overrides():
    for frm, actor in itertools.product(S, A):
        for to in (S.DISMISSED, S.OVERRIDE_APPROVED):
            if can_transition(frm, to, actor):
                assert actor is A.OWNER


def test_viewer_can_never_transition_anything():
    assert not any(can_transition(f, t, A.VIEWER) for f, t in itertools.product(S, S))


def test_terminal_states_have_no_exits():
    for terminal in TERMINAL_STATES:
        assert allowed_transitions(terminal, A.OWNER) == frozenset()
        assert allowed_transitions(terminal, A.AGENT) == frozenset()


def test_no_self_transitions():
    assert not any(can_transition(s, s, a) for s, a in itertools.product(S, A))


# --- Rationale enforcement ------------------------------------------------


def test_override_approve_requires_rationale():
    with pytest.raises(TransitionError, match="rationale"):
        assert_transition(S.OPEN, S.OVERRIDE_APPROVED, A.OWNER)
    with pytest.raises(TransitionError, match="rationale"):
        assert_transition(S.OPEN, S.OVERRIDE_APPROVED, A.OWNER, rationale="   ")
    assert_transition(S.OPEN, S.OVERRIDE_APPROVED, A.OWNER, rationale="client signed off")


def test_dismiss_does_not_require_rationale():
    assert_transition(S.OPEN, S.DISMISSED, A.OWNER)


def test_assert_transition_reports_why():
    with pytest.raises(TransitionError, match="no path"):
        assert_transition(S.OPEN, S.AGENT_RECHECKING, A.AGENT)
    with pytest.raises(TransitionError, match="may not move"):
        assert_transition(S.OPEN, S.DISMISSED, A.REVIEWER)


# --- Reachability ---------------------------------------------------------


def test_happy_path_is_walkable():
    """open -> fix_submitted -> agent_rechecking -> verified_resolved"""
    assert_transition(S.OPEN, S.FIX_SUBMITTED, A.REVIEWER)
    assert_transition(S.FIX_SUBMITTED, S.AGENT_RECHECKING, A.AGENT)
    assert_transition(S.AGENT_RECHECKING, S.VERIFIED_RESOLVED, A.AGENT)


def test_failed_recheck_returns_to_open():
    assert_transition(S.AGENT_RECHECKING, S.OPEN, A.AGENT)


def test_allowed_transitions_drives_ui():
    assert allowed_transitions(S.OPEN, A.REVIEWER) == frozenset({S.FIX_SUBMITTED})
    assert allowed_transitions(S.OPEN, A.OWNER) == frozenset(
        {S.FIX_SUBMITTED, S.DISMISSED, S.OVERRIDE_APPROVED}
    )
    assert allowed_transitions(S.OPEN, A.VIEWER) == frozenset()
