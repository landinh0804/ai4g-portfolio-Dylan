"""Streamlit interface.

    streamlit run app.py

Laid out for a phone on a bad connection, because that is where the brief's primary
user reads: single column, no side-by-side comparisons, the most serious findings
first, and nothing that needs horizontal scrolling.

The visual language lives in `contract_trap_finder.ui`; this file is the page order.
"""

from __future__ import annotations

import io
import logging
import sys
import threading
import time
from pathlib import Path

import streamlit as st

# Works whether or not the package has been pip-installed.
SRC = Path(__file__).parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from contract_trap_finder import config, ui  # noqa: E402
from contract_trap_finder import progress as ctf_progress  # noqa: E402
from contract_trap_finder.llm import MissingAPIKey, build_client  # noqa: E402
from contract_trap_finder.llm import ollama_client  # noqa: E402
from contract_trap_finder.models import Report  # noqa: E402
from contract_trap_finder.pipeline import analyse  # noqa: E402
from contract_trap_finder.safety import DISCLAIMER, NO_FINDINGS_MESSAGE, TALK_TO_A_HUMAN  # noqa: E402
from contract_trap_finder.steps import s1_ingest  # noqa: E402
from contract_trap_finder import takeaway  # noqa: E402

SAMPLES_DIR = Path(__file__).parent / "samples"

CATEGORY_LABELS = {
    "ILLEGAL": "Against the law",
    "RISK_SHIFT": "Legal, but the risk is all yours",
    "BELOW_EQUAL_TREATMENT": "Possibly less than you are entitled to",
}
CATEGORY_HELP = {
    "ILLEGAL": "These terms are not allowed. A term like this has no legal force, even though it is written in your contract.",
    "RISK_SHIFT": "These terms are allowed. They are here because of what they would mean for you if something goes wrong.",
    "BELOW_EQUAL_TREATMENT": "Dutch law may already promise you more than these documents offer.",
}
# Shorter wording for the summary tiles, where there is no room for a sentence.
CATEGORY_TILE_LABELS = {
    "ILLEGAL": "against the law",
    "RISK_SHIFT": "risk shifted onto you",
    "BELOW_EQUAL_TREATMENT": "possibly below your entitlement",
}

# The sidebar starts collapsed because on a phone Streamlit renders it as an overlay
# across the whole screen. Nothing the user needs in order to use the tool lives
# there - the language selector is in the main column, above everything else.
st.set_page_config(
    page_title="Contract Trap Finder",
    page_icon="📄",
    layout="centered",
    initial_sidebar_state="collapsed",
)


def html(markup: str) -> None:
    """Write one of the blocks from `ui`. Everything inside is already escaped."""
    st.markdown(markup, unsafe_allow_html=True)


# --- State -----------------------------------------------------------------


def _state():
    st.session_state.setdefault("documents", [])
    st.session_state.setdefault("report", None)
    st.session_state.setdefault("error", None)
    st.session_state.setdefault("ran_with_model", None)
    st.session_state.setdefault("ran_with_provider", None)
    st.session_state.setdefault("provider", config.DEFAULT_PROVIDER)
    st.session_state.setdefault("ollama_model", config.OLLAMA_MODEL)


def _add_document(doc) -> None:
    existing = {d.doc_id for d in st.session_state.documents}
    if doc.doc_id in existing:
        doc = doc.model_copy(update={"doc_id": f"{doc.doc_id}_{len(existing)}"})
    st.session_state.documents.append(doc)


# --- Which model reads the documents ---------------------------------------

PROVIDER_LABELS = {
    "gemini": "Google Gemini (over the internet)",
    "ollama": "On this computer (Ollama)",
}


@st.cache_data(ttl=20, show_spinner=False)
def _local_models(host: str) -> list[str]:
    """Models installed on the Ollama server. Cached so a rerun is not a round trip.

    Streamlit reruns this whole script on every interaction, including every
    keystroke elsewhere on the page, and an uncached call would put an HTTP request
    on each one.
    """
    return ollama_client.list_models(host)


@st.cache_data(ttl=20, show_spinner=False)
def _local_status(host: str) -> tuple[bool, str]:
    return ollama_client.server_status(host)


def render_engine_picker() -> tuple[str, str | None]:
    """The engine control. Returns `(provider, model)` for this run.

    It lives in the sidebar rather than the main column deliberately. The main
    column is written for someone reading a contract on a phone twenty minutes
    before they are asked to sign it, and one more decision in front of that is a
    cost; the people who need this control - us, while testing, and anyone who wants
    the documents to stay on their own machine - will open the sidebar to find it.
    """
    st.subheader("Which model reads this")

    provider = st.radio(
        "Engine",
        options=list(config.PROVIDERS),
        format_func=lambda p: PROVIDER_LABELS.get(p, p),
        key="provider",
        label_visibility="collapsed",
    )

    if provider == "gemini":
        st.caption(f"Model: `{config.MODEL}`")
        if config.MODEL_FALLBACKS:
            st.caption(f"Falls back to: `{', '.join(config.MODEL_FALLBACKS)}`")
        if not config.get_api_key():
            st.error("No API key. Copy `.env.example` to `.env` and set `GEMINI_API_KEY`.")
        return provider, None

    reachable, message = _local_status(config.OLLAMA_HOST)
    if not reachable:
        st.error(message)
        st.caption("Install it from ollama.com, then `ollama pull qwen3:8b`.")
        # Still return the local choice: the run will fail with the same message,
        # which is more honest than silently sending the documents to Google after
        # the user asked for them to stay here.
        return provider, st.session_state.ollama_model

    installed = _local_models(config.OLLAMA_HOST)
    if not installed:
        st.warning(f"{message}, but no models are installed. Run `ollama pull qwen3:8b`.")
        return provider, st.session_state.ollama_model

    # Keep whatever was chosen before if it is still installed, so a rerun does not
    # quietly move the run to a different model.
    current = st.session_state.ollama_model
    index = installed.index(current) if current in installed else 0
    model = st.selectbox("Model", options=installed, index=index)
    st.session_state.ollama_model = model

    col_refresh, _ = st.columns([1, 1])
    if col_refresh.button("Refresh list", use_container_width=True):
        _local_models.clear()
        _local_status.clear()
        st.rerun()

    st.caption(message)
    if model in config.OLLAMA_TRUSTED_MODELS:
        st.caption("This model has been checked against the sample bundles.")
    else:
        st.caption(
            "Local models are smaller than the hosted ones and read a contract less accurately. "
            "Reports from this engine are marked as lower confidence."
        )
    return provider, model


# --- Input -----------------------------------------------------------------


def render_input() -> None:
    html(ui.step_heading(1, "Add your documents"))
    st.caption(
        "Add everything you were given: the employment contract, the housing agreement, any paper about "
        "deductions from your pay, transport or insurance. You do not need all of them — we will tell you "
        "what seems to be missing."
    )

    # First thing on the page that takes an action, and deliberately above the
    # uploader rather than beside it. Nothing in the analysis needs to know who the
    # worker is: the rules are about clauses, amounts and dates, and a name changes no
    # finding. So the honest instruction is to take the name out, and it has to arrive
    # before the file does.
    st.warning(
        "**Take your personal details out first.** Delete or black out your name, your date of birth, "
        "your BSN, your address, and the name of your employer or agency before you add a document. "
        "This check does not need them — it reads the clauses, the amounts and the dates, and none of "
        "the findings depend on who you are. Anything you leave in is sent onward with the text."
        if st.session_state.provider == "gemini"
        else "**Take your personal details out first.** Delete or black out your name, your date of "
        "birth, your BSN, your address, and the name of your employer or agency before you add a "
        "document. This check does not need them — it reads the clauses, the amounts and the dates, "
        "and none of the findings depend on who you are."
    )

    uploaded = st.file_uploader(
        "Upload files",
        type=["txt", "pdf"],
        accept_multiple_files=True,
        help="Text files and PDFs you can select text in. Photographs are not supported yet.",
    )
    if uploaded:
        for file in uploaded:
            if any(d.filename == file.name for d in st.session_state.documents):
                continue
            try:
                _add_document(s1_ingest.from_upload(file.name, file.getvalue(), len(st.session_state.documents)))
            except s1_ingest.UnsupportedFormat as exc:
                st.warning(str(exc))
            except s1_ingest.IngestError as exc:
                st.error(str(exc))

    with st.expander("Or paste the text of a document"):
        st.caption(
            "Leave out your name, your date of birth, your BSN and your address when you copy the text. "
            "Write `[removed]` in their place if it helps you keep track of the clause numbering."
        )
        pasted = st.text_area("Paste here", height=180, label_visibility="collapsed", key="paste_box")
        name = st.text_input("What is this document?", placeholder="e.g. housing agreement", key="paste_name")
        if st.button("Add this document", use_container_width=True):
            if not pasted.strip():
                st.warning("Nothing to add — the box is empty.")
            else:
                try:
                    _add_document(
                        s1_ingest.from_text(pasted, name.strip() or "pasted text", len(st.session_state.documents))
                    )
                    st.rerun()
                except s1_ingest.IngestError as exc:
                    st.error(str(exc))

    _render_sample_loader()

    if st.session_state.documents:
        st.write("")
        for index, doc in enumerate(st.session_state.documents):
            col_name, col_remove = st.columns([6, 1], vertical_alignment="center")
            col_name.markdown(
                f"**{ui.esc(doc.filename)}**  \n"
                f"<span style='color:#75757F;font-size:0.85rem'>{doc.char_count:,} characters</span>",
                unsafe_allow_html=True,
            )
            if col_remove.button("✕", key=f"remove_{index}", help="Remove this document"):
                st.session_state.documents.pop(index)
                st.rerun()


# Language codes that can appear in a bundle directory name. Anything else is shown
# as-is rather than guessed at.
BUNDLE_LANGUAGES = {"nl": "Dutch", "en": "English"}


def _bundle_label(name: str) -> str:
    """`bundle_e_en_tied_housing` -> `E · English · tied housing`.

    The directory name carries the document language deliberately (see
    samples/expectations.json), and that is worth showing rather than making the
    reader parse underscores: which language the documents are written in is the first
    thing anyone choosing an example needs to know.
    """
    parts = name.split("_")
    if len(parts) < 4 or parts[0] != "bundle" or parts[2] not in BUNDLE_LANGUAGES:
        return name
    return f"{parts[1].upper()} · {BUNDLE_LANGUAGES[parts[2]]} · {' '.join(parts[3:])}"


def _render_sample_loader() -> None:
    """Loads the example bundles. Used for the demo and for working without files."""
    bundles = sorted(p for p in SAMPLES_DIR.glob("*") if p.is_dir()) if SAMPLES_DIR.exists() else []
    if not bundles:
        return
    with st.expander("Try it with an example bundle"):
        st.caption(
            "Invented documents built for testing, in Dutch and in English. No real person's contract "
            "is included in this repository."
        )
        by_label = {_bundle_label(p.name): p.name for p in bundles}
        choice_label = st.selectbox("Example", ["—"] + list(by_label), label_visibility="collapsed")
        choice = by_label.get(choice_label, "—")
        if choice != "—" and st.button("Load this example", use_container_width=True):
            st.session_state.documents = []
            for path in sorted((SAMPLES_DIR / choice).glob("*.txt")):
                _add_document(s1_ingest.from_path(path, len(st.session_state.documents)))
            st.session_state.report = None
            st.rerun()


# --- Output ----------------------------------------------------------------


def render_report(report: Report) -> None:
    if report.gated:
        st.error(f"**We are not confident enough to summarise these documents.**\n\n{report.gate_reason}")
        if report.conflicts:
            st.write("**Where your documents disagree with each other:**")
            for conflict in report.conflicts:
                st.write(f"- {conflict}")
        st.info("The organisations at the bottom of this page can read these documents with you.")

    if report.missing_documents:
        with st.container(border=True):
            st.write("**Documents we did not get**")
            st.caption("Many people do not realise they signed several separate things.")
            for item in report.missing_documents:
                st.write(f"- {item}")

    html(ui.step_heading(3, "What we found"))

    if not report.findings:
        st.info(NO_FINDINGS_MESSAGE)
    else:
        # Before the counts and before the first card. A reader who has already been
        # through three quoted clauses has formed their view; the place to say "a
        # computer read this and it misses things" is ahead of the findings, not in a
        # footer underneath them.
        html(ui.human_callout(TALK_TO_A_HUMAN))

        # Counts first, so the shape of the answer is visible before the detail.
        html(
            ui.glance(
                [
                    (
                        CATEGORY_TILE_LABELS[category],
                        sum(1 for f in report.findings if f.category == category),
                        ui.accent(category),
                    )
                    for category in CATEGORY_LABELS
                ]
            )
        )

        current_category = None
        for finding in report.findings:
            if finding.category != current_category:
                current_category = finding.category
                html(
                    ui.category_heading(
                        CATEGORY_LABELS.get(finding.category, finding.category),
                        CATEGORY_HELP.get(finding.category, ""),
                        finding.category,
                    )
                )
            html(
                ui.finding_card(
                    title=finding.title,
                    what_it_means=finding.what_it_means,
                    severity=finding.severity,
                    category=finding.category,
                    quotes=[(q.doc_id, q.clause_ref, q.quote) for q in finding.quotes],
                    unverified=bool(finding.rule_id and not finding.rule_verified),
                )
            )

    if report.exit_scenario and report.exit_scenario.events:
        st.subheader("If this work ends")
        scenario = report.exit_scenario
        st.write(scenario.trigger_description)
        for event in scenario.events:
            when = (
                "The same day"
                if event.day_offset == 0
                else (f"After {event.day_offset} days" if event.day_offset is not None else "Timing not stated")
            )
            html(ui.timeline_event(when, event.label, event.description))
            for quote in event.quotes:
                st.caption(f"From {quote.doc_id}")
                st.markdown(f"> {quote.quote.strip()}")
        if scenario.outstanding_amount:
            st.warning(f"Still owed when this ends: {scenario.currency} {scenario.outstanding_amount:,.2f}")
        if scenario.caveat:
            st.caption(f"Note: {scenario.caveat}")

    if report.safe_questions:
        st.subheader("Questions that are safe to ask")
        st.caption(
            "Ask these by message rather than in person. The point is not only the answer — it is having "
            "the answer in writing."
        )
        for question in report.safe_questions:
            with st.container(border=True):
                st.markdown(f"**{question.question_in_user_language}**")
                st.code(question.question_in_employer_language, language=None)
                st.caption(f"Why this matters: {question.why_this_question}")
                st.caption(f"If they will not put it in writing: {question.what_a_refusal_means}")

    if report.contacts:
        st.subheader("Who you can talk to")
        st.caption(
            "Confidential advice first. Enforcement bodies are last, and are your choice alone. "
            "If anything was found in your documents, this is the list to use — these organisations "
            "read contracts like yours every week, and a computer does not."
        )
        for contact in report.contacts:
            with st.expander(f"{contact.name} — {contact.kind.replace('_', ' ')}"):
                st.write(contact.what_they_do)
                st.write(f"**Will your employer find out?** {contact.will_employer_find_out}")
                st.write(f"**How long it takes:** {contact.typical_response_time}")
                st.write(f"**Contact:** {contact.contact}")
                if contact.url:
                    st.write(contact.url)

    with st.expander("How sure is this?"):
        st.write(f"**Confidence: {report.overall_confidence:.0%}**")
        if st.session_state.ran_with_provider == "gemini":
            st.write(
                "**Where these documents went:** the text of each one was sent to Google's Gemini API to "
                "be read, and the findings came back from there. Nothing was stored by this tool and "
                "nothing was written to disk."
            )
        ran_with = st.session_state.ran_with_model
        if st.session_state.ran_with_provider == "ollama" and ran_with:
            st.write(
                f"This report was written by `{ran_with}`, running on this computer. A different model "
                "can give a different answer."
            )
        elif ran_with and ran_with != config.MODEL:
            st.write(
                f"This report was written by `{ran_with}` because `{config.MODEL}` was unavailable. "
                "A different model can give a different answer."
            )
        if report.dropped_finding_count:
            st.write(
                f"{report.dropped_finding_count} suggested finding(s) were thrown away because the text they "
                "quoted could not be found in your documents. This is the check that stops the system "
                "inventing clauses."
            )
        if report.unverified_rule_ids:
            st.write(f"Rules used that our team has not yet verified: `{', '.join(report.unverified_rule_ids)}`")
        for note in report.notes:
            st.write(f"- {note}")

    html(ui.disclaimer(DISCLAIMER))

    # Two downloads, and the order is deliberate. The sheet is the one that is any
    # use to the person this tool is for: a page in their language and in Dutch that
    # they can print, keep and hold up in a conversation they cannot otherwise have.
    # The JSON is for a caseworker or for us.
    sheet, raw = st.columns([2, 1])

    with sheet:
        st.download_button(
            "Download the sheet to take with you (Word)",
            data=_takeaway_bytes(report),
            file_name=takeaway.default_filename(report),
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
            type="primary",
        )
        st.caption(
            "Your questions in your language and in Dutch, side by side, with the clauses they come "
            "from quoted exactly as your documents word them."
        )

    with raw:
        st.download_button(
            "Report as JSON",
            data=report.model_dump_json(indent=2),
            file_name="contract-report.json",
            mime="application/json",
            use_container_width=True,
        )



def _takeaway_bytes(report: Report) -> bytes:
    """The .docx as bytes, built in memory so nothing touches disk.

    Streamlit wants the whole file up front for a download button, and this page is
    handling somebody's employment contract: writing a temporary file would be the
    only point in the web app where the documents leave memory.
    """
    buffer = io.BytesIO()
    takeaway.build_document(report).save(buffer)
    return buffer.getvalue()


# --- Running ---------------------------------------------------------------


class _StatusLogHandler(logging.Handler):
    """Feeds the backends' own log lines into the status panel.

    The pipeline reports *what phase* it is in; the LLM clients report *what they
    are waiting on*, at INFO, and that is where a slow run actually spends its time.
    This is the bridge. It runs on the worker thread, so it only appends to a list
    under a lock — drawing stays on the main thread, where Streamlit requires it.
    """

    def __init__(self, record_fn) -> None:
        super().__init__(level=logging.INFO)
        self._record = record_fn

    def emit(self, record: logging.LogRecord) -> None:
        try:
            kind = ctf_progress.WARN if record.levelno >= logging.WARNING else ctf_progress.RESULT
            self._record(kind, record.getMessage())
        except Exception:  # noqa: BLE001 - logging must never break the run
            pass


def _draw(status, entries: list[tuple[str, str]], lock: threading.Lock, drawn: int) -> int:
    """Write any entries that have appeared since the last pass. Returns the new mark.

    Steps are the spine of the transcript and get weight; everything else is
    supporting detail and is deliberately quieter, so that scanning the panel while
    it runs still shows the shape of the run rather than a wall of equal lines.
    """
    with lock:
        pending = entries[drawn:]
        new_mark = len(entries)

    # Not passed through `ui.esc`: that is for the raw-HTML blocks in `ui`, and
    # `st.markdown`/`st.caption` escape HTML themselves. Escaping first would put
    # the entities on the page as text.
    for kind, text in pending:
        if kind == ctf_progress.STEP:
            status.markdown(f"**{text}**")
        elif kind == ctf_progress.WARN:
            status.markdown(f"⚠️ {text}")
        else:
            # Details and results both read as evidence under the current step.
            status.caption(text)
    return new_mark


def _relabel(status, shared: dict, lock: threading.Lock, started: float) -> None:
    """Keep the header honest: current phase, sub-progress, elapsed.

    `expanded=True` has to be passed on every call, not just at creation. The
    docstring on `st.status(...).update()` says an unspecified argument is left
    unchanged; the implementation clears the field instead, and the frontend's
    default for a cleared `expanded` is collapsed. Since this runs several times a
    second, omitting it snaps the panel shut on the first tick and holds it shut for
    the whole run - which is exactly how a transcript of the work ends up invisible
    behind a header that is merely counting seconds.
    """
    with lock:
        step, detail = str(shared["step"]), str(shared["detail"])
    headline = f"{step} · {detail}" if detail else step
    status.update(label=f"{headline}  ·  {time.monotonic() - started:.0f}s", expanded=True)


def run_analysis(language: str, provider: str, model: str | None) -> None:
    """Run the pipeline, showing what it is doing while it does it.

    The threading here is not incidental. Calling `analyse` directly blocks the
    script, and Streamlit only repaints between statements, so the label freezes on
    whatever it said when the step began - during a slow API call, a counter stuck at
    "1s" for a minute, which is exactly the moment people close the tab. Running the
    work beside a polling loop is what makes the elapsed time actually move.

    The worker never touches Streamlit. It records into `shared`, and this loop, on
    the main thread, is the only thing that draws: calling st.* from a thread with no
    script context is unsupported and silently does nothing.
    """
    st.session_state.error = None
    started = time.monotonic()
    status = st.status("Starting…", expanded=True)

    lock = threading.Lock()
    # (kind, text) in the order they happened. The worker appends; the loop below
    # draws. Nothing is ever removed, so the panel is a transcript of the run.
    entries: list[tuple[str, str]] = []
    shared: dict[str, object] = {"step": "Starting", "detail": "", "report": None, "error": None, "model": None}

    def record(kind: str, text: str) -> None:
        with lock:
            entries.append((kind, text))
            if kind == ctf_progress.STEP:
                shared["step"] = text
                # A new step invalidates the old sub-progress, or the headline would
                # claim we are still on document 3 of 4 during the next phase.
                shared["detail"] = ""
            elif kind == ctf_progress.DETAIL:
                shared["detail"] = text

    def on_progress(event: str) -> None:
        record(ctf_progress.kind_of(event), str(event))

    def work() -> None:
        # The backends narrate at INFO - which model, which schema, how many tokens,
        # how long it took. Without a handler none of that reaches the browser, and
        # the panel goes quiet for exactly as long as the slowest call takes.
        handler = _StatusLogHandler(record)
        package_logger = logging.getLogger("contract_trap_finder")
        previous_level = package_logger.level
        package_logger.setLevel(logging.INFO)
        package_logger.addHandler(handler)
        try:
            # Built here rather than left to `analyse`, so afterwards we can tell the
            # reader which model actually answered when the pinned one was unavailable.
            client = build_client(provider, model=model)
            report = analyse(documents, language=language, client=client, progress=on_progress)
            with lock:
                shared["report"] = report
                shared["model"] = client.last_model_used
        except MissingAPIKey as exc:
            with lock:
                shared["error"] = str(exc)
        except Exception as exc:  # noqa: BLE001 - the user needs a message, not a traceback
            with lock:
                shared["error"] = (
                    f"We could not finish reading these documents: {exc}\n\n"
                    "Nothing was saved. You can try again, or contact one of the "
                    "organisations listed in the README."
                )
        finally:
            package_logger.removeHandler(handler)
            package_logger.setLevel(previous_level)

    # Read session state here, on the main thread: it is not available inside the
    # worker, which has no script context of its own.
    documents = list(st.session_state.documents)

    worker = threading.Thread(target=work, daemon=True)
    worker.start()

    drawn = 0
    while worker.is_alive():
        drawn = _draw(status, entries, lock, drawn)
        _relabel(status, shared, lock, started)
        time.sleep(0.3)
    worker.join()
    # Anything recorded between the last poll and the thread ending.
    _draw(status, entries, lock, drawn)

    if shared["error"]:
        status.update(label="Something went wrong", state="error")
        st.session_state.error = shared["error"]
        return

    st.session_state.report = shared["report"]
    st.session_state.ran_with_model = shared["model"]
    st.session_state.ran_with_provider = provider
    status.update(label=f"Done in {time.monotonic() - started:.0f}s", state="complete", expanded=False)


# --- Page ------------------------------------------------------------------


def main() -> None:
    _state()
    html(ui.STYLESHEET)

    html(
        ui.masthead(
            "Contract Trap Finder",
            "See what these documents actually say: what is not allowed, what puts every risk on you, "
            "and where you may be entitled to more than you are being offered.",
        )
    )

    # First control on the page, before any instructions the user may not be able to
    # read. It is not in the sidebar on purpose: see the note on set_page_config.
    language = st.selectbox(
        "Read the report in",
        options=list(config.SUPPORTED_LANGUAGES),
        format_func=lambda code: config.SUPPORTED_LANGUAGES[code],
        index=list(config.SUPPORTED_LANGUAGES).index(config.DEFAULT_LANGUAGE),
    )
    st.caption(
        "This tool is not equally good in all of these languages. Dutch and English are strongest. "
        "See ETHICS.md."
    )

    with st.sidebar:
        st.header("About")
        provider, model = render_engine_picker()
        st.divider()
        # Where the documents go is the one fact in this panel that changes with the
        # choice above, so it is stated in terms of the choice rather than in general.
        if provider == "ollama":
            st.caption(
                "Nothing you upload is stored, and with this engine nothing leaves this computer: the "
                "documents are read by a model running on it and are held in memory for this session only."
            )
        else:
            st.caption(
                "**Your documents are sent to Google.** Nothing you upload is stored by us and nothing is "
                "written to disk, but the full text of every document is sent to Google's Gemini API to be "
                "analysed, and what Google does with it is outside our control and unreviewed by us. "
                "Remove your personal details before uploading, and use the local engine above if the text "
                "must not leave this computer."
            )
        st.divider()
        st.caption("This is information, not legal advice. It does not tell you whether to sign.")

    if provider == "gemini" and not config.get_api_key():
        st.error("No API key set. Copy `.env.example` to `.env` and add your Gemini key.")

    render_input()

    html(ui.step_heading(2, "Read what they say"))

    # Only shown for the local engine. Nobody needs telling that the default sends
    # the documents to a cloud API - that is in the sidebar and in the disclaimer -
    # but somebody who switched to the local one is entitled to see it confirmed on
    # the page they are about to press the button on.
    if provider == "ollama":
        st.caption(
            f"Reading with `{model or config.OLLAMA_MODEL}` on this computer. Nothing is sent over the "
            "internet, and it will be slower than the online version."
        )
    else:
        # The one thing on this page somebody could later say they were not told. It is
        # stated where the button is, not only in the sidebar and the README: a user
        # whose central fear is that information about them travels is entitled to read
        # that it will, immediately before the press that sends it.
        st.warning(
            f"**These documents will be sent to Google.** Pressing the button below sends the text of "
            f"every document you added to Google's Gemini API (`{config.MODEL}`) over the internet, to "
            "be read there. That includes anything identifying you that is still in the text. We do not "
            "store your documents and we do not log their contents, but we cannot make any promise "
            "about what Google does with them — we have not reviewed the data-retention terms of the "
            "API tier we use, and you should assume the text leaves your control. "
            "To keep everything on this computer instead, choose **On this computer (Ollama)** in the "
            "sidebar; that reads the documents with a model running here and sends nothing."
        )

    disabled = not st.session_state.documents
    if st.button(
        "Check these documents",
        type="primary",
        use_container_width=True,
        disabled=disabled,
        help="Add at least one document first." if disabled else None,
    ):
        run_analysis(language, provider, model)

    if st.session_state.error:
        st.error(st.session_state.error)

    if st.session_state.report is not None:
        render_report(st.session_state.report)


if __name__ == "__main__":
    main()
