"""Platform placement checks (phase 9): pure geometry, advisory forever.

The lifecycle-isolation gate is structural: a PlacementFinding has no status
field from the defect state machine, and nothing here imports it.
"""

import pytest

from app.domain import platforms
from app.domain.lifecycle import DefectState
from app.domain.platforms import CROP_LOSS_THRESHOLD, PLATFORMS, check, crop_box, safe_area

# --- crop arithmetic --------------------------------------------------------


def test_a_wide_image_loses_its_sides_to_a_tall_crop():
    box = crop_box(1920, 1080, "tiktok")  # 16:9 into 9:16
    assert box.height == 1080
    assert box.width == round(1080 * 9 / 16)
    assert box.top == 0
    assert box.left == (1920 - box.width) // 2


def test_a_matching_aspect_loses_nothing():
    box = crop_box(1080, 1920, "tiktok")
    assert (box.left, box.top, box.width, box.height) == (0, 0, 1080, 1920)
    assert platforms.crop_loss(1080, 1920, "tiktok") == 0


def test_crop_loss_is_the_share_of_pixels_gone():
    # 16:9 into 9:16 keeps (1080*607)/(1920*1080) ≈ 31.6% — loses ~68%.
    loss = platforms.crop_loss(1920, 1080, "tiktok")
    assert loss == pytest.approx(1 - (round(1080 * 9 / 16) * 1080) / (1920 * 1080))
    assert loss > 0.6


def test_safe_area_sits_inside_the_crop():
    box = crop_box(1080, 1920, "tiktok")
    safe = safe_area(1080, 1920, "tiktok")
    assert safe.left >= box.left and safe.top >= box.top
    assert safe.left + safe.width <= box.left + box.width
    assert safe.top + safe.height <= box.top + box.height
    # TikTok's caption zone eats the bottom 14%.
    assert safe.top + safe.height == box.top + box.height - round(box.height * 0.14)


# --- findings ----------------------------------------------------------------


def test_a_mismatched_aspect_earns_a_crop_loss_advisory():
    findings = check(1920, 1080, "tiktok")
    kinds = [f.kind for f in findings]
    assert "crop_loss" in kinds
    detail = next(f for f in findings if f.kind == "crop_loss").detail
    assert "%" in detail and "TikTok" in detail and "9:16" in detail


def test_a_native_asset_at_full_resolution_is_clean():
    assert check(1080, 1920, "tiktok") == []
    assert check(1200, 675, "web") == []


def test_a_small_asset_earns_the_resolution_advisory():
    findings = check(540, 960, "tiktok")
    assert [f.kind for f in findings] == ["resolution"]
    assert "540×960" in findings[0].detail


def test_an_unknown_placement_or_zero_size_says_nothing():
    assert check(1080, 1920, "myspace") == []
    assert check(0, 0, "tiktok") == []


def test_finding_keys_are_stable_per_image_platform_kind():
    (finding,) = check(540, 960, "tiktok")
    assert finding.key_for("img1") == "img1:tiktok:resolution"


def test_threshold_is_a_named_constant_not_a_vibe():
    assert 0 < CROP_LOSS_THRESHOLD < 1


# --- lifecycle isolation (gate 9) --------------------------------------------


def test_placement_findings_share_nothing_with_the_defect_lifecycle():
    """Structural: no defect-state field exists to transition, and no value of
    the defect state machine appears anywhere in a finding."""
    (finding,) = check(540, 960, "tiktok")
    payload = finding.model_dump()
    assert "status" not in payload
    for value in payload.values():
        assert value not in set(DefectState)


def test_every_platform_preset_is_complete():
    for name, spec in PLATFORMS.items():
        assert set(spec) >= {"label", "aspect", "min_width", "min_height", "insets"}, name
        assert set(spec["insets"]) == {"top", "bottom", "left", "right"}
