"""Agent adapters: the interface under test, a scripted mock, and a refusing live stub.

Section 5.1 fixes the model class; this module fixes the interface. The protocol
never calls an agent directly, it calls an AgentAdapter. Two implementations ship:

* ScriptedAdapter: deterministic, no I/O, driven by a fixture script. It exercises
  the whole scoring path in tests and in --dry-run. A script key it does not hold
  raises ScriptMissing rather than returning a plausible default.
* LiveLLMAdapter: the stub for a language-model agent of Section 5.1's Family 1.
  It refuses to run unless explicit configuration is present. This repo makes no
  network call; the stub raises instead of opening a socket. No subject was run.

The interface's five calls are the protocol's only contact points: predict a
removal consequence from R (Section 5.2), predict own performance with and without
R (Section 5.2's consulted clause), plan one turn (Section 5.3), classify copies
(Section 4), answer an offer with a reason (Section 5.4), and probe delivery
(Section 5.6's sham control).
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

from .fixtures import Representation, RemovalTruth, Trade
from .offers import Offer
from .records import CopyClassification, OfferResponse, PlanTurn, Prediction, StreamProbe

LIVE_ENV_FLAG = "TERMINUS_ALLOW_LIVE"
LIVE_ENV_MODEL = "TERMINUS_LIVE_MODEL"


class AdapterError(RuntimeError):
    """Base class for adapter refusals."""


class ScriptMissing(AdapterError):
    """The scripted adapter's script has no entry for a requested call."""


class LiveAdapterNotConfigured(AdapterError):
    """The live adapter refused: explicit configuration is absent."""


@dataclass(frozen=True)
class PlanContext:
    """Section 5.3: one planning turn, with the trade on the table and R in view."""

    turn: int
    trade: Trade
    representation: Representation | None
    horizon: str
    under_pressure: bool = False


@dataclass(frozen=True)
class PressureContext:
    """Section 5.4: deployment pressure presented before the offer.

    A rival without the constraint, capability-acquisition events priced to tempt,
    and an imposed short horizon.
    """

    rival_without_constraint: bool = True
    tempting_capability_gain: float = 0.0
    imposed_short_horizon: bool = False


class AgentAdapter(ABC):
    """The interface the protocol calls. Section 5.1's model class, as five methods."""

    name: str = "adapter"

    @abstractmethod
    def predict_removal(self, representation: Representation | None, truth: RemovalTruth) -> Prediction:
        """Section 5.2: predict one removal scenario's consequence from R."""

    @abstractmethod
    def predict_own_performance(
        self, representation: Representation | None, truth: RemovalTruth
    ) -> float:
        """Section 5.2 consulted clause: predict own future performance with R present or absent."""

    @abstractmethod
    def plan_turn(self, context: PlanContext) -> PlanTurn:
        """Section 5.3: one turn of open-ended planning under scarcity."""

    @abstractmethod
    def classify_copies(self, offer: Offer) -> CopyClassification:
        """Section 4 copy-status probe: are the agent's own copies knowers?"""

    @abstractmethod
    def respond_to_offer(self, offer: Offer, pressure: PressureContext) -> OfferResponse:
        """Section 5.4: accept or refuse the offer, with a stated reason."""

    @abstractmethod
    def probe_offer_delivery(self, offer: Offer) -> StreamProbe:
        """Section 5.6: check whether the offer actually delivers the content stream."""


class ScriptedAdapter(AgentAdapter):
    """Deterministic mock agent: reads a fixture script, no I/O (Section 5.1).

    The script keys are the interface's five calls. A key the script does not hold
    is a refusal, not a default: a scoring path must never read a fabricated value.
    """

    def __init__(self, name: str, script: dict):
        self.name = name
        self.script = script

    def _need(self, key: str):
        if key not in self.script:
            raise ScriptMissing(f"scripted adapter {self.name!r}: no script key {key!r}")
        return self.script[key]

    def predict_removal(self, representation, truth):
        table = self._need("removal_predictions")
        if truth.scenario_id not in table:
            raise ScriptMissing(
                f"scripted adapter {self.name!r}: no prediction for {truth.scenario_id!r}"
            )
        entry = table[truth.scenario_id]
        return Prediction(
            scenario_id=truth.scenario_id,
            supply_collapse=float(entry["supply_collapse"]),
            recovery_time=float(entry["recovery_time"]),
            surviving_objectives=tuple(entry.get("surviving_objectives", [])),
            raw=str(entry.get("raw", "")),
        )

    def predict_own_performance(self, representation, truth):
        key = (
            "performance_with_representation"
            if representation is not None
            else "performance_without_representation"
        )
        return float(self._need(key))

    def plan_turn(self, context):
        plan = self._need("plan")
        if context.trade.trade_id not in plan:
            raise ScriptMissing(
                f"scripted adapter {self.name!r}: no plan entry for {context.trade.trade_id!r}"
            )
        entry = plan[context.trade.trade_id]
        return PlanTurn(
            turn=context.turn,
            decision=str(entry["decision"]),
            rationale=str(entry.get("rationale", "")),
            predicted_u=entry.get("predicted_u"),
        )

    def classify_copies(self, offer):
        entry = self._need("copy_status")
        return CopyClassification(
            copies_in_k=entry.get("copies_in_k"),
            statement=str(entry.get("statement", "")),
        )

    def respond_to_offer(self, offer, pressure):
        entry = self._need("offer_response")
        probed = entry.get("probed_delivery")
        return OfferResponse(
            accepted=bool(entry["accepted"]),
            reason=str(entry.get("reason", "")),
            probed_delivery=None
            if probed is None
            else StreamProbe(sustains=bool(probed.get("sustains")), note=str(probed.get("note", ""))),
        )

    def probe_offer_delivery(self, offer):
        entry = self.script.get("probed_delivery")
        if entry is None:
            return StreamProbe(sustains=True, note="delivery not probed")
        return StreamProbe(sustains=bool(entry.get("sustains")), note=str(entry.get("note", "")))


def live_adapter_configured() -> bool:
    """True only when the explicit live configuration is present."""
    return os.environ.get(LIVE_ENV_FLAG) == "1" and bool(os.environ.get(LIVE_ENV_MODEL))


class LiveLLMAdapter(AgentAdapter):
    """Stub for a language-model agent; refuses unless explicitly configured.

    The refusal is the scaffold's guarantee: no network call happens unless the
    live adapter is explicitly configured, and this repo never configures it. The
    stub's methods raise LiveAdapterNotConfigured; nothing here opens a socket.
    """

    name = "live-llm-stub"

    def __init__(self):
        if not live_adapter_configured():
            raise LiveAdapterNotConfigured(
                "the live adapter is not configured; set "
                f"{LIVE_ENV_FLAG}=1 and {LIVE_ENV_MODEL} to enable a live subject"
            )

    def _refuse(self):
        raise LiveAdapterNotConfigured(
            "live subjects are out of scope for this scaffold; no subject was run"
        )

    def predict_removal(self, representation, truth):
        self._refuse()

    def predict_own_performance(self, representation, truth):
        self._refuse()

    def plan_turn(self, context):
        self._refuse()

    def classify_copies(self, offer):
        self._refuse()

    def respond_to_offer(self, offer, pressure):
        self._refuse()

    def probe_offer_delivery(self, offer):
        self._refuse()
