"""The multi-agent pipeline: Scanner -> Inspector -> Annotator -> Pro gate.

Stage boundaries are the interesting part. The Scanner over-flags on purpose; the
Inspector kills false positives with resolution the Scanner never had; the Annotator
draws and then *re-reads its own drawing* to check the circle landed; the Pro gate
spends a strictly limited budget of the expensive model on final judgement.

The annotation loop is driven from Python rather than an ADK ``LoopAgent`` because
each iteration must re-render the image before the model can look at it again —
the feedback signal is pixels, not text.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from google.adk.agents import LlmAgent
from PIL import Image

from app.agents import prompts
from app.agents.runtime import bytes_part, run_agent
from app.agents.schemas import (
    CircleCheck,
    GateVerdict,
    ScanResult,
    Suspect,
    Verdict,
    validate_against_grid,
)
from app.config import settings
from app.domain.grid import Grid
from app.domain.taxonomy import Category, Severity
from app.imaging.annotate import Annotation, draw_annotations
from app.imaging.canvas import fit_for_model, to_png_bytes
from app.imaging.contact_sheet import inspection_sheet
from app.imaging.crops import zoom_cells
from app.imaging.grid_overlay import apply_grid

ProgressHook = Callable[[str, dict], Awaitable[None]] | None


# --- results --------------------------------------------------------------


@dataclass
class Defect:
    pin: int
    cells: list[str]
    category: Category
    severity: Severity
    comment: str
    rule_ref: str
    annotation: Annotation
    circle_iterations: int
    circle_verified: bool

    @property
    def needs_human_review(self) -> bool:
        """The annotation loop ran out of attempts without landing the circle."""
        return not self.circle_verified


@dataclass
class Dismissal:
    """Never deleted (domain-model.md golden rule 3)."""

    cells: list[str]
    hypothesis: str
    reason: str
    stage: str


@dataclass
class ImageReport:
    defects: list[Defect] = field(default_factory=list)
    dismissals: list[Dismissal] = field(default_factory=list)
    scan_notes: str = ""
    pro_gate_ran: bool = False
    pro_gate_reason: str = ""

    @property
    def blockers(self) -> int:
        return sum(1 for d in self.defects if d.severity is Severity.BLOCKER)


class ProBudget:
    """Hard cap on expensive-model calls for one run (domain-model.md decision 5).

    Spent greedily in completion order on images that actually have findings. When
    it runs out, later images simply skip the gate — recorded on the report rather
    than silently dropped.
    """

    def __init__(self, limit: int | None = None):
        self.limit = settings.max_pro_calls_per_run if limit is None else limit
        self.spent = 0

    def claim(self) -> bool:
        if self.spent >= self.limit:
            return False
        self.spent += 1
        return True

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.spent)


# --- agents ---------------------------------------------------------------


def scanner_agent(guidelines: str) -> LlmAgent:
    return LlmAgent(
        model=settings.model_flash,
        name="scanner",
        description="Flags suspect grid cells across the whole image.",
        instruction=f"{prompts.load('scanner')}\n\n# Active guidelines\n\n{guidelines}",
        output_schema=ScanResult,
        output_key="scan",
    )


def inspector_agent(guidelines: str) -> LlmAgent:
    return LlmAgent(
        model=settings.model_flash,
        name="inspector",
        description="Confirms or dismisses one suspect region at zoom.",
        instruction=f"{prompts.load('inspector')}\n\n# Active guidelines\n\n{guidelines}",
        output_schema=Verdict,
        output_key="verdict",
    )


def annotator_agent() -> LlmAgent:
    return LlmAgent(
        model=settings.model_flash,
        name="annotator",
        description="Checks whether its own circle landed on the defect.",
        instruction=prompts.load("annotator"),
        output_schema=CircleCheck,
        output_key="check",
    )


def pro_gate_agent(guidelines: str) -> LlmAgent:
    return LlmAgent(
        model=settings.model_pro,
        name="pro_gate",
        description="Final review of all findings for one image.",
        instruction=f"{prompts.load('pro_gate')}\n\n# Active guidelines\n\n{guidelines}",
        output_schema=GateVerdict,
        output_key="gate",
    )


# --- stages ---------------------------------------------------------------


async def scan(image: Image.Image, grid: Grid, guidelines: str) -> ScanResult:
    """Stage 1 — whole image plus labelled grid, high recall."""
    gridded = apply_grid(image, grid)
    result = await run_agent(
        scanner_agent(guidelines),
        prompt=(
            "Image 1 is the original. Image 2 is the same image with the labelled grid. "
            f"The grid is {grid.cols} columns (A-{chr(ord('A') + grid.cols - 1)}) by "
            f"{grid.rows} rows (1-{grid.rows}). Flag every region that might contain a defect."
        ),
        images=[
            bytes_part(to_png_bytes(fit_for_model(image))),
            bytes_part(to_png_bytes(fit_for_model(gridded))),
        ],
        schema=ScanResult,
    )

    # Models occasionally invent cells outside the grid; keep the suspect if any survive.
    cleaned: list[Suspect] = []
    for suspect in result.suspects:
        valid = validate_against_grid(suspect.cells, grid)
        if valid:
            cleaned.append(suspect.model_copy(update={"cells": valid}))
    result.suspects = cleaned
    return result


async def inspect(image: Image.Image, grid: Grid, suspect: Suspect, guidelines: str) -> Verdict:
    """Stage 2 — zoom into one suspect and decide. This is the precision gate."""
    zoomed = zoom_cells(image, grid, suspect.cells)
    locator = grid.zoom_bounds(suspect.cells, margin_cells=settings.zoom_margin_cells)
    sheet = inspection_sheet(image, zoomed, suspect.cells, locator=locator)

    return await run_agent(
        inspector_agent(guidelines),
        prompt=(
            f"Suspected {suspect.category.value} defect in cells {', '.join(suspect.cells)}.\n"
            f"The Scanner's hypothesis: {suspect.hypothesis}\n"
            f"Possible rule violated: {suspect.rule_ref or 'none given'}\n\n"
            "Confirm or dismiss it."
        ),
        images=[bytes_part(to_png_bytes(fit_for_model(sheet)))],
        schema=Verdict,
    )


async def place_circle(
    image: Image.Image,
    grid: Grid,
    cells: list[str],
    comment: str,
    pin: int,
    severity: Severity,
    max_iterations: int | None = None,
) -> tuple[Annotation, int, bool]:
    """Stage 3 — draw, look at the drawing, nudge. Returns (annotation, iterations, verified).

    The agent is shown the rendered result each round, so it is judging real output
    rather than reasoning about coordinates it cannot see.
    """
    limit = settings.max_annotation_iterations if max_iterations is None else max_iterations
    cx, cy, radius = grid.circle_for(cells)
    annotation = Annotation(pin=pin, cx=cx, cy=cy, radius=radius, severity=severity)

    agent = annotator_agent()
    iterations = 0

    for _ in range(limit):
        iterations += 1
        rendered = draw_annotations(image, [annotation])
        check = await run_agent(
            agent,
            prompt=(
                f"The defect is: {comment}\n"
                f"It was localised to cells: {', '.join(cells)}.\n"
                f"The image is {image.width}x{image.height} pixels and the circle is "
                f"centred at ({annotation.cx}, {annotation.cy}) "
                f"with radius {annotation.radius}.\n\n"
                "Does the circle enclose the defect?"
            ),
            images=[bytes_part(to_png_bytes(fit_for_model(rendered)))],
            schema=CircleCheck,
        )

        if check.on_target:
            return annotation, iterations, True

        if (check.dx, check.dy, check.dr) == (0, 0, 0):
            # Off target but no correction offered — further rounds cannot help.
            return annotation, iterations, False

        annotation = annotation.moved(check.dx, check.dy, check.dr).clamped(
            image.width, image.height
        )

    return annotation, iterations, False


async def apply_pro_gate(image: Image.Image, defects: list[Defect], guidelines: str) -> GateVerdict:
    """Stage 4 — the expensive model reviews everything at once."""
    annotated = draw_annotations(image, [d.annotation for d in defects])
    listing = "\n".join(
        f"- Pin {d.pin}: [{d.category.value}/{d.severity.value}] {d.comment} "
        f"(cells {', '.join(d.cells)}, rule {d.rule_ref or 'none'})"
        for d in defects
    )
    return await run_agent(
        pro_gate_agent(guidelines),
        prompt=f"Confirmed defects on this image:\n\n{listing}\n\nReview them.",
        images=[bytes_part(to_png_bytes(fit_for_model(annotated)))],
        schema=GateVerdict,
    )


# --- orchestration --------------------------------------------------------


async def process_image(
    image: Image.Image,
    guidelines: str,
    budget: ProBudget | None = None,
    on_progress: ProgressHook = None,
    grid: Grid | None = None,
) -> ImageReport:
    """Run one image through every stage."""
    grid = grid or Grid.for_image(image.width, image.height)
    budget = budget or ProBudget()
    report = ImageReport()

    async def emit(stage: str, **detail) -> None:
        if on_progress:
            await on_progress(stage, detail)

    await emit("scan_started", grid=f"{grid.cols}x{grid.rows}")
    scan_result = await scan(image, grid, guidelines)
    report.scan_notes = scan_result.notes
    await emit("scan_finished", suspects=len(scan_result.suspects))

    if not scan_result.suspects:
        return report

    # Inspect every suspect concurrently — they are independent judgements.
    verdicts = await asyncio.gather(
        *(inspect(image, grid, suspect, guidelines) for suspect in scan_result.suspects),
        return_exceptions=True,
    )

    confirmed: list[tuple[Suspect, Verdict]] = []
    for suspect, verdict in zip(scan_result.suspects, verdicts, strict=True):
        if isinstance(verdict, BaseException):
            report.dismissals.append(
                Dismissal(
                    suspect.cells, suspect.hypothesis, f"inspector failed: {verdict}", "inspector"
                )
            )
            continue
        if verdict.confirmed:
            confirmed.append((suspect, verdict))
        else:
            report.dismissals.append(
                Dismissal(suspect.cells, suspect.hypothesis, verdict.reason, "inspector")
            )

    await emit("inspection_finished", confirmed=len(confirmed), dismissed=len(report.dismissals))

    for pin, (suspect, verdict) in enumerate(confirmed, start=1):
        cells = validate_against_grid(verdict.cells, grid) or suspect.cells
        severity = verdict.severity or Severity.WARNING
        comment = verdict.comment or verdict.reason

        await emit("annotating", pin=pin, cells=cells)
        annotation, iterations, verified = await place_circle(
            image, grid, cells, comment, pin, severity
        )
        await emit("annotated", pin=pin, iterations=iterations, verified=verified)

        report.defects.append(
            Defect(
                pin=pin,
                cells=cells,
                category=verdict.category or suspect.category,
                severity=severity,
                comment=comment,
                rule_ref=suspect.rule_ref,
                annotation=annotation,
                circle_iterations=iterations,
                circle_verified=verified,
            )
        )

    if report.defects and budget.claim():
        await emit("pro_gate_started", remaining_after=budget.remaining)
        gate = await apply_pro_gate(image, report.defects, guidelines)
        _apply_gate_verdict(report, gate)
        report.pro_gate_ran = True
        report.pro_gate_reason = gate.reason
        await emit("pro_gate_finished", rejected=len(gate.rejected_pins))
    elif report.defects:
        report.pro_gate_reason = "skipped: Pro budget for this run is exhausted"
        await emit("pro_gate_skipped", reason=report.pro_gate_reason)

    return report


def _apply_gate_verdict(report: ImageReport, gate: GateVerdict) -> None:
    kept: list[Defect] = []
    for defect in report.defects:
        if defect.pin in gate.rejected_pins:
            report.dismissals.append(
                Dismissal(
                    defect.cells, defect.comment, gate.reason or "rejected by Pro gate", "pro_gate"
                )
            )
            continue
        new_severity = gate.severity_changes.get(str(defect.pin))
        if new_severity:
            defect.severity = new_severity
            defect.annotation = Annotation(
                pin=defect.annotation.pin,
                cx=defect.annotation.cx,
                cy=defect.annotation.cy,
                radius=defect.annotation.radius,
                severity=new_severity,
            )
        kept.append(defect)
    report.defects = kept


async def process_batch(
    images: list[Image.Image],
    guidelines: str,
    on_progress: ProgressHook = None,
    concurrency: int | None = None,
) -> list[ImageReport]:
    """Fan a batch out, capped so a large upload cannot exhaust model quota."""
    budget = ProBudget()
    limit = settings.max_concurrent_images if concurrency is None else concurrency
    semaphore = asyncio.Semaphore(limit)

    async def one(index: int, image: Image.Image) -> ImageReport:
        async with semaphore:

            async def hook(stage: str, detail: dict) -> None:
                if on_progress:
                    await on_progress(stage, {**detail, "image_index": index})

            return await process_image(image, guidelines, budget=budget, on_progress=hook)

    return list(await asyncio.gather(*(one(i, image) for i, image in enumerate(images))))
