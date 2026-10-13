"""Streamlit Community Cloud entrypoint for the Bahn-Puls dashboard.

Community Cloud splits the requirements path on spaces, so it can't install
dependencies for an app inside "Term 1/Week 6/...". This launcher sits in a
space-free folder next to a dashboard-only requirements.txt and runs the real
dashboard.
"""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parents[2] / "Term 1" / "Week 6" / "hackathon" / "dashboard.py"),
               run_name="__main__")
