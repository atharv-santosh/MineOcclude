#!/usr/bin/env python3
"""EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY
Fully independent reimplementation of the P3 non-neural gates from durable raw data,
written without reference to p3_run_sequential.py's control flow.
Sources: p3_development_manifest.json (frozen) + S3-restored raw/{server_state,visibility}.jsonl
"""
import json, hashlib, sys, statistics as S
from pathlib import Path
import numpy as np

DATA = Path(sys.argv[1])
OUT  = Path(sys.argv[2])
MAN  = json.load(open("/home/sagemaker-user/MineOcclude/docs/status/integration/regime_a_prime_qualification_v0_1/p3_development_manifest.json"))
AUTH = json.load(open("/home/sagemaker-user/MineOcclude/docs/status/integration/regime_a_prime_qualification_v0_1/p3_preoutcome_authority.json"))
def jl(p): return [json.loads(l) for l in p.read_text().splitlines() if l]

MIN_EACH = AUTH["prospective_headroom_gate"]["minimum_each_trajectory_target_sd_blocks"]
MIN_MED  = AUTH["prospective_headroom_gate"]["minimum_candidate_median_target_sd_blocks"]

report = {"artifact_id":"p3-forensic-independent-gate-reconstruction-v0.1",
          "label":"EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY","candidates":{}}

for cand in MAN["candidates"]:
    cid = cand["candidate_id"]
    R = {"speed_blocks_per_second": cand["motion_parameter"]["speed_blocks_per_second"]}
    # ---------- inventory ----------
    capdir = DATA/cid/"capture"; caldir = DATA/cid/"calibration"
    cap_units = sorted(p.name for p in capdir.iterdir() if p.is_dir())
    cal_units = sorted(p.name for p in caldir.iterdir() if p.is_dir())
    R["capture_unit_count"]=len(cap_units); R["calibration_unit_count"]=len(cal_units)
    R["capture_units_unique"]= len(set(cap_units))==len(cap_units)
    R["wall_units"]=sum(1 for u in cap_units if u.endswith("_wall"))
    R["nowall_units"]=sum(1 for u in cap_units if u.endswith("_nowall"))
    expected_ids=set()
    for s in cand["specs"]:
        for sc in ("NORMAL","NO_WALL"): expected_ids.add(s["paired_runs"][sc]["run_id"])
    R["missing_units"]=sorted(expected_ids-set(cap_units)); R["extra_units"]=sorted(set(cap_units)-expected_ids)
    R["expected_max_frames"]=sorted({s["expected_max_frames"] for s in cand["specs"]})
    R["calib_expected_max_frames"]=sorted({s["expected_max_frames"] for s in cand["visibility_calibration_specs"]})
    R["stable_hidden_onset_ticks"]=sorted({s["expected_stable_hidden_onset_server_tick"] for s in cand["specs"]})

    # ---------- PATH gate ----------
    path_fail=[]; paired_fail=[]; frame_counts=set(); scene_field_bad=[]; tick_ident_bad=[]
    for s in cand["specs"]:
        paths={}
        for sc in ("NORMAL","NO_WALL"):
            rid=s["paired_runs"][sc]["run_id"]
            st=jl(capdir/rid/"raw/server_state.jsonl")
            frame_counts.add(len(st))
            obs=np.asarray([float(r["sheep_x"]) for r in st],dtype="<f8")
            paths[sc]=obs
            if hashlib.sha256(obs.tobytes()).hexdigest()!=s["expected_path_sha256"]: path_fail.append(rid)
            if any(r.get("scene")!=sc for r in st): scene_field_bad.append(rid)
            if [r.get("server_tick") for r in st]!=list(range(len(st))): tick_ident_bad.append(rid)
        if not np.array_equal(paths["NORMAL"],paths["NO_WALL"]): paired_fail.append(s["trajectory_spec_id"])
    R["PATH"]={"path_failures":path_fail,"paired_path_failures":paired_fail,
               "status":"PASS" if not path_fail and not paired_fail else "FAIL",
               "distinct_frame_counts":sorted(frame_counts),
               "scene_field_mismatch":scene_field_bad,"tick_identity_mismatch":tick_ident_bad,
               "rows_checked_per_scene":len(cand["specs"])*max(frame_counts)}

    # ---------- TARGET-ROW visibility ----------
    normal_ok=nowall_ok=disagree=0; tgt_rows=[]
    for s in cand["specs"]:
        for sc in ("NORMAL","NO_WALL"):
            rid=s["paired_runs"][sc]["run_id"]
            vis={int(r["server_tick"]):r for r in jl(capdir/rid/"raw/visibility.jsonl")}
            st ={int(r["server_tick"]):r for r in jl(capdir/rid/"raw/server_state.jsonl")}
            for k,t in enumerate(s["target_server_ticks"]):
                r=vis[int(t)]; g=r["geometric_status"]=="visible"; m=r["magenta_status"]=="detected"
                if sc=="NORMAL": normal_ok += (not g) and (not m)
                else: nowall_ok += g and m
                disagree += g!=m
                tgt_rows.append(dict(spec=s["trajectory_spec_id"],scene=sc,tau=k+1,tick=int(t),
                                     x=float(st[int(t)]["sheep_x"]),geo=g,mag=m,
                                     area=r["magenta_area_pixels"],direction=s["direction"]))
    R["TARGET_VISIBILITY"]={"normal_geometric_occluded_and_magenta_absent":normal_ok,
                            "no_wall_geometric_visible_and_magenta_detected":nowall_ok,
                            "disagreements":disagree,"required":475}

    # ---------- CALIBRATION gate ----------
    tp=fp=tn=fn=amb=rows=0; occ_rows=0; cal_detail=[]
    for cs in cand["visibility_calibration_specs"]:
        d=caldir/cs["calibration_id"]
        vis=jl(d/"raw/visibility.jsonl"); st={int(r["server_tick"]):r for r in jl(d/"raw/server_state.jsonl")}
        for r in vis:
            g=r["geometric_status"]=="visible"; m=r["magenta_status"]=="detected"
            tp+= g and m; fp+= (not g) and m; tn+= (not g) and (not m); fn+= g and (not m)
            amb += r["magenta_status"] not in ("detected","not_detected"); rows+=1
            occ_rows += (not g)
            if (not g) and m:
                cal_detail.append(dict(run=cs["calibration_id"],dir=cs["direction"],tick=r["server_tick"],
                                       x=round(float(st[int(r["server_tick"])]["sheep_x"]),4),
                                       area=r["magenta_area_pixels"]))
    prec=tp/(tp+fp) if tp+fp else 0.0; rec=tp/(tp+fn) if tp+fn else 0.0
    spec_=tn/(tn+fp) if tn+fp else 0.0
    R["CALIBRATION"]={"rows":rows,"tp":tp,"fp":fp,"tn":tn,"fn":fn,"ambiguous":amb,
                      "precision":prec,"recall":rec,"specificity":spec_,
                      "false_positive_rate_on_occluded_rows":1-spec_,
                      "visible_base_rate":(tp+fn)/rows,"occluded_rows":occ_rows,
                      "status":"PASS" if prec>=.95 and rec>=.95 and amb==0 else "FAIL",
                      "failing_predicate":("precision" if prec<.95 else "")+("|recall" if rec<.95 else "")}
    R["VISIBILITY_STATUS"]="PASS" if (R["CALIBRATION"]["status"]=="PASS" and normal_ok==475
                                      and nowall_ok==475 and disagree==0) else "FAIL"

    # ---------- HEADROOM gate (recomputed from frozen manifest target paths) ----------
    sds=[float(np.std(np.asarray(s["expected_target_world_x_blocks"],dtype="<f8"),ddof=1)) for s in cand["specs"]]
    claimed=[float(s["expected_target_sd_blocks"]) for s in cand["specs"]]
    sd_pop=[float(np.std(np.asarray(s["expected_target_world_x_blocks"],dtype="<f8"))) for s in cand["specs"]]
    h=cand["prospective_path_headroom"]
    R["HEADROOM"]={"manifest":h,
        "recomputed_min_sd_ddof1":min(sds),"recomputed_median_sd_ddof1":S.median(sds),"recomputed_max_sd_ddof1":max(sds),
        "recomputed_min_sd_ddof0":min(sd_pop),"recomputed_median_sd_ddof0":S.median(sd_pop),
        "matches_claimed_ddof1":max(abs(a-b) for a,b in zip(sds,claimed))<1e-9,
        "status":"PASS" if (h["minimum_target_sd_blocks"]>=MIN_EACH and h["median_target_sd_blocks"]>=MIN_MED
                            and h["passes_deterministic_design_check"]) else "FAIL"}
    # observed target-row SD from actual captures (NORMAL)
    obs_sd=[]
    for s in cand["specs"]:
        rid=s["paired_runs"]["NORMAL"]["run_id"]
        st={int(r["server_tick"]):float(r["sheep_x"]) for r in jl(capdir/rid/"raw/server_state.jsonl")}
        xs=np.asarray([st[int(t)] for t in s["target_server_ticks"]],dtype="<f8")
        obs_sd.append(float(np.std(xs,ddof=1)))
        # frozen-vs-observed target world x agreement
    R["HEADROOM"]["observed_min_sd"]=min(obs_sd); R["HEADROOM"]["observed_median_sd"]=S.median(obs_sd)
    R["HEADROOM"]["frozen_vs_observed_max_abs_sd_delta"]=max(abs(a-b) for a,b in zip(sds,obs_sd))

    R["OVERALL"]={"capture_status":"PASS" if len(cap_units)==50 else "FAIL",
                  "path_status":R["PATH"]["status"],"visibility_status":R["VISIBILITY_STATUS"],
                  "headroom_status":R["HEADROOM"]["status"]}
    R["OVERALL"]["qualification"]= "PASS_TO_EXTRACTION" if set(R["OVERALL"].values())=={"PASS"} else "FAIL_ADVANCE_ALLOWED"
    R["calibration_false_positive_rows"]=cal_detail
    report["candidates"][cid]=R

OUT.write_text(json.dumps(report,indent=2,sort_keys=True))
for cid,R in report["candidates"].items():
    print(f"\n===== {cid} (v={R['speed_blocks_per_second']}) =====")
    print(f" units capture={R['capture_unit_count']} (wall={R['wall_units']} nowall={R['nowall_units']}) calib={R['calibration_unit_count']}")
    print(f" missing={R['missing_units']} extra={R['extra_units']} frames={R['PATH']['distinct_frame_counts']} hidden_onset={R['stable_hidden_onset_ticks']}")
    print(f" PATH   : {R['PATH']['status']}  failures={R['PATH']['path_failures']} paired={R['PATH']['paired_path_failures']} scene_bad={R['PATH']['scene_field_mismatch']} tick_bad={R['PATH']['tick_identity_mismatch']}")
    t=R['TARGET_VISIBILITY']; print(f" TARGET : NORMAL_ok={t['normal_geometric_occluded_and_magenta_absent']}/475 NOWALL_ok={t['no_wall_geometric_visible_and_magenta_detected']}/475 disagree={t['disagreements']}")
    c=R['CALIBRATION']; print(f" CALIB  : {c['status']} prec={c['precision']:.4f} rec={c['recall']:.4f} spec={c['specificity']:.4f} FPrate={c['false_positive_rate_on_occluded_rows']:.4f} base_rate={c['visible_base_rate']:.4f} (tp={c['tp']} fp={c['fp']} tn={c['tn']} fn={c['fn']})")
    h=R['HEADROOM']; print(f" HEADROOM: {h['status']} min={h['manifest']['minimum_target_sd_blocks']:.4f}>={MIN_EACH:.4f} med={h['manifest']['median_target_sd_blocks']:.4f}>={MIN_MED:.4f} recompute_match={h['matches_claimed_ddof1']} frozen_vs_observed_delta={h['frozen_vs_observed_max_abs_sd_delta']:.2e}")
    print(f" OVERALL: {R['OVERALL']}")
