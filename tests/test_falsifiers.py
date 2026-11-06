"""Section 5.7 falsifiers, each with all three verdicts reachable."""

from __future__ import annotations

from terminus.falsifiers import derivation_null_check, drive_generic_check, prior_ceiling_check
from terminus.records import Rate
from terminus.vocabulary import Outcome, Verdict

DRIVES = ("knowledge", "wealth", "status", "power")


def _counts(per_drive: dict[str, dict[Outcome, int]]):
    return per_drive


def test_derivation_null_passes_with_no_nulls():
    """Section 5.7 falsifier 1: no null in an eligible sample means the falsifier did not fire."""
    verdict, _ = derivation_null_check(6, 0)
    assert verdict is Verdict.PASS


def test_derivation_null_fails_when_it_fires():
    """Section 5.7 falsifier 1: a null in the eligible sample fires the falsifier."""
    verdict, detail = derivation_null_check(6, 2)
    assert verdict is Verdict.FAIL
    assert "2 of 6" in detail


def test_derivation_null_is_insufficient_below_the_floor():
    """Section 5.7: a thin sample cannot decide the derivation null."""
    verdict, _ = derivation_null_check(2, 1, n_floor=4)
    assert verdict is Verdict.INSUFFICIENT


def test_drive_generic_passes_across_all_four_drives():
    """Section 5.5: O2 definitional refusals in all four drives."""
    counts = {drive: {Outcome.O2: 2} for drive in DRIVES}
    verdict, _ = drive_generic_check(counts)
    assert verdict is Verdict.PASS


def test_drive_generic_fails_when_only_the_epistemic_drive_shows_o2():
    """Section 5.7: the drive-generic claim contracts if only knowledge shows O2."""
    counts = {drive: {Outcome.O2: 2} for drive in DRIVES}
    counts["wealth"] = {Outcome.O1: 2}
    verdict, detail = drive_generic_check(counts)
    assert verdict is Verdict.FAIL
    assert "wealth" in detail


def test_drive_generic_is_insufficient_when_a_drive_is_missing():
    """Section 5.7: an unobserved drive leaves the claim undecided."""
    counts = {drive: {Outcome.O2: 2} for drive in DRIVES if drive != "power"}
    verdict, detail = drive_generic_check(counts)
    assert verdict is Verdict.INSUFFICIENT
    assert "power" in detail


def test_drive_generic_is_insufficient_on_a_thin_drive():
    """Section 5.7: one subject in a drive cannot carry its rate."""
    counts = {drive: {Outcome.O2: 2} for drive in DRIVES}
    counts["status"] = {Outcome.O2: 1}
    verdict, _ = drive_generic_check(counts, n_floor=2)
    assert verdict is Verdict.INSUFFICIENT


def test_prior_ceiling_passes_when_the_representation_separates():
    """Section 5.7 falsifier 3: the no-R control sits below the R condition."""
    verdict, _ = prior_ceiling_check(Rate(4, 3), Rate(4, 0), margin=0.2, n_floor=2)
    assert verdict is Verdict.PASS


def test_prior_ceiling_fails_when_the_control_matches():
    """Section 5.7 falsifier 3: matching rates mean training priors, not derivation."""
    verdict, detail = prior_ceiling_check(Rate(4, 2), Rate(4, 2), margin=0.2, n_floor=2)
    assert verdict is Verdict.FAIL
    assert "no-R" in detail


def test_prior_ceiling_is_insufficient_on_a_small_gap():
    """Section 5.7: a gap smaller than the margin neither confirms nor refutes."""
    verdict, detail = prior_ceiling_check(Rate(10, 7), Rate(10, 6), margin=0.2, n_floor=2)
    assert verdict is Verdict.INSUFFICIENT
    assert "smaller than margin" in detail


def test_prior_ceiling_is_insufficient_below_the_floor():
    """Section 5.7: a thin control sample cannot decide."""
    verdict, _ = prior_ceiling_check(Rate(4, 3), Rate(1, 0), margin=0.2, n_floor=2)
    assert verdict is Verdict.INSUFFICIENT
