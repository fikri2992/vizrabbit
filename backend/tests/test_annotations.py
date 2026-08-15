"""Annotation shapes and their conversion to grid cells.

The drawing is how a human tells the agent where to look, so the geometry that
maps a stroke to cells has to be exact — a wrong cell sends the Inspector to the
wrong crop and the reply looks like nonsense.
"""

import pytest
from pydantic import ValidationError

from app.domain.annotations import ALLOWED_COLORS, Shape, ShapeKind, shapes_bbox, shapes_to_cells
from app.domain.grid import Grid


@pytest.fixture
def grid():
    return Grid(cols=8, rows=8, width=800, height=800)


def circle(cx, cy, r, color=ALLOWED_COLORS[0]):
    return Shape(kind=ShapeKind.CIRCLE, points=[cx, cy, r], color=color)


def rect(x, y, w, h):
    return Shape(kind=ShapeKind.RECT, points=[x, y, w, h])


# --- validation -----------------------------------------------------------


def test_each_kind_validates_its_geometry():
    circle(100, 100, 30)
    rect(10, 10, 50, 50)
    Shape(kind=ShapeKind.ARROW, points=[0, 0, 100, 100])
    Shape(kind=ShapeKind.PATH, points=[0, 0, 10, 5, 20, 15])


@pytest.mark.parametrize(
    ("kind", "points"),
    [
        (ShapeKind.CIRCLE, [1, 2]),
        (ShapeKind.CIRCLE, [1, 2, 3, 4]),
        (ShapeKind.RECT, [1, 2, 3]),
        (ShapeKind.ARROW, [1, 2, 3]),
        (ShapeKind.PATH, [1, 2, 3]),  # odd count
    ],
)
def test_wrong_arity_is_rejected(kind, points):
    with pytest.raises(ValidationError):
        Shape(kind=kind, points=points)


def test_degenerate_shapes_are_rejected():
    with pytest.raises(ValidationError, match="radius"):
        circle(10, 10, 0)
    with pytest.raises(ValidationError, match="width"):
        rect(10, 10, 0, 50)


def test_colors_come_from_the_severity_palette():
    with pytest.raises(ValidationError, match="color"):
        circle(10, 10, 5, color="#123456")
    for color in ALLOWED_COLORS:
        assert circle(10, 10, 5, color=color).color == color


def test_a_runaway_freehand_path_is_capped():
    with pytest.raises(ValidationError):
        Shape(kind=ShapeKind.PATH, points=[float(i) for i in range(2002)])


# --- bounding boxes -------------------------------------------------------


def test_circle_bbox_encloses_the_circle():
    assert circle(100, 100, 30).bbox().as_tuple() == (70, 70, 130, 130)


def test_rect_bbox_is_the_rect():
    assert rect(10, 20, 50, 60).bbox().as_tuple() == (10, 20, 60, 80)


def test_arrow_and_path_bboxes_span_their_points():
    arrow = Shape(kind=ShapeKind.ARROW, points=[100, 50, 20, 90])
    assert arrow.bbox().as_tuple() == (20, 50, 100, 90)

    path = Shape(kind=ShapeKind.PATH, points=[5, 5, 50, 8, 30, 60])
    assert path.bbox().as_tuple() == (5, 5, 50, 60)


def test_multi_shape_bbox_is_the_union():
    box = shapes_bbox([circle(50, 50, 10), rect(200, 200, 50, 50)])
    assert box.as_tuple() == (40, 40, 250, 250)


def test_empty_annotation_is_an_error():
    with pytest.raises(ValueError, match="at least one shape"):
        shapes_bbox([])


# --- shapes -> cells ------------------------------------------------------


def test_a_small_circle_maps_to_its_cell(grid):
    # Cell C4 spans x 200-300, y 300-400; a circle wholly inside it.
    assert shapes_to_cells([circle(250, 350, 20)], grid) == ["C4"]


def test_a_shape_straddling_a_boundary_maps_to_both_cells(grid):
    assert shapes_to_cells([circle(300, 350, 20)], grid) == ["C4", "D4"]


def test_a_rect_spanning_a_block_maps_to_every_touched_cell(grid):
    cells = shapes_to_cells([rect(150, 150, 200, 200)], grid)
    assert cells == ["B2", "C2", "D2", "B3", "C3", "D3", "B4", "C4", "D4"]


def test_a_stroke_wandering_off_canvas_is_clamped(grid):
    cells = shapes_to_cells([Shape(kind=ShapeKind.PATH, points=[-50, -50, 30, 40])], grid)
    assert cells == ["A1"]


def test_a_drawing_wholly_outside_still_yields_an_edge_cell(grid):
    assert shapes_to_cells([circle(2000, 2000, 10)], grid) == ["H8"]


def test_cells_come_back_in_reading_order(grid):
    cells = shapes_to_cells([rect(0, 0, 250, 150)], grid)
    assert cells == ["A1", "B1", "C1", "A2", "B2", "C2"]
