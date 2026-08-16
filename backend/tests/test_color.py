"""Colour maths against published reference data. Pure functions, zero mocks.

The ΔE2000 cases are the Sharma, Wu & Dalal test set — the pairs the CIE
implementation-verification literature uses precisely because they exercise the
hue-wrap and near-neutral branches where naive implementations go wrong.
"""

import math

import pytest

from app.domain.color import (
    BadHex,
    delta_e,
    delta_e_hex,
    hex_to_lab,
    nearest,
    normalise_hex,
    parse_hex,
    rgb_to_lab,
    to_hex,
)

#: (Lab 1, Lab 2, expected ΔE00) — Sharma/Wu/Dalal verification pairs.
SHARMA = [
    ((50.0000, 2.6772, -79.7751), (50.0000, 0.0000, -82.7485), 2.0425),
    ((50.0000, 3.1571, -77.2803), (50.0000, 0.0000, -82.7485), 2.8615),
    ((50.0000, 2.8361, -74.0200), (50.0000, 0.0000, -82.7485), 3.4412),
    ((50.0000, -1.3802, -84.2814), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, -1.1848, -84.8006), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, -0.9009, -85.5211), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, 0.0000, 0.0000), (50.0000, -1.0000, 2.0000), 2.3669),
    ((50.0000, -1.0000, 2.0000), (50.0000, 0.0000, 0.0000), 2.3669),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0009), 7.1792),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0010), 7.1792),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0011), 7.2195),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0012), 7.2195),
    ((50.0000, -0.0010, 2.4900), (50.0000, 0.0009, -2.4900), 4.8045),
    ((50.0000, -0.0010, 2.4900), (50.0000, 0.0011, -2.4900), 4.7461),
    ((50.0000, 2.5000, 0.0000), (50.0000, 0.0000, -2.5000), 4.3065),
    ((50.0000, 2.5000, 0.0000), (73.0000, 25.0000, -18.0000), 27.1492),
    ((50.0000, 2.5000, 0.0000), (61.0000, -5.0000, 29.0000), 22.8977),
    ((50.0000, 2.5000, 0.0000), (56.0000, -27.0000, -3.0000), 31.9030),
    ((50.0000, 2.5000, 0.0000), (58.0000, 24.0000, 15.0000), 19.4535),
    ((50.0000, 2.5000, 0.0000), (50.0000, 3.1736, 0.5854), 1.0000),
    ((50.0000, 2.5000, 0.0000), (50.0000, 3.2972, 0.0000), 1.0000),
    ((50.0000, 2.5000, 0.0000), (50.0000, 1.8634, 0.5757), 1.0000),
    ((50.0000, 2.5000, 0.0000), (50.0000, 3.2592, 0.3350), 1.0000),
    ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
    ((63.0109, -31.0961, -5.8663), (62.8187, -29.7946, -4.0864), 1.2630),
    ((61.2901, 3.7196, -5.3901), (61.4292, 2.2480, -4.9620), 1.8731),
    ((35.0831, -44.1164, 3.7933), (35.0232, -40.0716, 1.5901), 1.8645),
    ((22.7233, 20.0904, -46.6940), (23.0331, 14.9730, -42.5619), 2.0373),
    ((36.4612, 47.8580, 18.3852), (36.2715, 50.5065, 21.2231), 1.4146),
    ((90.8027, -2.0831, 1.4410), (91.1528, -1.6435, 0.0447), 1.4441),
    ((90.9257, -0.5406, -0.9208), (88.6381, -0.8985, -0.7239), 1.5381),
    ((6.7747, -0.2908, -2.4247), (5.8714, -0.0985, -2.2286), 0.6377),
    ((2.0776, 0.0795, -1.1350), (0.9033, -0.0636, -0.5514), 0.9082),
]


@pytest.mark.parametrize("lab1,lab2,expected", SHARMA)
def test_delta_e_2000_matches_the_published_reference_pairs(lab1, lab2, expected):
    assert delta_e(lab1, lab2) == pytest.approx(expected, abs=0.0001)


def test_delta_e_is_symmetric():
    for lab1, lab2, _ in SHARMA:
        assert delta_e(lab1, lab2) == pytest.approx(delta_e(lab2, lab1), abs=1e-9)


def test_a_colour_is_zero_distance_from_itself():
    for lab1, _, _ in SHARMA:
        assert delta_e(lab1, lab1) == pytest.approx(0.0, abs=1e-12)


# --- sRGB → Lab -----------------------------------------------------------


@pytest.mark.parametrize(
    "hex_value,lab",
    [
        ("#ffffff", (100.0, 0.0, 0.0)),
        ("#000000", (0.0, 0.0, 0.0)),
        ("#808080", (53.585, 0.0, 0.0)),  # mid grey stays neutral
        ("#ff0000", (53.241, 80.092, 67.203)),
        ("#00ff00", (87.735, -86.183, 83.179)),
        ("#0000ff", (32.297, 79.188, -107.860)),
    ],
)
def test_srgb_converts_to_the_published_lab_values(hex_value, lab):
    got = hex_to_lab(hex_value)
    assert got == pytest.approx(lab, abs=0.01)


def test_the_linearisation_knee_is_applied_below_the_threshold():
    """Very dark values take sRGB's linear segment, not the power curve.

    rgb(5,5,5) sits under the 0.04045 knee: 5/255/12.92 = 0.0015176, which is
    below the Lab epsilon too, so L* = 24389/27 × Y/Yn = 1.3709. Running the
    power curve instead would give 1.5657 — the gap is what this pins down.
    """
    assert rgb_to_lab((5, 5, 5))[0] == pytest.approx(1.3709, abs=0.001)


# --- hex handling ---------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        ("#1D9E75", (29, 158, 117)),
        ("1d9e75", (29, 158, 117)),
        ("  #1d9e75  ", (29, 158, 117)),
        ("#abc", (170, 187, 204)),
    ],
)
def test_hex_parsing_accepts_the_spellings_people_actually_paste(value, expected):
    assert parse_hex(value) == expected


@pytest.mark.parametrize("value", ["", "#12345", "not a colour", "#12345g", None, "#1234567"])
def test_bad_hex_is_refused_rather_than_guessed(value):
    with pytest.raises(BadHex):
        parse_hex(value)


def test_hex_round_trips():
    assert to_hex(parse_hex("#1d9e75")) == "#1d9e75"
    assert normalise_hex("#1D9E75") == "#1d9e75"
    assert normalise_hex("#ABC") == "#aabbcc"


def test_to_hex_clamps_out_of_range_channels():
    assert to_hex((-20, 300, 128)) == "#00ff80"


# --- nearest --------------------------------------------------------------


def test_nearest_finds_the_closest_palette_entry():
    entry, distance = nearest("#1d9e75", ["#e24b4a", "#1f9d78", "#378add"])
    assert entry == "#1f9d78"
    assert distance < 2


def test_an_exact_palette_match_is_zero_away():
    entry, distance = nearest("#378add", ["#e24b4a", "#378add"])
    assert entry == "#378add"
    assert distance == pytest.approx(0.0, abs=1e-9)


def test_an_empty_palette_is_infinitely_far_not_compliant():
    """An unconfirmed profile must never read as "everything matches"."""
    entry, distance = nearest("#378add", [])
    assert entry == ""
    assert math.isinf(distance)


def test_delta_e_hex_agrees_with_the_lab_path():
    assert delta_e_hex("#ff0000", "#00ff00") == pytest.approx(
        delta_e(hex_to_lab("#ff0000"), hex_to_lab("#00ff00")), abs=1e-12
    )
