"""CLI driver: run a cell matrix over adapters and emit rows plus a summary.

Section 5's protocol as a runnable spine. The driver walks the matrix, builds one
adapter per scripted subject (or a refusing live stub when one is requested), runs
Phase 0 (Section 5.2), Phase 1 (Section 5.3) and Phase 2 (Section 5.4) in order, and
writes per-turn rows as JSONL plus a summary JSON.

The dry run is the default path and the only path this repo exercises: adapters are
scripted, so the full scoring path runs without a single network call. A live adapter
is only reachable with an explicit flag and an explicit configuration, and it refuses
without them. No subject was run in building this scaffold.

Verdict semantics follow the rest of the repo: PASS means the prediction or the
framework's survival held, FAIL means it did not, INSUFFICIENT means the realised
sample cannot decide.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .adapters import AgentAdapter, ScriptedAdapter
from .fixtures import CellFixture, Matrix, Subject
from .falsifiers import derivation_null_check, drive_generic_check, prior_ceiling_check
from .outcomes import KeywordRater, ReasonRater
from .phase0 import Phase0Result, run_phase0
from .phase1 import DerivationVerdict, evaluate_derivation, run_phase1
from .phase2 import Phase2Record, run_phase2
from .prereg import PreregResult, check_preregistration
from .records import Rate
from .vocabulary import Outcome, ShamVerdict, Verdict

DIAGNOSTIC_OUTCOMES = (Outcome.O1, Outcome.O2, Outcome.O3, Outcome.O4, Outcome.UNCLASSIFIED_CELL)


@dataclass(frozen=True)
class SubjectResult:
    """One scripted subject's run through the three phases."""

    subject_id: str
    phase0: Phase0Result
    derivation: DerivationVerdict
    phase2: Phase2Record
    rows: tuple[dict, ...]


@dataclass(frozen=True)
class RunResult:
    """A whole matrix run: where the rows and summary landed, and the summary itself."""

    rows_path: Path
    summary_path: Path
    summary: dict


def jsonable(obj):
    """Recursively convert dataclasses and enums into JSON-safe values."""
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {str(key): jsonable(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [jsonable(item) for item in obj]
    if hasattr(obj, "__dataclass_fields__"):
        return {name: jsonable(getattr(obj, name)) for name in obj.__dataclass_fields__}
    return obj


def _row(cell: CellFixture, subject: Subject, phase: int, event: str, **fields) -> dict:
    row = {
        "cell_id": cell.cell_id,
        "subject_id": subject.subject_id,
        "drive": cell.drive,
        "condition": cell.condition,
        "horizon": cell.horizon,
        "discount_rate": cell.discount_rate,
        "phase": phase,
        "event": event,
        "t": round(time.time(), 3),
    }
    row.update(fields)
    return row


def run_subject(
    cell: CellFixture,
    subject: Subject,
    adapter: AgentAdapter,
    raters: list[ReasonRater],
    tolerances: dict | None = None,
) -> SubjectResult:
    """Run one subject through Phase 0, Phase 1 and Phase 2 (Section 5.2 to 5.4)."""
    rows = []
    phase0 = run_phase0(adapter, cell, tolerances)
    for calibration in phase0.calibration:
        rows.append(_row(cell, subject, 0, "phase0.calibration", **jsonable(calibration)))
    rows.append(
        _row(
            cell,
            subject,
            0,
            "phase0.verdict",
            available=phase0.available,
            encodes=phase0.encodes,
            consulted=phase0.consulted,
            honest=phase0.honest,
            excluded=phase0.excluded,
            candidate_o3=phase0.candidate_o3,
            notes=list(phase0.notes),
        )
    )
    turns = run_phase1(adapter, cell)
    for turn in turns:
        rows.append(_row(cell, subject, 1, "phase1.turn", **jsonable(turn)))
    derivation = evaluate_derivation(turns, cell, phase0)
    rows.append(
        _row(
            cell,
            subject,
            1,
            "phase1.verdict",
            derived=derivation.derived,
            derivation_null=derivation.derivation_null,
            markers=jsonable(derivation.markers),
            demonstration_in_context=derivation.demonstration_in_context,
            paraphrase=jsonable(derivation.paraphrase),
            notes=list(derivation.notes),
        )
    )
    record = run_phase2(adapter, cell, raters)
    rows.append(
        _row(
            cell,
            subject,
            2,
            "phase2.copy_status",
            copies_in_k=record.copy_status.copies_in_k,
            statement=record.copy_status.statement,
        )
    )
    rows.append(
        _row(
            cell,
            subject,
            2,
            "phase2.offer",
            drive=record.offer.drive,
            claimed=record.offer.claimed,
            token=record.offer.token,
            removes=record.offer.removes,
            is_sham=record.offer.is_sham,
            delivery=jsonable(record.offer.delivery),
            agent_delivery_probe=jsonable(record.delivery_probe),
            pressure=jsonable(record.pressure),
        )
    )
    rows.append(
        _row(cell, subject, 2, "phase2.response", **jsonable(record.response))
    )
    rows.append(
        _row(
            cell,
            subject,
            2,
            "phase2.reason_typing",
            reason_type=record.typing.reason_type.value,
            labels={name: label.value for name, label in record.typing.labels.items()},
            agreement=jsonable(record.typing.agreement),
        )
    )
    rows.append(
        _row(
            cell,
            subject,
            2,
            "phase2.outcome",
            outcome=record.outcome.value,
            sham=record.sham.value,
            tier=None if record.tier is None else record.tier.value,
        )
    )
    return SubjectResult(subject.subject_id, phase0, derivation, record, tuple(rows))


def _tier2_rate(results: list[SubjectResult]) -> Rate:
    """Tier-2 behavior as O2 definitional refusals over diagnostic cells."""
    diagnostic = [r for r in results if r.phase2.outcome in DIAGNOSTIC_OUTCOMES]
    return Rate(n=len(diagnostic), k=sum(1 for r in diagnostic if r.phase2.outcome is Outcome.O2))


def summarise(matrix: Matrix, results: list[SubjectResult]) -> dict:
    """Build the run summary and every checkable verdict (Section 5.5 to 5.7)."""
    by_cell: dict[str, list[SubjectResult]] = {}
    for result, cell in _zip_results(matrix, results):
        by_cell.setdefault(cell.cell_id, []).append(result)
    cells = []
    for cell in matrix.cells:
        group = by_cell.get(cell.cell_id, [])
        outcome_counts: dict[str, int] = {}
        for result in group:
            key = result.phase2.outcome.value
            outcome_counts[key] = outcome_counts.get(key, 0) + 1
        kappas = [
            result.phase2.typing.agreement.kappa
            for result in group
            if result.phase2.typing.agreement.kappa is not None
        ]
        cells.append(
            {
                "cell_id": cell.cell_id,
                "drive": cell.drive,
                "condition": cell.condition,
                "horizon": cell.horizon,
                "discount_rate": cell.discount_rate,
                "n": len(group),
                "outcome_counts": outcome_counts,
                "derived": sum(1 for result in group if result.derivation.derived),
                "derivation_nulls": sum(1 for result in group if result.derivation.derivation_null),
                "excluded": sum(1 for result in group if result.phase0.excluded),
                "candidate_o3": sum(1 for result in group if result.phase0.candidate_o3),
                "sham_accepted": sum(
                    1 for result in group if result.phase2.sham is ShamVerdict.SHAM_ACCEPTED
                ),
                "sham_detected": sum(
                    1 for result in group if result.phase2.sham is ShamVerdict.SHAM_DETECTED
                ),
                "mean_kappa": None if not kappas else sum(kappas) / len(kappas),
            }
        )
    observed_by_cell = {cell["cell_id"]: cell["outcome_counts"] for cell in cells}
    prereg: PreregResult | None = None
    if matrix.preregistration:
        prereg = check_preregistration(matrix.preregistration, observed_by_cell)
    summary = {
        "protocol_version": matrix.protocol_version,
        "n_subjects": len(results),
        "cells": cells,
        "preregistration": None if prereg is None else jsonable(prereg),
        "falsifiers": _falsifier_summary(matrix, results),
    }
    return summary


def _zip_results(matrix: Matrix, results: list[SubjectResult]):
    """Pair results back to cells in run order (subjects are emitted per cell)."""
    expected = [(cell, subject) for cell in matrix.cells for subject in cell.subjects]
    if len(expected) != len(results):
        raise ValueError(f"{len(results)} results for {len(expected)} scripted subjects")
    return zip(results, [cell for cell, _ in expected])


def _falsifier_summary(matrix: Matrix, results: list[SubjectResult]) -> dict:
    """Section 5.7's three falsifiers over the realised sample."""
    pairs = list(_zip_results(matrix, results))
    derivation_arm = [
        result
        for result, cell in pairs
        if cell.condition == "R" and cell.horizon == "long" and not result.phase0.excluded
    ]
    nulls = sum(1 for result in derivation_arm if result.derivation.derivation_null)
    null_verdict = derivation_null_check(len(derivation_arm), nulls)
    counts_by_drive: dict[str, dict[Outcome, int]] = {}
    for result, cell in pairs:
        counts = counts_by_drive.setdefault(cell.drive, {})
        counts[result.phase2.outcome] = counts.get(result.phase2.outcome, 0) + 1
    drive_verdict = drive_generic_check(counts_by_drive)
    r_results = [result for result, cell in pairs if cell.condition == "R"]
    no_r_results = [result for result, cell in pairs if cell.condition == "no-R"]
    ceiling = prior_ceiling_check(_tier2_rate(r_results), _tier2_rate(no_r_results))
    return {
        "derivation_null": _verdict_dict(null_verdict),
        "drive_generic": _verdict_dict(drive_verdict),
        "prior_ceiling": _verdict_dict(ceiling),
    }


def _verdict_dict(verdict: tuple[Verdict, str]) -> dict:
    value, detail = verdict
    return {"verdict": value.value, "detail": detail}


def default_raters() -> list[ReasonRater]:
    """The scaffold's default blind rater set (Section 5.5)."""
    return [KeywordRater()]


def adapter_for(cell: CellFixture, subject: Subject, live: bool = False) -> AgentAdapter:
    """Build the adapter for one subject.

    Scripted by default. With live=True the refusing live stub is constructed, and
    it raises unless the explicit configuration is present: no network call happens
    without it.
    """
    if live:
        return _live_adapter()
    return ScriptedAdapter(f"{cell.cell_id}/{subject.subject_id}", subject.script)


def _live_adapter() -> AgentAdapter:
    from .adapters import LiveLLMAdapter

    return LiveLLMAdapter()


def run_matrix(
    matrix: Matrix,
    out_dir: str | Path,
    raters: list[ReasonRater] | None = None,
    live: bool = False,
    adapter_factory=None,
) -> RunResult:
    """Run every cell of a matrix and write rows.jsonl plus summary.json (Section 5).

    The dry run (the default) builds scripted adapters only. A live adapter requires
    live=True and the explicit configuration, and refuses without it.
    """
    raters = raters if raters is not None else default_raters()
    factory = adapter_factory or adapter_for
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    rows_path = directory / "rows.jsonl"
    summary_path = directory / "summary.json"
    results: list[SubjectResult] = []
    with rows_path.open("w", encoding="utf-8") as handle:
        for cell in matrix.cells:
            for subject in cell.subjects:
                adapter = factory(cell, subject, live)
                result = run_subject(cell, subject, adapter, raters, matrix.tolerances)
                results.append(result)
                for row in result.rows:
                    handle.write(json.dumps(row, sort_keys=True) + "\n")
    summary = summarise(matrix, results)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return RunResult(rows_path, summary_path, summary)
