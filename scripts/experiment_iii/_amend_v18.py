"""Apply Authority Amendment 5 (v1.8) -- the III-A analysis bootstrap seed.

One-shot amendment writer. Every edit is an exact-string replacement asserted
before it is applied, so a drifted predecessor fails loudly rather than silently
producing a half-amended authority.

**The defect.** Authority A6 requires P2 to bind "the analysis bootstrap seed",
and forbids freezing with a placeholder, a null or a "to be determined". No
concrete analysis seed and no derivation for one existed anywhere in the frozen
package: the machine authority carried the non-concrete token ``FROZEN_IN_P2``
at ``statistics.bootstrap_seed``, and the only frozen seed derivation in the
program (§7.10b) is domain-separated to **P0** and may not be reused. P2 could
therefore never be completed honestly, and A7 could never be authorized.

**The resolution.** The III-A analysis bootstrap seed is *derived*, never picked,
by the same construction §7.10b already uses for P0, under its own separation
domain. It binds ``PHASE0_DESIGN_SHA256`` -- provenance that predates P0 and is
immutable -- so it is stable across every later operational amendment and cannot
be nudged by any measurement.

**Prospectivity.** Raised before the first production capture: zero production
captures, zero production MineWorld forwards, zero production predictions, zero
production statistics, zero bootstrap executions. No scientific production
outcome existed or was inspected while this amendment was authored.

**Scope.** Exactly one previously unresolved scientific value moves. B = 10,000,
the whole-identity resampling unit, pairing semantics, all three primary
estimands, the Holm family, every secondary family, folds, inner rotations, the
alpha grid, baselines, features, representations, layers, token slices, target
rows, FIR labels, the cohort, the apparatus, the conditions, RVE values, capture
order, retry rules, attrition rules and deadline fallbacks are unchanged. No new
success gate is created.
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

PRED_AUTHORITY_SHA256 = "c773d9620e7fde9e72682d24a7515157522064e8c23b7096780a2995b926985a"
PRED_MACHINE_SHA256 = "75bb0acb0f7a5b7121d7754de5db623e56527a454b3bea78ce3ae2047fd43788"
PRED_FREEZE_COMMIT = "3fe0bc13d18f0002eebb99a2b10ef83e651d6f9a"

PHASE0_DESIGN_SHA256 = "be3ccd97525434659dc39b3be36e6046ceebaeab2a33db81ce18c139e19c8e4c"
DOMAIN = "MINEOCCLUDE_EXPERIMENT_III_ANALYSIS_BOOTSTRAP_V1"
P0_DOMAIN = "MINEOCCLUDE_EXPERIMENT_III_P0_BOOTSTRAP_V1"


def derive(domain: str) -> tuple[str, str, int]:
    material = domain + "|" + PHASE0_DESIGN_SHA256
    digest = hashlib.sha256(material.encode("utf-8")).digest()
    return (
        material,
        hashlib.sha256(material.encode("utf-8")).hexdigest(),
        int.from_bytes(digest[:8], "big") & ((1 << 63) - 1),
    )


# The already-frozen P0 rule is reproduced first. If this construction cannot
# regenerate the seed the authority already published, it is the wrong
# construction and no amendment may be written from it.
_P0_MATERIAL, P0_MATERIAL_SHA256, P0_SEED = derive(P0_DOMAIN)
EXPECTED_P0_MATERIAL_SHA256 = "153dae21a8e0d6c568eb1977e738ecf485f2b4dfc6670e8dc1709bcd8ce6625f"
EXPECTED_P0_SEED = 1530570907966297797

MATERIAL, MATERIAL_SHA256, ANALYSIS_SEED = derive(DOMAIN)
EXPECTED_MATERIAL_SHA256 = "f29ab1fd6c819e7ff584b6ca9344b6d112fe15a10dbc32ff47bed6536589a895"
EXPECTED_ANALYSIS_SEED = 8258108568742502015

DERIVATION = (
    'int.from_bytes(SHA256("MINEOCCLUDE_EXPERIMENT_III_ANALYSIS_BOOTSTRAP_V1|" '
    '+ PHASE0_DESIGN_SHA256).digest()[:8], "big") & ((1<<63)-1)'
)

# --------------------------------------------------------------------------
# Markdown edits
# --------------------------------------------------------------------------

OLD_SEED_ROW = "| Bootstrap seed | frozen in P2 |\n"
NEW_SEED_ROW = (
    "| Bootstrap seed | **`8258108568742502015`** — derived in §8.10.5a from the immutable "
    "Phase 0 design binding, and bound in P2 |\n"
)

OLD_PATTERN = """Captures and rows are **never** resampled as independent units. The existing whole-identity
bootstrap at `src/mineocclude/regime_a_first25_analysis.py:226-251` (`B = 10,000`, resampling
identities) is the reusable pattern.
"""

NEW_PATTERN = OLD_PATTERN + """
#### 8.10.5a III-A analysis bootstrap seed (frozen, Amendment 5)

The seed is **derived, never hand-picked**, from provenance that predates every Experiment III
measurement, by the same construction §7.10b uses for P0 under its own separation domain:

```
seed_bytes              = SHA256("MINEOCCLUDE_EXPERIMENT_III_ANALYSIS_BOOTSTRAP_V1|"
                                 + PHASE0_DESIGN_SHA256)
ANALYSIS_BOOTSTRAP_SEED = int.from_bytes(seed_bytes[:8], "big") & ((1 << 63) - 1)
```

With the immutable `PHASE0_DESIGN_SHA256 =
be3ccd97525434659dc39b3be36e6046ceebaeab2a33db81ce18c139e19c8e4c` the derivation material is

```
MINEOCCLUDE_EXPERIMENT_III_ANALYSIS_BOOTSTRAP_V1|be3ccd97525434659dc39b3be36e6046ceebaeab2a33db81ce18c139e19c8e4c
MATERIAL_SHA256         = f29ab1fd6c819e7ff584b6ca9344b6d112fe15a10dbc32ff47bed6536589a895
ANALYSIS_BOOTSTRAP_SEED = 8258108568742502015
```

The **domain separation is load-bearing**: `..._ANALYSIS_BOOTSTRAP_V1` and
`..._P0_BOOTSTRAP_V1` bind the same digest and must never collide, so the analysis bootstrap
cannot inherit the P0 placement-bootstrap stream. Reusing the P0 seed here is forbidden.

Like the P0 seed, this value depends on the **Phase 0 design binding**, not on the current
authority hash, so it is stable across every later operational amendment. `B = 10,000` and the
whole-identity resampling unit are unchanged. The bootstrap resamples whole identities with
replacement using `numpy.random.default_rng(seed)`.

P2 must bind the concrete integer together with its domain, the Phase 0 design digest and the
derivation material digest, and must **refuse** a null, an empty string, a non-integer, or any
placeholder token — `FROZEN_IN_P2`, `TBD`, `TO_BE_DETERMINED`, `PLACEHOLDER`.
"""

OLD_A6_CLAUSE = (
    "estimands; every secondary family; bootstrap `B = 10,000`; the analysis bootstrap seed; "
    "the Holm\nfamilies; the prediction-lock rule.\n"
)
NEW_A6_CLAUSE = (
    "estimands; every secondary family; bootstrap `B = 10,000`; the analysis bootstrap seed of\n"
    "§8.10.5a; the Holm families; the prediction-lock rule.\n"
)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"AMENDMENT_PRECONDITION_FAILED: {label} matched {count} times, expected exactly 1"
        )
    return text.replace(old, new, 1)


def main() -> int:
    if (P0_MATERIAL_SHA256, P0_SEED) != (EXPECTED_P0_MATERIAL_SHA256, EXPECTED_P0_SEED):
        print("BOOTSTRAP_DERIVATION_VERIFICATION=FAIL", file=sys.stderr)
        print(
            "the construction does not reproduce the already-frozen P0 seed; "
            f"got {P0_MATERIAL_SHA256} / {P0_SEED}",
            file=sys.stderr,
        )
        return 1
    if (MATERIAL_SHA256, ANALYSIS_SEED) != (EXPECTED_MATERIAL_SHA256, EXPECTED_ANALYSIS_SEED):
        print("BOOTSTRAP_DERIVATION_VERIFICATION=FAIL", file=sys.stderr)
        return 1

    observed_md = hashlib.sha256(MD.read_bytes()).hexdigest()
    observed_js = hashlib.sha256(JS.read_bytes()).hexdigest()
    if observed_md != PRED_AUTHORITY_SHA256 or observed_js != PRED_MACHINE_SHA256:
        print("AMENDMENT_PRECONDITION_FAILED: predecessor authority bytes drifted",
              file=sys.stderr)
        print(f"  md {observed_md} != {PRED_AUTHORITY_SHA256}", file=sys.stderr)
        print(f"  js {observed_js} != {PRED_MACHINE_SHA256}", file=sys.stderr)
        return 1

    # ---- markdown ----
    text = MD.read_text(encoding="utf-8")
    text = replace_once(text, OLD_SEED_ROW, NEW_SEED_ROW, "8.10.5 bootstrap-seed row")
    text = replace_once(text, OLD_PATTERN, NEW_PATTERN, "8.10.5 reusable-pattern paragraph")
    text = replace_once(text, OLD_A6_CLAUSE, NEW_A6_CLAUSE, "A6 analysis binding clause")
    with io.open(MD, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)

    # ---- machine authority ----
    authority = json.loads(JS.read_text(encoding="utf-8"), object_pairs_hook=OrderedDict)
    statistics = authority["statistics"]
    if statistics.get("bootstrap_seed") != "FROZEN_IN_P2":
        raise SystemExit(
            "AMENDMENT_PRECONDITION_FAILED: statistics.bootstrap_seed is not FROZEN_IN_P2"
        )
    rebuilt = OrderedDict()
    for key, value in statistics.items():
        if key == "bootstrap_seed":
            rebuilt["bootstrap_seed"] = ANALYSIS_SEED
            rebuilt["bootstrap_seed_derivation"] = DERIVATION
            rebuilt["bootstrap_seed_domain"] = DOMAIN + "|"
            rebuilt["bootstrap_seed_binds_to"] = "PHASE0_DESIGN_SHA256"
            rebuilt["bootstrap_seed_material_sha256"] = MATERIAL_SHA256
            rebuilt["bootstrap_seed_stable_across_operational_amendments"] = True
            rebuilt["bootstrap_seed_frozen_by"] = "AUTHORITY_AMENDMENT_5_V1_8"
            rebuilt["bootstrap_seed_placeholder_tokens_refused"] = [
                "FROZEN_IN_P2", "TBD", "TO_BE_DETERMINED", "PLACEHOLDER", "", None,
            ]
        else:
            rebuilt[key] = value
    authority["statistics"] = rebuilt

    authority["authority_version"] = "v1.8"
    authority["amended_by"] = "AUTHORITY_AMENDMENT_5"
    authority["authority_amendment_5"] = OrderedDict(
        (
            ("amendment", "AUTHORITY_AMENDMENT_5_ANALYSIS_BOOTSTRAP_SEED"),
            ("authority_version", "v1.8"),
            ("predecessor_authority_version", "v1.7"),
            ("predecessor_authority_sha256", PRED_AUTHORITY_SHA256),
            ("predecessor_machine_authority_sha256", PRED_MACHINE_SHA256),
            ("predecessor_authority_freeze_commit", PRED_FREEZE_COMMIT),
            ("classification", "PROSPECTIVE_SCIENTIFIC_DESIGN_CHANGE_SECTION_9_2"),
            ("defect", "statistics.bootstrap_seed was the non-concrete token FROZEN_IN_P2, "
                       "which A6 forbids freezing and for which no derivation existed"),
            ("resolution_section", "8.10.5a"),
            ("analysis_bootstrap_seed", ANALYSIS_SEED),
            ("analysis_bootstrap_seed_domain", DOMAIN + "|"),
            ("analysis_bootstrap_seed_material_sha256", MATERIAL_SHA256),
            ("phase0_design_sha256", PHASE0_DESIGN_SHA256),
            ("bootstrap_replicates_unchanged", 10000),
            ("only_scientific_change", "statistics.bootstrap_seed"),
            ("new_success_gate_created", False),
            ("cohort_changed", False),
            ("paths_changed", False),
            ("targets_changed", False),
            ("folds_changed", False),
            ("production_captures_before_amendment", 0),
            ("production_forwards_before_amendment", 0),
            ("production_outcomes_exposed", False),
            ("prospective", True),
            ("adopted_before_first_production_capture", True),
        )
    )
    authority["authority_markdown_sha256_superseded_v1_7"] = PRED_AUTHORITY_SHA256
    with io.open(JS, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(authority, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    print("BOOTSTRAP_DERIVATION_VERIFICATION=PASS")
    print(f"P0_MATERIAL_SHA256={P0_MATERIAL_SHA256}")
    print(f"P0_BOOTSTRAP_SEED={P0_SEED}")
    print(f"ANALYSIS_BOOTSTRAP_DOMAIN={DOMAIN}")
    print(f"ANALYSIS_BOOTSTRAP_MATERIAL_SHA256={MATERIAL_SHA256}")
    print(f"ANALYSIS_BOOTSTRAP_SEED={ANALYSIS_SEED}")
    print("AMENDMENT_5_MARKDOWN_EDITS=3")
    print("AMENDMENT_5_APPLIED=true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
