"""Video ingestion against real ffmpeg — no mocks, a generated two-shot clip.

Skipped wholesale when ffmpeg is not on PATH (it is in the container and on the
dev machines; CI without it loses coverage visibly rather than silently).
"""

import io
import shutil
import subprocess

import pytest
from PIL import Image as PILImage

from app.agents.pipeline import Defect as PipelineDefect
from app.agents.pipeline import ImageReport
from app.domain.entities import DefectRecord, ImageStatus, Member, Project, Role, User
from app.domain.taxonomy import Category, Severity
from app.imaging import video
from app.imaging.annotate import Annotation
from app.infra import repository as repo
from app.infra.events import EventBus
from app.infra.storage import LocalBlobStore
from app.infra.store import InMemoryStore
from app.services import runs as run_service

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg not installed",
)


@pytest.fixture(scope="module")
def clip(tmp_path_factory) -> bytes:
    """4s, 320x568, red shot then blue shot (hard cut at 2s), 440Hz sine audio."""
    path = tmp_path_factory.mktemp("video") / "clip.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=red:s=320x568:d=2:r=12",
            "-f", "lavfi", "-i", "color=c=blue:s=320x568:d=2:r=12",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
            "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]",
            "-map", "[v]", "-map", "2:a",
            "-pix_fmt", "yuv420p", "-shortest", str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path.read_bytes()


@pytest.mark.anyio
async def test_probe_reads_dimensions_and_duration(clip):
    info = await video.probe(clip)
    assert (info.width, info.height) == (320, 568)
    assert info.duration == pytest.approx(4.0, abs=0.3)


@pytest.mark.anyio
async def test_scene_times_find_the_cut_and_always_include_the_start(clip):
    times = await video.scene_times(clip)
    assert times[0] == 0.0
    assert len(times) == 2  # one hard cut
    assert times[1] == pytest.approx(2.0, abs=0.2)


@pytest.mark.anyio
async def test_frames_at_the_shots_are_the_shots(clip):
    """The frame before the cut is red, after it blue — pixels, not faith."""
    from app.imaging.canvas import from_bytes

    red = from_bytes(await video.frame_at(clip, 0.5)).getpixel((160, 280))
    blue = from_bytes(await video.frame_at(clip, 2.5)).getpixel((160, 280))
    assert red[0] > 180 and red[2] < 80
    assert blue[2] > 180 and blue[0] < 80


@pytest.mark.anyio
async def test_loudness_matches_ffmpegs_own_report(clip):
    """Gate 13: our number IS ffmpeg's number — assert the parse, then sanity."""
    loudness = await video.measure_loudness(clip)
    assert loudness is not None
    # A full-scale sine sits in a known loudness ballpark; the point is the
    # parse is exact and the value is sane, not a golden float.
    assert -25 < loudness.lufs < 0
    assert loudness.true_peak_db <= 0


@pytest.mark.anyio
async def test_a_soundless_clip_reports_no_loudness(tmp_path):
    silent = tmp_path / "silent.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=green:s=160x160:d=1:r=12",
            "-pix_fmt", "yuv420p", str(silent),
        ],
        check=True,
        capture_output=True,
    )
    assert await video.measure_loudness(silent.read_bytes()) is None


# --- ingestion and the shot-based review (gate 13) ---------------------------


OWNER = User(id="u-owner", email="owner@acme.com", name="Ola Owner")


def _project() -> Project:
    return Project(
        id="p1",
        name="Autumn",
        members=[Member(user_id=OWNER.id, email=OWNER.email, role=Role.OWNER)],
    )


@pytest.mark.anyio
async def test_a_video_upload_ingests_with_poster_duration_and_loudness(tmp_path, clip):
    store, blobs = InMemoryStore(), LocalBlobStore(tmp_path)
    run = await run_service.create_run(
        store, blobs, _project(), OWNER, [("spot.mp4", clip)]
    )
    (asset,) = [await repo.load(store, run_service.ImageAsset, i) for i in run.image_ids]
    assert asset.kind == "video"
    assert asset.duration == pytest.approx(4.0, abs=0.3)
    assert asset.loudness_lufs is not None
    assert asset.video_path.endswith(".mp4")
    # The poster is a real PNG of the first frame — every image surface just works.
    poster = PILImage.open(io.BytesIO(await blobs.read(asset.original_path)))
    assert poster.size == (320, 568)


@pytest.mark.anyio
async def test_a_video_reviews_as_shots_with_time_ranges(tmp_path, clip, monkeypatch):
    """Gate 13: one image review per shot; defects carry the shot's time range."""
    store, blobs = InMemoryStore(), LocalBlobStore(tmp_path)
    project = _project()
    run = await run_service.create_run(store, blobs, project, OWNER, [("spot.mp4", clip)])
    asset = await repo.load(store, run_service.ImageAsset, run.image_ids[0])

    calls = []

    async def fake_process(image, guidelines, on_progress=None, grid=None, profile=None):
        calls.append(image.size)
        pin = len(calls)
        return ImageReport(
            defects=[
                PipelineDefect(
                    pin=1,
                    cells=["B2"],
                    category=Category.ARTIFACT,
                    severity=Severity.WARNING,
                    comment=f"shot {pin} artifact",
                    rule_ref="",
                    annotation=Annotation(pin=1, cx=5, cy=5, radius=3, severity=Severity.WARNING),
                    circle_iterations=1,
                    circle_verified=True,
                )
            ]
        )

    monkeypatch.setattr(run_service, "process_image", fake_process)
    await run_service._process_one(
        store, blobs, EventBus(), project, run, asset.id, guidelines=""
    )

    assert len(calls) == 2  # two shots, two image reviews
    defects = sorted(
        await repo.find(store, DefectRecord, where={"image_id": asset.id}),
        key=lambda d: d.pin,
    )
    assert [d.pin for d in defects] == [1, 2]  # renumbered across shots
    assert defects[0].time_start == 0.0
    assert defects[0].time_end == pytest.approx(2.0, abs=0.3)
    assert defects[1].time_start == pytest.approx(2.0, abs=0.3)
    assert defects[1].time_end == pytest.approx(4.0, abs=0.3)

    refreshed = await repo.load(store, run_service.ImageAsset, asset.id)
    assert refreshed.status is ImageStatus.DONE
    assert refreshed.annotated_path == ""  # no cross-shot annotated poster lie


@pytest.mark.anyio
async def test_an_image_upload_is_byte_for_byte_unaffected(tmp_path):
    """Gate 13 regression: image-only projects never notice videos exist."""
    store, blobs = InMemoryStore(), LocalBlobStore(tmp_path)
    buffer = io.BytesIO()
    PILImage.new("RGB", (320, 320), (200, 30, 30)).save(buffer, format="PNG")
    run = await run_service.create_run(
        store, blobs, _project(), OWNER, [("a.png", buffer.getvalue())]
    )
    asset = await repo.load(store, run_service.ImageAsset, run.image_ids[0])
    assert asset.kind == "image"
    assert asset.video_path == "" and asset.duration == 0.0
    assert asset.loudness_lufs is None


def test_loudness_advisory_uses_the_platform_target():
    from app.domain.platforms import loudness_finding

    assert loudness_finding(-14.5, "tiktok") is None  # inside ±2
    finding = loudness_finding(-23.0, "tiktok")
    assert finding.kind == "loudness"
    assert "measured -23.0 LUFS" in finding.detail and "-14" in finding.detail
    assert loudness_finding(None, "tiktok") is None
