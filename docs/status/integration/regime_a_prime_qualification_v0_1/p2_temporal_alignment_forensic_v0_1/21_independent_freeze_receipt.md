# 21 — Final Independent Freeze Receipt

**Review date (UTC):** 2026-08-16

**Base, pre-review HEAD, and pre-review upstream:** \
`351da852965bb20f89fe848bdef71703c34f0705`

**Accepted scope:** only
`docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/`,
`src/mineocclude/prospective/`, and `tests/prospective/`. Generated
`__pycache__` files are excluded.

## Independent acceptance

- `FREEZE_STATUS=PASS`
- `PHASE_A_ADVERSARIAL_STATUS=PASS`
- `R1=PASS`: correct bytes, Git mode, and expected commit binding verified;
  index-only/worktree-only mode changes, staged/unstaged byte changes,
  staged-only absent paths, deletion, and wrong expected commit all failed.
- `R2=PASS`: `episode_id=True`, string seed, float count/index,
  `respawn_count=True`, non-finite values, and Boolean integer impostors could
  not produce `passed=true`.
- `R3=PASS`: 2 in-support plus 98 outside failed a 100-sample requirement;
  malformed/non-finite observations failed closed; endpoints and gaps used only
  in-support evidence.
- `R5=PASS`: ten-tick, irregular, duplicate, non-monotonic, and missing tick
  coordinates failed closed; unit spacing resolved; FIR mapping is
  `index+1-lag`; retained arrays are detached/read-only; requirements are
  caller supplied.
- `R6=PASS`: `point=false, any_silhouette=false, fraction=1.0` resolved to
  `UNRESOLVED`; no policy returned `UNADJUDICATED`; no predicate received
  implicit precedence.
- `ANALOGOUS_FIXES_VERIFIED=PASS`: in-support endpoint spans, immutable
  retained alignment evidence, and the corrected FIR state-to-render mapping
  all passed exact regressions.

## Scientific reproduction

- Physics-only alignment rerun over 12 existing trajectories:
  `GROUP_DELAY_TICKS=3.363631073825902`;
  Student-t interval
  `[3.1850024634276997, 3.5422596842241045]`;
  trajectory bootstrap
  `[3.2187625523392898, 3.522819291615068]`.
  The causal FIR response is spread, not a pure delay. Alignment estimation
  imports no decoder performance and uses no neural metric.
- The regenerated impulse receipt has identical units, kernels, headline
  estimates, and intervals. Its sample-SD serialization differs from the
  candidate receipt by one binary64 ULP
  (`0.28114122212750625` versus `0.2811412221275063`) under the current
  runtime's `statistics.stdev`; this does not affect any headline value or
  conclusion.
- Frozen P2 harness control reproduced historical BEST-K RMSE
  `0.166027` and FULL RMSE `0.166577`. The required corrected-label rerun
  reproduced BEST-K RMSE `0.077802`, macro R² `0.955541`, FULL RMSE
  `0.106828`, and macro R² `0.916702`, matching the stored exact values
  `0.07780238881820632`, `0.9555412043446805`,
  `0.10682847906619956`, and `0.9167019115351303`.
  `P2_CONCLUSION=VALID_WITH_NUMERIC_REVISION`.
- All 25 locally reused P2 activation arrays matched their frozen manifest
  SHA-256 values.
- Direct Regime A rerun was byte-identical to
  `regime_a_blast_radius.json`: BEST-K RMSE
  `0.3279604464581371`, FULL RMSE `0.39275371161349065`, time-only RMSE
  `0.14083792313865104`, and training-mean RMSE
  `0.16882992428099125`. FULL macro R² remains
  `-0.8693120006803948`; both trivial baselines beat both neural readouts.
  `REGIME_A_CONCLUSION_STABLE=yes` and the historical substantive result
  remains `FAIL_NO_DEFENSIBLE_DECODING`.

## Neutrality, fail-closed, and tests

- `AUTHORITY_NEUTRALITY_STATUS=PASS`: no reusable module embeds visibility
  thresholds, hidden/calibration bounds, required N, required
  speeds/directions, lag tolerances, RMSE/R² gates, or confirmatory thresholds.
  The fixed `1e-9` camera comparison is an encoding tolerance for an
  authority value serialized to ten decimal places, not a scientific gate.
- `FAIL_CLOSED_STATUS=PASS`: invalid, missing, ambiguous, contradictory, or
  insufficient evidence cannot produce PASS, `verified=true`, a stable
  regime, qualification, or `fully_covered=true`.
- `python3 -m pytest tests/prospective/ -q`:
  `196 passed in 2.29s`.
- `python3 -m compileall -q src/mineocclude/prospective tests/prospective`:
  PASS (no output).
- No historical P1/P2/P3 result, authority, P3 terminal freeze artifact, or
  other tracked file differs from the immutable base.

## Preserved provenance caveats

- D-08 is permanent and unrepairable: the historical P3 controller was
  untracked at execution. Its current hash cannot retroactively prove the
  executed bytes. This freeze does not upgrade that claim.
- The prior S3 preservation receipt compared coverage, size, ETags, and 162
  unit manifests, but did not download and independently recompute SHA-256 for
  the full 2.45 GB raw-object payload. This freeze preserves that limitation.
- Reproduction reused already-downloaded existing evidence; it performed no
  capture or collection.

## Authority state

- `NEW_PROSPECTIVE_AUTHORITY_FROZEN=false`
- `NEW_CAPTURE_AUTHORIZED=false`
- `REGIME_A_PRIME_COLLECTION_AUTHORIZED=NO`
- `CONFIRMATORY_COLLECTION_AUTHORIZED=false`
- `NEXT_ALLOWED_ACTION=draft corrected prospective authority + Stage-1 qualification package; no collection yet`

## Accepted payload SHA-256

The freeze commit binds this receipt. The manifest below hashes every other
accepted payload file; a manifest cannot include its own final digest without
self-reference.

```text
6d273016dc5f350a387d6347b8200978381681a6f67c5834a95a1ceb4a4824b5  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/00_checkpoint_receipt.json
9ebe71c4ced12382a66ee952547186439e8625b29337abb56647eda26c72c924  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/01_evidence_inventory.json
4373712a2ae9606126e8ac08ac224e07afffe3da267f8f4c56d8ac58bf024cb1  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/02_temporal_lag_reproduction.md
44dc8f205598fe5e0b554a875b9beecb7db9408cb196b81caeb2b2ce466c3d0c  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/03_clock_domain_trace.md
ab8814f62228e7d62441b3f0caf6b895289590e36ec2cb5385fda4530a0e0245  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/04_p2_alignment_trace.md
bf918fede30b5e5082ace938ae75f948f52a60789de518ff67f499f5c7087add  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/05_p2_corrected_metrics.json
283442a3c47ad397bd22b71ada890f5c983fa619eeb07f3fabc2d8de1b637c48  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/06_p2_impact_analysis.md
6d6c9a402f84fe4c2da08b12c8d989b9c53f7705a0488376924d5201cd51df3d  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/07_future_threshold_blast_radius.md
e2705640b9030b0b00ef4b2a2b9337387b865a27db04dce5b6774127fb1f448a  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/08_regime_a_blast_radius.md
326cf09278fd5c863b64c6e2d4b6de119ce23ff3f8425a33e0fedb92ef7bc377  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/09_run_identity_audit.md
8eff1d53fcc7adf9bd8052e8e3804594f1c4a41b0d8ed62e3164a6aa7af70532  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/10_path_gate_audit.md
6def1f6c77307ecdb61cbb08dae4fb4f79eb5300cf909fbcda9261b9590eaf75  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/11_defect_register.md
c9a251d8cf10bd60c2761d115cd5c04943dde98d18fb3838195af7d1199b5898  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/12_repair_summary.md
5d23d94f82384ccee747e9088afaceaba8ab80ab11427475a8c7ec04cfb3bdc1  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/13_repair_validation.md
5d86797ce4b0973317c50315fb59c40b6cb838e2fdf517fb487406068ace5f79  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/14_redesign_readiness.md
2c047c664c8b994935f9a9ac0f9ffecb8276db0e492eec222677aad78eff2106  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/15_codex_blocker_repair.md
d94c3d7d990516346336967c58ac9f6a35c2217a0ee2c7c4e7c262df141f5f2a  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/16_authority_neutrality_audit.md
1b4dc9de3dac3509f472492a9540497f8045f14e7993d7756572e0946ed521a1  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/17_fail_closed_audit.md
8c91f0aaa9b9633c25ac531a445b7ee90f891d8318c02807096b0f979c32cfb5  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/18_regime_a_direct_reanalysis.md
b7010549d3c979ae9ab4c35857e77039b765b17b7b8e7740399030265adf818d  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/19_repair_acceptance_readiness.md
bcefe1c3ed8ac4bfdf7aaf46b9c10183b4199475095174e96a7ffa8e5ddeadde  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/20_bounded_repair_2.md
148acc202e0cb2386669f394f27785ec4dbd2953b8f94fe21934f80a79997702  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/AUDIT_SUMMARY.md
7fb7c5a98ba340a9c43a2dcdbd3f9887ddd0220b6da60c1c24286bb4b80da7e2  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/audit_scripts/b00_checkpoint_receipt.py
77e365ae0f5fe340e6da044732173354dea8184de2fe313818b368bc09373fd8  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/audit_scripts/b01_evidence_inventory.py
0cd0f0d1680497e86561aa8b20c907ea7396ee94569c3b0407f89af46abab055  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/audit_scripts/b02_lag_multimethod.py
9a12b48ea9356c3b2d29e33c0a5a9b4d71f362630fa50ac5953f35ea1782a52f  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/audit_scripts/b03_impulse_response.py
89918a7ee55de8a83f5e83a5c34668027812be1506b5b75f1f7048f3e08e149c  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/audit_scripts/b05_p2_corrected_metrics.py
3baa0e004c1d567166b047ff2560652a31f2efea63dfa7f713623249379174b0  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/audit_scripts/b06_label_variance_control.py
a92fe0c59fc28bf0413a3bfe75a597e52f51d8fb97ad84df00b2e9b4cae01bdf  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/audit_scripts/b08_regime_a_blast_radius.py
c94c337189abcba51c99d0fa1e859fdde8e884f2bb5678d1b135fd307e30ac6f  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/audit_scripts/b10_path_gate_blast_radius.py
08191d7519492713cec60b79cab79c3a7502b554dbc0efeba19a3618c6cd8d45  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/impulse_response_raw.json
04a68fb4ac75512b43ef1a64df8286d1a481c35fba06cc0219a75dfba16eac54  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/label_variance_control.json
e41b21fd744438355f16d8c4a7551a8a89e8640a46a9a20d92efa4e3c748e116  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/lag_multimethod_raw.json
955a07b194b7331a2cb8b320eda72ac4d6b57070d0708bd10ef0114c5fe6fccf  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/p2_recompute.log
3bee842d18675f255e6c3fc9033cf488422981da9b3713b348d7de2ab5da9cf9  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/path_gate_blast_radius.json
c2f4e443b6c6ffda73df9991c305c38c89a44b414381396e471bf549c08413ba  docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/regime_a_blast_radius.json
86623129376ff72cac9487fc7acfee7bf78148ee355bc6cefba00b3c82c099ff  src/mineocclude/prospective/__init__.py
7b85aad8409667c935242851ce77e6a6c2dccb291cb332b114635d624549b905  src/mineocclude/prospective/calibration_support.py
8736a2861369e8af36de48258fd1e60237cd3bc51b6d35f819cb51a8f2362826  src/mineocclude/prospective/clock_domains.py
9df4f6a34de9c80adcac26ef4cf34a4d109681ec91e1f6d25ddaccac3e8749b1  src/mineocclude/prospective/detection_diagnostics.py
07fb088cb045ac43352f00662c97846d6e5bf48f9e0eb99644ffb8b69c613204  src/mineocclude/prospective/path_state_gate.py
4402ad6f8612f87ab355e1aa30054f1bb0ebe411f3a66c6683a2db728f48e534  src/mineocclude/prospective/run_identity.py
ab55c00d7407c3c9b2e6ec1f481f6b98830acadfeb30558cd3107fca998a6484  src/mineocclude/prospective/source_provenance.py
2c09066f6822813213282a147107a619f02fc10d7f893a229638cb4b2d01637a  src/mineocclude/prospective/temporal_alignment.py
77b07461ee6dbdf8958da4b8a0a24b4d4518119277c42a896cc45d7798a7c972  src/mineocclude/prospective/visibility_semantics.py
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  tests/prospective/__init__.py
4c00a1b0e32604fd76f01d8f621249077f7e9757db48fda71e04fba11f2247ab  tests/prospective/test_calibration_support.py
12582b11be67b02ac1070df0c536312ff8e96c87e7d861d3f4e33461caec83ab  tests/prospective/test_clock_domains.py
e38307554b2fae9eb84dbdd317f26ff4431e6fa421ab3a71abe7889975fab34d  tests/prospective/test_detection_diagnostics.py
95f2dc893908c18654a63ee61d3256b101920d538204e6aacfaf5012a208b9e1  tests/prospective/test_forensic_repair_receipts.py
d395fba3e9da0c4668b3e7e6ec8c372a4619df935d65d31fd8fd37f64c762d47  tests/prospective/test_path_state_gate.py
76acd88dd1496f036a2e0bcb02307a9ba92624c267bb0296ff74542280a9adad  tests/prospective/test_run_identity.py
77a2d6c022733255a032d00f17f572955de0f6dce9537849633dd64ac9c42312  tests/prospective/test_source_provenance.py
9bceae8fdaa16895c01f2b872eadda2547269f1214b7f313c3f917a6861b91f3  tests/prospective/test_temporal_alignment.py
f77a207a460994835ef58f137f2846dffb0881b4a7a6612230a6722e0664a03d  tests/prospective/test_visibility_semantics.py
```
