"""Tests for step 4 — the deterministic legal checks.

These run without an API key, which is the point: the part of the tool that decides
what is unlawful is ordinary Python and can be tested like ordinary Python.
"""

from __future__ import annotations

import pytest

from contract_trap_finder.models import (
    ExtractedFlag,
    MoneyTerm,
    SourceQuote,
    StructuredDocument,
)
from contract_trap_finder.rules import reference_value
from contract_trap_finder.steps import s4_legal_checks as checks


def quote(text: str = "some clause text", doc_id: str = "doc1") -> SourceQuote:
    return SourceQuote(doc_id=doc_id, quote=text)


def doc(
    flags: list[str] | None = None,
    money: list[MoneyTerm] | None = None,
    hours: float | None = None,
    doc_type: str = "employment_contract",
    doc_id: str = "doc1",
) -> StructuredDocument:
    return StructuredDocument(
        doc_id=doc_id,
        doc_type=doc_type,
        detected_language="nl",
        extraction_confidence=0.9,
        contracted_hours_per_week=hours,
        money_terms=money or [],
        flags=[ExtractedFlag(flag=f, present=True, source=quote(f"clause about {f}")) for f in (flags or [])],
    )


def fired_rule_ids(docs) -> set[str]:
    findings, _notes = checks.run_checks(docs)
    return {f.rule_id for f in findings}


# --- single-flag rules -----------------------------------------------------


def test_recruitment_fee_is_reported_as_illegal():
    findings, _notes = checks.run_checks([doc(flags=["worker_charged_recruitment_fee"])])
    fee = next(f for f in findings if f.rule_id == "NL-WAADI-09-FEE")
    assert fee.category == "ILLEGAL"
    assert fee.origin == "deterministic"
    assert fee.quotes


def test_direct_employment_restriction_is_reported():
    assert "NL-WAADI-09A-OBSTRUCTION" in fired_rule_ids([doc(flags=["direct_employment_restricted"])])


def test_nothing_fires_on_an_empty_bundle_of_flags():
    assert fired_rule_ids([doc()]) == set()


def test_no_documents_produces_a_note_not_a_crash():
    findings, notes = checks.run_checks([])
    assert findings == []
    assert notes


# --- combination rules -----------------------------------------------------


def test_tied_housing_needs_both_halves_of_the_combination():
    """The whole argument of the project: neither clause is remarkable alone."""
    assert "RS-TIED-HOUSING" not in fired_rule_ids([doc(flags=["housing_tied_to_employment"])])
    assert "RS-TIED-HOUSING" not in fired_rule_ids([doc(flags=["contract_ends_with_assignment"])])
    assert "RS-TIED-HOUSING" in fired_rule_ids(
        [doc(flags=["housing_tied_to_employment", "contract_ends_with_assignment"])]
    )


def test_tied_housing_fires_across_two_separate_documents():
    """The two clauses normally live in different files. That must still trigger."""
    employment = doc(flags=["contract_ends_with_assignment"], doc_id="doc1")
    housing = doc(flags=["housing_tied_to_employment"], doc_type="housing_agreement", doc_id="doc2")
    assert "RS-TIED-HOUSING" in fired_rule_ids([employment, housing])


def test_everything_at_once_needs_two_of_three_dependencies():
    assert "RS-EVERYTHING-AT-ONCE" not in fired_rule_ids([doc(flags=["housing_tied_to_employment"])])
    assert "RS-EVERYTHING-AT-ONCE" in fired_rule_ids(
        [doc(flags=["housing_tied_to_employment", "transport_tied_to_employment"])]
    )


def test_no_hours_plus_no_other_work_fires():
    assert "RS-NO-HOURS-NO-OTHER-WORK" in fired_rule_ids(
        [doc(flags=["no_guaranteed_hours", "other_work_prohibited"])]
    )


# --- equal treatment -------------------------------------------------------


def test_equal_treatment_does_not_fire_for_a_direct_employment_contract():
    """A direct employer is not a placement. This rule must not fire on every job."""
    direct = StructuredDocument(
        doc_id="doc1",
        doc_type="employment_contract",
        detected_language="nl",
        extraction_confidence=0.9,
        parties=[{"name": "De Groene Kas B.V.", "role": "employer_or_agency", "source": quote()}],
    )
    assert "ET-WAADI-08-EQUAL-PAY" not in fired_rule_ids([direct])


def test_equal_treatment_fires_when_the_work_is_a_placement():
    assert "ET-WAADI-08-EQUAL-PAY" in fired_rule_ids([doc(flags=["contract_ends_with_assignment"])])


# --- computed checks -------------------------------------------------------


def test_computed_checks_refuse_to_run_without_a_minimum_wage(monkeypatch):
    """With no figure to work from, the checks must say so rather than assume one.

    A guessed minimum wage produces confident, wrong statements about somebody's pay.
    This used to assert against the shipped rules file back when it had no figure in
    it; the figure is filled in now, so the empty state is simulated instead. The
    behaviour under test is the same one, and it is the behaviour that matters.
    """
    monkeypatch.setattr(checks, "reference_value", lambda name: (None, False))

    money = [MoneyTerm(kind="wage", label="uurloon", amount=13.50, period="hour", source=quote())]
    _findings, notes = checks.run_checks([doc(money=money, hours=40)])
    assert any("could not run" in note for note in notes)


def test_computed_checks_run_against_the_shipped_minimum_wage():
    """The counterpart: with the rules file as shipped, the checks actually run.

    The figure was unfilled for long enough that "could not run" read as normal
    output. It is not normal, and this test fails if the figure is ever emptied or
    the reference value is renamed.
    """
    minimum_hourly, verified = reference_value("statutory_minimum_wage_hourly_eur")
    assert minimum_hourly is not None, "statutory_minimum_wage_hourly_eur has no value"
    assert verified, "statutory_minimum_wage_hourly_eur is not marked verified"

    money = [MoneyTerm(kind="wage", label="uurloon", amount=13.50, period="hour", source=quote())]
    _findings, notes = checks.run_checks([doc(money=money, hours=40)])
    assert not any("could not run" in note for note in notes)


def test_below_minimum_wage_fires_against_the_shipped_figure():
    """An hourly wage under the statutory minimum is caught with no monkeypatching."""
    minimum_hourly, _verified = reference_value("statutory_minimum_wage_hourly_eur")
    money = [
        MoneyTerm(
            kind="wage",
            label="uurloon",
            amount=minimum_hourly - 2.0,
            period="hour",
            source=quote(),
        )
    ]
    assert checks.check_effective_wage([doc(money=money, hours=40)]).fired


def test_deduction_ceiling_fires_when_the_figures_are_supplied(monkeypatch):
    values = {
        "statutory_minimum_wage_hourly_eur": (14.00, True),
        "housing_deduction_max_share_of_minimum_wage": (0.25, True),
        "assumed_hours_per_week_when_none_stated": (40, True),
    }
    monkeypatch.setattr(checks, "reference_value", lambda name: values.get(name, (None, False)))

    # 40h at EUR 14.00 is about EUR 2,427/month; the ceiling is about EUR 607.
    money = [MoneyTerm(kind="housing_cost", label="huisvesting", amount=700.0, period="month", source=quote())]
    result = checks.check_deduction_ceiling([doc(money=money, hours=40)])
    assert result.fired
    assert "700" in result.finding_text


def test_deduction_ceiling_stays_quiet_when_under_the_limit(monkeypatch):
    values = {
        "statutory_minimum_wage_hourly_eur": (14.00, True),
        "housing_deduction_max_share_of_minimum_wage": (0.25, True),
        "assumed_hours_per_week_when_none_stated": (40, True),
    }
    monkeypatch.setattr(checks, "reference_value", lambda name: values.get(name, (None, False)))

    money = [MoneyTerm(kind="housing_cost", label="huisvesting", amount=400.0, period="month", source=quote())]
    assert not checks.check_deduction_ceiling([doc(money=money, hours=40)]).fired


def test_assumed_hours_are_stated_in_the_finding(monkeypatch):
    """If the contract guarantees no hours, the assumption must be visible."""
    values = {
        "statutory_minimum_wage_hourly_eur": (14.00, True),
        "housing_deduction_max_share_of_minimum_wage": (0.25, True),
        "assumed_hours_per_week_when_none_stated": (40, False),
    }
    monkeypatch.setattr(checks, "reference_value", lambda name: values.get(name, (None, False)))

    money = [MoneyTerm(kind="housing_cost", label="huisvesting", amount=900.0, period="month", source=quote())]
    result = checks.check_deduction_ceiling([doc(money=money, hours=None)])
    assert result.fired
    stated = " ".join(result.assumptions)
    assert "assume" in stated and "40 hours a week" in stated
    # And the part of the answer that does not rest on the assumption is still given:
    # the ceiling per hour worked, which is what the statute actually fixes.
    assert "for every hour you work" in result.finding_text


def test_effective_wage_detects_pay_below_minimum_after_deductions(monkeypatch):
    values = {
        "statutory_minimum_wage_hourly_eur": (14.00, True),
        "assumed_hours_per_week_when_none_stated": (40, True),
    }
    monkeypatch.setattr(checks, "reference_value", lambda name: values.get(name, (None, False)))

    money = [
        MoneyTerm(kind="wage", label="uurloon", amount=14.50, period="hour", source=quote()),
        MoneyTerm(kind="housing_cost", label="huisvesting", amount=487.50, period="month", source=quote()),
        MoneyTerm(kind="insurance_premium", label="zorgverzekering", amount=145.0, period="month", source=quote()),
    ]
    result = checks.check_effective_wage([doc(money=money, hours=40)])
    assert result.fired
    assert "14.00" in result.finding_text


# --- period conversion -----------------------------------------------------


@pytest.mark.parametrize(
    "amount,period,expected",
    [
        (100.0, "month", 100.0),
        (100.0, "week", pytest.approx(433.33, abs=0.1)),
        (1200.0, "year", 100.0),
        (100.0, "four_weeks", pytest.approx(108.33, abs=0.1)),
    ],
)
def test_period_conversion(amount, period, expected):
    assert checks._to_monthly(amount, period, hours_per_week=40) == expected


@pytest.mark.parametrize("period", ["one_off", "unknown", "day"])
def test_unconvertible_periods_return_none_rather_than_a_guess(period):
    assert checks._to_monthly(100.0, period, hours_per_week=40) is None


def test_hourly_conversion_needs_hours():
    assert checks._to_monthly(10.0, "hour", hours_per_week=None) is None


# --- ordering --------------------------------------------------------------


def test_findings_sort_illegal_first():
    findings, _ = checks.run_checks(
        [
            doc(
                flags=[
                    "wage_partly_paid_as_expense_reimbursement",
                    "housing_tied_to_employment",
                    "contract_ends_with_assignment",
                    "worker_charged_recruitment_fee",
                ]
            )
        ]
    )
    categories = [f.category for f in checks.sort_findings(findings)]
    assert categories == sorted(categories, key=lambda c: checks.CATEGORY_ORDER[c])
    assert categories[0] == "ILLEGAL"


# --- The reported case, run as arithmetic ----------------------------------


def _reported_case(hours: float):
    """EUR 125 a week for a room, deducted whichever hours are worked.

    The figures are from the worker quoted by EenVandaag on 26 November 2025
    ("Ik betaal 125 euro per week voor mijn kamer, ongeacht hoeveel uur ik werk...
    Soms krijg ik maar 19 of 20 uur werk"), and they are in the README under
    *How big this is*. Kept as a test because it is the case the tool exists for,
    and because it is the one a reader can check by hand.
    """
    money = [MoneyTerm(kind="housing_cost", label="huur kamer", amount=125.0, period="week", source=quote())]
    return checks.check_deduction_ceiling([doc(money=money, hours=hours)])


def test_a_fixed_rent_crosses_the_ceiling_in_a_short_week(monkeypatch):
    """The mechanism the rule is for: the rent is fixed, the ceiling is not.

    At 19 hours the worker's minimum wage for the week is 19 x EUR 14.99, so at most
    about EUR 71 may be taken for accommodation. The rent is EUR 125 and does not
    move. If this ever stops firing, the tool has stopped catching the case its own
    problem statement is built on.
    """
    values = {
        "statutory_minimum_wage_hourly_eur": (14.99, True),
        "housing_deduction_max_share_of_minimum_wage": (0.25, True),
    }
    monkeypatch.setattr(checks, "reference_value", lambda name: values.get(name, (None, False)))

    result = _reported_case(hours=19)
    assert result.fired
    # The ceiling is stated as a rate, because that is what the statute fixes.
    assert "EUR 3.75 for every hour you work" in result.finding_text
    # And the hours came from the document, so nothing is assumed about them.
    assert not any("assume" in a for a in result.assumptions)


def test_the_same_rent_is_lawful_in_a_full_week(monkeypatch):
    """The other half of the mechanism, and the reason the finding says it out loud.

    At 40 hours the ceiling is about EUR 150 and the same EUR 125 sits under it. A
    check that fired here would be telling somebody a lawful deduction is unlawful,
    which is the error this project treats as equal in weight to missing one.
    """
    values = {
        "statutory_minimum_wage_hourly_eur": (14.99, True),
        "housing_deduction_max_share_of_minimum_wage": (0.25, True),
    }
    monkeypatch.setattr(checks, "reference_value", lambda name: values.get(name, (None, False)))

    assert not _reported_case(hours=40).fired
