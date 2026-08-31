"""Rebind the validation report's artifact hash table to the files on disk.

Every row is recomputed by hashing the file, never copied forward. Run last, after
every other authority artifact is final.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "docs" / "experiment_iii" / "final_authorities"
REPORT = ROOT / "AUTHORITY_VALIDATION_REPORT.md"

ROW = re.compile(r"^\| `([0-9a-f]{64})` \| ([\d,]+) \| `([^`]+)` \|$")


def main() -> int:
    lines = REPORT.read_text(encoding="utf-8").splitlines()
    changed = 0
    for position, line in enumerate(lines):
        match = ROW.match(line)
        if not match:
            continue
        name = match.group(3)
        target = ROOT / name
        if not target.is_file():
            continue
        payload = target.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        replacement = f"| `{digest}` | {len(payload):,} | `{name}` |"
        if replacement != line:
            lines[position] = replacement
            changed += 1
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"hash table rows rebound: {changed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
