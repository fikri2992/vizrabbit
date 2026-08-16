"""Persistent entities, in the ubiquitous language of docs/domain-model.md.

Pydantic rather than dataclasses because these cross the wire to the frontend and
into Firestore documents, and both boundaries want validation and serialisation.
"""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.domain.annotations import Shape
from app.domain.lifecycle import Actor, DefectState
from app.domain.taxonomy import Category, Severity


def now() -> datetime:
    return datetime.now(UTC)


class Role(StrEnum):
    """Who a member is on a project. Exactly one OWNER per project."""

    OWNER = "owner"
    REVIEWER = "reviewer"
    VIEWER = "viewer"

    def as_actor(self) -> Actor:
        return Actor(self.value)


class User(BaseModel):
    id: str
    email: str
    name: str = ""
    picture: str = ""


class Member(BaseModel):
    user_id: str
    email: str
    name: str = ""
    role: Role = Role.REVIEWER


class Clarification(BaseModel):
    """A grilling answer appended to a guideline at upload time."""

    question: str
    answer: str
    answered_by: str = ""
    answered_at: datetime = Field(default_factory=now)


class Guideline(BaseModel):
    id: str
    project_id: str
    name: str
    raw_text: str
    clarifications: list[Clarification] = Field(default_factory=list)
    active: bool = True
    updated_at: datetime = Field(default_factory=now)

    def as_prompt(self) -> str:
        """Raw doc plus its clarifications — never compiled, never lossy."""
        if not self.clarifications:
            return self.raw_text
        answered = "\n".join(f"- Q: {c.question}\n  A: {c.answer}" for c in self.clarifications)
        return f"{self.raw_text}\n\n## Clarifications from the brand owner\n\n{answered}"


class MemoryRule(BaseModel):
    """A defect promoted to a standing check (domain-model.md decision 9)."""

    id: str
    project_id: str
    description: str
    category: Category = Category.MEMORY
    source_defect_id: str = ""
    proposed_by: str = ""
    approved_by: str = ""
    active: bool = False  # inactive until the Owner approves
    created_at: datetime = Field(default_factory=now)


class PaletteEntry(BaseModel):
    """One approved brand colour and how far a rendering may drift from it.

    Tolerance is per entry rather than global because brands do not police every
    colour equally: a logo red is exact, a background wash is not.
    """

    hex: str
    role: str = ""
    #: Maximum ΔE2000 from this hex before the colour counts as off-palette.
    tolerance: float = 3.0


class BrandProfile(BaseModel):
    """A project's confirmed palette. Never fires until the Owner confirms it.

    Extraction proposes; the Owner disposes. ``entries`` is what the pipeline
    measures against and is only ever written by a confirmation, while
    ``proposed`` holds whatever the griller read out of a guideline and is inert
    (domain-model.md decision 16).
    """

    id: str
    project_id: str
    entries: list[PaletteEntry] = Field(default_factory=list)
    proposed: list[PaletteEntry] = Field(default_factory=list)
    #: Where the proposal came from, for the confirmation form's provenance line.
    source: str = ""
    confirmed_by: str = ""
    confirmed_at: datetime | None = None
    updated_at: datetime = Field(default_factory=now)

    @property
    def is_active(self) -> bool:
        """Unconfirmed or empty means the brand checker stays silent."""
        return bool(self.confirmed_by and self.entries)

    @property
    def palette(self) -> list[str]:
        return [entry.hex for entry in self.entries]

    def entry_for(self, hex_value: str) -> PaletteEntry | None:
        return next((entry for entry in self.entries if entry.hex == hex_value), None)


class Project(BaseModel):
    id: str
    name: str
    members: list[Member] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=now)

    def member(self, user_id: str) -> Member | None:
        return next((m for m in self.members if m.user_id == user_id), None)

    def role_of(self, user_id: str) -> Role | None:
        member = self.member(user_id)
        return member.role if member else None

    @property
    def owner(self) -> Member | None:
        return next((m for m in self.members if m.role is Role.OWNER), None)


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class Run(BaseModel):
    id: str
    project_id: str
    started_by: str
    status: RunStatus = RunStatus.QUEUED
    image_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=now)
    finished_at: datetime | None = None


class Slot(BaseModel):
    """One creative intent — the unit of work. Variants compete inside it.

    Deliberately thin: which variants belong to it, which one won, and whether it
    is complete are all derived from the images that point here (decision 14), so
    there is no slot state that can drift out of step with them.
    """

    id: str
    project_id: str
    name: str = ""
    created_at: datetime = Field(default_factory=now)


class ImageStatus(StrEnum):
    QUEUED = "queued"
    SCANNING = "scanning"
    REVIEWING = "reviewing"
    DONE = "done"
    FAILED = "failed"


class ImageAsset(BaseModel):
    id: str
    project_id: str
    run_id: str
    filename: str
    #: Empty on pre-slot data; ``domain.slots`` wraps those in a synthetic slot on read.
    slot_id: str = ""
    #: Which competing candidate of the slot this is, numbered from 1.
    variant: int = 1
    version: int = 1
    #: Who put this version here. Empty on data that predates per-version attribution.
    uploaded_by: str = ""
    #: Set when this image is a re-upload fixing an earlier version.
    supersedes_id: str | None = None
    width: int = 0
    height: int = 0
    original_path: str = ""
    gridded_path: str = ""
    annotated_path: str = ""
    status: ImageStatus = ImageStatus.QUEUED
    approved_by: str | None = None
    approved_at: datetime | None = None
    created_at: datetime = Field(default_factory=now)

    @property
    def is_approved(self) -> bool:
        return self.approved_by is not None


class Circle(BaseModel):
    cx: int
    cy: int
    radius: int


class Region(BaseModel):
    """A defect's tight extent in natural pixels — what the review UI outlines."""

    left: int
    top: int
    width: int
    height: int


class DefectRecord(BaseModel):
    id: str
    project_id: str
    image_id: str
    pin: int
    cells: list[str]
    category: Category
    severity: Severity
    comment: str
    rule_ref: str = ""
    circle: Circle
    #: None only on records that predate region tracking; the UI falls back to the circle.
    region: Region | None = None
    circle_iterations: int = 1
    circle_verified: bool = True
    status: DefectState = DefectState.OPEN
    #: Only set when the Owner override-approves; always carries a rationale.
    rationale: str = ""
    resolved_in_image_id: str | None = None
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class DismissalRecord(BaseModel):
    """Golden rule 3: logged, never deleted."""

    id: str
    project_id: str
    image_id: str
    cells: list[str]
    hypothesis: str
    reason: str
    stage: str
    created_at: datetime = Field(default_factory=now)


class Comment(BaseModel):
    id: str
    project_id: str
    defect_id: str
    author_id: str
    author_name: str = ""
    is_agent: bool = False
    body: str
    mentions: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=now)


class ThreadAgentState(StrEnum):
    """Whether the agent was asked to look at a human annotation, and how that went."""

    NONE = "none"
    INSPECTING = "inspecting"
    ANSWERED = "answered"
    FAILED = "failed"


class ReviewThread(BaseModel):
    """A human-anchored annotation: drawn shapes plus a comment thread.

    Shares one pin sequence with defects so the canvas numbering is a single
    story. Comments attach via their ``defect_id`` field carrying this thread's
    id — one thread mechanism, two kinds of author.
    """

    id: str
    project_id: str
    image_id: str
    pin: int
    author_id: str
    author_name: str = ""
    shapes: list[Shape] = Field(default_factory=list)
    resolved: bool = False
    agent_state: ThreadAgentState = ThreadAgentState.NONE
    #: Set when an agent inspection confirmed a defect here.
    defect_id: str | None = None
    created_at: datetime = Field(default_factory=now)


class NotificationKind(StrEnum):
    MENTION = "mention"
    RUN_FINISHED = "run_finished"
    MEMORY_PROPOSED = "memory_proposed"
    DEFECT_RESOLVED = "defect_resolved"


class Notification(BaseModel):
    id: str
    user_id: str
    project_id: str
    kind: NotificationKind
    body: str
    link: str = ""
    read: bool = False
    created_at: datetime = Field(default_factory=now)
