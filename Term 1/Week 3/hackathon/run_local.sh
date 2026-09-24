#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Contract Trap Finder - launcher for macOS and Linux.
#
# The counterpart of run_local.bat, and the same idea: create the virtual
# environment if it is missing, install the requirements if they are missing or
# have changed, then start the app. It never activates the environment; it calls
# .venv/bin/python by path, which is what activation exists to arrange.
#
#   chmod +x run_local.sh   (once)
#   ./run_local.sh
# ---------------------------------------------------------------------------

set -euo pipefail
cd "$(dirname "$0")"

VENV=".venv"
VPY="$VENV/bin/python"
STAMP="$VENV/requirements.stamp"

echo
echo "  Contract Trap Finder"
echo "  --------------------"
echo

# --- 1. The virtual environment --------------------------------------------

if [ ! -x "$VPY" ]; then
    if command -v python3 >/dev/null 2>&1; then
        echo "  First run: creating the virtual environment in $VENV"
        echo
        python3 -m venv "$VENV"
    else
        echo "  Python 3 was not found on this computer."
        echo "  Install Python 3.11 or newer, then run this script again."
        echo
        exit 1
    fi
fi

# --- 2. Dependencies --------------------------------------------------------
# The stamp holds the modification time of requirements.txt as it was when pip
# last succeeded, so a normal start does no work and a changed requirements.txt
# triggers a reinstall.

req_time="$(ls -l requirements.txt)"
old_time="$(cat "$STAMP" 2>/dev/null || true)"

if [ "$req_time" != "$old_time" ]; then
    echo "  Installing dependencies. This takes a few minutes the first time."
    echo
    "$VPY" -m pip install --upgrade pip --quiet
    "$VPY" -m pip install -r requirements.txt
    # Written only on success - set -e means a failed install never reaches this
    # line, so the next start retries rather than silently skipping it.
    printf '%s' "$req_time" > "$STAMP"
    echo
fi

# --- 3. Configuration -------------------------------------------------------
# Absence of .env is not an error: without a key the app still starts, and the
# sidebar's local mode (Ollama) needs no key at all.

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp ".env.example" ".env"
    echo "  Created .env from .env.example."
    echo
    echo "  For the hosted mode, open .env and set GEMINI_API_KEY."
    echo "  Without a key, choose \"On this computer (Ollama)\" in the sidebar,"
    echo "  which needs no key and sends nothing over the internet."
    echo
fi

# --- 4. Go ------------------------------------------------------------------

echo "  Starting. Your browser opens at http://localhost:8501"
echo "  Press Ctrl+C in this window to stop the app."
echo

exec "$VPY" -m streamlit run app.py
