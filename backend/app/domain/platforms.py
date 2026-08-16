"""Platform placement checks (phase 9) — pure geometry, advisory by design.

A placement finding belongs to an (image, platform) pair and never enters the
defect lifecycle: platforms change their chrome without the asset changing, so
these are context advisories a human acknowledges or waives, not defects the
agent could verify fixed.

v1 is mechanical only: centre-crop arithmetic, resolution floors, safe-area
geometry. No model calls. Findings are derived on read (decision 20); only the
human's acknowledge/waive decision is stored.
"""

from pydantic import BaseModel

#: What each placement means, mechanically. Insets are fractions of the cropped
#: frame that the platform's own UI covers (captions, action rails, tab bars).
PLATFORMS: dict[str, dict] = {
    "tiktok": {
        "label": "TikTok",
        "aspect": 9 / 16,
        "min_width": 1080,
        "min_height": 1920,
        # Caption block along the bottom, action rail down the right edge.
        "insets": {"top": 0.08, "bottom": 0.14, "left": 0.0, "right": 0.12},
    },
    "instagram": {
        "label": "Instagram feed",
        "aspect": 4 / 5,
        "min_width": 1080,
        "min_height": 1350,
        "insets": {"top": 0.04, "bottom": 0.08, "left": 0.03, "right": 0.03},
    },
    "web": {
        "label": "Web",
        "aspect": 16 / 9,
        "min_width": 1200,
        "min_height": 675,
        "insets": {"top": 0.0, "bottom": 0.0, "left": 0.0, "right": 0.0},
    },
}

#: Below this share of pixels lost to the crop, nobody needs telling.
CROP_LOSS_THRESHOLD = 0.10


class CropBox(BaseModel):
    left: int
    top: int
    width: int
    height: int


class PlacementFinding(BaseModel):
    """Advisory, never a defect. ``key`` is its stable identity for decisions."""

    platform: str
    kind: str  # crop_loss | resolution
    detail: str

    def key_for(self, image_id: str) -> str:
        return f"{image_id}:{self.platform}:{self.kind}"


def crop_box(width: int, height: int, platform: str) -> CropBox:
    """The centre crop the platform would take from this image."""
    target = PLATFORMS[platform]["aspect"]
    if width / height > target:  # too wide — sides go
        kept = round(height * target)
        return CropBox(left=(width - kept) // 2, top=0, width=kept, height=height)
    kept = round(width / target)  # too tall — top and bottom go
    return CropBox(left=0, top=(height - kept) // 2, width=width, height=kept)


def crop_loss(width: int, height: int, platform: str) -> float:
    box = crop_box(width, height, platform)
    return 1 - (box.width * box.height) / (width * height)


def safe_area(width: int, height: int, platform: str) -> CropBox:
    """The part of the crop the platform's own UI does not cover — for the overlay."""
    box = crop_box(width, height, platform)
    insets = PLATFORMS[platform]["insets"]
    left = box.left + round(box.width * insets["left"])
    top = box.top + round(box.height * insets["top"])
    right = box.left + box.width - round(box.width * insets["right"])
    bottom = box.top + box.height - round(box.height * insets["bottom"])
    return CropBox(left=left, top=top, width=max(0, right - left), height=max(0, bottom - top))


def check(width: int, height: int, platform: str) -> list[PlacementFinding]:
    """Every mechanical advisory this image earns on this platform."""
    if platform not in PLATFORMS or not width or not height:
        return []
    spec = PLATFORMS[platform]
    findings: list[PlacementFinding] = []

    loss = crop_loss(width, height, platform)
    if loss > CROP_LOSS_THRESHOLD:
        findings.append(
            PlacementFinding(
                platform=platform,
                kind="crop_loss",
                detail=(
                    f"{loss:.0%} of the image is lost to the {spec['label']} "
                    f"{_aspect_text(spec['aspect'])} crop"
                ),
            )
        )

    box = crop_box(width, height, platform)
    if box.width < spec["min_width"] or box.height < spec["min_height"]:
        findings.append(
            PlacementFinding(
                platform=platform,
                kind="resolution",
                detail=(
                    f"cropped frame is {box.width}×{box.height}, below the "
                    f"{spec['label']} recommendation of {spec['min_width']}×{spec['min_height']}"
                ),
            )
        )
    return findings


def _aspect_text(aspect: float) -> str:
    known = {9 / 16: "9:16", 4 / 5: "4:5", 16 / 9: "16:9"}
    return known.get(aspect, f"{aspect:.2f}")
