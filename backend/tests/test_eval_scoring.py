"""Scoring logic — the arithmetic Gate 1 rests on.

If this is wrong, the benchmark lies about whether the pipeline beats the baseline,
which is the one claim the whole project stands on. Tested exhaustively.
"""

import json

import pytest

from app.domain.taxonomy import Category
from app.eval.dataset import LabelledImage, TruthDefect, load_labels, summarise
from app.eval.scoring import (
    Metrics,
    cell_distance,
    gate_1_verdict,
    match_defects,
    region_distance,
    regions_match,
)

# --- distance -------------------------------------------------------------


def test_a_cell_is_zero_distance_from_itself():
    assert cell_distance("C4", "C4") == 0


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("C4", "D4", 1),  # horizontal neighbour
        ("C4", "C5", 1),  # vertical neighbour
        ("C4", "D5", 1),  # diagonal is still one cell away
        ("C4", "E4", 2),
        ("A1", "H8", 7),
    ],
)
def test_chebyshev_distance(a, b, expected):
    assert cell_distance(a, b) == expected
    assert cell_distance(b, a) == expected


def test_region_distance_is_the_closest_pair():
    assert region_distance(["A1", "C4"], ["D4", "H8"]) == 1


def test_region_distance_ignores_unparsable_refs():
    assert region_distance(["junk", "C4"], ["D4"]) == 1


def test_region_distance_of_all_junk_is_effectively_infinite():
    assert region_distance(["junk"], ["D4"]) > 1000


# --- matching -------------------------------------------------------------


def test_exact_overlap_matches():
    assert regions_match(["C4"], ["C4"])


def test_adjacent_cells_are_the_same_finding():
    """A defect straddling a boundary must not be scored as a miss."""
    assert regions_match(["C4"], ["D4"])
    assert regions_match(["C4"], ["D5"])


def test_two_cells_apart_is_a_different_finding():
    assert not regions_match(["C4"], ["E4"])


def test_tolerance_is_configurable():
    assert regions_match(["C4"], ["E4"], tolerance=2)
    assert not regions_match(["C4"], ["D4"], tolerance=0)


def test_a_perfect_prediction_scores_all_true_positives():
    result = match_defects([["C4"], ["F6"]], [["C4"], ["F6"]])
    assert result.true_positives == 2
    assert result.false_positives == [] and result.false_negatives == []


def test_an_extra_prediction_is_a_false_positive():
    result = match_defects([["C4"], ["A1"]], [["C4"]])
    assert result.true_positives == 1
    assert result.false_positives == [1]


def test_a_missed_defect_is_a_false_negative():
    result = match_defects([["C4"]], [["C4"], ["H8"]])
    assert result.true_positives == 1
    assert result.false_negatives == [1]


def test_predicting_nothing_misses_everything():
    result = match_defects([], [["C4"], ["H8"]])
    assert result.true_positives == 0
    assert result.false_negatives == [0, 1]


def test_predictions_on_a_clean_image_are_all_false_positives():
    result = match_defects([["C4"], ["H8"]], [])
    assert result.false_positives == [0, 1]
    assert result.true_positives == 0


def test_matching_is_one_to_one():
    """Three predictions on one defect must not score three true positives."""
    result = match_defects([["C4"], ["C4"], ["D4"]], [["C4"]])
    assert result.true_positives == 1
    assert len(result.false_positives) == 2


def test_one_prediction_cannot_cover_two_defects():
    result = match_defects([["C4"]], [["C4"], ["D4"]])
    assert result.true_positives == 1
    assert len(result.false_negatives) == 1


def test_nearest_pairs_are_matched_first():
    """The exact match must claim its truth, leaving the distant one unmatched."""
    result = match_defects([["D4"], ["C4"]], [["C4"]])
    assert result.matched == [(1, 0)]
    assert result.false_positives == [0]


def test_multi_cell_regions_match_on_any_overlap():
    assert match_defects([["C4", "D4", "E4"]], [["E4"]]).true_positives == 1


# --- metrics --------------------------------------------------------------


def test_metrics_of_a_perfect_run():
    metrics = Metrics()
    metrics.add(match_defects([["C4"]], [["C4"]]), is_clean=False, seconds=10)
    assert metrics.recall == 1.0
    assert metrics.precision == 1.0
    assert metrics.f1 == 1.0


def test_recall_counts_only_what_was_findable():
    metrics = Metrics()
    metrics.add(match_defects([["C4"]], [["C4"], ["H8"]]), is_clean=False)
    assert metrics.recall == 0.5
    assert metrics.precision == 1.0


def test_precision_counts_only_what_was_returned():
    metrics = Metrics()
    metrics.add(match_defects([["C4"], ["A1"]], [["C4"]]), is_clean=False)
    assert metrics.precision == 0.5
    assert metrics.recall == 1.0


def test_empty_metrics_do_not_divide_by_zero():
    metrics = Metrics()
    assert (metrics.recall, metrics.precision, metrics.f1) == (0.0, 0.0, 0.0)
    assert metrics.false_positives_per_clean_image == 0.0
    assert metrics.seconds_per_image == 0.0


def test_f1_is_zero_when_either_side_is_zero():
    metrics = Metrics()
    metrics.add(match_defects([["A1"]], [["H8"]]), is_clean=False)
    assert metrics.precision == 0.0 and metrics.recall == 0.0
    assert metrics.f1 == 0.0


def test_clean_image_false_positives_are_tracked_separately():
    metrics = Metrics()
    metrics.add(match_defects([["C4"], ["A1"]], []), is_clean=True)
    metrics.add(match_defects([], []), is_clean=True)
    assert metrics.clean_images == 2
    assert metrics.false_positives_on_clean == 2
    assert metrics.false_positives_per_clean_image == 1.0


def test_defective_image_false_positives_do_not_pollute_the_clean_rate():
    metrics = Metrics()
    metrics.add(match_defects([["A1"], ["B2"]], [["H8"]]), is_clean=False)
    assert metrics.false_positives == 2
    assert metrics.false_positives_per_clean_image == 0.0


def test_latency_is_averaged_per_image():
    metrics = Metrics()
    metrics.add(match_defects([], []), is_clean=True, seconds=100)
    metrics.add(match_defects([], []), is_clean=True, seconds=50)
    assert metrics.seconds_per_image == 75.0


def test_row_renders_every_metric():
    metrics = Metrics()
    metrics.add(match_defects([["C4"]], [["C4"]]), is_clean=False, seconds=12.3)
    row = metrics.as_row("pipeline")
    assert row.startswith("| pipeline |")
    assert "1.00" in row and "12.3s" in row


# --- Gate 1 verdict -------------------------------------------------------


def _metrics(tp, fp, fn, clean_fp=0, clean=1, seconds=10.0):
    metrics = Metrics(
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        clean_images=clean,
        false_positives_on_clean=clean_fp,
        images=1,
        total_seconds=seconds,
    )
    return metrics


def test_gate_1_passes_when_every_threshold_is_met():
    pipeline = _metrics(tp=9, fp=2, fn=1)  # recall 0.90, precision 0.82
    baseline = _metrics(tp=5, fp=3, fn=5)  # recall 0.50
    assert all(passed for _, passed, _ in gate_1_verdict(pipeline, baseline))


def test_gate_1_fails_on_insufficient_lift_over_the_baseline():
    """The point of the benchmark: a good score that a naive prompt also gets is no win."""
    pipeline = _metrics(tp=8, fp=1, fn=2)  # recall 0.80
    baseline = _metrics(tp=8, fp=1, fn=2)  # identical
    checks = dict((name, passed) for name, passed, _ in gate_1_verdict(pipeline, baseline))
    assert checks["recall >= 0.75"] is True
    assert checks["recall lift >= +10pts vs naive"] is False


def test_gate_1_fails_on_low_recall():
    pipeline = _metrics(tp=5, fp=0, fn=5)  # recall 0.50
    baseline = _metrics(tp=1, fp=0, fn=9)
    checks = dict((name, passed) for name, passed, _ in gate_1_verdict(pipeline, baseline))
    assert checks["recall >= 0.75"] is False


def test_gate_1_fails_when_precision_is_bought_with_noise():
    pipeline = _metrics(tp=9, fp=20, fn=1)
    baseline = _metrics(tp=4, fp=1, fn=6)
    checks = dict((name, passed) for name, passed, _ in gate_1_verdict(pipeline, baseline))
    assert checks["precision >= 0.70"] is False
    assert checks["precision not worse than naive"] is False


def test_gate_1_fails_on_a_noisy_clean_set():
    pipeline = _metrics(tp=9, fp=5, fn=1, clean_fp=5, clean=2)
    baseline = _metrics(tp=2, fp=0, fn=8)
    checks = dict((name, passed) for name, passed, _ in gate_1_verdict(pipeline, baseline))
    assert checks["<= 1.0 false positive per clean image"] is False


def test_gate_1_fails_when_too_slow():
    pipeline = _metrics(tp=9, fp=1, fn=1, seconds=200.0)
    baseline = _metrics(tp=2, fp=0, fn=8)
    checks = dict((name, passed) for name, passed, _ in gate_1_verdict(pipeline, baseline))
    assert checks["<= 120s per image"] is False


# --- dataset --------------------------------------------------------------


def test_labels_load_from_disk(tmp_path):
    path = tmp_path / "labels.json"
    path.write_text(
        json.dumps(
            [
                {
                    "image": "a.png",
                    "defects": [
                        {"cells": ["c4"], "category": "anatomy", "rule": "ANAT-01", "note": "hand"}
                    ],
                },
                {"image": "clean.png", "defects": []},
            ]
        ),
        encoding="utf-8",
    )

    labels = load_labels(path)
    assert labels[0].defects[0].cells == ["C4"]
    assert labels[0].defects[0].category is Category.ANATOMY
    assert labels[1].is_clean is True
    assert labels[0].is_clean is False


def test_summarise_reports_set_composition():
    labels = [
        LabelledImage("a.png", [TruthDefect(["C4"], Category.ANATOMY)]),
        LabelledImage(
            "b.png", [TruthDefect(["A1"], Category.PHYSICS), TruthDefect(["B2"], Category.ANATOMY)]
        ),
        LabelledImage("clean.png", []),
    ]
    counts = summarise(labels)
    assert counts["images"] == 3
    assert counts["clean_images"] == 1
    assert counts["defects"] == 3
    assert counts["defects_anatomy"] == 2
    assert counts["defects_physics"] == 1
    assert counts["defects_brand"] == 0
