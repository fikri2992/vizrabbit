"""Run the synthetic brand-palette benchmark (Gate 7).

    uv run python -m scripts.check_palette_eval --mechanical
    uv run python -m scripts.check_palette_eval            # full pipeline, needs a model

``--mechanical`` scores the measurement layer alone: no model calls, no cost, and
it answers "does the instrument find the planted element". The full run scores
the pipeline's judgement — whether the Inspector keeps designed violations and
throws out photographic colour.

Gate 7 thresholds apply to the full run: recall ≥ 0.8 on the violating set and
≤ 1 false positive across the clean set.
"""

import argparse
import asyncio
import sys

from app.domain.brand import PaletteOffence
from app.domain.taxonomy import Category
from app.eval.palette import Case, dataset, profile, run_mechanical, score

RECALL_TARGET = 0.8
FALSE_POSITIVE_BUDGET = 1


async def run_full(cases: list[Case]) -> list[tuple[Case, list[PaletteOffence]]]:
    """Score confirmed BRAND-* defects from the real pipeline."""
    from app.agents.pipeline import ProBudget, process_image
    from app.domain.brand import PaletteOffence as Offence

    brand = profile()
    budget = ProBudget(limit=0)  # the Pro gate is not what is being measured here
    results = []

    for case in cases:
        report = await process_image(
            case.image, guidelines="", budget=budget, grid=case.grid, profile=brand
        )
        # Re-express confirmed brand defects as offences so both modes score alike.
        found = [
            Offence(
                cells=defect.cells,
                hex="",
                coverage=0.0,
                nearest_hex="",
                delta_e=0.0,
                tolerance=0.0,
            )
            for defect in report.defects
            if defect.category is Category.BRAND
        ]
        print(f"  {case.name}: {len(found)} brand defect(s)", flush=True)
        results.append((case, found))

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mechanical",
        action="store_true",
        help="score the measurement layer only, without calling a model",
    )
    parser.add_argument("--violating", type=int, default=10)
    parser.add_argument("--clean", type=int, default=10)
    args = parser.parse_args()

    cases = dataset(args.violating, args.clean)
    print(f"{len(cases)} synthetic cases: {args.violating} violating, {args.clean} clean\n")

    results = run_mechanical(cases) if args.mechanical else asyncio.run(run_full(cases))

    result = score(results)
    print()
    print(result.as_table())

    if args.mechanical:
        print(
            "\nMechanical mode: a false positive here is expected and correct — the "
            "photographic blob is genuinely off-palette. Only the full run's false "
            "positives count against Gate 7."
        )
        return 0

    ok = result.recall >= RECALL_TARGET and result.false_positives <= FALSE_POSITIVE_BUDGET
    print(
        f"\nGate 7: recall ≥ {RECALL_TARGET} and ≤ {FALSE_POSITIVE_BUDGET} false positive(s) "
        f"— {'PASS' if ok else 'FAIL'}"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
