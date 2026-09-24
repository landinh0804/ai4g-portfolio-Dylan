"""Tests that the verified flag in contacts.json cannot lie either.

`rules/legal_rules.json` has had this guard since the verified flag was flipped on
three rules nobody had checked (see tests/test_legal_rules_verification.py).
`contacts.json` carries the same flag for the same reason and had no guard at all
until its six entries were checked on 2026-09-22 and set to true.

It matters in the same way. `s5_compose.get_contacts` appends "(check the website -
we have not verified this detail)" to any entry marked unverified, so setting the
flag switches that warning off for a person who is frightened to call at all. An
entry may claim to be verified only if it also records when it was checked, what was
read, and a route somebody could actually follow.
"""

from __future__ import annotations

import re

import pytest

from contract_trap_finder import config
from contract_trap_finder.rules import load_contacts

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LANGUAGE_CODE = re.compile(r"^[a-z]{2}$")

# Long enough that "checked" does not pass for a record of what was read.
MIN_EVIDENCE_CHARS = 80


def contacts() -> list[dict]:
    return load_contacts()["contacts"]


def verified_contacts() -> list[dict]:
    return [c for c in contacts() if c.get("verified")]


@pytest.mark.parametrize("entry", verified_contacts(), ids=lambda e: e["name"])
def test_verified_contact_records_when_it_was_checked(entry: dict) -> None:
    verified_on = entry.get("verified_on")
    assert verified_on, f"{entry['name']} claims verified:true but records no verified_on"
    assert ISO_DATE.match(verified_on), f"{entry['name']} has verified_on={verified_on!r}, expected YYYY-MM-DD"


@pytest.mark.parametrize("entry", verified_contacts(), ids=lambda e: e["name"])
def test_verified_contact_records_what_was_read(entry: dict) -> None:
    evidence = (entry.get("verified_by") or "").strip()
    assert evidence, f"{entry['name']} claims verified:true but records no verified_by"
    assert len(evidence) >= MIN_EVIDENCE_CHARS, (
        f"{entry['name']} has a verified_by of {len(evidence)} characters. It should say where the "
        f"number, the hours and the languages were read."
    )


@pytest.mark.parametrize("entry", verified_contacts(), ids=lambda e: e["name"])
def test_verified_contact_gives_a_route_somebody_can_follow(entry: dict) -> None:
    """"See their website" was what these entries said before they were checked.

    A verified entry has to carry something a person can act on without first finding
    the organisation themselves: a number, an address, or an email.
    """
    route = entry["contact"]
    has_number = any(ch.isdigit() for ch in route)
    has_address = "@" in route or "." in route
    assert has_number or has_address, f"{entry['name']} is verified but its contact line names no route"


@pytest.mark.parametrize("entry", contacts(), ids=lambda e: e["name"])
def test_unverified_contact_does_not_claim_a_check(entry: dict) -> None:
    if entry.get("verified"):
        return
    assert not entry.get("verified_on"), f"{entry['name']} is unverified but records verified_on"
    assert not entry.get("verified_by"), f"{entry['name']} is unverified but records verified_by"


@pytest.mark.parametrize("entry", contacts(), ids=lambda e: e["name"])
def test_language_codes_are_two_letter_codes(entry: dict) -> None:
    """Sorting in get_contacts matches on these, so a stray 'PL' silently demotes an entry."""
    for code in entry.get("languages", []):
        assert LANGUAGE_CODE.match(code), f"{entry['name']} lists language {code!r}, expected a two-letter code"


@pytest.mark.parametrize("language", sorted(config.SUPPORTED_LANGUAGES))
def test_every_reading_language_has_confidential_advice_in_it(language: str) -> None:
    """The routing promise: whoever the report is written for can talk to someone.

    Enforcement bodies do not count. A worker whose employer is also their landlord
    needs somewhere confidential to go first, and offering the report in a language
    that no confidential organisation on the list speaks would be an empty version of
    the same inequality this tool is about.
    """
    speakers = [c["name"] for c in contacts() if c["kind"] != "enforcement" and language in c.get("languages", [])]
    assert speakers, f"The report is offered in {language!r} but no confidential contact covers it"
