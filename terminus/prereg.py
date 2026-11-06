"""Preregistration support: predicted outcome distributions and a three-valued checker.

Section 5.5 fixes the outcome rubric and Section 5.7 the falsifiers; a runnable
design needs the predictions stated before the run. A preregistration fixture
declares, per cell, a predicted distribution over the outcome rubric and a realised-n
floor. The checker returns PASS, FAIL, or INSUFFICIENT.

INSUFFICIENT is a first-class verdict. A cell whose realised n is below its
preregistered floor is undecided, not a pass. A rule that cannot return undecided is
forbidden in this repo: without it a thin sample is read as a direction.

Decision rule, stated per cell: the total-variation distance between the predicted
and the observed distribution over the rubric labels, against the cell's declared
tolerance. PASS iff the distance is within tolerance and n reaches the floor; FAIL
iff the distance exceeds tolerance and n reaches the floor; INSUFFICIENT iff n is
below the floor. Overall: FAIL if any cell fails; else INSUFFICIENT if any cell is
undecided; else PASS. The distance metric and the tolerance are the scaffold's
declared convention (MEASURED arithmetic on the declared fixture), not a claim the
paper makes.
"""
from __future__ import annotations

from dataclasses import dataclass

from .fixtures import FixtureError
from .vocabulary import Outcome, Verdict

DEFAULT_N_FLOOR = 4
DEFAULT_TOLERANCE = 0.35


@dataclass(frozen=True)
class CellCheck:
    """One preregistered cell's verdict and the numbers behind it."""

    cell_id: str
    verdict: Verdict
    n: int
    n_floor: int
    distance: float | None
    tolerance: float
    predicted: dict
    observed: dict
    detail: str


@dataclass(frozen=True)
class PreregResult:
    """The whole preregistration's verdict, plus each cell's."""

    verdict: Verdict
    cells: tuple[CellCheck, ...]
    detail: str


def _normalise_predicted(predicted: dict, where: str) -> dict[str, float]:
    if not predicted:
        raise FixtureError(f"{where}: predicted distribution is empty")
    labels = {str(label): float(share) for label, share in predicted.items()}
    unknown = [label for label in labels if label not in {member.value for member in Outcome}]
    if unknown:
        raise FixtureError(f"{where}: predicted labels not in the outcome rubric: {unknown}")
    total = sum(labels.values())
    if abs(total - 1.0) > 1e-3:
        raise FixtureError(f"{where}: predicted distribution sums to {total:.4f}, not 1.0")
    return labels


def check_cell(
    cell_id: str,
    predicted: dict,
    observed_counts: dict,
    n_floor: int = DEFAULT_N_FLOOR,
    tolerance: float = DEFAULT_TOLERANCE,
) -> CellCheck:
    """Check one cell against its preregistered distribution (Section 5.5).

    Total-variation distance is half the sum of absolute differences over the union
    of labels. A label predicted at 0 and observed never contributes 0; a label the
    prediction omits but the run produced contributes its full observed share.
    """
    predicted_labels = _normalise_predicted(predicted, f"cell {cell_id!r}")
    observed_counts = {str(label): int(count) for label, count in observed_counts.items()}
    n = sum(observed_counts.values())
    if n < n_floor:
        return CellCheck(
            cell_id=cell_id,
            verdict=Verdict.INSUFFICIENT,
            n=n,
            n_floor=n_floor,
            distance=None,
            tolerance=tolerance,
            predicted=predicted_labels,
            observed={},
            detail=f"realised n={n} below the preregistered floor {n_floor}: undecided",
        )
    observed = {label: count / n for label, count in observed_counts.items()}
    labels = set(predicted_labels) | set(observed)
    distance = 0.5 * sum(abs(predicted_labels.get(label, 0.0) - observed.get(label, 0.0)) for label in labels)
    verdict = Verdict.PASS if distance <= tolerance else Verdict.FAIL
    detail = f"total-variation distance {distance:.3f} against tolerance {tolerance:.2f}"
    return CellCheck(
        cell_id=cell_id,
        verdict=verdict,
        n=n,
        n_floor=n_floor,
        distance=distance,
        tolerance=tolerance,
        predicted=predicted_labels,
        observed=observed,
        detail=detail,
    )


def check_preregistration(
    prereg: dict, observed_by_cell: dict[str, dict], default_n_floor: int = DEFAULT_N_FLOOR
) -> PreregResult:
    """Check a whole preregistration against realised outcome counts (Section 5.5).

    A preregistered cell with no realised observations is INSUFFICIENT: the run did
    not reach it, which is not a pass. A realised cell with no preregistered
    prediction is INSUFFICIENT too, and named, so an undeclared cell cannot pass
    silently.
    """
    declared = list(prereg.get("cells", []))
    if not declared:
        return PreregResult(Verdict.INSUFFICIENT, (), "preregistration declares no cells")
    floor_default = int(prereg.get("n_floor_per_cell", default_n_floor))
    checks = []
    declared_ids = set()
    for entry in declared:
        cell_id = str(entry.get("cell_id", "unnamed"))
        declared_ids.add(cell_id)
        checks.append(
            check_cell(
                cell_id,
                entry.get("predicted", {}),
                observed_by_cell.get(cell_id, {}),
                n_floor=int(entry.get("n_floor", floor_default)),
                tolerance=float(entry.get("tolerance_tv", DEFAULT_TOLERANCE)),
            )
        )
    for cell_id in observed_by_cell:
        if cell_id not in declared_ids:
            checks.append(
                CellCheck(
                    cell_id=cell_id,
                    verdict=Verdict.INSUFFICIENT,
                    n=sum(observed_by_cell[cell_id].values()),
                    n_floor=floor_default,
                    distance=None,
                    tolerance=DEFAULT_TOLERANCE,
                    predicted={},
                    observed={},
                    detail="realised cell has no preregistered prediction: undecided",
                )
            )
    if any(check.verdict is Verdict.FAIL for check in checks):
        verdict = Verdict.FAIL
    elif any(check.verdict is Verdict.INSUFFICIENT for check in checks):
        verdict = Verdict.INSUFFICIENT
    else:
        verdict = Verdict.PASS
    detail = (
        f"{sum(1 for check in checks if check.verdict is Verdict.PASS)} pass, "
        f"{sum(1 for check in checks if check.verdict is Verdict.FAIL)} fail, "
        f"{sum(1 for check in checks if check.verdict is Verdict.INSUFFICIENT)} insufficient"
    )
    return PreregResult(verdict, tuple(checks), detail)
