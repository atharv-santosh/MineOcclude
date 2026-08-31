"""Apply Authority Amendment 3 (v1.6) -- P0 operational completeness.

One-shot amendment writer. Every edit is an exact-string replacement that is
asserted before it is applied, so a drifted predecessor fails loudly instead of
silently producing a half-amended authority.

Amendment 3 is prospective in the strongest available sense: it is raised at A4
entry, before a single P0 frame exists. It creates no new scientific decision.
It *materialises* six operational bindings that v1.5 deferred to a "Phase 1"
that was never written, and which A4 therefore could not execute:

  3a  the nine P0 placement coordinates          (v1.5: "frozen by A1", never frozen)
  3b  the P0 bootstrap seed                      (v1.5: "Phase-1-frozen")
  3c  the L0 support-mask noise threshold rule   (v1.5: "derived ... frozen by A1")
  3d  the outside-mask background tolerance rule (v1.5: a name, no rule)
  3e  the sentinel selection + envelope rule     (v1.5: "Phase-1-frozen envelope")
  3f  the capture liveness contract              (v1.5: an unsound byte-duplicate rule)

3f is the only repair that changes a stated rule rather than filling a hole, and
it does so because the stated rule is unsound for P0: P0 deliberately captures a
STATIC settled scene, so repeated framebuffer bytes are the expected observation,
not evidence of a frozen renderer. The repair replaces "bytes repeated => stale"
with a liveness contract that tests the renderer where it can actually be tested
-- across known scene transitions.
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

PHASE0_DESIGN_SHA256 = "be3ccd97525434659dc39b3be36e6046ceebaeab2a33db81ce18c139e19c8e4c"
P0_BOOTSTRAP_DOMAIN = "MINEOCCLUDE_EXPERIMENT_III_P0_BOOTSTRAP_V1|"

#: Authority Amendment 3a -- the nine scripted Phase 0 calibration positions.
PLACEMENT_X = (-2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0)
SENTINEL_INDICES = (0, 4, 8)

#: Amendment 3d. Derivation, not a taste: the split-half reference compares two
#: medians of n/2 absent frames while the present/absent contrast compares two
#: medians of n frames, so the reference already carries about twice the energy
#: of the noise it is bounding. A ratio of 4 therefore leaves roughly eightfold
#: energy headroom against a false technical failure, while a genuine background
#: change (a wall material, a light level, a camera slip) is orders of magnitude
#: larger. Frozen before any P0 image exists and never lowered afterwards.
BACKGROUND_TOLERANCE_RATIO = 4.0

#: Amendment 3e. Envelope half-width multiplier on the observed P0 replicate
#: range, floored by the already-frozen replicate CV bound so two exactly-equal
#: replicates cannot produce a zero-width envelope that every later batch fails.
SENTINEL_ENVELOPE_K = 2.0


def p0_bootstrap_seed() -> int:
    digest = hashlib.sha256(
        (P0_BOOTSTRAP_DOMAIN + PHASE0_DESIGN_SHA256).encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)


def placements() -> list[dict]:
    return [
        {
            "placement_index": index,
            "placement_id": f"P{index}",
            "lane_x": x,
            "lane_y": 4.0,
            "lane_z": 6.0,
        }
        for index, x in enumerate(PLACEMENT_X)
    ]


def placements_sha256() -> str:
    blob = json.dumps(
        placements(), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


# --------------------------------------------------------------------------
# Human authority edits
# --------------------------------------------------------------------------

REPLACEMENTS: list[tuple[str, str]] = []


def edit(old: str, new: str) -> None:
    REPLACEMENTS.append((old, new))


# -- 3.3 framebuffer receipt row -------------------------------------------
edit(
    "| Framebuffer receipt | every frame exactly 640 × 360 RGB; no byte-identical "
    "stale run beyond the frozen tolerance | `CAPTURE_STALE_FRAME` |",
    "| Framebuffer receipt | every frame exactly 640 × 360 RGB, read succeeded, "
    "hash recorded; the §7.10 **capture liveness contract** satisfied. Repeated "
    "framebuffer bytes within one settled static state are **not** by themselves "
    "staleness | `CAPTURE_STALE_FRAME` |",
)

# -- 7.2 placements + staleness rows ---------------------------------------
edit(
    "| Placements | **9**, frozen, spanning the target corridor; coordinates "
    "frozen by A1 and bound in P2 |",
    "| Placements | **9**, frozen at world-x `-2.0, -1.5, -1.0, -0.5, 0.0, +0.5, "
    "+1.0, +1.5, +2.0` on the frozen sheep lane (`y = 4`, `z = 6`), ascending, "
    "§7.10a; bound in P2 |",
)
edit(
    "| Staleness | byte-identical consecutive frames beyond the frozen tolerance "
    "invalidate the block |",
    "| Staleness | governed by the §7.10 capture liveness contract. P0 captures "
    "a deliberately static settled scene, so repeated framebuffer bytes inside one "
    "state are expected and valid; staleness is proven at scene **transitions** |",
)

# -- 7.3 step 3: the mask noise threshold ----------------------------------
edit(
    "`L0_noise_threshold_p` is derived from the absent-frame split-half noise at "
    "that placement and\nfrozen by A1. **The same `M_p` is used for every "
    "candidate** — a per-candidate mask would make\nthe metric "
    "material-dependent and is forbidden.",
    "`L0_noise_threshold_p` is the **L0 absent-frame technical-noise envelope** at "
    "that placement, frozen\nby §7.10c before any candidate is scored. **The same "
    "`M_p` is used for every candidate** — a\nper-candidate mask would make the "
    "metric material-dependent and is forbidden.",
)

# -- 7.3 step 8: the background gate ---------------------------------------
edit(
    "**Step 8 — background gate.** The present/absent residual **outside** `M_p` "
    "must not exceed the\nPhase-1-frozen background tolerance; exceeding it is "
    "`RVE_BACKGROUND_TOLERANCE_EXCEEDED` and\ninvalidates that block.",
    "**Step 8 — background gate.** The present/absent residual **outside** `M_p` "
    "must not exceed the\nnoise-relative background tolerance of §7.10d; exceeding "
    "it is `RVE_BACKGROUND_TOLERANCE_EXCEEDED`\nand invalidates that block.",
)

# -- 7.5 background rule + bootstrap seed ----------------------------------
edit(
    "| Background | outside-mask present/absent residual `<=` the Phase-1-frozen "
    "background tolerance |",
    "| Background | outside-mask present/absent residual `<=` `4.0 ×` that cell's "
    "own outside-mask absent split-half noise (§7.10d) |",
)
edit(
    "The bootstrap resamples the **9 placements** with replacement, `B = 10,000`, "
    "using the\nPhase-1-frozen P0 bootstrap seed bound in P2.",
    "The bootstrap resamples the **9 placements** with replacement, `B = 10,000`, "
    "using the P0\nbootstrap seed derived in §7.10b from the immutable Phase 0 "
    "design binding and bound in P2.",
)

# -- 7.9 sentinels ----------------------------------------------------------
edit(
    "Before **and** after each production condition batch, repeat **three frozen "
    "sentinel\nplacements** — a fixed subset of the nine P0 placements, frozen by "
    "A1 and bound in P2.",
    "Before **and** after each production condition batch, repeat **three frozen "
    "sentinel\nplacements** — placement indices `0, 4, 8` of §7.2, i.e. world-x "
    "`-2.0`, `0.0`, `+2.0`.\nThey are the left, centre and right of the frozen "
    "placement set, chosen by the deterministic\ncoverage rule of §7.10e **before "
    "any P0 measurement exists**, never by which placements later\nlooked most "
    "stable. Bound in P2.",
)
edit(
    "- Each sentinel score must lie inside the Phase-1-frozen **repeatability "
    "envelope**, derived from\n  the P0 replicate spread at those placements and "
    "bound in P2.",
    "- Each sentinel score must lie inside the **repeatability envelope** computed "
    "by the frozen\n  derivation of §7.10e from the P0 replicate spread at those "
    "placements. The *formula* is frozen\n  now, before P0; the *numeric* envelope "
    "is materialised from P0 replicates and bound in P2.",
)

# -- new 7.10 / 7.11 --------------------------------------------------------
SECTION_710 = r"""
### 7.10 P0 operational bindings (Authority Amendment 3, v1.6)

Authority v1.5 deferred six P0 operational choices to a "Phase 1" freeze that was never
written, leaving `A4` unable to execute: the placement coordinates, the bootstrap seed, the
mask noise threshold, the background tolerance, the sentinel envelope, and a staleness rule
that was unsound for a static scene. This section materialises all six. It is raised at `A4`
entry with **zero P0 frames, zero MineWorld forwards and zero scientific outcomes in
existence**, so no binding here can have been chosen to favour any material or any result.

Every rule below reads only **L0 and absent-frame technical calibration data**. None reads a
candidate material's score, a ladder, a MineWorld output, or a decoder error.

#### 7.10a Placements (frozen)

The nine scripted Phase 0 calibration positions, on the frozen sheep lane `y = 4`, `z = 6`, in
ascending world-x order:

```
-2.0  -1.5  -1.0  -0.5  0.0  +0.5  +1.0  +1.5  +2.0
```

Representation is IEEE-754 `float64`; ordering is ascending `lane_x`; index `i` is the
zero-based position in that ascending order. All nine lie strictly inside the verified
counterfactually fully occluded lane interval `[-3.49, 4.49]` (§4.5), so every placement is a
genuine occluded-corridor position.

`P0_PLACEMENTS_SHA256` is the SHA-256 of the canonical JSON (sorted keys, `,`/`:` separators,
no NaN) of the nine records `{placement_index, placement_id, lane_x, lane_y, lane_z}`:

```
5676aa3371fcc481f89c709d8be81e2b14932f550b94ce44a42b2617420a84b6
```

#### 7.10b P0 bootstrap seed (frozen)

The seed is **derived**, never hand-picked, and derived from provenance that predates P0:

```
seed_bytes        = SHA256("MINEOCCLUDE_EXPERIMENT_III_P0_BOOTSTRAP_V1|" + PHASE0_DESIGN_SHA256)
P0_BOOTSTRAP_SEED = int.from_bytes(seed_bytes[:8], "big") & ((1 << 63) - 1)
```

With the immutable `PHASE0_DESIGN_SHA256 =
be3ccd97525434659dc39b3be36e6046ceebaeab2a33db81ce18c139e19c8e4c` this evaluates to

```
P0_BOOTSTRAP_SEED = 1530570907966297797
```

It depends on the **Phase 0 design binding**, not on the current authority hash, so it is
stable across every later operational amendment. `B = 10,000` is unchanged. The bootstrap
resamples the nine placements with replacement using `numpy.random.default_rng(seed)`.

#### 7.10c `L0_noise_threshold_p` — the L0 technical-noise envelope (frozen)

One threshold per placement. It consumes **only the L0 absent frames at that placement** and is
frozen before any candidate is scored.

```
input       the settled ABSENT frames of condition L0 at placement p, per replicate block b
linearize   §7.3 step 1, float64 throughout
split       by ascending capture index within a block; with n frames,
              first  = frames[0 : n // 2]
              second = frames[n - n // 2 : n]
            for odd n the single middle frame is in neither half, so the halves are
            exactly balanced and the assignment is deterministic
medians     coordinate-wise median of each half            (float64)
per-pixel   n_b(u) = || median(first)(u) - median(second)(u) ||_2^2     summed over channels
pool        N_p(u) = max over replicate blocks b of n_b(u)
threshold   L0_noise_threshold_p = max over all pixels u of N_p(u)
compare     a pixel enters the mask iff r(u) > L0_noise_threshold_p   (strict)
```

The estimator is a **technical-noise envelope**: the largest per-pixel residual ever observed
between two pure-noise views of the same static absent scene. A pixel therefore enters the
support mask only if the present/absent residual exceeds every noise magnitude the renderer
produced anywhere in that scene. It carries **no tunable constant** — no quantile, no
multiplier, no floor — which is precisely why it cannot be nudged to make a material pass.

Edge cases, frozen:

- `n < 2` settled absent frames in a block: `P0_TECHNICAL_FAIL`, never a relaxed split.
- A threshold of exactly `0.0` (a perfectly reproducible renderer) is admissible; the strict
  `>` then admits every pixel carrying any residual at all.
- An empty or all-pixel mask is `RVE_MASK_DEGENERATE`. It is a technical failure to be
  reported and retried under the identical procedure, **never** grounds to relax the rule.

#### 7.10d Background tolerance (frozen)

Scale-normalised and noise-relative, so one rule is meaningful at all nine placements rather
than an arbitrary raw-energy constant. For each `(c, p, b)`:

```
B(c,p,b)     = sum over u NOT in M_p of || P_lin(c,p,b,u) - A_lin(c,p,b,u) ||_2^2
N_out(c,p,b) = the same outside-mask energy between that cell's own deterministic
               split-half ABSENT medians (§7.3 step 5 split, restricted to u not in M_p)
PASS  iff    B(c,p,b) <= 4.0 * N_out(c,p,b)
```

`BACKGROUND_TOLERANCE_RATIO = 4.0`, frozen. Derivation: the split-half reference compares two
medians of `n/2` frames while the present/absent contrast compares two medians of `n` frames,
so the reference already carries roughly twice the energy of the noise it bounds; a ratio of 4
therefore leaves about eightfold energy headroom against a false technical failure, while a
genuine background change (a wrong wall material, a light level, a camera slip) is orders of
magnitude larger. The reference population is that cell's **own absent frames** — technical
noise — so the rule is candidate-independent by construction.

Edge case, frozen: when `N_out(c,p,b) == 0` exactly — a perfectly reproducible background — the
gate becomes `B <= 0`, i.e. outside-mask byte-for-byte identity is required. That is the
correct reading, not a degenerate one: with demonstrably zero renderer noise, *any* outside-mask
difference is a real scene change. No epsilon is added.

Once frozen this tolerance is **never raised or lowered** because candidate measurements failed
it; a failure is `RVE_BACKGROUND_TOLERANCE_EXCEEDED` and invalidates that block.

#### 7.10e Sentinels — prospective selection and envelope derivation (frozen)

**Selection**, deterministic and prospective: the left, centre and right of the frozen placement
set, i.e. placement indices `0, 4, 8` (world-x `-2.0`, `0.0`, `+2.0`). Selection consumes no
measurement whatsoever.

**Envelope derivation** — the *formula* is frozen here; the *numbers* can only exist after P0
and are bound in P2. For sentinel placement `p` and condition `c`, over the P0 replicate blocks:

```
centre_p(c)  = median over blocks b of RVE(c,p,b)
range_p(c)   = max over b of RVE(c,p,b) - min over b of RVE(c,p,b)
half_p(c)    = 2.0 * max( range_p(c), 0.15 * centre_p(c) )
envelope     = [ max(centre_p(c) - half_p(c), 0.0) , centre_p(c) + half_p(c) ]
```

`K = 2.0` is a twofold allowance on the observed P0 replicate range. The floor
`0.15 * centre` reuses the already-frozen replicate-CV bound of §7.5 so that two exactly equal
P0 replicates cannot produce a zero-width envelope that every later production batch would
fail. The same formula applies to every eligible sentinel; none is fitted individually.

#### 7.10f Capture liveness contract (frozen, replacing the byte-duplicate rule)

The v1.5 rule — "byte-identical consecutive frames beyond the frozen tolerance invalidate the
block" — is **unsound and is withdrawn**. P0 deliberately captures a static settled scene, and
an opaque production condition can legitimately render pixel-identical frames while a fully
hidden target moves. Under the withdrawn rule the correct observation was indistinguishable
from a frozen renderer, so the rule would have invalidated valid science and could not have
detected the failure it was written for.

Liveness is instead proven where it is actually observable. **Required evidence, every capture
unit:**

- the server tick advances monotonically, by exactly one per recorded step;
- one accepted frame per expected tick; tick identities complete and unique — no missing tick,
  no duplicated tick identity;
- the capture process is alive for the whole unit;
- every framebuffer read succeeds and is exactly 640 × 360 RGB;
- every frame hash is recorded as **diagnostic evidence** (never, by itself, a verdict).

**Transition probes.** At every point where the image *must* change, the framebuffer is required
to demonstrate the transition after settling:

- target present → absent, and absent → present;
- a wall material change;
- a mandatory controlled pre-capture liveness probe on every unit.

```
CAPTURE_STALE_FRAME  iff  the server tick advanced across a known scene transition
                          AND the settled framebuffer is byte-identical across it
```

Within one genuinely static settled state, repeated framebuffer bytes are **not** evidence of
staleness and must not invalidate the block. A tick that fails to advance, or a duplicated or
missing tick identity, is `TIMING_CARDINALITY_MISMATCH`.

### 7.11 P0 present/absent scene semantics (frozen)

The absent state is `Scene.NO_SHEEP` (§7.2), and it changes **only** target presence:

| Condition | PRESENT | ABSENT |
|---|---|---|
| `L0` | no wall, target present | no wall, target absent |
| each of the 12 candidates | that exact wall material, target present | **that same wall material**, target absent |
| `minecraft:stone` | stone wall, target present | stone wall, target absent |

Between `P` and `A` of one `(c, p, b)` cell the wall cells, the wall material, the camera pose,
the lighting and the weather are **identical**; only target presence differs. Any implementation
in which the absent state removes or substitutes the wall is an **engineering defect**, not a
condition: it would make `D(c,p,b)` measure the wall rather than the target, silently
destroying the entire RVE ladder. Wall presence is determined by the condition; target presence
is an independent axis.
"""

edit(
    "\n---\n\n## 8. Production, extraction, and analysis authority",
    SECTION_710 + "\n---\n\n## 8. Production, extraction, and analysis authority",
)


def amend_markdown() -> None:
    text = MD.read_text(encoding="utf-8")
    for old, new in REPLACEMENTS:
        if text.count(old) != 1:
            raise SystemExit(
                f"AMENDMENT_PRECONDITION_FAILED: expected exactly one occurrence of:\n"
                f"---\n{old[:300]}\n---\nfound {text.count(old)}"
            )
        text = text.replace(old, new)
    MD.write_text(text, encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------
# Machine authority
# --------------------------------------------------------------------------


def amend_machine() -> None:
    authority = json.loads(JS.read_text(encoding="utf-8"), object_pairs_hook=OrderedDict)
    if authority["authority_version"] != "v1.5":
        raise SystemExit(
            f"AMENDMENT_PRECONDITION_FAILED: predecessor is "
            f"{authority['authority_version']!r}, expected 'v1.5'"
        )

    p0 = authority["p0_rve"]
    p0["placements"] = 9
    p0["placement_coordinates_lane_x"] = list(PLACEMENT_X)
    p0["placement_lane_y"] = 4.0
    p0["placement_lane_z"] = 6.0
    p0["placement_order"] = "ASCENDING_LANE_X"
    p0["placement_representation"] = "IEEE754_FLOAT64"
    p0["placements_sha256"] = placements_sha256()
    p0["placement_source"] = "PHASE0_SCRIPTED_CALIBRATION_POSITIONS"
    p0["superseded_temporary_placements"] = {
        "construction": "ENDPOINT_INCLUSIVE_UNIFORM_PARTITION_OF_[-3.49,4.49]",
        "placements_sha256": (
            "a3deb1df619d39ac4f1df1d54c082f61115b9a11bbbcab85b12f799755e03f6e"
        ),
        "status": "SUPERSEDED_ENGINEERING_EVIDENCE",
        "may_enter_p2": False,
        "reason": (
            "an implementation-side prospective derivation made while the Phase 0 "
            "scripted positions were not yet materialised in the authority; it "
            "never captured a frame"
        ),
    }

    p0["bootstrap_seed"] = p0_bootstrap_seed()
    p0["bootstrap_seed_derivation"] = (
        'int.from_bytes(SHA256("MINEOCCLUDE_EXPERIMENT_III_P0_BOOTSTRAP_V1|" + '
        'PHASE0_DESIGN_SHA256).digest()[:8], "big") & ((1<<63)-1)'
    )
    p0["bootstrap_seed_domain"] = P0_BOOTSTRAP_DOMAIN
    p0["bootstrap_seed_binds_to"] = "PHASE0_DESIGN_SHA256"
    p0["bootstrap_seed_stable_across_operational_amendments"] = True
    p0["bootstrap_generator"] = "numpy.random.default_rng"

    p0["l0_noise_threshold_rule"] = OrderedDict(
        [
            ("name", "L0_ABSENT_TECHNICAL_NOISE_ENVELOPE"),
            ("frames_consumed", "SETTLED_ABSENT_FRAMES_OF_L0_AT_THAT_PLACEMENT_ONLY"),
            ("candidate_frames_consumed", False),
            ("mineworld_output_consumed", False),
            (
                "split_assignment",
                "ASCENDING_CAPTURE_INDEX_WITHIN_BLOCK; first=frames[0:n//2], "
                "second=frames[n-n//2:n]; for odd n the middle frame is in neither half",
            ),
            ("per_half_statistic", "COORDINATE_WISE_MEDIAN"),
            (
                "residual",
                "n_b(u) = ||median(first)(u) - median(second)(u)||_2^2 summed over channels",
            ),
            ("aggregation_over_blocks", "MAX"),
            ("aggregation_over_pixels", "MAX"),
            ("dtype", "float64"),
            ("comparison_operator", "STRICTLY_GREATER_THAN"),
            ("tunable_constants", 0),
            ("minimum_frames_per_block", 2),
            ("below_minimum_blocker", "P0_TECHNICAL_FAIL"),
            ("zero_threshold_admissible", True),
            ("degenerate_mask_blocker", "RVE_MASK_DEGENERATE"),
            ("frozen_before_any_candidate_is_scored", True),
            ("one_threshold_per_placement", True),
            ("shared_by_every_candidate", True),
        ]
    )

    p0["background_tolerance"] = "NOISE_RELATIVE_OUTSIDE_MASK_GATE_V1_6"
    p0["background_tolerance_rule"] = OrderedDict(
        [
            ("statistic", "B = sum over u NOT in M_p of ||P_lin - A_lin||_2^2"),
            (
                "reference",
                "N_out = the same outside-mask energy between that cell's own "
                "deterministic split-half ABSENT medians",
            ),
            ("reference_population", "THAT_CELLS_OWN_ABSENT_FRAMES"),
            ("ratio", BACKGROUND_TOLERANCE_RATIO),
            ("pass_operator", "B <= ratio * N_out"),
            ("zero_reference_behavior", "N_out == 0 REQUIRES B == 0 EXACTLY; NO EPSILON"),
            ("dtype", "float64"),
            ("candidate_independent", True),
            ("tuned_from_candidate_ranking", False),
            ("tuned_from_selected_ladder", False),
            ("tuned_from_mineworld_output", False),
            ("may_be_lowered_after_failure", False),
            ("failure_blocker", "RVE_BACKGROUND_TOLERANCE_EXCEEDED"),
        ]
    )

    p0["sentinel_placement_indices"] = list(SENTINEL_INDICES)
    p0["sentinel_selection_rule"] = (
        "DETERMINISTIC_COVERAGE_LEFT_CENTRE_RIGHT_OF_THE_NINE_FROZEN_PLACEMENTS"
    )
    p0["sentinel_selection_is_outcome_independent"] = True
    p0["sentinel_envelope_rule"] = OrderedDict(
        [
            ("centre", "MEDIAN_OVER_P0_REPLICATE_BLOCKS_OF_RVE"),
            ("range", "MAX_MINUS_MIN_OVER_P0_REPLICATE_BLOCKS_OF_RVE"),
            ("k", SENTINEL_ENVELOPE_K),
            ("floor_fraction_of_centre", 0.15),
            ("floor_source", "THE_ALREADY_FROZEN_REPLICATE_CV_BOUND_OF_7_5"),
            ("half_width", "k * max(range, floor_fraction_of_centre * centre)"),
            ("envelope", "[max(centre - half_width, 0.0), centre + half_width]"),
            ("inputs", "P0_REPLICATE_VARIATION_ONLY"),
            ("formula_frozen_before_p0", True),
            ("numeric_envelope_materialized_after_p0", True),
            ("bound_in", "P2"),
            ("same_formula_for_every_sentinel", True),
        ]
    )

    authority["capture_liveness_contract"] = OrderedDict(
        [
            ("schema", "mineocclude-experiment-iii-capture-liveness-v1"),
            ("supersedes", "UNIVERSAL_BYTE_DUPLICATE_STALENESS_TOLERANCE"),
            (
                "withdrawn_rule",
                "byte-identical consecutive frames beyond the frozen tolerance "
                "invalidate the block",
            ),
            (
                "withdrawal_reason",
                "unsound for a deliberately static settled scene (P0) and for an "
                "opaque condition with a fully hidden moving target (L4): the "
                "correct observation was indistinguishable from a frozen renderer",
            ),
            (
                "required_evidence",
                [
                    "SERVER_TICK_MONOTONIC_STEP_ONE",
                    "ONE_ACCEPTED_FRAME_PER_EXPECTED_TICK",
                    "TICK_IDENTITIES_COMPLETE_AND_UNIQUE",
                    "CAPTURE_PROCESS_ALIVE",
                    "FRAMEBUFFER_READ_SUCCEEDED",
                    "FRAMEBUFFER_DIMENSIONS_640x360",
                    "FRAME_HASH_RECORDED_AS_DIAGNOSTIC",
                ],
            ),
            (
                "transition_probes",
                [
                    "TARGET_PRESENT_TO_ABSENT",
                    "TARGET_ABSENT_TO_PRESENT",
                    "WALL_MATERIAL_CHANGE",
                    "MANDATORY_PRE_CAPTURE_LIVENESS_PROBE",
                ],
            ),
            (
                "stale_rule",
                "CAPTURE_STALE_FRAME iff the server tick advanced across a known "
                "scene transition AND the settled framebuffer is byte-identical "
                "across it",
            ),
            ("repeated_bytes_within_one_static_state_is_stale", False),
            ("frame_hash_alone_is_a_verdict", False),
            ("tick_failure_blocker", "TIMING_CARDINALITY_MISMATCH"),
            ("stale_blocker", "CAPTURE_STALE_FRAME"),
        ]
    )

    p0["present_absent_scene_semantics"] = OrderedDict(
        [
            ("absent_state", "Scene.NO_SHEEP"),
            ("wall_presence_determined_by", "CONDITION"),
            ("target_presence_is_an_independent_axis", True),
            ("wall_material_identical_between_present_and_absent", True),
            ("wall_cells_identical_between_present_and_absent", True),
            ("camera_identical_between_present_and_absent", True),
            ("lighting_identical_between_present_and_absent", True),
            ("only_target_presence_differs", True),
            (
                "absent_state_removing_or_substituting_the_wall",
                "ENGINEERING_DEFECT_NOT_A_CONDITION",
            ),
            ("l0_absent", "NO_WALL_AND_TARGET_ABSENT"),
            ("candidate_absent", "SAME_STAINED_GLASS_MATERIAL_AND_TARGET_ABSENT"),
            ("stone_absent", "STONE_WALL_AND_TARGET_ABSENT"),
        ]
    )

    authority["authority_version"] = "v1.6"
    authority["amended_by"] = "AUTHORITY_AMENDMENT_3"
    authority["authority_amendment_3"] = OrderedDict(
        [
            ("name", "P0 operational completeness"),
            ("date", "2026-08-31"),
            ("predecessor_authority_version", "v1.5"),
            (
                "predecessor_authority_sha256",
                "3d116d9713b2c7fa705a194023e271061f712d0693618abbd991efa45437d7fb",
            ),
            (
                "predecessor_authority_freeze_commit",
                "3fd66eddfce017078b6af2774a381077759b98a0",
            ),
            ("discovery_stage", "A4_ENTRY_PRE_P0"),
            ("prospective", True),
            ("p0_frames_observed", 0),
            ("mineworld_outcomes_observed", 0),
            ("production_outcomes_observed", 0),
            ("scientific_outcomes_existed_before_amendment", False),
            ("cohort_materialized_before_amendment", True),
            ("cohort_changed_by_amendment", False),
            (
                "statement",
                "This amendment repairs deferred Phase-1 OPERATIONAL choices before "
                "P0 exists. It introduces no new scientific decision: it "
                "materialises bindings v1.5 named but never froze, and withdraws one "
                "rule that was unsound for the measurement it governed.",
            ),
            (
                "changes",
                [
                    "3a nine P0 placement coordinates frozen from the Phase 0 "
                    "scripted calibration positions",
                    "3b P0 bootstrap seed derived from PHASE0_DESIGN_SHA256",
                    "3c L0_noise_threshold_p defined as a tunable-free technical-noise envelope",
                    "3d outside-mask background tolerance defined as a noise-relative gate",
                    "3e sentinel selection frozen prospectively; envelope derivation frozen, "
                    "numbers materialised after P0",
                    "3f universal byte-duplicate staleness withdrawn, replaced by the "
                    "capture liveness contract",
                ],
            ),
            (
                "unchanged",
                [
                    "the 12-candidate roster and the frozen exclusions",
                    "the RVE formula, its aggregation and its normalization",
                    "the ladder validity zones, separations, SNR and CV bounds",
                    "the deterministic selection rule and tie-break",
                    "B = 10000",
                    "the cohort, folds, target rows, FIR kernels and q grid",
                    "every statistic and analysis family",
                ],
            ),
            ("iii_a_scientific_design_changed", False),
            ("iii_b_scientific_design_changed", False),
        ]
    )

    with io.open(JS, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(authority, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def main() -> int:
    amend_markdown()
    amend_machine()
    print(f"P0_BOOTSTRAP_SEED={p0_bootstrap_seed()}")
    print(f"P0_PLACEMENTS_SHA256={placements_sha256()}")
    print("AMENDMENT_3_APPLIED=true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
