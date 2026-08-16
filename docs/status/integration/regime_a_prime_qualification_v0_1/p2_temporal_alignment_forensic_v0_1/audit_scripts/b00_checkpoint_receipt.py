#!/usr/bin/env python3
"""EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY - Phase 0 checkpoint receipt (read-only)."""
import json,hashlib,subprocess
from pathlib import Path
R=Path("/home/sagemaker-user/MineOcclude")
Q=R/"docs/status/integration/regime_a_prime_qualification_v0_1"
F=Q/"p3_terminal_freeze_v0_1"
EXPECTED="351da852965bb20f89fe848bdef71703c34f0705"
def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()
def g(*a): return subprocess.run(["git",*a],cwd=R,text=True,capture_output=True).stdout.strip()

head=g("rev-parse","HEAD"); branch=g("branch","--show-current"); up=g("rev-parse","@{u}")
status=g("status","--porcelain=v1").splitlines()
tracked_mod=[l for l in status if not l.startswith("??")]

EXPECT_HASHES={
 "historical_evidence_manifest.json":"369502d9e075d5e1ca0434cf1c5ef5657bb2c03a51d229b6a0275c41a9c9af78",
 "p3_terminal_receipt.json":"f4b044636725777c15187349a5f066282622af3a48e404f2cc8f8d629279f5a0",
 "forensic_audit_hash_manifest.json":"cfbacee9ed3688882345b0095796db7a99c66316f88fec8ede1843d7a592afed"}
freeze={}
for name,exp in EXPECT_HASHES.items():
    got=sha(F/name); freeze[name]={"expected":exp,"observed":got,"match":got==exp}
for name in ("deferred_to_claude_repair.json","posthoc_p3_controller_receipt.json",
             "runtime_recovery_manifest.json","s3_preservation_receipt.json"):
    freeze[name]={"observed":sha(F/name),"expected":None,"match":None}

CTRL="scripts/regime_a_prime_qualification_v0_1/p3_run_sequential.py"
ctrl_expected="29ee438980448f8b0f0c8d9ecc534a63aecb539309065692f70e5fc920630c1b"
ctrl_got=sha(R/CTRL)

HIST={}
for name in ("p3_preoutcome_authority.json","p3_development_manifest.json","p3_terminal_result.json",
             "p3_progress.json","p3_events.jsonl","p2_preoutcome_authority.json","p2_best_k_results.json",
             "p2_full_results.json","p2_closeout_receipt.json","p2_predictions.parquet",
             "p2_activation_manifest.json","p2_target_row_manifest.json","p2_capture_ledger.jsonl",
             "p1_receipt.json","p0_receipt.json",
             "p3_p3dev_c01_non_neural_gates.json","p3_p3dev_c02_non_neural_gates.json",
             "p3_p3dev_c03_non_neural_gates.json"):
    p=Q/name
    if p.exists(): HIST[name]={"sha256":sha(p),"bytes":p.stat().st_size}

p2bk=json.load(open(Q/"p2_best_k_results.json")); p2fl=json.load(open(Q/"p2_full_results.json"))
def pick(d,*keys):
    for k in keys:
        if isinstance(d,dict) and k in d: d=d[k]
        else: return None
    return d

receipt={
 "artifact_id":"p2-temporal-alignment-forensic-checkpoint-receipt-v0.1",
 "label":"EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY","phase":"PHASE_0",
 "verification_utc":subprocess.run(["date","-u","+%Y-%m-%dT%H:%M:%SZ"],capture_output=True,text=True).stdout.strip(),
 "branch":{"observed":branch,"expected":"exploration/regime-a-prime-qualification-v0-1",
           "match":branch=="exploration/regime-a-prime-qualification-v0-1"},
 "head":{"observed":head,"expected":EXPECTED,"match":head==EXPECTED},
 "upstream":{"ref":g("rev-parse","--abbrev-ref","--symbolic-full-name","@{u}"),
             "observed":up,"expected":EXPECTED,"match":up==EXPECTED},
 "worktree":{"porcelain_entries":status,"tracked_modifications":tracked_mod,
             "clean_tracked":len(tracked_mod)==0,
             "untracked_count":len([l for l in status if l.startswith("??")])},
 "freeze_artifacts":freeze,
 "freeze_artifacts_all_expected_hashes_match":all(v["match"] for v in freeze.values() if v["match"] is not None),
 "posthoc_controller":{"path":CTRL,"expected":ctrl_expected,"observed":ctrl_got,"match":ctrl_got==ctrl_expected,
   "provenance_caveat":"THIS HASH DOES NOT RETROACTIVELY PROVE THAT THE EXECUTED P3 CONTROLLER WAS BYTE-IDENTICAL TO THE CURRENT FILE. Historical gap is NOT repaired by this audit."},
 "historical_artifact_hashes":HIST,
 "historical_p3_verdicts_observed":{
   c:{k:json.load(open(Q/f"p3_p3dev_{c}_non_neural_gates.json"))[k]
      for k in ("status","path_status","visibility_status","headroom_status","capture_status")}
   for c in ("c01","c02","c03")},
 "historical_p2_headline":{
   "best_k_rmse_expected":0.1660274234445584,"full_rmse_expected":0.16657677302324672,
   "best_k_macro_r2_expected":0.7906954002303574,"full_macro_r2_expected":0.7548030087626074},
 "s3_preservation":{
   "primary":"s3://sagemaker-us-east-1-323206973672/mineocclude/regime_a_prime_qualification_v0_1/p3_sequential_development_v0_1/",
   "secondary":"s3://sagemaker-us-east-1-323206973672/mineocclude/historical_preservation/regime_a_prime_qualification_v0_1/p3_terminal_preservation_2026-08-15/",
   "objects":32844,"bytes":2455084221,
   "verified_by_codex":"coverage/object-size/ETag comparison PASSED; all 162 unit SHA-256 manifests matched ledger-recorded hashes and backup copies",
   "LIMITATION":"Full 2.45 GB raw-object payload SHA-256 values were NOT independently recomputed by downloading the entire cohort. This limitation is preserved verbatim and is NOT repaired by this audit."},
 "terminology_separation":{
   "NORMAL_TARGET_ROW_CONTAMINATION":"C02=1 row, C03=7 rows - scientifically observed detector/geometry disagreement on scientific target rows. Codex handoff CONTAMINATION_DETECTED=true refers to THIS.",
   "RUNTIME_RECOVERY_CONTAMINATION":"false - independently established by p3_terminal_forensic_audit_v0_1/07. These are DISTINCT concepts and must not be conflated."},
 "claude_modification_boundary":{
   "may_modify":"future-facing source code on confirmed defect; new tests; new forensic artifacts",
   "must_not_modify":["Codex freeze artifacts","historical authority","historical P1/P2/P3 manifests",
                      "historical P1/P2/P3 results","historical P3 progress/events","historical terminal verdicts"],
   "commit":False,"push":False,"branch_change":False},
}
receipt["CHECKPOINT_STATUS"]="PASS" if (receipt["branch"]["match"] and receipt["head"]["match"]
    and receipt["upstream"]["match"] and receipt["worktree"]["clean_tracked"]
    and receipt["freeze_artifacts_all_expected_hashes_match"] and receipt["posthoc_controller"]["match"]) else "BLOCKED"
out=Q/"p2_temporal_alignment_forensic_v0_1/00_checkpoint_receipt.json"
out.write_text(json.dumps(receipt,indent=2,sort_keys=True))
print("CHECKPOINT_STATUS =",receipt["CHECKPOINT_STATUS"])
print("branch/head/upstream match:",receipt["branch"]["match"],receipt["head"]["match"],receipt["upstream"]["match"])
print("tracked modifications:",len(tracked_mod),"| untracked:",receipt["worktree"]["untracked_count"])
print("freeze hashes match:",receipt["freeze_artifacts_all_expected_hashes_match"])
print("controller hash match:",receipt["posthoc_controller"]["match"])
print("historical verdicts:",json.dumps(receipt["historical_p3_verdicts_observed"]))
print("wrote",out)
