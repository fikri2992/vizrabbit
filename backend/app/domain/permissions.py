"""What each role may do.

The Brand Owner is the single accountable member: they answer guideline grilling,
gate memory rules, own false positives, and give "approved" its meaning. Reviewers
do the work; Viewers observe. Nobody but the agent resolves a defect.

Pure logic — the API layer asks these questions, it does not re-implement them.
"""

from enum import StrEnum

from app.domain.entities import Project, Role
from app.domain.lifecycle import DefectState, TransitionError, assert_transition, can_transition


class Permission(StrEnum):
    VIEW_PROJECT = "view_project"
    COMMENT = "comment"
    UPLOAD_IMAGES = "upload_images"
    SUBMIT_FIX = "submit_fix"
    PROPOSE_MEMORY_RULE = "propose_memory_rule"
    #: Point the Inspector at a drawn region. Spends model budget, so not a viewer action.
    ASK_AGENT = "ask_agent"

    # Owner-only, all of them accountability decisions.
    ANSWER_GRILLING = "answer_grilling"
    APPROVE_MEMORY_RULE = "approve_memory_rule"
    DISMISS_DEFECT = "dismiss_defect"
    OVERRIDE_APPROVE_DEFECT = "override_approve_defect"
    APPROVE_IMAGE = "approve_image"
    OVERRIDE_SEVERITY = "override_severity"
    MANAGE_MEMBERS = "manage_members"
    EDIT_GUIDELINE = "edit_guideline"
    #: Removes the whole version lineage and its records — an accountability decision.
    DELETE_IMAGE = "delete_image"
    #: Turns an extracted palette into one the pipeline enforces. Owner-only because
    #: confirming it is what makes brand defects the Owner's to answer for.
    CONFIRM_BRAND_PROFILE = "confirm_brand_profile"
    #: Animate an approved still into a motion variant (decision 24). Owner-only:
    #: it spends real model budget and manufactures a deliverable from the
    #: approved asset.
    ANIMATE_APPROVED = "animate_approved"
    RENAME_PROJECT = "rename_project"
    #: Destroys the project and everything in it. The most consequential action here.
    DELETE_PROJECT = "delete_project"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.VIEWER: frozenset({Permission.VIEW_PROJECT, Permission.COMMENT}),
    Role.REVIEWER: frozenset(
        {
            Permission.VIEW_PROJECT,
            Permission.COMMENT,
            Permission.UPLOAD_IMAGES,
            Permission.SUBMIT_FIX,
            Permission.PROPOSE_MEMORY_RULE,
            Permission.ASK_AGENT,
        }
    ),
    Role.OWNER: frozenset(Permission),  # every permission, by definition
}


class PermissionError_(PermissionError):
    """Raised when a member attempts something their role does not allow."""


def has(role: Role | None, permission: Permission) -> bool:
    if role is None:
        return False
    return permission in ROLE_PERMISSIONS[role]


def can(project: Project, user_id: str, permission: Permission) -> bool:
    return has(project.role_of(user_id), permission)


def require(project: Project, user_id: str, permission: Permission) -> None:
    if not can(project, user_id, permission):
        role = project.role_of(user_id)
        who = f"role {role}" if role else "non-member"
        raise PermissionError_(f"{who} may not {permission.value}")


def permissions_for(role: Role | None) -> frozenset[Permission]:
    """Drives which controls the UI renders."""
    return ROLE_PERMISSIONS[role] if role else frozenset()


# --- defect lifecycle, expressed in project roles -------------------------


def can_move_defect(project: Project, user_id: str, state: DefectState, to: DefectState) -> bool:
    role = project.role_of(user_id)
    if role is None:
        return False
    return can_transition(state, to, role.as_actor())


def require_defect_move(
    project: Project,
    user_id: str,
    state: DefectState,
    to: DefectState,
    rationale: str | None = None,
) -> None:
    """Raise unless this member may make this exact lifecycle move."""
    role = project.role_of(user_id)
    if role is None:
        raise PermissionError_("not a member of this project")
    try:
        assert_transition(state, to, role.as_actor(), rationale=rationale)
    except TransitionError as exc:
        raise PermissionError_(str(exc)) from exc


def only_owner_may(permission: Permission) -> bool:
    """True when a permission is part of the Owner's accountability."""
    return not (has(Role.REVIEWER, permission) or has(Role.VIEWER, permission))


# --- membership invariants ------------------------------------------------


def validate_membership(project: Project) -> None:
    """Exactly one Owner, no duplicate members."""
    owners = [m for m in project.members if m.role is Role.OWNER]
    if len(owners) != 1:
        raise ValueError(f"a project needs exactly one owner, found {len(owners)}")

    ids = [m.user_id for m in project.members]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate member")
