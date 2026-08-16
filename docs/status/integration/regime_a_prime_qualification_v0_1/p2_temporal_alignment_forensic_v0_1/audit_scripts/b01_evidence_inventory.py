#!/usr/bin/env python3
"""EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY - Phase 1 timing evidence inventory + source map."""
import json,hashlib,subprocess
from pathlib import Path
R=Path("/home/sagemaker-user/MineOcclude")
Q=R/"docs/status/integration/regime_a_prime_qualification_v0_1"
def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()
def tracked(rel):
    return subprocess.run(["git","ls-files","--error-unmatch",rel],cwd=R,capture_output=True).returncode==0

SOURCE_MAP=[
 ("fabric/mineocclude-mod/src/main/java/com/mineocclude/server/EpisodeManager.java",
  "SERVER_ENTITY_STATE","tick()","server entity update + geometric_visible single-ray point test (:453-459)"),
 ("fabric/mineocclude-mod/src/main/java/com/mineocclude/server/ServerStateLogger.java",
  "SERVER_ENTITY_STATE","write()","server_state.jsonl emission incl. server_epoch_nanos"),
 ("fabric/mineocclude-mod/src/main/java/com/mineocclude/server/SheepController.java",
  "SERVER_ENTITY_STATE","-","target motion integration from the frozen noise schedule"),
 ("fabric/mineocclude-mod/src/main/java/com/mineocclude/server/NoiseSchedule.java",
  "SERVER_ENTITY_STATE","-","immutable per-tick noise draws"),
 ("fabric/mineocclude-mod/src/main/java/com/mineocclude/net/TickSyncPacket.java",
  "NETWORK_UPDATE","-","authoritative tick broadcast (does NOT carry entity position)"),
 ("fabric/mineocclude-mod/src/main/java/com/mineocclude/net/CaptureAckPacket.java",
  "NETWORK_UPDATE","-","lockstep acknowledgement: holds the world until capture completes"),
 ("fabric/mineocclude-mod/src/main/java/com/mineocclude/client/MineOccludeClient.java",
  "CLIENT_RENDER -> CAPTURE_FRAME","onFrame()/captureOne()",
  "capture at END_CLIENT_TICK of 'the last fully completed frame' (:88-101); entity position is the vanilla client-interpolated one"),
 ("fabric/mineocclude-mod/src/main/java/com/mineocclude/client/FrameCapture.java",
  "CAPTURE_FRAME","capture()","framebuffer readback -> PNG; stale-frame detector"),
 ("fabric/mineocclude-mod/src/main/java/com/mineocclude/client/ClientLogger.java",
  "CAPTURE_FRAME","-","client_tick.jsonl: server_epoch_nanos, client_recv_nanos, client_capture_nanos"),
 ("scripts/regime_a_prime_qualification_v0_1/p2c_capture.py",
  "CAPTURE_FRAME -> MODEL_FRAME","package()","capture packaging; scientific_run_id silent default (:233)"),
 ("scripts/regime_a_prime_qualification_v0_1/p3_run_sequential.py",
  "MODEL_FRAME","derive_artifacts()","collapses model_frame_idx/server_tick/render_frame_idx/action_idx to one index (:340-367)"),
 ("scripts/regime_a_prime_qualification_v0_1/p2d_extract.py",
  "ACTIVATION_ROW","main()","context = range(target-15, target+1); layer-4 capture (:133-189)"),
 ("scripts/regime_a_prime_qualification_v0_1/p2e_analyze.py",
  "GROUND_TRUTH_TARGET","load()","world_x := coordinates[model_frame_idx].world_x (:57-76)"),
 ("src/mineocclude/regime_a_first25_analysis.py","-","-","frozen BEST-K / kernel ridge mechanics"),
 ("src/mineocclude/vision/magenta.py","-","detect_magenta()","frozen rendered-visibility detector"),
 ("scripts/regime_a_prime_qualification_v0_1/p3a_freeze.py","-","first_stable_hidden_onset()",
  "HIDDEN_BOUNDS fixed world-x constants (:39-42), speed-blind"),
]
inv={"artifact_id":"p2-temporal-alignment-evidence-inventory-v0.1",
     "label":"EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY",
     "phase":"PHASE_1","timing_source_map":[],"timing_streams":{},"evidence_used":{},
     "no_interpolation_or_nearest_join_found_in_pipeline":True,
     "ffmpeg_or_video_reencode_in_scientific_path":False}
for rel,domain,fn,role in SOURCE_MAP:
    p=R/rel
    if p.exists():
        inv["timing_source_map"].append({"path":rel,"clock_domain":domain,"function":fn,
            "role":role,"bytes":p.stat().st_size,"sha256":sha(p),"git_tracked":tracked(rel)})
inv["timing_streams"]={
 "server_state.jsonl":{"clock":"SERVER_ENTITY_STATE","key":"server_tick",
    "timing_fields":["server_epoch_nanos"],"carries":"sheep_x/y/z, geometric_visible, player_*"},
 "client_tick.jsonl":{"clock":"CAPTURE_FRAME","key":"server_tick",
    "timing_fields":["server_epoch_nanos","client_recv_nanos","client_capture_nanos","tick_queue_depth_at_capture"],
    "carries":"render_frame_idx, frame_path"},
 "actions.jsonl":{"clock":"ACTION","key":"action_idx"},
 "frames/NNNNNN.png":{"clock":"CAPTURE_FRAME","key":"filename index"},
 "visibility.jsonl":{"clock":"MODEL_FRAME","key":"model_frame_idx",
    "carries":"geometric_status, magenta_status, magenta_area_pixels, tau"},
 "coordinates.jsonl":{"clock":"SERVER_ENTITY_STATE (labelled with MODEL_FRAME index)",
    "key":"model_frame_idx","carries":"world_x (verified identical to sheep_x, max|delta|=0.0)"},
 "layer4/*.npy":{"clock":"ACTIVATION_ROW","shape":[19,336,2048],"dtype":"float16"},
}
inv["evidence_used"]={
 "P2_no_wall_diagnostic":{"s3":"s3://sagemaker-us-east-1-323206973672/mineocclude/regime_a_prime_qualification_v0_1/p2_no_wall_diagnostic_v0_1/",
   "units":25,"frames_per_unit":260,"speed_blocks_per_second":1.5,"scene":"NO_WALL",
   "frames_downloaded_for_lag":8,"activations_downloaded":25,"activation_bytes":653724800},
 "P3_development":{"s3":"s3://sagemaker-us-east-1-323206973672/mineocclude/regime_a_prime_qualification_v0_1/p3_sequential_development_v0_1/",
   "units":150,"calibrations":12,"frames_per_unit":180,"speeds":[2.0,2.5,3.0],
   "frames_downloaded_for_lag":4},
 "P1_last_seen_rows":{"path":"docs/status/integration/regime_a_prime_qualification_v0_1/p1_last_seen_rows.parquet",
   "rows":475,"used_for":"Regime A blast-radius reanalysis"},
}
for name in ("p1_last_seen_rows.parquet","p1_best_k_vs_last_seen.json","p2_best_k_results.json",
             "p2_full_results.json","p2_activation_manifest.json","p2_predictions.parquet",
             "p2_preoutcome_authority.json","p3_preoutcome_authority.json","p3_development_manifest.json"):
    p=Q/name
    if p.exists():
        inv.setdefault("historical_artifacts_read",[]).append(
            {"path":str(p.relative_to(R)),"sha256":sha(p),"bytes":p.stat().st_size,"access":"READ_ONLY"})
out=Q/"p2_temporal_alignment_forensic_v0_1/01_evidence_inventory.json"
out.write_text(json.dumps(inv,indent=2,sort_keys=True))
print("wrote",out,"| source map entries:",len(inv["timing_source_map"]))
