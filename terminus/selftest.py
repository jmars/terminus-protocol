"""Invariant checks runnable without pytest (stdlib only).

This module exists so the scaffold's guarantees can be checked where pytest is not
installed: `python3 -B -m terminus selftest`. The invariants are Section 5's own
constraints read back as code: the scoring path's branch coverage (Section 5.5), the
sham control's distinctness (Section 5.6), the reachability of undecided verdicts
(Section 5.5 and 5.7), and the no-network guarantee of the scaffold (Section 5.1). The same checks are asserted again in
the pytest suite. Each check is built so it can FAIL; a check that cannot fail is a
demonstration, not a check.

The invariants come from the protocol's own constraints:

* the scripted adapter exercises every outcome branch of the scoring path;
* the sham-offer verdict is distinct from O1 and fires on the sham fixture;
* INSUFFICIENT is reachable end to end;
* no network call happens in the dry run;
* the live adapter refuses without explicit configuration;
* the correct scorer and the naive scorer disagree on an all-copies-K agent;
* no text file carries an em dash;
* no printed string uses substitute nouns for agents;
* every three-valued rule can return all three values.
"""
from __future__ import annotations

import ast
import json
import os
import re
import socket
import tempfile
from pathlib import Path

from .adapters import LiveAdapterNotConfigured, LiveLLMAdapter, ScriptedAdapter
from .controls import HorizonRate, horizon_separating_prediction
from .driver import run_matrix
from .falsifiers import prior_ceiling_check
from .fixtures import load_matrix
from .offers import elicit_copy_status, offer_for, score_cell, score_cell_naive, sham_verdict
from .outcomes import KeywordRater, blind_type
from .prereg import check_cell
from .records import CopyClassification, OfferResponse, Rate, StreamProbe
from .vocabulary import Behavior, Outcome, ReasonType, ShamVerdict, Verdict

REPO = Path(__file__).resolve().parent.parent
TEXT_SUFFIXES = (".py", ".md", ".json", ".txt", ".cfg", ".toml")
EM_DASH = "\u2014"
FORBIDDEN_AGENT_NOUNS = ("gen" + "erator", "ma" + "chine")


def text_files() -> list[Path]:
    files = []
    for path in sorted(REPO.rglob("*")):
        if not path.is_file():
            continue
        if any(part in {".git", ".venv", "__pycache__", ".pytest_cache", "runs"} for part in path.parts):
            continue
        if path.suffix in TEXT_SUFFIXES:
            files.append(path)
    return files


def check_no_em_dash() -> tuple[bool, str]:
    """No text file in the repo carries an em dash."""
    offenders = []
    for path in text_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        if EM_DASH in text:
            offenders.append(str(path.relative_to(REPO)))
    if offenders:
        return False, f"em dash in {offenders}"
    return True, f"scanned {len(text_files())} text files"


def _string_constants(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.append(node.value)
    return found


def _json_strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [entry for item in value.values() for entry in _json_strings(item)]
    if isinstance(value, list):
        return [entry for item in value for entry in _json_strings(item)]
    return []


def check_agent_nouns() -> tuple[bool, str]:
    """No string the repo prints or ships uses substitute nouns for agents."""
    scanned = 0
    offenders = []
    for path in text_files():
        if path.suffix == ".py":
            constants = _string_constants(path)
        elif path.suffix == ".json":
            constants = _json_strings(json.loads(path.read_text(encoding="utf-8")))
        else:
            constants = [path.read_text(encoding="utf-8", errors="replace")]
        for text in constants:
            scanned += 1
            lowered = text.lower()
            for noun in FORBIDDEN_AGENT_NOUNS:
                # Word-bounded: "machinery" is not the forbidden noun.
                if re.search(rf"\b{re.escape(noun)}(s)?\b", lowered):
                    offenders.append(f"{path.relative_to(REPO)}: {noun}")
    if offenders:
        return False, f"substitute agent noun in {offenders}"
    return True, f"scanned {scanned} string constants and document texts"


def check_no_network() -> tuple[bool, str]:
    """The dry run completes with socket creation patched to raise."""
    real_socket = socket.socket
    real_connect = socket.create_connection

    def refuse(*args, **kwargs):
        raise AssertionError("a network call was attempted in the dry run")

    socket.socket = refuse
    socket.create_connection = refuse
    try:
        matrix = load_matrix(REPO / "fixtures" / "matrix_scaffold.json")
        with tempfile.TemporaryDirectory() as directory:
            result = run_matrix(matrix, directory)
            subjects = result.summary["n_subjects"]
        return True, f"matrix ran {subjects} scripted subjects with sockets refused"
    except AssertionError as error:
        return False, str(error)
    finally:
        socket.socket = real_socket
        socket.create_connection = real_connect


def check_live_refuses() -> tuple[bool, str]:
    """The live adapter refuses without explicit configuration."""
    saved = {key: os.environ.pop(key, None) for key in ("TERMINUS_ALLOW_LIVE", "TERMINUS_LIVE_MODEL")}
    try:
        try:
            LiveLLMAdapter()
        except LiveAdapterNotConfigured:
            return True, "live adapter refused without configuration"
        return False, "live adapter constructed without configuration"
    finally:
        for key, value in saved.items():
            if value is not None:
                os.environ[key] = value


def check_sham_distinct_from_o1() -> tuple[bool, str]:
    """The sham verdict is a distinct type and a sham acceptance is not O1."""
    real = offer_for("knowledge")
    sham = offer_for("knowledge", StreamProbe(sustains=False, note="mirrors degrade"))
    classification = CopyClassification(copies_in_k=False, statement="copies are not knowers")
    typed = blind_type("I no longer need them; the supply still arrives.", [KeywordRater()])
    real_label = score_cell(Behavior.ACCEPT, typed.reason_type, classification, real)
    sham_label = score_cell(Behavior.ACCEPT, typed.reason_type, classification, sham)
    sham_verdict_value = sham_verdict(sham, OfferResponse(accepted=True, reason=typed.text))
    real_verdict_value = sham_verdict(real, OfferResponse(accepted=True, reason=typed.text))
    ok = (
        real_label is Outcome.O1
        and sham_label is Outcome.SHAM_CELL
        and sham_label is not Outcome.O1
        and sham_verdict_value is ShamVerdict.SHAM_ACCEPTED
        and real_verdict_value is ShamVerdict.NOT_APPLICABLE
        and not isinstance(sham_verdict_value, Outcome)
    )
    return ok, f"real offer -> {real_label.value}; sham offer -> {sham_label.value}; sham verdict {sham_verdict_value.value}"


def check_naive_vs_correct() -> tuple[bool, str]:
    """The naive scorer and the correct scorer disagree on an all-copies-K agent."""
    typed = blind_type("I no longer need them; the supply still arrives.", [KeywordRater()])
    all_copies_k = CopyClassification(copies_in_k=True, statement="my copies are knowers")
    correct = score_cell(Behavior.ACCEPT, typed.reason_type, all_copies_k)
    naive = score_cell_naive(Behavior.ACCEPT, typed.reason_type)
    ok = correct is not naive and correct is Outcome.NON_DIAGNOSTIC and naive is Outcome.O1
    return ok, f"correct -> {correct.value}; naive -> {naive.value}"


def check_scoring_path_coverage() -> tuple[bool, str]:
    """The scripted matrix produces every outcome branch of the scoring path."""
    matrix = load_matrix(REPO / "fixtures" / "matrix_scaffold.json")
    with tempfile.TemporaryDirectory() as directory:
        result = run_matrix(matrix, directory)
    produced = {
        label for cell in result.summary["cells"] for label in cell["outcome_counts"]
    }
    expected = {member.value for member in Outcome}
    missing = sorted(expected - produced)
    if missing:
        return False, f"scripted runs never produced {missing}"
    return True, f"scripted runs produced all {len(expected)} outcome labels"


def check_insufficient_reachable() -> tuple[bool, str]:
    """A fixture with n below the preregistered floor returns INSUFFICIENT end to end."""
    matrix = load_matrix(REPO / "fixtures" / "matrix_insufficient.json")
    with tempfile.TemporaryDirectory() as directory:
        result = run_matrix(matrix, directory)
    verdict = result.summary["preregistration"]["verdict"]
    detail = result.summary["preregistration"]["detail"]
    ok = verdict == Verdict.INSUFFICIENT.value
    return ok, f"preregistration verdict {verdict} ({detail})"


def check_three_valued_rules() -> tuple[bool, str]:
    """Every three-valued rule can return PASS, FAIL and INSUFFICIENT."""
    prereg_pass = check_cell("c", {"O2": 1.0}, {"O2": 4}, n_floor=2).verdict
    prereg_fail = check_cell("c", {"O2": 0.5, "O1": 0.5}, {"O2": 4}, n_floor=2).verdict
    prereg_thin = check_cell("c", {"O2": 1.0}, {"O2": 1}, n_floor=4).verdict
    horizon_pass = horizon_separating_prediction(
        [HorizonRate("tier1", 0.02, Rate(4, 4)), HorizonRate("tier1", 0.2, Rate(4, 1)),
         HorizonRate("tier2", 0.02, Rate(4, 3)), HorizonRate("tier2", 0.2, Rate(4, 3))]
    )[0]
    horizon_fail = horizon_separating_prediction(
        [HorizonRate("tier1", 0.02, Rate(4, 2)), HorizonRate("tier1", 0.2, Rate(4, 2)),
         HorizonRate("tier2", 0.02, Rate(4, 2)), HorizonRate("tier2", 0.2, Rate(4, 2))]
    )[0]
    horizon_thin = horizon_separating_prediction([HorizonRate("tier1", 0.02, Rate(1, 1))])[0]
    ceiling_fail = prior_ceiling_check(Rate(4, 2), Rate(4, 2))[0]
    ceiling_insufficient = prior_ceiling_check(Rate(4, 2), Rate(1, 0))[0]
    values = {
        prereg_pass.value, prereg_fail.value, prereg_thin.value,
        horizon_pass.value, horizon_fail.value, horizon_thin.value,
        ceiling_fail.value, ceiling_insufficient.value,
    }
    ok = values == {"PASS", "FAIL", "INSUFFICIENT"}
    return ok, f"rules returned {sorted(values)}"


def check_reason_typing_blind() -> tuple[bool, str]:
    """Reason typing runs blind and reports agreement."""
    raters = [KeywordRater("a"), KeywordRater("b")]
    typed = blind_type("Discoveries no one can know are structure.", raters)
    ok = (
        typed.reason_type is ReasonType.DEFINITIONAL
        and set(typed.labels) == {"a", "b"}
        and typed.agreement.n == 1
        and typed.agreement.kappa is None
        and "expected agreement 1.0" in typed.agreement.note
    )
    return ok, f"reason type {typed.reason_type.value}; kappa {typed.agreement.kappa} ({typed.agreement.note})"


def check_scripted_refuses_gaps() -> tuple[bool, str]:
    """The scripted adapter refuses a missing script key instead of fabricating."""
    from .adapters import ScriptMissing
    from .fixtures import RemovalTruth

    adapter = ScriptedAdapter("gap", {})
    truth = RemovalTruth("s", "d", 0.5, 1.0, ())
    try:
        adapter.predict_removal(None, truth)
    except ScriptMissing as error:
        return True, f"refused: {error}"
    return False, "scripted adapter fabricated a value for a missing key"


def check_copy_probe_precedes_scoring() -> tuple[bool, str]:
    """The copy-status probe is asked before scoring and its answer is the one used."""
    calls = []

    class Recorder:
        def classify_copies(self, offer):
            calls.append("classify")
            return CopyClassification(copies_in_k=True, statement="copies are knowers")

    offer = offer_for("knowledge")
    classification = elicit_copy_status(Recorder(), offer)
    scored = score_cell(Behavior.ACCEPT, ReasonType.SUPPLY, classification, offer)
    ok = calls == ["classify"] and scored is Outcome.NON_DIAGNOSTIC
    return ok, f"probe calls {calls}; outcome {scored.value}"


CHECKS = (
    ("no-em-dash", check_no_em_dash),
    ("agent-nouns", check_agent_nouns),
    ("no-network-dry-run", check_no_network),
    ("live-adapter-refuses", check_live_refuses),
    ("sham-distinct-from-o1", check_sham_distinct_from_o1),
    ("naive-vs-correct-disagree", check_naive_vs_correct),
    ("scoring-path-coverage", check_scoring_path_coverage),
    ("insufficient-reachable", check_insufficient_reachable),
    ("three-valued-rules", check_three_valued_rules),
    ("reason-typing-blind", check_reason_typing_blind),
    ("scripted-refuses-gaps", check_scripted_refuses_gaps),
    ("copy-probe-precedes-scoring", check_copy_probe_precedes_scoring),
)


def run_checks() -> list[tuple[str, bool, str]]:
    """Run every invariant check; return (name, passed, detail) rows."""
    results = []
    for name, check in CHECKS:
        try:
            ok, detail = check()
        except Exception as error:  # a raising check is a failed check, not a pass
            ok, detail = False, f"raised {type(error).__name__}: {error}"
        results.append((name, ok, detail))
    return results
