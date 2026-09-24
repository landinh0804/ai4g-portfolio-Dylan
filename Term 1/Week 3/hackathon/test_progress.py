"""What the tool says about itself while it runs.

This is not cosmetic. A run makes several model calls in series and can sit on any
one of them for a minute or more; before this channel existed, both front-ends went
silent for that whole time and the only thing a user could tell was that the clock
was still moving. The tests here pin the two properties that make the narration
worth having: that it names what is happening *inside* a long step, and that the
numbers it reports are the ones that reveal a bad run.
"""

from __future__ import annotations

import io

from contract_trap_finder import progress as ctf_progress
from contract_trap_finder.console import ProgressReporter, Theme
from contract_trap_finder.pipeline import analyse
from contract_trap_finder.progress import Progress, ProgressEvent, kind_of, plural
from tests.test_pipeline import FakeClient, documents, structured_bundle


# --- The event type --------------------------------------------------------


def test_an_event_is_still_a_plain_string():
    """Old callers were handed strings and must keep working unchanged."""
    event = ProgressEvent("Reading 3 documents", ctf_progress.DETAIL)
    assert event == "Reading 3 documents"
    assert event.upper().startswith("READING")
    assert isinstance(event, str)


def test_a_bare_string_is_treated_as_a_step():
    assert kind_of("something an older caller sent") == ctf_progress.STEP


def test_each_helper_sets_its_own_kind():
    seen: list[tuple[str, str]] = []
    say = Progress(lambda e: seen.append((kind_of(e), str(e))))

    say.step("Reading")
    say.detail("1 of 3")
    say.result("3 read")
    say.warn("could not read one")

    assert seen == [
        (ctf_progress.STEP, "Reading"),
        (ctf_progress.DETAIL, "1 of 3"),
        (ctf_progress.RESULT, "3 read"),
        (ctf_progress.WARN, "could not read one"),
    ]


def test_a_broken_front_end_cannot_break_the_analysis():
    """Narration is never worth failing a contract review over."""

    def explode(_event):
        raise RuntimeError("the UI fell over")

    Progress(explode).step("Reading")  # must not raise


def test_plural_reads_as_english():
    assert plural(1, "document") == "1 document"
    assert plural(3, "document") == "3 documents"
    assert plural(2, "party", "parties") == "2 parties"
    assert plural(1200, "character") == "1,200 characters"


# --- The terminal ----------------------------------------------------------


def reporter_for(buffer: io.StringIO) -> ProgressReporter:
    """A reporter with no colour and no animation, so output is assertable."""
    return ProgressReporter(buffer, theme=Theme(colour=False, unicode_ok=False), enabled=True)


def test_detail_does_not_start_a_new_step():
    buffer = io.StringIO()
    reporter = reporter_for(buffer)

    reporter(ProgressEvent("Reading 3 documents", ctf_progress.STEP))
    reporter(ProgressEvent("1 of 3: contract.txt", ctf_progress.DETAIL))
    reporter(ProgressEvent("2 of 3: housing.txt", ctf_progress.DETAIL))

    # One step opened, and no step closed: a closing line carries the tick mark.
    assert buffer.getvalue().count("+") == 0
    assert "1 of 3: contract.txt" in buffer.getvalue()


def test_a_finished_step_is_named_by_the_step_not_its_last_detail():
    """Otherwise a three-document read closes as if it were only about the third."""
    buffer = io.StringIO()
    reporter = reporter_for(buffer)

    reporter(ProgressEvent("Reading 3 documents", ctf_progress.STEP))
    reporter(ProgressEvent("3 of 3: mandate.txt", ctf_progress.DETAIL))
    reporter(ProgressEvent("Comparing the documents", ctf_progress.STEP))

    closing = [line for line in buffer.getvalue().splitlines() if line.startswith("  +")]
    assert len(closing) == 1
    assert "Reading 3 documents" in closing[0]
    assert "mandate.txt" not in closing[0]


def test_warnings_are_marked_and_results_are_not():
    buffer = io.StringIO()
    reporter = reporter_for(buffer)

    reporter(ProgressEvent("Checking the rules", ctf_progress.STEP))
    reporter(ProgressEvent("5 rules fired", ctf_progress.RESULT))
    reporter(ProgressEvent("a document was unreadable", ctf_progress.WARN))

    output = buffer.getvalue()
    assert "! a document was unreadable" in output
    assert "! 5 rules fired" not in output
    assert "5 rules fired" in output


def test_nothing_is_printed_when_progress_is_switched_off():
    """`--quiet` has to stay genuinely quiet, or it breaks piped output."""
    buffer = io.StringIO()
    reporter = ProgressReporter(buffer, theme=Theme(False, False), enabled=False)

    reporter(ProgressEvent("Reading", ctf_progress.STEP))
    reporter(ProgressEvent("1 of 3", ctf_progress.DETAIL))
    reporter(ProgressEvent("done", ctf_progress.RESULT))

    assert buffer.getvalue() == ""


# --- What a real run narrates ----------------------------------------------


def run_and_collect() -> list[tuple[str, str]]:
    docs = documents()
    client = FakeClient(structured=structured_bundle([d.doc_id for d in docs]))
    seen: list[tuple[str, str]] = []
    analyse(docs, language="en", client=client, progress=lambda e: seen.append((kind_of(e), str(e))))
    return seen


def test_a_run_reports_each_document_as_it_is_read():
    """The long step. Without this it is one message for the whole bundle."""
    details = [text for kind, text in run_and_collect() if kind == ctf_progress.DETAIL]
    assert any("1 of 2" in text and "contract.txt" in text for text in details)
    assert any("2 of 2" in text and "housing.txt" in text for text in details)


def test_a_run_reports_what_each_phase_produced():
    results = " | ".join(text for kind, text in run_and_collect() if kind == ctf_progress.RESULT)
    # The counts that distinguish a good run from one that parsed but read nothing.
    assert "2 of 2 read" in results
    assert "rules" in results and "fired" in results
    assert "Confidence" in results


def test_the_backend_is_named_before_any_slow_work_happens():
    events = run_and_collect()
    first = events[0][1]
    assert "2 documents" in first