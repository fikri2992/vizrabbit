"""Check the ask-agent flow against a real model, in both directions.

A human draws a region and asks; the Inspector must confirm a real defect there
and decline to invent one on a clean region.

    uv run python -m scripts.check_ask_agent
"""

import asyncio
import sys
from pathlib import Path

from app.domain.annotations import Shape, ShapeKind
from app.domain.entities import ImageAsset, Member, Project, Role, ThreadAgentState, User
from app.imaging.canvas import load, to_png_bytes
from app.infra import repository as repo
from app.infra.events import EventBus
from app.infra.storage import LocalBlobStore
from app.infra.store import InMemoryStore
from app.services import threads as service

USER = User(id="u1", email="owner@acme.com", name="Ola")


def with_defect(image):
    """Paint unmistakably broken lettering — each glyph at its own drunken offset.

    check_recheck's overlaid-strings defect is too polite for this check: a legible
    top string over faint ghosts reads as intentional double-exposure typography,
    and the Inspector defensibly dismisses it. Here the letters must be wrong, not
    just layered.
    """
    import random

    from PIL import ImageDraw

    from app.domain.grid import Grid
    from app.imaging.canvas import font_for

    random.seed(7)
    damaged = image.convert("RGB").copy()
    grid = Grid.for_image(damaged.width, damaged.height)
    cells = ["D3", "E3"]
    box = grid.span_bounds(cells)

    draw = ImageDraw.Draw(damaged)
    draw.rectangle(box.as_tuple(), fill=(20, 18, 24))
    size = max(20, box.height // 4)
    font = font_for(size)

    x = box.left + 10
    for glyph in "RAD1AWCE":
        y = box.center[1] - size // 2 + random.randint(-size // 2, size // 2)
        draw.text((x, y), glyph, font=font, fill=(228, 226, 220))
        # Overstrike a second wrong glyph on some positions.
        if random.random() < 0.5:
            draw.text((x + 3, y + size // 3), random.choice("XKQZ"), font=font,
                      fill=(228, 226, 220))
        x += int(size * 0.55)
    return damaged, cells


async def main(source: Path) -> int:
    store, blobs, bus = InMemoryStore(), LocalBlobStore("./.blobs-check"), EventBus()
    project = Project(
        id="p1",
        name="check",
        members=[Member(user_id=USER.id, email=USER.email, role=Role.OWNER)],
    )
    await repo.save(store, project)

    clean = load(source)
    damaged, defect_cells = with_defect(clean)
    print(f"source: {source.name}, synthetic defect at {defect_cells}\n")

    image = ImageAsset(
        id="i1", project_id="p1", run_id="r1", filename=source.name,
        width=damaged.width, height=damaged.height,
    )
    image.original_path = await blobs.write("check/original.png", to_png_bytes(damaged))
    await repo.save(store, image)

    failures = []

    # Case 1: a rect drawn over the damaged region -> should confirm and file a defect.
    from app.domain.grid import Grid

    grid = Grid.for_image(damaged.width, damaged.height)
    box = grid.span_bounds(defect_cells)
    rect = Shape(
        kind=ShapeKind.RECT,
        points=[box.left, box.top, box.width, box.height],
        color="#E24B4A",
    )
    thread, _ = await service.create_thread(
        store, project, image, USER, "This text looks garbled to me — is it?", [rect]
    )
    await service.ask_agent(store, blobs, bus, project, image, thread, USER, "Garbled text?")
    thread = await repo.load(store, type(thread), thread.id)
    replies = await repo.comments_for_defect(store, thread.id)
    print(f"case 1 (defect region): state={thread.agent_state} defect={bool(thread.defect_id)}")
    print(f"  agent: {replies[-1].body[:120]}")
    if thread.agent_state is not ThreadAgentState.ANSWERED or not thread.defect_id:
        failures.append("a drawn region over a real defect was not confirmed")
    else:
        defect = (await repo.defects_for_image(store, image.id))[0]
        if defect.pin != thread.pin:
            failures.append(f"defect pin {defect.pin} != thread pin {thread.pin}")

    # Case 2: a circle on clean background -> must not invent a defect.
    clean_circle = Shape(kind=ShapeKind.CIRCLE, points=[80, 80, 60], color="#378ADD")
    thread2, _ = await service.create_thread(
        store, project, image, USER, "Anything wrong in this corner?", [clean_circle]
    )
    await service.ask_agent(store, blobs, bus, project, image, thread2, USER, "Anything wrong?")
    thread2 = await repo.load(store, type(thread2), thread2.id)
    replies2 = await repo.comments_for_defect(store, thread2.id)
    print(f"\ncase 2 (clean region): state={thread2.agent_state} defect={bool(thread2.defect_id)}")
    print(f"  agent: {replies2[-1].body[:120]}")
    if thread2.defect_id:
        failures.append("the agent invented a defect on a clean region")

    if failures:
        for failure in failures:
            print(f"\nFAIL: {failure}")
        return 1
    print("\nAsk-agent check: PASS")
    return 0


if __name__ == "__main__":
    default = Path("../eval/images/clean_01.png")
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else default
    if not path.exists():
        print(f"no image at {path}")
        raise SystemExit(2)
    raise SystemExit(asyncio.run(main(path)))
