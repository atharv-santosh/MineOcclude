#!/usr/bin/env python3
"""EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY
Phase 10: independently verify PATH_IMPLEMENTATION_MATCHES_AUTHORITY=false and
measure the blast radius -- i.e. would a COMPLETE authority-scope path/state gate
have reached a different verdict on the historical P3 cohort?
Historical verdicts are read only; nothing is rewritten.
"""
import json,sys,hashlib
from pathlib import Path
import numpy as np
DATA=Path(sys.argv[1])
Q=Path("/home/sagemaker-user/MineOcclude/docs/status/integration/regime_a_prime_qualification_v0_1")
MAN=json.load(open(Q/"p3_development_manifest.json"))
AUTH=json.load(open(Q/"p3_preoutcome_authority.json"))
def jl(p): return [json.loads(l) for l in p.read_text().splitlines() if l]
FIX=AUTH["fixed_apparatus"]
CAM=FIX["camera_eye_world_xyz"]

print("AUTHORITY exact_fields:",AUTH["path_and_state_gate"]["exact_fields"])
print("AUTHORITY rows_checked_per_scene_per_candidate:",AUTH["path_and_state_gate"]["rows_checked_per_scene_per_candidate"])
print()
summary={}
for cand in MAN["candidates"]:
    cid=cand["candidate_id"]
    checks={k:0 for k in ("sheep_x_sha","paired_x_equal","sheep_y_const","sheep_z_const",
                          "camera_eye_xyz","camera_bitwise_constant","camera_yaw_pitch",
                          "tick_dense","tick_order","scene_field","seed_field","spec_hash_field",
                          "spec_id_field","q_field","v_field","v_sign_matches_direction",
                          "commanded_v_field","respawn_zero","uuid_single","row_count")}
    fails={k:[] for k in checks}
    rows_checked=0
    for spec in cand["specs"]:
        paths={}
        for sc in ("NORMAL","NO_WALL"):
            rid=spec["paired_runs"][sc]["run_id"]
            st=jl(DATA/cid/"capture"/rid/"raw/server_state.jsonl")
            rows_checked+=len(st)
            x=np.asarray([float(r["sheep_x"]) for r in st],dtype="<f8"); paths[sc]=x
            def chk(name,cond):
                if cond: checks[name]+=1
                else: fails[name].append(rid)
            chk("sheep_x_sha",hashlib.sha256(x.tobytes()).hexdigest()==spec["expected_path_sha256"])
            chk("sheep_y_const",all(float(r["sheep_y"])==4.0 for r in st))
            chk("sheep_z_const",all(float(r["sheep_z"])==6.0 for r in st))
            # The authority stores the eye height as a 10-decimal rounding of the
            # true float (5.6200000048 vs 5.620000004768372, delta 3.2e-11), so an
            # exact comparison against the authority constant is not meaningful.
            # Compare within that rounding, and separately require bitwise
            # constancy across every row of the run.
            chk("camera_eye_xyz",all(abs(float(r["player_x"])-CAM[0])<1e-9
                                     and abs(float(r["player_y"])-CAM[1])<1e-9
                                     and abs(float(r["player_z"])-CAM[2])<1e-9 for r in st))
            chk("camera_bitwise_constant",len({(r["player_x"],r["player_y"],r["player_z"]) for r in st})==1)
            chk("camera_yaw_pitch",all(float(r["player_yaw"])==0.0 and float(r["player_pitch"])==0.0 for r in st))
            chk("tick_dense",[int(r["server_tick"]) for r in st]==list(range(len(st))))
            chk("scene_field",all(r["scene"]==sc for r in st))
            chk("seed_field",all(int(r["seed"])==int(spec["seed"]) for r in st))
            chk("spec_hash_field",all(r["spec_hash"]==spec["spec_hash"] for r in st))
            chk("spec_id_field",all(r["trajectory_spec_id"]==spec["trajectory_spec_id"] for r in st))
            chk("q_field",all(float(r["q"])==float(spec["motion_noise_q"]) for r in st))
            # server_state.v is the SIGNED commanded velocity; the spec records
            # unsigned speed plus a separate direction. Compare magnitude, and
            # check the sign against the spec direction.
            sign=1.0 if spec["direction"]=="LEFT_TO_RIGHT" else -1.0
            chk("v_field",all(abs(float(r["v"]))==float(spec["speed_blocks_per_second"]) for r in st))
            chk("v_sign_matches_direction",all(float(r["v"])*sign>0 for r in st))
            chk("commanded_v_field",all(float(r["commanded_v"])==float(r["v"]) for r in st))
            chk("respawn_zero",all(int(r["target_respawn_count"])==0 for r in st))
            chk("uuid_single",len({r["target_entity_uuid"] for r in st})==1)
            chk("row_count",len(st)==int(spec["expected_max_frames"]))
            # target tick IDs and order
            vis={int(r["server_tick"]):r for r in jl(DATA/cid/"capture"/rid/"raw/visibility.jsonl")}
            tt=list(spec["target_server_ticks"])
            chk("tick_order",tt==sorted(tt) and len(set(tt))==19 and all(t in vis for t in tt))
        checks["paired_x_equal"]+= 1 if np.array_equal(paths["NORMAL"],paths["NO_WALL"]) else 0
        if not np.array_equal(paths["NORMAL"],paths["NO_WALL"]): fails["paired_x_equal"].append(spec["trajectory_spec_id"])
    expect_run=len(cand["specs"])*2
    print(f"--- {cid} (rows checked={rows_checked}; authority says 4500 per scene = {4500*2} total) ---")
    for k in checks:
        exp = len(cand["specs"]) if k=="paired_x_equal" else expect_run
        status="OK " if checks[k]==exp else "FAIL"
        print(f"   {status} {k:18s} {checks[k]}/{exp}" + (f"  failures={fails[k][:3]}" if fails[k] else ""))
    summary[cid]={"rows_checked_total":rows_checked,"checks":checks,
                  "any_failure":any(fails[k] for k in fails)}
print()
print("BLAST RADIUS: a complete authority-scope gate would have changed a verdict:",
      any(v["any_failure"] for v in summary.values()))
json.dump({"artifact_id":"p3-path-gate-blast-radius-v0.1",
           "label":"EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY",
           "implemented_by_historical_gate":["sha256 of sheep_x column","NORMAL==NO_WALL on sheep_x"],
           "authority_exact_fields":AUTH["path_and_state_gate"]["exact_fields"],
           "independently_rechecked":summary},open(sys.argv[2],"w"),indent=2)
