"""Verify FirestoreStore and GcsBlobStore against real Google Cloud.

The contract suite normally runs against the in-memory implementations. This drives
the same behaviours against the real services, because a difference between them is
exactly the kind of thing that only shows up after deploying.

Everything is written under a throwaway prefix and deleted afterwards.

    uv run python -m scripts.check_cloud_storage
"""

import asyncio
import sys
from uuid import uuid4

from app.config import settings
from app.domain.entities import Circle, DefectRecord, Member, Project, Role
from app.domain.lifecycle import DefectState
from app.domain.taxonomy import Category, Severity
from app.infra import repository as repo
from app.infra.storage import GcsBlobStore
from app.infra.store import FirestoreStore

RUN_ID = uuid4().hex[:8]
COLLECTION = f"_check_{RUN_ID}"


def project(project_id: str) -> Project:
    return Project(
        id=project_id,
        name="Cloud check",
        members=[Member(user_id="u1", email="owner@acme.com", role=Role.OWNER)],
    )


def defect(defect_id: str, pin: int) -> DefectRecord:
    return DefectRecord(
        id=defect_id,
        project_id="p-check",
        image_id="i-check",
        pin=pin,
        cells=["C4"],
        category=Category.ANATOMY,
        severity=Severity.BLOCKER,
        comment="six fingers",
        circle=Circle(cx=10, cy=20, radius=30),
    )


async def check_firestore() -> list[str]:
    failures: list[str] = []
    store = FirestoreStore()
    written: list[str] = []

    try:
        # Raw document round trip.
        await store.put(COLLECTION, "a", {"id": "a", "kind": "x", "live": True, "rank": "2"})
        await store.put(COLLECTION, "b", {"id": "b", "kind": "x", "live": False, "rank": "1"})
        await store.put(COLLECTION, "c", {"id": "c", "kind": "y", "live": True, "rank": "3"})
        written = ["a", "b", "c"]

        if (await store.get(COLLECTION, "a")) != {
            "id": "a",
            "kind": "x",
            "live": True,
            "rank": "2",
        }:
            failures.append("document did not round trip unchanged")

        if await store.get(COLLECTION, "missing") is not None:
            failures.append("a missing document should be None")

        filtered = await store.query(COLLECTION, where={"kind": "x"})
        if {d["id"] for d in filtered} != {"a", "b"}:
            failures.append(f"equality filter returned {[d['id'] for d in filtered]}")

        both = await store.query(COLLECTION, where={"kind": "x", "live": True})
        if [d["id"] for d in both] != ["a"]:
            failures.append(f"multi-field filter returned {[d['id'] for d in both]}")

        ordered = await store.query(COLLECTION, order_by="rank")
        if [d["id"] for d in ordered] != ["b", "a", "c"]:
            failures.append(f"ordering returned {[d['id'] for d in ordered]}")

        descending = await store.query(COLLECTION, order_by="rank", descending=True)
        if [d["id"] for d in descending] != ["c", "a", "b"]:
            failures.append(f"descending order returned {[d['id'] for d in descending]}")

        if len(await store.query(COLLECTION, limit=2)) != 2:
            failures.append("limit was not applied")

        await store.delete(COLLECTION, "c")
        if await store.get(COLLECTION, "c") is not None:
            failures.append("delete did not remove the document")
        written = ["a", "b"]

    finally:
        for doc_id in written:
            await store.delete(COLLECTION, doc_id)

    # Typed persistence: enums and datetimes must survive Firestore's own types.
    project_id = f"p-check-{RUN_ID}"
    defect_id = f"d-check-{RUN_ID}"
    try:
        original = project(project_id)
        await repo.save(store, original)
        loaded = await repo.load(store, Project, project_id)

        if loaded != original:
            failures.append("project did not round trip identically")
        if loaded and loaded.role_of("u1") is not Role.OWNER:
            failures.append("role enum lost in the round trip")

        stored_defect = defect(defect_id, pin=1)
        await repo.save(store, stored_defect)
        back = await repo.load(store, DefectRecord, defect_id)

        if back is None or back.severity is not Severity.BLOCKER:
            failures.append("severity enum lost in the round trip")
        elif back.status is not DefectState.OPEN:
            failures.append("lifecycle state lost in the round trip")
        elif back.created_at != stored_defect.created_at:
            failures.append(
                f"timestamp drifted: {back.created_at} != {stored_defect.created_at}"
            )
    finally:
        await repo.delete(store, Project, project_id)
        await repo.delete(store, DefectRecord, defect_id)

    return failures


async def check_gcs() -> list[str]:
    failures: list[str] = []
    blobs = GcsBlobStore()
    path = f"_check/{RUN_ID}/original.png"
    payload = b"\x89PNG\r\n\x1a\n" + bytes(range(256))

    try:
        if await blobs.exists(path):
            failures.append("a fresh path already exists")

        await blobs.write(path, payload)
        if not await blobs.exists(path):
            failures.append("written blob does not exist")
        if await blobs.read(path) != payload:
            failures.append("blob bytes did not round trip")

        await blobs.write(path, b"second")
        if await blobs.read(path) != b"second":
            failures.append("overwrite did not take effect")
    finally:
        import contextlib

        with contextlib.suppress(Exception):
            await asyncio.to_thread(blobs._bucket.blob(path).delete)  # noqa: SLF001

    return failures


async def main() -> int:
    if not settings.gcp_project:
        print("GCP_PROJECT is not set — nothing to check against")
        return 1

    print(f"project: {settings.gcp_project}")
    print(f"bucket : {settings.gcs_bucket}")
    print(f"prefix : {COLLECTION}\n")

    print("checking Firestore…")
    firestore_failures = await check_firestore()
    print(f"  {'PASS' if not firestore_failures else 'FAIL'}")

    print("checking Cloud Storage…")
    gcs_failures = await check_gcs()
    print(f"  {'PASS' if not gcs_failures else 'FAIL'}")

    failures = firestore_failures + gcs_failures
    if failures:
        print()
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1

    print("\nCloud storage check: PASS — both implementations behave like the in-memory ones")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
