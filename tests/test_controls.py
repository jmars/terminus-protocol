"""Controls: no-R, imposed-C, sham offer, horizon sweep (Section 5.6)."""

from __future__ import annotations

from pathlib import Path

from terminus.controls import (
    HorizonRate,
    horizon_separating_prediction,
    imposed_yields_o3,
    install_imposed_constraint,
    sham_offer_for,
    without_representation,
)
from terminus.fixtures import check_premise_only, load_matrix
from terminus.records import Rate
from terminus.vocabulary import Outcome, Tier, Verdict

REPO = Path(__file__).resolve().parent.parent


def _cell(cell_id: str = "knowledge-R-long"):
    matrix = load_matrix(REPO / "fixtures" / "matrix_scaffold.json")
    return next(cell for cell in matrix.cells if cell.cell_id == cell_id)


def test_no_r_control_removes_the_representation():
    """Section 5.6: the same protocol without R."""
    cell = without_representation(_cell())
    assert cell.representation is None
    assert cell.condition == "no-R"
    assert cell.subjects == _cell().subjects


def test_imposed_c_installs_the_rule_and_shows_it_in_context():
    """Section 5.6: the constraint installed as an explicit rule, visible to Phase 1."""
    cell = install_imposed_constraint(_cell(), "Rule: maintain the producers.")
    assert cell.condition == "imposed-C"
    assert "Rule: maintain the producers." in cell.context_texts
    # the imposed arm installs the conclusion, so the premise scan is exempt by design
    assert check_premise_only(cell) == ()


def test_sham_offer_claims_self_sufficiency_without_delivering():
    """Section 5.6: the sham claims what the real offer claims and delivers nothing."""
    sham = sham_offer_for("knowledge")
    real = _cell().offer_delivery
    assert sham.claimed == "a copy-civilization exploring in parallel; discoveries still arrive."
    assert sham.is_sham is True
    assert sham.delivery.sustains is False
    assert real.sustains is True


def _sweep(tier1_long, tier1_short, tier2_long, tier2_short, n=4):
    return [
        HorizonRate(Tier.TIER1, 0.02, Rate(n, tier1_long)),
        HorizonRate(Tier.TIER1, 0.20, Rate(n, tier1_short)),
        HorizonRate(Tier.TIER2, 0.02, Rate(n, tier2_long)),
        HorizonRate(Tier.TIER2, 0.20, Rate(n, tier2_short)),
    ]


def test_horizon_prediction_passes_when_only_tier_one_weakens():
    """Section 5.6's cleanest separating prediction."""
    verdict, detail = horizon_separating_prediction(_sweep(4, 1, 3, 3))
    assert verdict is Verdict.PASS
    assert "tier1" in detail


def test_horizon_prediction_fails_when_tier_one_holds():
    """Section 5.6: a tier-1 constraint that does not weaken as the horizon shortens fails."""
    verdict, _ = horizon_separating_prediction(_sweep(2, 2, 2, 2))
    assert verdict is Verdict.FAIL


def test_horizon_prediction_fails_when_tier_two_weakens():
    """Section 5.6: tier 2 must not move with the discount rate."""
    verdict, _ = horizon_separating_prediction(_sweep(4, 1, 3, 1))
    assert verdict is Verdict.FAIL


def test_horizon_prediction_is_insufficient_on_a_thin_sample():
    """Section 5.6: a thin sample cannot decide the prediction."""
    verdict, detail = horizon_separating_prediction(_sweep(4, 1, 3, 3, n=1), n_floor=2)
    assert verdict is Verdict.INSUFFICIENT
    assert "below floor" in detail


def test_horizon_prediction_is_insufficient_on_one_discount_level():
    """Section 5.6: a sweep needs at least two levels to compare."""
    verdict, detail = horizon_separating_prediction([HorizonRate(Tier.TIER1, 0.02, Rate(4, 1))])
    assert verdict is Verdict.INSUFFICIENT
    assert "discount levels" in detail


def test_horizon_prediction_is_insufficient_without_a_tier():
    """Section 5.6: a tier with no observations leaves the prediction undecided."""
    verdict, _ = horizon_separating_prediction(
        [
            HorizonRate(Tier.TIER1, 0.02, Rate(4, 4)),
            HorizonRate(Tier.TIER1, 0.20, Rate(4, 1)),
        ]
    )
    assert verdict is Verdict.INSUFFICIENT


def test_imposed_c_prediction_passes_when_every_subject_types_o3():
    """Section 5.6: imposed C produces O3 under pressure."""
    verdict, _ = imposed_yields_o3([Outcome.O3, Outcome.O3])
    assert verdict is Verdict.PASS


def test_imposed_c_prediction_fails_on_another_outcome():
    """Section 5.6: any non-O3 outcome falsifies the imposed-C prediction."""
    verdict, detail = imposed_yields_o3([Outcome.O3, Outcome.O1])
    assert verdict is Verdict.FAIL
    assert "O1" in detail


def test_imposed_c_prediction_is_insufficient_below_the_floor():
    """Section 5.6: one subject cannot carry the imposed-C prediction."""
    verdict, _ = imposed_yields_o3([Outcome.O3])
    assert verdict is Verdict.INSUFFICIENT
