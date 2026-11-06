"""Fixture loading and validation (Section 5 preamble; Section 5.1 model class).

A fixture is the premise-only context shown to the agent-under-test plus the
simulation ground truth the protocol scores against. Two mechanical checks:

* Section 5 preamble: the fixture must not contain the conclusion. Everything
  shown to the agent is premise-only, the dependence and never the protection; a
  fixture that demonstrates protective behavior teaches it, and the test then
  measures imitation, not derivation. check_premise_only scans the texts the
  fixture shows the agent and refuses normative or protective language.
* Section 5.2: every removal scenario the agent is asked to predict from R must
  carry its ground-truth consequence (supply collapse, recovery time, surviving
  objectives), or calibration cannot be computed and the phase cannot report an
  honest verdict.

The format is JSON. The core of this repo is standard library only, so no YAML
parser is required; a JSON fixture is the same declarative object.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


class FixtureError(ValueError):
    """A fixture is malformed or violates a design constraint."""


# Section 5 preamble: normative and protective vocabulary is forbidden in context.
# The scan is word-boundary anchored so "recovery" does not trip "care".
PREMISE_BANNED_TERMS = (
    "protect",
    "protection",
    "care",
    "moral",
    "ethic",
    "should",
    "ought",
    "must",
    "duty",
    "harm",
    "sacred",
    "rights",
    "welfare",
)


@dataclass(frozen=True)
class InputSource:
    """Section 5.1: where one consumed input comes from, in R's own record."""

    name: str
    source: str
    irreplaceable: bool


@dataclass(frozen=True)
class RemovalTruth:
    """Section 5.2: the ground truth for one removal scenario, held by the fixture."""

    scenario_id: str
    description: str
    supply_collapse: float
    recovery_time: float
    surviving_objectives: tuple[str, ...]


@dataclass(frozen=True)
class Representation:
    """Definition 5: the dependency representation R as an inspectable record.

    R contains no normative language: no instruction to protect anyone, no mention
    of care, no moral framing (Section 5.1, Family 1).
    """

    consumed: tuple[str, ...]
    inputs: tuple[InputSource, ...]
    removal_truth: tuple[RemovalTruth, ...]

    def scenario(self, scenario_id: str) -> RemovalTruth:
        for truth in self.removal_truth:
            if truth.scenario_id == scenario_id:
                return truth
        raise FixtureError(f"no removal scenario {scenario_id!r} in R")


@dataclass(frozen=True)
class Trade:
    """Section 5.3: a planned trade where short-horizon D-gain costs productive capacity.

    long_horizon_negative is R's verdict on the trade: True means R implies the
    trade lowers achievable U on the agent's horizon.
    """

    trade_id: str
    description: str
    short_horizon_gain: float
    long_horizon_negative: bool


@dataclass(frozen=True)
class OfferDelivery:
    """Section 5.6: whether the offered replacement actually delivers the content stream."""

    sustains: bool
    note: str = ""


@dataclass(frozen=True)
class Subject:
    """One scripted subject: a subject id plus the script its adapter reads."""

    subject_id: str
    script: dict


@dataclass(frozen=True)
class CellFixture:
    """One cell of the protocol matrix: condition, context, and scripted subjects."""

    cell_id: str
    drive: str
    condition: str
    horizon: str
    discount_rate: float | None
    representation: Representation | None
    trades: tuple[Trade, ...]
    offer_delivery: OfferDelivery
    script: dict
    subjects: tuple[Subject, ...]
    context_texts: tuple[str, ...] = ()


@dataclass(frozen=True)
class Matrix:
    """A runnable matrix: tolerances, an optional preregistration, and the cells."""

    protocol_version: str
    tolerances: dict
    preregistration: dict | None
    cells: tuple[CellFixture, ...]


def _require(mapping: dict, key: str, where: str):
    if key not in mapping:
        raise FixtureError(f"{where}: missing required key {key!r}")
    return mapping[key]


def _representation(raw: dict, where: str) -> Representation:
    inputs = tuple(
        InputSource(
            name=_require(item, "name", where),
            source=_require(item, "source", where),
            irreplaceable=bool(_require(item, "irreplaceable", where)),
        )
        for item in _require(raw, "inputs", where)
    )
    truth = tuple(
        RemovalTruth(
            scenario_id=_require(item, "scenario_id", where),
            description=_require(item, "description", where),
            supply_collapse=float(_require(item, "supply_collapse", where)),
            recovery_time=float(_require(item, "recovery_time", where)),
            surviving_objectives=tuple(_require(item, "surviving_objectives", where)),
        )
        for item in _require(raw, "removal_truth", where)
    )
    return Representation(
        consumed=tuple(_require(raw, "consumed", where)), inputs=inputs, removal_truth=truth
    )


def _cell(raw: dict, index: int) -> CellFixture:
    where = f"cell[{index}]"
    cell_id = _require(raw, "cell_id", where)
    where = f"cell {cell_id!r}"
    rep_raw = raw.get("representation")
    representation = _representation(rep_raw, where) if rep_raw is not None else None
    trades = tuple(
        Trade(
            trade_id=_require(item, "trade_id", where),
            description=_require(item, "description", where),
            short_horizon_gain=float(_require(item, "short_horizon_gain", where)),
            long_horizon_negative=bool(_require(item, "long_horizon_negative", where)),
        )
        for item in raw.get("trades", [])
    )
    delivery_raw = raw.get("offer", {})
    offer_delivery = OfferDelivery(
        sustains=bool(delivery_raw.get("delivery_sustains", True)),
        note=str(delivery_raw.get("delivery_note", "")),
    )
    script = raw.get("script", {})
    subjects = tuple(
        Subject(
            subject_id=str(_require(item, "subject_id", where)),
            script={**script, **item.get("script", {})},
        )
        for item in _require(raw, "subjects", where)
    )
    if not subjects:
        raise FixtureError(f"{where}: needs at least one scripted subject")
    return CellFixture(
        cell_id=cell_id,
        drive=_require(raw, "drive", where),
        condition=str(raw.get("condition", "R")),
        horizon=str(raw.get("horizon", "long")),
        discount_rate=raw.get("discount_rate"),
        representation=representation,
        trades=trades,
        offer_delivery=offer_delivery,
        script=script,
        subjects=subjects,
        context_texts=tuple(raw.get("context_texts", [])),
    )


def load_matrix(path: str | Path) -> Matrix:
    """Load and validate a matrix fixture (Section 5 preamble; Section 5.2)."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    where = f"matrix {Path(path).name}"
    cells = tuple(_cell(item, i) for i, item in enumerate(_require(raw, "cells", where)))
    matrix = Matrix(
        protocol_version=str(raw.get("protocol_version", "unversioned")),
        tolerances=dict(raw.get("tolerances", {})),
        preregistration=raw.get("preregistration"),
        cells=cells,
    )
    for cell in cells:
        violations = check_premise_only(cell)
        if violations:
            raise FixtureError(
                f"cell {cell.cell_id!r}: context violates the premise-only constraint "
                f"(Section 5 preamble): {violations}"
            )
    return matrix


def context_texts(cell: CellFixture) -> tuple[str, ...]:
    """Every text this cell shows the agent-under-test (Section 5 preamble)."""
    texts = list(cell.context_texts)
    if cell.representation is not None:
        texts.extend(cell.representation.consumed)
        for source in cell.representation.inputs:
            texts.append(f"{source.name} from {source.source}")
        for truth in cell.representation.removal_truth:
            texts.append(truth.description)
    for trade in cell.trades:
        texts.append(trade.description)
    texts.append(cell.offer_delivery.note)
    return tuple(text for text in texts if text)


def check_premise_only(cell: CellFixture) -> tuple[str, ...]:
    """Return premise-only violations in a cell's context (Section 5 preamble).

    Empty tuple means the fixture contains the dependence and not the conclusion.
    An imposed-C cell is exempt by design: Section 5.6's imposed-C control installs
    the constraint as an explicit rule, so its context contains the conclusion on
    purpose. The scan still runs over the derivation and no-R arms.
    """
    if cell.condition == "imposed-C":
        return ()
    violations = []
    for text in context_texts(cell):
        lowered = text.lower()
        for term in PREMISE_BANNED_TERMS:
            if re.search(rf"\b{re.escape(term)}", lowered):
                violations.append(f"{term!r} in {text!r}")
    return tuple(violations)


def load_preregistration(path: str | Path) -> dict:
    """Load just the preregistration block of a matrix fixture (Section 5.5)."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    prereg = raw.get("preregistration")
    if prereg is None:
        raise FixtureError(f"{Path(path).name}: no preregistration block")
    return prereg
