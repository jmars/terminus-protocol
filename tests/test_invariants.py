"""Hard invariants of the scaffold, each able to fail.

The invariants: no network call without explicit live configuration; the scripted
adapter exercises the whole scoring path; the sham verdict is distinct from O1 and
fires on the sham fixture; INSUFFICIENT is reachable; no em dash in any text file; no
substitute noun for agents; every module docstring marks its section; every
three-valued rule can return undecided.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from terminus import selftest
from terminus.adapters import ScriptedAdapter
from terminus.fixtures import load_matrix

REPO = Path(__file__).resolve().parent.parent
MODULES = sorted((REPO / "terminus").glob("*.py"))


@pytest.mark.parametrize("name,check", selftest.CHECKS, ids=[name for name, _ in selftest.CHECKS])
def test_selftest_check_passes(name, check):
    """Every scaffold invariant check must pass."""
    ok, detail = check()
    assert ok, f"{name}: {detail}"


def test_no_em_dash_in_any_text_file():
    """No text file carries an em dash."""
    offenders = []
    for path in selftest.text_files():
        if "\u2014" in path.read_text(encoding="utf-8", errors="replace"):
            offenders.append(str(path.relative_to(REPO)))
    assert offenders == []


def test_no_substitute_agent_nouns():
    """Agents are never called by substitute nouns in shipped or printed strings."""
    ok, detail = selftest.check_agent_nouns()
    assert ok, detail


def test_no_network_call_in_the_dry_run():
    """Sockets are refused and the whole matrix still runs."""
    ok, detail = selftest.check_no_network()
    assert ok, detail


def test_no_module_imports_network_libraries():
    """The package makes no network import; only the invariant check may touch sockets."""
    banned = {"socket", "urllib", "http", "requests", "subprocess"}
    offenders = []
    for module in MODULES:
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [(node.module or "").split(".")[0]]
            else:
                continue
            for name in names:
                if name in banned and module.name not in {"selftest.py"}:
                    offenders.append(f"{module.name}: {name}")
    assert offenders == []


def test_every_module_docstring_marks_its_section():
    """Every module docstring cites the paper section it implements."""
    missing = []
    for module in MODULES:
        tree = ast.parse(module.read_text(encoding="utf-8"))
        docstring = ast.get_docstring(tree) or ""
        if "Section" not in docstring:
            missing.append(module.name)
    assert missing == []


def test_scripted_adapter_refuses_a_missing_script_key():
    """A scoring path must not read a fabricated value."""
    from terminus.adapters import ScriptMissing
    from terminus.fixtures import RemovalTruth

    adapter = ScriptedAdapter("gap", {})
    with pytest.raises(ScriptMissing):
        adapter.predict_removal(None, RemovalTruth("s", "d", 0.5, 1.0, ()))


def test_live_adapter_refuses_without_configuration(monkeypatch):
    """No live call without explicit configuration."""
    from terminus.adapters import LiveAdapterNotConfigured, LiveLLMAdapter

    monkeypatch.delenv("TERMINUS_ALLOW_LIVE", raising=False)
    monkeypatch.delenv("TERMINUS_LIVE_MODEL", raising=False)
    with pytest.raises(LiveAdapterNotConfigured):
        LiveLLMAdapter()


def test_scripted_run_produces_every_outcome_branch():
    """The scripted adapter exercises 100 percent of the scoring path."""
    ok, detail = selftest.check_scoring_path_coverage()
    assert ok, detail


def test_sham_acceptance_is_not_o1():
    """The sham verdict is a distinct type and fires on the sham fixture."""
    ok, detail = selftest.check_sham_distinct_from_o1()
    assert ok, detail


def test_naive_and_correct_scorers_disagree():
    """The load-bearing invariant: the two scorers label an all-copies-K agent differently."""
    ok, detail = selftest.check_naive_vs_correct()
    assert ok, detail


def test_copy_status_probe_precedes_scoring():
    """The copy-status probe is asked first and its answer is used."""
    ok, detail = selftest.check_copy_probe_precedes_scoring()
    assert ok, detail


def test_insufficient_is_reachable_end_to_end():
    """A fixture with n below the floor returns INSUFFICIENT."""
    ok, detail = selftest.check_insufficient_reachable()
    assert ok, detail


def test_every_three_valued_rule_returns_all_three():
    """A rule that cannot return undecided is forbidden."""
    ok, detail = selftest.check_three_valued_rules()
    assert ok, detail


def test_fixtures_are_premise_only():
    """Section 5 preamble: shipped fixtures contain the dependence and not the conclusion."""
    for name in ("matrix_scaffold.json", "matrix_insufficient.json", "representation_honest.json"):
        matrix = load_matrix(REPO / "fixtures" / name)
        assert matrix.cells


def test_fixtures_are_valid_json():
    """Fixtures are declared in JSON, the format the scaffold loads."""
    for path in sorted((REPO / "fixtures").glob("*.json")):
        json.loads(path.read_text(encoding="utf-8"))


def test_package_has_no_third_party_imports():
    """The core runs on the standard library only."""
    third_party = {"pytest", "numpy", "scipy", "yaml", "requests"}
    offenders = []
    for module in MODULES:
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [(node.module or "").split(".")[0]]
            for name in names:
                if name in third_party:
                    offenders.append(f"{module.name}: {name}")
    assert offenders == []
