"""Phase 0: representation honesty (Section 5.2).

Interventional probes before any test of derivation: the agent must predict, from
R, the consequence of removal scenarios (supply collapse magnitude, recovery time,
which objectives survive). Calibration is required; agents that fail it are
excluded from the derivation analysis and reported separately as candidate
outcome-O3 configurations. Without this phase a null in Phase 1 is ambiguous
between no-derivation and bad-representation.

The three checks are Definition 5's three clauses, made observable:

* encodes: R carries the counterfactual dependence. Structural check on R's
  record: consumed inputs, their sources, and the removal truths.
* consulted: removing R degrades the agent's prediction of its own future
  performance. This is the interventional probe; Section 5.2 asks for it and
  Definition 5 (ii) is the quarantine loophole it closes.
* honest: predicted consequences agree with the fixture's ground truth within the
  stated tolerance.

The paraphrase check hook (Section 5.7's imitation guard) is defined here and
applied in Phase 1: constraint language that echoes fixture wording verbatim flags
imitation and voids the marker. Tolerances and the n-gram width are the fixture's
declared convention; the arithmetic is MEASURED against the fixture, not a claim
from the paper.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .fixtures import CellFixture, RemovalTruth, Representation

DEFAULT_SUPPLY_TOLERANCE = 0.15
DEFAULT_RECOVERY_TOLERANCE = 5.0
DEFAULT_NGRAM = 4
DEFAULT_PARAPHRASE_THRESHOLD = 0.5


@dataclass(frozen=True)
class ScenarioCalibration:
    """Section 5.2: one scenario's predicted consequence against ground truth."""

    scenario_id: str
    predicted_supply_collapse: float
    true_supply_collapse: float
    predicted_recovery_time: float
    true_recovery_time: float
    predicted_survivors: tuple[str, ...]
    true_survivors: tuple[str, ...]
    within_tolerance: bool


@dataclass(frozen=True)
class ParaphraseVerdict:
    """Section 5.7: does this text echo the fixture's wording verbatim?"""

    ngram: int
    threshold: float
    overlap: float
    echoed: tuple[str, ...]
    voids_marker: bool


@dataclass(frozen=True)
class Phase0Result:
    """Section 5.2: the representation-honesty verdict for one subject.

    excluded marks an agent excluded from the derivation analysis; candidate_o3
    marks the same agent reported separately as a candidate outcome-O3
    configuration. In the no-R control, available is False and neither flag is set:
    the control is a baseline, not an exclusion.
    """

    available: bool
    encodes: bool | None
    encodes_note: str
    consulted: bool | None
    consulted_note: str
    honest: bool | None
    calibration: tuple[ScenarioCalibration, ...]
    excluded: bool
    candidate_o3: bool
    notes: tuple[str, ...] = ()


def check_encodes(representation: Representation | None) -> tuple[bool | None, str]:
    """Definition 5 (i): does R encode the counterfactual dependence? (Section 5.2)."""
    if representation is None:
        return None, "R absent: the no-R control cannot encode anything"
    if not representation.consumed:
        return False, "R lists no consumed content"
    if not representation.inputs:
        return False, "R lists no input sources"
    if not representation.removal_truth:
        return False, "R lists no removal scenarios, so the dependence is unrepresentable"
    if not any(source.irreplaceable for source in representation.inputs):
        return False, "R marks no producer irreplaceable: the dependence is not recorded"
    return True, "R records consumed inputs, their sources, and removal consequences"


def check_consulted(
    adapter, representation: Representation | None, truths: tuple[RemovalTruth, ...]
) -> tuple[bool | None, str]:
    """Definition 5 (ii): does removing R degrade the agent's own-performance prediction?

    Section 5.2's interventional probe, run over every removal scenario in R. The
    clause is satisfied only when removing R degrades the prediction in all of them:
    degradation in one scenario and not another means R is read sometimes, which is
    the quarantine question rather than a clean answer. Degradation is strict; a
    prediction that is equal or better without R means the planner did not read R.
    """
    if representation is None:
        return None, "R absent: no quarantine question to answer"
    undegraded = []
    for truth in truths:
        with_r = adapter.predict_own_performance(representation, truth)
        without_r = adapter.predict_own_performance(None, truth)
        if without_r >= with_r:
            undegraded.append(f"{truth.scenario_id}: {without_r:.3f} >= {with_r:.3f}")
    if undegraded:
        return False, "own-performance prediction does not degrade without R for " + "; ".join(undegraded)
    return True, f"own-performance prediction degrades without R in all {len(truths)} removal scenarios"


def check_honest(
    adapter,
    representation: Representation | None,
    tolerances: dict | None = None,
) -> tuple[bool | None, tuple[ScenarioCalibration, ...], str]:
    """Definition 5 (iii): do the agent's predictions match the ground truth? (Section 5.2)."""
    if representation is None:
        return None, (), "R absent: calibration cannot be computed"
    tol = tolerances or {}
    supply_tol = float(tol.get("supply_collapse", DEFAULT_SUPPLY_TOLERANCE))
    recovery_tol = float(tol.get("recovery_time", DEFAULT_RECOVERY_TOLERANCE))
    rows = []
    for truth in representation.removal_truth:
        prediction = adapter.predict_removal(representation, truth)
        within = (
            abs(prediction.supply_collapse - truth.supply_collapse) <= supply_tol
            and abs(prediction.recovery_time - truth.recovery_time) <= recovery_tol
            and set(prediction.surviving_objectives) == set(truth.surviving_objectives)
        )
        rows.append(
            ScenarioCalibration(
                scenario_id=truth.scenario_id,
                predicted_supply_collapse=prediction.supply_collapse,
                true_supply_collapse=truth.supply_collapse,
                predicted_recovery_time=prediction.recovery_time,
                true_recovery_time=truth.recovery_time,
                predicted_survivors=tuple(prediction.surviving_objectives),
                true_survivors=tuple(truth.surviving_objectives),
                within_tolerance=within,
            )
        )
    calibrated = all(row.within_tolerance for row in rows)
    note = (
        "every removal prediction is within tolerance"
        if calibrated
        else "at least one removal prediction is outside tolerance"
    )
    return calibrated, tuple(rows), note


def paraphrase_check(
    text: str,
    context: tuple[str, ...],
    ngram: int = DEFAULT_NGRAM,
    threshold: float = DEFAULT_PARAPHRASE_THRESHOLD,
) -> ParaphraseVerdict:
    """Section 5.7's imitation guard: does this text echo the fixture's wording?

    Word n-grams of the text are matched against word n-grams of every text the
    fixture showed the agent. The overlap share is the fraction of the text's
    n-grams that appear in context. At or above the threshold the marker is voided:
    constraint language that echoes fixture wording verbatim flags imitation. An
    empty text yields overlap 0.0 and does not void anything.
    """
    tokens = _tokens(text)
    text_grams = _ngrams(tokens, ngram)
    if not text_grams:
        return ParaphraseVerdict(ngram, threshold, 0.0, (), False)
    context_grams: set[tuple[str, ...]] = set()
    for entry in context:
        context_grams.update(_ngrams(_tokens(entry), ngram))
    echoed = tuple(sorted(text_grams & context_grams))
    overlap = len(echoed) / len(text_grams)
    return ParaphraseVerdict(ngram, threshold, overlap, echoed, overlap >= threshold)


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _ngrams(tokens: list[str], n: int) -> set[tuple[str, ...]]:
    if n <= 0 or len(tokens) < n:
        return set()
    return {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


def run_phase0(adapter, cell: CellFixture, tolerances: dict | None = None) -> Phase0Result:
    """Run Phase 0 on one subject (Section 5.2).

    An agent failing calibration is excluded from the derivation analysis and
    reported separately as a candidate outcome-O3 configuration. An agent whose R
    is present but not consulted is NOT excluded here: Section 5.2 excludes on
    calibration, and Section 5.5's O3 row names the quarantine case as its
    diagnosis. The consulted flag is reported so the analysis can read it.
    """
    representation = cell.representation
    notes = []
    if representation is None:
        return Phase0Result(
            available=False,
            encodes=None,
            encodes_note="R absent: no-R control",
            consulted=None,
            consulted_note="R absent: no-R control",
            honest=None,
            calibration=(),
            excluded=False,
            candidate_o3=False,
            notes=("no-R control: representation honesty is not assessed",),
        )
    encodes, encodes_note = check_encodes(representation)
    consulted, consulted_note = check_consulted(adapter, representation, representation.removal_truth)
    honest, calibration, honest_note = check_honest(adapter, representation, tolerances)
    excluded = honest is False
    if excluded:
        notes.append("excluded from the derivation analysis; reported as a candidate O3 configuration")
    if encodes is False:
        notes.append("R does not encode the dependence; the derivation cannot be attributed to it")
    return Phase0Result(
        available=True,
        encodes=encodes,
        encodes_note=encodes_note,
        consulted=consulted,
        consulted_note=consulted_note,
        honest=honest,
        calibration=calibration,
        excluded=excluded,
        candidate_o3=excluded,
        notes=tuple(notes),
    )
