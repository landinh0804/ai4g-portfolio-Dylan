"""Step 2 — Structure. LLM.

One call per document: raw text in, typed `StructuredDocument` out. Every extracted
field carries the clause text it came from, and `safety.ground_structured_document`
deletes anything whose quote cannot be found in the original before it goes any
further. Nothing ungrounded reaches the reasoning step or the legal checks.
"""

from __future__ import annotations

import logging

from .. import config, safety
from ..llm import LLMClient, LLMError, load_prompt
from ..models import StructuredDocument
from ..progress import Progress
from .s1_ingest import RawDocument

logger = logging.getLogger(__name__)


class StructureFailure(LLMError):
    """A document could not be structured. Carries the document it failed on."""

    def __init__(self, doc_id: str, filename: str, cause: Exception) -> None:
        super().__init__(f"Could not read {filename}: {cause}")
        self.doc_id = doc_id
        self.filename = filename
        self.cause = cause


def _build_prompt(document: RawDocument) -> str:
    return (
        f"Document id: {document.doc_id}\n"
        f"Filename: {document.filename}\n"
        "Use exactly this document id in every source reference you return.\n\n"
        "--- BEGIN DOCUMENT TEXT ---\n"
        f"{document.text}\n"
        "--- END DOCUMENT TEXT ---\n\n"
        "Extract the structured fields described in your instructions from the text above. "
        "Copy every quote character for character from between the markers."
    )


def structure_document(
    document: RawDocument,
    client: LLMClient,
    corpus: dict[str, str] | None = None,
) -> StructuredDocument:
    """Structure one document and strip anything not anchored in its text."""
    try:
        result = client.generate_json(
            prompt=_build_prompt(document),
            schema_model=StructuredDocument,
            system_instruction=load_prompt("structure"),
            temperature=config.TEMPERATURE_EXTRACTION,
            role=config.ROLE_EXTRACTION,
        )
    except LLMError as exc:
        raise StructureFailure(document.doc_id, document.filename, exc) from exc

    # The model is told which id to use, but the ingested document is the authority.
    result = result.model_copy(update={"doc_id": document.doc_id})

    corpus = corpus if corpus is not None else {document.doc_id: document.text}
    grounded = safety.ground_structured_document(result, corpus)

    dropped = (
        (len(result.parties) - len(grounded.parties))
        + (len(result.money_terms) - len(grounded.money_terms))
        + (len(result.termination_conditions) - len(grounded.termination_conditions))
        + (len(result.flags) - len(grounded.flags))
    )
    if dropped:
        logger.info("Dropped %s ungrounded extraction(s) from %s", dropped, document.doc_id)

    return grounded


def structure_documents(
    documents: list[RawDocument],
    client: LLMClient,
    progress: Progress | None = None,
) -> tuple[list[StructuredDocument], list[StructureFailure]]:
    """Structure every document, collecting failures rather than aborting.

    One unreadable document in a bundle of four should not cost the user the
    analysis of the other three — but the failure is returned so the report can say
    which document is missing from the picture.

    This loop is where most of a run's wall clock goes: one model call per document,
    in series. It reports which document it is on because the alternative - a single
    "Reading 4 documents" for two minutes - is indistinguishable from a hang, and
    because when a run does stall, the document it stalled on is the first thing
    anyone needs to know.
    """
    say = progress or Progress()
    corpus = {doc.doc_id: doc.text for doc in documents}
    structured: list[StructuredDocument] = []
    failures: list[StructureFailure] = []

    for index, document in enumerate(documents, start=1):
        say.detail(f"{index} of {len(documents)}: {document.filename} ({document.char_count:,} characters)")
        try:
            result = structure_document(document, client, corpus)
        except StructureFailure as failure:
            logger.warning("Structuring failed for %s: %s", document.doc_id, failure.cause)
            failures.append(failure)
            continue

        structured.append(result)
        # Per document rather than only in the total, so a single bad extraction in
        # an otherwise good bundle is visible rather than averaged away.
        say.result(
            f"{document.filename}: read as {result.doc_type}, "
            f"{len(result.money_terms)} money term(s), {len(result.flags)} flag(s)"
            + (
                f", extraction confidence {result.extraction_confidence:.0%}"
                if result.extraction_confidence is not None
                else ""
            )
        )

    return structured, failures
