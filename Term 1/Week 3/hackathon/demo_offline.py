"""Run the whole pipeline with a stubbed model — no API key, no network, no cost.

    py scripts/demo_offline.py

What this is for: seeing the output format, checking the renderer after a change,
and demonstrating the safety behaviour. The stub deliberately includes one invented
finding, so every run shows the grounding check throwing something away.

What this is NOT: evidence that the tool works. The extraction here is hard-coded.
Use `py cli.py samples/bundle_a_nl_tied_housing/*.txt` with a real key for that.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from contract_trap_finder._bootstrap import require_dependencies  # noqa: E402

require_dependencies()

from contract_trap_finder.cli import _force_utf8_output, render_text  # noqa: E402
from contract_trap_finder.models import (  # noqa: E402
    ComposedOutput,
    CrossReferenceResult,
    Dependency,
    ExitEvent,
    ExitScenario,
    ExtractedFlag,
    Finding,
    MoneyTerm,
    SafeQuestion,
    SourceQuote,
    StructuredDocument,
)
from contract_trap_finder.pipeline import analyse  # noqa: E402
from contract_trap_finder.steps.s1_ingest import from_path  # noqa: E402

BUNDLE = ROOT / "samples" / "bundle_a_nl_tied_housing"


def q(doc_id: str, text: str, clause: str | None = None) -> SourceQuote:
    return SourceQuote(doc_id=doc_id, quote=text, clause_ref=clause)


class StubClient:
    """Returns fixed answers in place of Gemini, dispatching on the schema asked for."""

    def __init__(self, ids: list[str]) -> None:
        self.contract, self.housing, self.mandate = ids
        # `pipeline.analyse` reads this off the client to decide whether to scale
        # confidence down for a weak fallback model. There is no model here at all,
        # so nothing was degraded.
        self.last_model_used = None

    @property
    def answered_degraded(self) -> bool:
        return False

    def generate_json(self, *, prompt, schema_model, **_kwargs):
        name = schema_model.__name__
        if name == "StructuredDocument":
            for doc_id, builder in (
                (self.contract, self._contract),
                (self.housing, self._housing),
                (self.mandate, self._mandate),
            ):
                if doc_id in prompt:
                    return builder()
            raise AssertionError("unexpected document in prompt")
        if name == "CrossReferenceResult":
            return self._cross()
        if name == "ComposedOutput":
            return self._composed()
        raise AssertionError(name)

    # --- stubbed step 2 ---------------------------------------------------

    def _contract(self) -> StructuredDocument:
        d = self.contract
        return StructuredDocument(
            doc_id=d,
            doc_type="employment_contract",
            detected_language="nl",
            extraction_confidence=0.93,
            contracted_hours_per_week=None,
            parties=[
                {
                    "name": "Westhoek Flexwerk B.V.",
                    "role": "employer_or_agency",
                    "registration_number": "61234567",
                    "address": "Industrieweg 44, Zoetermeer",
                    "source": q(d, "Westhoek Flexwerk B.V., gevestigd te Zoetermeer, Industrieweg 44, KvK 61234567"),
                }
            ],
            money_terms=[
                MoneyTerm(kind="wage", label="bruto uurloon", amount=13.50, period="hour",
                          source=q(d, "Het bruto uurloon bedraagt EUR 13,50 per gewerkt uur.", "4.1")),
                MoneyTerm(kind="recruitment_or_placement_fee", label="bemiddelingsvergoeding", amount=350.0,
                          period="one_off",
                          source=q(d, "een eenmalige\nbemiddelingsvergoeding verschuldigd van EUR 350,00", "5.1")),
                MoneyTerm(kind="transport_cost", label="vervoer", amount=80.0, period="month",
                          source=q(d, "tegen een vergoeding van EUR 80,00 per maand", "7.2")),
                MoneyTerm(kind="insurance_premium", label="zorgverzekering", amount=145.0, period="month",
                          source=q(d, "De premie van EUR 145,00 per maand wordt ingehouden op het loon.", "7.3")),
                MoneyTerm(kind="advance_or_loan", label="reisvoorschot", amount=400.0, period="one_off",
                          source=q(d, "een voorschot van EUR 400,00 ter dekking van de\nreis naar Nederland", "6.1")),
            ],
            termination_conditions=[
                {
                    "trigger": "de terbeschikkingstelling eindigt",
                    "effect": "de arbeidsovereenkomst eindigt dezelfde dag",
                    "notice_days_worker": 30,
                    "notice_days_employer": 2,
                    "source": q(d, "De arbeidsovereenkomst eindigt van rechtswege op het moment dat de\nterbeschikkingstelling op verzoek van de opdrachtgever eindigt, op dezelfde dag", "3.2"),
                }
            ],
            flags=[
                ExtractedFlag(flag="contract_ends_with_assignment", present=True,
                              source=q(d, "eindigt van rechtswege op het moment dat de\nterbeschikkingstelling", "3.2")),
                ExtractedFlag(flag="no_guaranteed_hours", present=True,
                              source=q(d, "Er wordt geen minimum aantal arbeidsuren per week gegarandeerd.", "2.1")),
                ExtractedFlag(flag="other_work_prohibited", present=True,
                              source=q(d, "Het is de uitzendkracht niet toegestaan gedurende het dienstverband\nwerkzaamheden te verrichten voor derden", "8.1")),
                ExtractedFlag(flag="worker_charged_recruitment_fee", present=True,
                              source=q(d, "Voor de werving, selectie en plaatsing is de uitzendkracht een eenmalige\nbemiddelingsvergoeding verschuldigd", "5.1")),
                ExtractedFlag(flag="direct_employment_restricted", present=True,
                              source=q(d, "is de uitzendkracht een vergoeding verschuldigd van EUR 2.500,00 wegens\ngederfde inkomsten", "9.1")),
                ExtractedFlag(flag="identity_document_retained", present=True,
                              source=q(d, "Het document wordt bewaard in de administratie gedurende de\nlooptijd van de overeenkomst", "11.1")),
                ExtractedFlag(flag="travel_advance_repaid_by_deduction", present=True,
                              source=q(d, "Het voorschot wordt terugbetaald door inhouding van EUR 100,00 per maand", "6.2")),
                ExtractedFlag(flag="penalty_for_early_departure", present=True,
                              source=q(d, "Bij beeindiging van de overeenkomst binnen zes maanden is het resterende bedrag\nineens opeisbaar.", "6.3")),
                ExtractedFlag(flag="penalty_for_lost_equipment", present=True,
                              source=q(d, "is de uitzendkracht een bedrag van EUR 150,00 per item verschuldigd", "10.1")),
                ExtractedFlag(flag="asymmetric_notice_period", present=True,
                              source=q(d, "De uitzendkracht dient een opzegtermijn van een (1) maand in acht te nemen", "3.3")),
                ExtractedFlag(flag="wage_partly_paid_as_expense_reimbursement", present=True,
                              source=q(d, "Een deel van de beloning wordt uitgekeerd als onbelaste kostenvergoeding", "4.3")),
                ExtractedFlag(flag="transport_tied_to_employment", present=True,
                              source=q(d, "Bij het einde van de\nterbeschikkingstelling vervalt het recht op vervoer.", "7.2")),
                ExtractedFlag(flag="insurance_tied_to_employment", present=True,
                              source=q(d, "De deelname eindigt aan het einde van de maand waarin de arbeidsovereenkomst eindigt.", "7.3")),
            ],
        )

    def _housing(self) -> StructuredDocument:
        d = self.housing
        return StructuredDocument(
            doc_id=d,
            doc_type="housing_agreement",
            detected_language="nl",
            extraction_confidence=0.95,
            parties=[
                {
                    "name": "Westhoek Huisvesting B.V.",
                    "role": "landlord_or_housing_provider",
                    "registration_number": "61234599",
                    "address": "Industrieweg 44, Zoetermeer",
                    "source": q(d, "Westhoek Huisvesting B.V., Industrieweg 44, Zoetermeer, KvK 61234599"),
                }
            ],
            money_terms=[
                MoneyTerm(kind="housing_cost", label="huisvestingsvergoeding", amount=112.50, period="week",
                          source=q(d, "De vergoeding bedraagt EUR 112,50 per week per persoon", "2.1")),
                MoneyTerm(kind="deduction", label="borgsom", amount=300.0, period="one_off",
                          source=q(d, "een borgsom van EUR 300,00 verschuldigd, in te houden in drie\ntermijnen op het loon", "5.1")),
            ],
            termination_conditions=[
                {
                    "trigger": "de arbeidsovereenkomst eindigt",
                    "effect": "het gebruiksrecht eindigt en de accommodatie moet binnen 3 dagen worden verlaten",
                    "notice_days_worker": None,
                    "notice_days_employer": None,
                    "source": q(d, "De gebruiker dient de accommodatie te verlaten binnen drie (3) kalenderdagen na\nhet einde van de arbeidsovereenkomst.", "3.2"),
                }
            ],
            flags=[
                ExtractedFlag(flag="housing_tied_to_employment", present=True,
                              source=q(d, "De accommodatie wordt ter beschikking gesteld in verband met de\nterbeschikkingstelling", "1.1")),
            ],
        )

    def _mandate(self) -> StructuredDocument:
        d = self.mandate
        return StructuredDocument(
            doc_id=d,
            doc_type="deduction_authorisation",
            detected_language="nl",
            extraction_confidence=0.96,
            flags=[
                ExtractedFlag(flag="deduction_authorisation_open_ended", present=True,
                              source=q(d, "De machtiging geldt voor de gehele duur van het dienstverband en is onherroepelijk\nzolang enig bedrag openstaat. Er is geen maximum overeengekomen.")),
            ],
        )

    # --- stubbed steps 3 and 5 -------------------------------------------

    def _cross(self) -> CrossReferenceResult:
        return CrossReferenceResult(
            same_or_related_entities=[
                "Westhoek Flexwerk B.V. (employer) and Westhoek Huisvesting B.V. (landlord) share the "
                "registered address Industrieweg 44, Zoetermeer, and consecutive KvK numbers."
            ],
            dependencies=[
                Dependency(
                    description="The employment ends the day the assignment ends, and the accommodation must be vacated three days later.",
                    from_doc_id=self.contract,
                    to_doc_id=self.housing,
                    quotes=[
                        q(self.contract, "eindigt van rechtswege op het moment dat de\nterbeschikkingstelling", "3.2"),
                        q(self.housing, "binnen drie (3) kalenderdagen na\nhet einde van de arbeidsovereenkomst", "3.2"),
                    ],
                )
            ],
            asymmetries=[
                {
                    "description": "The worker must give one month's notice; the agency needs two working days.",
                    "binds": "both_unequally",
                    "quotes": [q(self.contract, "De uitzendkracht dient een opzegtermijn van een (1) maand in acht te nemen", "3.3")],
                }
            ],
            reasoning_confidence=0.88,
            conflicts=[],
        )

    def _composed(self) -> ComposedOutput:
        return ComposedOutput(
            findings=[
                Finding(
                    id="MOD-1",
                    category="RISK_SHIFT",
                    severity="high",
                    title="Your employer and your landlord are the same operation",
                    what_it_means=(
                        "The company that employs you and the company that houses you share an address and "
                        "have consecutive registration numbers. A disagreement at work is therefore also a "
                        "disagreement with the person who controls where you sleep."
                    ),
                    quotes=[
                        q(self.contract, "Westhoek Flexwerk B.V., gevestigd te Zoetermeer, Industrieweg 44, KvK 61234567"),
                        q(self.housing, "Westhoek Huisvesting B.V., Industrieweg 44, Zoetermeer, KvK 61234599"),
                    ],
                    origin="model",
                ),
                # Deliberately ungrounded: this clause is not in any document. Every run
                # should show it being discarded by the grounding check.
                Finding(
                    id="MOD-2",
                    category="ILLEGAL",
                    severity="high",
                    title="(invented finding, should never be displayed)",
                    what_it_means="Based on a clause that does not exist in the documents.",
                    quotes=[q(self.contract, "De werkgever verstrekt een bonus van EUR 5.000 per jaar aan de werknemer.")],
                    origin="model",
                ),
            ],
            exit_scenario=ExitScenario(
                trigger_description="If the company you are placed at ends your assignment on a Friday:",
                events=[
                    ExitEvent(day_offset=0, label="your job ends",
                              description="Your employment ends the same day, with no notice required from the agency.",
                              quotes=[q(self.contract, "op dezelfde dag\nzonder dat opzegging is vereist", "3.2")]),
                    ExitEvent(day_offset=0, label="your transport stops",
                              description="The right to organised transport to work ends with the assignment.",
                              quotes=[q(self.contract, "Bij het einde van de\nterbeschikkingstelling vervalt het recht op vervoer.", "7.2")]),
                    ExitEvent(day_offset=3, label="you must leave your accommodation",
                              description="You have three calendar days to move out, after which EUR 75 per day is charged.",
                              quotes=[q(self.housing, "binnen drie (3) kalenderdagen na\nhet einde van de arbeidsovereenkomst", "3.2")]),
                    ExitEvent(day_offset=30, label="your health insurance stops",
                              description="Cover ends at the end of the month in which the contract ends.",
                              quotes=[q(self.contract, "De deelname eindigt aan het einde van de maand waarin de arbeidsovereenkomst eindigt.", "7.3")]),
                ],
                outstanding_amount=750.0,
                currency="EUR",
                caveat="The remaining travel advance depends on how many months you have worked, which these documents do not fix.",
            ),
            safe_questions=[
                SafeQuestion(
                    question_in_user_language="If I move to a different job later, can I stay in the accommodation?",
                    question_in_employer_language="Als ik later ander werk vind, kan ik dan in de woning blijven wonen?",
                    why_this_question="The answer tells you whether your home depends on this one job, without asking about it directly.",
                    what_a_refusal_means="If nobody will answer this in writing, treat the accommodation as tied to the job.",
                ),
                SafeQuestion(
                    question_in_user_language="How many hours per week can I count on?",
                    question_in_employer_language="Op hoeveel uur per week kan ik rekenen?",
                    why_this_question="Your contract guarantees none. A written answer is something you can hold them to.",
                    what_a_refusal_means="A refusal to name a number in writing usually means there is no number.",
                ),
                SafeQuestion(
                    question_in_user_language="Which company will I actually be working at?",
                    question_in_employer_language="Bij welk bedrijf ga ik precies werken?",
                    why_this_question="You need this to find out what that company's own staff are paid for the same work.",
                    what_a_refusal_means="This is ordinary information. Refusing to give it is itself worth noting.",
                ),
            ],
        )


def main() -> int:
    _force_utf8_output()

    paths = sorted(BUNDLE.glob("*.txt"))
    if len(paths) != 3:
        print(f"Expected 3 sample files in {BUNDLE}, found {len(paths)}.")
        return 1

    documents = [from_path(path, index) for index, path in enumerate(paths)]
    client = StubClient([d.doc_id for d in documents])

    report = analyse(documents, language="en", client=client, progress=lambda m: print(f"  ... {m}"))
    print()
    print(render_text(report))

    print("\n" + "=" * 72)
    print("STUB RUN - the extraction above was hard-coded, not produced by a model.")
    print(f"Findings shown: {len(report.findings)} | discarded as ungrounded: {report.dropped_finding_count}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
