"""Repo-root pytest conftest: make ``src/`` importable without an
editable install, so ``import mineocclude...`` works from a plain
``pytest`` invocation.
"""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
