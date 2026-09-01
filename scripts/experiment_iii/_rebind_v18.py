"""Rebind every controlling hash and version string to the v1.8 successor.

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

PRED_MD = "c773d9620e7fde9e72682d24a7515157522064e8c23b7096780a2995b926985a"
PRED_JS = "75bb0acb0f7a5b7121d7754de5db623e56527a454b3bea78ce3ae2047fd43788"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    md_bytes = MD.read_bytes()
    md_sha = hashlib.sha256(md_bytes).hexdigest()
    if md_sha == PRED_MD:
        raise SystemExit("REBIND_PRECONDITION_FAILED: markdown still hashes to v1.7")

    authority = json.loads(JS.read_text(encoding="utf-8"), object_pairs_hook=OrderedDict)
    authority["authority_markdown_sha256"] = md_sha
    authority["authority_markdown_bytes"] = len(md_bytes)
    authority["authority_markdown_hash_recomputed_by"] = "AUTHORITY_AMENDMENT_5_V1_8"
    with io.open(JS, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(authority, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    js_sha = sha256_file(JS)

    # ---- README ----
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    old = (
        "AUTHORITY_VERSION             = v1.7  (III-A + Amendment 1 / III-B + "
        "repair passes 1-2 + ultimate closure + Amendment 2 cohort admission "
        "feasibility + Amendment 3 P0 operational completeness + Amendment 4 "
        "capture liveness successor rule)"
    )
    if old not in text:
        raise SystemExit("REBIND_PRECONDITION_FAILED: README v1.7 version line not found")
    text = text.replace(old, old.replace("= v1.7", "= v1.8").rstrip(")")
                        + " + Amendment 5 III-A analysis bootstrap seed)")
    readme.write_text(text, encoding="utf-8", newline="\n")

    # ---- validation report ----
    report = ROOT / "AUTHORITY_VALIDATION_REPORT.md"
    text = report.read_text(encoding="utf-8")
    text = text.replace("**Authority version:** `v1.7`", "**Authority version:** `v1.8`")
    replaced = 0
    for old_line, new_line in (
        (f"| `{PRED_JS}` |", f"| `{js_sha}` |"),
        (f"| `{PRED_MD}` |", f"| `{md_sha}` |"),
    ):
        if old_line in text:
            text = text.replace(old_line, new_line, 1)
            replaced += 1
    if "## 19. Authority Amendment 5 (v1.8)" not in text:
        text = text.rstrip("\n") + """

---

## 19. Authority Amendment 5 (v1.8) — III-A analysis bootstrap seed

Prospective §9.2 amendment, raised at the `A6`/`A7` boundary with **zero production captures,
zero production MineWorld forwards, zero production predictions, zero production statistics and
zero bootstrap executions** in existence.

| | |
|---|---|
| Defect | `A6` requires P2 to bind "the analysis bootstrap seed" and forbids freezing with a placeholder; the machine authority carried the non-concrete token `FROZEN_IN_P2` at `statistics.bootstrap_seed`, and no concrete value or derivation for it existed anywhere in the package |
| Consequence | P2 could never be completed honestly, and `A7` could never be authorized; the passing predecessor P2 in fact froze the placeholder string |
| 5a | the III-A analysis bootstrap seed is **derived, never picked**, by the §7.10b construction under its own separation domain `MINEOCCLUDE_EXPERIMENT_III_ANALYSIS_BOOTSTRAP_V1` over the immutable `PHASE0_DESIGN_SHA256` |
| 5b | `ANALYSIS_BOOTSTRAP_SEED = 8258108568742502015`, material digest `f29ab1fd6c819e7ff584b6ca9344b6d112fe15a10dbc32ff47bed6536589a895` |
| 5c | domain separation is load-bearing: the analysis bootstrap may **not** inherit the P0 placement-bootstrap stream |
| 5d | P2 must refuse `null`, `""`, a non-integer, and the tokens `FROZEN_IN_P2`, `TBD`, `TO_BE_DETERMINED`, `PLACEHOLDER` |
| Scientific design | `B = 10,000`, whole-identity resampling unit, pairing, the three primary estimands, Holm family, secondary families, folds, inner rotations, alpha grid, baselines, features, representations, layers, token slices, target rows, FIR labels, cohort, apparatus, conditions, RVE, capture order, retry, attrition and deadline fallbacks all unchanged |
| New success gate | none |
| Cohort invariance | `master_salt` binds `COHORT_SALT_AUTHORITY_SHA256` (v1.5), not the live hash, so the 25-identity cohort, paths, targets and folds are byte-identical across the amendment |
| Invalidation | receipt currentness only; the predecessor P2 is `SUPERSEDED_BEFORE_PRODUCTION`; P0 and P1 scientific evidence unaffected |

```
AMENDMENT_5_STATUS = PASS
BLOCKING_DEFECTS   = 0
```
"""
    report.write_text(text, encoding="utf-8", newline="\n")

    # ---- audit suite version targets ----
    audit = ROOT / "final_audit" / "audit_final.py"
    if audit.is_file():
        text = audit.read_text(encoding="utf-8")
        for old_line, new_line in (
            ('chk("README states authority version v1.7", "AUTHORITY_VERSION             = v1.7" in RM)',
             'chk("README states authority version v1.8", "AUTHORITY_VERSION             = v1.8" in RM)'),
            ('chk("authority version is v1.7", A["authority_version"] == "v1.7")',
             'chk("authority version is v1.8", A["authority_version"] == "v1.8")'),
            ('chk("authority version is v1.7", A["authority_version"]=="v1.7")',
             'chk("authority version is v1.8", A["authority_version"]=="v1.8")'),
            ('chk("README states v1.7","AUTHORITY_VERSION             = v1.7" in RM)',
             'chk("README states v1.8","AUTHORITY_VERSION             = v1.8" in RM)'),
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
