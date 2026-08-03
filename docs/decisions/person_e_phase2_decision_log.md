# Person E Phase 2 decision log

Status: **proposed, not signed off.** Every decision below was taken by Person E
while building the Phase 2 measurement foundation and is recorded here so it can
be confirmed or overruled by the named approver. None of these decisions is
claimed as team-approved, and none of them may be cited as a frozen contract
until the approver accepts it.

This log is additive to `docs/decisions/person_e_phase1_decision_log.md`, which is
signed off at `integration/mvp@80d41c5ca0e341263a7b0c683fae4b51be376c55` and must
not be edited in place. Phase 2 decisions carry `PE-P2-*` identifiers so they
cannot be confused with the Phase 1 numbering or with the `PE-OWN-*` ownership
questions.

## Sources of authority

- Detector calibration dataset shape:
  `validate_detector_calibration_dataset` in `src/mineocclude/vision/calibration.py`.
- Frame decoding: `src/mineocclude/vision/png_decode.py`.
- Marker colour gates: `MARKER_COLOUR_GATES` in `src/mineocclude/vision/markers.py`.
- Dependency policy: `requirements.txt`, which is deliberately empty until
  MineWorld's own dependencies are pinned.

---

## `PE-P2-001` — Frame decoding uses the standard library only

**Decision.** Person E decodes Person C's delivered PNG frames with a
first-party, standard-library-only decoder (`zlib` and `struct`), not with
Pillow, imageio, OpenCV, or any other third-party image library.

**Why.** Two constraints force it.

1. `requirements.txt` is intentionally empty: the project does not pin
   third-party packages until MineWorld's own dependency set is fixed. Taking an
   image library now would either pin a version that later conflicts, or leave an
   unpinned dependency that reproduces differently on a teammate's machine.
2. All thirteen files in `scripts/` are standard-library only. A measurement
   script a teammate cannot run without first installing something is an
   operations-and-measurement failure, which is precisely the role that is
   supposed to guarantee reproducibility.

**Scope.** The decoder accepts exactly the profile Person C ships — 8-bit,
non-interlaced, truecolour RGB or opaque RGBA — and rejects every other profile
rather than guessing at it. Partially transparent pixels are rejected rather than
composited, because a composite would silently invent pixel values. Chunk CRCs
are verified, so byte corruption surfaces at decode time rather than later as an
unexplained detector miss.

**Evidence.** Decoded output is byte-identical to **both** Pillow and imageio
across all 72 delivered frames — 72/72 against each library, zero mismatches.
That is a genuine cross-check: two independent mature implementations agree with
this one on every frame that will be used scientifically.

**Cost, stated honestly.** Roughly 162 ms per frame, which is far slower than a
C-backed library. At 72 frames this is irrelevant. If frame counts later reach the
thousands, this decision should be revisited rather than endured.

**Approver.** Person A, as the owner of runtime and environment provenance.
Confirm that a standard-library decoder is acceptable for artifact-bearing
workflows, or name the image library that should be pinned instead.

---

## `PE-P2-002` — White ground-marker saturation ceiling tightened from 0.18 to 0.10

**Decision.** The `white` entry of `MARKER_COLOUR_GATES` uses a saturation
ceiling of **0.10**, replacing the prototype's 0.18.

**Why.** The white marker is separated from the scene by near-zero saturation
rather than by hue, so its saturation ceiling is the only bound doing real work.
The competing scenery is the horizon row, where grass blends into sky and
produces a desaturated blue-green. At a 0.18 ceiling that horizon blend is
admitted as a rival blob of comparable size, which either triggers the ambiguity
rejection or, worse, wins the largest-blob pick and yields a confidently wrong
marker point.

**Evidence — measured, not chosen for convenience.** Across all six layouts:

| quantity | measured saturation |
|---|---|
| white marker pixels | 0.035 – 0.046 |
| horizon blend | 0.169 |

A 0.10 ceiling clears the marker by a factor of 2.2 and excludes the horizon by a
factor of 1.7. It sits in the gap between two well-separated populations rather
than being tuned until a particular frame passed.

**Leakage.** The threshold was selected using **calibration-split, no-sheep
frames only**. No held-out frame and no U4 outcome influenced it. This is the
rule from Phase 1 decisions 10 and 15, and it is why the value can be frozen at
all.

**Regression protection.** `tests/vision/test_markers.py::TestMarkerGates::
test_white_saturation_ceiling_excludes_the_horizon` reads the ceiling from the
module and asserts that the marker's 0.037 is still admitted while the horizon's
0.172 is excluded, and that the horizon sits below the superseded 0.18 — that is,
that the horizon is exactly the thing the tightening newly excludes. Loosening
the ceiling back toward 0.18 fails that test.

**⚠️ Scope limit — this is not the magenta sheep detector.** `MARKER_COLOUR_GATES`
governs the four coloured **ground-plane geometry markers** used to fit
homographies. It has nothing to do with the magenta **sheep** detector in
`src/mineocclude/vision/magenta.py`. The Phase 1 decision log lists "HSV ranges,
morphology, and valid blob-area limits" under *deliberately pending decisions*,
awaiting Person C's calibration and held-out visible/negative frames. **That item
remains pending and is not resolved by this record.** Nothing here should be read
as Person E quietly freezing the sheep-detector thresholds.

**Approver.** Person C, as the owner of capture, layouts, and markers. Confirm
that the marker blocks are the ones these gates describe and that no layout uses
a white-adjacent block elsewhere in frame. Person B is a consumer only.

---

## Related open item, recorded here so it is not lost

`layout_02`'s yellow marker blob runs into image column 0. Its declared
`marker_visibility` of "all 4 in-frame, unoccluded" is therefore not accurate for
that layout. A clipped marker's centroid is pulled inward and biases the
homography while still producing a plausible-looking number, so the detector
rejects it rather than reporting it. This is not fixable by tuning and is not
Person E's decision to resolve: it needs either a re-capture or an explicit
exclusion ruling from Person C. Tracked as a blocker, not as a decision.
