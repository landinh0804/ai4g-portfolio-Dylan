"""Step 4 — Legal checks. Plain Python. No model is called anywhere in this file.

These answers must be correct, not plausible, so they are not asked of a model. The
model's job was to extract *what the document says*; this module decides *what that
means legally*, by matching those extractions against `rules/legal_rules.json`.

Two kinds of check:

* **Declarative** — a rule fires when a combination of extracted flags or money
  terms is present. The combinations live in the JSON, so a change to the law is a
  data change, not a code change.
* **Computed** — arithmetic against published figures: deduction ceilings and
  effective hourly pay. These are the checks most likely to be wrong in a way that
  matters, so when a figure they depend on has not been filled in, they refuse to
  run and say so rather than assuming a default.

Every finding produced here carries `rule_verified`, taken from the JSON. Until a
team member has confirmed a rule against the version in force, the report shows it
with a visible caveat. See *Current status and limitations* in README.md.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from ..models import Finding, SourceQuote, StructuredDocument
from ..rules import load_rules, reference_value

logger = logging.getLogger(__name__)

WEEKS_PER_MONTH = 52 / 12
MONTHS_PER_YEAR = 12

# Money kinds that count as money leaving the worker's wage.
DEDUCTION_KINDS = {"deduction", "housing_cost", "insurance_premium", "transport_cost"}


class CheckResult:
    """A computed check's outcome: a finding, a reason it could not run, or neither."""

    def __init__(
        self,
        finding_text: str | None = None,
        quotes: list[SourceQuote] | None = None,
        note: str | None = None,
        assumptions: list[str] | None = None,
    ) -> None:
        self.finding_text = finding_text
        self.quotes = quotes or []
        self.note = note
        self.assumptions = assumptions or []

    @property
    def fired(self) -> bool:
        return self.finding_text is not None and bool(self.quotes)


# --- Small helpers over the structured documents ---------------------------


def _present_flags(docs: list[StructuredDocument]) -> dict[str, SourceQuote]:
    """Flags marked present anywhere in the bundle, with the quote that evidences them.

    Flags without a quote never reach here — `safety.ground_structured_document`
    removes them — so anything in this map is anchored in real document text.
    """
    found: dict[str, SourceQuote] = {}
    for doc in docs:
        for flag in doc.flags:
            if flag.present and flag.source is not None and flag.flag not in found:
                found[flag.flag] = flag.source
    return found


def _money_of_kind(docs: list[StructuredDocument], kind: str) -> list[tuple[StructuredDocument, Any]]:
    return [(doc, term) for doc in docs for term in doc.money_terms if term.kind == kind]


def _hours_per_week(docs: list[StructuredDocument]) -> tuple[float | None, bool]:
    """Guaranteed hours per week, and whether it came from a document or an assumption."""
    for doc in docs:
        if doc.contracted_hours_per_week:
            return doc.contracted_hours_per_week, True
    assumed, _verified = reference_value("assumed_hours_per_week_when_none_stated")
    return (float(assumed) if assumed else None), False


def _to_monthly(amount: float, period: str, hours_per_week: float | None) -> float | None:
    """Convert an amount to a monthly figure, or None if that cannot be done safely."""
    if period == "month":
        return amount
    if period == "week":
        return amount * WEEKS_PER_MONTH
    if period == "four_weeks":
        return amount * 13 / MONTHS_PER_YEAR
    if period == "year":
        return amount / MONTHS_PER_YEAR
    if period == "hour":
        return amount * hours_per_week * WEEKS_PER_MONTH if hours_per_week else None
    # "day", "one_off" and "unknown" are not safely convertible without more context.
    return None


# --- Declarative trigger evaluation ----------------------------------------


def _evaluate_trigger(trigger: dict[str, Any], docs: list[StructuredDocument]) -> list[SourceQuote] | None:
    """Return the evidence quotes if the trigger fires, otherwise None."""
    flags = _present_flags(docs)
    kind = trigger.get("type")

    if kind == "flag":
        quote = flags.get(trigger["flag"])
        return [quote] if quote else None

    if kind == "money_kind":
        matches = _money_of_kind(docs, trigger["kind"])
        return [term.source for _doc, term in matches] if matches else None

    if kind == "all_of":
        needed = trigger["flags"]
        if all(f in flags for f in needed):
            return [flags[f] for f in needed]
        return None

    if kind == "count_of":
        present = [flags[f] for f in trigger["flags"] if f in flags]
        return present if len(present) >= trigger.get("min_count", 2) else None

    if kind == "any_of":
        evidence: list[SourceQuote] = []
        for condition in trigger["conditions"]:
            result = _evaluate_trigger(condition, docs)
            if result:
                evidence.extend(result)
        return evidence or None

    if kind == "always_if_agency_work":
        # The equal-treatment norm applies to agency work, not to every job. An
        # employer party alone does not establish that — a direct contract has one
        # too. Require actual evidence of a placement: a third company the worker is
        # sent to, or employment that ends with the assignment.
        for doc in docs:
            for party in doc.parties:
                if party.role == "hiring_company":
                    return [party.source]
        quote = flags.get("contract_ends_with_assignment")
        return [quote] if quote else None

    if kind == "computed":
        return None  # handled separately by _run_computed_checks

    logger.warning("Unknown trigger type in rules file: %s", kind)
    return None


# --- Computed checks -------------------------------------------------------


def check_deduction_ceiling(docs: list[StructuredDocument]) -> CheckResult:
    """Is more being deducted for accommodation than the ceiling allows?"""
    minimum_hourly, mw_verified = reference_value("statutory_minimum_wage_hourly_eur")
    ceiling_share, share_verified = reference_value("housing_deduction_max_share_of_minimum_wage")

    if minimum_hourly is None:
        return CheckResult(
            note=(
                "The deduction ceiling check could not run: the statutory minimum wage has not been "
                "filled in yet in rules/legal_rules.json. No assumption was made in its place."
            )
        )
    if ceiling_share is None:
        return CheckResult(note="The deduction ceiling check could not run: no ceiling share is configured.")

    hours, hours_from_document = _hours_per_week(docs)
    if not hours:
        return CheckResult(
            note="The deduction ceiling check could not run: the documents state no guaranteed hours per week."
        )

    assumptions: list[str] = []
    if not hours_from_document:
        assumptions.append(
            f"These documents guarantee no hours, so the monthly figures assume {hours:g} hours a week. "
            "The ceiling per hour worked does not depend on that assumption."
        )
    if not (mw_verified and share_verified):
        assumptions.append("The minimum wage figure and the ceiling used here have not yet been verified by the team.")

    # The ceiling is a share of the minimum wage the worker actually earns, and since
    # 1 January 2024 that wage is reckoned per hour worked (WML art. 8(1)(a), BMLMV
    # art. 2a(1)(a)). So the honest form of this number is per hour; the monthly figure
    # is the same ceiling written out over a week of `hours`, which is only an
    # assumption when the documents guarantee none. See docs/decisions.md.
    ceiling_per_hour = float(minimum_hourly) * float(ceiling_share)
    monthly_minimum = float(minimum_hourly) * hours * WEEKS_PER_MONTH
    ceiling = monthly_minimum * float(ceiling_share)

    housing_total = 0.0
    quotes: list[SourceQuote] = []
    unconvertible = 0
    for _doc, term in _money_of_kind(docs, "housing_cost") + [
        (d, t) for d, t in _money_of_kind(docs, "deduction") if "hous" in t.label.lower() or "accommod" in t.label.lower() or "huisvest" in t.label.lower()
    ]:
        if term.amount is None:
            continue
        monthly = _to_monthly(term.amount, term.period, hours)
        if monthly is None:
            unconvertible += 1
            continue
        housing_total += monthly
        quotes.append(term.source)

    if unconvertible:
        assumptions.append(f"{unconvertible} housing charge(s) gave no usable period and were left out of this total.")

    if not quotes:
        return CheckResult(note="No accommodation charge with a usable amount was found, so the ceiling check did not apply.")
    if housing_total <= ceiling:
        return CheckResult(assumptions=assumptions)

    text = (
        f"These documents deduct about EUR {housing_total:,.0f} a month for accommodation. "
        f"The law allows at most {float(ceiling_share):.0%} of the minimum wage you earn to be taken for "
        f"accommodation, which is EUR {ceiling_per_hour:,.2f} for every hour you work - about "
        f"EUR {ceiling:,.0f} a month at {hours:g} hours a week. "
        "That ceiling falls in a week where you work fewer hours, while a fixed rent does not, so the "
        "gap is wider in a short week than the monthly figure suggests."
    )
    if assumptions:
        text += " " + " ".join(assumptions)
    return CheckResult(finding_text=text, quotes=quotes, assumptions=assumptions)


def check_effective_wage(docs: list[StructuredDocument]) -> CheckResult:
    """After the deductions in these documents, is the hourly pay below the minimum?"""
    minimum_hourly, mw_verified = reference_value("statutory_minimum_wage_hourly_eur")
    if minimum_hourly is None:
        return CheckResult(
            note=(
                "The effective wage check could not run: the statutory minimum wage has not been filled in "
                "yet in rules/legal_rules.json."
            )
        )

    hours, hours_from_document = _hours_per_week(docs)
    if not hours:
        return CheckResult(note="The effective wage check could not run: no hours per week are stated.")

    wage_terms = [(d, t) for d, t in _money_of_kind(docs, "wage") if t.amount is not None]
    if not wage_terms:
        return CheckResult(note="The effective wage check could not run: no wage amount was found in the documents.")

    doc, wage_term = wage_terms[0]
    monthly_gross = _to_monthly(wage_term.amount, wage_term.period, hours)
    if monthly_gross is None:
        return CheckResult(note="The effective wage check could not run: the wage is stated over a period we cannot convert.")

    assumptions: list[str] = []
    if not hours_from_document:
        assumptions.append(f"These documents guarantee no hours, so the calculation assumes {hours:g} hours a week.")
    if not mw_verified:
        assumptions.append("The minimum wage figure used here has not yet been verified by the team.")

    quotes: list[SourceQuote] = [wage_term.source]
    monthly_deductions = 0.0
    for _d, term in [(d, t) for kind in DEDUCTION_KINDS for d, t in _money_of_kind(docs, kind)]:
        if term.amount is None:
            continue
        monthly = _to_monthly(term.amount, term.period, hours)
        if monthly is None:
            continue
        monthly_deductions += monthly
        quotes.append(term.source)

    monthly_hours = hours * WEEKS_PER_MONTH
    effective_hourly = (monthly_gross - monthly_deductions) / monthly_hours

    if effective_hourly >= float(minimum_hourly):
        return CheckResult(assumptions=assumptions)

    text = (
        f"The wage in these documents works out at about EUR {monthly_gross / monthly_hours:,.2f} an hour before "
        f"deductions. After the deductions set out here, about EUR {effective_hourly:,.2f} an hour is left, "
        f"against a statutory minimum of EUR {float(minimum_hourly):,.2f}."
    )
    if assumptions:
        text += " " + " ".join(assumptions)
    return CheckResult(finding_text=text, quotes=quotes, assumptions=assumptions)


COMPUTED_CHECKS: dict[str, Callable[[list[StructuredDocument]], CheckResult]] = {
    "check_deduction_ceiling": check_deduction_ceiling,
    "check_effective_wage": check_effective_wage,
}


# --- Entry point -----------------------------------------------------------


def run_checks(docs: list[StructuredDocument]) -> tuple[list[Finding], list[str]]:
    """Run every rule against the bundle.

    Returns `(findings, notes)`. Notes record checks that could not run — a check
    that silently did not happen is indistinguishable to the user from a check that
    passed, and the difference matters a great deal here.
    """
    if not docs:
        return [], ["No documents could be read, so no legal checks were run."]

    findings: list[Finding] = []
    notes: list[str] = []
    rules = load_rules()["rules"]

    for rule in rules:
        trigger = rule.get("trigger", {})

        if trigger.get("type") == "computed":
            function = COMPUTED_CHECKS.get(trigger.get("function", ""))
            if function is None:
                notes.append(f"Rule {rule['id']} names a check that does not exist in the code.")
                continue
            result = function(docs)
            if result.note:
                notes.append(result.note)
            if not result.fired:
                continue
            findings.append(
                Finding(
                    id=f"DET-{rule['id']}",
                    category=rule["category"],
                    severity=rule["severity"],
                    title=rule["title"],
                    what_it_means=f"{rule['what_it_means']} {result.finding_text}",
                    quotes=result.quotes,
                    origin="deterministic",
                    rule_id=rule["id"],
                    rule_verified=bool(rule.get("verified", False)),
                    confidence=1.0,
                )
            )
            continue

        evidence = _evaluate_trigger(trigger, docs)
        if not evidence:
            continue

        findings.append(
            Finding(
                id=f"DET-{rule['id']}",
                category=rule["category"],
                severity=rule["severity"],
                title=rule["title"],
                what_it_means=rule["what_it_means"],
                quotes=evidence,
                origin="deterministic",
                rule_id=rule["id"],
                rule_verified=bool(rule.get("verified", False)),
                confidence=1.0,
            )
        )

    return findings, notes


CATEGORY_ORDER = {"ILLEGAL": 0, "RISK_SHIFT": 1, "BELOW_EQUAL_TREATMENT": 2}
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def sort_findings(findings: list[Finding]) -> list[Finding]:
    """Illegal first, then risk, then equal treatment; by severity within each."""
    return sorted(
        findings,
        key=lambda f: (CATEGORY_ORDER.get(f.category, 9), SEVERITY_ORDER.get(f.severity, 9), f.id),
    )
