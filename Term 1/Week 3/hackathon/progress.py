"""What the pipeline tells the outside world while it is running.

The pipeline used to report five sentences - one per step - and nothing else. That
is close to useless while it runs, because the five sentences are not where the time
goes: one bundle of four documents makes six or seven model calls, each taking
anywhere from two seconds to two minutes, and all of them happen inside those five
sentences. What the user saw was a clock counting up with no idea whether the tool
was working, retrying, or hung.

So there are four kinds of message rather than one:

* `step`    - a new phase of work. Replaces the headline.
* `detail`  - progress *inside* the current phase, e.g. document 2 of 4. Refines the
              headline without ending the step or resetting its clock.
* `result`  - what the phase actually produced, in numbers. This is the one that
              turns "Checking against the legal rules" into "14 rules checked, 5
              fired", which is the difference between watching a spinner and being
              able to tell that something went wrong.
* `warn`    - something the reader should see now rather than in the report.

`ProgressEvent` is a `str` subclass on purpose. Every existing consumer - the tests,
`scripts/demo_offline.py`, anything that passes a bare `print`-like callable - keeps
working unchanged, because an event *is* the message. A front-end that wants to do
better reads `.kind` and renders accordingly. Introducing a new type here would have
meant changing every caller to unpack it, for no gain to the ones that do not care.
"""

from __future__ import annotations

from typing import Callable

# The callback the pipeline is handed. It receives `ProgressEvent`s, which are
# strings, so the old signature is still an accurate description of it.
ProgressCallback = Callable[[str], None]

STEP = "step"
DETAIL = "detail"
RESULT = "result"
WARN = "warn"


class ProgressEvent(str):
    """A progress message that is still, for all other purposes, a plain string."""

    kind: str

    def __new__(cls, text: str, kind: str = STEP) -> "ProgressEvent":
        event = super().__new__(cls, text)
        event.kind = kind
        return event

    def __repr__(self) -> str:  # pragma: no cover - debugging convenience
        return f"ProgressEvent({str(self)!r}, kind={self.kind!r})"


def _noop(_event: str) -> None:
    pass


class Progress:
    """The handle the pipeline and its steps report through.

    Wrapping the raw callback rather than calling it directly keeps the four kinds
    from being four conventions that each call site has to remember, and gives one
    place to add counting or throttling later.
    """

    def __init__(self, callback: ProgressCallback | None = None) -> None:
        self._callback = callback or _noop

    def _emit(self, text: str, kind: str) -> None:
        try:
            self._callback(ProgressEvent(text, kind))
        except Exception:  # noqa: BLE001 - narration must never break the analysis
            pass

    def step(self, text: str) -> None:
        """Begin a new phase."""
        self._emit(text, STEP)

    def detail(self, text: str) -> None:
        """Say where we are inside the current phase, without ending it."""
        self._emit(text, DETAIL)

    def result(self, text: str) -> None:
        """Say what the phase produced, in numbers wherever there are numbers."""
        self._emit(text, RESULT)

    def warn(self, text: str) -> None:
        """Something the reader should see now."""
        self._emit(text, WARN)


def kind_of(event: str) -> str:
    """The kind of an event, for a front-end handed a plain string by an old caller."""
    return getattr(event, "kind", STEP)


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    """`3 documents`, `1 document`. Used often enough here to be worth having."""
    word = singular if count == 1 else (plural_form or f"{singular}s")
    return f"{count:,} {word}"
