"""Tests for the guardrails.

The grounding check is the thing standing between a model's invention and a worker's
decision about their housing, so it gets the most attention here.
"""

from __future__ import annotations

import pytest

from contract_trap_finder import safety
from contract_trap_finder.models import (
    ExtractedFlag,
    Finding,
    SourceQuote,
    StructuredDocument,
)

DOC_TEXT = """Artikel 3 - Duur en beeindiging
3.2 De arbeidsovereenkomst eindigt van rechtswege op het moment dat de
terbeschikkingstelling op verzoek van de opdrachtgever eindigt, op dezelfde dag.
"""

CORPUS = {"doc1": DOC_TEXT}


def quote(text: str, doc_id: str = "doc1") -> SourceQuote:
    return SourceQuote(doc_id=doc_id, quote=text)


# --- normalisation ---------------------------------------------------------


def test_normalise_collapses_whitespace_and_case():
    assert safety.normalise_text("De  ARBEIDS\novereenkomst") == "de arbeids overeenkomst"


def test_normalise_joins_words_split_across_a_line_break():
    # PDF extractors hyphenate at line ends; the word is not really hyphenated.
    assert "terbeschikkingstelling" in safety.normalise_text("terbeschikking-\nstelling")


def test_normalise_folds_curly_quotes_and_dashes():
    assert safety.normalise_text("“test” – x") == safety.normalise_text('"test" - x')


# --- match_ratio -----------------------------------------------------------


def test_exact_quote_scores_one():
    assert safety.match_ratio("op dezelfde dag", DOC_TEXT) == 1.0


def test_quote_differing_only_in_whitespace_scores_one():
    assert safety.match_ratio("De   arbeidsovereenkomst\n eindigt", DOC_TEXT) == 1.0


def test_fabricated_quote_scores_low():
    ratio = safety.match_ratio(
        "De werkgever betaalt een bonus van EUR 5.000 bij goed functioneren.", DOC_TEXT
    )
    assert ratio < safety.config.GROUNDING_MIN_RATIO


def test_paraphrase_does_not_pass_the_threshold():
    # The meaning is right, the words are not. This must still be rejected: a quote
    # the worker cannot find in their own document is not evidence they can use.
    ratio = safety.match_ratio(
        "The employment ends automatically when the assignment ends.", DOC_TEXT
    )
    assert ratio < safety.config.GROUNDING_MIN_RATIO


def test_empty_quote_scores_zero():
    assert safety.match_ratio("", DOC_TEXT) == 0.0


# --- verify_quote ----------------------------------------------------------


def test_verify_accepts_a_real_quote():
    grounded, ratio, corrected = safety.verify_quote(quote("op dezelfde dag"), CORPUS)
    assert grounded and ratio == 1.0 and corrected is None


def test_verify_rejects_an_invented_quote():
    grounded, _ratio, _corrected = safety.verify_quote(quote("De werknemer ontvangt een auto van de zaak."), CORPUS)
    assert not grounded


def test_verify_corrects_a_mislabelled_document_id():
    # Real text, wrong file named. That is a citation error, not a fabrication.
    corpus = {"doc1": DOC_TEXT, "doc2": "Iets heel anders."}
    grounded, _ratio, corrected = safety.verify_quote(quote("op dezelfde dag", doc_id="doc2"), corpus)
    assert grounded and corrected == "doc1"


# --- findings --------------------------------------------------------------


def make_finding(finding_id: str, quote_text: str) -> Finding:
    return Finding(
        id=finding_id,
        category="RISK_SHIFT",
        severity="high",
        title="t",
        what_it_means="w",
        quotes=[quote(quote_text)],
    )


def test_ground_findings_keeps_real_and_drops_invented():
    kept, dropped = safety.ground_findings(
        [
            make_finding("real", "op dezelfde dag"),
            make_finding("invented", "De werkgever verstrekt een pensioenregeling van 12%."),
        ],
        CORPUS,
    )
    assert [f.id for f in kept] == ["real"]
    assert [f.id for f in dropped] == ["invented"]


def test_a_flag_without_a_surviving_quote_becomes_absent():
    """A flag the model asserts but cannot evidence must not reach the legal checks."""
    doc = StructuredDocument(
        doc_id="doc1",
        doc_type="employment_contract",
        detected_language="nl",
        extraction_confidence=0.9,
        flags=[
            ExtractedFlag(flag="contract_ends_with_assignment", present=True, source=quote("op dezelfde dag")),
            ExtractedFlag(flag="identity_document_retained", present=True, source=quote("Het paspoort wordt ingenomen.")),
            ExtractedFlag(flag="no_guaranteed_hours", present=True, source=None),
        ],
    )
    grounded = safety.ground_structured_document(doc, CORPUS)
    assert [f.flag for f in grounded.flags] == ["contract_ends_with_assignment"]


# --- missing documents -----------------------------------------------------


def test_missing_documents_are_inferred_from_what_the_bundle_refers_to():
    doc = StructuredDocument(
        doc_id="doc1",
        doc_type="employment_contract",
        detected_language="nl",
        extraction_confidence=0.9,
        flags=[ExtractedFlag(flag="housing_tied_to_employment", present=True, source=quote("op dezelfde dag"))],
    )
    missing = safety.detect_missing_documents([doc])
    assert any("housing" in m.lower() for m in missing)
    assert not any("employment contract" in m.lower() for m in missing)


# --- the gate --------------------------------------------------------------


def test_conflicting_documents_always_gate():
    gated, reason = safety.should_gate(confidence=0.99, conflicts=["two different hourly rates"])
    assert gated and reason


def test_low_confidence_gates():
    gated, _reason = safety.should_gate(confidence=0.10, conflicts=[])
    assert gated


def test_good_confidence_without_conflicts_does_not_gate():
    gated, reason = safety.should_gate(confidence=0.95, conflicts=[])
    assert not gated and reason is None


def test_confidence_takes_the_weakest_document_not_the_average():
    docs = [
        StructuredDocument(doc_id="a", doc_type="employment_contract", detected_language="nl", extraction_confidence=1.0),
        StructuredDocument(doc_id="b", doc_type="housing_agreement", detected_language="nl", extraction_confidence=0.2),
    ]
    confidence = safety.compute_overall_confidence(docs, reasoning_confidence=1.0, dropped_count=0, kept_count=3)
    assert confidence <= 0.2


def test_an_unstated_reasoning_confidence_does_not_zero_the_score():
    """None means the model did not say. Only a stated 0.0 means no confidence."""
    docs = [
        StructuredDocument(doc_id="a", doc_type="employment_contract", detected_language="nl", extraction_confidence=0.9),
    ]
    unstated = safety.compute_overall_confidence(docs, reasoning_confidence=None, dropped_count=0, kept_count=2)
    stated_zero = safety.compute_overall_confidence(docs, reasoning_confidence=0.0, dropped_count=0, kept_count=2)

    assert unstated > 0.0
    assert stated_zero == 0.0


def test_a_document_that_does_not_rate_itself_does_not_zero_the_score():
    docs = [
        StructuredDocument(doc_id="a", doc_type="employment_contract", detected_language="nl", extraction_confidence=0.9),
        StructuredDocument(doc_id="b", doc_type="housing_agreement", detected_language="nl"),
    ]
    assert docs[1].extraction_confidence is None

    confidence = safety.compute_overall_confidence(docs, reasoning_confidence=0.9, dropped_count=0, kept_count=2)
    assert confidence > 0.0


def test_no_confidence_signal_at_all_scores_zero_and_gates():
    """Nothing stated anywhere is not the same as everything being fine."""
    docs = [StructuredDocument(doc_id="a", doc_type="employment_contract", detected_language="nl")]

    confidence = safety.compute_overall_confidence(docs, reasoning_confidence=None, dropped_count=0, kept_count=0)
    assert confidence == 0.0
    assert safety.should_gate(confidence, conflicts=[])[0]


# --- no instructions to act ------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Do not sign this contract.",
        "You should quit and find another employer.",
        "This contract is fine.",
        "No problems found.",
    ],
)
def test_instruction_language_is_detected(text):
    assert safety.find_instruction_language(text)


def test_plain_description_is_not_flagged():
    assert not safety.find_instruction_language(
        "If your work ends on a Friday, you must leave the accommodation within three days."
    )


# --- a finding routes to a person ------------------------------------------


def test_the_talk_to_a_human_message_says_the_check_is_automated_and_incomplete():
    """The rubric for this project is honesty about what the tool cannot do.

    Three things have to be in that sentence or it is decoration: that a machine did
    the reading, that it can be wrong, and that a person should look at it. Asserted
    on the text rather than trusted to survive an edit, because this is the one line
    standing between a confident report and a user who cannot check it.
    """
    message = safety.TALK_TO_A_HUMAN.lower()
    assert "computer" in message
    assert "misses things" in message
    assert "talk to a person" in message


def test_the_talk_to_a_human_message_does_not_instruct_the_user_to_act():
    """It sends people to advice, not to a decision. Rule 5 applies to it too."""
    assert not safety.find_instruction_language(safety.TALK_TO_A_HUMAN)
