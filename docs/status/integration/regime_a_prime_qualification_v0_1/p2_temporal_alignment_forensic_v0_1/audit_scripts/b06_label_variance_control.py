#!/usr/bin/env python3
"""EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY
Adversarial control for the P2 recomputation.

Concern: MODEL B's label is a smoothed (kernel-convolved) version of the logged
path, so part of its lower RMSE could be a trivial variance artifact rather than
a genuine alignment gain.  This script measures, decoder-free, how much label
variance each alignment model actually removes.  If the variance is essentially
unchanged, the RMSE/R2 gain cannot be a smoothing artifact.

Also reports the pure integer-shift labels (C_int3 / D_int4), which apply NO
smoothing at all and therefore have the same marginal statistics as the
historical label by construction.
"""
import json,sys
from pathlib import Path
import numpy as np
R=Path("/home/sagemaker-user/MineOcclude")
sys.path.insert(0,str(R)); sys.path.insert(0,str(R/"src"))
sys.path.insert(0,str(R/"scripts/regime_a_prime_qualification_v0_1"))
from p2_common import OUT, source_specs, p2_run_id, read_jsonl
DATA=Path(sys.argv[1]); KERN=json.load(open(sys.argv[2]))
H=np.asarray(KERN["mean_kernel"]); H=H/H.sum(); GD=float(KERN["group_delay_mean"])
man=json.loads((OUT/"p2_activation_manifest.json").read_text())
by_run={r["p2_no_wall_run_id"]:r for r in man["runs"]}

def xat(st,t):
    lo=int(np.floor(t)); f=t-lo; n=max(st)
    return st[max(0,min(lo,n))]*(1-f)+st[max(0,min(lo+1,n))]*f

labels={k:[] for k in ("A_historical","B_kernel_convolved","B2_point_group_delay",
                       "C_int3","D_int4","F_falsification_plus3")}
per_traj={k:{} for k in labels}
for spec in source_specs():
    ident=str(spec["trajectory_spec_id"]); run=p2_run_id(ident)
    st={int(r["server_tick"]):float(r["sheep_x"]) for r in read_jsonl(DATA/run/"raw/server_state.jsonl")}
    tgts=[int(v) for v in by_run[run]["targets"]]
    vals={"A_historical":[st[t] for t in tgts],
          "B_kernel_convolved":[sum(H[k]*st[max(0,t-k)] for k in range(len(H))) for t in tgts],
          "B2_point_group_delay":[xat(st,t-GD) for t in tgts],
          "C_int3":[st[max(0,t-3)] for t in tgts],
          "D_int4":[st[max(0,t-4)] for t in tgts],
          "F_falsification_plus3":[xat(st,t+3) for t in tgts]}
    for k,v in vals.items():
        labels[k]+=v; per_traj[k][ident]=float(np.std(v))

print(f"{'model':24s} {'pooled SD':>10s} {'mean within-traj SD':>21s} {'vs historical':>14s}")
base_p=float(np.std(labels["A_historical"]))
base_w=float(np.mean(list(per_traj["A_historical"].values())))
out={}
for k in labels:
    p=float(np.std(labels[k])); w=float(np.mean(list(per_traj[k].values())))
    out[k]={"pooled_sd":p,"mean_within_trajectory_sd":w,
            "within_traj_sd_ratio_vs_historical":w/base_w}
    print(f"{k:24s} {p:10.5f} {w:21.5f} {w/base_w:13.4f}x")
print()
print("The readout is scored trajectory-equal, so WITHIN-TRAJECTORY label SD is the")
print("relevant scale. If it is ~1.0x the historical value, the RMSE gain is NOT a")
print("variance/smoothing artifact.")
print()
print("MODEL A RMSE 0.166027 / within-traj SD %.5f = %.4f  (normalised error)" % (base_w,0.166027/base_w))
b=out["B_kernel_convolved"]["mean_within_trajectory_sd"]
print("MODEL B RMSE 0.077802 / within-traj SD %.5f = %.4f  (normalised error)" % (b,0.077802/b))
print()
print("Displacement implied by the lag at P2 speed 1.5 b/s: %.4f blocks" % (GD*1.5*0.05))
print("Irreducible unpredictable component over the lag (sigma=0.05 blocks/tick):")
print("   sqrt(%.3f)*0.05 = %.4f blocks" % (GD, np.sqrt(GD)*0.05))
print("Quadrature reduction actually observed A->B: %.4f blocks" %
      float(np.sqrt(0.166027**2-0.077802**2)))
json.dump({"artifact_id":"p2-label-variance-control-v0.1",
           "label":"EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY","models":out,
           "group_delay_ticks":GD},open(sys.argv[3],"w"),indent=2)
