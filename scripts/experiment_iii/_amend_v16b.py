"""Amendment 3g — pin the master salt to the authority that materialised the cohort.

Discovered while revalidating A2 under v1.6: ``EXPERIMENT_III_MASTER_SALT`` is
derived from ``AUTHORITY_SHA256``, so **any** later authority amendment silently
regenerates a different candidate stream and therefore a different 25-identity
cohort. Under v1.5 that was harmless -- Amendment 2 landed before the cohort was
materialised. It is not harmless now: the cohort exists, is hash-bound in the A1
receipts, and is the scientific population.

An operational amendment must not change the cohort. So the salt is pinned to the
authority hash **under which the cohort was actually materialised** -- v1.5's
``3d116d97...``.

This preserves the property §2.2 exists to guarantee. The salt is still *derived,
never chosen*: its inputs are two immutable, published digests that nobody can
alter to obtain a more convenient candidate stream. What changes is only that the
binding no longer floats with the current authority version, which was an
unintended coupling between an operational edit and the scientific population.

It is the same reasoning as 3b, where the P0 bootstrap seed binds the immutable
Phase 0 design digest rather than the current authority hash.
"""

from __future__ import annotations

import io
import json
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "docs" / "experiment_iii" / "final_authorities"
MD = ROOT / "EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.md"
JS = ROOT / "EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.json"

#: v1.5 — the authority under which the cohort was materialised by A1.
COHORT_SALT_AUTHORITY_SHA256 = (
    "3d116d9713b2c7fa705a194023e271061f712d0693618abbd991efa45437d7fb"
)

OLD_ROW = (
    "| Master salt | `EXPERIMENT_III_MASTER_SALT = "
    'sha256("MINEOCCLUDE_EXPERIMENT_III_V1|" + AUTHORITY_SHA256 + "|" + '
    "PHASE0_DESIGN_SHA256)`, materialized and frozen by A1, bound in P2 |"
)
NEW_ROW = (
    "| Master salt | `EXPERIMENT_III_MASTER_SALT = "
    'sha256("MINEOCCLUDE_EXPERIMENT_III_V1|" + COHORT_SALT_AUTHORITY_SHA256 + "|" + '
    "PHASE0_DESIGN_SHA256)`, materialized and frozen by A1, bound in P2. "
    "`COHORT_SALT_AUTHORITY_SHA256` is **pinned** to the authority under which the "
    "cohort was materialized (v1.5, `3d116d97…`), not to the current authority "
    "hash — see §2.2a |"
)

SECTION_22A = """
**§2.2a Salt pinning (Authority Amendment 3g).** `COHORT_SALT_AUTHORITY_SHA256` is the
**immutable** hash of the authority under which A1 materialized the cohort:

```
COHORT_SALT_AUTHORITY_SHA256 = 3d116d9713b2c7fa705a194023e271061f712d0693618abbd991efa45437d7fb   (v1.5)
```

The predecessor formula read the *current* `AUTHORITY_SHA256`, which coupled the scientific
population to every later edit of the authority document: any amendment, however operational,
would have produced a different master salt, a different candidate stream, and therefore a
different 25-identity cohort. Under v1.5 that coupling was latent, because Amendment 2 landed
before the cohort existed. Once the cohort was materialized it became a live defect, and
Amendment 3 closes it.

The property §2.2 exists to guarantee is **unchanged**: the salt remains *derived, never
chosen*. Both of its inputs are immutable published digests, so no one can substitute a salt to
obtain a more convenient candidate stream — which remains an explicitly forbidden repair. The
only thing removed is an unintended dependency of the cohort on operational edits. This mirrors
§7.10b, where the P0 bootstrap seed binds the immutable Phase 0 design digest for the same
reason.

The materialized cohort is therefore **byte-identical** across v1.5 and v1.6, and
`production_identity_manifest.sha256` is unchanged.
"""


def main() -> int:
    text = MD.read_text(encoding="utf-8")
    if text.count(OLD_ROW) != 1:
        raise SystemExit("AMENDMENT_PRECONDITION_FAILED: master salt row not found")
    text = text.replace(OLD_ROW, NEW_ROW)

    anchor = "**Iterative recurrence is mandatory, and the operand order is load-bearing.**"
    if text.count(anchor) != 1:
        raise SystemExit("AMENDMENT_PRECONDITION_FAILED: 2.2 anchor not found")
    text = text.replace(anchor, SECTION_22A.strip() + "\n\n" + anchor)
    MD.write_text(text, encoding="utf-8", newline="\n")

    authority = json.loads(JS.read_text(encoding="utf-8"), object_pairs_hook=OrderedDict)
    cohort = authority["cohort"]
    cohort["master_salt_formula"] = (
        "sha256('MINEOCCLUDE_EXPERIMENT_III_V1|' + COHORT_SALT_AUTHORITY_SHA256 + "
        "'|' + PHASE0_DESIGN_SHA256)"
    )
    cohort["cohort_salt_authority_sha256"] = COHORT_SALT_AUTHORITY_SHA256
    cohort["cohort_salt_authority_version"] = "v1.5"
    cohort["master_salt_pinned_to"] = (
        "THE_AUTHORITY_UNDER_WHICH_THE_COHORT_WAS_MATERIALIZED"
    )
    cohort["master_salt_floats_with_current_authority"] = False
    cohort["master_salt_pinning_rationale"] = (
        "the predecessor formula read the current AUTHORITY_SHA256, so any later "
        "amendment would have regenerated a different candidate stream and a "
        "different cohort; the salt remains derived, never chosen, because both "
        "inputs are immutable published digests"
    )
    cohort["cohort_byte_identical_across_v1_5_and_v1_6"] = True

    record = authority["authority_amendment_3"]
    record["changes"] = list(record["changes"]) + [
        "3g master salt pinned to COHORT_SALT_AUTHORITY_SHA256 (v1.5), so an "
        "operational amendment cannot regenerate the materialized cohort"
    ]
    record["cohort_changed_by_amendment"] = False
    record["cohort_byte_identical_across_the_amendment"] = True

    with io.open(JS, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(authority, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print("AMENDMENT_3G_APPLIED=true")
    print(f"COHORT_SALT_AUTHORITY_SHA256={COHORT_SALT_AUTHORITY_SHA256}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
