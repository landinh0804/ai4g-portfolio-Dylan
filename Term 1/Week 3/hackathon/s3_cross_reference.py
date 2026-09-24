"""Step 3 — Cross-reference. LLM. The reasoning step.

Takes every structured document at once and asks what is true about the *relationship*
between them: shared entities, dependencies where one ending triggers another, and
obligations that bind only one side.

This is the step that justifies using a language model at all. A clause saying
accommodation is "made available in connection with the assignment" and a clause
saying employment ends when the assignment ends are, together, a statement that the
worker loses their home when the work stops. Neither sentence says that, and no
keyword search over two files with no shared schema will find it.
"""

from __future__ import annotations

import json
import logging

from .. import config, safety
from ..llm import LLMClient, LLMError, load_prompt
from ..models import CrossReferenceResult, StructuredDocument

logger = logging.getLogger(__name__)


def _summarise_for_reasoning(doc: StructuredDocument) -> dict:
    """A compact view of one document: enough to reason over, with quotes intact."""
    return {
        "doc_id": doc.doc_id,
        "doc_type": doc.doc_type,
        "language": doc.detected_language,
        "contracted_hours_per_week": doc.contracted_hours_per_week,
        "parties": [
            {
                "name": p.name,
                "role": p.role,
                "registration_number": p.registration_number,
                "address": p.address,
                "quote": p.source.quote,
            }
            for p in doc.parties
        ],
        "money_terms": [
            {
                "kind": m.kind,
                "label": m.label,
                "amount": m.amount,
                "currency": m.currency,
                "period": m.period,
                "quote": m.source.quote,
            }
            for m in doc.money_terms
        ],
        "termination_conditions": [
            {
                "trigger": t.trigger,
                "effect": t.effect,
                "notice_days_worker": t.notice_days_worker,
                "notice_days_employer": t.notice_days_employer,
                "quote": t.source.quote,
            }
            for t in doc.termination_conditions
        ],
        "flags": [
            {"flag": f.flag, "present": f.present, "quote": f.source.quote if f.source else None}
            for f in doc.flags
        ],
        "extraction_confidence": doc.extraction_confidence,
        "unreadable_sections": doc.unreadable_sections,
    }


def cross_reference(
    documents: list[StructuredDocument],
    client: LLMClient,
    corpus: dict[str, str],
) -> CrossReferenceResult | None:
    """Find relationships between documents, keeping only grounded quotes.

    Returns `None` rather than raising if the model call fails: losing the
    cross-document layer degrades the report, but the deterministic legal checks and
    the single-document findings still stand, and the pipeline records the gap.

    `None` is the *only* signal that this step failed. It used to be a result whose
    `reasoning_confidence` was `0.0`, which a successful call was able to produce by
    omitting the field — so a completed comparison, dependencies and all, was
    reported to the user as one that never ran, and zeroed the report's confidence
    on the way out. Failure and a low score are different facts and now have
    different representations.
    """
    if not documents:
        return CrossReferenceResult(reasoning_confidence=0.0)

    if len(documents) == 1:
        logger.info("Only one document — cross-referencing has little to work with.")

    payload = json.dumps([_summarise_for_reasoning(d) for d in documents], ensure_ascii=False, indent=2)
    prompt = (
        f"You were given {len(documents)} document(s) belonging to one worker.\n\n"
        "--- BEGIN STRUCTURED DOCUMENTS ---\n"
        f"{payload}\n"
        "--- END STRUCTURED DOCUMENTS ---\n\n"
        "Identify shared or related entities, dependencies between documents, asymmetric "
        "obligations, and any conflicts between them."
    )

    try:
        result = client.generate_json(
            prompt=prompt,
            schema_model=CrossReferenceResult,
            system_instruction=load_prompt("cross_reference"),
            temperature=config.TEMPERATURE_REASONING,
            role=config.ROLE_REASONING,
        )
    except LLMError as exc:
        logger.warning("Cross-referencing failed, continuing without it: %s", exc)
        return None

    return _ground(result, corpus)


def _ground(result: CrossReferenceResult, corpus: dict[str, str]) -> CrossReferenceResult:
    """Drop dependencies and asymmetries whose quotes are not in the source text."""
    dependencies = []
    for dep in result.dependencies:
        quotes = safety.ground_quotes(dep.quotes, corpus)
        if quotes:
            dependencies.append(dep.model_copy(update={"quotes": quotes}))

    asymmetries = []
    for asym in result.asymmetries:
        quotes = safety.ground_quotes(asym.quotes, corpus)
        if quotes:
            asymmetries.append(asym.model_copy(update={"quotes": quotes}))

    dropped = (len(result.dependencies) - len(dependencies)) + (len(result.asymmetries) - len(asymmetries))
    if dropped:
        logger.info("Dropped %s ungrounded cross-reference item(s)", dropped)

    return result.model_copy(update={"dependencies": dependencies, "asymmetries": asymmetries})
