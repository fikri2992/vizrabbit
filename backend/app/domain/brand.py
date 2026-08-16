"""Deciding what counts as off-palette, given measurements and a confirmed profile.

Pure: it takes colours somebody else measured and a profile somebody else
confirmed, and reports which measurements breach which tolerance. No image
handling, no model, no I/O.

The split matters. Everything here is arithmetic the Owner can re-do by hand, so
a brand defect never rests on the model's opinion of a colour — only on its
opinion of whether the measured thing was *designed* (domain-model.md decision
17). That is the part a model is actually good at.
"""

from pydantic import BaseModel, Field

from app.domain.color import nearest, normalise_hex
from app.domain.entities import BrandProfile

#: Rule id every palette finding cites. Brand rules are BRAND-*; this is the
#: mechanical one, so a later BRAND-TYPO or BRAND-LOGO slots in beside it.
PALETTE_RULE = "BRAND-PALETTE"


class MeasuredColour(BaseModel):
    """A colour actually present in a region of the image, and how much of it."""

    #: Grid cell refs the measurement came from, e.g. ``["C4"]``.
    cells: list[str] = Field(default_factory=list)
    hex: str
    #: Share of the region's pixels this colour accounts for, 0..1.
    coverage: float = 0.0


class PaletteOffence(BaseModel):
    """A measured colour that no palette entry accounts for, with the number."""

    cells: list[str]
    hex: str
    coverage: float
    nearest_hex: str
    nearest_role: str = ""
    delta_e: float
    tolerance: float

    def describe(self) -> str:
        """The sentence that carries the measurement into the defect comment."""
        role = f" ({self.nearest_role})" if self.nearest_role else ""
        return (
            f"Measured {self.hex} against the confirmed palette: "
            f"ΔE2000 {self.delta_e:.1f} from the nearest brand colour "
            f"{self.nearest_hex}{role}, which allows {self.tolerance:.1f}."
        )


def evaluate(
    measurements: list[MeasuredColour],
    profile: BrandProfile | None,
    min_coverage: float = 0.0,
) -> list[PaletteOffence]:
    """Off-palette measurements, worst first.

    An unconfirmed or absent profile yields nothing at all — not "everything
    passes" and not "everything fails". Silence is the only honest answer when
    nobody has said what the brand colours are.
    """
    if profile is None or not profile.is_active:
        return []

    palette = profile.palette
    offences: list[PaletteOffence] = []

    for measurement in measurements:
        if measurement.coverage < min_coverage:
            continue
        try:
            hex_value = normalise_hex(measurement.hex)
        except ValueError:
            continue

        match, distance = nearest(hex_value, palette)
        entry = profile.entry_for(match)
        tolerance = entry.tolerance if entry else 0.0
        if distance <= tolerance:
            continue

        offences.append(
            PaletteOffence(
                cells=measurement.cells,
                hex=hex_value,
                coverage=measurement.coverage,
                nearest_hex=match,
                nearest_role=entry.role if entry else "",
                delta_e=round(distance, 2),
                tolerance=tolerance,
            )
        )

    return sorted(offences, key=lambda o: (-o.delta_e, o.cells))


def offences_for_cells(
    offences: list[PaletteOffence], cells: list[str]
) -> list[PaletteOffence]:
    """The subset of offences touching any of ``cells`` — what the Inspector is shown."""
    wanted = set(cells)
    return [offence for offence in offences if wanted.intersection(offence.cells)]


def attach_measurement(
    comment: str, rule_ref: str, is_brand: bool, here: list[PaletteOffence]
) -> tuple[str, str]:
    """Put the measurement into a confirmed brand defect's comment and rule id.

    Done in code rather than asked of the model: a defect that quotes a ΔE the
    Owner can re-derive is evidence, and a defect that quotes a ΔE the model
    retyped is a rumour. Returns ``(comment, rule_ref)`` unchanged when this is
    not a brand finding or nothing was measured here.
    """
    if not is_brand or not here:
        return comment, rule_ref

    worst = max(here, key=lambda offence: offence.delta_e)
    stamped = comment
    if f"{worst.delta_e:.1f}" not in comment:
        stamped = f"{comment.rstrip()} {worst.describe()}".strip()
    return stamped, rule_ref or PALETTE_RULE


def summarise(offences: list[PaletteOffence], limit: int = 12) -> str:
    """The measurement block handed to the Scanner as evidence, not instruction.

    Capped because a busy photograph can produce dozens of off-palette readings
    and a wall of them would drown the guideline text it sits next to.
    """
    if not offences:
        return ""

    lines = [
        f"- cells {', '.join(offence.cells)}: {offence.hex} "
        f"({offence.coverage:.0%} of the region), ΔE2000 {offence.delta_e:.1f} from "
        f"{offence.nearest_hex} (tolerance {offence.tolerance:.1f})"
        for offence in offences[:limit]
    ]
    more = len(offences) - limit
    if more > 0:
        lines.append(f"- …and {more} further off-palette region(s)")

    return (
        "# Measured colour findings\n\n"
        "These are mechanical measurements, not defects. A region is only a brand "
        "defect if the off-palette colour belongs to a *designed* element — a logo, "
        "type, packaging, a graphic panel. Photographic scene content (skin, sky, "
        "food, foliage, reflections) is not governed by the palette, so dismiss it.\n\n"
        + "\n".join(lines)
    )
