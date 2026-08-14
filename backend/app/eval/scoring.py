"""Matching predictions to ground truth, and the metrics Gate 1 is measured against.

A prediction matches a truth defect when their cell regions are close enough to be
the same finding. Tolerance exists because "the defect is at C4" and "the defect is
at C5" are the same report when the defect straddles the boundary — but two cells
apart is a different part of the picture.

Matching is one-to-one and greedy by proximity: one true defect cannot be credited
to three predictions, and one prediction cannot cover three defects.
"""

from dataclasses import dataclass

from app.domain.grid import GridError, parse_ref

#: Chebyshev distance in cells within which two regions are considered the same finding.
DEFAULT_TOLERANCE = 1


def cell_distance(a: str, b: str) -> int:
    """Chebyshev distance between two cell refs, in cells."""
    a_col, a_row = parse_ref(a)
    b_col, b_row = parse_ref(b)
    return max(abs(a_col - b_col), abs(a_row - b_row))


def region_distance(predicted: list[str], truth: list[str]) -> int:
    """Closest approach between two cell regions."""
    best = None
    for p in predicted:
        for t in truth:
            try:
                distance = cell_distance(p, t)
            except GridError:
                continue
            if best is None or distance < best:
                best = distance
    return best if best is not None else 10**6


def regions_match(
    predicted: list[str], truth: list[str], tolerance: int = DEFAULT_TOLERANCE
) -> bool:
    return region_distance(predicted, truth) <= tolerance


@dataclass
class MatchResult:
    """Which predictions landed, which truths were missed."""

    matched: list[tuple[int, int]]  # (prediction index, truth index)
    false_positives: list[int]  # prediction indices
    false_negatives: list[int]  # truth indices

    @property
    def true_positives(self) -> int:
        return len(self.matched)


def match_defects(
    predicted: list[list[str]],
    truth: list[list[str]],
    tolerance: int = DEFAULT_TOLERANCE,
) -> MatchResult:
    """Greedy one-to-one matching, nearest pairs first."""
    candidates = []
    for p_index, p_cells in enumerate(predicted):
        for t_index, t_cells in enumerate(truth):
            distance = region_distance(p_cells, t_cells)
            if distance <= tolerance:
                candidates.append((distance, p_index, t_index))
    candidates.sort()

    used_predictions: set[int] = set()
    used_truths: set[int] = set()
    matched: list[tuple[int, int]] = []

    for _, p_index, t_index in candidates:
        if p_index in used_predictions or t_index in used_truths:
            continue
        used_predictions.add(p_index)
        used_truths.add(t_index)
        matched.append((p_index, t_index))

    return MatchResult(
        matched=matched,
        false_positives=[i for i in range(len(predicted)) if i not in used_predictions],
        false_negatives=[i for i in range(len(truth)) if i not in used_truths],
    )


@dataclass
class Metrics:
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    clean_images: int = 0
    false_positives_on_clean: int = 0
    images: int = 0
    total_seconds: float = 0.0

    def add(self, result: MatchResult, *, is_clean: bool, seconds: float = 0.0) -> None:
        self.true_positives += result.true_positives
        self.false_positives += len(result.false_positives)
        self.false_negatives += len(result.false_negatives)
        self.images += 1
        self.total_seconds += seconds
        if is_clean:
            self.clean_images += 1
            self.false_positives_on_clean += len(result.false_positives)

    @property
    def recall(self) -> float:
        relevant = self.true_positives + self.false_negatives
        return self.true_positives / relevant if relevant else 0.0

    @property
    def precision(self) -> float:
        returned = self.true_positives + self.false_positives
        return self.true_positives / returned if returned else 0.0

    @property
    def f1(self) -> float:
        if not (self.precision and self.recall):
            return 0.0
        return 2 * self.precision * self.recall / (self.precision + self.recall)

    @property
    def false_positives_per_clean_image(self) -> float:
        return self.false_positives_on_clean / self.clean_images if self.clean_images else 0.0

    @property
    def seconds_per_image(self) -> float:
        return self.total_seconds / self.images if self.images else 0.0

    def as_row(self, label: str) -> str:
        return (
            f"| {label} | {self.recall:.2f} | {self.precision:.2f} | {self.f1:.2f} | "
            f"{self.false_positives_per_clean_image:.2f} | {self.seconds_per_image:.1f}s |"
        )


TABLE_HEADER = (
    "| Run | Recall | Precision | F1 | FP/clean image | s/image |\n"
    "| --- | --- | --- | --- | --- | --- |"
)


def gate_1_verdict(pipeline: Metrics, baseline: Metrics) -> list[tuple[str, bool, str]]:
    """The Gate 1 thresholds from docs/implementation-plan.md, checked explicitly."""
    recall_lift = (pipeline.recall - baseline.recall) * 100
    return [
        ("recall >= 0.75", pipeline.recall >= 0.75, f"{pipeline.recall:.2f}"),
        ("precision >= 0.70", pipeline.precision >= 0.70, f"{pipeline.precision:.2f}"),
        (
            "recall lift >= +10pts vs naive",
            recall_lift >= 10.0,
            f"{recall_lift:+.1f}pts",
        ),
        (
            "precision not worse than naive",
            pipeline.precision >= baseline.precision,
            f"{pipeline.precision:.2f} vs {baseline.precision:.2f}",
        ),
        (
            "<= 1.0 false positive per clean image",
            pipeline.false_positives_per_clean_image <= 1.0,
            f"{pipeline.false_positives_per_clean_image:.2f}",
        ),
        (
            "<= 120s per image",
            pipeline.seconds_per_image <= 120.0,
            f"{pipeline.seconds_per_image:.1f}s",
        ),
    ]
