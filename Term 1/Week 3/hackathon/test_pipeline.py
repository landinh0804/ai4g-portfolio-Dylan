"""End-to-end pipeline tests with a stubbed model.

No API key and no network. The stub returns whatever the test tells it to, which is
how the interesting cases get covered: a model that invents a clause, a model that
tries to delete a legal finding, a model that returns a verdict the code never
issued.
"""

from __future__ import annotations

import pytest

from contract_trap_finder.models import (
    ComposedOutput,
    CrossReferenceResult,
    ExitScenario,
    ExtractedFlag,
    Finding,
    SourceQuote,
    StructuredDocument,
)
from contract_trap_finder import config
from contract_trap_finder.pipeline import analyse
from contract_trap_finder.steps.s1_ingest import from_text

CONTRACT = """Artikel 3 - Duur
3.2 De arbeidsovereenkomst eindigt van rechtswege op het moment dat de
terbeschikkingstelling eindigt, op dezelfde dag.

Artikel 5 - Bemiddeling
5.1 Voor de plaatsing is de uitzendkracht een bemiddelingsvergoeding verschuldigd
van EUR 350,00.
"""

HOUSING = """Artikel 1
1.1 De accommodatie wordt ter beschikking gesteld in verband met de
terbeschikkingstelling.

Artikel 3
3.2 De gebruiker dient de accommodatie te verlaten binnen drie kalenderdagen na het
einde van de arbeidsovereenkomst.
"""


def documents():
    return [from_text(CONTRACT, "contract.txt", 0), from_text(HOUSING, "housing.txt", 1)]


class FakeClient:
    """Stands in for GeminiClient, dispatching on the requested schema."""

    def __init__(self, structured=None, cross=None, composed=None, model="gemini-3.8-flash"):
        self._structured = structured or {}
        self._cross = cross
        self._composed = composed
        self.calls: list[str] = []
        self.last_model_used = model

    @property
    def answered_degraded(self) -> bool:
        return config.is_degraded_model(self.last_model_used)

    def generate_json(self, *, prompt, schema_model, **_kwargs):
        self.calls.append(schema_model.__name__)

        if schema_model is StructuredDocument:
            for doc_id, result in self._structured.items():
                if doc_id in prompt:
                    return result
            raise AssertionError("no stubbed structure result matched the prompt")

        if schema_model is CrossReferenceResult:
            return self._cross or CrossReferenceResult(reasoning_confidence=0.9)

        if schema_model is ComposedOutput:
            return self._composed or ComposedOutput(
                exit_scenario=ExitScenario(trigger_description="If your work ends")
            )

        raise AssertionError(f"unexpected schema {schema_model}")


def quote(text: str, doc_id: str) -> SourceQuote:
    return SourceQuote(doc_id=doc_id, quote=text)


def structured_bundle(doc_ids):
    contract_id, housing_id = doc_ids
    return {
        contract_id: StructuredDocument(
            doc_id=contract_id,
            doc_type="employment_contract",
            detected_language="nl",
            extraction_confidence=0.95,
            flags=[
                ExtractedFlag(
                    flag="contract_ends_with_assignment",
                    present=True,
                    source=quote("eindigt van rechtswege op het moment dat de", contract_id),
                ),
                ExtractedFlag(
                    flag="worker_charged_recruitment_fee",
                    present=True,
                    source=quote("een bemiddelingsvergoeding verschuldigd", contract_id),
                ),
            ],
        ),
        housing_id: StructuredDocument(
            doc_id=housing_id,
            doc_type="housing_agreement",
            detected_language="nl",
            extraction_confidence=0.95,
            flags=[
                ExtractedFlag(
                    flag="housing_tied_to_employment",
                    present=True,
                    source=quote("ter beschikking gesteld in verband met de", housing_id),
                )
            ],
        ),
    }


# --- the happy path --------------------------------------------------------


def test_pipeline_produces_a_report_with_findings():
    docs = documents()
    ids = [d.doc_id for d in docs]
    client = FakeClient(structured=structured_bundle(ids))

    report = analyse(docs, language="en", client=client)

    assert not report.gated
    assert report.findings
    rule_ids = {f.rule_id for f in report.findings}
    assert "NL-WAADI-09-FEE" in rule_ids
    assert "RS-TIED-HOUSING" in rule_ids  # only findable across the two documents
    assert client.calls.count("StructuredDocument") == 2


def test_report_lists_the_documents_it_read():
    docs = documents()
    client = FakeClient(structured=structured_bundle([d.doc_id for d in docs]))
    report = analyse(docs, language="en", client=client)
    assert {d.filename for d in report.documents_received} == {"contract.txt", "housing.txt"}


def test_contacts_are_always_present_and_advice_comes_before_enforcement():
    docs = documents()
    client = FakeClient(structured=structured_bundle([d.doc_id for d in docs]))
    report = analyse(docs, language="en", client=client)

    kinds = [c.kind for c in report.contacts]
    assert kinds
    assert kinds.index("confidential_advice") < kinds.index("enforcement")


# --- when the model misbehaves ---------------------------------------------


def test_invented_findings_are_dropped():
    docs = documents()
    ids = [d.doc_id for d in docs]
    composed = ComposedOutput(
        findings=[
            Finding(
                id="MOD-1",
                category="RISK_SHIFT",
                severity="high",
                title="Invented",
                what_it_means="Based on a clause that does not exist.",
                quotes=[quote("De werkgever verstrekt een bonus van EUR 5.000 per jaar.", ids[0])],
                origin="model",
            )
        ],
        exit_scenario=ExitScenario(trigger_description="If your work ends"),
    )
    client = FakeClient(structured=structured_bundle(ids), composed=composed)

    report = analyse(docs, language="en", client=client)

    assert "MOD-1" not in {f.id for f in report.findings}
    assert report.dropped_finding_count >= 1


def test_the_model_cannot_delete_a_legal_finding():
    """A deterministic finding the model omits is put back."""
    docs = documents()
    ids = [d.doc_id for d in docs]
    composed = ComposedOutput(  # returns nothing at all
        findings=[], exit_scenario=ExitScenario(trigger_description="If your work ends")
    )
    client = FakeClient(structured=structured_bundle(ids), composed=composed)

    report = analyse(docs, language="en", client=client)

    assert "NL-WAADI-09-FEE" in {f.rule_id for f in report.findings}


def test_the_model_cannot_invent_a_rule_based_verdict():
    docs = documents()
    ids = [d.doc_id for d in docs]
    composed = ComposedOutput(
        findings=[
            Finding(
                id="DET-NL-MADE-UP-RULE",
                category="ILLEGAL",
                severity="high",
                title="Fabricated illegality",
                what_it_means="The model decided this was unlawful.",
                quotes=[quote("eindigt van rechtswege", ids[0])],
                origin="deterministic",
                rule_id="NL-MADE-UP-RULE",
            )
        ],
        exit_scenario=ExitScenario(trigger_description="If your work ends"),
    )
    client = FakeClient(structured=structured_bundle(ids), composed=composed)

    report = analyse(docs, language="en", client=client)

    assert "NL-MADE-UP-RULE" not in {f.rule_id for f in report.findings}
    assert any("invented" in note.lower() for note in report.notes)


def test_the_model_cannot_change_a_findings_category():
    """Wording is the model's; the verdict is the code's."""
    docs = documents()
    ids = [d.doc_id for d in docs]
    composed = ComposedOutput(
        findings=[
            Finding(
                id="DET-NL-WAADI-09-FEE",
                category="BELOW_EQUAL_TREATMENT",  # downgraded by the model
                severity="low",
                title="Opłata za pośrednictwo",
                what_it_means="Pobrano od Ciebie opłatę za znalezienie pracy.",
                quotes=[],
                origin="model",
            )
        ],
        exit_scenario=ExitScenario(trigger_description="If your work ends"),
    )
    client = FakeClient(structured=structured_bundle(ids), composed=composed)

    report = analyse(docs, language="pl", client=client)

    fee = next(f for f in report.findings if f.rule_id == "NL-WAADI-09-FEE")
    assert fee.category == "ILLEGAL"  # restored
    assert fee.severity == "high"  # restored
    assert fee.title == "Opłata za pośrednictwo"  # model's wording kept
    assert fee.quotes  # original evidence restored


# --- gating ----------------------------------------------------------------


def test_conflicting_documents_gate_before_composing():
    docs = documents()
    ids = [d.doc_id for d in docs]
    client = FakeClient(
        structured=structured_bundle(ids),
        cross=CrossReferenceResult(reasoning_confidence=0.9, conflicts=["two different hourly rates"]),
    )

    report = analyse(docs, language="en", client=client)

    assert report.gated
    assert report.exit_scenario is None
    assert report.safe_questions == []
    assert report.contacts  # the user is still routed somewhere
    assert "ComposedOutput" not in client.calls  # the call was never made


def test_unreadable_documents_gate():
    docs = documents()
    ids = [d.doc_id for d in docs]
    bundle = structured_bundle(ids)
    for doc_id in bundle:
        bundle[doc_id] = bundle[doc_id].model_copy(update={"extraction_confidence": 0.1})
    client = FakeClient(structured=bundle)

    report = analyse(docs, language="en", client=client)
    assert report.gated


def test_no_documents_returns_a_gated_report_not_a_crash():
    report = analyse([], language="en")
    assert report.gated
    assert report.findings == []


# --- missing documents -----------------------------------------------------


def test_missing_housing_agreement_is_named():
    """Only the employment contract is uploaded, but it refers to housing."""
    docs = [from_text(CONTRACT, "contract.txt", 0)]
    doc_id = docs[0].doc_id
    structured = {
        doc_id: StructuredDocument(
            doc_id=doc_id,
            doc_type="employment_contract",
            detected_language="nl",
            extraction_confidence=0.95,
            flags=[
                ExtractedFlag(
                    flag="housing_tied_to_employment",
                    present=True,
                    source=quote("eindigt van rechtswege", doc_id),
                )
            ],
        )
    }
    report = analyse(docs, language="en", client=FakeClient(structured=structured))
    assert any("housing" in m.lower() for m in report.missing_documents)


# --- a comparison that ran is not a comparison that failed -------------------
#
# The regression these cover: `reasoning_confidence` is not something the model is
# obliged to answer, and Gemini did in fact leave it out. Pydantic filled in the
# field's default of 0.0, which was also the value the *failure* path returned, so a
# comparison that completed and found a tied-housing dependency was announced to the
# user as one that never ran and had its confidence zeroed on the way out.


def test_a_comparison_that_omits_its_confidence_is_not_reported_as_failed():
    docs = documents()
    ids = [d.doc_id for d in docs]

    # Exactly what came back from the API: every other field populated, no
    # reasoning_confidence.
    silent = CrossReferenceResult(
        same_or_related_entities=["Westhoek Flexwerk B.V. and Westhoek Huisvesting B.V."],
        conflicts=[],
    )
    assert silent.reasoning_confidence is None

    report = analyse(docs, client=FakeClient(structured=structured_bundle(ids), cross=silent))

    assert not any("did not complete" in note for note in report.notes)
    assert not report.gated
    assert report.overall_confidence > 0.0


def test_a_comparison_that_actually_failed_is_reported_as_failed():
    from contract_trap_finder.llm import LLMUnavailable

    docs = documents()
    ids = [d.doc_id for d in docs]

    class FailingCrossReference(FakeClient):
        def generate_json(self, *, prompt, schema_model, **kwargs):
            if schema_model is CrossReferenceResult:
                raise LLMUnavailable("simulated outage")
            return super().generate_json(prompt=prompt, schema_model=schema_model, **kwargs)

    report = analyse(docs, client=FailingCrossReference(structured=structured_bundle(ids)))

    assert any("did not complete" in note for note in report.notes)
    # The deterministic findings survive a failed comparison; only the cross-document
    # layer is lost.
    assert report.findings


def test_a_model_stating_zero_confidence_is_still_believed():
    """0.0 from the model is a real answer, and must still gate the report."""
    docs = documents()
    ids = [d.doc_id for d in docs]

    report = analyse(
        docs,
        client=FakeClient(
            structured=structured_bundle(ids),
            cross=CrossReferenceResult(reasoning_confidence=0.0),
        ),
    )

    assert report.gated
    assert not any("did not complete" in note for note in report.notes)


# --- degradation -----------------------------------------------------------


def test_a_failed_compose_still_returns_the_legal_findings():
    from contract_trap_finder.llm import LLMUnavailable

    docs = documents()
    ids = [d.doc_id for d in docs]

    class FailingCompose(FakeClient):
        def generate_json(self, *, prompt, schema_model, **kwargs):
            if schema_model is ComposedOutput:
                raise LLMUnavailable("simulated outage")
            return super().generate_json(prompt=prompt, schema_model=schema_model, **kwargs)

    report = analyse(docs, language="pl", client=FailingCompose(structured=structured_bundle(ids)))

    assert report.findings
    assert any("English" in note for note in report.notes)


def test_one_unreadable_document_does_not_lose_the_others():
    from contract_trap_finder.llm import LLMInvalidOutput

    docs = documents()
    ids = [d.doc_id for d in docs]
    bundle = structured_bundle(ids)

    class PartialFailure(FakeClient):
        def generate_json(self, *, prompt, schema_model, **kwargs):
            if schema_model is StructuredDocument and ids[1] in prompt:
                raise LLMInvalidOutput("simulated bad output")
            return super().generate_json(prompt=prompt, schema_model=schema_model, **kwargs)

    report = analyse(docs, language="en", client=PartialFailure(structured=bundle))

    assert report.findings  # the readable document still produced findings
    assert any("housing.txt" in note for note in report.notes)


# --- the report never declares the contract safe ---------------------------


def test_a_report_with_no_findings_does_not_say_the_contract_is_fine():
    from contract_trap_finder.cli import render_text

    docs = documents()
    ids = [d.doc_id for d in docs]
    empty = {
        doc_id: StructuredDocument(
            doc_id=doc_id, doc_type="employment_contract", detected_language="nl", extraction_confidence=0.95
        )
        for doc_id in ids
    }
    report = analyse(docs, language="en", client=FakeClient(structured=empty))

    assert not report.findings
    text = render_text(report).lower()

    # The phrase "this contract is fine" may appear only inside its own denial.
    assert "we did not find these specific problems" in text
    assert "not the same as saying this contract is fine" in text
    assert text.count("contract is fine") == 1


def test_a_report_with_findings_tells_the_reader_to_talk_to_a_person():
    """The other half of the "no safe verdict" rule.

    A quiet report is bounded by NO_FINDINGS_MESSAGE. A report full of quoted,
    specific, correct findings is the one a user is most likely to read as the whole
    truth about their contract, and it gets `TALK_TO_A_HUMAN` above the findings for
    that reason — above, because a reader who has reached the bottom of the list has
    already decided what it means.
    """
    from contract_trap_finder.cli import render_text
    from contract_trap_finder.safety import TALK_TO_A_HUMAN

    docs = documents()
    ids = [d.doc_id for d in docs]
    report = analyse(docs, language="en", client=FakeClient(structured=structured_bundle(ids)))

    assert report.findings
    text = render_text(report)
    assert TALK_TO_A_HUMAN in text
    assert text.index(TALK_TO_A_HUMAN) < text.index(report.findings[0].title)
