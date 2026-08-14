# Eval set

The benchmark that decides Gate 1. It answers the only question that matters about
this project: **does the multi-agent pipeline actually beat a naive single prompt?**

Harness code lives in `backend/app/eval/`; this directory holds the data.

## Layout

```
eval/
  images/        # the eval images (git-ignored — keep them out of the repo)
  labels.json    # ground truth, committed
  output/        # benchmark.md + benchmark.json (git-ignored)
```

## Building the set

Target composition, per `docs/implementation-plan.md`:

| | Count | Why |
| --- | --- | --- |
| Images with known defects | ≥20 | Measures recall |
| Clean images | ≥10 | Measures the false-positive rate |
| **Total** | **30** | |

Cover all four built-in categories — `anatomy`, `physics`, `artifact` — plus `brand`
once a project guideline is attached. Anatomy defects (hands, faces) should be the
largest group because they are the most common real failure and the most embarrassing
to publish.

### Sourcing defective images is the hard part

**Tried and rejected: generating flawed images with a current top-tier model.**
`scripts/generate_eval_images.py` produces candidates with `gemini-3.1-flash-image`,
using prompts chosen to stress hands, overlapping limbs, text and reflections. On
inspection the output was essentially clean — a four-person toast with eight hands and
overlapping glassware had correct digit counts, and a wine bottle label read
"CHÂTEAU LUNA" crisply under 3× zoom. The generator is too good to be a reliable
source of defects.

Labelling those images as defective anyway — on the strength of what the prompt asked
for rather than what is visible — would corrupt the benchmark in precisely the
direction that flatters the pipeline. Don't.

Where the defects actually have to come from:

- **Older or weaker generators.** SD 1.5, early SDXL, older Midjourney versions, or
  any model at low step counts. This is the most reliable supply.
- **Real AI slop from the wild** — the actual target domain, and the most defensible
  source for a demo.
- **Deliberate corruption** of clean generations (warp a hand region, splice a limb).
  Cheap and controllable, but visibly synthetic; use sparingly and never as the whole
  defective set.

Clean images must be genuinely clean and genuinely AI-generated — using photographs as
the clean set would let the pipeline pass by detecting "is this AI" rather than "is
this wrong". The `clean_*` candidates from the generator are fine for this half.

### Label what you see, not what you asked for

Open each image, zoom in, and write down only defects you can actually point at. The
`--out` renders from `scripts/run_pipeline.py` and a gridded copy make this quick:

```bash
cd backend && uv run python -m scripts.run_pipeline ../eval/images/x.png
```

**Label honestly.** A defect you cannot see at full resolution should not be in the
labels, and neither should style you happen to dislike. An eval set that rewards
over-flagging will send the pipeline in the wrong direction for the whole build.

## Label format

Cells are grid refs against the deterministic grid the pipeline derives from the
image's dimensions (roughly 8×8, adapted to aspect ratio). Load the image, print
`Grid.for_image(w, h)`, and read the cell off a gridded render:

```bash
cd backend
uv run python -c "from app.imaging.canvas import load; from app.imaging.grid_overlay import apply_grid; im = load('../eval/images/hands_01.png'); apply_grid(im).save('../eval/output/hands_01_grid.png')"
```

```json
[
  {
    "image": "hands_01.png",
    "defects": [
      { "cells": ["C4", "D4"], "category": "anatomy", "rule": "ANAT-01", "note": "six fingers on the left hand" }
    ]
  },
  { "image": "clean_01.png", "defects": [] }
]
```

Matching tolerates being one cell off, so label the cell the defect is centred on
rather than agonising over boundaries.

## Running the benchmark

```bash
cd backend && uv run python -m app.eval.run
```

Exits non-zero if any Gate 1 threshold fails, so it can gate a merge. Writes
`eval/output/benchmark.md` — the table that goes in the README and the demo video.

Re-run the full set before merging any prompt change. A 5-image subset is fine while
iterating; only the full set counts as a Gate 1 result.
