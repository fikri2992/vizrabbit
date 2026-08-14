"""Frame.io-style annotations: numbered pins and circles.

The model never draws. It emits cell refs and nudges; this module renders them,
which is what makes the Annotator's self-check meaningful — it is looking at the
same pixels a human reviewer will see.
"""

from dataclasses import dataclass

from PIL import Image, ImageDraw

from app.domain.taxonomy import Severity
from app.imaging.canvas import font_for

SEVERITY_COLORS: dict[Severity, tuple[int, int, int]] = {
    Severity.BLOCKER: (239, 68, 68),
    Severity.WARNING: (245, 158, 11),
    Severity.NITPICK: (96, 165, 250),
}

#: Stroke weights are relative to the image's short edge. Absolute pixel widths
#: look right at one resolution and vanish at another — a 4px ring is invisible
#: on a 4000px asset, and reviewers judge these annotations at full size.
REFERENCE_EDGE = 1000
RING_WIDTH = 6
PIN_RADIUS = 22
MIN_RING_WIDTH = 2
MIN_PIN_RADIUS = 10


def _scale_for(image: Image.Image) -> float:
    return max(min(image.width, image.height) / REFERENCE_EDGE, 0.5)


@dataclass(frozen=True)
class Annotation:
    """A rendered circle: pixel geometry plus what the pin should say."""

    pin: int
    cx: int
    cy: int
    radius: int
    severity: Severity = Severity.WARNING

    def moved(self, dx: int, dy: int, dr: int = 0) -> "Annotation":
        """Apply one nudge from the Annotator's self-check."""
        return Annotation(
            pin=self.pin,
            cx=self.cx + dx,
            cy=self.cy + dy,
            radius=max(4, self.radius + dr),
            severity=self.severity,
        )

    def clamped(self, width: int, height: int) -> "Annotation":
        """Keep the circle's centre on the canvas after a nudge."""
        return Annotation(
            pin=self.pin,
            cx=min(max(self.cx, 0), width),
            cy=min(max(self.cy, 0), height),
            radius=max(4, min(self.radius, max(width, height))),
            severity=self.severity,
        )


def draw_annotations(image: Image.Image, annotations: list[Annotation]) -> Image.Image:
    """Render every circle and numbered pin onto a copy of ``image``."""
    canvas = image.convert("RGB").copy()
    draw = ImageDraw.Draw(canvas)

    scale = _scale_for(canvas)
    ring_width = max(MIN_RING_WIDTH, round(RING_WIDTH * scale))
    pin_radius = max(MIN_PIN_RADIUS, round(PIN_RADIUS * scale))
    font = font_for(max(12, round(pin_radius * 1.15)))

    for annotation in annotations:
        color = SEVERITY_COLORS[annotation.severity]
        _draw_ring(draw, annotation, color, ring_width)
        _draw_pin(draw, annotation, color, font, pin_radius, ring_width)

    return canvas


def _draw_ring(draw: ImageDraw.ImageDraw, annotation: Annotation, color, width: int) -> None:
    box = [
        annotation.cx - annotation.radius,
        annotation.cy - annotation.radius,
        annotation.cx + annotation.radius,
        annotation.cy + annotation.radius,
    ]
    # A dark halo on both sides keeps the ring readable over light and dark imagery.
    # PIL grows stroke width inwards, so the halo ring is both offset outwards and
    # widened by 2x the halo — otherwise it shows only on the outer edge and reads
    # as a second concentric ring rather than an outline.
    halo = max(1, width // 2)
    draw.ellipse(
        [c + o * halo for c, o in zip(box, (-1, -1, 1, 1), strict=True)],
        outline=(0, 0, 0),
        width=width + 2 * halo,
    )
    draw.ellipse(box, outline=color, width=width)


def _draw_pin(
    draw: ImageDraw.ImageDraw, annotation: Annotation, color, font, radius: int, stroke: int
) -> None:
    """Numbered badge on the circle's upper-left, the way frame.io pins read."""
    offset = int(annotation.radius * 0.7071)
    px, py = annotation.cx - offset, annotation.cy - offset
    box = [px - radius, py - radius, px + radius, py + radius]

    draw.ellipse(box, fill=color, outline=(0, 0, 0), width=max(2, stroke // 2))
    draw.text((px, py), str(annotation.pin), font=font, fill=(0, 0, 0), anchor="mm")
