# Executed commands — Experiment III-A, A7 → A19

Every command below is **EXACT_RECORDED**, not reconstructed. The source is the ops
orchestration that actually drove the run, preserved verbatim in
[`../code/ops/`](../code/ops/), together with the supervisor's own timestamped log in
[`../code/logs/supervisor.log`](../code/logs/supervisor.log).

Anything reconstructed is labelled `RECONSTRUCTED` inline. Nothing in §1–§2 is.

Shared environment for every stage (set by `supervise.py`):

```
GIT_DISCOVERY_ACROSS_FILESYSTEM=1
PYTHONPATH=/home/sagemaker-user/MineOcclude-Exp3/src
cwd=/home/sagemaker-user/MineOcclude-Exp3
```

Two interpreters were used, deliberately:

| symbol | path | stages |
|---|---|---|
| `PY312` | `/opt/conda/bin/python3.12` | A7, A8, A10 – A19 |
| `MWPY` | `/home/sagemaker-user/.conda/envs/mineworld/bin/python` (3.10.20) | **A9 only** |

`REPO=/home/sagemaker-user/MineOcclude-Exp3`, `D=$REPO/docs/experiment_iii`,
`PROD=$REPO/data/experiment_iii/production`, `RESULTS=$D/results`.

---

## 1. A7 — production capture

Launched detached from `exp3-terminal-ops/a7/launch_a7.sh`, which the supervisor then waited on:

```bash
exec /opt/conda/bin/python3.12 -u "$REPO/scripts/experiment_iii/run_production_capture.py" \
  --execute \
  --p2 "$REPO/docs/experiment_iii/p2/P2_FREEZE_PACKAGE.json" \
  --capture-host-receipt "$REPO/docs/experiment_iii/receipts/environment_receipt_sagemaker_capture_host.json" \
  --ladder "$REPO/docs/experiment_iii/p0/P0_SELECTED_LADDER.json" \
  --runtime-config "$OPS/capture_runtime_config.json"
```

`OPS=/home/sagemaker-user/exp3-terminal-ops`; that runtime config is preserved at
[`../code/ops/capture_runtime_config.json`](../code/ops/capture_runtime_config.json).
A7 ran under Xvfb on `:99` and finished 125/125 in 2975.5 s with 0 errors and 0 retries.

## 2. A8 → A19 — the supervised chain

From [`../code/ops/supervise.py`](../code/ops/supervise.py), verbatim argument vectors:

```bash
# A8  CAPTURE_COHORT_VALIDATION
PY312 -u $REPO/scripts/experiment_iii/validate_capture_cohort.py

# A9  ACTIVATION_EXTRACTION   (GPU; the mineworld interpreter, not 3.12)
MWPY  -u $REPO/scripts/experiment_iii/run_extraction.py --execute \
  --a3-receipt $D/receipts/environment_receipt_gpu_extraction_host_postprovision.json \
  --mineworld-source-root /home/sagemaker-user/MineWorld-Upstream \
  --model-config    /home/sagemaker-user/MineWorld-Upstream/configs/700M_16f.yaml \
  --main-checkpoint /home/sagemaker-user/MineWorld-Assets-Pinned/checkpoints/700M_16f.ckpt \
  --vae-config      /home/sagemaker-user/MineWorld-Assets-Pinned/checkpoints/vae/config.json \
  --vae-checkpoint  /home/sagemaker-user/MineWorld-Assets-Pinned/checkpoints/vae/vae.ckpt \
  --model-config-sha256        e13b3a80fb370547a05852809c2c8f02d05ebe2fce3b3bb2fd1ee54eee78c018 \
  --vae-config-sha256          32ca759d5b90f0c5aa5df0e312a81e03dd4d3af68896863c88f910d19f2526cb \
  --environment-report-sha256  b27491bf0c31d52579bbbebd41516a239025882f938894030e041f73bc2cc1a9 \
  --mineworld-source-revision  9f49efbcc68a5f0cf60e78f0abc566eac409282f \
  --modelscope-asset-revision  0dd5561ab317115831badc50e09a6ebe98693d0e \
  --runtime-id experiment-iii-a9-production \
  --precision float16 --device cuda:0

# A10 EXTRACTION_VALIDATION
PY312 -u $REPO/scripts/experiment_iii/validate_extraction.py \
  $PROD/activations --expect-captures 125 --expect-arrays 750

# A11 FEATURE_CONSTRUCTION
PY312 -u $REPO/scripts/experiment_iii/build_features.py

# A12 PREDICTION_LOCK
PY312 -u $REPO/scripts/experiment_iii/lock_predictions.py --stage lock

# A13 BASELINES_CONTROLS
PY312 -u $REPO/scripts/experiment_iii/lock_predictions.py --stage baselines

# A14 / A15 / A16
PY312 -u $REPO/scripts/experiment_iii/run_primary_analysis.py --stage primary
PY312 -u $REPO/scripts/experiment_iii/run_primary_analysis.py --stage temporal
PY312 -u $REPO/scripts/experiment_iii/run_primary_analysis.py --stage context

# A17 / A18 / A19
PY312 -u $REPO/scripts/experiment_iii/build_scientific_package.py --stage adjudication
PY312 -u $REPO/scripts/experiment_iii/build_scientific_package.py --stage package
PY312 -u $REPO/scripts/experiment_iii/build_scientific_package.py --stage closure
```

There is **no investigator-authored predictions file**. A12 computes its own predictions from
the A11 feature blocks, `folds.json` and P2, then seals: `A12_EXTERNAL_PREDICTIONS_REQUIRED=false`.

## 3. Timeline as recorded

| stage | started (UTC) | exit | terminal line |
|---|---|---|---|
| A7  | 2026-09-02T03:08:28Z (waited on) | 0 | `A7_EXECUTED=true`, 125/125, 2375 rows |
| A8  | 03:57:28Z | 0 | `COHORT_CLOSURE_RECEIPT_SHA256=3762eb94…` |
| A9  | 03:57:29Z | 0 | `A9_EXECUTED=true`, 750 arrays, 4730.8 s |
| A10 | 05:18:07Z | 0 | `EXTRACTION_VALIDATION_RECEIPT_SHA256=1b2a23dc…` |
| A11 | 05:20:35Z | 0 | `A11_FEATURE_CONFIG_SHA256=7892b738…` |
| A12 | 05:24:01Z | 0 | `A12_EXTERNAL_PREDICTIONS_REQUIRED=false` |
| A13 | 05:33:07Z | 0 | `OVERALL_PASS_FAIL_VERDICT=none` |
| A14 | 05:33:07Z | 0 | `OVERALL_PASS_FAIL_VERDICT=none` |
| A15 | 05:33:09Z | 0 | `OVERALL_PASS_FAIL_VERDICT=none` |
| A16 | 05:33:10Z | 0 | `OVERALL_PASS_FAIL_VERDICT=none` |
| A17 | 05:33:10Z | 0 | `ADJUDICATION_RECEIPT_SHA256=55e612ad…` |
| A18 | 05:33:10Z | 0 | `OVERALL_PASS_FAIL_VERDICT=none` |
| A19 | 05:33:11Z | 0 | `CLOSURE_RECEIPT_SHA256=920c8778…` |

`A7 -> A19 COMPLETE` at 2026-09-02T05:33:11Z, `errors_seen=0`.

## 4. Qualification stages P0 / P1 / P2 / A2 / A3

These ran **before** the supervised chain and were not driven by `supervise.py`, so no single
verbatim argv record survives for them. Their **receipts** do survive in full and are published
under [`receipts/`](receipts/). The canonical entrypoints, read from the committed source, are:

| stage | entrypoint | status |
|---|---|---|
| P0 ladder selection | `scripts/experiment_iii/run_p0_rve_calibration.py` | `RECONSTRUCTED` from the committed entrypoint; receipt `P0_SELECTED_LADDER.json` is original |
| P1 pilot capture | `scripts/experiment_iii/run_p1_pilot.py`, `launch_p1_capture.sh` | `RECONSTRUCTED`; receipt `p1_pilot_receipt.json` is original |
| P1 pilot extraction | `scripts/experiment_iii/run_p1_extraction.py` | `RECONSTRUCTED`; ops wrapper `exp3-p1-ops/run_a5_extraction_detached.sh` survives on this host |
| P2 freeze | `scripts/experiment_iii/build_p2_freeze.py` | `RECONSTRUCTED`; `P2_FREEZE_PACKAGE.json` (`f0e9d954…`) is original |
| A2 static validation | `pytest tests/experiment_iii/` then `scripts/experiment_iii/build_static_validation_receipt.py` | entrypoint recorded verbatim in the receipt's own `entrypoint` field |
| A3 host qualification | `scripts/experiment_iii/preflight.py` | `RECONSTRUCTED`; both environment receipts are original |

A2's receipt records its own entrypoint literally — `pytest tests/experiment_iii/`, 35 suite
files, suite digest `c4296d4eec7612d33ed4864564f04bfcc77505f1d4070d44d2a970ccd52a342a` — so that
one line is `EXACT_RECORDED` even though the shell invocation around it is not.
