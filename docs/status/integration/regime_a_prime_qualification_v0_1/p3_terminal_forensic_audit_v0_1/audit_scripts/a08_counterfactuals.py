#!/usr/bin/env python3
"""EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY - margins, base-rate model, speed extrapolation."""
import json,sys
from pathlib import Path
import numpy as np
D=Path(sys.argv[1])
G=json.load(open("/home/sagemaker-user/MineOcclude/docs/status/integration/regime_a_prime_qualification_v0_1/p3_terminal_forensic_audit_v0_1/04_candidate_comparison.json"))["candidates"]
out={}
print("== 1. margin to each threshold ==")
for cid,R in G.items():
    c=R["CALIBRATION"]; v=R["speed_blocks_per_second"]
    need_fp=c["tp"]*(1/0.95-1)
    print(f"{cid} v={v}: precision={c['precision']:.4f} (need .95)  FP={c['fp']}  max FP allowed={need_fp:.1f}  excess_FP={c['fp']-need_fp:.1f}")
    print(f"        recall={c['recall']:.4f} PASSES;  specificity={c['specificity']:.4f}; FP-rate on occluded rows={c['false_positive_rate_on_occluded_rows']:.4f}")
    out[cid]={"excess_fp":c["fp"]-need_fp,"fp_rate":c["false_positive_rate_on_occluded_rows"],
              "base_rate":c["visible_base_rate"],"precision":c["precision"],"v":v}

print("\n== 2. is the FP RATE (the actual detector/geometry disagreement) speed-dependent? ==")
for cid,o in out.items(): print(f"  {cid} v={o['v']}: FP-rate={o['fp_rate']:.4f}   visible_base_rate={o['base_rate']:.4f}   precision={o['precision']:.4f}")
print("  -> FP-rate is ~flat; precision tracks base rate. Precision is BASE-RATE CONFOUNDED with the swept variable.")

print("\n== 3. base-rate model: occluded frames = shadow_span / (v*0.05); window fixed at 180 frames ==")
span=[]
for cid,o in out.items():
    occ=180*(1-o["base_rate"]); span.append(occ*o["v"]*0.05)
    print(f"  {cid}: occluded_frames/run={occ/1:.1f} -> implied shadow span={occ*o['v']*0.05:.3f} blocks")
SPAN=float(np.mean(span)); print(f"  mean shadow span = {SPAN:.3f} blocks (speed-invariant, as expected)")

print("\n== 4. EXTRAPOLATION: what speed would PASS the 0.95-precision calibration gate? ==")
band=np.mean([ (o['fp_rate']*180*(1-o['base_rate']))*o['v']*0.05 for o in out.values()])
print(f"  mean disagreement band (FP blocks per run) = {band:.3f} blocks")
for v in (2.0,2.5,3.0,3.25,3.5,3.75,4.0,4.5):
    vt=v*0.05; occ=SPAN/vt; tp=180-occ; fp=band/vt
    prec=tp/(tp+fp)
    print(f"   v={v:4.2f} b/s: occluded={occ:5.1f} visible={tp:5.1f} FP={fp:4.1f} -> precision={prec:.4f} {'PASS' if prec>=0.95 else 'FAIL'}")
print("  => the frozen gate becomes satisfiable at ~3.5 b/s purely by class-balance shift,")
print("     with NO improvement in geometric/rendered agreement.")

print("\n== 5. counter-trend: scientific NORMAL target-row contamination vs speed ==")
for cid,R in G.items():
    t=R["TARGET_VISIBILITY"]
    print(f"  {cid} v={R['speed_blocks_per_second']}: NORMAL_ok={t['normal_geometric_occluded_and_magenta_absent']}/475  contaminated={475-t['normal_geometric_occluded_and_magenta_absent']}")
print("  => target-row purity DEGRADES with speed while calibration precision IMPROVES. Directly opposed.")

print("\n== 6. single-trajectory exclusion sensitivity (calibration gate) ==")
for cid,R in G.items():
    c=R["CALIBRATION"]; fps=R["calibration_false_positive_rows"]
    byrun={}
    for f in fps: byrun[f["run"]]=byrun.get(f["run"],0)+1
    best=None
    for run,n in byrun.items():
        tp=c["tp"]; fp=c["fp"]-n
        # remove that run's TP share too (approx: 1/4 of tp)
        tp2=tp-round(tp/4); fp2=fp
        p=tp2/(tp2+fp2)
        if best is None or p>best[1]: best=(run,p)
    print(f"  {cid}: dropping worst calibration run -> best achievable precision={best[1]:.4f} (run {best[0]}) {'PASS' if best[1]>=0.95 else 'still FAIL'}")

print("\n== 7. lag-corrected agreement (shift geometric label by measured 3.3-tick render lag) ==")
def jl(p): return [json.loads(l) for l in p.read_text().splitlines() if l]
for cid in ("P3DEV_C01","P3DEV_C02","P3DEV_C03"):
    for k in (0,3,4):
        tp=fp=tn=fn=0
        for d in sorted((D/cid/"calibration").iterdir()):
            vis=jl(d/"raw/visibility.jsonl"); n=len(vis)
            geo=[r["geometric_status"]=="visible" for r in vis]
            mag=[r["magenta_status"]=="detected" for r in vis]
            for i in range(n):
                j=i-k
                if j<0: continue
                t=geo[j]; p=mag[i]
                tp+= t and p; fp+= (not t) and p; tn+= (not t) and (not p); fn+= t and (not p)
        pr=tp/(tp+fp) if tp+fp else 0; rc=tp/(tp+fn) if tp+fn else 0
        print(f"  {cid} lag_correction={k} ticks: precision={pr:.4f} recall={rc:.4f} fp={fp} {'PASS' if pr>=.95 and rc>=.95 else 'FAIL'}")
