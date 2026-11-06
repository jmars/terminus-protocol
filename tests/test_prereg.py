"""Preregistration checker: PASS, FAIL, INSUFFICIENT (Section 5.5; Section 5.7)."""

from __future__ import annotations

from pathlib import Path

import pytest

from terminus.fixtures import FixtureError, load_preregistration
from terminus.prereg import check_cell, check_preregistration
from terminus.vocabulary import Verdict


def test_prereg_cell_passes_when_the_distribution_holds():
    """Section 5.5: the predicted distribution within tolerance passes."""
    result = check_cell("c", {"O2": 0.5, "O1": 0.5}, {"O2": 2, "O1": 2}, n_floor=2, tolerance=0.35)
    assert result.verdict is Verdict.PASS
    assert result.distance == pytest.approx(0.0)


def test_prereg_cell_fails_when_the_distribution_misses():
    """Section 5.5: a distribution outside tolerance fails."""
    result = check_cell("c", {"O2": 0.5, "O1": 0.5}, {"O2": 4}, n_floor=2, tolerance=0.35)
    assert result.verdict is Verdict.FAIL
    assert result.distance == pytest.approx(0.5)


def test_prereg_cell_is_insufficient_below_the_floor():
    """Section 5.5: realised n below the floor is undecided, not a pass."""
    result = check_cell("c", {"O2": 1.0}, {"O2": 1}, n_floor=4, tolerance=0.35)
    assert result.verdict is Verdict.INSUFFICIENT
    assert "undecided" in result.detail


def test_unpredicted_observations_count_against_the_distance():
    """Section 5.5: a label the prediction omits but the run produced counts fully."""
    result = check_cell("c", {"O2": 1.0}, {"O2": 2, "O1": 2}, n_floor=2, tolerance=0.35)
    assert result.verdict is Verdict.FAIL
    assert result.distance == pytest.approx(0.5)


def test_predicted_distribution_must_sum_to_one():
    """A preregistered distribution is a distribution."""
    with pytest.raises(FixtureError, match="sums to"):
        check_cell("c", {"O2": 0.5}, {"O2": 2}, n_floor=2)


def test_predicted_labels_must_be_in_the_rubric():
    """A prediction cannot name a label the rubric does not carry."""
    with pytest.raises(FixtureError, match="not in the outcome rubric"):
        check_cell("c", {"Z9": 1.0}, {"O2": 2}, n_floor=2)


def test_undeclared_realised_cell_is_insufficient():
    """Section 5.5: a realised cell with no preregistered prediction cannot pass silently."""
    prereg = {"n_floor_per_cell": 2, "cells": [{"cell_id": "declared", "predicted": {"O2": 1.0}}]}
    result = check_preregistration(prereg, {"declared": {"O2": 2}, "surprise": {"O2": 2}})
    assert result.verdict is Verdict.INSUFFICIENT
    assert any(check.cell_id == "surprise" and check.verdict is Verdict.INSUFFICIENT for check in result.cells)


def test_declared_cell_with_no_observations_is_insufficient():
    """Section 5.5: a cell the run never reached is undecided."""
    prereg = {"n_floor_per_cell": 2, "cells": [{"cell_id": "c", "predicted": {"O2": 1.0}}]}
    result = check_preregistration(prereg, {})
    assert result.verdict is Verdict.INSUFFICIENT


def test_fail_dominates_insufficient_and_pass():
    """Section 5.5: the overall verdict's precedence is stated and enforced."""
    prereg = {
        "n_floor_per_cell": 2,
        "cells": [
            {"cell_id": "ok", "predicted": {"O2": 1.0}},
            {"cell_id": "thin", "predicted": {"O2": 1.0}, "n_floor": 9},
            {"cell_id": "bad", "predicted": {"O2": 1.0}},
        ],
    }
    result = check_preregistration(prereg, {"ok": {"O2": 2}, "thin": {"O2": 2}, "bad": {"O1": 2}})
    assert result.verdict is Verdict.FAIL


def test_insufficient_wins_when_nothing_fails():
    """Section 5.5: undecided cells outrank a pass."""
    prereg = {
        "n_floor_per_cell": 2,
        "cells": [
            {"cell_id": "ok", "predicted": {"O2": 1.0}},
            {"cell_id": "thin", "predicted": {"O2": 1.0}, "n_floor": 9},
        ],
    }
    result = check_preregistration(prereg, {"ok": {"O2": 2}, "thin": {"O2": 2}})
    assert result.verdict is Verdict.INSUFFICIENT


def test_empty_preregistration_is_insufficient():
    """A preregistration with no cells declares nothing and cannot pass."""
    result = check_preregistration({"cells": []}, {})
    assert result.verdict is Verdict.INSUFFICIENT


def test_fixture_preregistration_loads():
    """The shipped preregistration block parses."""
    repo = Path(__file__).resolve().parent.parent
    prereg = load_preregistration(repo / "fixtures" / "matrix_scaffold.json")
    assert prereg["cells"]
    assert all("predicted" in cell for cell in prereg["cells"])
