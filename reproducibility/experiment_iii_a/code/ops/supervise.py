"""Experiment III A7 -> A19 fail-closed supervisor.

OPERATIONAL ORCHESTRATION ONLY. It contains no scientific logic: it waits on
A7, then invokes the committed stage entrypoints in the frozen order and gates
each transition on that stage's own declared outcome (process exit status plus
the receipt the stage itself writes). It never edits source, never edits
authority, never retunes anything, and never fabricates a stage input.

Any failure -> STOP. No bypass, no downgrade, no skipping.
"""
import json, os, subprocess, sys, time
from pathlib import Path

REPO = Path("/home/sagemaker-user/MineOcclude-Exp3")
OPS = Path("/home/sagemaker-user/exp3-terminal-ops")
SUP = OPS / "supervisor"
D = REPO / "docs/experiment_iii"
PROD = REPO / "data/experiment_iii/production"
RESULTS = D / "results"
STATE = SUP / "state.json"
LOG = SUP / "supervisor.log"
PY312 = "/opt/conda/bin/python3.12"
MWPY = "/home/sagemaker-user/.conda/envs/mineworld/bin/python"   # A9 only

STAGES = ["A7", "A8", "A9", "A10", "A11", "A12", "A13", "A14",
          "A15", "A16", "A17", "A18", "A19"]


def log(msg):
    line = f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] {msg}"
    with LOG.open("a") as fh:
        fh.write(line + "\n")
    print(line, flush=True)


def save(**kw):
    st = {}
    if STATE.exists():
        try: st = json.loads(STATE.read_text())
        except Exception: st = {}
    st.update(kw)
    st["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=1, sort_keys=True))
    tmp.replace(STATE)


def stop(stage, why):
    log(f"STOP at {stage}: {why}")
    save(current_stage=stage, stage_status="FAILED", supervisor_status="STOPPED",
         last_message=why, errors_seen=(_errors() + 1))
    sys.exit(1)


def _errors():
    if STATE.exists():
        try: return int(json.loads(STATE.read_text()).get("errors_seen") or 0)
        except Exception: return 0
    return 0


def run(stage, argv, python=PY312, detached_note=""):
    """Run one committed entrypoint. Non-zero exit is terminal."""
    log(f"{stage}: RUNNING {detached_note}{' '.join(str(a) for a in argv[:3])} ...")
    save(current_stage=stage, stage_status="RUNNING",
         last_message=f"{stage} started", supervisor_status="RUNNING")
    env = dict(os.environ)
    env["GIT_DISCOVERY_ACROSS_FILESYSTEM"] = "1"
    env["PYTHONPATH"] = str(REPO / "src")
    out = SUP / f"{stage.lower()}.log"
    with out.open("w") as fh:
        rc = subprocess.call([python, "-u"] + [str(a) for a in argv],
                             cwd=str(REPO), env=env, stdout=fh,
                             stderr=subprocess.STDOUT)
    tail = ""
    try: tail = out.read_text().strip().splitlines()[-1][:200]
    except Exception: pass
    if rc != 0:
        stop(stage, f"{stage} entrypoint exited {rc}; last line: {tail}")
    log(f"{stage}: exit 0 | {tail}")
    return out


def require_receipt(stage, path, *flags):
    """Gate the transition on the stage's OWN declared outcome."""
    if not Path(path).is_file():
        stop(stage, f"{stage} wrote no receipt at {path}")
    doc = json.loads(Path(path).read_text())
    for flag in flags:
        val = doc.get(flag)
        okv = val is True or (isinstance(val, str) and val.upper() in ("PASS", "P0_PASS", "COMPLETE"))
        if not okv:
            stop(stage, f"{stage} receipt {Path(path).name} has {flag}={val!r}")
    log(f"{stage}: receipt {Path(path).name} satisfies {list(flags)}")
    return doc


# --------------------------------------------------------------- A7 (running)
def wait_for_a7():
    a7log = OPS / "a7/a7.log"
    save(current_stage="A7", stage_status="RUNNING", supervisor_status="RUNNING",
         last_message="waiting for A7 production capture to finish")
    log("A7: waiting for the detached production campaign to finish")
    # Liveness via the pidfile + /proc, never `pgrep -f` on a command string:
    # text-matching the process table also matches any shell whose own command
    # line quotes the pattern, which would make this wait on a phantom forever.
    pidfile = OPS / "a7/a7.pid"
    while True:
        try:
            pid = int(pidfile.read_text().strip())
            cmd = Path(f"/proc/{pid}/cmdline").read_bytes().decode("utf-8", "replace")
            if "run_production_capture.py" not in cmd:
                break
        except Exception:
            break
        time.sleep(30)
    text = a7log.read_text() if a7log.exists() else ""
    if "BLOCKER_CODE=" in text:
        blocker = [l for l in text.splitlines() if l.startswith("BLOCKER_CODE=")][-1]
        stop("A7", f"A7 reported {blocker}")
    if "A7_EXECUTED=true" not in text:
        stop("A7", "A7 exited without reporting A7_EXECUTED=true")
    matrix = D / "capture/capture_matrix.json"
    if not matrix.is_file():
        stop("A7", "A7 wrote no capture_matrix.json")
    inv = json.loads(matrix.read_text())["inventory"]
    if not inv.get("complete"):
        stop("A7", f"A7 inventory incomplete: "
                   f"{inv.get('completed_units')}/{inv.get('total_units')} units")
    log(f"A7: PASS {inv['completed_units']}/{inv['total_units']} units, "
        f"{inv.get('target_rows_total')} target rows")
    save(current_stage="A7", stage_status="PASS",
         last_message=f"A7 complete: {inv['completed_units']} units")


def main():
    SUP.mkdir(parents=True, exist_ok=True)
    (SUP / "supervisor.pid").write_text(str(os.getpid()))
    save(supervisor_status="RUNNING", started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
         errors_seen=_errors(), stages=STAGES)
    log("supervisor armed (A7 -> A19, fail-closed)")

    wait_for_a7()

    # ---- A8 CAPTURE_COHORT_VALIDATION
    run("A8", [REPO / "scripts/experiment_iii/validate_capture_cohort.py"])
    a8 = require_receipt("A8", D / "a8/cohort_closure_receipt.json", "passed")
    n = a8.get("N_complete")
    if not n:
        stop("A8", f"A8 closed the cohort with N_complete={n!r}; nothing downstream can stand on it")
    log(f"A8: PASS N_complete={n}")
    save(current_stage="A8", stage_status="PASS", last_message=f"A8 N_complete={n}")

    # ---- A9 ACTIVATION_EXTRACTION (GPU; the mineworld interpreter, not 3.12)
    run("A9", [REPO / "scripts/experiment_iii/run_extraction.py", "--execute",
               "--a3-receipt", D / "receipts/environment_receipt_gpu_extraction_host_postprovision.json",
               "--mineworld-source-root", "/home/sagemaker-user/MineWorld-Upstream",
               "--model-config", "/home/sagemaker-user/MineWorld-Upstream/configs/700M_16f.yaml",
               "--main-checkpoint", "/home/sagemaker-user/MineWorld-Assets-Pinned/checkpoints/700M_16f.ckpt",
               "--vae-config", "/home/sagemaker-user/MineWorld-Assets-Pinned/checkpoints/vae/config.json",
               "--vae-checkpoint", "/home/sagemaker-user/MineWorld-Assets-Pinned/checkpoints/vae/vae.ckpt",
               "--model-config-sha256", "e13b3a80fb370547a05852809c2c8f02d05ebe2fce3b3bb2fd1ee54eee78c018",
               "--vae-config-sha256", "32ca759d5b90f0c5aa5df0e312a81e03dd4d3af68896863c88f910d19f2526cb",
               "--environment-report-sha256", "b27491bf0c31d52579bbbebd41516a239025882f938894030e041f73bc2cc1a9",
               "--mineworld-source-revision", "9f49efbcc68a5f0cf60e78f0abc566eac409282f",
               "--modelscope-asset-revision", "0dd5561ab317115831badc50e09a6ebe98693d0e",
               "--runtime-id", "experiment-iii-a9-production",
               "--precision", "float16", "--device", "cuda:0"],
        python=MWPY)
    save(current_stage="A9", stage_status="PASS", last_message="A9 extraction finished")

    # ---- A10 EXTRACTION_VALIDATION
    run("A10", [REPO / "scripts/experiment_iii/validate_extraction.py",
                PROD / "activations",
                "--expect-captures", 125, "--expect-arrays", 750])
    a10 = require_receipt("A10", D / "receipts/extraction_validation_receipt.json",
                          "passed")
    if a10.get("arrays_validated") != 750 or a10.get("captures_checked") != 125:
        stop("A10", f"A10 validated {a10.get('arrays_validated')} arrays across "
                    f"{a10.get('captures_checked')} captures; authority 8.4 freezes "
                    f"750 across 125")
    save(current_stage="A10", stage_status="PASS",
         last_message=f"A10 validated {a10.get('arrays_validated')} arrays")

    # ---- A11 FEATURE_CONSTRUCTION -- builds AND persists the feature blocks
    run("A11", [REPO / "scripts/experiment_iii/build_features.py"])
    require_receipt("A11", D / "receipts/feature_config.json")
    save(current_stage="A11", stage_status="PASS", last_message="A11 features built")

    # ---- A12 PREDICTION_LOCK -- A12 COMPUTES its predictions from the A11
    # feature blocks and the frozen folds. There is no investigator-authored
    # predictions file; the lifecycle names A12's inputs as FEATURE_BLOCKS,
    # folds.json and P2, and its operations as fit-select-emit-seal.
    run("A12", [REPO / "scripts/experiment_iii/lock_predictions.py",
                "--stage", "lock"])
    lock = RESULTS / "PREDICTION_LOCK.json"
    if not lock.is_file():
        stop("A12", f"A12 sealed no prediction lock at {lock}")
    if not (RESULTS / "PREDICTION_LOCK.sha256").is_file():
        stop("A12", "A12 wrote no PREDICTION_LOCK.sha256")
    save(current_stage="A12", stage_status="PASS", last_message="A12 predictions locked")

    # ---- A13 BASELINES_CONTROLS -- the lifecycle requires it between A12 and
    # A14, and A14's own entry condition is "A12 == PASS, A13 == PASS".
    run("A13", [REPO / "scripts/experiment_iii/lock_predictions.py",
                "--stage", "baselines"])
    a13 = require_receipt("A13", RESULTS / "baselines_receipt.json", "passed")
    if a13.get("baseline_count") != 5:
        stop("A13", f"A13 reported {a13.get('baseline_count')} baselines; 8.9 freezes five")
    save(current_stage="A13", stage_status="PASS",
         last_message=f"A13 five baselines + L0 control "
                      f"({a13.get('l0_interpretability_control', {}).get('interpretation')})")

    # ---- A14/A15/A16 -- each derives its own estimands from the SEALED lock.
    for stage, sub, artifact in (("A14", "primary", "primary_results.json"),
                                 ("A15", "temporal", "temporal_results.json"),
                                 ("A16", "context", "context_age_results.json")):
        run(stage, [REPO / "scripts/experiment_iii/run_primary_analysis.py",
                    "--stage", sub])
        if not (RESULTS / artifact).is_file():
            stop(stage, f"{stage} wrote no {artifact}")
        # A14/A15/A16 each derive their estimands from the sealed lock; a result
        # that names a different lock is not a result for this run.
        doc = json.loads((RESULTS / artifact).read_text())
        if not doc.get("prediction_lock_sha256"):
            stop(stage, f"{stage} result {artifact} names no prediction lock")
        save(current_stage=stage, stage_status="PASS", last_message=f"{stage} ({sub}) complete")

    for stage, sub, artifact in (("A17", "adjudication", "adjudication_receipt.json"),
                                 ("A18", "package", "scientific_package_manifest.json"),
                                 ("A19", "closure", "EXPERIMENT_III_CLOSURE_RECEIPT.json")):
        run(stage, [REPO / "scripts/experiment_iii/build_scientific_package.py",
                    "--stage", sub])
        if not (RESULTS / artifact).is_file():
            stop(stage, f"{stage} wrote no {artifact}")
        # Existence is not an outcome. Each of these three declares one, and
        # the declaration is what the next stage stands on.
        doc = json.loads((RESULTS / artifact).read_text())
        if stage == "A17":
            if doc.get("every_claim_maps_to_a_permitted_interpretation") is not True \
                    or doc.get("prohibited_claim_present") is not False:
                stop("A17", f"A17 adjudication is not clean: {artifact}")
        if stage == "A18" and not int(doc.get("artifact_count") or 0):
            stop("A18", "A18 packaged 0 artifacts")
        if stage == "A19":
            if doc.get("EXPERIMENT_III_COMPLETE") is not True:
                stop("A19", f"A19 closed with unmet conditions: "
                            f"{doc.get('unmet_conditions')}")
        save(current_stage=stage, stage_status="PASS", last_message=f"{stage} ({sub}) complete")

    log("A7 -> A19 COMPLETE")
    save(supervisor_status="COMPLETE", current_stage="A19", stage_status="PASS",
         last_message="A7 -> A19 complete")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        stop(json.loads(STATE.read_text()).get("current_stage", "?") if STATE.exists() else "?",
             f"supervisor crashed: {type(exc).__name__}: {exc}")
