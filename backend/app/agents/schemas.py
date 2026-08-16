"""Structured outputs for every agent in the pipeline.

Models emit these and nothing else. Cell refs are validated against the actual
grid before any of it reaches the imaging layer (AGENTS.md golden rule 1).
"""

from pydantic import BaseModel, Field, field_validator

from app.domain.grid import Grid, GridError, parse_ref
from app.domain.taxonomy import Category, Severity


def _normalise_refs(refs: list[str]) -> list[str]:
    cleaned: list[str] = []
    for ref in refs:
        parse_ref(ref)  # raises GridError on malformed input
        upper = ref.strip().upper()
        if upper not in cleaned:
            cleaned.append(upper)
    return cleaned


class Suspect(BaseModel):
    """One region the Scanner thinks is worth a closer look. High recall by design."""

    cells: list[str] = Field(description="Grid cells covering the suspect region, e.g. ['C4','D4']")
    category: Category
    hypothesis: str = Field(description="What might be wrong here, in one sentence")
    rule_ref: str = Field(default="", description="Id of the guideline rule this may violate")
    confidence: float = Field(ge=0.0, le=1.0, description="0-1; low is fine, the Inspector decides")

    @field_validator("cells")
    @classmethod
    def _validate_cells(cls, refs: list[str]) -> list[str]:
        if not refs:
            raise ValueError("a suspect must name at least one cell")
        return _normalise_refs(refs)


class ScanResult(BaseModel):
    suspects: list[Suspect] = Field(default_factory=list)
    notes: str = Field(default="", description="Anything the Inspector should know")


class Verdict(BaseModel):
    """The Inspector's precision gate on one suspect."""

    confirmed: bool = Field(description="True only if a real defect is visible in the zoom")
    reason: str = Field(description="What you actually saw, in one sentence")
    category: Category | None = None
    severity: Severity | None = None
    comment: str = Field(
        default="", description="Reviewer-facing note, written for a designer to act on"
    )
    cells: list[str] = Field(
        default_factory=list, description="Tighter cell refs if the defect is smaller than flagged"
    )

    @field_validator("cells")
    @classmethod
    def _validate_cells(cls, refs: list[str]) -> list[str]:
        return _normalise_refs(refs)


class CircleCheck(BaseModel):
    """The Annotator looking at its own drawing and deciding whether to nudge it."""

    on_target: bool = Field(description="True if the circle encloses the defect")
    dx: int = Field(default=0, description="Pixels to move the circle right (negative = left)")
    dy: int = Field(default=0, description="Pixels to move the circle down (negative = up)")
    dr: int = Field(default=0, description="Change in radius; positive grows the circle")
    reason: str = Field(default="", description="Why it is or is not on target")


class GateVerdict(BaseModel):
    """The Pro gate's final review of the whole image's findings."""

    rejected_pins: list[int] = Field(
        default_factory=list, description="Pin numbers that are false positives"
    )
    severity_changes: dict[str, Severity] = Field(
        default_factory=dict, description="Pin number (as string) -> corrected severity"
    )
    reason: str = Field(default="", description="Brief justification for the changes")


class RecheckVerdict(BaseModel):
    """Whether a submitted fix actually removed the defect it claims to fix."""

    resolved: bool = Field(description="True only if the described defect is gone")
    reason: str = Field(description="What you see in the AFTER panel, in one sentence")
    note: str = Field(
        default="", description="Anything else worth flagging, e.g. a new problem introduced"
    )


class GuidelineQuestion(BaseModel):
    question: str
    why_it_matters: str = Field(default="")


class GuidelineGrilling(BaseModel):
    """Ambiguities found in an uploaded guideline, put to the Brand Owner."""

    questions: list[GuidelineQuestion] = Field(default_factory=list)


class ProposedColour(BaseModel):
    """One palette colour read out of a guideline document."""

    hex: str = Field(description="Six-digit hex, e.g. #1d9e75")
    role: str = Field(default="", description="What the brand calls it: primary, accent, ink…")
    #: How the colour was obtained. A hex printed as text is far more reliable than
    #: one read off a swatch, and the confirmation form says so to the Owner.
    read_from: str = Field(
        default="swatch", description="'text' if the hex was printed, 'swatch' if sampled visually"
    )
    note: str = Field(default="", description="Where in the document it appeared")


class PaletteExtraction(BaseModel):
    """A proposed brand palette plus whatever the document left unclear."""

    colours: list[ProposedColour] = Field(default_factory=list)
    questions: list[GuidelineQuestion] = Field(default_factory=list)
    notes: str = Field(default="")


def validate_against_grid(refs: list[str], grid: Grid) -> list[str]:
    """Drop refs the model invented that fall outside this image's grid.

    Models occasionally emit ``J9`` for an 8x8 grid. Silently dropping is right:
    the Inspector re-localises anyway, and a hard failure would lose the whole scan.
    """
    kept = []
    for ref in refs:
        try:
            grid.parse(ref)
        except GridError:
            continue
        kept.append(ref.strip().upper())
    return kept
