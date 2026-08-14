"""Pipeline logic that does not need a model: budgets, gate application, schemas.

The agents themselves are deliberately not tested here — mocking Gemini would
prove nothing about detection quality. That is the eval harness's job (AGENTS.md).
"""

import pytest
from pydantic import ValidationError

from app.agents.pipeline import Defect, Dismissal, ImageReport, ProBudget, _apply_gate_verdict
from app.agents.schemas import (
    CircleCheck,
    GateVerdict,
    ScanResult,
    Suspect,
    Verdict,
    validate_against_grid,
)
from app.config import settings
from app.domain.grid import Grid, GridError
from app.domain.taxonomy import Category, Severity
from app.imaging.annotate import Annotation


@pytest.fixture
def grid():
    return Grid(cols=8, rows=8, width=800, height=800)


def make_defect(pin=1, severity=Severity.WARNING, cells=None) -> Defect:
    return Defect(
        pin=pin,
        cells=cells or ["C4"],
        category=Category.ANATOMY,
        severity=severity,
        comment=f"defect {pin}",
        rule_ref="ANAT-01",
        annotation=Annotation(pin=pin, cx=100, cy=100, radius=40, severity=severity),
        circle_iterations=1,
        circle_verified=True,
    )


# --- Pro budget -----------------------------------------------------------


def test_budget_defaults_to_the_configured_cap():
    assert ProBudget().limit == settings.max_pro_calls_per_run == 3


def test_budget_allows_exactly_its_limit():
    budget = ProBudget(limit=3)
    assert [budget.claim() for _ in range(3)] == [True, True, True]
    assert budget.claim() is False
    assert budget.spent == 3


def test_budget_reports_what_is_left():
    budget = ProBudget(limit=3)
    assert budget.remaining == 3
    budget.claim()
    assert budget.remaining == 2


def test_exhausted_budget_never_goes_negative():
    budget = ProBudget(limit=1)
    budget.claim()
    for _ in range(5):
        assert budget.claim() is False
    assert budget.remaining == 0


def test_a_zero_budget_blocks_every_call():
    assert ProBudget(limit=0).claim() is False


def test_budget_is_shared_across_a_batch():
    """One run's cap, not one per image — three images exhaust it for the fourth."""
    budget = ProBudget(limit=3)
    granted = [budget.claim() for _ in range(4)]
    assert granted == [True, True, True, False]


# --- Pro gate application -------------------------------------------------


def test_gate_rejection_moves_a_defect_to_the_dismissal_log():
    report = ImageReport(defects=[make_defect(1), make_defect(2)])
    _apply_gate_verdict(report, GateVerdict(rejected_pins=[1], reason="not visible"))

    assert [d.pin for d in report.defects] == [2]
    assert len(report.dismissals) == 1
    assert report.dismissals[0].stage == "pro_gate"
    assert report.dismissals[0].reason == "not visible"


def test_rejected_defects_are_never_silently_dropped():
    """Golden rule 3: dismissals are logged, never deleted."""
    report = ImageReport(defects=[make_defect(1), make_defect(2), make_defect(3)])
    _apply_gate_verdict(report, GateVerdict(rejected_pins=[1, 2, 3], reason="all wrong"))

    assert report.defects == []
    assert len(report.dismissals) == 3


def test_gate_can_correct_a_severity():
    report = ImageReport(defects=[make_defect(1, severity=Severity.NITPICK)])
    _apply_gate_verdict(report, GateVerdict(severity_changes={"1": Severity.BLOCKER}))

    assert report.defects[0].severity is Severity.BLOCKER


def test_severity_correction_recolours_the_annotation():
    """The drawn ring must match the corrected severity, or the image lies."""
    report = ImageReport(defects=[make_defect(1, severity=Severity.NITPICK)])
    _apply_gate_verdict(report, GateVerdict(severity_changes={"1": Severity.BLOCKER}))

    assert report.defects[0].annotation.severity is Severity.BLOCKER


def test_severity_correction_preserves_circle_geometry():
    report = ImageReport(defects=[make_defect(1)])
    before = report.defects[0].annotation
    _apply_gate_verdict(report, GateVerdict(severity_changes={"1": Severity.BLOCKER}))
    after = report.defects[0].annotation

    assert (after.cx, after.cy, after.radius, after.pin) == (
        before.cx,
        before.cy,
        before.radius,
        before.pin,
    )


def test_an_empty_verdict_changes_nothing():
    report = ImageReport(defects=[make_defect(1), make_defect(2)])
    _apply_gate_verdict(report, GateVerdict())

    assert len(report.defects) == 2
    assert report.dismissals == []


def test_gate_ignores_pins_that_do_not_exist():
    report = ImageReport(defects=[make_defect(1)])
    _apply_gate_verdict(
        report, GateVerdict(rejected_pins=[99], severity_changes={"98": Severity.BLOCKER})
    )

    assert len(report.defects) == 1
    assert report.defects[0].severity is Severity.WARNING


# --- report -----------------------------------------------------------------


def test_report_counts_blockers():
    report = ImageReport(
        defects=[
            make_defect(1, severity=Severity.BLOCKER),
            make_defect(2, severity=Severity.BLOCKER),
            make_defect(3, severity=Severity.NITPICK),
        ]
    )
    assert report.blockers == 2


def test_an_unverified_circle_needs_human_review():
    defect = make_defect(1)
    defect.circle_verified = False
    assert defect.needs_human_review is True
    assert make_defect(2).needs_human_review is False


def test_dismissals_record_which_stage_rejected_them():
    dismissal = Dismissal(["C4"], "six fingers?", "only four, in shadow", "inspector")
    assert dismissal.stage == "inspector"


# --- schemas ----------------------------------------------------------------


def test_suspect_normalises_cell_refs():
    suspect = Suspect(
        cells=[" c4 ", "d4"], category=Category.ANATOMY, hypothesis="x", confidence=0.5
    )
    assert suspect.cells == ["C4", "D4"]


def test_suspect_deduplicates_cells():
    suspect = Suspect(
        cells=["C4", "c4", "C4"], category=Category.PHYSICS, hypothesis="x", confidence=0.1
    )
    assert suspect.cells == ["C4"]


def test_suspect_requires_at_least_one_cell():
    with pytest.raises(ValidationError):
        Suspect(cells=[], category=Category.ANATOMY, hypothesis="x", confidence=0.5)


def test_suspect_rejects_malformed_cells():
    with pytest.raises((ValidationError, GridError)):
        Suspect(cells=["banana"], category=Category.ANATOMY, hypothesis="x", confidence=0.5)


@pytest.mark.parametrize("confidence", [-0.1, 1.1, 2.0])
def test_confidence_must_be_a_probability(confidence):
    with pytest.raises(ValidationError):
        Suspect(cells=["C4"], category=Category.ANATOMY, hypothesis="x", confidence=confidence)


def test_scan_result_defaults_to_empty():
    result = ScanResult()
    assert result.suspects == []
    assert result.notes == ""


def test_a_dismissing_verdict_needs_no_category_or_severity():
    """Dismissals must not be forced to invent a classification."""
    verdict = Verdict(confirmed=False, reason="normal shadow")
    assert verdict.category is None and verdict.severity is None


def test_circle_check_defaults_to_no_movement():
    check = CircleCheck(on_target=True)
    assert (check.dx, check.dy, check.dr) == (0, 0, 0)


# --- grid validation --------------------------------------------------------


def test_invented_cells_are_dropped_not_fatal(grid):
    """A hallucinated ref must not lose the whole scan."""
    assert validate_against_grid(["C4", "Z9", "D4"], grid) == ["C4", "D4"]


def test_validation_keeps_order_and_normalises(grid):
    assert validate_against_grid([" d4", "c4"], grid) == ["D4", "C4"]


def test_validation_can_return_nothing(grid):
    assert validate_against_grid(["Z9", "Y8"], grid) == []


def test_validation_rejects_malformed_refs_without_raising(grid):
    assert validate_against_grid(["not-a-ref", "C4"], grid) == ["C4"]
