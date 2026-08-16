"""Palette measurement and off-palette judgement.

Real Pillow images with colours planted at known cells, real arithmetic, no
mocks. The question each test answers is "would the Owner agree with the
number", which is the only thing that makes a brand defect defensible.
"""

import pytest
from PIL import Image, ImageDraw

from app.domain.brand import (
    PALETTE_RULE,
    MeasuredColour,
    attach_measurement,
    evaluate,
    offences_for_cells,
    summarise,
)
from app.domain.entities import BrandProfile, PaletteEntry
from app.domain.grid import Grid
from app.imaging.palette import dominant_colours, measure_cells, measure_region

BRAND_TEAL = "#1d9e75"
BRAND_INK = "#1c1e2a"
#: Far from everything in the profile; its nearest entry is the ink, at ΔE ~46.
OFF_ORANGE = "#d85a30"
#: A near-miss green: ΔE 5.2 from the teal, so it breaches a 3.0 tolerance while
#: still being unmistakably "meant to be" the brand colour.
OFF_GREEN = "#3aad88"


def profile(entries=None, confirmed="u-owner") -> BrandProfile:
    return BrandProfile(
        id="bp1",
        project_id="p1",
        entries=entries
        if entries is not None
        else [
            PaletteEntry(hex=BRAND_TEAL, role="primary", tolerance=3.0),
            PaletteEntry(hex=BRAND_INK, role="ink", tolerance=5.0),
        ],
        confirmed_by=confirmed,
    )


def measured(hex_value, cells=("C4",), coverage=0.5) -> MeasuredColour:
    return MeasuredColour(cells=list(cells), hex=hex_value, coverage=coverage)


# --- the confirmation gate ------------------------------------------------


def test_an_unconfirmed_profile_produces_no_findings_at_all():
    """Gate 7: nobody has said what the brand colours are, so nothing is off them."""
    unconfirmed = profile(confirmed="")
    assert unconfirmed.is_active is False
    assert evaluate([measured(OFF_ORANGE)], unconfirmed) == []


def test_a_confirmed_but_empty_profile_is_also_silent():
    assert evaluate([measured(OFF_ORANGE)], profile(entries=[])) == []


def test_no_profile_at_all_is_silent():
    assert evaluate([measured(OFF_ORANGE)], None) == []


# --- the measurement itself -----------------------------------------------


def test_an_exact_brand_colour_is_not_an_offence():
    assert evaluate([measured(BRAND_TEAL)], profile()) == []


def test_an_imperceptible_drift_stays_inside_tolerance():
    """One step off the brand teal is a rendering artefact, not a violation."""
    assert evaluate([measured("#1e9f76")], profile()) == []


def test_a_clearly_different_colour_is_an_offence_carrying_its_number():
    [offence] = evaluate([measured(OFF_ORANGE)], profile())
    assert offence.hex == OFF_ORANGE
    # Nearest is the ink, not the teal — an orange is closer to near-black than
    # to a saturated green, which is the sort of thing ΔE settles and eyes argue about.
    assert offence.nearest_hex == BRAND_INK
    assert offence.nearest_role == "ink"
    assert offence.delta_e > 20
    assert offence.tolerance == 5.0


def test_a_near_miss_of_a_brand_colour_is_still_an_offence():
    """The dangerous case: close enough to look intentional, far enough to be wrong."""
    [offence] = evaluate([measured(OFF_GREEN)], profile())
    assert offence.nearest_hex == BRAND_TEAL
    assert offence.nearest_role == "primary"
    assert 3.0 < offence.delta_e < 8.0


def test_tolerance_is_read_from_the_nearest_entry_not_a_global():
    """The ink allows 5.0, the teal 3.0 — a drift of ~4 is fine on one, not the other."""
    loose = profile(
        entries=[
            PaletteEntry(hex=BRAND_TEAL, role="primary", tolerance=1.0),
            PaletteEntry(hex=BRAND_INK, role="ink", tolerance=12.0),
        ]
    )
    near_ink = evaluate([measured("#242738")], loose)
    near_teal = evaluate([measured("#2aa47d")], loose)
    assert near_ink == []
    assert len(near_teal) == 1
    assert near_teal[0].nearest_hex == BRAND_TEAL


def test_hex_spelling_does_not_change_the_verdict():
    assert evaluate([measured("#1D9E75")], profile()) == []


def test_an_unparseable_measurement_is_skipped_not_reported():
    assert evaluate([measured("chartreuse")], profile()) == []


def test_low_coverage_readings_can_be_filtered_out():
    speck = [measured(OFF_ORANGE, coverage=0.02)]
    assert evaluate(speck, profile(), min_coverage=0.10) == []
    assert len(evaluate(speck, profile(), min_coverage=0.0)) == 1


def test_offences_come_back_worst_first():
    offences = evaluate(
        [measured(OFF_GREEN, cells=["A1"]), measured(OFF_ORANGE, cells=["B2"])],
        profile(),
    )
    assert [o.cells for o in offences] == [["B2"], ["A1"]]


def test_the_description_carries_the_measured_delta_e():
    """Gate 7: the defect comment must quote the number, not just assert a breach."""
    [offence] = evaluate([measured(OFF_ORANGE)], profile())
    text = offence.describe()
    assert "ΔE2000" in text
    assert f"{offence.delta_e:.1f}" in text
    assert offence.nearest_hex in text


# --- what the agents are shown --------------------------------------------


def test_the_scanner_summary_frames_measurements_as_evidence_not_verdicts():
    block = summarise(evaluate([measured(OFF_ORANGE)], profile()))
    assert "not defects" in block
    assert "designed" in block
    assert "skin" in block  # scene content is named, so it can be dismissed


def test_an_empty_measurement_set_produces_no_summary_block():
    assert summarise([]) == ""


def test_the_summary_caps_a_noisy_image_rather_than_flooding_the_prompt():
    noisy = evaluate(
        [measured(OFF_ORANGE, cells=[f"A{i % 8 + 1}"], coverage=0.5) for i in range(30)],
        profile(),
    )
    block = summarise(noisy, limit=5)
    assert "…and 25 further off-palette region(s)" in block


def test_only_the_offences_touching_a_suspect_reach_the_inspector():
    offences = evaluate(
        [measured(OFF_ORANGE, cells=["A1"]), measured(OFF_ORANGE, cells=["H8"])],
        profile(),
    )
    picked = offences_for_cells(offences, ["H8"])
    assert [o.cells for o in picked] == [["H8"]]


def test_the_rule_id_is_a_brand_rule():
    assert PALETTE_RULE.startswith("BRAND-")


# --- stamping the measurement onto a confirmed defect ---------------------


def test_a_confirmed_brand_defect_gains_the_measurement_and_the_rule_id():
    """Gate 7: the number in the comment is computed, never retyped by the model."""
    here = evaluate([measured(OFF_ORANGE)], profile())
    comment, rule = attach_measurement("The pack panel is the wrong colour.", "", True, here)

    assert rule == PALETTE_RULE
    assert "ΔE2000" in comment
    assert comment.startswith("The pack panel is the wrong colour.")


def test_a_non_brand_defect_is_left_alone_even_where_colour_was_measured():
    here = evaluate([measured(OFF_ORANGE)], profile())
    comment, rule = attach_measurement("Six fingers.", "ANAT-01", False, here)
    assert comment == "Six fingers."
    assert rule == "ANAT-01"


def test_a_brand_defect_with_no_measurement_here_is_left_alone():
    comment, rule = attach_measurement("Logo is stretched.", "BRAND-LOGO", True, [])
    assert comment == "Logo is stretched."
    assert rule == "BRAND-LOGO"


def test_an_existing_rule_id_survives_the_stamp():
    here = evaluate([measured(OFF_ORANGE)], profile())
    _, rule = attach_measurement("Off colour.", "BRAND-LOGO", True, here)
    assert rule == "BRAND-LOGO"


def test_the_measurement_is_not_repeated_if_the_model_already_quoted_it():
    here = evaluate([measured(OFF_ORANGE)], profile())
    already = f"Panel reads ΔE2000 {here[0].delta_e:.1f} off brand."
    comment, _ = attach_measurement(already, "", True, here)
    assert comment == already


def test_the_worst_offence_in_the_region_is_the_one_quoted():
    here = evaluate(
        [measured(OFF_GREEN, cells=["C4"]), measured(OFF_ORANGE, cells=["C4"])], profile()
    )
    comment, _ = attach_measurement("Off colour.", "", True, here)
    worst = max(here, key=lambda offence: offence.delta_e)
    assert f"{worst.delta_e:.1f}" in comment


# --- Pillow measurement ---------------------------------------------------


def test_a_flat_swatch_reads_back_as_its_own_colour():
    swatch = Image.new("RGB", (64, 64), (29, 158, 117))
    [(hex_value, coverage)] = dominant_colours(swatch)
    assert hex_value == BRAND_TEAL
    assert coverage == pytest.approx(1.0, abs=0.01)


def test_a_half_and_half_region_reports_both_at_roughly_half():
    image = Image.new("RGB", (64, 64), (29, 158, 117))
    ImageDraw.Draw(image).rectangle([0, 0, 63, 31], fill=(216, 90, 48))
    readings = dict(dominant_colours(image))
    assert set(readings) == {BRAND_TEAL, OFF_ORANGE}
    assert readings[OFF_ORANGE] == pytest.approx(0.5, abs=0.05)


def test_an_empty_region_measures_nothing():
    assert dominant_colours(Image.new("RGB", (0, 0))) == []


def test_a_planted_off_palette_element_is_found_in_its_own_cell():
    """A small designed element dominates its cell even when the frame ignores it."""
    image = Image.new("RGB", (800, 800), (29, 158, 117))
    grid = Grid.for_image(800, 800)
    box = grid.cell_bounds("C4")
    ImageDraw.Draw(image).rectangle(box.as_tuple(), fill=(216, 90, 48))

    offences = evaluate(measure_cells(image, grid), profile())
    assert [offence.cells for offence in offences] == [["C4"]]
    assert offences[0].hex == OFF_ORANGE


def test_an_entirely_on_palette_image_yields_nothing():
    image = Image.new("RGB", (800, 800), (29, 158, 117))
    grid = Grid.for_image(800, 800)
    ImageDraw.Draw(image).rectangle([100, 100, 400, 400], fill=(28, 30, 42))

    assert evaluate(measure_cells(image, grid), profile()) == []


def test_measuring_only_the_cells_asked_for():
    image = Image.new("RGB", (800, 800), (29, 158, 117))
    grid = Grid.for_image(800, 800)
    measurements = measure_cells(image, grid, cells=["A1", "B1"])
    assert {tuple(m.cells) for m in measurements} == {("A1",), ("B1",)}


def test_unknown_cell_refs_are_ignored_rather_than_raising():
    image = Image.new("RGB", (800, 800), (29, 158, 117))
    grid = Grid.for_image(800, 800)
    assert measure_cells(image, grid, cells=["Z9"]) == []


def test_a_span_is_measured_as_one_region():
    image = Image.new("RGB", (800, 800), (29, 158, 117))
    grid = Grid.for_image(800, 800)
    ImageDraw.Draw(image).rectangle(grid.span_bounds(["C4", "D4"]).as_tuple(), fill=(216, 90, 48))

    readings = measure_region(image, grid, ["C4", "D4"])
    assert readings
    assert readings[0].hex == OFF_ORANGE
    assert readings[0].cells == ["C4", "D4"]
