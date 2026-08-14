"""The naive baseline the pipeline must beat.

One model call, the same model, the same guidelines, the same gridded image — the
thing any competent developer would build in an afternoon. If the pipeline cannot
beat this, the pipeline is not worth its latency and cost, and we would rather
find that out in week one than on stage.

Deliberately fair: the baseline sees exactly the information the Scanner sees. What
it does not get is the zoom pass, the self-check, or the Pro gate.
"""

from google.adk.agents import LlmAgent
from PIL import Image

from app.agents.runtime import bytes_part, run_agent
from app.agents.schemas import ScanResult, validate_against_grid
from app.config import settings
from app.domain.grid import Grid
from app.imaging.canvas import fit_for_model, to_png_bytes
from app.imaging.grid_overlay import apply_grid

BASELINE_INSTRUCTION = """
You are a visual QA reviewer for AI-generated commercial imagery.

You receive an image and the same image with a labelled grid over it (cells are
labelled in their top-left corner, `A1` at the top-left).

Report every defect you can find. For each one give the grid cells it occupies, its
category, what is wrong, the guideline rule id if one applies, and your confidence.

Report real defects only — not stylisation, artistic lighting, shallow depth of field
or motion blur.

Respond ONLY with JSON matching the schema.
""".strip()


def baseline_agent(guidelines: str) -> LlmAgent:
    return LlmAgent(
        model=settings.model_flash,
        name="baseline",
        description="Single-pass defect detection, no verification.",
        instruction=f"{BASELINE_INSTRUCTION}\n\n# Active guidelines\n\n{guidelines}",
        output_schema=ScanResult,
        output_key="scan",
    )


async def run_baseline(image: Image.Image, guidelines: str, grid: Grid | None = None) -> ScanResult:
    grid = grid or Grid.for_image(image.width, image.height)
    gridded = apply_grid(image, grid)

    result = await run_agent(
        baseline_agent(guidelines),
        prompt=(
            "Image 1 is the original, image 2 has the labelled grid. "
            f"The grid is {grid.cols} columns by {grid.rows} rows. "
            "List every defect you find."
        ),
        images=[
            bytes_part(to_png_bytes(fit_for_model(image))),
            bytes_part(to_png_bytes(fit_for_model(gridded))),
        ],
        schema=ScanResult,
    )

    result.suspects = [
        suspect.model_copy(update={"cells": valid})
        for suspect in result.suspects
        if (valid := validate_against_grid(suspect.cells, grid))
    ]
    return result
