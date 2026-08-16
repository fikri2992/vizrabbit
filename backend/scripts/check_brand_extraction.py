"""Read a real brand guideline PDF and report the palette proposed (Gate 7).

    uv run python -m scripts.check_brand_extraction path/to/guideline.pdf

Gate 7 asks for ≥ 3 hexes including at least one read from a swatch graphic
rather than from printed text — that last one is the case a text-only reader
misses, and the reason pages are rendered and looked at.

Nothing is written and nothing is confirmed: this prints a proposal. Only the
Owner, through the confirmation form, can make a palette enforceable.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from app.imaging.documents import MAX_PAGES, NotAPdf, page_count
from app.services.guidelines import as_entries, extract_palette

MIN_HEXES = 3


async def run(path: Path) -> int:
    data = path.read_bytes()
    try:
        pages = page_count(data)
    except NotAPdf as exc:
        print(f"error: {exc}")
        return 2

    print(f"{path.name}: {pages} page(s), reading the first {min(pages, MAX_PAGES)}\n")
    extraction = await extract_palette(pdf=data, name=path.stem)

    if not extraction.colours:
        print("No palette proposed.")
        if extraction.notes:
            print(f"notes: {extraction.notes}")
        return 1

    print(f"{len(extraction.colours)} colour(s) proposed:\n")
    for colour in extraction.colours:
        role = f"  {colour.role}" if colour.role else ""
        note = f"  — {colour.note}" if colour.note else ""
        print(f"  {colour.hex:<9} [{colour.read_from}]{role}{note}")

    if extraction.questions:
        print(f"\n{len(extraction.questions)} question(s) for the Brand Owner:\n")
        for question in extraction.questions:
            print(f"  - {question.question}")

    entries = as_entries(extraction)
    from_swatch = [c for c in extraction.colours if c.read_from == "swatch"]

    print("\n--- Gate 7 ---")
    print(f"parseable hexes            {len(entries)}  (need ≥ {MIN_HEXES})")
    print(f"read from a swatch graphic {len(from_swatch)}  (need ≥ 1)")

    ok = len(entries) >= MIN_HEXES and len(from_swatch) >= 1
    print(f"\n{'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="a real brand guideline PDF")
    args = parser.parse_args()

    if not args.pdf.exists():
        print(f"error: {args.pdf} does not exist")
        return 2
    return asyncio.run(run(args.pdf))


if __name__ == "__main__":
    sys.exit(main())
