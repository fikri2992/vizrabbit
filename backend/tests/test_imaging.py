"""Imaging toolkit — real Pillow operations, asserted on measurable properties.

No mocks: every test renders actual pixels and checks geometry, colour and
content. Synthetic fixtures have known structure so crops can be verified by
what they contain, not merely by their size.
"""

import pytest
from PIL import Image

from app.domain.grid import Grid
from app.domain.taxonomy import Severity
from app.imaging.annotate import SEVERITY_COLORS, Annotation, draw_annotations
from app.imaging.canvas import fit_for_model, font_for, from_bytes, to_png_bytes
from app.imaging.contact_sheet import contact_sheet, highlight_region, inspection_sheet
from app.imaging.crops import zoom_cells
from app.imaging.grid_overlay import apply_grid

GREY = (128, 128, 128)


@pytest.fixture
def flat_image():
    """Uniform grey — any non-grey pixel afterwards was drawn by us."""
    return Image.new("RGB", (800, 800), GREY)


@pytest.fixture
def quadrant_image():
    """Four distinctly coloured quadrants, so crops can be identified by colour."""
    image = Image.new("RGB", (800, 800))
    image.paste(Image.new("RGB", (400, 400), (255, 0, 0)), (0, 0))
    image.paste(Image.new("RGB", (400, 400), (0, 255, 0)), (400, 0))
    image.paste(Image.new("RGB", (400, 400), (0, 0, 255)), (0, 400))
    image.paste(Image.new("RGB", (400, 400), (255, 255, 0)), (400, 400))
    return image


@pytest.fixture
def grid():
    return Grid(cols=8, rows=8, width=800, height=800)


# --- canvas ---------------------------------------------------------------


def test_png_bytes_round_trip(quadrant_image):
    restored = from_bytes(to_png_bytes(quadrant_image))
    assert restored.size == quadrant_image.size
    assert restored.getpixel((10, 10)) == (255, 0, 0)
    assert restored.getpixel((790, 790)) == (255, 255, 0)


def test_fit_for_model_downscales_only_when_needed():
    big = Image.new("RGB", (4000, 2000))
    fitted = fit_for_model(big, max_edge=1536)
    assert max(fitted.size) == 1536
    assert fitted.width / fitted.height == pytest.approx(2.0, abs=0.01)


def test_fit_for_model_never_upscales():
    small = Image.new("RGB", (200, 100))
    assert fit_for_model(small, max_edge=1536).size == (200, 100)


def test_font_is_always_available():
    assert font_for(18) is not None


# --- grid overlay ---------------------------------------------------------


def test_overlay_preserves_dimensions(flat_image, grid):
    assert apply_grid(flat_image, grid).size == flat_image.size


def test_overlay_does_not_mutate_the_original(flat_image, grid):
    apply_grid(flat_image, grid)
    assert flat_image.getpixel((400, 400)) == GREY


def test_overlay_draws_lines_on_cell_boundaries(flat_image, grid):
    marked = apply_grid(flat_image, grid)
    # Sample an interior vertical boundary, away from any corner label.
    boundary_x = grid.x_edges()[4]
    assert marked.getpixel((boundary_x, 700)) != GREY


def test_overlay_leaves_cell_interiors_readable(flat_image, grid):
    """Lines and labels must not wash out the imagery being inspected."""
    marked = apply_grid(flat_image, grid)
    box = grid.cell_bounds("D5")
    assert marked.getpixel(box.center) == GREY


def test_overlay_labels_every_cell(flat_image, grid):
    """Each cell's top-left corner region must contain drawn label pixels."""
    marked = apply_grid(flat_image, grid)

    for ref in grid.all_refs():
        box = grid.cell_bounds(ref)
        corner = marked.crop((box.left + 1, box.top + 1, box.left + 45, box.top + 32))
        assert any(pixel != GREY for pixel in corner.get_flattened_data()), f"{ref} has no label"


def test_overlay_labels_survive_a_white_background(grid):
    """High-contrast stroke: labels must be visible on light imagery too."""
    white = Image.new("RGB", (800, 800), (255, 255, 255))
    marked = apply_grid(white, grid)
    corner = marked.crop((1, 1, 45, 32))
    assert any(sum(pixel) < 200 for pixel in corner.get_flattened_data()), "no dark stroke on white"


def test_overlay_infers_its_own_grid(flat_image):
    assert apply_grid(flat_image).size == flat_image.size


def test_overlay_rejects_a_mismatched_grid(flat_image):
    with pytest.raises(ValueError, match="grid is"):
        apply_grid(flat_image, Grid(cols=8, rows=8, width=1000, height=1000))


# --- crops ----------------------------------------------------------------


def test_zoom_crops_the_right_region(quadrant_image, grid):
    """A1 with no margin sits wholly inside the red quadrant."""
    crop = zoom_cells(quadrant_image, grid, ["A1"], margin_cells=0, upscale=1)
    assert crop.size == (100, 100)
    assert set(crop.get_flattened_data()) == {(255, 0, 0)}


def test_zoom_crop_of_the_far_corner_is_the_yellow_quadrant(quadrant_image, grid):
    crop = zoom_cells(quadrant_image, grid, ["H8"], margin_cells=0, upscale=1)
    assert set(crop.get_flattened_data()) == {(255, 255, 0)}


def test_zoom_margin_pulls_in_neighbouring_content(quadrant_image, grid):
    """D4 borders the quadrant seam, so a margin must reveal more than one colour."""
    crop = zoom_cells(quadrant_image, grid, ["D4"], margin_cells=1, upscale=1)
    assert crop.size == (300, 300)
    assert len(set(crop.get_flattened_data())) > 1


def test_zoom_upscales_by_the_configured_factor(quadrant_image, grid):
    crop = zoom_cells(quadrant_image, grid, ["C4"], margin_cells=1, upscale=2)
    assert crop.size == (600, 600)


def test_zoom_uses_config_defaults(quadrant_image, grid):
    """margin=1, upscale=2 from settings: (3 cells * 100px) * 2."""
    assert zoom_cells(quadrant_image, grid, ["C4"]).size == (600, 600)


def test_zoom_clamps_at_edges_without_padding(quadrant_image, grid):
    """A corner crop is smaller than an interior one — it must not be padded."""
    corner = zoom_cells(quadrant_image, grid, ["A1"], margin_cells=1, upscale=1)
    interior = zoom_cells(quadrant_image, grid, ["D4"], margin_cells=1, upscale=1)
    assert corner.size == (200, 200)
    assert interior.size == (300, 300)


def test_zoom_spanning_cells_covers_both(quadrant_image, grid):
    crop = zoom_cells(quadrant_image, grid, ["A1", "B1"], margin_cells=0, upscale=1)
    assert crop.size == (200, 100)


# --- contact sheets -------------------------------------------------------


def test_contact_sheet_places_every_panel(quadrant_image):
    sheet = contact_sheet([("A", quadrant_image), ("B", quadrant_image)], panel_height=200)
    assert sheet.height == 200 + 34 + 24
    assert sheet.width > 400


def test_contact_sheet_scales_panels_to_a_common_height(quadrant_image):
    tall = Image.new("RGB", (100, 900), (10, 10, 10))
    sheet = contact_sheet([("wide", quadrant_image), ("tall", tall)], panel_height=300)
    assert sheet.height == 300 + 34 + 24


def test_contact_sheet_rejects_an_empty_panel_list():
    with pytest.raises(ValueError, match="at least one panel"):
        contact_sheet([])


def test_inspection_sheet_shows_context_and_detail(quadrant_image, grid):
    zoomed = zoom_cells(quadrant_image, grid, ["C4"])
    sheet = inspection_sheet(quadrant_image, zoomed, ["C4"], panel_height=300)

    assert sheet.width > sheet.height  # two panels side by side
    assert sheet.height == 300 + 34 + 24


def test_locator_dims_outside_the_region_but_not_inside(quadrant_image, grid):
    box = grid.zoom_bounds(["A1"], margin_cells=0)
    marked = highlight_region(quadrant_image, box)

    inside = marked.getpixel((box.left + 20, box.top + 20))
    outside = marked.getpixel((700, 700))

    assert inside == (255, 0, 0), "the region under inspection must not be dimmed"
    assert sum(outside) < sum(quadrant_image.getpixel((700, 700))), "surroundings not dimmed"


def test_locator_outlines_the_region(quadrant_image, grid):
    box = grid.zoom_bounds(["D4"], margin_cells=1)
    marked = highlight_region(quadrant_image, box)
    assert marked.getpixel((box.center[0], box.top + 1)) == (255, 255, 255)


def test_locator_preserves_size(quadrant_image, grid):
    box = grid.zoom_bounds(["D4"], margin_cells=1)
    assert highlight_region(quadrant_image, box).size == quadrant_image.size


def test_inspection_sheet_marks_where_the_zoom_came_from(quadrant_image, grid):
    """Without the locator the model must guess how the panels correspond."""
    box = grid.zoom_bounds(["C4"], margin_cells=1)
    zoomed = zoom_cells(quadrant_image, grid, ["C4"])

    plain = inspection_sheet(quadrant_image, zoomed, ["C4"], panel_height=300)
    located = inspection_sheet(quadrant_image, zoomed, ["C4"], panel_height=300, locator=box)

    assert plain.size == located.size
    assert list(plain.get_flattened_data()) != list(located.get_flattened_data())


def test_inspection_sheet_captions_carry_the_cell_refs(quadrant_image, grid):
    """The caption bar must have drawn text, or the model cannot tell panels apart."""
    zoomed = zoom_cells(quadrant_image, grid, ["C4", "D4"])
    sheet = inspection_sheet(quadrant_image, zoomed, ["C4", "D4"], panel_height=200)

    caption_strip = sheet.crop((0, 0, sheet.width, 46))
    assert len(set(caption_strip.get_flattened_data())) > 1


# --- annotations ----------------------------------------------------------


def test_annotation_draws_inside_the_flagged_cell(flat_image, grid):
    cx, cy, radius = grid.circle_for(["C4"])
    marked = draw_annotations(flat_image, [Annotation(pin=1, cx=cx, cy=cy, radius=radius)])

    # The ring crosses the circle's horizontal extremity.
    assert marked.getpixel((cx + radius, cy)) != GREY


def test_annotation_preserves_image_size(flat_image, grid):
    cx, cy, radius = grid.circle_for(["C4"])
    marked = draw_annotations(flat_image, [Annotation(pin=1, cx=cx, cy=cy, radius=radius)])
    assert marked.size == flat_image.size


def test_annotation_leaves_the_circle_interior_untouched(flat_image, grid):
    """A filled circle would hide the defect the reviewer needs to see."""
    cx, cy, radius = grid.circle_for(["C4"])
    marked = draw_annotations(flat_image, [Annotation(pin=1, cx=cx, cy=cy, radius=radius)])
    assert marked.getpixel((cx, cy)) == GREY


@pytest.mark.parametrize("severity", list(Severity))
def test_ring_colour_matches_severity(flat_image, grid, severity):
    cx, cy, radius = grid.circle_for(["D5"])
    marked = draw_annotations(
        flat_image, [Annotation(pin=1, cx=cx, cy=cy, radius=radius, severity=severity)]
    )

    expected = SEVERITY_COLORS[severity]
    ring_strip = marked.crop((cx + radius - 4, cy - 2, cx + radius + 4, cy + 2))
    assert expected in set(ring_strip.get_flattened_data())


def test_every_severity_has_a_distinct_colour():
    assert len(set(SEVERITY_COLORS.values())) == len(Severity)


def test_multiple_annotations_all_render(flat_image, grid):
    annotations = []
    for pin, ref in enumerate(["B2", "E5", "G7"], start=1):
        cx, cy, radius = grid.circle_for([ref])
        annotations.append(Annotation(pin=pin, cx=cx, cy=cy, radius=radius))

    marked = draw_annotations(flat_image, annotations)
    for annotation in annotations:
        assert marked.getpixel((annotation.cx + annotation.radius, annotation.cy)) != GREY


# --- the self-correction nudge -------------------------------------------


def test_nudge_moves_the_circle():
    moved = Annotation(pin=1, cx=100, cy=100, radius=50).moved(dx=10, dy=-5, dr=8)
    assert (moved.cx, moved.cy, moved.radius) == (110, 95, 58)


def test_nudge_preserves_pin_and_severity():
    original = Annotation(pin=7, cx=100, cy=100, radius=50, severity=Severity.BLOCKER)
    moved = original.moved(dx=5, dy=5)
    assert moved.pin == 7
    assert moved.severity is Severity.BLOCKER


def test_nudge_cannot_shrink_the_circle_away():
    assert Annotation(pin=1, cx=100, cy=100, radius=10).moved(0, 0, dr=-999).radius == 4


def test_clamping_keeps_the_centre_on_canvas():
    clamped = Annotation(pin=1, cx=-40, cy=9000, radius=30).clamped(800, 800)
    assert (clamped.cx, clamped.cy) == (0, 800)


def test_clamping_leaves_a_valid_annotation_alone():
    annotation = Annotation(pin=1, cx=400, cy=400, radius=60)
    assert annotation.clamped(800, 800) == annotation


def test_a_nudged_annotation_still_renders(flat_image):
    """Whatever the self-check does, the result must be drawable."""
    annotation = Annotation(pin=1, cx=10, cy=10, radius=20).moved(-100, -100).clamped(800, 800)
    assert draw_annotations(flat_image, [annotation]).size == (800, 800)
