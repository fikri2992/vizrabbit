"""Synthetic benchmark for the brand palette checker (Gate 7).

Two populations, both generated so the ground truth is exact rather than labelled:

- **Violating**: an on-brand composition with one *designed* element — a panel,
  a strapline bar, a logo lockup — recoloured off-palette. A brand defect should
  be raised, in a known cell.
- **Clean**: an on-brand composition whose only off-palette colours are
  *photographic* — skin, produce, foliage, sky, a warm reflection. Those colours
  measure far from the palette by design; raising a defect on one is the false
  positive this benchmark exists to catch.

That asymmetry is the whole point. The measurement layer cannot tell the two
apart and is not supposed to: it should find every off-palette region in both
populations. Separating them is the Inspector's job, so the two modes report
different things — ``mechanical`` measures recall of the *measurement*, and
``full`` measures whether the pipeline's judgement holds.
"""

import math
import random
from dataclasses import dataclass, field

from PIL import Image, ImageDraw

from app.domain.brand import PaletteOffence, evaluate
from app.domain.entities import BrandProfile, PaletteEntry
from app.domain.grid import Grid
from app.imaging.palette import measure_cells

#: A plausible small brand palette: primary, ink, paper, accent.
BRAND_PALETTE = ["#1d9e75", "#1c1e2a", "#f1efe8", "#534ab7"]

#: Off-palette colours for planted *designed* elements. Each is far enough from
#: every brand colour to be unambiguous, and none is a natural skin or foliage tone.
OFF_PALETTE = [
    "#d85a30",
    "#e24b4a",
    "#ba7517",
    "#d4537e",
    "#378add",
    "#97c459",
    "#ef9f27",
    "#993556",
    "#0f6e56",
    "#712b13",
]

#: Colours that are off-palette but unmistakably scene content, not design.
PHOTOGRAPHIC = [
    "#c68642",  # skin, mid
    "#8d5524",  # skin, deep
    "#ffdbac",  # skin, light
    "#4f7942",  # foliage
    "#87ceeb",  # sky
    "#b7410e",  # rust / terracotta prop
]


def profile() -> BrandProfile:
    """A confirmed profile — the benchmark measures the checker, not the gate."""
    return BrandProfile(
        id="bench",
        project_id="bench",
        entries=[
            PaletteEntry(hex=BRAND_PALETTE[0], role="primary", tolerance=3.0),
            PaletteEntry(hex=BRAND_PALETTE[1], role="ink", tolerance=4.0),
            PaletteEntry(hex=BRAND_PALETTE[2], role="paper", tolerance=4.0),
            PaletteEntry(hex=BRAND_PALETTE[3], role="accent", tolerance=3.0),
        ],
        confirmed_by="bench-owner",
    )


@dataclass
class Case:
    name: str
    image: Image.Image
    grid: Grid
    #: Cell refs where a brand defect *should* be raised. Empty for clean cases.
    truth_cells: list[str] = field(default_factory=list)
    violating: bool = False


def _rgb(hex_value: str) -> tuple[int, int, int]:
    return tuple(int(hex_value.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore


def _compose(draw: ImageDraw.ImageDraw, size: int, rng: random.Random) -> None:
    """An on-brand layout: paper ground, ink header, primary product block."""
    draw.rectangle([0, 0, size, size], fill=_rgb(BRAND_PALETTE[2]))
    draw.rectangle([0, 0, size, size // 8], fill=_rgb(BRAND_PALETTE[1]))
    inset = size // 6
    draw.rounded_rectangle(
        [inset, size // 3, size - inset, size - inset], size // 20, fill=_rgb(BRAND_PALETTE[0])
    )
    if rng.random() < 0.5:
        draw.rectangle(
            [inset, size // 5, size // 2, size // 5 + size // 16], fill=_rgb(BRAND_PALETTE[3])
        )


def violating_case(index: int, size: int = 800, seed: int | None = None) -> Case:
    """On-brand composition with one designed element recoloured off-palette."""
    rng = random.Random(seed if seed is not None else 1000 + index)
    image = Image.new("RGB", (size, size))
    grid = Grid.for_image(size, size)
    draw = ImageDraw.Draw(image)
    _compose(draw, size, rng)

    # Plant the element on a whole cell so the truth is a cell ref, not a guess.
    ref = rng.choice([r for r in grid.all_refs() if not r.endswith("1")])
    box = grid.cell_bounds(ref)
    colour = OFF_PALETTE[index % len(OFF_PALETTE)]
    draw.rectangle(box.as_tuple(), fill=_rgb(colour))

    return Case(
        name=f"violating_{index:02d}_{colour.lstrip('#')}",
        image=image,
        grid=grid,
        truth_cells=[ref],
        violating=True,
    )


def clean_case(index: int, size: int = 800, seed: int | None = None) -> Case:
    """On-brand composition whose off-palette colour is photographic, not designed.

    Rendered as a soft radial blob rather than a hard rectangle: the softness is
    the visual cue that separates a photograph from a graphic, and a checker that
    cannot use it will fail this half of the benchmark.
    """
    rng = random.Random(seed if seed is not None else 2000 + index)
    image = Image.new("RGB", (size, size))
    grid = Grid.for_image(size, size)
    draw = ImageDraw.Draw(image)
    _compose(draw, size, rng)

    colour = _rgb(PHOTOGRAPHIC[index % len(PHOTOGRAPHIC)])
    cx, cy = rng.randint(size // 3, 2 * size // 3), rng.randint(size // 2, 3 * size // 4)
    radius = size // 6
    base = image.getpixel((cx, cy))
    for step in range(radius, 0, -2):
        blend = 1 - (step / radius) ** 2
        shade = tuple(round(base[i] + (colour[i] - base[i]) * blend) for i in range(3))
        draw.ellipse([cx - step, cy - step, cx + step, cy + step], fill=shade)

    return Case(name=f"clean_{index:02d}", image=image, grid=grid, violating=False)


def dataset(violating: int = 10, clean: int = 10) -> list[Case]:
    return [violating_case(i) for i in range(violating)] + [clean_case(i) for i in range(clean)]


# --- scoring --------------------------------------------------------------


@dataclass
class Score:
    recall: float
    false_positives: int
    detected: int
    total_violating: int
    clean_cases: int

    def as_table(self) -> str:
        return (
            f"recall            {self.recall:.2f}  ({self.detected}/{self.total_violating})\n"
            f"false positives   {self.false_positives}  (across {self.clean_cases} clean images)"
        )


def hit(offences: list[PaletteOffence], truth_cells: list[str]) -> bool:
    """Did anything get flagged on a truth cell?"""
    wanted = set(truth_cells)
    return any(wanted.intersection(offence.cells) for offence in offences)


def score(results: list[tuple[Case, list[PaletteOffence]]]) -> Score:
    violating = [(case, found) for case, found in results if case.violating]
    clean = [(case, found) for case, found in results if not case.violating]

    detected = sum(1 for case, found in violating if hit(found, case.truth_cells))
    false_positives = sum(1 for _, found in clean if found)

    return Score(
        recall=detected / len(violating) if violating else math.nan,
        false_positives=false_positives,
        detected=detected,
        total_violating=len(violating),
        clean_cases=len(clean),
    )


def run_mechanical(cases: list[Case]) -> list[tuple[Case, list[PaletteOffence]]]:
    """Measurement only — no model, no cost, no judgement.

    Expect near-perfect recall *and* a false positive on every clean case: the
    photographic blob really is off-palette. That is the measurement doing its
    job and handing the hard question to the Inspector.
    """
    brand = profile()
    return [
        (case, evaluate(measure_cells(case.image, case.grid), brand)) for case in cases
    ]
