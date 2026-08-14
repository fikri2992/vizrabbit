# Labelling worklist

What the benchmark needs to become decidable. Everything here is careful looking, not
coding.

## Why this matters

The first run scored precision **0.50** and a recall lift of **+8.3 points**, missing two
Gate 1 thresholds. Neither number is currently about the pipeline:

- **Precision is a lower bound.** Only the headline defect in each image is labelled, so
  every *other* real defect the pipeline finds counts against it. Verified: on
  `defective_12_white_hatchback` it flagged malformed wheel-rim spokes and melted
  windshield wipers — both real, both unlabelled, both scored as false positives.
- **The lift is underpowered.** With 12 labelled defects, one defect is worth 8.3 recall
  points. "+8.3" means the pipeline found exactly one more defect than the baseline.

**Target: ≥ 40 labelled defects.** At that size one defect is worth under 2.5 points and
precision becomes a real measurement rather than a floor.

## The rule that matters most

**Label every defect you can see in an image, not just the obvious one.** A partially
labelled image is worse than an unlabelled one, because it actively penalises correct
findings. If you only have time to do some images, do fewer images *exhaustively* rather
than all of them partially — and delete the partial ones from `labels.json`.

Equally: **label only what you can actually see.** Not what the prompt asked for, not what
the Commons description claims. If you cannot point at it, it is not a defect. The
descriptions below are hints about where to look, nothing more.

## How to get cell refs

Render a gridded copy and read the labels off it:

```bash
cd backend && uv run python -c "from pathlib import Path; from app.imaging.canvas import load, fit_for_model; from app.imaging.grid_overlay import apply_grid; p=Path('../eval/images/defective/NAME.png'); apply_grid(fit_for_model(load(p), max_edge=1100)).save('../eval/output/grid.png')"
```

Grid dimensions adapt to aspect ratio, so a 16:9 image is 11×6 and a square one 8×8. Use
the labels drawn on the render, not a fixed assumption. Matching tolerates being one cell
out, so name the cell the defect is centred on rather than agonising over boundaries.

## Format

Add to `eval/labels.json`. Paths are relative to `eval/images/`.

```json
{
  "image": "defective/defective_02_horse_riding_astronaut.png",
  "defects": [
    {
      "cells": ["D4"],
      "category": "anatomy",
      "rule": "ANAT-02",
      "note": "What you can see, in one sentence."
    }
  ]
}
```

- `category` — `anatomy` · `physics` · `artifact` · `brand` · `memory`
- `rule` — the built-in rule id from `backend/app/agents/prompts/built_in_guideline.md`
  (`ANAT-01`…`ANAT-05`, `PHYS-01`…`PHYS-06`, `ARTF-01`…`ARTF-06`). Optional but useful.
- `cells` — one or two cells is ideal. Only list more when the defect genuinely spans them.

## Already done (6 images, 12 defects)

`01_ai_generated_hand` · `11_guinea_pig_writer` · `12_white_hatchback` ·
`16_godzilla_court` · `18_wikipedia_vase` · `20_leerparadijs_education`

These were labelled with the headline defects only. **They are worth a second pass** to
add the ones that were skipped — `12_white_hatchback` in particular is missing the wheel
rim and windshield wipers.

## Remaining (14 images)

Hints are from the Wikimedia descriptions in `defective-image-sources.md`. Confirm each
one visually before writing it down; ignore any you cannot see.

| Image | Look for | Likely category |
|---|---|---|
| `02_horse_riding_astronaut` | Horse and suit fuse into one body; hooves, suit seams, contact shadows | anatomy, physics |
| `03_ai_sauna` | Arms/legs/hands attached to wrong bodies or disconnected; distorted deck objects and boats | anatomy |
| `04_listenbourg_grid` | Warped windows, towers, rooflines; fake glyphs on signage; repeated facade textures | artifact |
| `05_boanthropy` | Human and cow bodies merge; cow legs, human fingers, cloth boundaries | anatomy |
| `06_gorilla_rifle` | Rifle, forearms and hands fuse into an impossible grip; eye/visor, toes, shadows | anatomy, physics |
| `07_emperor_giant_book` | Book and page geometry structurally impossible; missing writing hand/pen; blurred face | artifact, anatomy |
| `08_penang_street` | Utility wires break, warp and terminate mid-air; buildings melt into each other | physics, artifact |
| `09_educationtechnology` | Duplicated/deformed people and limbs; malformed screen UI, cables, background faces | anatomy, artifact |
| `10_indian_tailor` | Measuring tape duplicates, intersects the body, wraps impossibly; hand contact | physics |
| `13_crossword_globe` | Letter tiles spell gibberish; puzzle pieces interlock impossibly across curvature | artifact |
| `14_wikipedia_logo` | Malformed lettering; incompatible puzzle geometry; robot hand/arm attachment | artifact, anatomy |
| `15_ubik_advertisement` | Spray exits the wrong part of the can; duplicate nozzles; floating cap; warped text | physics, artifact |
| `17_underwater_teddy_research` | Paws merge into equipment; screens, cords, bubbles, underwater lighting | anatomy, physics |
| `19_leerparadijs_hackathon` | Raised arms and fists disconnected or attached to wrong bodies; background hands, faces, laptops | anatomy |

## Also useful, lower priority

**More clean images.** There are only 4, so the false-positive rate resolves in steps of
0.25. Ten would make it meaningful. They must be genuinely clean *and* genuinely
AI-generated — photographs would let the pipeline pass by detecting "is this AI" rather
than "is this wrong". `scripts/generate_eval_images.py` produces suitable candidates; its
`clean_*` prompts came out clean on inspection.

**A brand guideline with matching imagery.** Nothing currently exercises the `brand`
category end to end: a short real guideline plus a handful of images that violate it
(wrong logo colour, logo too small, off-palette) would cover the part of the product that
is actually the commercial pitch.

## Re-running

```bash
cd backend && uv run python -m app.eval.run
```

Exits non-zero if any Gate 1 threshold fails. The report writes to
`eval/output/benchmark.md` and states its own caveats about label completeness and sample
size.
