"""Loading and validating the rule data.

The legal rules live in JSON rather than in Python so that the team member who
verifies a rule against the law does not have to touch the code, and so that a
change to a ceiling is a one-line diff that is easy to review.
"""

from __future__ import annotations

import functools
import json
from typing import Any

from .. import config

RULES_PATH = config.RULES_DIR / "legal_rules.json"
CONTACTS_PATH = config.RULES_DIR / "contacts.json"


class RuleDataError(RuntimeError):
    """The rule files are missing or malformed."""


@functools.lru_cache(maxsize=1)
def load_rules() -> dict[str, Any]:
    return _load(RULES_PATH, required_keys=("meta", "reference_values", "rules"))


@functools.lru_cache(maxsize=1)
def load_contacts() -> dict[str, Any]:
    return _load(CONTACTS_PATH, required_keys=("meta", "contacts"))


def _load(path, required_keys: tuple[str, ...]) -> dict[str, Any]:
    if not path.exists():
        raise RuleDataError(f"Rule file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuleDataError(f"{path.name} is not valid JSON: {exc}") from exc
    missing = [k for k in required_keys if k not in data]
    if missing:
        raise RuleDataError(f"{path.name} is missing required key(s): {', '.join(missing)}")
    return data


def rule_by_id(rule_id: str) -> dict[str, Any] | None:
    for rule in load_rules()["rules"]:
        if rule["id"] == rule_id:
            return rule
    return None


def reference_value(name: str) -> tuple[Any, bool]:
    """Return `(value, verified)` for a reference figure.

    Callers must handle `value is None`. A check that cannot run because a figure
    has not been filled in must say so, never assume a default — a guessed minimum
    wage would produce confident, wrong numbers about somebody's pay.
    """
    entry = load_rules()["reference_values"].get(name)
    if entry is None:
        return None, False
    return entry.get("value"), bool(entry.get("verified", False))


def unverified_rule_ids() -> list[str]:
    """Rules whose legal basis has not yet been confirmed by the team."""
    return [r["id"] for r in load_rules()["rules"] if not r.get("verified", False)]


def unverified_reference_values() -> list[str]:
    return [name for name, entry in load_rules()["reference_values"].items() if not entry.get("verified", False)]
