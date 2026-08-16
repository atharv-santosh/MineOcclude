#!/usr/bin/env python3
"""EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY
Recompute the P2 layer-4 BEST-K and FULL readouts under alternative physical
image<->label alignments, using the FROZEN readout procedure unchanged
(best_k_readout / full_readout / summarize imported verbatim from p2e_analyze).
ONLY the label vector changes. Activations are the persisted P2 layer-4 tensors.

No new capture. No historical artifact is written or modified.
Alignment was estimated in b03_impulse_response.py from physics alone; it is
NOT tuned against any readout metric here.
"""
import json,sys,hashlib
from pathlib import Path
import numpy as np
R=Path("/home/sagemaker-user/MineOcclude")
sys.path.insert(0,str(R)); sys.path.insert(0,str(R/"src"))
sys.path.insert(0,str(R/"scripts/regime_a_prime_qualification_v0_1"))
from p2_common import OUT, source_specs, p2_run_id, read_jsonl
import p2e_analyze as PA

DATA=Path(sys.argv[1]); OUTJ=Path(sys.argv[2])
KERN=json.load(open(sys.argv[3]))
H=np.asarray(KERN["mean_kernel"],dtype=np.float64); H=H/H.sum()
GD=float(KERN["group_delay_mean"]); CI=KERN["group_delay_ci95"]

def build():
    manifest=json.loads((OUT/"p2_activation_manifest.json").read_text())
    specs=source_specs(); by_run={r["p2_no_wall_run_id"]:r for r in manifest["runs"]}
    rows=[];arrays=[];ids=[];outer={};direction={};xseries={}
    for spec in specs:
        ident=str(spec["trajectory_spec_id"]); run=p2_run_id(ident); rec=by_run[run]
        npy=DATA/run/"layer4"/f"{run}.layer_04.npy"
        arr=np.load(npy,mmap_mode="r")
        assert arr.shape==(19,336,2048) and arr.dtype==np.float16, run
        st={int(r["server_tick"]):float(r["sheep_x"]) for r in read_jsonl(DATA/run/"raw/server_state.jsonl")}
        xseries[ident]=st
        coords={int(r["model_frame_idx"]):r for r in read_jsonl(DATA/run/"coordinates.jsonl")}
        for off,frame in enumerate(int(v) for v in rec["targets"]):
            rows.append({"trajectory_id":ident,"p2_no_wall_run_id":run,"activation_row":off,
                         "model_frame_idx":frame,"server_tick":frame,"tau":off+1,
                         "outer_fold":int(spec["outer_fold"]),"direction":spec["direction"],
                         "world_x":float(coords[frame]["world_x"])})
        arrays.append(arr); ids.append(ident)
        outer[ident]=int(spec["outer_fold"]); direction[ident]=str(spec["direction"])
    feats=np.concatenate(arrays,axis=0)
    assert feats.shape==(475,336,2048) and len(rows)==475
    return feats,rows,ids,outer,direction,xseries

def xat(st,t):
    """position at (possibly fractional) tick t, linear interpolation, clamped to run."""
    lo=int(np.floor(t)); hi=lo+1; f=t-lo
    n=max(st); lo=max(0,min(lo,n)); hi=max(0,min(hi,n))
    return st[lo]*(1-f)+st[hi]*f

def label(model,rows,xs,direction):
    out=np.empty(len(rows))
    for i,r in enumerate(rows):
        st=xs[r["trajectory_id"]]; t=r["server_tick"]
        if model=="A_historical":            out[i]=st[t]
        elif model=="B_kernel_convolved":    out[i]=sum(H[k]*st[max(0,t-k)] for k in range(len(H)))
        elif model=="B2_point_group_delay":  out[i]=xat(st,t-GD)
        elif model=="C_lower_bound":         out[i]=xat(st,t-CI[0])
        elif model=="D_upper_bound":         out[i]=xat(st,t-CI[1])
        elif model=="C_int3":                out[i]=st[max(0,t-3)]
        elif model=="D_int4":                out[i]=st[max(0,t-4)]
        elif model=="E_direction_aware":
            d=3.287 if direction[r["trajectory_id"]]=="LEFT_TO_RIGHT" else 3.516
            out[i]=xat(st,t-d)
        elif model=="F_falsification_plus3": out[i]=xat(st,t+3)   # WRONG-SIGN control
        else: raise ValueError(model)
    return out

if __name__=="__main__":
    feats,rows,ids,outer,direction,xs=build()
    MODELS=["A_historical","B_kernel_convolved","B2_point_group_delay","C_lower_bound",
            "D_upper_bound","C_int3","D_int4","E_direction_aware","F_falsification_plus3"]
    results={"artifact_id":"p2-corrected-alignment-metrics-v0.1",
             "label":"EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY",
             "alignment_source":"b03_impulse_response.py (physics only; NOT tuned on readout metrics)",
             "group_delay_ticks":GD,"group_delay_ci95":CI,"kernel":H.tolist(),
             "activation_source":str(DATA),"procedure":"frozen p2e_analyze.best_k_readout/full_readout/summarize",
             "models":{}}
    for m in MODELS:
        y=label(m,rows,xs,direction)
        for i,r in enumerate(rows): r["world_x"]=float(y[i])
        tgt=np.asarray(y,dtype=np.float64)
        best_oof,best_sel,_=PA.best_k_readout(feats,tgt,rows,ids,outer,direction)
        full_oof,full_sel,_=PA.full_readout(feats,tgt,rows,ids,outer,direction)
        for i,r in enumerate(rows):
            r["predicted_layer4_best_k"]=float(best_oof[i]); r["predicted_layer4_full"]=float(full_oof[i])
        bk=PA.summarize(rows,"predicted_layer4_best_k"); fl=PA.summarize(rows,"predicted_layer4_full")
        for d in (bk,fl): d.pop("per_trajectory",None)
        results["models"][m]={"label_sd_blocks":float(np.std(tgt)),"BEST_K":bk,"FULL":fl,
                              "best_k_selection":best_sel,"full_selection":full_sel}
        print(f"{m:24s} BEST-K rmse={bk['rmse_blocks']:.6f} mae={bk['mae_blocks']:.6f} "
              f"macroR2={bk['macro_r2']:.6f} boot=[{bk['bootstrap']['lower_2_5']:.4f},{bk['bootstrap']['upper_97_5']:.4f}] "
              f"| FULL rmse={fl['rmse_blocks']:.6f} macroR2={fl['macro_r2']:.6f}")
        sys.stdout.flush()
    OUTJ.write_text(json.dumps(results,indent=2,sort_keys=True))
    print("\nwrote",OUTJ)
