"""Shared test fixtures."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Ensure the project root is importable when pytest is invoked from elsewhere.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Isolated SQLite path BEFORE any project module imports config, so the test
# suite never touches the developer's real data/trustloop.db.
_DB_DIR = tempfile.mkdtemp(prefix="trustloop_tests_")
os.environ.setdefault("TRUSTLOOP_DB_PATH", os.path.join(_DB_DIR, "test.db"))
