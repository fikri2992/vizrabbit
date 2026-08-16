"""The synthetic brand benchmark's own properties.

A benchmark that quietly stops testing what it claims to test is worse than no
benchmark, so these assert the *dataset* is still shaped the way Gate 7 assumes
— before anyone reads a score off it.
"""

from app.domain.brand import evaluate
from app.domain.color import delta_e_hex
from app.eval.palette import (
    BRAND_PALETTE,
    OFF_PALETTE,
    PHOTOGRAPHIC,
    clean_case,
    dataset,
    hit,
    profile,
    run_mechanical,
    score,
    violating_case,
)
from app.imaging.palette import measure_cells


def test_the_dataset_is_the_size_gate_7_specifies():
    cases = dataset()
    assert sum(1 for case in cases if case.violating) == 10
    assert sum(1 for case in cases if not case.violating) == 10


def test_every_violating_case_names_the_cell_it_planted():
    for index in range(10):
        case = violating_case(index)
        assert len(case.truth_cells) == 1
        assert case.grid.contains(case.truth_cells[0])


def test_clean_cases_claim_no_truth_cells():
    assert all(clean_case(index).truth_cells == [] for index in range(10))


def test_the_cases_are_deterministic_so_a_score_is_comparable():
    first, second = violating_case(3), violating_case(3)
    assert first.truth_cells == second.truth_cells
    assert first.image.tobytes() == second.image.tobytes()


def test_every_planted_colour_is_genuinely_off_the_palette():
    """If a planted colour were within tolerance the case would be unwinnable."""
    brand = profile()
    for colour in OFF_PALETTE:
        distances = [delta_e_hex(colour, entry.hex) for entry in brand.entries]
        tolerances = [entry.tolerance for entry in brand.entries]
        assert all(d > t for d, t in zip(distances, tolerances, strict=True)), colour


def test_the_photographic_colours_are_also_off_palette_by_design():
    """The clean set is only a real test if its colours would fool a pure measurement."""
    brand = profile()
    for colour in PHOTOGRAPHIC:
        assert all(
            delta_e_hex(colour, entry.hex) > entry.tolerance for entry in brand.entries
        ), colour


def test_the_brand_colours_measure_as_compliant_with_themselves():
    brand = profile()
    assert [entry.hex for entry in brand.entries] == BRAND_PALETTE


def test_the_measurement_layer_finds_every_planted_element():
    """Recall of the instrument, with no model in the loop — currently 10/10."""
    results = run_mechanical([violating_case(index) for index in range(10)])
    assert score(results).recall == 1.0


def test_the_measurement_layer_cannot_tell_photographs_from_design():
    """Documented on purpose: separating these is the Inspector's job, not the maths'.

    If this ever starts passing, the measurement has become opinionated and the
    division of labour the design rests on has quietly moved.
    """
    brand = profile()
    flagged = [
        bool(evaluate(measure_cells(case.image, case.grid), brand))
        for case in (clean_case(index) for index in range(10))
    ]
    assert all(flagged)


def test_hit_requires_the_flag_to_land_on_the_planted_cell():
    case = violating_case(0)
    [offence] = [
        o
        for o in evaluate(measure_cells(case.image, case.grid), profile())
        if o.cells == case.truth_cells
    ]
    assert hit([offence], case.truth_cells)
    assert not hit([offence], ["A1"] if case.truth_cells != ["A1"] else ["H8"])
