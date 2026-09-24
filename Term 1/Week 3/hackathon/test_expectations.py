"""Tests that samples/expectations.json stays in step with the rest of the repository.

The expectations file is ground truth for scripts/evaluate.py, which means it can rot
in two directions: a rule gets renamed and an expectation silently stops being
checked, or a bundle is added and nobody writes down what it should produce. Both
failures look like a passing evaluation run, which is the worst way for a measurement
to break.

These tests need no API key and no model. They check the file, not the pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from contract_trap_finder.rules import load_rules

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
EXPECTATIONS = SAMPLES / "expectations.json"


def expectations() -> dict:
    return json.loads(EXPECTATIONS.read_text(encoding="utf-8"))


def known_rule_ids() -> set[str]:
    return {rule["id"] for rule in load_rules()["rules"]}


def sample_directories() -> set[str]:
    return {p.name for p in SAMPLES.iterdir() if p.is_dir()}


def rule_lists(spec: dict) -> list[tuple[str, list[str]]]:
    return [
        ("expect_rules", spec.get("expect_rules", [])),
        ("forbid_rules", spec.get("forbid_rules", [])),
        ("watch_rules", spec.get("watch_rules", [])),
    ]


def test_every_sample_bundle_has_expectations() -> None:
    """A bundle with no expectations is a bundle the harness cannot score."""
    described = set(expectations()["bundles"])
    missing = sample_directories() - described
    assert not missing, (
        f"These sample bundles have no entry in expectations.json: {sorted(missing)}. "
        f"Add one, or scripts/evaluate.py will skip them without saying so."
    )


def test_expectations_do_not_name_bundles_that_are_gone() -> None:
    described = set(expectations()["bundles"])
    orphaned = described - sample_directories()
    assert not orphaned, f"expectations.json describes bundles that do not exist: {sorted(orphaned)}"


@pytest.mark.parametrize("bundle", sorted(expectations()["bundles"]))
def test_every_referenced_rule_id_exists(bundle: str) -> None:
    """Catches a rule rename turning an expectation into a no-op."""
    spec = expectations()["bundles"][bundle]
    known = known_rule_ids()
    for list_name, ids in rule_lists(spec):
        unknown = [rule_id for rule_id in ids if rule_id not in known]
        assert not unknown, f"{bundle}.{list_name} names rules that are not in legal_rules.json: {unknown}"


@pytest.mark.parametrize("bundle", sorted(expectations()["bundles"]))
def test_a_rule_is_not_both_expected_and_forbidden(bundle: str) -> None:
    spec = expectations()["bundles"][bundle]
    expect = set(spec.get("expect_rules", []))
    forbid = set(spec.get("forbid_rules", []))
    watch = set(spec.get("watch_rules", []))
    assert not expect & forbid, f"{bundle} both expects and forbids {sorted(expect & forbid)}"
    assert not expect & watch, f"{bundle} both expects and watches {sorted(expect & watch)}"
    assert not forbid & watch, f"{bundle} both forbids and watches {sorted(forbid & watch)}"


@pytest.mark.parametrize("bundle", sorted(expectations()["bundles"]))
def test_expected_rules_say_which_clause_plants_them(bundle: str) -> None:
    """An expectation without a clause behind it is a guess.

    clause_map is what makes a missed rule diagnosable: it says what was written into
    the bundle to make that rule fire, so a failure points at a clause rather than at
    a rule id.
    """
    spec = expectations()["bundles"][bundle]
    clause_map = spec.get("clause_map", {})
    undocumented = [rule_id for rule_id in spec.get("expect_rules", []) if rule_id not in clause_map]
    assert not undocumented, (
        f"{bundle} expects {undocumented} but clause_map does not say which clause plants them"
    )


@pytest.mark.parametrize("bundle", sorted(expectations()["bundles"]))
def test_watched_rules_say_why_they_are_only_watched(bundle: str) -> None:
    """watch_rules is the honest category, and it should stay honest.

    A rule lands here when whether it fires depends on arithmetic against a figure
    that moves or on a judgement the team has not settled. Both are reasons that can
    be written down; "we are not sure" without a reason belongs in expect or forbid.
    """
    spec = expectations()["bundles"][bundle]
    notes = spec.get("watch_notes", {})
    watched = spec.get("watch_rules", [])
    if not watched:
        return
    assert notes, f"{bundle} watches {watched} but records no watch_notes explaining why"


CONTROL_BUNDLES = ("bundle_b_nl_clean", "bundle_f_en_clean")


@pytest.mark.parametrize("bundle", CONTROL_BUNDLES)
def test_the_control_bundles_forbid_the_equal_pay_rule(bundle: str) -> None:
    """A named guard for the false positive that matters most.

    Both control bundles are direct employment contracts, not placements, so the
    equal-treatment question does not arise. If this rule ever fires there, the tool is
    telling someone they may be underpaid relative to colleagues on the basis of a
    status they do not have, and samples/README.md calls this out specifically. It is
    checked in both languages because the control only controls for what it covers:
    the Dutch bundle says nothing about how the English contract is read.
    """
    spec = expectations()["bundles"][bundle]
    assert "ET-WAADI-08-EQUAL-PAY" in spec["forbid_rules"]


def test_every_bundle_name_carries_its_document_language() -> None:
    """The name is the only place a reader sees which language a bundle is in.

    A directory called bundle_g_something tells whoever adds it nothing about what it
    has to contain, and the whole reason the English bundles exist is that a score over
    the Dutch ones does not carry across. Ten directories in, this convention is the
    thing that keeps that visible.
    """
    known_languages = {"nl", "en"}
    for name in sample_directories():
        parts = name.split("_")
        assert len(parts) >= 4 and parts[0] == "bundle", (
            f"{name} does not follow bundle_<letter>_<language>_<what it is>"
        )
        assert parts[2] in known_languages, (
            f"{name} names language {parts[2]!r}, which is not one of {sorted(known_languages)}. "
            f"Add it here deliberately: a new document language is a new thing to measure, "
            f"not a spelling change."
        )
