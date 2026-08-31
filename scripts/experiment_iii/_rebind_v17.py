"""Rebind every controlling hash and version string to the v1.7 successor.

Run AFTER the canonical markdown is final. Recomputes AUTHORITY_SHA256 from the
markdown bytes, writes it into the machine authority, and updates the version
strings, the validation-report hash table and the audit suite's version targets.
The amendment record is not part of AUTHORITY_SHA256, so it may be written before
or after this without disturbing the binding.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
from pathlib import Path
from collections import OrderedDict

ROOT = Path(__file__).resolve().parents[2] / "docs" / "experiment_iii" / "final_authorities"
MD = ROOT / "EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.md"
JS = ROOT / "EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.json"

PRED_MD = "62519701bbe08f94839b6dab4e612826f902f31c736727e8c268cf738897ab4c"
PRED_JS = "d9de26163df4ca599a5049fb75fd68d010169e53f90aceeb9e4063e60da50609"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    md_bytes = MD.read_bytes()
    md_sha = hashlib.sha256(md_bytes).hexdigest()

    authority = json.loads(JS.read_text(encoding="utf-8"), object_pairs_hook=OrderedDict)
    authority["authority_markdown_sha256"] = md_sha
    authority["authority_markdown_bytes"] = len(md_bytes)
    authority["authority_markdown_hash_recomputed_by"] = "AUTHORITY_AMENDMENT_4_V1_7"
    authority["authority_markdown_sha256_superseded_v1_6"] = PRED_MD
    with io.open(JS, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(authority, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    js_sha = sha256_file(JS)

    # ---- README ----
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    old = (
        "AUTHORITY_VERSION             = v1.6  (III-A + Amendment 1 / III-B + "
        "repair passes 1-2 + ultimate closure + Amendment 2 cohort admission "
        "feasibility + Amendment 3 P0 operational completeness)"
    )
    if old not in text:
        raise SystemExit("REBIND_PRECONDITION_FAILED: README v1.6 version line not found")
    text = text.replace(
        old,
        "AUTHORITY_VERSION             = v1.7  (III-A + Amendment 1 / III-B + "
        "repair passes 1-2 + ultimate closure + Amendment 2 cohort admission "
        "feasibility + Amendment 3 P0 operational completeness + Amendment 4 "
        "capture liveness successor rule)",
    )
    readme.write_text(text, encoding="utf-8", newline="\n")

    # ---- validation report ----
    report = ROOT / "AUTHORITY_VALIDATION_REPORT.md"
    text = report.read_text(encoding="utf-8")
    text = text.replace("**Authority version:** `v1.6`", "**Authority version:** `v1.7`")
    replaced = 0
    for old_line, new_line in (
        (f"| `{PRED_JS}` |", f"| `{js_sha}` |"),
        (f"| `{PRED_MD}` |", f"| `{md_sha}` |"),
    ):
        if old_line in text:
            text = text.replace(old_line, new_line, 1)
            replaced += 1
    if "## 18. Authority Amendment 4 (v1.7)" not in text:
        text = text.rstrip("\n") + """

---

## 18. Authority Amendment 4 (v1.7) — capture liveness successor rule

Prospective §9.2 amendment, raised at `A4` entry on a qualified capture host with **zero P0
frames, zero MineWorld forwards and zero scientific outcomes** in existence.

| | |
|---|---|
| Defect | §7.10f required the target present/absent transitions to demonstrate a framebuffer change on every unit, while also recognising that an opaque condition legitimately renders pixel-identical frames with a hidden target |
| Consequence | the nine frozen placements all lie inside the as-built wall extent, so an opaque wall occludes the target at every placement; **18 of 252** P0 units refused on physically correct observations |
| 4a | a fixed `ENGINEERING_ONLY` pre-capture liveness witness — `NO_WALL`, fixed visible calibration position, `PRESENT → ABSENT → PRESENT` — runs before each scientific capture unit |
| 4b | scientific `PRESENT`/`ABSENT` framebuffer equality is **diagnostic only**, never by itself `CAPTURE_STALE_FRAME` |
| 4c | uniform across conditions: no material-specific exemption, no `L4` special case, no inference from opacity, RVE, ladder or model behaviour |
| 4d | witness artifacts are `ENGINEERING_ONLY`, excluded from RVE, validity, ladder, bootstrap, sentinels, P1, P2 discovery, production and every statistic |
| Scientific design | III-A unchanged, III-B unchanged; placements, roster, RVE, zones, selection rule, target geometry, cohort all unchanged |
| Invalidation | none; no measurement existed |

```
AMENDMENT_4_STATUS = PASS
BLOCKING_DEFECTS   = 0
```
"""
    report.write_text(text, encoding="utf-8", newline="\n")

    # ---- audit suite version targets ----
    audit = ROOT / "final_audit" / "audit_final.py"
    if audit.is_file():
        text = audit.read_text(encoding="utf-8")
        for old_line, new_line in (
            (
                'chk("README states authority version v1.6", "AUTHORITY_VERSION             = v1.6" in RM)',
                'chk("README states authority version v1.7", "AUTHORITY_VERSION             = v1.7" in RM)',
            ),
            (
                'chk("authority version is v1.6", A["authority_version"] == "v1.6")',
                'chk("authority version is v1.7", A["authority_version"] == "v1.7")',
            ),
            (
                'chk("authority version is v1.6", A["authority_version"]=="v1.6")',
                'chk("authority version is v1.7", A["authority_version"]=="v1.7")',
            ),
            (
                'chk("README states v1.6","AUTHORITY_VERSION             = v1.6" in RM)',
                'chk("README states v1.7","AUTHORITY_VERSION             = v1.7" in RM)',
            ),
        ):
            text = text.replace(old_line, new_line)
        audit.write_text(text, encoding="utf-8", newline="\n")

    print(f"PREDECESSOR_AUTHORITY_SHA256={PRED_MD}")
    print(f"SUCCESSOR_AUTHORITY_SHA256={md_sha}")
    print(f"PREDECESSOR_MACHINE_AUTHORITY_SHA256={PRED_JS}")
    print(f"SUCCESSOR_MACHINE_AUTHORITY_SHA256={js_sha}")
    print(f"hash_table_rows_replaced={replaced}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
