"""Full role x permission matrix, plus the accountability invariants.

Written as an independent restatement of the intended policy, not derived from
ROLE_PERMISSIONS — so changing the policy has to be deliberate in two places.
"""

import itertools

import pytest

from app.domain.entities import Member, Project, Role
from app.domain.lifecycle import DefectState as S
from app.domain.permissions import (
    Permission,
    PermissionError_,
    can,
    can_move_defect,
    has,
    only_owner_may,
    permissions_for,
    require,
    require_defect_move,
    validate_membership,
)

P = Permission

#: Independently specified: what a Reviewer may do. Viewers get the first two.
REVIEWER_ALLOWED = {
    P.VIEW_PROJECT,
    P.COMMENT,
    P.UPLOAD_IMAGES,
    P.SUBMIT_FIX,
    P.PROPOSE_MEMORY_RULE,
}
VIEWER_ALLOWED = {P.VIEW_PROJECT, P.COMMENT}


@pytest.fixture
def project():
    return Project(
        id="p1",
        name="Autumn campaign",
        members=[
            Member(user_id="owner", email="owner@acme.com", role=Role.OWNER),
            Member(user_id="designer", email="designer@acme.com", role=Role.REVIEWER),
            Member(user_id="sales", email="sales@acme.com", role=Role.VIEWER),
        ],
    )


# --- the matrix -----------------------------------------------------------


@pytest.mark.parametrize(("role", "permission"), list(itertools.product(Role, Permission)))
def test_full_role_permission_matrix(role, permission):
    expected = {
        Role.OWNER: True,
        Role.REVIEWER: permission in REVIEWER_ALLOWED,
        Role.VIEWER: permission in VIEWER_ALLOWED,
    }[role]
    assert has(role, permission) is expected, f"{role} / {permission}"


def test_owner_holds_every_permission():
    assert permissions_for(Role.OWNER) == frozenset(Permission)


def test_a_non_member_has_nothing():
    assert permissions_for(None) == frozenset()
    for permission in Permission:
        assert has(None, permission) is False


def test_viewer_permissions_are_a_subset_of_reviewer():
    assert permissions_for(Role.VIEWER) < permissions_for(Role.REVIEWER)


def test_reviewer_permissions_are_a_subset_of_owner():
    assert permissions_for(Role.REVIEWER) < permissions_for(Role.OWNER)


# --- accountability -------------------------------------------------------


@pytest.mark.parametrize(
    "permission",
    [
        P.ANSWER_GRILLING,
        P.APPROVE_MEMORY_RULE,
        P.DISMISS_DEFECT,
        P.OVERRIDE_APPROVE_DEFECT,
        P.APPROVE_IMAGE,
        P.OVERRIDE_SEVERITY,
        P.MANAGE_MEMBERS,
        P.EDIT_GUIDELINE,
    ],
)
def test_accountability_decisions_are_owner_only(permission):
    """The whole point of one Brand Owner — these must never spread to other roles."""
    assert only_owner_may(permission)
    assert has(Role.REVIEWER, permission) is False
    assert has(Role.VIEWER, permission) is False


def test_anyone_may_propose_a_memory_rule_but_only_the_owner_approves():
    assert has(Role.REVIEWER, P.PROPOSE_MEMORY_RULE)
    assert not has(Role.REVIEWER, P.APPROVE_MEMORY_RULE)


def test_viewers_cannot_upload():
    """Sales consumes collateral; it does not put work into the pipeline."""
    assert not has(Role.VIEWER, P.UPLOAD_IMAGES)


# --- project-scoped checks ------------------------------------------------


def test_can_resolves_the_members_role(project):
    assert can(project, "owner", P.APPROVE_IMAGE) is True
    assert can(project, "designer", P.APPROVE_IMAGE) is False
    assert can(project, "sales", P.UPLOAD_IMAGES) is False
    assert can(project, "designer", P.UPLOAD_IMAGES) is True


def test_a_stranger_can_do_nothing(project):
    for permission in Permission:
        assert can(project, "stranger", permission) is False


def test_require_raises_with_a_useful_message(project):
    with pytest.raises(PermissionError_, match="role reviewer may not approve_image"):
        require(project, "designer", P.APPROVE_IMAGE)

    with pytest.raises(PermissionError_, match="non-member"):
        require(project, "stranger", P.COMMENT)


def test_require_passes_silently_when_allowed(project):
    require(project, "owner", P.APPROVE_IMAGE)
    require(project, "designer", P.SUBMIT_FIX)
    require(project, "sales", P.COMMENT)


# --- lifecycle through roles ----------------------------------------------


def test_reviewer_may_submit_a_fix_but_not_resolve(project):
    assert can_move_defect(project, "designer", S.OPEN, S.FIX_SUBMITTED) is True
    assert can_move_defect(project, "designer", S.AGENT_RECHECKING, S.VERIFIED_RESOLVED) is False


def test_owner_cannot_resolve_by_hand_either(project):
    """Resolution is the agent's act. Owners override instead, on the record."""
    assert can_move_defect(project, "owner", S.AGENT_RECHECKING, S.VERIFIED_RESOLVED) is False
    assert can_move_defect(project, "owner", S.OPEN, S.OVERRIDE_APPROVED) is True


def test_only_the_owner_dismisses(project):
    assert can_move_defect(project, "owner", S.OPEN, S.DISMISSED) is True
    assert can_move_defect(project, "designer", S.OPEN, S.DISMISSED) is False
    assert can_move_defect(project, "sales", S.OPEN, S.DISMISSED) is False


def test_viewers_move_nothing(project):
    for frm, to in itertools.product(S, S):
        assert can_move_defect(project, "sales", frm, to) is False


def test_non_members_move_nothing(project):
    for frm, to in itertools.product(S, S):
        assert can_move_defect(project, "stranger", frm, to) is False


def test_override_requires_a_rationale_through_the_permission_layer(project):
    with pytest.raises(PermissionError_, match="rationale"):
        require_defect_move(project, "owner", S.OPEN, S.OVERRIDE_APPROVED)

    require_defect_move(project, "owner", S.OPEN, S.OVERRIDE_APPROVED, rationale="client approved")


def test_require_defect_move_rejects_a_reviewer_dismissal(project):
    with pytest.raises(PermissionError_, match="may not move"):
        require_defect_move(project, "designer", S.OPEN, S.DISMISSED)


def test_require_defect_move_rejects_non_members(project):
    with pytest.raises(PermissionError_, match="not a member"):
        require_defect_move(project, "stranger", S.OPEN, S.FIX_SUBMITTED)


# --- membership invariants ------------------------------------------------


def test_a_valid_project_passes(project):
    validate_membership(project)


def test_a_project_needs_an_owner():
    project = Project(
        id="p", name="x", members=[Member(user_id="a", email="a@b.c", role=Role.REVIEWER)]
    )
    with pytest.raises(ValueError, match="exactly one owner"):
        validate_membership(project)


def test_a_project_cannot_have_two_owners():
    """Two accountable people is the same as none."""
    project = Project(
        id="p",
        name="x",
        members=[
            Member(user_id="a", email="a@b.c", role=Role.OWNER),
            Member(user_id="b", email="b@b.c", role=Role.OWNER),
        ],
    )
    with pytest.raises(ValueError, match="exactly one owner"):
        validate_membership(project)


def test_duplicate_members_are_rejected():
    project = Project(
        id="p",
        name="x",
        members=[
            Member(user_id="a", email="a@b.c", role=Role.OWNER),
            Member(user_id="a", email="a@b.c", role=Role.REVIEWER),
        ],
    )
    with pytest.raises(ValueError, match="duplicate"):
        validate_membership(project)


def test_project_exposes_its_owner(project):
    assert project.owner.user_id == "owner"
    assert project.role_of("designer") is Role.REVIEWER
    assert project.role_of("nobody") is None
