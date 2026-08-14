"""Zoom crops — the resolution the Scanner never had.

A suspect cell is cropped with a margin of whole cells around it and upscaled,
so the Inspector sees the defect large enough to confirm or dismiss it.
"""

from PIL import Image

from app.config import settings
from app.domain.grid import Box, Grid


def crop_box(image: Image.Image, box: Box) -> Image.Image:
    return image.crop(box.as_tuple())


def zoom_cells(
    image: Image.Image,
    grid: Grid,
    refs: list[str],
    margin_cells: int | None = None,
    upscale: int | None = None,
) -> Image.Image:
    """Crop the flagged cells plus margin, then upscale for the Inspector."""
    margin = settings.zoom_margin_cells if margin_cells is None else margin_cells
    factor = settings.zoom_upscale if upscale is None else upscale

    box = grid.zoom_bounds(refs, margin_cells=margin)
    crop = crop_box(image, box)
    if factor <= 1:
        return crop
    return crop.resize((crop.width * factor, crop.height * factor), Image.LANCZOS)
