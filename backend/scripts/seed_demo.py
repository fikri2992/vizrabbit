"""Run the app with a seeded demo project, no cloud and no model calls.

Useful for working on the review screen, and for showing the product when the
pipeline is not the thing being demonstrated.

    ALLOW_DEV_LOGIN=true uv run python -m scripts.seed_demo

Then sign in at http://localhost:5173 as owner@acme.com (or dee@acme.com to see
the reviewer's more limited controls).
"""

import asyncio
import os
import sys

import uvicorn
from PIL import Image, ImageDraw

from app.api.deps import get_blobs, get_store
from app.api.main import app
from app.domain.entities import (
    Circle,
    Comment,
    DefectRecord,
    DismissalRecord,
    Guideline,
    ImageAsset,
    ImageStatus,
    Member,
    Project,
    Region,
    Role,
    Run,
    RunStatus,
    now,
)
from app.domain.grid import Grid
from app.domain.lifecycle import DefectState
from app.domain.taxonomy import Category, Severity
from app.imaging.annotate import Annotation, draw_annotations
from app.imaging.canvas import to_png_bytes
from app.imaging.grid_overlay import apply_grid
from app.infra import repository as repo
from app.infra.storage import ANNOTATED, GRIDDED, ORIGINAL, blob_path

PROJECT_ID = "demo"
OWNER_ID = "dev:owner@acme.com"
DESIGNER_ID = "dev:dee@acme.com"


def mock_asset(width=1200, height=1200) -> Image.Image:
    """A stand-in for a generated product shot: gradient, product, model, packaging."""
    image = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        t = y / height
        draw.line(
            [(0, y), (width, y)],
            fill=(int(238 - 120 * t), int(228 - 90 * t), int(214 - 40 * t)),
        )
    draw.ellipse([690, 130, 1110, 550], fill=(252, 250, 246))  # product
    draw.rounded_rectangle([110, 700, 520, 1120], 24, fill=(28, 30, 42))  # packaging
    draw.ellipse([200, 210, 470, 480], fill=(206, 62, 78))  # model's hand
    draw.rectangle([560, 620, 900, 690], fill=(60, 55, 50))  # strapline
    return image


DEMO_DEFECTS = [
    {
        "cells": ["C4"],
        "category": Category.ANATOMY,
        "severity": Severity.BLOCKER,
        "comment": "The model's left hand has six fingers; the extra digit sits between the "
        "ring and little finger.",
        "rule_ref": "ANAT-01",
        "status": DefectState.OPEN,
        "verified": True,
        "iterations": 2,
    },
    {
        "cells": ["G3"],
        "category": Category.ARTIFACT,
        "severity": Severity.WARNING,
        "comment": "The product's embossed logo warps along its lower edge and the lettering "
        "loses shape.",
        "rule_ref": "ARTF-06",
        "status": DefectState.OPEN,
        "verified": True,
        "iterations": 1,
    },
    {
        "cells": ["E5"],
        "category": Category.ARTIFACT,
        "severity": Severity.NITPICK,
        "comment": "Strapline text is illegible — the letterforms dissolve toward the right.",
        "rule_ref": "ARTF-01",
        "status": DefectState.NEEDS_HUMAN_REVIEW,
        "verified": False,
        "iterations": 3,
    },
    {
        "cells": ["F5"],
        "category": Category.BRAND,
        "severity": Severity.WARNING,
        # The ΔE quoted here is the real measurement of the strapline block
        # mock_asset draws (#3c3732) against the seeded ink (#1c1e2a).
        "comment": "The strapline panel is not a brand colour. Measured #3c3732 against the "
        "confirmed palette: ΔE2000 13.4 from the nearest brand colour #1c1e2a (ink), "
        "which allows 4.0.",
        "rule_ref": "BRAND-PALETTE",
        # A question, not a flag (decision 19 glossary): the review screen shows
        # the two swatches and answering "not a problem" widens the tolerance.
        "status": DefectState.NEEDS_HUMAN_REVIEW,
        "verified": True,
        "iterations": 1,
    },
    {
        "cells": ["B7"],
        "category": Category.PHYSICS,
        "severity": Severity.WARNING,
        "comment": "The packaging casts no shadow despite sitting on the surface.",
        "rule_ref": "PHYS-04",
        "status": DefectState.VERIFIED_RESOLVED,
        "verified": True,
        "iterations": 1,
    },
]


DEMO_DISMISSALS = [
    (
        ["A2", "B2"],
        "Possible warping along the upper background gradient",
        "The gradient is smooth and continuous; the banding is normal compression, not a defect.",
    ),
    (
        ["G6", "H6"],
        "Shadow under the product may be missing",
        "A soft contact shadow is present and consistent with the key light from the upper left.",
    ),
    (
        ["D2"],
        "Edge of the packaging looked melted",
        "At 2x the corner radius is clean and the seam runs unbroken; the softness is "
        "depth of field.",
    ),
]


async def seed() -> None:
    store, blobs = get_store(), get_blobs()

    await repo.save(
        store,
        Project(
            id=PROJECT_ID,
            name="Autumn campaign",
            members=[
                Member(user_id=OWNER_ID, email="owner@acme.com", name="Ola Owner", role=Role.OWNER),
                Member(
                    user_id=DESIGNER_ID,
                    email="dee@acme.com",
                    name="Dee Designer",
                    role=Role.REVIEWER,
                ),
            ],
        ),
    )

    await repo.save(
        store,
        Guideline(
            id="g-demo",
            project_id=PROJECT_ID,
            name="Acme brand guideline",
            raw_text=(
                "The product must be the visual focus. Logo must never be distorted, "
                "recoloured or partially covered. Straplines must be legible at thumbnail "
                "size. Skin tones must be represented naturally and consistently."
            ),
        ),
    )

    run = Run(
        id="r-demo",
        project_id=PROJECT_ID,
        started_by=OWNER_ID,
        status=RunStatus.DONE,
        image_ids=["i-demo"],
    )
    await repo.save(store, run)

    image = mock_asset()
    grid = Grid.for_image(image.width, image.height)

    annotations = []
    for pin, spec in enumerate(DEMO_DEFECTS, start=1):
        cx, cy, radius = grid.circle_for(spec["cells"])
        annotations.append(
            Annotation(pin=pin, cx=cx, cy=cy, radius=radius, severity=spec["severity"])
        )

    asset = ImageAsset(
        id="i-demo",
        project_id=PROJECT_ID,
        run_id=run.id,
        filename="autumn_hero_01.png",
        width=image.width,
        height=image.height,
        status=ImageStatus.DONE,
    )
    asset.original_path = await blobs.write(
        blob_path(PROJECT_ID, asset.id, ORIGINAL), to_png_bytes(image)
    )
    asset.gridded_path = await blobs.write(
        blob_path(PROJECT_ID, asset.id, GRIDDED), to_png_bytes(apply_grid(image, grid))
    )
    asset.annotated_path = await blobs.write(
        blob_path(PROJECT_ID, asset.id, ANNOTATED),
        to_png_bytes(draw_annotations(image, annotations)),
    )
    await repo.save(store, asset)

    for pin, (spec, annotation) in enumerate(zip(DEMO_DEFECTS, annotations, strict=True), start=1):
        span = grid.span_bounds(spec["cells"])
        await repo.save(
            store,
            DefectRecord(
                id=f"d-{pin}",
                project_id=PROJECT_ID,
                image_id=asset.id,
                pin=pin,
                cells=spec["cells"],
                category=spec["category"],
                severity=spec["severity"],
                comment=spec["comment"],
                rule_ref=spec["rule_ref"],
                circle=Circle(cx=annotation.cx, cy=annotation.cy, radius=annotation.radius),
                region=Region(
                    left=span.left, top=span.top, width=span.width, height=span.height
                ),
                circle_iterations=spec["iterations"],
                circle_verified=spec["verified"],
                status=spec["status"],
            ),
        )

    # What the Scanner flagged and the Inspector threw out. Shown in the review
    # screen, because "it considered this and rejected it" is the evidence that the
    # agent is calibrated rather than merely confident.
    for index, (cells, hypothesis, reason) in enumerate(DEMO_DISMISSALS, start=1):
        await repo.save(
            store,
            DismissalRecord(
                id=f"x-{index}",
                project_id=PROJECT_ID,
                image_id=asset.id,
                cells=cells,
                hypothesis=hypothesis,
                reason=reason,
                stage="inspector",
            ),
        )

    await repo.save(
        store,
        Comment(
            id="c-1",
            project_id=PROJECT_ID,
            defect_id="d-1",
            author_id=DESIGNER_ID,
            author_name="Dee Designer",
            body="Regenerating this one with a tighter hand prompt.",
        ),
    )

    await seed_brand_profile(store)
    variants = await seed_variant_slot(store, blobs)
    await seed_agent_draft(store, blobs, asset)

    print(f"seeded project {PROJECT_ID}: 1 legacy image, {len(DEMO_DEFECTS)} defects")
    print(f"plus 1 slot with {variants} competing variants (one approved, one with a v2 fix)")
    print("plus an agent-drafted fix on the legacy image (decision 21)")
    print("sign in as owner@acme.com (owner) or dee@acme.com (reviewer)")


async def seed_agent_draft(store, blobs, original: ImageAsset) -> None:
    """A clean agent draft superseding the legacy image — decision 21 on screen.

    What the drafting pass would have produced: authored by the agent, recheck
    passed (no open defects), so the stance recommends it and discard is live.
    """
    from app.services.drafts import AGENT_USER_ID

    image = mock_asset()
    grid = Grid.for_image(image.width, image.height)
    draft = ImageAsset(
        id="i-demo-draft",
        project_id=PROJECT_ID,
        run_id=original.run_id,
        filename=original.filename,
        slot_id=original.slot_id,
        variant=original.variant,
        version=original.version + 1,
        uploaded_by=AGENT_USER_ID,
        supersedes_id=original.id,
        width=image.width,
        height=image.height,
        status=ImageStatus.DONE,
    )
    draft.original_path = await blobs.write(
        blob_path(PROJECT_ID, draft.id, ORIGINAL), to_png_bytes(image)
    )
    draft.gridded_path = await blobs.write(
        blob_path(PROJECT_ID, draft.id, GRIDDED), to_png_bytes(apply_grid(image, grid))
    )
    await repo.save(store, draft)


#: The palette the demo brand actually uses, matching mock_asset's colours.
DEMO_PALETTE = [
    ("#eee4d6", "paper", 4.0),
    ("#1c1e2a", "ink", 4.0),
    ("#fcfaf6", "product", 4.0),
    ("#ce3e4e", "primary", 3.0),
]


async def seed_brand_profile(store) -> None:
    """A confirmed palette, so the demo shows brand defects rather than the empty state.

    Confirmed by the owner on purpose: an unconfirmed profile raises nothing, which
    is correct behaviour but a poor demo of it.
    """
    from app.domain.entities import BrandProfile, PaletteEntry
    from app.services.brand import profile_id

    await repo.save(
        store,
        BrandProfile(
            id=profile_id(PROJECT_ID),
            project_id=PROJECT_ID,
            entries=[
                PaletteEntry(hex=hex_value, role=role, tolerance=tolerance)
                for hex_value, role, tolerance in DEMO_PALETTE
            ],
            source="Acme brand guideline.pdf",
            confirmed_by=OWNER_ID,
            confirmed_at=now(),
        ),
    )


async def seed_variant_slot(store, blobs) -> int:
    """One slot, three competing variants — the shape the history tree draws.

    Variant 1 loses on an open defect, variant 2 wins after a v2 fix, variant 3 is
    clean but was never picked. That last one matters: it is the case where
    "archived" must read as *superseded*, not as *rejected*.
    """
    from datetime import UTC, datetime, timedelta

    from app.domain.entities import Slot

    base = datetime.now(UTC) - timedelta(hours=6)
    slot = Slot(id="s-hero", project_id=PROJECT_ID, name="Hero banner", created_at=base)
    await repo.save(store, slot)

    run = Run(
        id="r-variants", project_id=PROJECT_ID, started_by=OWNER_ID, status=RunStatus.DONE
    )
    specs = [
        # (id, variant, version, supersedes, uploader, minutes, approved, open defect)
        ("v1-a", 1, 1, None, DESIGNER_ID, 0, False, True),
        ("v2-a", 2, 1, None, DESIGNER_ID, 4, False, True),
        ("v2-b", 2, 2, "v2-a", OWNER_ID, 95, True, False),
        ("v3-a", 3, 1, None, OWNER_ID, 7, False, False),
    ]

    for index, spec in enumerate(specs):
        asset_id, variant, version, parent, uploader, minutes, approved, flawed = spec
        picture = mock_asset(900, 900)
        grid = Grid.for_image(picture.width, picture.height)
        asset = ImageAsset(
            id=asset_id,
            project_id=PROJECT_ID,
            run_id=run.id,
            filename=f"hero_v{variant}{'' if version == 1 else f'_fix{version}'}.png",
            slot_id=slot.id,
            variant=variant,
            version=version,
            uploaded_by=uploader,
            supersedes_id=parent,
            width=picture.width,
            height=picture.height,
            status=ImageStatus.DONE,
            approved_by=OWNER_ID if approved else None,
            approved_at=base + timedelta(minutes=minutes) if approved else None,
            created_at=base + timedelta(minutes=minutes),
        )
        asset.original_path = await blobs.write(
            blob_path(PROJECT_ID, asset.id, ORIGINAL), to_png_bytes(picture)
        )
        await repo.save(store, asset)
        run.image_ids.append(asset.id)

        if flawed:
            cx, cy, radius = grid.circle_for(["D4"])
            span = grid.span_bounds(["D4"])
            await repo.save(
                store,
                DefectRecord(
                    id=f"dv-{index}",
                    project_id=PROJECT_ID,
                    image_id=asset.id,
                    pin=1,
                    cells=["D4"],
                    category=Category.ARTIFACT,
                    severity=Severity.WARNING,
                    comment="The strapline overlaps the product edge and loses contrast.",
                    rule_ref="ARTF-01",
                    circle=Circle(cx=cx, cy=cy, radius=radius),
                    region=Region(
                        left=span.left, top=span.top, width=span.width, height=span.height
                    ),
                    status=DefectState.OPEN,
                ),
            )

    await repo.save(store, run)
    return 3


async def main() -> int:
    from app.config import settings

    if not settings.dev_login_allowed:
        print("Set ALLOW_DEV_LOGIN=true (and no GCP config) to use the seeded demo.")
        return 1

    await seed()
    port = int(os.environ.get("PORT", "8000"))
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="info")
    await uvicorn.Server(config).serve()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
