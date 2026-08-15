"""Human-drawn annotation shapes, in the image's natural pixel space.

Frame.io's model: a reviewer draws directly on the frame and the drawing anchors a
comment. Shapes are stored in natural pixels (never screen pixels) so they survive
any zoom level, and are converted to grid cells only when the agent needs to look
at the region — the same cells-first boundary every model call already uses.

Geometry is a flat float list interpreted per kind, which keeps one wire schema:

    circle  [cx, cy, r]
    rect    [x, y, w, h]
    arrow   [x1, y1, x2, y2]
    path    [x1, y1, x2, y2, ...]  free-hand polyline, >= 2 points
"""

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from app.domain.grid import Box, Grid


class ShapeKind(StrEnum):
    CIRCLE = "circle"
    RECT = "rect"
    ARROW = "arrow"
    PATH = "path"


#: Severity palette, reused so human annotations speak the product's colour language.
ALLOWED_COLORS = ("#E24B4A", "#EF9F27", "#378ADD", "#22C55E", "#E879F9")

_MIN_VALUES = {ShapeKind.CIRCLE: 3, ShapeKind.RECT: 4, ShapeKind.ARROW: 4, ShapeKind.PATH: 4}
_EXACT = {ShapeKind.CIRCLE, ShapeKind.RECT, ShapeKind.ARROW}


class Shape(BaseModel):
    kind: ShapeKind
    points: list[float] = Field(min_length=3, max_length=2000)
    color: str = ALLOWED_COLORS[0]

    @model_validator(mode="after")
    def _validate_geometry(self) -> "Shape":
        wanted = _MIN_VALUES[self.kind]
        if self.kind in _EXACT and len(self.points) != wanted:
            raise ValueError(f"{self.kind} needs exactly {wanted} values")
        if self.kind is ShapeKind.PATH and (len(self.points) < wanted or len(self.points) % 2):
            raise ValueError("path needs an even number of values, at least 4")
        if self.kind is ShapeKind.CIRCLE and self.points[2] <= 0:
            raise ValueError("circle radius must be positive")
        if self.kind is ShapeKind.RECT and (self.points[2] <= 0 or self.points[3] <= 0):
            raise ValueError("rect needs positive width and height")
        if self.color not in ALLOWED_COLORS:
            raise ValueError(f"color must be one of {ALLOWED_COLORS}")
        return self

    def bbox(self) -> Box:
        """Axis-aligned bounds, used to find which grid cells the shape touches."""
        if self.kind is ShapeKind.CIRCLE:
            cx, cy, r = self.points
            return Box(round(cx - r), round(cy - r), round(cx + r), round(cy + r))
        if self.kind is ShapeKind.RECT:
            x, y, w, h = self.points
            return Box(round(x), round(y), round(x + w), round(y + h))
        xs, ys = self.points[0::2], self.points[1::2]
        return Box(round(min(xs)), round(min(ys)), round(max(xs)), round(max(ys)))


def shapes_bbox(shapes: list[Shape]) -> Box:
    """The union bounds of every shape in an annotation."""
    if not shapes:
        raise ValueError("an annotation needs at least one shape")
    boxes = [shape.bbox() for shape in shapes]
    return Box(
        left=min(b.left for b in boxes),
        top=min(b.top for b in boxes),
        right=max(b.right for b in boxes),
        bottom=max(b.bottom for b in boxes),
    )


def shapes_to_cells(shapes: list[Shape], grid: Grid) -> list[str]:
    """Grid cells the drawn region touches — how a drawing becomes agent-readable.

    Clamped to the image: a stroke that wanders off-canvas still resolves to the
    cells it actually crossed. A drawing wholly outside the image yields the
    nearest edge cell rather than nothing, so the agent always has a region.
    """
    box = shapes_bbox(shapes)
    left = max(0, min(box.left, grid.width - 1))
    top = max(0, min(box.top, grid.height - 1))
    right = max(left + 1, min(box.right, grid.width))
    bottom = max(top + 1, min(box.bottom, grid.height))

    cells = [
        ref
        for ref in grid.all_refs()
        if (bounds := grid.cell_bounds(ref)).left < right
        and bounds.right > left
        and bounds.top < bottom
        and bounds.bottom > top
    ]
    return cells
