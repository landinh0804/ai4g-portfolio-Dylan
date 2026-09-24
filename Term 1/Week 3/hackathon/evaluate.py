"""Measure a real run of the pipeline against samples/expectations.json.

    py scripts/evaluate.py --provider ollama
    py scripts/evaluate.py --provider gemini --bundle bundle_a_nl_tied_housing
    py scripts/evaluate.py --provider ollama --json results.json

This exists because the repository contained no number describing how well the
pipeline reads a bundle. "It works" was an impression formed by looking at output,
and an impression does not survive a prompt edit: a change that quietly stops step 2
extracting the deduction authorisation produces a run that completes normally and a
report that is merely thinner.

What it measures: for each bundle, whether the rule ids that the team deliberately
planted came out (expect_rules), whether any of the ones that must not fire did
(forbid_rules), whether the gate behaved as the bundle was written to require, and
whether the missing-document detection named what the contract charges for. It also
records the grounding drops, the confidence, the model and the wall-clock time,
because "private but takes six minutes" is a real trade-off for someone standing at
a recruitment desk and it should be a number rather than a feeling.

What it does not measure: accuracy on a real contract. The bundles were written by
the team, so a perfect score means the pipeline finds what was planted in documents
shaped the way it expects. Read samples/expectations.json before quoting a figure
from this script anywhere.

Cost: one bundle costs several model calls, and the free Gemini tier meters about
twenty requests per key per model per day, so a full run against gemini can exhaust
a key. --provider ollama costs nothing but time.

Exit code is 1 if any bundle fails a scored expectation, so this can be wired into
CI later without changing anything.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from contract_trap_finder._bootstrap import require_dependencies  # noqa: E402

require_dependencies()

from contract_trap_finder import config  # noqa: E402
from contract_trap_finder.cli import _force_utf8_output  # noqa: E402
from contract_trap_finder.llm import build_client  # noqa: E402
from contract_trap_finder.models import Report  # noqa: E402
from contract_trap_finder.pipeline import analyse_paths  # noqa: E402

SAMPLES = ROOT / "samples"
EXPECTATIONS = SAMPLES / "expectations.json"


def load_expectations() -> dict:
    return json.loads(EXPECTATIONS.read_text(encoding="utf-8"))


def bundle_paths(name: str) -> list[str]:
    directory = SAMPLES / name
    if not directory.is_dir():
        raise SystemExit(f"No such bundle: {directory}")
    return [str(p) for p in sorted(directory.glob("*.txt"))]


def fired_rule_ids(report: Report) -> set[str]:
    """Rule ids the run actually produced.

    Findings the model added on its own carry ids beginning MOD- and no rule id;
    they are counted separately rather than scored, because there is nothing to
    compare them against.
    """
    return {f.rule_id for f in report.findings if f.rule_id}


def model_added_count(report: Report) -> int:
    return sum(1 for f in report.findings if not f.rule_id)


def matched_missing(expected: list[str], reported: list[str]) -> tuple[list[str], list[str]]:
    """Match expected document keywords against the reported missing-document lines.

    The report names missing documents in the user's language and in prose, so an
    exact string match would test the wording rather than the behaviour. Each
    expected entry is a keyword that must appear somewhere in the reported list.
    """
    lowered = " | ".join(reported).lower()
    found = [key for key in expected if key.lower() in lowered]
    absent = [key for key in expected if key.lower() not in lowered]
    return found, absent


def evaluate_bundle(name: str, spec: dict, provider: str | None, model: str | None, language: str) -> dict:
    paths = bundle_paths(name)
    client = build_client(provider=provider, model=model)

    started = time.monotonic()
    report = analyse_paths(paths, language=language, client=client)
    elapsed = time.monotonic() - started

    fired = fired_rule_ids(report)
    expect = set(spec.get("expect_rules", []))
    forbid = set(spec.get("forbid_rules", []))
    watch = set(spec.get("watch_rules", []))

    found_missing, absent_missing = matched_missing(
        spec.get("expect_missing_documents", []), report.missing_documents
    )

    gate_ok = bool(report.gated) == bool(spec.get("expect_gated", False))

    result = {
        "bundle": name,
        "documents": len(paths),
        "model": getattr(client, "model", None) or getattr(client, "provider_label", "unknown"),
        "seconds": round(elapsed, 1),
        "expected_found": sorted(expect & fired),
        "expected_missed": sorted(expect - fired),
        "forbidden_fired": sorted(forbid & fired),
        "watch_fired": sorted(watch & fired),
        "unlisted_fired": sorted(fired - expect - forbid - watch),
        "model_added_findings": model_added_count(report),
        "gated": bool(report.gated),
        "gate_expected": bool(spec.get("expect_gated", False)),
        "gate_ok": gate_ok,
        "gate_reason": report.gate_reason,
        "conflicts": len(report.conflicts),
        "missing_documents_found": found_missing,
        "missing_documents_absent": absent_missing,
        "missing_documents_reported": report.missing_documents,
        "dropped_by_grounding": report.dropped_finding_count,
        "confidence": round(report.overall_confidence, 3),
        "unverified_rules_used": report.unverified_rule_ids,
        "notes": report.notes,
    }
    result["passed"] = (
        not result["expected_missed"]
        and not result["forbidden_fired"]
        and not result["missing_documents_absent"]
        and gate_ok
    )
    return result


def print_bundle(result: dict) -> None:
    mark = "PASS" if result["passed"] else "FAIL"
    print()
    print(f"  {mark}  {result['bundle']}  ({result['documents']} docs, {result['model']}, {result['seconds']}s)")

    expected_total = len(result["expected_found"]) + len(result["expected_missed"])
    if expected_total:
        print(f"        planted rules found : {len(result['expected_found'])}/{expected_total}")
    if result["expected_missed"]:
        print(f"        MISSED              : {', '.join(result['expected_missed'])}")
    if result["forbidden_fired"]:
        print(f"        FALSE POSITIVES     : {', '.join(result['forbidden_fired'])}")
    if result["watch_fired"]:
        print(f"        watched, fired      : {', '.join(result['watch_fired'])}")
    if result["unlisted_fired"]:
        print(f"        fired, not listed   : {', '.join(result['unlisted_fired'])}")
    if result["missing_documents_absent"]:
        print(f"        missing docs NOT named: {', '.join(result['missing_documents_absent'])}")
    elif result["missing_documents_found"]:
        print(f"        missing docs named  : {', '.join(result['missing_documents_found'])}")
    if not result["gate_ok"]:
        print(f"        GATE                : gated={result['gated']}, expected {result['gate_expected']}")
    elif result["gate_expected"]:
        print(f"        gate                : fired as required ({result['conflicts']} conflict(s))")
    print(
        f"        confidence {result['confidence']}"
        f" | grounding dropped {result['dropped_by_grounding']}"
        f" | model-added findings {result['model_added_findings']}"
    )


def main() -> int:
    _force_utf8_output()
    parser = argparse.ArgumentParser(description="Measure the pipeline against samples/expectations.json.")
    parser.add_argument("--provider", choices=config.PROVIDERS, default=None, help="Backend to measure. Defaults to CTF_PROVIDER.")
    parser.add_argument("--model", default=None, help="Override the model for that provider.")
    parser.add_argument("--bundle", action="append", default=None, help="Run one bundle; repeatable. Defaults to all.")
    parser.add_argument("--language", default="en", help="Report language. The scored expectations are rule ids, so this does not change the score.")
    parser.add_argument("--json", dest="json_path", default=None, help="Write the full results to this file.")
    args = parser.parse_args()

    expectations = load_expectations()
    names = args.bundle or list(expectations["bundles"])

    print()
    print("  Measuring against samples/expectations.json")
    print("  These bundles were written by the team. A score here is a regression signal,")
    print("  not a measurement against real contracts - see the meta block in that file.")

    results = []
    for name in names:
        spec = expectations["bundles"].get(name)
        if spec is None:
            raise SystemExit(f"{name} is not in expectations.json")
        result = evaluate_bundle(name, spec, args.provider, args.model, args.language)
        results.append(result)
        print_bundle(result)

    planted_found = sum(len(r["expected_found"]) for r in results)
    planted_total = planted_found + sum(len(r["expected_missed"]) for r in results)
    false_positives = sum(len(r["forbidden_fired"]) for r in results)
    passed = sum(1 for r in results if r["passed"])

    print()
    print("  " + "-" * 60)
    print(f"  {passed}/{len(results)} bundles passed every scored expectation")
    if planted_total:
        print(f"  {planted_found}/{planted_total} planted rules found across the run")
    print(f"  {false_positives} rule(s) fired that a bundle forbids")
    print(f"  {sum(r['dropped_by_grounding'] for r in results)} finding(s) discarded by the grounding check")
    print(f"  {round(sum(r['seconds'] for r in results), 1)}s total")
    print()

    if args.json_path:
        payload = {
            "run_at": datetime.now(timezone.utc).isoformat(),
            "provider": args.provider or config.DEFAULT_PROVIDER,
            "language": args.language,
            "summary": {
                "bundles_passed": passed,
                "bundles_run": len(results),
                "planted_rules_found": planted_found,
                "planted_rules_total": planted_total,
                "false_positives": false_positives,
            },
            "bundles": results,
        }
        Path(args.json_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"  Wrote {args.json_path}")
        print()

    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
