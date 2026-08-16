"""Approved export (phase 8): the zip that closes the dead end.

Approval used to be a terminal screen state — the asset was blessed and then
lived in the app forever. This turns completion into a deliverable: the latest
approved version of every complete slot's winning variant, clean originals
only, never an annotated render.
"""

import io
import re
import zipfile

from app.domain.entities import ImageAsset
from app.infra import repository as repo
from app.infra.storage import BlobStore
from app.infra.store import Store
from app.services import slots as slot_service


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^\w\- ]+", "", name).strip().replace(" ", "_")
    return cleaned or "asset"


async def approved_assets(store: Store, project_id: str) -> list[tuple[str, ImageAsset]]:
    """(zip filename, asset) for every complete slot — the winner's approved version.

    Filenames are unique by construction: slot name + version, with an ordinal
    suffix when two slots share a name.
    """
    groups = await slot_service.project_slots(store, project_id)
    names = {slot.id: slot.name for slot in await repo.slots_for_project(store, project_id)}

    chosen: list[tuple[str, ImageAsset]] = []
    used: dict[str, int] = {}
    for group in groups:
        winner = group.winner
        if winner is None:
            continue
        approved = winner.approved_version
        if approved is None:  # unreachable while winner is defined by approval; belt anyway
            continue
        base = _safe_name(names.get(group.slot_id) or approved.filename.rsplit(".", 1)[0])
        stem = f"{base}-v{approved.version}"
        used[stem] = used.get(stem, 0) + 1
        if used[stem] > 1:
            stem = f"{stem}-{used[stem]}"
        chosen.append((f"{stem}.png", approved))
    return chosen


async def build_zip(store: Store, blobs: BlobStore, project_id: str) -> bytes:
    """The deliverable: clean originals only — the annotated render never ships."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename, asset in await approved_assets(store, project_id):
            archive.writestr(filename, await blobs.read(asset.original_path))
    return buffer.getvalue()
