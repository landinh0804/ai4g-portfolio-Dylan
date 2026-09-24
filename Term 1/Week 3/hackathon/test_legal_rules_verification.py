"""Tests that the verified flag in legal_rules.json cannot lie.

`verified` is not bookkeeping. The pipeline reads it and attaches a visible caveat to
every finding derived from an entry that has not been checked, so flipping it to true
does not mark a job as done - it switches a warning off for the person reading the
report. Commit 77947c1 flipped it for four entries without reading a source, and
nothing failed, because the only thing asserting that the flag was earned was a
sentence in a notes file.

These tests are that assertion, in code. An entry may claim to be verified only if it
also records when it was checked, what was read, and - where it rests on a published
source - a source_url that points at something more specific than a domain.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

import pytest

from contract_trap_finder.rules import load_rules

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Long enough that "checked" or "ok" does not pass for a record of what was read.
MIN_EVIDENCE_CHARS = 80


def entries() -> list[tuple[str, dict]]:
    """Every rule and every reference value, as (name, entry) pairs."""
    rules = load_rules()
    named = [(rule["id"], rule) for rule in rules["rules"]]
    named += [(name, entry) for name, entry in rules["reference_values"].items()]
    return named


def verified_entries() -> list[tuple[str, dict]]:
    return [(name, entry) for name, entry in entries() if entry.get("verified")]


@pytest.mark.parametrize("name, entry", verified_entries(), ids=lambda v: v if isinstance(v, str) else "")
def test_verified_entry_records_when_it_was_checked(name: str, entry: dict) -> None:
    verified_on = entry.get("verified_on")
    assert verified_on, f"{name} claims verified:true but records no verified_on"
    assert ISO_DATE.match(verified_on), f"{name} has verified_on={verified_on!r}, expected YYYY-MM-DD"


@pytest.mark.parametrize("name, entry", verified_entries(), ids=lambda v: v if isinstance(v, str) else "")
def test_verified_entry_records_what_was_read(name: str, entry: dict) -> None:
    evidence = (entry.get("verified_by") or "").strip()
    assert evidence, f"{name} claims verified:true but records no verified_by"
    assert len(evidence) >= MIN_EVIDENCE_CHARS, (
        f"{name} has a verified_by of {len(evidence)} characters. It should say which article or "
        f"document was read, in which version, and that it matches the claim made here."
    )


@pytest.mark.parametrize("name, entry", verified_entries(), ids=lambda v: v if isinstance(v, str) else "")
def test_verified_entry_source_url_is_not_a_bare_domain(name: str, entry: dict) -> None:
    """A link to belastingdienst.nl is not a citation; a link to an article is.

    source_url is allowed to be absent: three of the risk-shift rules assert no legal
    basis at all and say so in verified_by. What is not allowed is a URL that points at
    an organisation's front door while the entry claims its content was verified.
    """
    url = entry.get("source_url")
    if url is None:
        return
    path = urlparse(url).path.strip("/")
    assert path, f"{name} cites {url}, which is a bare domain rather than a specific document"


@pytest.mark.parametrize("name, entry", entries(), ids=lambda v: v if isinstance(v, str) else "")
def test_unverified_entry_does_not_claim_a_check(name: str, entry: dict) -> None:
    """The inverse: an entry marked unverified must not carry the evidence of a check.

    Either it was checked and is verified, or it was not and carries neither field.
    A leftover verified_by on an unverified entry means one of the two is wrong.
    """
    if entry.get("verified"):
        return
    assert not entry.get("verified_on"), f"{name} is unverified but records verified_on"
    assert not entry.get("verified_by"), f"{name} is unverified but records verified_by"


def test_full_time_hours_stays_an_assumption() -> None:
    """A named guard for the entry that has been flipped once already.

    Dutch law sets no statutory full-time week, so this figure cannot be verified
    against a source in the way the other reference values can. It exists to convert a
    monthly deduction into a comparable figure when the contract states no hours, and
    --check-setup is meant to keep listing it. If a future change makes it verifiable,
    delete this test deliberately rather than flipping the flag.
    """
    entry = load_rules()["reference_values"]["assumed_hours_per_week_when_none_stated"]
    assert entry["verified"] is False, (
        "assumed_hours_per_week_when_none_stated is an assumption, not a legal figure. It was flipped to "
        "true once in commit 77947c1; if it is being flipped again, read its note first."
    )


def test_every_rule_that_asserts_a_legal_basis_cites_a_source() -> None:
    """Rules that name a statute must link to one.

    The three risk-shift rules that report a combination rather than a legal position
    say so in legal_basis, and are exempt: they begin by stating that they are not
    unlawful, and they carry no source_url.
    """
    for rule in load_rules()["rules"]:
        basis = (rule.get("legal_basis") or "").strip()
        asserts_law = basis and not basis.lower().startswith("not unlawful")
        if asserts_law:
            assert rule.get("source_url"), (
                f"{rule['id']} states a legal basis but cites no source_url"
            )
