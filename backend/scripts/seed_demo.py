"""Run the app with a seeded demo project, no cloud and no model calls.

Useful for working on the review screen, and for showing the product when the
pipeline is not the thing being demonstrated.

    ALLOW_DEV_LOGIN=true uv run python -m scripts.seed_demo

Then sign in at http://localhost:5173 as owner@acme.com (or dee@acme.com to see
the reviewer's more limited controls).
"""

import asyncio
import sys

import uvicorn
from PIL import Image, ImageDraw

from app.api.deps import get_blobs, get_store
from app.api.main import app
from app.domain.entities import (
    Circle,
    Comment,
    DefectRecord,
    Guideline,
    ImageAsset,
    ImageStatus,
    Member,
    Project,
    Role,
    Run,
    RunStatus,
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
                circle_iterations=spec["iterations"],
                circle_verified=spec["verified"],
                status=spec["status"],
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

    print(f"seeded project {PROJECT_ID}: 1 image, {len(DEMO_DEFECTS)} defects")
    print("sign in as owner@acme.com (owner) or dee@acme.com (reviewer)")


async def main() -> int:
    from app.config import settings

    if not settings.dev_login_allowed:
        print("Set ALLOW_DEV_LOGIN=true (and no GCP config) to use the seeded demo.")
        return 1

    await seed()
    config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="info")
    await uvicorn.Server(config).serve()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
