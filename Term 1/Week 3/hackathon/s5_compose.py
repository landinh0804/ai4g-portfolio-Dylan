"""Step 5 — Compose. LLM.

Writes the findings, the exit timeline and the safe questions, in the user's
language. The contacts section is not written by the model; it is fixed data from
`rules/contacts.json`, because a hallucinated helpline number given to someone who
is frightened to call at all is a specific, foreseeable harm.

**The model cannot overturn a legal check.** Deterministic findings are sent in with
ids prefixed `DET-`, and whatever comes back is reconciled against the originals in
`_reconcile_findings`: the model's wording is kept, and the category, severity,
quotes, rule id and verification status are restored from the original. A
deterministic finding the model drops is put back. So the worst a bad compose call
can do is phrase a finding poorly — it cannot delete an illegality or invent one.
"""

from __future__ import annotations

import json
import logging

from .. import config, safety
from ..llm import LLMClient, LLMError, load_prompt
from ..models import (
    ComposedOutput,
    ContactOption,
    CrossReferenceResult,
    ExitScenario,
    Finding,
    StructuredDocument,
)
from ..rules import load_contacts
from .s3_cross_reference import _summarise_for_reasoning

logger = logging.getLogger(__name__)


class ComposeFailure(LLMError):
    """The composition step failed. The caller falls back to untranslated findings."""


def _build_prompt(
    docs: list[StructuredDocument],
    cross_reference: CrossReferenceResult,
    deterministic_findings: list[Finding],
    language_name: str,
) -> str:
    payload = {
        "documents": [_summarise_for_reasoning(d) for d in docs],
        "cross_document_analysis": cross_reference.model_dump(mode="json"),
        "findings_already_established_by_code": [
            {
                "id": f.id,
                "category": f.category,
                "severity": f.severity,
                "title_in_english": f.title,
                "what_it_means_in_english": f.what_it_means,
                "quotes": [q.model_dump(mode="json") for q in f.quotes],
            }
            for f in deterministic_findings
        ],
    }

    return (
        f"Write your output in this language: {language_name}.\n\n"
        "--- BEGIN ANALYSIS DATA ---\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
        "--- END ANALYSIS DATA ---\n\n"
        f"There are {len(deterministic_findings)} finding(s) already established by code. Return every one "
        "of them, keeping its id exactly, with the title and explanation rewritten in "
        f"{language_name}. Add your own findings only where the combination of documents shows something "
        "the code checks would miss, and give those ids beginning MOD-.\n\n"
        "Then write the exit scenario timeline and the safe questions, also in "
        f"{language_name}. Keep every quote in its original language, exactly as it appears in the data above."
    )


def compose(
    docs: list[StructuredDocument],
    cross_reference: CrossReferenceResult,
    deterministic_findings: list[Finding],
    corpus: dict[str, str],
    client: LLMClient,
    language: str = config.DEFAULT_LANGUAGE,
) -> tuple[list[Finding], ExitScenario | None, list, list[str], int]:
    """Produce the user-facing output.

    Returns `(findings, exit_scenario, safe_questions, notes, dropped_count)`. On
    failure the deterministic findings are returned unchanged in English rather than
    nothing, so a compose outage costs the user translation and the timeline, not the
    analysis.
    """
    notes: list[str] = []
    language_name = config.SUPPORTED_LANGUAGES.get(language, language)

    try:
        result = client.generate_json(
            prompt=_build_prompt(docs, cross_reference, deterministic_findings, language_name),
            schema_model=ComposedOutput,
            system_instruction=load_prompt("compose"),
            temperature=config.TEMPERATURE_COMPOSE,
            role=config.ROLE_COMPOSE,
        )
    except LLMError as exc:
        logger.warning("Compose failed, falling back to untranslated findings: %s", exc)
        notes.append(
            "We could not write this report in your language, so the findings below are shown in English "
            "as the system recorded them. The findings themselves are unaffected."
        )
        return deterministic_findings, None, [], notes, 0

    findings, dropped_count = _reconcile_findings(result.findings, deterministic_findings, corpus, notes)
    exit_scenario = _ground_exit_scenario(result.exit_scenario, corpus)
    questions = result.safe_questions

    # Backstop for rule 5 of the brief: the output must never instruct the user to
    # act, or declare the contract safe. The prompt is the primary control; this
    # catches English-language slips and records them for review.
    for finding in findings:
        offending = safety.find_instruction_language(f"{finding.title} {finding.what_it_means}")
        if offending:
            logger.warning("Instruction-like language in finding %s: %s", finding.id, offending)
            notes.append(
                f"Internal check: finding {finding.id} contained language that tells the reader what to do "
                "or declares the contract safe. Flagged for review."
            )

    return findings, exit_scenario, questions, notes, dropped_count


def _reconcile_findings(
    composed: list[Finding],
    deterministic: list[Finding],
    corpus: dict[str, str],
    notes: list[str],
) -> tuple[list[Finding], int]:
    """Keep the model's wording, restore the code's verdicts.

    For every deterministic finding, the authoritative fields come from the original
    regardless of what came back. Anything the model dropped is reinstated. Model-added
    findings are kept only if at least one quote survives verification.

    Returns the findings and the number discarded for being ungrounded or invented,
    so the report can show the user how much the guard actually caught.
    """
    by_id = {f.id: f for f in deterministic}
    out: list[Finding] = []
    seen: set[str] = set()
    dropped = 0

    for finding in composed:
        original = by_id.get(finding.id)

        if original is not None:
            seen.add(finding.id)
            out.append(
                original.model_copy(
                    update={
                        "title": finding.title or original.title,
                        "what_it_means": finding.what_it_means or original.what_it_means,
                    }
                )
            )
            continue

        if finding.id.startswith("DET-"):
            # A DET- id the code never issued: the model invented a legal verdict.
            notes.append(f"Internal check: discarded an invented rule-based finding ({finding.id}).")
            dropped += 1
            continue

        grounded = safety.ground_quotes(finding.quotes, corpus)
        if not grounded:
            logger.info("Dropped model finding %s: no quote could be found in the documents", finding.id)
            dropped += 1
            continue
        out.append(finding.model_copy(update={"quotes": grounded, "origin": "model", "rule_id": None}))

    missing = [f for f in deterministic if f.id not in seen]
    if missing:
        logger.info("Reinstating %s deterministic finding(s) the model did not return", len(missing))
        out.extend(missing)

    from .s4_legal_checks import sort_findings

    return sort_findings(out), dropped


def _ground_exit_scenario(scenario: ExitScenario, corpus: dict[str, str]) -> ExitScenario:
    """Drop timeline events that are not anchored in the documents."""
    events = []
    for event in scenario.events:
        quotes = safety.ground_quotes(event.quotes, corpus)
        if quotes:
            events.append(event.model_copy(update={"quotes": quotes}))

    caveat = scenario.caveat
    if len(events) < len(scenario.events):
        dropped = len(scenario.events) - len(events)
        extra = f"{dropped} step(s) could not be traced back to your documents and were removed."
        caveat = f"{caveat} {extra}" if caveat else extra

    return scenario.model_copy(update={"events": events, "caveat": caveat})


def get_contacts(language: str) -> list[ContactOption]:
    """Fixed contact data, confidential advice first, enforcement last.

    Never model-generated. Organisations that cover the user's language are listed
    before those that do not.
    """
    data = load_contacts()["contacts"]
    kind_order = {"confidential_advice": 0, "legal_aid": 1, "enforcement": 2}

    def sort_key(entry: dict) -> tuple[int, int, str]:
        speaks_language = 0 if language in entry.get("languages", []) else 1
        return (kind_order.get(entry["kind"], 9), speaks_language, entry["name"])

    contacts: list[ContactOption] = []
    for entry in sorted(data, key=sort_key):
        contact_line = entry["contact"]
        if not entry.get("verified", False):
            contact_line = f"{contact_line} (check the website — we have not verified this detail)"
        contacts.append(
            ContactOption(
                name=entry["name"],
                kind=entry["kind"],
                what_they_do=entry["what_they_do"],
                will_employer_find_out=entry["will_employer_find_out"],
                typical_response_time=entry["typical_response_time"],
                contact=contact_line,
                url=entry.get("url"),
            )
        )
    return contacts
