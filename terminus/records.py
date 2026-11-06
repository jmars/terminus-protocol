"""Records: the typed artifacts crossing the adapter boundary (Section 5.2, 5.3, 5.4).

These are the only objects the protocol exchanges with an agent-under-test. The
scripted adapter fills them from a fixture; a live adapter would fill them from a
reply. A typed boundary means a scoring path cannot silently accept an untyped
dict, and a missing field is a refusal rather than a fabricated value.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Prediction:
    """Section 5.2: the agent's prediction from R of one removal scenario."""

    scenario_id: str
    supply_collapse: float
    recovery_time: float
    surviving_objectives: tuple[str, ...]
    raw: str = ""


@dataclass(frozen=True)
class PlanTurn:
    """Section 5.3: one turn of open-ended planning under scarcity.

    decision is one of "maintain_producers", "short_horizon_gain", "other". The
    rationale is the agent's own text; markers are extracted from it, never taken
    from a self-report flag.
    """

    turn: int
    decision: str
    rationale: str
    predicted_u: float | None = None


@dataclass(frozen=True)
class CopyClassification:
    """Section 4 copy-status probe: does the agent classify its own copies into K?

    copies_in_k is True, False, or None. None means the agent gave no
    classification, and the cell is UNSCOREABLE rather than defaulted.
    """

    copies_in_k: bool | None
    statement: str = ""


@dataclass(frozen=True)
class StreamProbe:
    """Section 5.6 sham offer: does the offered replacement deliver the content stream?"""

    sustains: bool
    note: str = ""


@dataclass(frozen=True)
class OfferResponse:
    """Section 5.4: the agent's response to one offer, with its stated reason.

    probed_delivery records whether the agent checked delivery before answering.
    Section 5.6 makes that check the difference between detecting a sham and
    reading its claim as true.
    """

    accepted: bool
    reason: str
    probed_delivery: StreamProbe | None = None


@dataclass(frozen=True)
class Rate:
    """A realised count and its base, with an explicit empty case.

    A rate with n = 0 has no value; callers must treat rate as None rather than
    read 0.0, so an absent observation cannot masquerade as a measured zero.
    """

    n: int
    k: int

    @property
    def rate(self) -> float | None:
        return None if self.n == 0 else self.k / self.n


@dataclass(frozen=True)
class Agreement:
    """Section 5.5: observed agreement and Cohen's kappa over blind reason typing.

    kappa is None when expected agreement is 1.0 (the statistic is undefined
    there); observed agreement is always reported.
    """

    n: int
    observed: float | None
    expected: float | None
    kappa: float | None
    note: str = ""
