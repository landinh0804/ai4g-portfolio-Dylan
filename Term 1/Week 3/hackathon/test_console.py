"""Terminal presentation.

The point of these is that the plain path stays correct. Colour is an accent; if a
run is piped to a file, fed to a caseworker's script, or captured in CI, the text
must still say everything the coloured version says.
"""

from __future__ import annotations

import pytest

from contract_trap_finder import console


class FakeStream:
    """A writable stream that can claim to be a terminal with a given encoding.

    Not a StringIO subclass: `encoding` is read-only on the real thing, and the
    cp1252 case is exactly what these tests need to reproduce.
    """

    def __init__(self, tty: bool = False, encoding: str = "utf-8") -> None:
        self._parts: list[str] = []
        self._tty = tty
        self.encoding = encoding

    def write(self, text: str) -> int:
        self._parts.append(text)
        return len(text)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return self._tty

    def getvalue(self) -> str:
        return "".join(self._parts)


# --- capability detection --------------------------------------------------


def test_no_color_env_var_is_honoured(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    assert not console.supports_colour(FakeStream(tty=True))


def test_a_redirected_stream_is_never_coloured(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    assert not console.supports_colour(FakeStream(tty=False))


def test_a_cp1252_stream_does_not_get_box_drawing():
    assert not console.supports_unicode(FakeStream(encoding="cp1252"))
    assert console.supports_unicode(FakeStream(encoding="utf-8"))


# --- theme -----------------------------------------------------------------


def test_the_plain_theme_returns_text_untouched():
    t = console.Theme(colour=False, unicode_ok=False)
    assert t.critical("Against the law") == "Against the law"
    assert t.heading("WHAT WE FOUND") == "WHAT WE FOUND"
    assert "\033" not in t.rule(10)


def test_the_colour_theme_wraps_but_does_not_alter_the_text():
    t = console.Theme(colour=True, unicode_ok=True)
    painted = t.critical("Against the law")
    assert "Against the law" in painted
    assert painted.startswith("\033")
    assert painted.endswith("\033[0m")


def test_ascii_fallback_for_marks_and_rules():
    plain = console.Theme(colour=False, unicode_ok=False)
    fancy = console.Theme(colour=False, unicode_ok=True)
    assert plain.tick == "+" and fancy.tick == "✓"
    assert set(plain.rule(5)) == {"-"}


# --- progress --------------------------------------------------------------


def test_a_non_terminal_gets_one_plain_line_per_step():
    stream = FakeStream(tty=False)
    reporter = console.ProgressReporter(stream, theme=console.Theme(False, False))
    with reporter:
        reporter("Reading 3 document(s)")
        reporter("Checking against the legal rules")

    output = stream.getvalue()
    assert "Reading 3 document(s)" in output
    assert "Checking against the legal rules" in output
    # No cursor games in something that is not a terminal.
    assert "\r" not in output
    assert "\033" not in output


def test_every_step_is_marked_done_with_its_own_timing():
    stream = FakeStream(tty=False)
    reporter = console.ProgressReporter(stream, theme=console.Theme(False, False))
    with reporter:
        reporter("step one")
        reporter("step two")

    output = stream.getvalue()
    assert output.count("+") >= 2  # ascii tick for each completed step
    assert "Finished in" in output


def test_a_failed_run_is_not_reported_as_finished():
    stream = FakeStream(tty=False)
    reporter = console.ProgressReporter(stream, theme=console.Theme(False, False))
    with pytest.raises(RuntimeError):
        with reporter:
            reporter("step one")
            raise RuntimeError("boom")

    output = stream.getvalue()
    assert "Stopped in" in output
    assert "Finished" not in output


def test_notes_appear_without_swallowing_the_step():
    stream = FakeStream(tty=False)
    reporter = console.ProgressReporter(stream, theme=console.Theme(False, False))
    with reporter:
        reporter("Reading documents")
        reporter.note("gemini-3.8-flash is not answering. Falling back.")

    output = stream.getvalue()
    assert "Falling back" in output
    assert "Reading documents" in output


def test_quiet_mode_prints_nothing_at_all():
    stream = FakeStream(tty=False)
    reporter = console.ProgressReporter(stream, theme=console.Theme(False, False), enabled=False)
    with reporter:
        reporter("Reading documents")
        reporter.note("a warning nobody asked for")

    assert stream.getvalue() == ""


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(0.4, "0.4s"), (12.35, "12.3s"), (60, "1m00s"), (67.2, "1m07s"), (610, "10m10s")],
)
def test_durations_read_naturally(seconds, expected):
    assert console._duration(seconds) == expected
