"""Check the Re-checker against a real model, in both directions.

The dangerous failure mode is closing a defect that is still present, so this
asserts both that a genuine fix is recognised AND that an unfixed asset is not
waved through.

Uses a synthetic, unmistakable defect (a smeared text blob over the product) so the
check tests the Re-checker's judgement rather than its eyesight.

    uv run python -m scripts.check_recheck [clean_image.png]
"""

import asyncio
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from app.agents.pipeline import recheck_defect
from app.domain.grid import Grid
from app.imaging.canvas import font_for, load

DEFECT_COMMENT = (
    "The text overlaid on the product is garbled — the letterforms are smeared and "
    "unreadable."
)


def with_defect(image: Image.Image) -> tuple[Image.Image, list[str]]:
    """Paint an obvious artifact defect and return the cells it lands in."""
    damaged = image.convert("RGB").copy()
    grid = Grid.for_image(damaged.width, damaged.height)
    cells = ["D3", "E3"]
    box = grid.span_bounds(cells)

    draw = ImageDraw.Draw(damaged)
    draw.rectangle(box.as_tuple(), fill=(20, 18, 24))
    font = font_for(max(18, box.height // 4))
    # Deliberately mangled lettering, drawn overlapping itself.
    for offset, text in ((0, "RADIINCE"), (6, "RAOIANCF"), (11, "RADlANCE")):
        draw.text(
            (box.left + 8 + offset, box.center[1] - box.height // 5 + offset),
            text,
            font=font,
            fill=(228, 226, 220),
        )
    return damaged, cells


async def main(source: Path) -> int:
    clean = load(source)
    damaged, cells = with_defect(clean)

    print(f"source: {source.name} ({clean.width}x{clean.height}), defect at {cells}\n")

    print("case 1: defect -> clean  (should be resolved)")
    fixed = await recheck_defect(damaged, clean, cells, DEFECT_COMMENT)
    print(f"  resolved={fixed.resolved}  {fixed.reason}")

    print("\ncase 2: defect -> defect (must NOT be resolved)")
    unfixed = await recheck_defect(damaged, damaged, cells, DEFECT_COMMENT)
    print(f"  resolved={unfixed.resolved}  {unfixed.reason}")

    failures = []
    if not fixed.resolved:
        failures.append("a genuine fix was not recognised")
    if unfixed.resolved:
        failures.append("an unfixed defect was closed — the worst outcome available")

    if failures:
        for failure in failures:
            print(f"\nFAIL: {failure}")
        return 1

    print("\nRe-check check: PASS")
    return 0


if __name__ == "__main__":
    default = Path("../eval/images/clean_01.png")
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else default
    if not path.exists():
        print(f"no image at {path} — pass one as an argument")
        raise SystemExit(2)
    raise SystemExit(asyncio.run(main(path)))
