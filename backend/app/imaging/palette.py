"""Measuring what colours are actually present, cell by cell.

Pillow work only: quantise a region, report its dominant colours and how much of
the region each covers. Whether any of that breaches a brand palette is decided
in ``domain/brand.py``, and whether a breach is a *defect* is decided by the
Inspector. Three separate jobs, three separate places.

Quantisation rather than raw pixel counting because a gradient or a JPEG artefact
spreads one apparent colour across thousands of near-identical values; counting
those raw would report a hundred colours at 0.01% each and find nothing.
"""

from PIL import Image

from app.domain.brand import MeasuredColour
from app.domain.color import to_hex
from app.domain.grid import Grid

#: Palette size per region. Small on purpose: a cell showing more than a handful
#: of distinct colours is texture, and its "dominant" colour means little.
REGION_COLOURS = 6

#: Ignore colours covering less than this share of a region — below it the
#: reading is edge antialiasing between two other colours, not a colour in use.
MIN_COVERAGE = 0.12

#: Downsample cap per region. Dominant colour is a statistic; full resolution
#: buys nothing and costs a lot across ~64 cells.
SAMPLE_EDGE = 64


def dominant_colours(
    image: Image.Image, count: int = REGION_COLOURS, min_coverage: float = MIN_COVERAGE
) -> list[tuple[str, float]]:
    """The (hex, coverage) pairs a region is mostly made of, most common first."""
    if image.width == 0 or image.height == 0:
        return []

    sample = image.convert("RGB")
    sample.thumbnail((SAMPLE_EDGE, SAMPLE_EDGE), Image.Resampling.BILINEAR)

    quantised = sample.quantize(colors=count, method=Image.Quantize.MEDIANCUT, dither=0)
    palette = quantised.getpalette() or []
    total = sample.width * sample.height
    if not total:
        return []

    readings: list[tuple[str, float]] = []
    for pixels, index in sorted(quantised.getcolors() or [], reverse=True):
        coverage = pixels / total
        if coverage < min_coverage:
            continue
        rgb = tuple(palette[index * 3 : index * 3 + 3])
        if len(rgb) == 3:
            readings.append((to_hex(rgb), round(coverage, 4)))
    return readings


def measure_cells(
    image: Image.Image,
    grid: Grid,
    cells: list[str] | None = None,
    min_coverage: float = MIN_COVERAGE,
) -> list[MeasuredColour]:
    """Dominant colours of every grid cell (or just the ones asked for).

    Per cell rather than whole-image because a brand violation is usually a small
    designed element — a recoloured logo occupying 2% of the frame never shows up
    in a whole-image palette, but it dominates its own cell.
    """
    refs = cells if cells is not None else grid.all_refs()
    measured: list[MeasuredColour] = []

    for ref in refs:
        if not grid.contains(ref):
            continue
        box = grid.cell_bounds(ref)
        region = image.crop(box.as_tuple())
        for hex_value, coverage in dominant_colours(region, min_coverage=min_coverage):
            measured.append(MeasuredColour(cells=[ref], hex=hex_value, coverage=coverage))

    return measured


def measure_region(
    image: Image.Image, grid: Grid, cells: list[str], min_coverage: float = MIN_COVERAGE
) -> list[MeasuredColour]:
    """Dominant colours across a multi-cell span, treated as one region."""
    if not cells:
        return []
    box = grid.span_bounds(cells)
    region = image.crop(box.as_tuple())
    return [
        MeasuredColour(cells=list(cells), hex=hex_value, coverage=coverage)
        for hex_value, coverage in dominant_colours(region, min_coverage=min_coverage)
    ]
