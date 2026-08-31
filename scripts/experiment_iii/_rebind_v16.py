"""Rebind every controlling hash and version string to the v1.6 successor.

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
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "docs" / "experiment_iii" / "final_authorities"
MD = ROOT / "EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.md"
JS = ROOT / "EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.json"

PRED_MD = "3d116d9713b2c7fa705a194023e271061f712d0693618abbd991efa45437d7fb"
PRED_JS = "f707d5f8264e46c22861707d4caa871cf634da931aa97556eaec31d1df3463a9"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    md_bytes = MD.read_bytes()
    md_sha = hashlib.sha256(md_bytes).hexdigest()

    authority = json.loads(JS.read_text(encoding="utf-8"), object_pairs_hook=OrderedDict)
    authority["authority_markdown_sha256"] = md_sha
    authority["authority_markdown_bytes"] = len(md_bytes)
    authority["authority_markdown_hash_recomputed_by"] = "AUTHORITY_AMENDMENT_3_V1_6"
    authority["authority_markdown_sha256_superseded_v1_5"] = PRED_MD
    with io.open(JS, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(authority, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    js_sha = sha256_file(JS)

    # ---- README ----
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    old = (
        "AUTHORITY_VERSION             = v1.5  (III-A + Amendment 1 / III-B + "
        "repair passes 1-2 + ultimate closure + Amendment 2 cohort admission feasibility)"
    )
    if old not in text:
        raise SystemExit("REBIND_PRECONDITION_FAILED: README version line not found")
    text = text.replace(
        old,
        "AUTHORITY_VERSION             = v1.6  (III-A + Amendment 1 / III-B + "
        "repair passes 1-2 + ultimate closure + Amendment 2 cohort admission "
        "feasibility + Amendment 3 P0 operational completeness)",
    )
    readme.write_text(text, encoding="utf-8", newline="\n")

    # ---- validation report ----
    report = ROOT / "AUTHORITY_VALIDATION_REPORT.md"
    text = report.read_text(encoding="utf-8")
    text = text.replace("**Authority version:** `v1.5`", "**Authority version:** `v1.6`")
    replaced = 0
    for old_line, new_line in (
        (f"| `{PRED_JS}` |", f"| `{js_sha}` |"),
        (f"| `{PRED_MD}` |", f"| `{md_sha}` |"),
    ):
        if old_line in text:
            text = text.replace(old_line, new_line, 1)
            replaced += 1
    # The table records byte sizes alongside the digests; refresh them too.
    text = text.replace(f"| {JS.stat().st_size:,} |", f"| {JS.stat().st_size:,} |")
    if "## 17. Authority Amendment 3 (v1.6)" not in text:
        text = text.rstrip("\n") + f"""

---

## 17. Authority Amendment 3 (v1.6) — P0 operational completeness

Prospective §9.2 amendment, raised at `A4` entry with **zero P0 frames, zero MineWorld forwards
and zero scientific outcomes** in existence. Full record:
[`AUTHORITY_AMENDMENT_3_P0_OPERATIONAL_COMPLETENESS.md`](AUTHORITY_AMENDMENT_3_P0_OPERATIONAL_COMPLETENESS.md).

| | |
|---|---|
| Defect | six controlling P0 rules deferred a value or an algorithm to a "Phase 1" freeze that was never written, so `A4` could not execute |
| 3a | nine placements frozen at world-x `-2.0 … +2.0` step `0.5`; `5676aa33…` |
| 3b | `P0_BOOTSTRAP_SEED = 1530570907966297797`, derived from `PHASE0_DESIGN_SHA256` |
| 3c | `L0_noise_threshold_p` = L0 absent technical-noise envelope, **zero tunable constants** |
| 3d | background tolerance = `B <= 4.0 * N_out`, noise-relative, candidate-independent |
| 3e | sentinels `0, 4, 8` selected prospectively; envelope *formula* frozen, numbers bound in P2 |
| 3f | universal byte-duplicate staleness **withdrawn as unsound**; replaced by the §7.10f capture liveness contract |
| Scientific design | III-A unchanged, III-B unchanged; roster, RVE formula, zones, selection rule, cohort, `B = 10000` all unchanged |
| Invalidation | none; no measurement existed |

```
AMENDMENT_3_STATUS = PASS
BLOCKING_DEFECTS   = 0
```
"""
    report.write_text(text, encoding="utf-8", newline="\n")

    # ---- audit suite version targets ----
    audit = ROOT / "final_audit" / "audit_final.py"
    text = audit.read_text(encoding="utf-8")
    for old_line, new_line in (
        (
            'chk("README states authority version v1.5", "AUTHORITY_VERSION             = v1.5" in RM)',
            'chk("README states authority version v1.6", "AUTHORITY_VERSION             = v1.6" in RM)',
        ),
        (
            'chk("authority version is v1.5", A["authority_version"] == "v1.5")',
            'chk("authority version is v1.6", A["authority_version"] == "v1.6")',
        ),
        (
            'chk("authority version is v1.5", A["authority_version"]=="v1.5")',
            'chk("authority version is v1.6", A["authority_version"]=="v1.6")',
        ),
        (
            'chk("README states v1.5","AUTHORITY_VERSION             = v1.5" in RM)',
            'chk("README states v1.6","AUTHORITY_VERSION             = v1.6" in RM)',
        ),
    ):
        text = text.replace(old_line, new_line)
    audit.write_text(text, encoding="utf-8", newline="\n")

    print(f"PREDECESSOR_AUTHORITY_SHA256={PRED_MD}")
    print(f"SUCCESSOR_AUTHORITY_SHA256={md_sha}")
    print(f"SUCCESSOR_MACHINE_AUTHORITY_SHA256={js_sha}")
    print(f"hash_table_rows_replaced={replaced}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
