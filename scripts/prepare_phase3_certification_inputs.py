"""Prepare or validate external Person A Phase 3 certification inputs."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.models.phase3_certification_inputs import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
