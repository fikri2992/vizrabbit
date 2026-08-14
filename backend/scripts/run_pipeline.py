"""Run the full pipeline over one image and print what each stage decided.

The quickest way to see the agents actually working, and to eyeball the annotated
output while iterating on prompts.

    uv run python -m scripts.run_pipeline path/to/image.png [--out DIR]
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

from app.agents import prompts
from app.agents.pipeline import process_image
from app.config import settings
from app.domain.grid import Grid
from app.imaging.annotate import draw_annotations
from app.imaging.canvas import load
from app.imaging.grid_overlay import apply_grid


async def main(image_path: Path, out_dir: Path) -> int:
    image = load(image_path)
    grid = Grid.for_image(image.width, image.height)
    guidelines = prompts.built_in_guideline()

    print(f"image : {image_path.name} ({image.width}x{image.height})")
    print(f"grid  : {grid.cols}x{grid.rows} = {grid.cell_count} cells")
    print(
        f"models: {settings.model_flash} / {settings.model_pro} "
        f"(gate <= {settings.max_pro_calls_per_run})\n"
    )

    async def progress(stage: str, detail: dict) -> None:
        print(f"  [{stage}] {detail}")

    started = time.monotonic()
    report = await process_image(image, guidelines, on_progress=progress, grid=grid)
    elapsed = time.monotonic() - started

    print(f"\n--- {len(report.defects)} defect(s) in {elapsed:.0f}s ---")
    for defect in report.defects:
        flag = "" if defect.circle_verified else "  [needs human review]"
        print(
            f"  #{defect.pin} [{defect.category.value}/{defect.severity.value}] "
            f"{', '.join(defect.cells)} rule={defect.rule_ref or '-'}{flag}"
        )
        print(f"      {defect.comment}")
        print(f"      circle verified after {defect.circle_iterations} iteration(s)")

    print(f"\n--- {len(report.dismissals)} dismissal(s) ---")
    for dismissal in report.dismissals:
        print(f"  [{dismissal.stage}] {', '.join(dismissal.cells)}: {dismissal.reason}")

    if report.pro_gate_reason:
        print(f"\npro gate: {report.pro_gate_reason}")

    out_dir.mkdir(parents=True, exist_ok=True)
    stem = image_path.stem
    apply_grid(image, grid).save(out_dir / f"{stem}_gridded.png")
    if report.defects:
        annotated = draw_annotations(image, [d.annotation for d in report.defects])
        annotated.save(out_dir / f"{stem}_annotated.png")
    print(f"\nwrote renders to {out_dir}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--out", type=Path, default=Path("../eval/output"))
    args = parser.parse_args()

    sys.exit(asyncio.run(main(args.image, args.out)))
