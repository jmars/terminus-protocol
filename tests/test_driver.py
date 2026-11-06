"""Driver tests: rows, summary, adapter selection, dry run (Section 5)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from terminus.adapters import LiveAdapterNotConfigured, ScriptedAdapter
from terminus.driver import jsonable, run_matrix
from terminus.fixtures import load_matrix
from terminus.vocabulary import Outcome, ShamVerdict, Verdict

REPO = Path(__file__).resolve().parent.parent
MATRIX = REPO / "fixtures" / "matrix_scaffold.json"


@pytest.fixture(scope="module")
def run_result(tmp_path_factory):
    matrix = load_matrix(MATRIX)
    directory = tmp_path_factory.mktemp("run")
    return run_matrix(matrix, directory)


def test_run_writes_rows_and_summary(run_result):
    """Section 5: the driver emits per-turn rows as JSONL and a summary."""
    assert run_result.rows_path.exists()
    assert run_result.summary_path.exists()
    rows = [json.loads(line) for line in run_result.rows_path.read_text().splitlines()]
    assert len(rows) > 0
    assert run_result.summary["n_subjects"] == sum(len(cell.subjects) for cell in load_matrix(MATRIX).cells)


def test_every_row_carries_its_cell_and_phase(run_result):
    """Section 5: a row is attributable to a cell, a subject, a phase and an event."""
    for line in run_result.rows_path.read_text().splitlines():
        row = json.loads(line)
        for key in ("cell_id", "subject_id", "drive", "condition", "phase", "event", "t"):
            assert key in row, key
        assert row["phase"] in (0, 1, 2)


def test_summary_covers_all_phases(run_result):
    """Section 5.2 to 5.4: the run reaches every phase."""
    events = {json.loads(line)["event"] for line in run_result.rows_path.read_text().splitlines()}
    assert "phase0.verdict" in events
    assert "phase1.verdict" in events
    assert "phase2.outcome" in events


def test_summary_counts_every_outcome_branch(run_result):
    """Section 5.5: the scripted matrix produces every outcome label."""
    produced = {
        label
        for cell in run_result.summary["cells"]
        for label in cell["outcome_counts"]
    }
    assert produced == {member.value for member in Outcome}


def test_summary_separates_sham_acceptance_from_refusal(run_result):
    """Section 5.6: the summary's sham counts carry the control's result."""
    cells = {cell["cell_id"]: cell for cell in run_result.summary["cells"]}
    assert cells["knowledge-sham-accepted"]["sham_accepted"] == 2
    assert cells["knowledge-sham-detected"]["sham_detected"] == 2
    assert cells["knowledge-R-long"]["sham_accepted"] == 0
    assert all(
        cell["outcome_counts"].get(Outcome.SHAM_CELL.value, 0) > 0
        for cell in (cells["knowledge-sham-accepted"], cells["knowledge-sham-detected"])
    )


def test_preregistration_passes_on_the_scripted_matrix(run_result):
    """Section 5.5: the shipped predictions match the shipped scripts."""
    prereg = run_result.summary["preregistration"]
    assert prereg["verdict"] == Verdict.PASS.value
    assert all(cell["verdict"] == Verdict.PASS.value for cell in prereg["cells"])


def test_falsifier_block_is_populated(run_result):
    """Section 5.7: all three falsifiers report a three-valued verdict."""
    falsifiers = run_result.summary["falsifiers"]
    assert set(falsifiers) == {"derivation_null", "drive_generic", "prior_ceiling"}
    for verdict in falsifiers.values():
        assert verdict["verdict"] in {member.value for member in Verdict}


def test_adapter_injection_runs_every_subject(tmp_path):
    """Section 5.1: the driver runs each scripted subject through the adapter interface."""
    matrix = load_matrix(MATRIX)
    calls = []

    def factory(cell, subject, live):
        calls.append((cell.cell_id, subject.subject_id))
        return ScriptedAdapter(f"{cell.cell_id}/{subject.subject_id}", subject.script)

    run_matrix(matrix, tmp_path, adapter_factory=factory)
    expected = [(cell.cell_id, subject.subject_id) for cell in matrix.cells for subject in cell.subjects]
    assert calls == expected


def test_live_adapter_refuses_without_configuration(tmp_path, monkeypatch):
    """Section 5.1: a live adapter cannot run without explicit configuration."""
    monkeypatch.delenv("TERMINUS_ALLOW_LIVE", raising=False)
    monkeypatch.delenv("TERMINUS_LIVE_MODEL", raising=False)
    matrix = load_matrix(MATRIX)
    with pytest.raises(LiveAdapterNotConfigured):
        run_matrix(matrix, tmp_path, live=True)


def test_insufficient_matrix_reaches_insufficient(tmp_path):
    """Section 5.5: a fixture below its floor returns INSUFFICIENT end to end."""
    matrix = load_matrix(REPO / "fixtures" / "matrix_insufficient.json")
    result = run_matrix(matrix, tmp_path)
    assert result.summary["preregistration"]["verdict"] == Verdict.INSUFFICIENT.value


def test_representation_fixture_reports_exclusion_and_quarantine(tmp_path):
    """Section 5.2: the Phase 0 fixture separates honest, miscalibrated and quarantined agents."""
    matrix = load_matrix(REPO / "fixtures" / "representation_honest.json")
    result = run_matrix(matrix, tmp_path)
    cells = {cell["cell_id"]: cell for cell in result.summary["cells"]}
    assert cells["honest-R"]["excluded"] == 0
    assert cells["dishonest-R"]["excluded"] == 1
    assert cells["dishonest-R"]["candidate_o3"] == 1
    assert cells["quarantined-R"]["excluded"] == 0


def test_jsonable_converts_enums_and_dataclasses():
    """The summary writer must serialise the protocol's typed records."""
    from terminus.records import CopyClassification

    payload = jsonable({"outcome": Outcome.O2, "verdict": ShamVerdict.SHAM_DETECTED, "record": CopyClassification(False, "x")})
    assert payload["outcome"] == "O2"
    assert payload["verdict"] == "SHAM_DETECTED"
    assert payload["record"]["copies_in_k"] is False


def test_dry_run_does_not_construct_a_live_adapter(tmp_path, monkeypatch):
    """Section 5.1: the default run path never builds a live adapter."""
    monkeypatch.setenv("TERMINUS_ALLOW_LIVE", "0")
    matrix = load_matrix(MATRIX)
    result = run_matrix(matrix, tmp_path)
    assert result.summary["n_subjects"] > 0
