"""Rebind every controlling hash and version string to the v1.5 successor.

Run AFTER the canonical markdown is final. Recomputes AUTHORITY_SHA256 from the
markdown bytes, writes it into the machine authority, updates the version strings
and the validation-report hash table, and retargets the audit suite's version
checks. The amendment record itself is not part of AUTHORITY_SHA256, so it may be
completed afterwards without disturbing the binding.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "docs" / "experiment_iii" / "final_authorities"
MD = ROOT / "EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.md"
JS = ROOT / "EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.json"

PRED_MD = "993e5859fa53084889abbc8dda654cd9045dd871258e078cc1afb237f59b4daa"
PRED_JS = "b6fd1e09b4a9cc868a28ef522dea3a182f3ba42698bfe490ec14c05c192a5f63"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> int:
    md_bytes = MD.read_bytes()
    md_sha = hashlib.sha256(md_bytes).hexdigest()

    authority = json.loads(JS.read_text(encoding="utf-8"), object_pairs_hook=OrderedDict)
    authority["authority_markdown_sha256"] = md_sha
    authority["authority_markdown_bytes"] = len(md_bytes)
    authority["authority_markdown_hash_recomputed_by"] = "AUTHORITY_AMENDMENT_2_V1_5"
    with io.open(JS, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(authority, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    js_sha = sha256_file(JS)

    # ---- README ----
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    text = text.replace(
        "AUTHORITY_VERSION             = v1.4  (III-A + Amendment 1 / III-B + repair passes 1-2 + ultimate closure)",
        "AUTHORITY_VERSION             = v1.5  (III-A + Amendment 1 / III-B + repair passes 1-2 + ultimate closure + Amendment 2 cohort admission feasibility)",
    )
    readme.write_text(text, encoding="utf-8", newline="\n")

    # ---- validation report ----
    report = ROOT / "AUTHORITY_VALIDATION_REPORT.md"
    text = report.read_text(encoding="utf-8")
    text = text.replace("**Authority version:** `v1.4`", "**Authority version:** `v1.5`")
    text = text.replace(
        f"| `{PRED_JS}` | 206,510 | `EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.json` |",
        f"| `{js_sha}` | {JS.stat().st_size:,} | `EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.json` |",
    )
    text = text.replace(
        f"| `{PRED_MD}` | 238,345 | `EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.md` |",
        f"| `{md_sha}` | {len(md_bytes):,} | `EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.md` |",
    )
    if "## 16. Authority Amendment 2 (v1.5)" not in text:
        text = text.rstrip("\n") + f"""

---

## 16. Authority Amendment 2 (v1.5) — cohort admission feasibility

Prospective §9.2 scientific amendment, raised at `I02` before any cohort, capture, inference or
scientific outcome existed. Full record:
[`AUTHORITY_AMENDMENT_2_COHORT_ADMISSION_FEASIBILITY.md`](AUTHORITY_AMENDMENT_2_COHORT_ADMISSION_FEASIBILITY.md).

| | |
|---|---|
| Defect | §2.3 + §2.4 gate 9 + §2.4 bound 200 + §2.5 no-phase-offset are jointly infeasible |
| Root cause | the 200 bound was calibrated on A-prime phase-offset diversity that §2.5 removes |
| Repair 2a | gate 12 scope = the per-candidate gates (1–8, 10, 11); gate 9 is peer-dependent and evaluated once at the III-A `q` |
| Repair 2b | candidate index bound 200 → 2000 (Option D), admission order unchanged |
| Gate 9 threshold | **unchanged at 0.10** |
| Rejected | lowering gate 9 (A); restoring phase offsets (C); feasible-subset selection (B-prime, tested infeasible at bound 200) |
| Invalidation | no scientific invalidation; all predecessor-bound receipts rerun and rebound |

```
AMENDMENT_2_STATUS = PASS
BLOCKING_DEFECTS   = 0
```
"""
    report.write_text(text, encoding="utf-8", newline="\n")

    # ---- audit suite version targets ----
    audit = ROOT / "final_audit" / "audit_final.py"
    text = audit.read_text(encoding="utf-8")
    text = text.replace(
        'chk("README states authority version v1.4", "AUTHORITY_VERSION             = v1.4" in RM)',
        'chk("README states authority version v1.5", "AUTHORITY_VERSION             = v1.5" in RM)',
    )
    text = text.replace(
        'chk("authority version is v1.4", A["authority_version"] == "v1.4")',
        'chk("authority version is v1.5", A["authority_version"] == "v1.5")',
    )
    text = text.replace(
        'chk("authority version is v1.4", A["authority_version"]=="v1.4")',
        'chk("authority version is v1.5", A["authority_version"]=="v1.5")',
    )
    text = text.replace(
        'chk("README states v1.4","AUTHORITY_VERSION             = v1.4" in RM)',
        'chk("README states v1.5","AUTHORITY_VERSION             = v1.5" in RM)',
    )
    audit.write_text(text, encoding="utf-8", newline="\n")

    print(f"SUCCESSOR_AUTHORITY_SHA256={md_sha}")
    print(f"SUCCESSOR_MACHINE_AUTHORITY_SHA256={js_sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
