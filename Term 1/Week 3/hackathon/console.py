"""Terminal presentation: colour, live progress, and the shape of the printed report.

Separate from `cli.py` so the argument handling stays readable, and so the "is this
thing still running?" problem is solved in one place.

That problem is real rather than cosmetic. A single run makes several LLM calls, and
when the pinned model is unavailable the client works down its fallback list, which
can take the better part of a minute before the first word is printed. A terminal
that shows nothing for that long looks broken, and the natural response is to kill it
and start again, which costs another wait and another API call.

Two rules shape everything below:

* Never require colour or Unicode to understand the output. Colour is an accent on
  text that already reads correctly in a pipe, a log file or a CI job.
* Never let decoration outrank meaning. This tool tells people whether a contract
  they are about to sign is legal, so severity is always spelled out in words and
  colour only ever agrees with the words.
"""

from __future__ import annotations

import itertools
import os
import sys
import threading
import time
from types import TracebackType
from typing import IO, TextIO

from . import progress

# --- Capability detection --------------------------------------------------


def supports_colour(stream: IO[str] | None = None) -> bool:
    """True if it is safe to write ANSI escapes to `stream`.

    Honours the NO_COLOR convention and FORCE_COLOR, and refuses to colour a
    redirected stream, where the escapes would land in the file as literal noise.
    """
    stream = stream or sys.stderr

    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    if os.environ.get("TERM") == "dumb":
        return False
    if not hasattr(stream, "isatty") or not stream.isatty():
        return False
    if sys.platform == "win32":
        return _enable_windows_vt()
    return True


def _enable_windows_vt() -> bool:
    """Turn on ANSI handling in the Windows console.

    Windows Terminal does this already; the older conhost.exe does not, and without
    it every escape sequence is printed literally as a stray bracket code.
    """
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        # -11 is STD_OUTPUT_HANDLE, -12 is STD_ERROR_HANDLE.
        for handle_id in (-11, -12):
            handle = kernel32.GetStdHandle(handle_id)
            mode = ctypes.c_ulong()
            if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                return False
            # 0x0004 is ENABLE_VIRTUAL_TERMINAL_PROCESSING.
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        return True
    except Exception:  # noqa: BLE001 - any failure here simply means no colour
        return False


def supports_unicode(stream: IO[str] | None = None) -> bool:
    """True if the stream can encode the box-drawing and spinner characters."""
    stream = stream or sys.stderr
    encoding = getattr(stream, "encoding", None) or ""
    try:
        "─┃⠋✓".encode(encoding or "ascii")
        return True
    except (UnicodeEncodeError, LookupError):
        return False


# --- Styling ---------------------------------------------------------------

ESC = "\033"

_CODES = {
    "reset": ESC + "[0m",
    "bold": ESC + "[1m",
    "dim": ESC + "[2m",
    "italic": ESC + "[3m",
    "red": ESC + "[31m",
    "green": ESC + "[32m",
    "yellow": ESC + "[33m",
    "blue": ESC + "[34m",
    "magenta": ESC + "[35m",
    "cyan": ESC + "[36m",
    "grey": ESC + "[90m",
    "bright_red": ESC + "[91m",
    "bright_yellow": ESC + "[93m",
}


class Theme:
    """Applies styles, or does nothing at all when colour is unavailable.

    The no-colour case is the same object with the same methods, so calling code
    never branches on it and the plain path cannot drift out of sync with the
    coloured one.
    """

    def __init__(self, colour: bool, unicode_ok: bool) -> None:
        self.colour = colour
        self.unicode = unicode_ok

    def __call__(self, text: str, *styles: str) -> str:
        if not self.colour or not styles:
            return text
        prefix = "".join(_CODES.get(s, "") for s in styles)
        return f"{prefix}{text}{_CODES['reset']}" if prefix else text

    # Named roles rather than colours at the call site, so what a colour means can
    # be changed in one place.
    def heading(self, text: str) -> str:
        return self(text, "bold", "cyan")

    def critical(self, text: str) -> str:
        return self(text, "bold", "bright_red")

    def warn(self, text: str) -> str:
        return self(text, "yellow")

    def ok(self, text: str) -> str:
        return self(text, "green")

    def muted(self, text: str) -> str:
        return self(text, "grey")

    def quote(self, text: str) -> str:
        return self(text, "italic", "grey")

    def rule(self, width: int = 72, heavy: bool = False) -> str:
        if self.unicode:
            char = "━" if heavy else "─"
        else:
            char = "=" if heavy else "-"
        return self.muted(char * width)

    @property
    def tick(self) -> str:
        return "✓" if self.unicode else "+"

    @property
    def cross(self) -> str:
        return "✗" if self.unicode else "x"

    @property
    def bullet(self) -> str:
        return "•" if self.unicode else "-"


def theme_for(stream: IO[str] | None = None) -> Theme:
    stream = stream or sys.stderr
    return Theme(colour=supports_colour(stream), unicode_ok=supports_unicode(stream))


# --- Live progress ---------------------------------------------------------

_SPINNER_UNICODE = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_SPINNER_ASCII = "|/-\\"


def _frames(unicode_ok: bool):
    return itertools.cycle(_SPINNER_UNICODE if unicode_ok else _SPINNER_ASCII)


def _duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, rest = divmod(int(seconds), 60)
    return f"{minutes}m{rest:02d}s"


class ProgressReporter:
    """A live one-line status with an elapsed clock, above a log of finished steps.

    Writes to stderr, so `--json` and `-o` keep producing clean, pipeable output on
    stdout.

    On a terminal this animates in place. Anywhere else - a pipe, a CI log, a file -
    it degrades to one plain line per step, because a spinner rewritten a hundred
    times is unreadable in a log, and an animation nobody watches is just noise.
    """

    def __init__(
        self,
        stream: TextIO | None = None,
        theme: Theme | None = None,
        enabled: bool = True,
    ) -> None:
        self.stream = stream or sys.stderr
        self.theme = theme or theme_for(self.stream)
        self.enabled = enabled
        self.animate = enabled and bool(getattr(self.stream, "isatty", lambda: False)())
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._message = ""
        self._detail = ""
        self._started = 0.0
        self._step_started = 0.0
        self._step = 0
        self._painted = False

    # -- lifecycle
    def __enter__(self) -> "ProgressReporter":
        self._started = self._step_started = time.monotonic()
        if self.animate:
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close(success=exc_type is None)

    def close(self, success: bool = True) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        with self._lock:
            self._clear()
            if self.enabled and self._step:
                # Close off the step that was still running when we stopped.
                elapsed = time.monotonic() - self._step_started
                mark = self.theme.ok(self.theme.tick) if success else self.theme.critical(self.theme.cross)
                self._raw(f"  {mark} {self.theme.muted(self._message)} {self.theme.muted('(' + _duration(elapsed) + ')')}\n")
                total = time.monotonic() - self._started
                verb = "Finished" if success else "Stopped"
                self._raw(self.theme.muted(f"  {verb} in {_duration(total)}\n"))
                self._step = 0

    # -- the ProgressCallback the pipeline expects
    def __call__(self, message: str) -> None:
        """Render one progress event.

        The pipeline sends `ProgressEvent`s, which are strings carrying a `kind`.
        Anything that sends a bare string - an older caller, a test - is treated as
        a step, which is what the whole channel used to be.
        """
        kind = getattr(message, "kind", progress.STEP)
        if kind == progress.DETAIL:
            self.detail(str(message))
        elif kind == progress.RESULT:
            self.note(f"{self.theme.bullet} {message}", style="muted")
        elif kind == progress.WARN:
            self.note(f"! {message}", style="warn")
        else:
            self.begin_step(str(message))

    def begin_step(self, message: str) -> None:
        """Mark the current step done and start a new one."""
        with self._lock:
            now = time.monotonic()
            self._clear()
            if self._step and self.enabled:
                done = self.theme.ok(self.theme.tick)
                took = self.theme.muted("(" + _duration(now - self._step_started) + ")")
                # The step's own name, not `_headline()`: the detail names whatever
                # it happened to be doing last, which as a *completed* line reads as
                # if the step were only about that one document.
                self._raw(f"  {done} {self.theme.muted(self._message)} {took}\n")
            self._step += 1
            self._message = message.rstrip("…").rstrip(".").rstrip()
            self._detail = ""
            self._step_started = now
            if not self.enabled:
                return
            if self.animate:
                self._paint(next(_frames(self.theme.unicode)))
            else:
                self._raw(f"  {self.theme.muted('...')} {self._message}\n")

    def detail(self, text: str) -> None:
        """Refine the live line without ending the step or resetting its clock.

        This is what makes a long step legible: "Reading documents" sits there for a
        minute and says nothing, while "Reading documents - 2 of 4, huisvesting.txt"
        tells the reader both that it is progressing and where it would be stuck if
        it were not.
        """
        with self._lock:
            self._detail = text.rstrip("…").rstrip(".").rstrip()
            if not self.enabled:
                return
            if self.animate:
                self._clear()
                self._paint(next(_frames(self.theme.unicode)))
            else:
                # No animation to refine, so it becomes its own indented line. In a
                # log file that is more useful than a line rewritten in place.
                self._raw(f"      {self.theme.muted(self._detail)}\n")

    def _headline(self) -> str:
        """The step, plus whatever detail it last reported."""
        if self._detail:
            return f"{self._message} {self.theme.bullet} {self._detail}"
        return self._message

    def note(self, message: str, style: str = "warn") -> None:
        """Print a line above the live status without disturbing it.

        This is how a model failover or a dropped finding reaches the user while a
        step is still spinning.
        """
        if not self.enabled:
            return
        with self._lock:
            self._clear()
            painter = {"warn": self.theme.warn, "muted": self.theme.muted}.get(style, self.theme.muted)
            self._raw(f"  {painter(message)}\n")
            if self.animate and self._message:
                self._paint(next(_frames(self.theme.unicode)))

    # -- internals
    def _spin(self) -> None:
        frames = _frames(self.theme.unicode)
        while not self._stop.is_set():
            with self._lock:
                if self._message:
                    self._paint(next(frames))
            self._stop.wait(0.12)

    def _paint(self, frame: str) -> None:
        elapsed = _duration(time.monotonic() - self._step_started)
        line = f"  {self.theme(frame, 'cyan')} {self._headline()} {self.theme.muted('(' + elapsed + ')')}"
        if self.theme.colour:
            self._raw("\r" + line + ESC + "[K")
        else:
            self._raw("\r" + line + "   ")
        self._painted = True

    def _clear(self) -> None:
        if not self._painted:
            return
        if self.theme.colour:
            self._raw("\r" + ESC + "[K")
        else:
            self._raw("\r" + " " * 78 + "\r")
        self._painted = False

    def _raw(self, text: str) -> None:
        try:
            self.stream.write(text)
            self.stream.flush()
        except (ValueError, OSError):  # pragma: no cover - stream closed under us
            pass
