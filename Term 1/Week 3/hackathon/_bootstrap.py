"""Pre-flight dependency check.

Imports nothing outside the standard library, so it can run before the packages it
is checking for exist. The failure it catches is running an entry point with the
system Python instead of the project's virtual environment, which otherwise shows up
as `ModuleNotFoundError: No module named 'dotenv'` four frames deep in an import
chain — accurate, and useless to anyone who has not seen it before.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

# Import name -> the name you install it under, where they differ.
REQUIRED = {
    "dotenv": "python-dotenv",
    "pydantic": "pydantic",
    "google.genai": "google-genai",
    "pypdf": "pypdf",
}


def _missing() -> list[str]:
    missing = []
    for module, package in REQUIRED.items():
        try:
            if importlib.util.find_spec(module) is None:
                missing.append(package)
        except (ImportError, ValueError):
            missing.append(package)
    return missing


def _in_virtualenv() -> bool:
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix) or bool(os.environ.get("VIRTUAL_ENV"))


def require_dependencies() -> None:
    """Exit with an actionable message if the dependencies are not importable."""
    missing = _missing()
    if not missing:
        return

    project_root = Path(__file__).resolve().parents[2]
    venv = project_root / ".venv"
    windows = os.name == "nt"

    # Built outside the f-strings below: backslashes inside f-string expressions are
    # a syntax error before Python 3.12, and this file must parse on 3.11.
    activate = ".venv\\Scripts\\Activate.ps1" if windows else "source .venv/bin/activate"
    venv_python = ".venv\\Scripts\\python.exe" if windows else ".venv/bin/python"
    new_venv = "py -m venv .venv" if windows else "python3 -m venv .venv"

    lines = [
        "",
        "Contract Trap Finder cannot start: missing " + ", ".join(missing) + ".",
        "",
        f"You are running: {sys.executable}",
    ]

    if venv.exists() and not _in_virtualenv():
        lines += [
            "",
            "This project has a virtual environment at .venv, but you are not using it.",
            "The dependencies are installed there, not in your system Python.",
            "",
            "Activate it first:",
            f"    {activate}",
            "",
            "then run the same command again with 'python' instead of 'py'.",
            "",
            "Or run it directly without activating:",
            f"    {venv_python} <script>",
        ]
    elif not venv.exists():
        lines += [
            "",
            "There is no virtual environment yet. Create one and install the dependencies:",
            "",
            f"    {new_venv}",
            f"    {activate}",
            "    pip install -r requirements.txt",
        ]
    else:
        lines += [
            "",
            "Install the dependencies into this environment:",
            "",
            "    pip install -r requirements.txt",
        ]

    lines.append("")
    print("\n".join(lines), file=sys.stderr)
    raise SystemExit(1)
