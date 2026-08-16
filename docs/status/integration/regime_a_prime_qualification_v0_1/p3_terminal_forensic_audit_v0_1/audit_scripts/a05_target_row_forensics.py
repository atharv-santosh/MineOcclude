#!/usr/bin/env python3
"""EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY - locate every scientific target-row visibility disagreement."""
import json,sys,statistics as S
from pathlib import Path
import numpy as np
DATA=Path(sys.argv[1])
MAN=json.load(open("/home/sagemaker-user/MineOcclude/docs/status/integration/regime_a_prime_qualification_v0_1/p3_development_manifest.json"))
def jl(p): return [json.loads(l) for l in p.read_text().splitlines() if l]

print("== scientific target-row disagreements (NORMAL scene) ==")
for cand in MAN["candidates"]:
    cid=cand["candidate_id"]; bad=[]
    margins=[]
    for s in cand["specs"]:
        rid=s["paired_runs"]["NORMAL"]["run_id"]
        vis={int(r["server_tick"]):r for r in jl(DATA/cid/"capture"/rid/"raw/visibility.jsonl")}
        st ={int(r["server_tick"]):r for r in jl(DATA/cid/"capture"/rid/"raw/server_state.jsonl")}
        # margin: how many ticks between geometric occlusion onset and first target tick
        geo=[(t,st[t]) for t in sorted(st)]
        onset=None
        for t in sorted(vis):
            if vis[t]["geometric_status"]=="occluded": onset=t; break
        first_tgt=int(s["target_server_ticks"][0])
        margins.append(first_tgt-onset if onset is not None else None)
        for k,t in enumerate(s["target_server_ticks"]):
            r=vis[int(t)]
            if r["magenta_status"]=="detected":
                bad.append(dict(spec=s["trajectory_spec_id"],dir=s["direction"],tau=k+1,tick=int(t),
                                x=round(float(st[int(t)]["sheep_x"]),4),area=r["magenta_area_pixels"],
                                onset_tick=onset,phase=s["occlusion_phase_frames"],
                                margin_ticks=first_tgt-onset))
    print(f"\n-- {cid} v={cand['motion_parameter']['speed_blocks_per_second']} : {len(bad)} contaminated NORMAL target rows")
    for b in bad: print("   ",b)
    m=[x for x in margins if x is not None]
    print(f"   margin (first_target_tick - geometric_onset_tick): min={min(m)} median={S.median(m)} max={max(m)}")
    # how many ticks does the transition band last at this speed?
    print(f"   transition band ~1.04 blocks => {1.04/(cand['motion_parameter']['speed_blocks_per_second']*0.05):.1f} ticks")

print("\n== headroom SD recomputation (ddof discrimination) ==")
for cand in MAN["candidates"]:
    cid=cand["candidate_id"]
    s0=cand["specs"][0]
    x=np.asarray(s0["expected_target_world_x_blocks"],dtype="<f8")
    print(f"{cid} spec0 claimed={s0['expected_target_sd_blocks']:.12f} ddof0={np.std(x):.12f} ddof1={np.std(x,ddof=1):.12f}")
    sds0=[float(np.std(np.asarray(s['expected_target_world_x_blocks']))) for s in cand["specs"]]
    cl=[float(s['expected_target_sd_blocks']) for s in cand["specs"]]
    print(f"   ddof0 max|delta| vs claimed = {max(abs(a-b) for a,b in zip(sds0,cl)):.3e}   min={min(sds0):.6f} median={S.median(sds0):.6f}")
    h=cand["prospective_path_headroom"]
    print(f"   manifest min={h['minimum_target_sd_blocks']:.6f} median={h['median_target_sd_blocks']:.6f} max={h['maximum_target_sd_blocks']:.6f}")
