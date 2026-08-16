#!/usr/bin/env python3
"""EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY - read-only evidence inventory."""
import json,hashlib,subprocess
from pathlib import Path
R=Path("/home/sagemaker-user/MineOcclude")
OUTDIR=R/"docs/status/integration/regime_a_prime_qualification_v0_1"
DATA=Path("/tmp/claude-1000/-home-sagemaker-user/0a11aa84-4159-4e2b-8f4c-3f92888226b4/scratchpad/p3data")
def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()
def g(*a): return subprocess.run(["git",*a],cwd=R,text=True,capture_output=True).stdout.strip()

inv={"artifact_id":"p3-terminal-forensic-audit-evidence-inventory-v0.1",
 "label":"EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY","read_only":True,
 "git":{"head":g("rev-parse","HEAD"),"branch":g("branch","--show-current"),
        "status_porcelain":g("status","--porcelain=v1").splitlines(),
        "authority_commit":"e56d90b3da11966e30119dc0efe39fa3b13f1b5c",
        "p2_closeout_commit":"c2ca2472e77934ba4780139f3f9743e8bcf74b78"},
 "authority_and_control_artifacts":[],"code_artifacts":[],"durable_data":{},"runtime_recovery":[]}

roles={
 "p0_receipt.json":"P0 bind receipt","p1_receipt.json":"P1 existing-data qualification receipt",
 "p2_preoutcome_authority.json":"P2 frozen authority","p2_closeout_receipt.json":"P2 closeout",
 "p2_best_k_results.json":"P2 BEST-K result (source of P3 thresholds)",
 "p2_full_results.json":"P2 FULL result","p2_visibility_qualification_receipt.json":"P2 visibility gate receipt",
 "p3_preoutcome_authority.json":"P3 FROZEN AUTHORITY (bd391bd6...)",
 "p3_development_manifest.json":"P3 frozen manifest: 3 candidates x 25 specs + 4 calib specs",
 "p3_authority_validation_receipt.json":"P3 authority validation",
 "p3_progress.json":"P3 controller progress (untracked)","p3_terminal_result.json":"P3 terminal adjudication (untracked)",
 "p3_events.jsonl":"P3 append-only event ledger (untracked)",
 "authority_hierarchy.json":"branch authority hierarchy","branch_authority.json":"branch authority",
}
for name,role in roles.items():
    p=OUTDIR/name
    if p.exists():
        inv["authority_and_control_artifacts"].append(
            {"path":str(p.relative_to(R)),"role":role,"bytes":p.stat().st_size,"sha256":sha(p),
             "git_tracked": bool(g("ls-files","--error-unmatch",str(p.relative_to(R))))})
for c in ("c01","c02","c03"):
    for k in ("calibration_ledger.jsonl","capture_ledger.jsonl","non_neural_gates.json"):
        p=OUTDIR/f"p3_p3dev_{c}_{k}"
        if p.exists():
            inv["authority_and_control_artifacts"].append(
              {"path":str(p.relative_to(R)),"role":f"P3 {c.upper()} {k}","bytes":p.stat().st_size,
               "sha256":sha(p),"git_tracked":False})

for rel,role in [
 ("scripts/regime_a_prime_qualification_v0_1/p3a_freeze.py","P3 design freeze (HIDDEN_BOUNDS, headroom, specs)"),
 ("scripts/regime_a_prime_qualification_v0_1/p3_run_sequential.py","P3 controller: capture, gates, adjudication (untracked)"),
 ("scripts/regime_a_prime_qualification_v0_1/p2c_capture.py","P2/P3 shared capture packaging + renderer identity"),
 ("scripts/regime_a_prime_qualification_v0_1/p2c_adjudicate.py","P2 path + visibility gate"),
 ("scripts/regime_a_prime_qualification_v0_1/p2_common.py","P2/P3 shared CaptureSession"),
 ("fabric/mineocclude-mod/src/main/java/com/mineocclude/server/EpisodeManager.java","SERVER: geometric_visible raycast"),
 ("fabric/mineocclude-mod/src/main/java/com/mineocclude/server/GeometryUtil.java","segmentHitsWall"),
 ("fabric/mineocclude-mod/src/main/java/com/mineocclude/server/ServerStateLogger.java","server_state.jsonl writer"),
 ("fabric/mineocclude-mod/src/main/java/com/mineocclude/client/FrameCapture.java","CLIENT: framebuffer capture"),
 ("src/mineocclude/vision/magenta.py","frozen magenta detector"),
 ("docs/status/person_e_phase3_step3_1_candidate_freeze_v0_1/detector_candidate_config.json","frozen detector config"),
 ("docs/status/integration/regime_a_occlusion_extraction_v0_1/v2_amendment_1/directional_visibility_authority_v2_1_amendment_1.json","DIRECTIONAL VISIBILITY AUTHORITY (source of HIDDEN_BOUNDS)"),
 ("docs/status/integration/regime_a_occlusion_extraction_v0_1/v2/directional_visibility_authority.json","historical v2 directional visibility authority"),
 ("src/mineocclude/regime_a.py","Regime A original directional bounds"),
 ("docs/status/integration/regime_a_occlusion_extraction_v0_1/geometry_camera_authority.json","camera authority"),
]:
    p=R/rel
    if p.exists():
        inv["code_artifacts"].append({"path":rel,"role":role,"bytes":p.stat().st_size,"sha256":sha(p),
                                      "git_tracked":bool(g("ls-files","--error-unmatch",rel))})

for cid in ("P3DEV_C01","P3DEV_C02","P3DEV_C03"):
    cap=sorted(p.name for p in (DATA/cid/"capture").iterdir() if p.is_dir())
    cal=sorted(p.name for p in (DATA/cid/"calibration").iterdir() if p.is_dir())
    inv["durable_data"][cid]={
      "s3_prefix":f"s3://sagemaker-us-east-1-323206973672/mineocclude/regime_a_prime_qualification_v0_1/p3_sequential_development_v0_1/{cid}",
      "capture_units":len(cap),"calibration_units":len(cal),
      "wall_units":sum(1 for u in cap if u.endswith("_wall")),
      "nowall_units":sum(1 for u in cap if u.endswith("_nowall")),
      "duplicate_ids":len(cap)!=len(set(cap)),
      "capture_unit_ids":cap,"calibration_unit_ids":cal,
      "per_unit_streams":["raw/server_state.jsonl","raw/visibility.jsonl","raw/frame_map.jsonl",
                          "raw/actions.jsonl","raw/client_tick.jsonl","raw/frames/000000..000179.png",
                          "coordinates.jsonl","sha256_manifest.json"],
      "frames_per_unit":180,
      "local_nvme_root_status":"WIPED (/mnt/sagemaker-nvme empty) - S3 is the sole surviving copy"}
inv["runtime_recovery"]=[
 {"event":"hard_failure","utc":"2026-08-15T12:15:53Z","error":"RuntimeError: approved JDK absent"},
 {"event":"hard_failure","utc":"2026-08-15T12:18:09Z","error":"FileNotFoundError: /usr/bin/xdpyinfo"},
 {"event":"runtime_provenance_verified","utc":"2026-08-15T11:49:07Z"},
 {"event":"runtime_provenance_verified","utc":"2026-08-15T12:30:56Z"},
 {"event":"runtime_provenance_verified","utc":"2026-08-15T15:05:26Z"}]
inv["local_evidence_outside_repo"]=[
 {"path":"/home/sagemaker-user/p3_restart_checkpoint","role":"restart checkpoint (progress + events tail)"},
 {"path":"/home/sagemaker-user/p3_terminal_nvme_archive_2026-08-15/logs/p3_controller.log","role":"controller log"},
 {"path":"/mnt/sagemaker-nvme","role":"P3 working root","status":"EMPTY/WIPED"}]
p=OUTDIR/"p3_terminal_forensic_audit_v0_1/00_evidence_inventory.json"
p.write_text(json.dumps(inv,indent=2,sort_keys=True))
print("wrote",p)
print("authority artifacts:",len(inv["authority_and_control_artifacts"]),"code artifacts:",len(inv["code_artifacts"]))
for cid,v in inv["durable_data"].items():
    print(f"  {cid}: capture={v['capture_units']} wall={v['wall_units']} nowall={v['nowall_units']} calib={v['calibration_units']} dup={v['duplicate_ids']}")
