"""The guardrails from section 4 of the brief, implemented as code rather than prose.

This module exists because a tool that tells a worried person at a recruitment desk
something false about their housing is worse than no tool at all. Five rules:

1. **No finding without a quote.** Every quote the model produces is checked back
   against the original document text. Anything that cannot be found is dropped
   before the user sees it. `verify_quote` is the function that does this, and it is
   the single most important thing in the repository.
2. **No safe verdict, ever.** Absence of findings is reported as "we did not find
   these problems in these documents", never as "this contract is fine".
3. **Name the missing documents.** Many workers do not realise they signed three
   separate things, so the gap is itself output.
4. **A confidence gate.** Below threshold, or where documents conflict, the tool
   refuses to summarise and routes to a named human organisation.
5. **No instruction to act.** Enforced in the prompts and re-checked here.

Alongside them, `TALK_TO_A_HUMAN` is shown whenever the run *did* find something.
Rule 4 sends the user to a person when the tool is unsure; that line sends them to a
person when it is sure, because a confident, specific, quoted list of problems is the
output most likely to be mistaken for a complete one.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from . import config
from .models import Finding, SourceQuote, StructuredDocument

# --- Text normalisation ----------------------------------------------------

# Characters that differ between a PDF's text layer and what a model echoes back,
# without any difference in meaning.
_QUOTE_CHARS = dict.fromkeys(map(ord, "‘’‚‛′´`"), "'")
_QUOTE_CHARS.update(dict.fromkeys(map(ord, "“”„‟″"), '"'))
_DASH_CHARS = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")
_DROP_CHARS = dict.fromkeys(map(ord, "­​‌‍﻿"), None)

_TRANSLATION = {**_QUOTE_CHARS, **_DASH_CHARS, **_DROP_CHARS}


def normalise_text(text: str) -> str:
    """Fold away differences that do not change what a clause says.

    Case, whitespace runs, curly vs straight quotes, dash variants, soft hyphens and
    the line breaks a PDF extractor inserts mid-sentence.
    """
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_TRANSLATION)
    text = text.lower()
    # A hyphen at a line break is a word split by the layout, not part of the word.
    text = re.sub(r"-\s*\n\s*", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# --- Rule 1: no finding without a quote ------------------------------------


def match_ratio(quote: str, document_text: str) -> float:
    """How much of `quote` can be found in `document_text`, from 0.0 to 1.0.

    1.0 means the quote appears verbatim once normalised. Lower values mean the
    model altered, paraphrased or invented part of it. The threshold is not 1.0
    because PDF text layers introduce noise that changes no meaning; it is high
    enough that a paraphrase or a fabrication will not pass.
    """
    needle = normalise_text(quote)
    haystack = normalise_text(document_text)

    if not needle or not haystack:
        return 0.0
    if needle in haystack:
        return 1.0

    matcher = SequenceMatcher(None, haystack, needle, autojunk=False)
    anchor = matcher.find_longest_match(0, len(haystack), 0, len(needle))
    if anchor.size == 0:
        return 0.0

    # Compare only the region of the document the quote plausibly came from, so the
    # score is not diluted by the rest of a long contract.
    start = max(0, anchor.a - anchor.b - 20)
    end = min(len(haystack), start + len(needle) + 40)
    window = haystack[start:end]

    matched = sum(block.size for block in SequenceMatcher(None, window, needle, autojunk=False).get_matching_blocks())
    return min(1.0, matched / len(needle))


def verify_quote(
    quote: SourceQuote,
    corpus: dict[str, str],
    threshold: float | None = None,
) -> tuple[bool, float, str | None]:
    """Check one quote against the documents it claims to come from.

    Returns `(grounded, ratio, corrected_doc_id)`. The quote is first checked against
    the document it names. If that fails it is checked against the others, because a
    mislabelled `doc_id` on a real quote is a citation error, not a fabrication, and
    is worth correcting rather than discarding.
    """
    threshold = config.GROUNDING_MIN_RATIO if threshold is None else threshold

    own_text = corpus.get(quote.doc_id)
    if own_text:
        ratio = match_ratio(quote.quote, own_text)
        if ratio >= threshold:
            return True, ratio, None

    best_ratio = 0.0
    best_doc: str | None = None
    for doc_id, text in corpus.items():
        if doc_id == quote.doc_id:
            continue
        ratio = match_ratio(quote.quote, text)
        if ratio > best_ratio:
            best_ratio, best_doc = ratio, doc_id

    if best_ratio >= threshold and best_doc is not None:
        return True, best_ratio, best_doc

    own_ratio = match_ratio(quote.quote, own_text) if own_text else 0.0
    return False, max(own_ratio, best_ratio), None


def ground_quotes(quotes: list[SourceQuote], corpus: dict[str, str]) -> list[SourceQuote]:
    """Keep only the quotes that survive verification, fixing wrong doc ids."""
    kept: list[SourceQuote] = []
    for quote in quotes:
        grounded, _ratio, corrected = verify_quote(quote, corpus)
        if not grounded:
            continue
        if corrected:
            quote = quote.model_copy(update={"doc_id": corrected})
        kept.append(quote)
    return kept


def ground_findings(findings: list[Finding], corpus: dict[str, str]) -> tuple[list[Finding], list[Finding]]:
    """Split findings into those anchored in real document text and those not.

    A finding whose quotes all fail verification is dropped. Deterministic findings
    from `s4_legal_checks` are already built from verified extractions, but they go
    through the same gate so there is exactly one rule, not two.
    """
    kept: list[Finding] = []
    dropped: list[Finding] = []

    for finding in findings:
        grounded = ground_quotes(finding.quotes, corpus)
        if not grounded:
            dropped.append(finding)
            continue
        kept.append(finding.model_copy(update={"quotes": grounded}))

    return kept, dropped


def ground_structured_document(doc: StructuredDocument, corpus: dict[str, str]) -> StructuredDocument:
    """Strip unverifiable extractions out of a structured document.

    Applied straight after step 2, so nothing ungrounded ever reaches the reasoning
    or the legal checks. A flag marked present with no surviving quote becomes
    absent — "the model said so" is not evidence.
    """
    parties = [p for p in doc.parties if verify_quote(p.source, corpus)[0]]
    money_terms = [m for m in doc.money_terms if verify_quote(m.source, corpus)[0]]
    terminations = [t for t in doc.termination_conditions if verify_quote(t.source, corpus)[0]]

    flags = []
    for flag in doc.flags:
        if not flag.present:
            flags.append(flag)
            continue
        if flag.source is None:
            continue
        grounded, _ratio, corrected = verify_quote(flag.source, corpus)
        if not grounded:
            continue
        if corrected:
            flag = flag.model_copy(update={"source": flag.source.model_copy(update={"doc_id": corrected})})
        flags.append(flag)

    return doc.model_copy(
        update={
            "parties": parties,
            "money_terms": money_terms,
            "termination_conditions": terminations,
            "flags": flags,
        }
    )


# --- Rule 3: name the missing documents ------------------------------------

# What a full bundle normally contains, and the evidence that one is referred to
# but was not handed over.
_EXPECTED_DOCUMENTS: dict[str, str] = {
    "employment_contract": "an employment contract with the agency or employer",
    "housing_agreement": "a housing or accommodation agreement",
    "deduction_authorisation": "a written authorisation for deductions from your wage",
}

_IMPLIED_BY_FLAG: dict[str, str] = {
    "housing_tied_to_employment": "housing_agreement",
    "insurance_tied_to_employment": "insurance_agreement",
    "transport_tied_to_employment": "transport_agreement",
    "travel_advance_repaid_by_deduction": "deduction_authorisation",
    "deduction_authorisation_open_ended": "deduction_authorisation",
}

_IMPLIED_BY_MONEY_KIND: dict[str, str] = {
    "housing_cost": "housing_agreement",
    "insurance_premium": "insurance_agreement",
    "transport_cost": "transport_agreement",
    "deduction": "deduction_authorisation",
}

_DOCUMENT_LABELS: dict[str, str] = {
    **_EXPECTED_DOCUMENTS,
    "insurance_agreement": "a health insurance agreement",
    "transport_agreement": "a transport agreement",
}


def detect_missing_documents(docs: list[StructuredDocument]) -> list[str]:
    """Which documents the bundle refers to but does not contain.

    Two sources of evidence: the types a bundle normally has, and the types the
    uploaded documents themselves point at. The second is the stronger signal — if
    the employment contract deducts rent, there is a housing agreement somewhere.
    """
    present = {doc.doc_type for doc in docs}
    missing: list[str] = []
    noted: set[str] = set()

    def note(doc_type: str, reason: str) -> None:
        # One line per document type. A type can be implied by several pieces of
        # evidence, and listing it once per piece would read as several gaps.
        if doc_type in present or doc_type in noted:
            return
        noted.add(doc_type)
        label = _DOCUMENT_LABELS.get(doc_type, doc_type.replace("_", " "))
        missing.append(f"{label} — {reason}")

    # Evidence from the documents themselves comes first, because "your contract
    # charges you rent" is a far stronger thing to tell someone than "bundles
    # usually include one", and only the first reason for a type is kept.
    for doc in docs:
        for term in doc.money_terms:
            if term.kind in _IMPLIED_BY_MONEY_KIND:
                note(_IMPLIED_BY_MONEY_KIND[term.kind], "your documents charge you for it, but we were not given the agreement itself")
        for flag in doc.flags:
            if flag.present and flag.flag in _IMPLIED_BY_FLAG:
                note(_IMPLIED_BY_FLAG[flag.flag], "your documents refer to it, but we were not given it")

    for doc_type in _EXPECTED_DOCUMENTS:
        note(doc_type, "usually part of this kind of bundle, but not among the documents you gave us")

    return missing


# --- Rule 4: the confidence gate -------------------------------------------


def compute_overall_confidence(
    docs: list[StructuredDocument],
    reasoning_confidence: float | None,
    dropped_count: int,
    kept_count: int,
) -> float:
    """A single number combining how well we read the documents and how much the
    model's output survived verification.

    Deliberately pessimistic: it takes the *lowest* self-reported confidence rather
    than the average, because one unreadable page can invalidate the whole
    cross-document picture.

    A score of `None` means the model did not state one, which is not the same as a
    model stating zero. Unstated scores are left out of the minimum rather than
    dragging it to zero: the caller records the gap in the report's notes, and a run
    where *nothing* was stated has no basis for confidence at all and returns 0.0,
    which routes it to a human through `should_gate`.
    """
    if not docs:
        return 0.0

    stated = [doc.extraction_confidence for doc in docs if doc.extraction_confidence is not None]
    if reasoning_confidence is not None:
        stated.append(reasoning_confidence)
    if not stated:
        return 0.0

    total_findings = kept_count + dropped_count
    survival = 1.0 if total_findings == 0 else kept_count / total_findings

    return round(min(stated) * (0.5 + 0.5 * survival), 3)


def should_gate(confidence: float, conflicts: list[str], threshold: float | None = None) -> tuple[bool, str | None]:
    """Decide whether to refuse to summarise and route to a human instead."""
    threshold = config.CONFIDENCE_GATE if threshold is None else threshold

    if conflicts:
        return True, (
            "Your documents say different things in different places, so we cannot tell you "
            "reliably what you would be agreeing to. A person should look at this with you."
        )
    if confidence < threshold:
        return True, (
            "We could not read enough of these documents to be confident about what they say. "
            "Rather than guess, we are pointing you to someone who can read them with you."
        )
    return False, None


# --- Rule 2: no safe verdict -----------------------------------------------

NO_FINDINGS_MESSAGE = (
    "We did not find these specific problems in the documents you gave us. "
    "That is not the same as saying this contract is fine. We can only comment on the "
    "pages we were given, and only on the things we check for."
)

DISCLAIMER = (
    "This is information, not legal advice, and it is produced by an automated system that "
    "can be wrong. It does not tell you whether to sign. If something here matters to you, "
    "check it with one of the organisations listed before you decide."
)

# Shown whenever the run produced findings. The report is at its most persuasive
# exactly where it is least complete: a list of specific, quoted problems reads as a
# finished assessment, and our user cannot tell the difference between what we found
# and what is there. So the output says, in the same breath as the findings, that a
# person should look at this. Rule 4 routes to a human when we are *unsure*; this is
# the line that routes to a human when we are confident, which is the case the gate
# was never going to catch.
TALK_TO_A_HUMAN = (
    "Talk to a person about what is below. This check was done by a computer and a computer "
    "misses things: it can read a clause wrongly, and it cannot see anything that is not in "
    "the pages you gave us. What we found is a starting point for that conversation, not the "
    "whole picture. The organisations at the end of this report will go through these "
    "documents with you. The ones at the top of that list are free and confidential, and each "
    "entry says whether your employer would find out."
)

# Phrases that would turn information into an instruction. Checked against composed
# output as a last line of defence behind the prompt itself.
_INSTRUCTION_PATTERNS = [
    re.compile(r"\b(do not|don't|never)\s+(sign|accept|agree)\b", re.I),
    re.compile(r"\byou should (quit|resign|refuse|leave the job)\b", re.I),
    re.compile(r"\bwe (advise|recommend) (you )?(not )?to sign\b", re.I),
    re.compile(r"\bthis contract is (fine|safe|legal|okay|ok)\b", re.I),
    re.compile(r"\bno problems? (were )?found\b", re.I),
]


def find_instruction_language(text: str) -> list[str]:
    """Return any phrases that instruct the user to act, or declare the contract safe.

    Used by the pipeline to flag output for review. It is a backstop for English
    output; the primary control is the prompt, since this cannot catch every
    phrasing in every language we support. See ETHICS.md.
    """
    return [match.group(0) for pattern in _INSTRUCTION_PATTERNS for match in pattern.finditer(text)]
