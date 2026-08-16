# 11 — What Did P3 Actually Establish?

**Label: EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY.**

## 1. Frozen prospective result (unchanged, and confirmed correct)
- All three candidates completed 50/50 paired captures with zero scientific capture failures.
- C01, C02, C03 each: capture PASS, **path PASS**, **headroom PASS**, **visibility FAIL** → `FAIL_NOT_QUALIFIED`.
- Extraction, BEST-K and FULL were `NOT_REACHED` and were **correctly** never authorised.
- Terminal state `BLOCKED_REQUIRES_NEW_PROSPECTIVE_AUTHORITY`, `selected_candidate = None`,
  `next_candidate_authorized = None`. No C04.
- **Independently reproduced from durable raw data, gate for gate.** `P3_TERMINAL_RESULT_CONFIRMED = true`.

## 2. Forensic post-hoc interpretation
- The failure is **entirely** the visibility gate, and within it **precision of the pre-candidate calibration
  gate** — never recall, never the geometric component, never capture, path or headroom.
- That precision requirement compares a **point-visibility** predicate (one ray to the target's centre point)
  against an **area-visibility** predicate (any magenta blob). Over the ~1.04-block band where the centre is
  behind the occluder but part of the body is not, disagreement is **guaranteed**. Frame inspection shows the
  target **97 % visible** at the exact frame the server first labels it "occluded".
- The metric is **base-rate confounded**: the detector's true error rate was flat (0.118 / 0.104 / 0.103) while
  precision rose only because faster candidates spend fewer of their fixed 180 frames occluded. A candidate at
  ≈3.75 b/s would **pass this gate with no physical improvement whatsoever**.
- Separately and independently, the rendered frame **lags the logged state by ≈3.3 server ticks**. This is a
  genuine apparatus defect, measured directly from pixels, constant in ticks across speeds and directions.
- The frozen `HIDDEN_BOUNDS` constant, inherited from Regime A at a single speed, therefore lost its ≈0.01-block
  safety margin above C01 and produced 0 / 1 / 7 contaminated NORMAL target rows.

## 3. Direct answers

**Did the tested speed family genuinely fail?**
No — not in the sense intended. The speed family was never scientifically tested: **no neural readout was ever
run**. What failed is an instrument-agreement gate that the speed family could not have passed, and that a
faster family would have passed for the wrong reason.

**Did the intended physical regime fail?**
**No.** The intended physical regime performed exactly as designed. Motion headroom — the quantity speed was
chosen to control — **passed comfortably at the very first candidate** (min SD 0.4187 vs 0.3321 required;
median 0.5683 vs 0.4981) and increased monotonically. Occlusion was achieved. Paired NORMAL/NO_WALL trajectories
were bit-identical. The apparatus produced 150/150 clean captures.

**Did only the implemented proxy fail?**
**Yes — this is the correct characterisation.** `geometric_visible` is a proxy for "the target is hidden", and
the magenta detector is a proxy for the same thing. P3 required the two proxies to agree to 95 % precision
across a regime in which the project's own bound authority already documented a 17–19-frame disagreement run.

**Is there evidence of a software defect?**
**Yes, but not one that produced a wrong verdict.** The verdicts are correct as the gate was written. The
defects are: the unimplemented identity/timestamp ambiguity check (H8); the path gate hashing only `sheep_x`
and not re-verifying camera/cadence/tick-order (D-P1/D-P2/D-P3); the speed-blind `HIDDEN_BOUNDS` constant (H5);
and the untracked, unhashed controller (H11).

**Is there evidence of apparatus mismatch?**
**Yes — the ≈3.3-tick render/state lag (H3).** It is the most consequential finding for the wider programme:
it has been present, unmeasured, across Regime A, P2 and P3, and it means every "position at tick *t*" label
is paired with a frame showing the position at ≈*t* − 3.3.

**Is there evidence that P3's candidate space was poorly chosen?**
**Yes.** The sweep varied a parameter that had already met its target at the first candidate and that cannot
affect the binding constraint — while incidentally degrading the other half of the same gate (target-row
contamination 0 → 1 → 7).

**Is speed likely the correct control variable?**
**No.** `IS_SPEED_THE_RIGHT_REDESIGN_VARIABLE = no`. Speed correctly controls headroom, and headroom is not the
blocker. The blocker is the definition of the visibility predicate and the geometry of the occlusion boundary.

**Can existing P3 data support redesign without new capture?**
Partly — for **design**, not for **qualification**. Already recoverable at zero capture cost: geometric shadow
edges per direction; rendered-hidden edges per direction *and per speed*; silhouette half-extent w ≈ 0.6–0.8
blocks; render lag ≈3.3 ticks plus a validated method to measure it; shadow span 10.635 blocks; the base-rate
model. All of it is development-tier and permanently excluded from the confirmatory cohort.

**What absolutely requires new prospective development data?**
Any *qualification* claim. Specifically: (a) that a corrected visibility predicate actually achieves its
threshold; (b) that a lag-corrected or lag-declared apparatus produces stable dual-hidden windows; (c) any
neural readout result — layer-4 BEST-K and FULL have **never been run** under Regime A′ and remain entirely
unevidenced.

## 4. Unresolved uncertainty (deliberately not collapsed)
- The exact partition of the 1.04-block band between silhouette extent and render lag is ±0.15 blocks.
- Whether the ≈3.3-tick lag is exactly Minecraft's client entity interpolation, or that plus a capture-pipeline
  offset, is **not** established — the mechanism is inferred, the magnitude is measured.
- The blast radius of the lag on **P2's** headline numbers (RMSE 0.1660, macro R² 0.7907) has **not** been
  re-derived here. P2's readout sees 16 context frames and could plausibly have learned the shifted mapping, so
  P2's result is not necessarily invalid — but it is now best described as *"position ≈3.3 ticks ahead of the
  most recent frame"*, which is partly motion extrapolation rather than pure instantaneous readout. **This
  should be re-examined before P2 is cited as the basis for any confirmatory threshold.**
- Regime A's postmortem conclusion (neural readout beaten by trivial baselines) was reached on data carrying
  the same uncorrected lag. Whether that changes the postmortem is **not** assessed here.
