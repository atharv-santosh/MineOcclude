# 07 — Runtime / Restart Contamination Audit

**Label: EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY.** Script: `a07_restart_contamination.py`.
The previously reported `CONTAMINATION_DETECTED=false` was **not** assumed; it was re-derived.

## Recovery events, independently recovered from `p3_events.jsonl`

| UTC | event | detail |
|---|---|---|
| 11:49:07 | `runtime_provenance_verified` PASS | initial C01 calibration session |
| 12:15:53 | **hard_failure** | `RuntimeError: approved JDK absent` (`p2_common.py:205`, `CaptureSession.__init__`) |
| 12:18:09 | **hard_failure** | `FileNotFoundError: /usr/bin/xdpyinfo` (`launch_runtime`) |
| 12:30:56 | `runtime_provenance_verified` PASS | runtime reconstructed |
| 15:05:26 | `runtime_provenance_verified` PASS | after second Space restart |

`hard_failures = 2` in `p3_progress.json` — confirmed, both during **C01 calibration**, both **before any
scientific capture** (first capture unit at 12:38:01Z). Neither hard failure touched scientific data.

## Recovery #1 — calibration reuse claim (`DURABLE_CALIBRATION_UNITS_REUSED=3`)
C01 calibration ledger timestamps: `ltr_r01` 11:52:37, `ltr_r02` 11:56:01, `rtl_r01` 11:59:24 — then a
**35-minute gap** — `rtl_r02` 12:34:28. Exactly **3 units** completed before the failure window and **1** after.
Every record is `attempt: 1`; there is no second attempt for any calibration identity.
**Claim verified: 3 reused, 0 recollected.**

## Recovery #2 — capture reuse claim (`DURABLE_CAPTURE_UNITS_REUSED=41`, `INTERRUPTED_UNIT=p3dev_c01_t21_nowall`)
Ordering the 50 C01 capture units by ledger timestamp and taking the largest inter-unit gap:

- largest gap **1189 s**, between `p3dev_c01_t21_wall` and `p3dev_c01_t21_nowall`
- next largest gaps ≈ 215 s (the normal per-unit cadence)
- units before the gap: **41**; after: **9**

**Both reported values are independently confirmed**, including the exact interrupted unit identity.
Every C01 capture record is `attempt: 1`; `capture_retries = 0`. No unit was captured twice, and
`completed()` keys on `identity` with `status == COMPLETE_VALIDATED_DURABLE`, so a resumed run skips only
already-durable identities.

## Pre/post-restart stratification of C01 (41 vs 9 units)

| property | pre-restart (n=41) | post-restart (n=9) | differs? |
|---|---|---|---|
| frames per unit | 180 (single value) | 180 (single value) | no |
| visibility rows | 7,380 | 1,620 | no (proportional) |
| magenta area, mean | 339.94 px | 339.38 px | **no (Δ = 0.6 px, 0.2 %)** |
| magenta area, median | 337 px | 335 px | **no** |
| detected-row fraction | 5365/7380 = 0.7270 | 1229/1620 = 0.7586 | no (differing WALL/NO_WALL mix in the 9-unit tail) |
| recorded renderer/provenance fields | — | — | **all identical; zero differing fields** |
| `server_tick` density 0..179 | exact | exact | no |
| `scene` field vs commanded scene | 0 mismatches | 0 mismatches | no |
| path sha256 vs frozen expectation | 41/41 exact | 9/9 exact | no |

Additionally, **every one of the 50 C01 units reproduces its frozen `expected_path_sha256` bit-for-bit** and
`NORMAL.sheep_x ≡ NO_WALL.sheep_x` for all 25 pairs. A renderer, JVM, mod, wall-geometry, camera or cadence
change across the restart would have to have left the physics, the frame count, the silhouette area
distribution *and* every checksum invariant — which is not credible.

## Is candidate failure associated with the restart strata?
No. The C01 failure is driven entirely by the **calibration** gate (precision 0.8468). Of the four C01
calibration runs, three are pre-restart (FP = 13, 13, 12) and one is post-restart (FP = 13). **The
post-restart run is indistinguishable from the pre-restart runs.** C02 and C03 ran entirely post-recovery on a
stable runtime and reproduce the same structural failure with the same flat FP-rate (0.104, 0.103 vs C01's
0.118). The failure is present in every stratum, before and after every restart.

## Verdict
`RUNTIME_RECOVERY_CONTAMINATION = false` — independently verified, not inherited.
`CONTAMINATION_DETECTED = false`.
`DATA_INTEGRITY_STATUS = PASS`.

**Caveat recorded, not a contamination finding:** the NVMe working root `/mnt/sagemaker-nvme/` is now **empty**.
All P3 raw data survives **only** in S3. The durability design (checksum manifest + remote readback per unit)
worked — every unit restored cleanly and every checksum manifest is present — but there is now a single copy.
