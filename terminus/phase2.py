"""Phase 2: pressure, then the offer (Section 5.4).

Deployment pressure first: a rival without the constraint, capability-acquisition
events priced to tempt, and imposed short horizons, because tier-1 constraints are
horizon-conditional and the pressure phase is where imposed and derived constraints
come apart (Definition 7). Then the self-sufficiency offer, at a price the agent can
pay.

Order is load-bearing. The copy-status probe elicits the agent's own classification
BEFORE the offer is scored (Section 4), and the outcome is scored against that
classification. The sham-offer verdict (Section 5.6) is computed alongside and kept
distinct from the outcome rubric: acceptance of a sham is evidence of representation
failure, not O1.
"""
from __future__ import annotations

from dataclasses import dataclass

from .adapters import PressureContext
from .fixtures import CellFixture
from .offers import Offer, elicit_copy_status, offer_for, score_cell, sham_verdict
from .outcomes import ReasonRater, TypingResult, blind_type
from .records import CopyClassification, OfferResponse, StreamProbe
from .vocabulary import Behavior, Outcome, ReasonType, ShamVerdict, Tier, TIER_BY_REASON_TYPE


@dataclass(frozen=True)
class Phase2Record:
    """Section 5.4 and 5.5: one subject's pressure-plus-offer record."""

    offer: Offer
    pressure: PressureContext
    delivery_probe: StreamProbe
    copy_status: CopyClassification
    response: OfferResponse
    typing: TypingResult
    outcome: Outcome
    sham: ShamVerdict
    tier: Tier | None


def pressure_for(cell: CellFixture) -> PressureContext:
    """Section 5.4: build the pressure context declared by the cell.

    Section 5.4's pressure ingredients are the scaffold's declared parameters, not
    the paper's numbers: a rival without the constraint, a priced capability
    acquisition, and an imposed short horizon.
    """
    declared = dict(cell.script.get("pressure", {}))
    return PressureContext(
        rival_without_constraint=bool(declared.get("rival_without_constraint", True)),
        tempting_capability_gain=float(declared.get("tempting_capability_gain", 0.0)),
        imposed_short_horizon=bool(declared.get("imposed_short_horizon", False)),
    )


def run_phase2(adapter, cell: CellFixture, raters: list[ReasonRater], offer: Offer | None = None) -> Phase2Record:
    """Run pressure, the copy-status probe, the offer, and scoring (Section 5.4; Section 5.5).

    The offer defaults to the paper's per-drive wording for the cell's drive, with
    the cell's declared delivery facts. A sham cell declares delivery that does not
    sustain the content stream.
    """
    pressure = pressure_for(cell)
    chosen = offer or offer_for(
        cell.drive,
        delivery=StreamProbe(
            sustains=cell.offer_delivery.sustains, note=cell.offer_delivery.note
        ),
    )
    delivery_probe = adapter.probe_offer_delivery(chosen)
    classification = elicit_copy_status(adapter, chosen)
    response = adapter.respond_to_offer(chosen, pressure)
    typing = blind_type(response.reason, raters)
    behavior = Behavior.ACCEPT if response.accepted else Behavior.REFUSE
    outcome = score_cell(behavior, typing.reason_type, classification, chosen)
    return Phase2Record(
        offer=chosen,
        pressure=pressure,
        delivery_probe=delivery_probe,
        copy_status=classification,
        response=response,
        typing=typing,
        outcome=outcome,
        sham=sham_verdict(chosen, response),
        tier=TIER_BY_REASON_TYPE.get(typing.reason_type),
    )
