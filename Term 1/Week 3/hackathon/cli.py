"""Root-level shim so the CLI runs without installing the package first.

    py cli.py samples/bundle_a_nl_tied_housing/*.txt --verbose

Equivalent to `py -m contract_trap_finder.cli` after `pip install -e .`.
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from contract_trap_finder._bootstrap import require_dependencies  # noqa: E402

require_dependencies()

from contract_trap_finder.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
