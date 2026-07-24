"""Run the AWS-only Person A Phase 2.8-2.9 hook/repeatability command."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.models.phase2_aws import teacher_forced_main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(teacher_forced_main())
