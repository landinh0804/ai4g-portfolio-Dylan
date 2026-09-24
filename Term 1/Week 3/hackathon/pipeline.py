"""The orchestrator: raw documents in, `Report` out.

Order of operations, and why:

    ingest -> structure -> cross-reference -> legal checks -> [GATE] -> compose

The confidence gate sits *before* composition, not after. If the documents conflict
with each other, or too little of them could be read, the tool stops and routes the
user to a human instead of writing a fluent summary of something it does not
understand. Composing first and then hiding the result would still have paid for the
call, and would leave a well-written wrong answer sitting in memory next to the
warning. Refusing earlier is both cheaper and harder to get wrong.

Deterministic findings are still shown when gated, because a rule check that fired
on a verified quote does not become less true when another document is unreadable.
What is withheld is the *summary*: the timeline and the questions, which depend on
the whole bundle hanging together.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from . import config, safety
from .llm import LLMClient, build_client
from .models import CrossReferenceResult, DocumentSummary, Report
from .progress import Progress, ProgressCallback, plural
from .rules import unverified_reference_values, unverified_rule_ids
from .steps import s2_structure, s3_cross_reference, s4_legal_checks, s5_compose
from .steps.s1_ingest import RawDocument, build_corpus, from_path

logger = logging.getLogger(__name__)


def analyse(
    documents: list[RawDocument],
    language: str = config.DEFAULT_LANGUAGE,
    client: LLMClient | None = None,
    progress: ProgressCallback | None = None,
) -> Report:
    """Run the whole pipeline over one bundle of documents."""
    say = Progress(progress)
    started = datetime.now(timezone.utc)
    notes: list[str] = []

    if not documents:
        return _empty_report(language, started, "No documents were provided.")

    client = client or build_client()
    corpus = build_corpus(documents)

    # Name the backend before anything slow happens. When a run takes two minutes,
    # the first thing worth knowing is what it is waiting on.
    say.result(
        f"{getattr(client, 'provider_label', 'model')}  {plural(sum(d.char_count for d in documents), 'character')} "
        f"across {plural(len(documents), 'document')}"
    )

    for document in documents:
        notes.extend(document.warnings)

    # --- Step 2 ---------------------------------------------------------
    say.step(f"Reading {plural(len(documents), 'document')}")
    structured, failures = s2_structure.structure_documents(documents, client, say)

    for failure in failures:
        notes.append(
            f"We could not read {failure.filename}. Anything in that document is missing from this report."
        )
        say.warn(f"Could not read {failure.filename}: {failure.cause}")

    say.result(_structure_summary(structured, len(documents)))

    if not structured:
        return _empty_report(
            language,
            started,
            "None of the documents could be read well enough to analyse.",
            notes=notes,
            contacts=s5_compose.get_contacts(language),
        )

    # --- Step 3 ---------------------------------------------------------
    #
    # `None` means the step failed; anything else means it ran. The two used to be
    # the same value — a result with `reasoning_confidence == 0.0` — which a
    # *successful* call produced simply by leaving the field out of its JSON. Every
    # completed comparison was therefore announced to the user as one that never
    # ran, and zeroed the confidence that decides whether the report is written at
    # all. Keep these two facts apart.
    say.step("Comparing the documents against each other")
    comparison = s3_cross_reference.cross_reference(structured, client, corpus)

    if comparison is None:
        cross_reference = CrossReferenceResult(reasoning_confidence=0.0)
        notes.append(
            "The comparison between your documents did not complete, so this report covers each document "
            "on its own rather than how they work together."
        )
        say.warn("The comparison step did not complete; each document is covered on its own.")
    else:
        cross_reference = comparison
        say.result(_cross_reference_summary(cross_reference))
        for conflict in cross_reference.conflicts:
            say.warn(f"Documents disagree: {conflict}")
        if cross_reference.reasoning_confidence is None:
            notes.append(
                "The comparison between your documents ran, but it did not rate how reliable its own "
                "reading was. Its findings are included; the confidence score below is based on the rest "
                "of the checks."
            )

    # --- Step 4 ---------------------------------------------------------
    say.step("Checking against the legal rules")
    deterministic_findings, check_notes = s4_legal_checks.run_checks(structured)
    notes.extend(check_notes)
    say.result(
        f"{plural(len(deterministic_findings), 'rule')} fired out of "
        f"{plural(_rule_count(), 'rule')} checked"
    )
    for note in check_notes:
        say.warn(note)

    missing_documents = safety.detect_missing_documents(structured)
    if missing_documents:
        say.result(f"{plural(len(missing_documents), 'document')} referred to but not supplied")

    # --- The gate -------------------------------------------------------
    confidence = safety.compute_overall_confidence(
        docs=structured,
        reasoning_confidence=cross_reference.reasoning_confidence,
        dropped_count=0,
        kept_count=len(deterministic_findings),
    )
    confidence = _penalise_degraded_model(confidence, client, notes)
    gated, gate_reason = safety.should_gate(confidence, cross_reference.conflicts)

    say.step("Deciding whether we are confident enough to summarise")
    say.result(f"Confidence {confidence:.0%}, and the gate sits at {config.CONFIDENCE_GATE:.0%}")

    if gated:
        say.warn(f"Stopping before the summary: {gate_reason}")
        logger.info("Gated: %s (confidence %.2f)", gate_reason, confidence)
        return Report(
            generated_at=started,
            user_language=language,
            documents_received=_summaries(documents, structured),
            missing_documents=missing_documents,
            findings=s4_legal_checks.sort_findings(deterministic_findings),
            exit_scenario=None,
            safe_questions=[],
            contacts=s5_compose.get_contacts(language),
            overall_confidence=confidence,
            gated=True,
            gate_reason=gate_reason,
            conflicts=cross_reference.conflicts,
            unverified_rule_ids=_unverified_used(deterministic_findings),
            notes=notes,
        )

    # --- Step 5 ---------------------------------------------------------
    say.step(f"Writing your report in {config.SUPPORTED_LANGUAGES.get(language, language)}")
    findings, exit_scenario, safe_questions, compose_notes, dropped_in_compose = s5_compose.compose(
        docs=structured,
        cross_reference=cross_reference,
        deterministic_findings=deterministic_findings,
        corpus=corpus,
        client=client,
        language=language,
    )
    notes.extend(compose_notes)
    for note in compose_notes:
        say.warn(note)

    # Final grounding pass. Deterministic findings were built from already-verified
    # quotes, so this is a no-op for them; it is the model-added findings it catches.
    say.step("Checking every quote against your documents")
    kept, dropped = safety.ground_findings(findings, corpus)
    if dropped:
        logger.info("Dropped %s finding(s) with unverifiable quotes", len(dropped))

    # Findings discarded during composition are counted too, so the number the user
    # sees is every suggestion the grounding check rejected, not just the last pass.
    total_dropped = len(dropped) + dropped_in_compose

    # The single most important number in this narration. It is the guardrail
    # working: every one of these was a clause the model put in the report that it
    # could not point to in the documents.
    if total_dropped:
        say.warn(
            f"{plural(total_dropped, 'suggested finding')} discarded - the quoted text is not in your documents"
        )
    say.result(f"{plural(len(kept), 'finding')} kept, {plural(len(safe_questions), 'question')} to ask")

    confidence = safety.compute_overall_confidence(
        docs=structured,
        reasoning_confidence=cross_reference.reasoning_confidence,
        dropped_count=total_dropped,
        kept_count=len(kept),
    )
    confidence = _penalise_degraded_model(confidence, client, notes)

    return Report(
        generated_at=started,
        user_language=language,
        documents_received=_summaries(documents, structured),
        missing_documents=missing_documents,
        findings=s4_legal_checks.sort_findings(kept),
        exit_scenario=exit_scenario,
        safe_questions=safe_questions,
        contacts=s5_compose.get_contacts(language),
        overall_confidence=confidence,
        gated=False,
        gate_reason=None,
        conflicts=cross_reference.conflicts,
        dropped_finding_count=total_dropped,
        unverified_rule_ids=_unverified_used(kept),
        notes=notes,
    )


def analyse_paths(
    paths: list[str],
    language: str = config.DEFAULT_LANGUAGE,
    client: LLMClient | None = None,
    progress: ProgressCallback | None = None,
) -> Report:
    """Convenience wrapper for the CLI and the tests."""
    documents = [from_path(path, index) for index, path in enumerate(paths)]
    return analyse(documents, language=language, client=client, progress=progress)


def _structure_summary(structured: list, asked_for: int) -> str:
    """What step 2 actually got out of the documents.

    Counts rather than adjectives, because counts are what let a reader tell a good
    run from a bad one. A local model that returns a valid but nearly empty
    `StructuredDocument` is the characteristic failure of this pipeline - the JSON
    parses, the run completes, and the report is quietly thin. "3 of 3 read, 0 money
    terms" says that happened; "Done" does not.
    """
    if not structured:
        return f"Nothing readable in {plural(asked_for, 'document')}"

    money = sum(len(doc.money_terms) for doc in structured)
    parties = sum(len(doc.parties) for doc in structured)
    endings = sum(len(doc.termination_conditions) for doc in structured)
    flags = sum(len(doc.flags) for doc in structured)

    confidences = [doc.extraction_confidence for doc in structured if doc.extraction_confidence is not None]
    read = f"{len(structured)} of {asked_for} read"
    if confidences:
        read += f" (extraction confidence {sum(confidences) / len(confidences):.0%})"

    return (
        f"{read}  {plural(parties, 'party', 'parties')}, {plural(money, 'money term')}, "
        f"{plural(endings, 'termination condition')}, {plural(flags, 'flag')}"
    )


def _cross_reference_summary(result: CrossReferenceResult) -> str:
    """What step 3 found tying the documents to each other."""
    parts = [
        plural(len(result.dependencies), "dependency", "dependencies"),
        plural(len(result.conflicts), "conflict"),
    ]
    if result.reasoning_confidence is not None:
        parts.append(f"reasoning confidence {result.reasoning_confidence:.0%}")
    return ", ".join(parts)


def _rule_count() -> int:
    """How many rules were available to fire. Reported next to how many did."""
    try:
        from .rules import load_rules

        return len(load_rules()["rules"])
    except Exception:  # noqa: BLE001 - narration must never break the analysis
        return 0


def _summaries(raw: list[RawDocument], structured: list) -> list[DocumentSummary]:
    by_id = {doc.doc_id: doc for doc in structured}
    summaries: list[DocumentSummary] = []
    for document in raw:
        match = by_id.get(document.doc_id)
        summaries.append(
            DocumentSummary(
                doc_id=document.doc_id,
                filename=document.filename,
                doc_type=match.doc_type if match else "unknown",
                detected_language=match.detected_language if match else "unknown",
                char_count=document.char_count,
            )
        )
    return summaries


def _unverified_used(findings: list) -> list[str]:
    """Rule ids in this report whose legal basis the team has not yet confirmed."""
    unverified = set(unverified_rule_ids())
    used = [f.rule_id for f in findings if f.rule_id and f.rule_id in unverified]
    # Reference values feed the computed checks, so an unverified figure taints them too.
    if unverified_reference_values():
        used = list(dict.fromkeys(used))
    return sorted(set(used))


def _penalise_degraded_model(confidence: float, client: LLMClient, notes: list[str]) -> float:
    """Scale confidence down when a model we do not trust produced the analysis.

    The fallback chain exists so an outage does not leave a worker with nothing. The
    cost of that is real: when the whole Flash tier is shedding load, the only ids
    still serving are the `-lite` ones, and a lite model reading an employment
    contract is materially worse at it. Left unmarked, the chain would quietly trade
    a visible failure for an invisible one, which is the worse of the two here.

    So the run is not rejected, it is discounted - enough that a report which was
    already marginal falls below CONFIDENCE_GATE and is routed to a human instead.

    The same discount covers a run on a local model, which is degraded for a
    different reason and says so: each backend supplies its own `degraded_reason`,
    because "we lowered our confidence" without the why is no use to a reader.
    """
    if not client.answered_degraded:
        return confidence

    note = getattr(client, "degraded_reason", None) or (
        f"This report was produced by {client.last_model_used}, a smaller model used only "
        "because the usual ones were unavailable. It is less reliable at reading contracts, "
        "so we have lowered our confidence in this report accordingly."
    )
    if note not in notes:
        notes.append(note)
    return round(confidence * config.DEGRADED_CONFIDENCE_FACTOR, 3)


def _empty_report(
    language: str,
    started: datetime,
    reason: str,
    notes: list[str] | None = None,
    contacts: list | None = None,
) -> Report:
    return Report(
        generated_at=started,
        user_language=language,
        gated=True,
        gate_reason=reason,
        contacts=contacts or [],
        notes=notes or [],
    )
