"""Typed schemas for every boundary in the pipeline.

Two rules shape this file:

1. Anything the model asserts must carry the exact source text it came from
   (`SourceQuote`). A field with no quote is treated as not extracted. This is what
   makes the "no finding without a quote" rule in `safety.py` enforceable rather
   than aspirational.
2. The model never returns a legal verdict. It returns *observations* (flags,
   amounts, clause text). Whether an observation is unlawful is decided in
   `steps/s4_legal_checks.py` by plain Python against `rules/legal_rules.json`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def _also_required(*names: str):
    """Add `names` to a model's JSON-schema `required` list without replacing it.

    Pydantic leaves any field with a default out of `required`, which for a
    confidence score means the model may simply not answer and Pydantic fills in the
    default. Passing a dict as `json_schema_extra` would overwrite the whole
    `required` list; a callable lets us append to it.
    """

    def apply(schema: dict) -> None:
        required = schema.setdefault("required", [])
        for name in names:
            if name not in required:
                required.append(name)

    return apply


# --- Enumerations ----------------------------------------------------------

DocType = Literal[
    "employment_contract",
    "housing_agreement",
    "deduction_authorisation",
    "transport_agreement",
    "insurance_agreement",
    "general_terms",
    "payslip",
    "unknown",
]

PartyRole = Literal[
    "employer_or_agency",
    "hiring_company",
    "landlord_or_housing_provider",
    "transport_provider",
    "insurer",
    "worker",
    "other",
]

MoneyKind = Literal[
    "wage",
    "deduction",
    "recruitment_or_placement_fee",
    "advance_or_loan",
    "penalty",
    "housing_cost",
    "insurance_premium",
    "transport_cost",
    "expense_reimbursement",
]

Period = Literal["hour", "day", "week", "four_weeks", "month", "year", "one_off", "unknown"]

FindingCategory = Literal["ILLEGAL", "RISK_SHIFT", "BELOW_EQUAL_TREATMENT"]
Severity = Literal["high", "medium", "low"]
Origin = Literal["deterministic", "model"]

# The observations the model is asked to look for. Each is a factual question about
# the text ("does a clause say X?"), never a legal conclusion ("is X allowed?").
FlagName = Literal[
    "worker_charged_recruitment_fee",
    "direct_employment_restricted",
    "identity_document_retained",
    "housing_tied_to_employment",
    "insurance_tied_to_employment",
    "transport_tied_to_employment",
    "contract_ends_with_assignment",
    "no_guaranteed_hours",
    "other_work_prohibited",
    "penalty_for_early_departure",
    "penalty_for_lost_equipment",
    "travel_advance_repaid_by_deduction",
    "asymmetric_notice_period",
    "wage_partly_paid_as_expense_reimbursement",
    "deduction_authorisation_open_ended",
]


# --- Building blocks -------------------------------------------------------


class SourceQuote(BaseModel):
    """Exact text copied from a document, plus where it came from.

    `quote` must be copied verbatim. `safety.verify_quote` checks it against the
    original text and anything that fails is discarded before the user sees it.
    """

    doc_id: str = Field(description="The id of the document this text was copied from.")
    quote: str = Field(description="Exact verbatim text from the document. Do not paraphrase, translate or reformat.")
    clause_ref: str | None = Field(default=None, description="Clause or article number if the document states one.")


class Party(BaseModel):
    name: str
    role: PartyRole
    registration_number: str | None = Field(default=None, description="KvK or company number if stated.")
    address: str | None = None
    source: SourceQuote


class MoneyTerm(BaseModel):
    kind: MoneyKind
    label: str = Field(description="Short description, for example: housing deduction, gross hourly wage.")
    amount: float | None = Field(default=None, description="Numeric amount. Null if the document gives no number.")
    currency: str = Field(default="EUR")
    period: Period = Field(default="unknown")
    source: SourceQuote


class TerminationCondition(BaseModel):
    trigger: str = Field(description="What causes this to end, for example: the assignment ends.")
    effect: str = Field(description="What ends as a result, for example: the employment contract ends the same day.")
    notice_days_worker: int | None = None
    notice_days_employer: int | None = None
    source: SourceQuote


class ExtractedFlag(BaseModel):
    """One factual observation about the text. Legal meaning is decided elsewhere."""

    flag: FlagName
    present: bool
    source: SourceQuote | None = Field(default=None, description="Required when present is true. A flag with present=true and no quote is discarded.")
    note: str | None = Field(default=None, description="One sentence of context, in English, for the caseworker.")


class StructuredDocument(BaseModel):
    """Step 2 output: one uploaded document turned into typed fields.

    `extraction_confidence` is in `required` for the same reason as
    `CrossReferenceResult.reasoning_confidence`: a field the model may silently omit
    becomes its Pydantic default, and a default of `0.0` for a confidence score is
    indistinguishable from the model telling us it could not read the document.
    """

    model_config = ConfigDict(json_schema_extra=_also_required("extraction_confidence"))

    doc_id: str
    doc_type: DocType
    detected_language: str = Field(description="ISO 639-1 code of the document language, for example: nl")
    parties: list[Party] = Field(default_factory=list)
    money_terms: list[MoneyTerm] = Field(default_factory=list)
    termination_conditions: list[TerminationCondition] = Field(default_factory=list)
    flags: list[ExtractedFlag] = Field(default_factory=list)
    contracted_hours_per_week: float | None = Field(default=None, description="Guaranteed hours per week if the document states a number.")
    extraction_confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Required. How completely this document could be read, from 0.0 to 1.0. Low "
            "for cropped, partial or illegible text. Null only if you cannot judge."
        ),
    )
    unreadable_sections: list[str] = Field(default_factory=list, description="Parts that appear to be missing or illegible.")


# --- Step 3: relationships between documents -------------------------------


class Dependency(BaseModel):
    """One contract's fate depending on another's. The core cross-document insight."""

    description: str = Field(description="Plain English: what ending triggers what other ending.")
    from_doc_id: str
    to_doc_id: str
    quotes: list[SourceQuote] = Field(default_factory=list)


class Asymmetry(BaseModel):
    """An obligation that binds one side and not the other."""

    description: str
    binds: Literal["worker", "employer", "both_unequally"]
    quotes: list[SourceQuote] = Field(default_factory=list)


class CrossReferenceResult(BaseModel):
    """What this step found. Absence of a field means the model did not say, never zero.

    `reasoning_confidence` is the model's own assessment of this step, and it used to
    be a plain `float` defaulting to `0.0`. Every field here carries a default, so
    Pydantic emitted no `required` list at all, and the model — given a bare
    `{"type": "number"}` with no description — simply left the field out. Pydantic
    then supplied `0.0`, which `pipeline.py` read as "the step failed" and
    `safety.compute_overall_confidence` read as "no confidence at all", gating a run
    that had in fact completed and found everything it was looking for.

    Two things stop that recurring: `None` means "not stated" and is distinguishable
    from a genuine `0.0`, and `model_config` below puts the field in the schema's
    `required` list so the model is obliged to answer in the first place.
    """

    model_config = ConfigDict(json_schema_extra=_also_required("reasoning_confidence"))

    same_or_related_entities: list[str] = Field(default_factory=list, description="Names that appear to be the same operation across documents, with the reason.")
    dependencies: list[Dependency] = Field(default_factory=list)
    asymmetries: list[Asymmetry] = Field(default_factory=list)
    reasoning_confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Required. How much you trust your own cross-document reasoning here, from 0.0 "
            "to 1.0. Lower it when documents are missing, when a link is inferred from "
            "wording rather than stated, or when you were given only one document. This is "
            "your assessment of this step, not of the documents."
        ),
    )
    conflicts: list[str] = Field(default_factory=list, description="Places where two documents state contradictory things.")


# --- Findings --------------------------------------------------------------


class Finding(BaseModel):
    id: str
    category: FindingCategory
    severity: Severity
    title: str = Field(description="Short headline in the user's language.")
    what_it_means: str = Field(description="One or two sentences on what this means in practice for the worker.")
    quotes: list[SourceQuote] = Field(default_factory=list)
    origin: Origin = Field(default="model", description="deterministic if produced by a Python rule check, model if by the LLM.")
    rule_id: str | None = Field(default=None, description="Id in rules/legal_rules.json, for deterministic findings.")
    rule_verified: bool = Field(default=False, description="False when the underlying legal figure has not been confirmed against the version in force. Surfaced to the user.")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


# --- Step 5: the four outputs ----------------------------------------------


class ExitEvent(BaseModel):
    day_offset: int | None = Field(default=None, description="Days after the trigger date. Zero means the same day. Null if the document gives no timing.")
    label: str
    description: str
    quotes: list[SourceQuote] = Field(default_factory=list)


class ExitScenario(BaseModel):
    """Not a legal summary. A dated timeline of what stops, and when."""

    trigger_description: str = Field(description="The event the timeline starts from, for example: if your assignment ends.")
    events: list[ExitEvent] = Field(default_factory=list)
    outstanding_amount: float | None = None
    currency: str = "EUR"
    caveat: str | None = Field(default=None, description="Set when timing could not be established from the documents.")


class SafeQuestion(BaseModel):
    question_in_user_language: str
    question_in_employer_language: str
    why_this_question: str = Field(description="What the answer would tell them.")
    what_a_refusal_means: str = Field(description="What it tells them if this is not answered in writing.")


class ContactOption(BaseModel):
    name: str
    kind: Literal["confidential_advice", "legal_aid", "enforcement"]
    what_they_do: str
    will_employer_find_out: str
    typical_response_time: str
    contact: str
    url: str | None = None


class ComposedOutput(BaseModel):
    """What the LLM writes in step 5, in the user's language."""

    findings: list[Finding] = Field(default_factory=list)
    exit_scenario: ExitScenario
    safe_questions: list[SafeQuestion] = Field(default_factory=list)


# --- The report ------------------------------------------------------------


class DocumentSummary(BaseModel):
    doc_id: str
    filename: str
    doc_type: DocType
    detected_language: str
    char_count: int


class Report(BaseModel):
    """What the user finally sees. Assembled in `pipeline.py`."""

    generated_at: datetime
    user_language: str
    documents_received: list[DocumentSummary] = Field(default_factory=list)
    missing_documents: list[str] = Field(default_factory=list, description="Document types we would expect in a bundle but did not receive.")

    findings: list[Finding] = Field(default_factory=list)
    exit_scenario: ExitScenario | None = None
    safe_questions: list[SafeQuestion] = Field(default_factory=list)
    contacts: list[ContactOption] = Field(default_factory=list)

    overall_confidence: float = 0.0
    gated: bool = Field(default=False, description="True when the tool refused to summarise and routed to a human instead.")
    gate_reason: str | None = None
    conflicts: list[str] = Field(default_factory=list)

    dropped_finding_count: int = Field(default=0, description="Findings discarded because their quote could not be found in the source text.")
    unverified_rule_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @property
    def no_findings(self) -> bool:
        return not self.findings
