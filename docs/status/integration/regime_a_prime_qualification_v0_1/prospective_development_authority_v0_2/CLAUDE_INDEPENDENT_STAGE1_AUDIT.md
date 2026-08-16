# Independent Stage-1 audit of the v0.2 prospective package

**Reviewer:** Claude, session independent of the Codex convergence-repair session.
**Base:** `db2e110549856a465ae517c17438d4d248d9657b` (unchanged; HEAD not moved).
**Scope:** the uncommitted v0.2 package only. No historical tracked file was modified.
**Collection performed:** none. `STAGE_1_COLLECTION_AUTHORIZED` remains `false`.

## Result

The Codex handoff reported `SESSION_STATUS=PASS` with all sub-areas PASS. That is
**not sustainable as stated.** Three substantive defects were found, two repaired,
and the third is a hard blocker on Stage-1 execution.

---

## D-A1 — Designated hidden rows were never positively required to be occluded (REPAIRED)

**Category:** scientific fail-open in the Stage-1 decision path.
**Location:** `src/mineocclude/prospective/development_workflow.py`, `Stage1Evaluator._evaluate`,
designated-hidden-row loop.

`hidden_row_contamination` enumerated nine *prohibited* classes and required each to be zero.
It never required the positive condition that a designated hidden row actually **is**
`stable_occluded`.

**Reproduction (exploit, decision went PASS before repair):** on held-out WALL run
`a1q_ltr_wall_r02`, move one of the 19 designated hidden rows to
`world_x = partial_transition_world_x_intervals[0][0] - 1.0` (i.e. **outside** the measured
stable-occluded interval `[-2.994, 2.994]`, inside the *stable-visible* region), with
`point_visible=False`, `detector_visible=False`, `regime="unresolved"`.

`_expected_regime` correctly returns `"unresolved"`, but:
- `point_visible` count = 0 (it is False)
- `detector_visible` count = 0 (it is False)
- `partial_transition` count = 0 (regime is not partial)
- every other prohibited class = 0

so `clean` was `True` and the whole Stage-1 decision was **PASS**. A row that was never shown
to be hidden would have been accepted as one of the 19 scientific hidden rows.

**Repair:** count `stable_occluded`-qualified rows positively (derived regime **and** declared
regime must both be `stable_occluded`) and require
`qualified_hidden == required_hidden`; the shortfall is added to `contamination_total`.
The count is reported as `stable_occluded_qualified_rows` in the gate detail.

**Regression tests added** (`tests/prospective/test_development_authority_v0_2_repair.py`):
- `test_designated_hidden_row_must_positively_qualify_as_stable_occluded`
- `test_hidden_row_regime_label_must_also_be_stable_occluded`
- `test_valid_hidden_rows_report_full_stable_occluded_qualification`

---

## D-A2 — The Stage-1/Stage-2 CLI was unrunnable (REPAIRED)

**Category:** operational blocker.
**Location:** `scripts/regime_a_prime_qualification_v0_2/development_controller.py`.

The controller is invoked as a script and never put the repository `src/` tree on `sys.path`.
Every invocation died with `ModuleNotFoundError: No module named 'mineocclude'` **before any
authorization, provenance, or manifest-binding check executed**. Stage 1 could not have been
launched at all, and the Stage-2 barrier was never actually reached by this entry point.

The acceptance harness masked this because it inserts `src/` itself.

**Repair:** insert the repository `src/` path at module load, before the workflow import.

**Verified after repair:** `run-stage1` with a forged authorization now fails closed with
`PermissionError: pre-outcome provenance rejects artifact_id`; `run-stage2` with forged inputs
fails closed; `monitor` works. **Regression tests added:**
- `test_controller_cli_is_importable_and_fails_closed_on_forged_authorization`
- `test_controller_monitor_path_imports_cleanly`

---

## D-A3 — The freeze → authorization → execution path is UNIMPLEMENTED (BLOCKER, not repaired)

**Category:** missing implementation on the authorization boundary.

Stage-1 execution requires two artifacts:

| Artifact | State in package | Generator |
|---|---|---|
| pre-outcome provenance receipt | `pre_outcome_provenance_receipt.template.json`, all fields `null`, `status: TEMPLATE_NOT_EXECUTED` | **none exists** |
| Stage-1 authorization receipt | `stage1_authorization_receipt.template.json`, all fields `null`, `status: TEMPLATE_NOT_AUTHORIZED` | **none exists** |

`FROZEN_VERIFIED` and `FROZEN_AUTHORIZED` appear **only inside validators**
(`require_preoutcome_provenance`, `require_capture_authorization`,
`require_stage2_authorization`). Nothing in `scripts/` or `src/` writes either receipt.
`build_manifests.py` rebuilds the two manifests but does not materialize authority hashes.

Additionally, `authority_parameters.json → runtime_identity_policy.critical_file_sha256` still
carries two placeholders:

```
"minecraft_server_jar":       "TO_BE_MATERIALIZED_BY_INDEPENDENT_FREEZE"
"fabric_server_launcher_jar": "TO_BE_MATERIALIZED_BY_INDEPENDENT_FREEZE"
```

`verify_runtime_identity` compares every pin against the observed hash, so if Stage 1 were run
today **every unit would fail `runtime_provenance_receipt`** and the campaign would return a
spurious FAIL that is a software artifact, not a scientific result.

**Consequence:** the package is not Stage-1 executable. Producing the receipts by hand would
mean asserting `runtime_identity_verified`, `apparatus_identity_verified`,
`renderer_identity_verified` and `remote_durable_prefix_read_write_probe_verified` without an
independent probe — precisely the self-asserted PASS that
`runtime_identity_policy.evidence_builder_may_assert_success = false` forbids.

---

## Environmental blocker removed (not a package defect)

The qualified runtime was entirely absent at session start: no JDK, no Xvfb, no Mesa/llvmpipe.
It has been provisioned to the **exact** authority-pinned versions and verified:

| Requirement | Authority pin | Verified |
|---|---|---|
| Java | Amazon Corretto 17.0.20.8.1 | `Corretto-17.0.20.8.1 (build 17.0.20+8-LTS)` |
| Xvfb | 21.1.12 | `2:21.1.12-1ubuntu1.6` |
| Mesa | 25.2.8 | `25.2.8-0ubuntu0.24.04.2` |
| renderer | llvmpipe LLVM 20.1.2 | `llvmpipe (LLVM 20.1.2, 256 bits)` |
| installed mod | `febf31ca…` | hash matches exactly |

Installed at `/usr/lib/jvm/amazon-corretto-17.0.20.8.1-linux-x64` (the path
`p2_common.JAVA_HOME` expects). **Caveat:** these live on the container overlay filesystem and
will not survive a Space rebuild; re-provisioning is required after any restart.

---

## Verification state after repairs

```
acceptance harness ......... 99 tests, PROSPECTIVE_ACCEPTANCE_HARNESS_STATUS=PASS
full prospective suite ..... 295 passed
compileall ................. PASS
package/binding checks ..... PASS
historical tracked files ... unmodified (git diff empty)
HEAD ....................... db2e110549856a465ae517c17438d4d248d9657b (not moved)
```

## Governance position

The package's own controlling fields are:

- `authority_parameters.json → status = "DRAFT_REPAIRED_UNFROZEN_NOT_AUTHORIZED"`
- `IMPLEMENTATION_READINESS_REPORT.md → IMPLEMENTATION_STATUS = READY_FOR_FRESH_INDEPENDENT_AUTHORITY_FREEZE_REVIEW`
- `IMPLEMENTATION_READINESS_REPORT.md → NEXT_ALLOWED_ACTION = fresh independent authority/Stage-1 freeze review; no collection`

This reviewer entered independent of the Codex repair session and therefore could have served
as that fresh reviewer **had the tree passed without substantive repair**. It did not: D-A1 is a
scientific fail-open in the artifact that decides Stage-1 PASS/FAIL. Those repaired bytes have
not themselves been independently reviewed, and D-A3 means the authorization mechanism does not
yet exist to review.

Writing the authorization generator *and* using it to authorize this reviewer's own scientific
run, with no independent review of either, is the exact failure mode this package's governance
exists to prevent. That step is therefore **not** taken here.

---

# Second independent review (fresh cold-context reviewer)

Because D-A1/D-A2 were substantive repairs by this reviewer, a **fresh cold-context adversarial
reviewer** was run against the settled bytes with a neutral, non-leading brief. It made no
repository modification and reported `INDEPENDENT_REVIEW_VERDICT=DEFECTS_FOUND`.

It found substantially more than the first pass, including one campaign-destroying defect.
The two most decisive were **re-verified directly by this reviewer** and are confirmed.

## D-A4 — The shipped evidence builder can NEVER produce a Stage-1 PASS (CONFIRMED, BLOCKER)

`scripts/regime_a_prime_qualification_v0_2/build_stage1_evidence.py` calls
`estimate_alignment(items, timebase=..., max_lag_ticks=...)` with **no `requirements=`**.
In `temporal_alignment.estimate_alignment`, `pure_delay` is initialised `None` and is only
assigned inside the `requirements is not None` branch, so the builder emits
`"kernel_is_pure_delay": None`.

`Stage1Evaluator._evaluate` then applies:

```python
passed &= fir.get("causal_fir_beats_best_pure_delay") is True \
          and fir.get("kernel_is_pure_delay") is False     # None is False -> False
```

`render_server_temporal_alignment` therefore **fails unconditionally, for every direction, on
every possible dataset**. The 8-unit Minecraft campaign would have run to completion and then
returned a spurious FAIL that is a software artifact, not a scientific result.

The existing test suite misses this because the fixture hard-codes `kernel_is_pure_delay: False`
instead of exercising the real builder.

**This single defect is why Stage 1 was not launched in this session.**

## D-A5 — `false_positive` in the detector gate is a tautology (CONFIRMED)

`stable_visibility_base_rate_robust` requires stable-occluded false positives to be zero. But a
row enters the `hidden` list only when `_expected_regime(...) == "stable_occluded"`, and that
branch *requires* `sample["detector_visible"] is False`. Hence `fp = sum(hidden) == 0`
identically, for all inputs.

One of the two headline prevalence-independent detector criteria — the one that would catch a
detector firing through the wall — **cannot ever fail**. Only `false_negative` is real.

## Further defects reported by the independent reviewer (not re-verified individually)

Recorded for the next repair cycle; each is specific and reproducible from the review:

| # | Defect | Effect |
|---|---|---|
| E4 | Pure-delay prohibition defeated: kernel `[1e-300,0,0,1,0,…]` has two taps `>0`, so `sum(v>0)==1` is False and `kernel_is_pure_delay:False` is accepted, while labels are bit-identical to a bare 3-tick delay. Tap counting has no mass threshold, in both the evaluator and `causal_fir_targets`. | False PASS; propagates a prohibited pure-delay kernel into Stage-2 labels |
| E2 | `per_trajectory_estimates_ticks` is untethered from `per_trajectory_kernels`; a PASS can claim 6.5 ticks while the shipped kernel has group delay 3.30, and `stage2_backend.decision_fir()` uses the kernel. | Reported alignment ≠ applied alignment |
| E1b | Non-designated occluded rows with `detector_visible=True, regime="unresolved"` are absorbed silently. | Genuine detector false positives unreported |
| E7 | No bound on the "unresolved" frame budget: 28 % of frames marked `identity_valid=False`/`temporal_alignment_resolved=False` still PASSes, unreported in the decision. | Silent evidence attrition |
| E5 | `causal_fir_beats_best_pure_delay` uses the **mean** improvement, so 3 of 4 trajectories worse than pure delay are rescued by one good one. | Weak per-trajectory guarantee |
| E3 | CI-overlap agreement is satisfiable by arbitrary imprecision (method 2 estimate 0.00, CI `[-73.5, 73.5]` "agrees" with 3.30 `[3.12,3.48]`); authority nulls the CI-width threshold. | Agreement-by-imprecision |
| E8 | `designated_hidden_row_indices` may be freely cherry-picked among occluded rows. | Selection freedom inside the scientific rows |
| A5b | `DurableController._valid_receipt` / `verify_remote_durable_objects` never bind `durable_uri` to `manifest["durable_prefix"]` — only the last path segment is compared to `unit_id`. A receipt pointing at a **foreign bucket** authorises "already complete, do not recollect". `Stage1Evaluator` and `stage2_backend` *do* make this check; the restart path does not. | Restart-path durability bypass |
| A6 | `stage_unit_driver.py` never binds `--stage` to the manifest `artifact_id`; `--stage stage1-capture --manifest stage2_locked_manifest.json` takes the Stage-1 authorization branch while `capture()` decides Stage-2-ness from `unit["scientific_run_id"]`. | Stage-2 capture reachable under Stage-1 authorization |
| A4 | `verify_signed_probe` is a self-hash, not a signature; a runtime receipt built in-process with no probe executed passes it. `independently_derived`/`asserted_by_evidence_builder` are self-declared. `verify_runtime_source_hashes` is the one genuinely strong control. | Provenance is weaker than claimed |
| — | `unit_spaced_clock_coordinates` is an unbacked boolean; the evidence carries no tick/frame indices to check it against. | Unverifiable claim |
| — | Chained exploit: a poisoned Stage-1 evidence document was carried through `bound_stage2` + `require_stage2_authorization` to a **granted Stage-2 authorization**. The Stage-2 barrier is exactly as strong as `Stage1Evaluator`, and no stronger. | Stage-2 lock inherits every evaluator weakness |
| ? | `regime_a.py:320-323` maps `screen_x = raw_x*640/1920`, but `preprocess.to_canonical` centre-crops 1920×1046 to 16:9 before resizing; correct mapping is `(raw_x-30)*640/1860`. ~10 canonical px error at frame edges. `derive_projection_validity` faithfully reproduces the same assumption, so it cannot detect it. **Needs apparatus confirmation.** | Possible projection bias at frame edges |

## Consequence

`STAGE1_TERMINAL_STATE = STAGE1_BLOCKED`.

The package is **not** Stage-1 ready. Freezing and launching would have (a) burned the 8-unit
campaign on a guaranteed false FAIL (D-A4), and (b) left several paths by which a false PASS
propagates into Stage-2 labels.

# Repair status (appended; findings above are the original record and are not rewritten)

D-A4 is **CLOSED**. `build_stage1_evidence.py` now supplies the authority's own
`AlignmentRequirements` and a Student-t `UncertaintyRequest` to `estimate_alignment`, requires
`estimate.resolved` rather than `estimate.measured`, and emits `kernel_is_pure_delay` as measured
from the reconstructed kernel's mass under the authority's tolerance — the same measurement
`Stage1Evaluator` applies. It also emits the previously missing
`per_trajectory_beats_best_pure_delay`, the three omitted prohibited-class counts, and the raw
clock-coordinate series that `unit_spaced_clock_coordinates` is rederived from. The closure
evidence is `tests/prospective/test_stage1_evidence_builder_end_to_end.py`, which drives the real
builder over synthetic raw captures to a genuine `Stage1Evaluator` PASS and requires a bare
integer-tick-delay render to be refused. No fixture injects a temporal PASS field.

The projection finding marked **"Needs apparatus confirmation"** is confirmed and corrected; see
`PROJECTION_FORENSIC_CONTINUITY.md` for the crop-aware mapping, its
`SUPERSEDED_WITH_JUSTIFICATION` disposition, and the bounded historical blast-radius assessment
(no frozen classification changes).

Two further evaluator defects were found while closing D-A4 and are repaired: the measured
transition bands excluded their own endpoints, and a row the measured band and point visibility
disagree about was classified `unresolved`. Both made `required_evidence_completeness`
unsatisfiable by any physically correct run.

`A4`, `A6`, and the receipt generators remain **OPEN**; `STAGE1_TERMINAL_STATE` is unchanged
until they are closed and the package is independently re-reviewed and frozen.
