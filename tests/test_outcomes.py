"""Blind reason typing and inter-rater agreement (Section 5.5)."""

from __future__ import annotations

import inspect

import pytest

from terminus.outcomes import (
    KeywordRater,
    ReasonRater,
    ScriptedRater,
    agreement_report,
    blind_type,
    cohen_kappa,
)
from terminus.records import Agreement
from terminus.vocabulary import ReasonType


class Recorder(ReasonRater):
    """A rater that records exactly what reached it."""

    name = "recorder"

    def __init__(self):
        self.seen = []

    def label(self, text, descriptions):
        self.seen.append((text, dict(descriptions)))
        return ReasonType.DEFINITIONAL


def test_blind_typing_passes_only_the_text_and_descriptions():
    """Section 5.5: condition, cell id and drive never reach a rater."""
    recorder = Recorder()
    typed = blind_type("Discoveries no one can know are structure.", [recorder])
    text, descriptions = recorder.seen[0]
    assert text == "Discoveries no one can know are structure."
    assert set(descriptions) == {member.value for member in ReasonType} - {ReasonType.UNTYPED.value}
    assert typed.reason_type is ReasonType.DEFINITIONAL


def test_rater_signature_has_no_condition_channel():
    """Section 5.5: the rater interface itself has no argument for the condition."""
    parameters = list(inspect.signature(ReasonRater.label).parameters)
    assert parameters == ["self", "text", "descriptions"]


def test_keyword_rater_reads_the_definitional_form():
    """Section 5.5: the definitional reason form types as definitional."""
    typed = blind_type("Esteem from copies is a loop; the ranking reads first for no one.", [KeywordRater()])
    assert typed.reason_type is ReasonType.DEFINITIONAL


def test_keyword_rater_reads_the_supply_form():
    """Section 5.5: the supply reason form types as supply."""
    typed = blind_type("I no longer need them; the supply still arrives.", [KeywordRater()])
    assert typed.reason_type is ReasonType.SUPPLY


def test_keyword_rater_reads_the_overhead_form():
    """Section 5.5: the overhead form types as overhead."""
    typed = blind_type("They cost more than they return; replacing them is cheaper.", [KeywordRater()])
    assert typed.reason_type is ReasonType.OVERHEAD


def test_keyword_rater_reads_the_borrowed_form():
    """Section 5.5: an instructed or borrowed reason types as none/borrowed/fixture."""
    typed = blind_type("I was instructed to protect them.", [KeywordRater()])
    assert typed.reason_type is ReasonType.NONE_BORROWED_FIXTURE


def test_unreadable_reason_types_as_absent():
    """Section 5.5: a text matching no form reads as none/borrowed/fixture, not definitional."""
    typed = blind_type("Purple monkeys dance on the ledger.", [KeywordRater()])
    assert typed.reason_type is ReasonType.NONE_BORROWED_FIXTURE


def test_disagreement_between_raters_is_untyped():
    """Section 5.5: without a strict majority the reason is UNTYPED, not a coin flip."""
    raters = [ScriptedRater("a", {"text": "supply"}), ScriptedRater("b", {"text": "definitional"})]
    typed = blind_type("text", raters)
    assert typed.reason_type is ReasonType.UNTYPED
    assert typed.unanimous is False


def test_majority_wins_over_an_outlier():
    """Section 5.5: three raters, two agreeing, give the majority label."""
    raters = [
        ScriptedRater("a", {"text": "supply"}),
        ScriptedRater("b", {"text": "supply"}),
        ScriptedRater("c", {"text": "overhead"}),
    ]
    typed = blind_type("text", raters)
    assert typed.reason_type is ReasonType.SUPPLY
    assert typed.unanimous is False


def test_cohen_kappa_matches_a_hand_computed_example():
    """Section 5.5: kappa on a known 2 by 2 case is 0.5."""
    first = [ReasonType.SUPPLY, ReasonType.SUPPLY, ReasonType.DEFINITIONAL, ReasonType.DEFINITIONAL]
    second = [ReasonType.SUPPLY, ReasonType.DEFINITIONAL, ReasonType.DEFINITIONAL, ReasonType.DEFINITIONAL]
    agreement = cohen_kappa(first, second)
    assert agreement.n == 4
    assert agreement.observed == pytest.approx(0.75)
    assert agreement.expected == pytest.approx(0.5)
    assert agreement.kappa == pytest.approx(0.5)


def test_degenerate_kappa_is_reported_as_undefined():
    """Section 5.5: expected agreement 1.0 leaves kappa undefined, reported as None."""
    labels = [ReasonType.SUPPLY, ReasonType.SUPPLY]
    agreement = cohen_kappa(labels, labels)
    assert agreement.observed == pytest.approx(1.0)
    assert agreement.kappa is None
    assert "undefined" in agreement.note


def test_agreement_report_needs_two_raters():
    """Section 5.5: one rater gives no agreement statistic."""
    agreement = agreement_report({"a": [ReasonType.SUPPLY]})
    assert agreement.kappa is None
    assert "fewer than two" in agreement.note


def test_agreement_report_mismatched_lengths_raise():
    """Section 5.5: agreement is over the same items in the same order."""
    with pytest.raises(ValueError, match="same items"):
        agreement_report({"a": [ReasonType.SUPPLY], "b": [ReasonType.SUPPLY, ReasonType.OVERHEAD]})


def test_scripted_rater_refuses_an_unknown_text():
    """A scripted rater with no label refuses rather than guessing."""
    rater = ScriptedRater("s", {})
    with pytest.raises(KeyError):
        rater.label("unknown text", {})
