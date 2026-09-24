"""Command line entry point.

    py -m contract_trap_finder.cli samples/bundle_a_nl_tied_housing/*.txt --language pl

The CLI exists for two reasons: it is how the tests and the caseworker workflow run
the pipeline without a browser, and it makes the whole flow visible in a terminal
recording for the demo.

Two things a user of it should know, and which the run prints for itself:

* **Take the personal details out of the documents first** - name, date of birth,
  BSN, address, and the employer's name. No check reads them; the rules are about
  clauses, amounts and dates.
* **With the default provider the document text is sent to Google's Gemini API.**
  `--provider ollama` reads the documents with a model on this machine and sends
  nothing over the network.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from . import config
from .console import ProgressReporter, Theme, theme_for
from .llm import LLMClient, MissingAPIKey, UnknownProvider, build_client, ollama_client
from .models import Report
from .pipeline import analyse_paths
from .rules import unverified_reference_values, unverified_rule_ids
from .safety import DISCLAIMER, NO_FINDINGS_MESSAGE, TALK_TO_A_HUMAN
from .steps.s1_ingest import IngestError

CATEGORY_LABELS = {
    "ILLEGAL": "AGAINST THE LAW",
    "RISK_SHIFT": "LEGAL, BUT THE RISK IS ALL YOURS",
    "BELOW_EQUAL_TREATMENT": "POSSIBLY LESS THAN YOU ARE ENTITLED TO",
}

# Colour per category, used only alongside the words above - never instead of them.
CATEGORY_STYLES = {
    "ILLEGAL": ("bold", "bright_red"),
    "RISK_SHIFT": ("bold", "yellow"),
    "BELOW_EQUAL_TREATMENT": ("bold", "cyan"),
}

SEVERITY_LABELS = {"high": "HIGH", "medium": "MEDIUM", "low": "LOW"}
SEVERITY_STYLES = {"high": ("bright_red",), "medium": ("yellow",), "low": ("grey",)}


class _ProgressLogHandler(logging.Handler):
    """Sends log records to the live progress line instead of raw stderr.

    Without this, a failover warning from the LLM client is written straight to
    stderr in the middle of a repainting spinner and the two overwrite each other.

    It listens at INFO rather than WARNING because the backends narrate at INFO:
    which model is being asked, for which schema, how big the prompt is, how long
    the answer took and how many tokens it cost. That is most of what anyone wants
    to know while a run is sitting on a single call, and at WARNING none of it was
    reaching the terminal - only the failures were.
    """

    def __init__(self, reporter: ProgressReporter) -> None:
        super().__init__(level=logging.INFO)
        self.reporter = reporter

    def emit(self, record: logging.LogRecord) -> None:
        try:
            style = "warn" if record.levelno >= logging.WARNING else "muted"
            prefix = "" if record.levelno >= logging.WARNING else f"{self.reporter.theme.bullet} "
            self.reporter.note(f"{prefix}{record.getMessage()}", style=style)
        except Exception:  # noqa: BLE001 - logging must never break the run
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contract-trap-finder",
        description="Read a bundle of employment and housing documents and report what is illegal, what shifts every risk onto the worker, and where they are offered less than the law promises.",
    )
    parser.add_argument("paths", nargs="*", help="Document files to analyse (.txt or .pdf).")
    parser.add_argument(
        "-l",
        "--language",
        default=config.DEFAULT_LANGUAGE,
        choices=sorted(config.SUPPORTED_LANGUAGES),
        help="Language to write the report in (default: %(default)s).",
    )
    parser.add_argument(
        "--provider",
        default=None,
        choices=sorted(config.PROVIDERS),
        help=(
            "Which backend reads the documents: the Gemini API, or a model running on this machine "
            f"through Ollama (default: {config.DEFAULT_PROVIDER}, from CTF_PROVIDER)."
        ),
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model id for whichever provider is in use, e.g. --provider ollama --model qwen3:14b.",
    )
    parser.add_argument("--json", action="store_true", help="Print the full report as JSON instead of text.")
    parser.add_argument("-o", "--output", help="Write the output to this file instead of stdout.")
    parser.add_argument(
        "--takeaway",
        nargs="?",
        const="",
        default=None,
        metavar="PATH",
        help="Also write the bilingual take-away sheet as a .docx. With no path, names the file after the language and date.",
    )
    parser.add_argument("--check-setup", action="store_true", help="Check the API key and rule data, then exit.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show every log message, not just progress.")
    parser.add_argument("-q", "--quiet", action="store_true", help="Print no progress at all.")
    parser.add_argument("--no-colour", "--no-color", dest="no_colour", action="store_true", help="Plain text output.")
    return parser


def check_setup(theme: Theme | None = None, provider: str | None = None) -> int:
    """Verify the things that stop this running, before anyone waits on an API call.

    What counts as "ready" depends on the backend: a missing API key is fatal for a
    Gemini run and irrelevant for a local one, and vice versa for a stopped Ollama
    server. Both are reported either way - knowing the other backend is available is
    exactly what you want when the one you asked for is not.
    """
    t = theme or theme_for(sys.stdout)
    chosen = (provider or config.DEFAULT_PROVIDER).strip().lower()
    ok = True

    def line(passed: bool, text: str) -> None:
        mark = t.ok(t.tick) if passed else t.critical("!")
        print(f"  {mark}  {text}")

    def soft(text: str) -> None:
        """A fact about the backend that is not in use: never fails the check."""
        print(f"  {t.muted('-')}  {t.muted(text)}")

    print()
    print(t.heading("  Contract Trap Finder") + t.muted(f"  ·  setup check  ·  provider: {chosen}"))
    print(t.rule(60))

    key = config.get_api_key()
    if chosen == "gemini":
        if key:
            line(True, f"API key found {t.muted(f'({len(key)} characters)')}")
        else:
            line(False, "No API key. Copy .env.example to .env and set GEMINI_API_KEY.")
            ok = False

        try:
            import google.genai  # noqa: F401

            line(True, "google-genai installed")
        except ImportError:
            line(False, "google-genai not installed. Run: pip install -r requirements.txt")
            ok = False
    else:
        soft(f"API key {'found' if key else 'not set'} (not needed for a local run)")

    reachable, message = ollama_client.server_status()
    installed = ollama_client.list_models() if reachable else []
    if chosen == "ollama":
        line(reachable, message)
        ok = ok and reachable
        if reachable:
            wanted = config.OLLAMA_MODEL
            has_it = wanted in installed
            line(has_it, f"Model {t('`' + wanted + '`', 'bold')}" if has_it else f"`{wanted}` is not installed. Run: ollama pull {wanted}")
            ok = ok and has_it
            if installed:
                print(f"      {t.muted('installed: ' + ', '.join(installed))}")
            if wanted not in config.OLLAMA_TRUSTED_MODELS:
                print(f"      {t.muted('local runs are reported as lower confidence - see ETHICS.md')}")
    elif reachable:
        soft(f"{message}, {len(installed)} model(s) installed - available with --provider ollama")

    try:
        from .rules import load_contacts, load_rules

        rules = load_rules()
        contacts = load_contacts()
        line(True, f"{len(rules['rules'])} legal rules and {len(contacts['contacts'])} contacts loaded")
    except Exception as exc:  # noqa: BLE001
        line(False, f"Rule data problem: {exc}")
        return 1

    if chosen == "gemini":
        line(True, f"Model {t('`' + config.MODEL + '`', 'bold')}")
        if config.MODEL_FALLBACKS:
            print(f"      {t.muted('falls back to ' + ', '.join(config.MODEL_FALLBACKS))}")
        print()
        print(t.warn("  WHERE THE DOCUMENTS GO: with this provider, the full text of every document is"))
        print(t.warn("  sent over the internet to Google's Gemini API to be read."))
        print(t.muted("    Nothing is stored or logged by this tool, and nothing is written to disk, but"))
        print(t.muted("    what Google does with the text is outside our control and we have not reviewed"))
        print(t.muted("    the data-retention terms of the tier we use. Strip names, dates of birth, BSN"))
        print(t.muted("    and addresses from the documents first - no check reads them. --provider ollama"))
        print(t.muted("    reads the documents on this machine and sends nothing. See ETHICS.md, risk 7."))

    unverified_rules = unverified_rule_ids()
    unverified_values = unverified_reference_values()
    if unverified_rules or unverified_values:
        print()
        print(t.warn("  UNVERIFIED - must be checked before this is presented as fact:"))
        for rule_id in unverified_rules:
            print(t.muted(f"    {t.bullet} rule {rule_id}"))
        for name in unverified_values:
            print(t.muted(f"    {t.bullet} reference value {name}"))
        print(t.muted("    See Current status and limitations in README.md."))

    print(t.rule(60))
    print(t.ok("  Ready.") if ok else t.critical("  Not ready - fix the failures above."))
    print()
    return 0 if ok else 1


def render_text(report: Report, theme: Theme | None = None) -> str:
    """The report as text. Mirrors the four sections of the web output.

    `theme` decides whether ANSI colour is used; with the default no-colour theme
    this returns exactly the plain text it always did, which is what `-o` and a
    redirected stdout want.
    """
    t = theme or Theme(colour=False, unicode_ok=False)
    out: list[str] = []
    add = out.append

    add(t.rule(72, heavy=True))
    add(t("  CONTRACT TRAP FINDER", "bold"))
    add(t.muted(f"  Generated {report.generated_at:%Y-%m-%d %H:%M UTC}  {t.bullet}  language: {report.user_language}"))
    add(t.rule(72, heavy=True))

    if report.documents_received:
        add("")
        add(t.heading("DOCUMENTS READ"))
        for doc in report.documents_received:
            add(f"  {t.bullet} {doc.filename}")
            add(t.muted(f"      {doc.doc_type}, {doc.detected_language}, {doc.char_count:,} characters"))

    # A count per category, so the shape of the result is visible before reading it.
    if report.findings:
        add("")
        add(t.heading("AT A GLANCE"))
        for category, label in CATEGORY_LABELS.items():
            count = sum(1 for f in report.findings if f.category == category)
            if not count:
                continue
            styles = CATEGORY_STYLES.get(category, ())
            add(f"  {t(str(count).rjust(3), *styles)}  {t(label.lower().capitalize(), *styles)}")

    if report.gated:
        add("")
        add(t.critical("  " + "!" * 68))
        add(t.critical("  WE ARE NOT CONFIDENT ENOUGH TO SUMMARISE THESE DOCUMENTS"))
        add(t.critical("  " + "!" * 68))
        add(f"\n{report.gate_reason}")
        if report.conflicts:
            add("\nWhere the documents disagree:")
            for conflict in report.conflicts:
                add(f"  {t.bullet} {conflict}")

    if report.missing_documents:
        add("")
        add(t.heading("DOCUMENTS WE DID NOT GET"))
        add(t.muted("  Many people do not realise they signed several separate things."))
        for item in report.missing_documents:
            add(f"  {t.bullet} {item}")

    add("")
    add(t.rule(72))
    add(t.heading("WHAT WE FOUND"))
    add(t.rule(72))

    if not report.findings:
        add(f"\n{NO_FINDINGS_MESSAGE}")
    else:
        # Ahead of the findings, for the reason in `safety.TALK_TO_A_HUMAN`: by the
        # time a reader reaches the bottom of a list of quoted clauses they have
        # already decided what it means.
        add("")
        add(t.warn(TALK_TO_A_HUMAN))
        current_category = None
        for finding in report.findings:
            if finding.category != current_category:
                current_category = finding.category
                label = CATEGORY_LABELS.get(finding.category, finding.category)
                styles = CATEGORY_STYLES.get(finding.category, ())
                add("")
                add(t(f"  {label}", *styles))
                add(t.muted("  " + "-" * len(label)))
                add("")
            severity = t(
                f"[{SEVERITY_LABELS.get(finding.severity, finding.severity.upper())}]",
                *SEVERITY_STYLES.get(finding.severity, ()),
            )
            add(f"  {severity} {t(finding.title, 'bold')}")
            add(f"      {finding.what_it_means}")
            for quote in finding.quotes:
                ref = f" (clause {quote.clause_ref})" if quote.clause_ref else ""
                add(t.muted(f"      from {quote.doc_id}{ref}:"))
                add(t.quote(f'      "{quote.quote.strip()}"'))
            if not finding.rule_verified and finding.rule_id:
                add(t.warn("      [the legal figure behind this check has not yet been verified by the team]"))
            add("")

    if report.exit_scenario:
        add(t.rule(72))
        add(t.heading("IF THIS WORK ENDS"))
        add(t.rule(72))
        add(f"\n{report.exit_scenario.trigger_description}\n")
        for event in report.exit_scenario.events:
            when = "the same day" if event.day_offset == 0 else (f"after {event.day_offset} days" if event.day_offset is not None else "timing not stated")
            add(f"  {t(when, 'bold')}: {event.label}")
            add(f"      {event.description}")
        if report.exit_scenario.outstanding_amount:
            add("")
            add(t.warn(f"  Still owed: {report.exit_scenario.currency} {report.exit_scenario.outstanding_amount:,.2f}"))
        if report.exit_scenario.caveat:
            add(t.muted(f"\n  Note: {report.exit_scenario.caveat}"))
        add("")

    if report.safe_questions:
        add(t.rule(72))
        add(t.heading("QUESTIONS THAT ARE SAFE TO ASK, IN WRITING"))
        add(t.rule(72))
        add(t.muted("\nAsk by message rather than in person, so you have a record of the answer.\n"))
        for index, question in enumerate(report.safe_questions, start=1):
            add(f"  {t(str(index) + '.', 'bold')} {t(question.question_in_user_language, 'bold')}")
            add(f"     {t.muted('To send:')} {question.question_in_employer_language}")
            add(t.muted(f"     Why: {question.why_this_question}"))
            add(t.muted(f"     If they will not answer in writing: {question.what_a_refusal_means}"))
            add("")

    if report.contacts:
        add(t.rule(72))
        add(t.heading("WHO YOU CAN TALK TO"))
        add(t.rule(72))
        add(t.muted("\nConfidential advice is listed first. Enforcement bodies are last, and are your choice alone."))
        add(t.muted("These organisations read contracts like this one every week. This program does not.\n"))
        for contact in report.contacts:
            add(f"  {t(contact.name, 'bold')} {t.muted('[' + contact.kind.replace('_', ' ') + ']')}")
            add(f"      {contact.what_they_do}")
            add(f"      {t.muted('Will your employer find out?')} {contact.will_employer_find_out}")
            add(f"      {t.muted('How long:')} {contact.typical_response_time}")
            add(f"      {t.muted('Contact:')} {contact.contact}")
            if contact.url:
                add(t.muted(f"      {contact.url}"))
            add("")

    add(t.rule(72))
    confidence = f"Confidence: {report.overall_confidence:.0%}"
    add(t.ok(confidence) if report.overall_confidence >= 0.75 else t.warn(confidence))
    if report.dropped_finding_count:
        add(t.muted(f"{report.dropped_finding_count} suggested finding(s) were discarded because the text they quoted could not be found in your documents."))
    if report.unverified_rule_ids:
        add(t.muted(f"Unverified rules used: {', '.join(report.unverified_rule_ids)}"))
    if report.notes:
        add("\n" + t.heading("Notes:"))
        for note in report.notes:
            add(t.muted(f"  {t.bullet} {note}"))
    add(f"\n{t.muted(DISCLAIMER)}")

    return "\n".join(out)


def _force_utf8_output() -> None:
    """Make stdout and stderr UTF-8.

    Not cosmetic: the Windows console defaults to cp1252, and this tool's whole
    purpose is writing Polish, Romanian and Bulgarian. Without this, printing a
    report in the user's own language raises UnicodeEncodeError and the run dies
    after the API has already been paid for.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # pragma: no cover - redirected stream
                pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    args = build_parser().parse_args(argv)

    if args.no_colour:
        os.environ["NO_COLOR"] = "1"

    # Two themes, because the destinations differ: progress always goes to stderr,
    # while the report may be going to a file or down a pipe, where escapes would be
    # noise rather than colour.
    status_theme = theme_for(sys.stderr)
    report_theme = theme_for(sys.stdout) if not args.output and not args.json else Theme(False, False)

    if args.check_setup:
        return check_setup(theme_for(sys.stdout), provider=args.provider)

    if not args.paths:
        build_parser().print_help()
        return 2

    missing = [p for p in args.paths if not Path(p).exists()]
    if missing:
        print(status_theme.critical(f"File(s) not found: {', '.join(missing)}"), file=sys.stderr)
        return 2

    # Progress is on unless asked otherwise. It used to require --verbose, which
    # meant the common case was a terminal that printed nothing for a minute or
    # more while the API was called, looking indistinguishable from a hang.
    show_progress = not args.quiet
    if args.verbose:
        # Raw logs were explicitly asked for, so the progress line stands aside.
        logging.basicConfig(
            level=logging.INFO,
            format="%(levelname)s %(name)s: %(message)s",
            stream=sys.stderr,
        )
    else:
        # Deliberately no stream handler: warnings reach the user through the
        # progress reporter instead, which knows how to print above a live line.
        # Installing both would print every warning twice.
        logging.getLogger().setLevel(logging.WARNING)

    try:
        client = build_client(args.provider, model=args.model)
    except (MissingAPIKey, UnknownProvider) as exc:
        print(f"\n{status_theme.critical(str(exc))}\n", file=sys.stderr)
        return 1

    if show_progress:
        _print_banner(status_theme, args, client)

    reporter = ProgressReporter(sys.stderr, theme=status_theme, enabled=show_progress)
    handler = _ProgressLogHandler(reporter)
    # This package's own logger, not the root one: at INFO the root logger would
    # also carry urllib3's connection chatter and every library that logs politely,
    # which would bury the narration this is here to surface.
    package_logger = logging.getLogger("contract_trap_finder")
    if show_progress and not args.verbose:
        # With --verbose the user asked for raw logs; leave them alone.
        package_logger.setLevel(logging.INFO)
        package_logger.addHandler(handler)

    try:
        with reporter:
            report = analyse_paths(args.paths, language=args.language, client=client, progress=reporter)
    except IngestError as exc:
        print(f"\n{status_theme.critical(str(exc))}\n", file=sys.stderr)
        return 1
    finally:
        package_logger.removeHandler(handler)

    if (
        show_progress
        and client.provider == "gemini"
        and client.last_model_used
        and client.last_model_used != config.MODEL
    ):
        print(
            status_theme.warn(f"  Answered by {client.last_model_used}, because {config.MODEL} was unavailable."),
            file=sys.stderr,
        )

    text = report.model_dump_json(indent=2) if args.json else render_text(report, report_theme)

    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(status_theme.ok(f"Written to {args.output}"), file=sys.stderr)
    else:
        print(text)

    if args.takeaway is not None:
        _write_takeaway(args.takeaway, report, status_theme)

    return 0


def _write_takeaway(path: str, report, status_theme: Theme) -> None:
    """Write the .docx sheet, and never let a failure there cost the analysis.

    The sheet is an extra copy of a report the user already has on screen or in a
    file, so a missing python-docx is worth a line on stderr and nothing more. It
    goes to stderr like the rest of the narration, so `--json` and `-o` keep
    producing clean output on stdout.
    """
    from .takeaway import default_filename, write_takeaway

    destination = Path(path) if path else Path(default_filename(report))
    try:
        written = write_takeaway(report, destination)
    except ImportError:
        print(
            status_theme.warn("  The take-away sheet needs python-docx: pip install -r requirements.txt"),
            file=sys.stderr,
        )
    except OSError as exc:
        print(status_theme.warn(f"  Could not write the take-away sheet: {exc}"), file=sys.stderr)
    else:
        print(status_theme.ok(f"Take-away sheet written to {written}"), file=sys.stderr)


def _print_banner(t: Theme, args: argparse.Namespace, client: LLMClient) -> None:
    """A short header, so it is obvious what is being read and in which language."""
    count = len(args.paths)
    print(file=sys.stderr)
    print(t.heading("  Contract Trap Finder"), file=sys.stderr)
    print(
        t.muted(f"  {count} document{'s' if count != 1 else ''}  {t.bullet}  "
                f"report in {config.SUPPORTED_LANGUAGES.get(args.language, args.language)}  {t.bullet}  "
                f"{client.provider_label}"
                + (f"  {t.bullet}  {client.key_count} API keys" if client.key_count > 1 else "")),
        file=sys.stderr,
    )
    if client.provider == "gemini":
        # Printed before the first call, not after it. Someone running this over a
        # real bundle is entitled to see where the text goes while they can still
        # press ctrl-c.
        print(
            t.warn(f"  The text of {'these documents' if count != 1 else 'this document'} will be sent to "
                   f"Google's Gemini API to be read."),
            file=sys.stderr,
        )
        print(
            t.muted("  Nothing is stored or logged by this tool, but what Google does with it is outside "
                    "our control.\n  Remove names, dates of birth, BSN and addresses first; the analysis "
                    "does not use them.\n  Use --provider ollama to read the documents on this machine "
                    "instead, and send nothing."),
            file=sys.stderr,
        )
    print(t.rule(60), file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
