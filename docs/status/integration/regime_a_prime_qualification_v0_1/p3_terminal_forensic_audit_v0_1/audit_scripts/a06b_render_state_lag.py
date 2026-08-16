#!/usr/bin/env python3
"""EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY
Direct render-vs-logged-state temporal alignment measurement.
Vectorised re-implementation of the frozen magenta detector (hsv 280-320deg, s>=0.5, v>=0.35,
8-connectivity, largest valid blob, area in [19,5000]) validated against the frozen detector,
then used to recover the blob centroid on NO_WALL runs (no occluder => silhouette always whole).
"""
import json,sys
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage
sys.path.insert(0,"/home/sagemaker-user/MineOcclude"); sys.path.insert(0,"/home/sagemaker-user/MineOcclude/src")

DATA=Path(sys.argv[1])
CFG=json.load(open("/home/sagemaker-user/MineOcclude/docs/status/person_e_phase3_step3_1_candidate_freeze_v0_1/detector_candidate_config.json"))["configuration"]["detector_settings"]
HMIN,HMAX,SMIN,SMAX,VMIN,VMAX=CFG["hsv_ranges"][0]
MINA,MAXA=CFG["min_area_pixels"],CFG["max_area_pixels"]
def jl(p): return [json.loads(l) for l in p.read_text().splitlines() if l]

def blob(png):
    a=np.asarray(Image.open(png).convert("RGB"),dtype=np.float32)/255.0
    mx=a.max(2); mn=a.min(2); d=mx-mn
    v=mx; s=np.where(mx>0,d/np.maximum(mx,1e-12),0.0)
    r,g,b=a[...,0],a[...,1],a[...,2]
    h=np.zeros_like(mx); m=d>0
    i=(mx==r)&m; h[i]=((g-b)[i]/d[i])%6
    i=(mx==g)&m; h[i]=((b-r)[i]/d[i])+2
    i=(mx==b)&m; h[i]=((r-g)[i]/d[i])+4
    h=(h*60.0)%360.0
    mask=(h>=HMIN)&(h<=HMAX)&(s>=SMIN)&(s<=SMAX)&(v>=VMIN)&(v<=VMAX)
    if not mask.any(): return None,0
    lab,n=ndimage.label(mask,structure=np.ones((3,3),bool))
    sizes=ndimage.sum(mask,lab,range(1,n+1))
    valid=[(sz,k+1) for k,sz in enumerate(sizes) if MINA<=sz<=MAXA]
    if not valid: return None,0
    sz,k=max(valid)
    ys,xs=np.nonzero(lab==k)
    return float(xs.mean()),int(sz)

# --- validation against frozen detector on sample frames ---
from mineocclude.vision.magenta import HsvRange, detect_magenta
from scripts.run_regime_a import detector_rgb_rows
TH=(HsvRange(HMIN,HMAX,SMIN,SMAX,VMIN,VMAX),)
val=[]
d0=DATA/"P3DEV_C01/capture/p3dev_c01_t01_nowall"
for i in (0,20,60,100,150):
    ref=detect_magenta(detector_rgb_rows(d0/f"raw/frames/{i:06d}.png",expected_size=(640,360)),
        hsv_ranges=TH,min_area_pixels=MINA,max_area_pixels=MAXA,open_iterations=CFG["open_iterations"],
        close_iterations=CFG["close_iterations"],morphology_radius_pixels=CFG["morphology_radius_pixels"],
        connectivity=CFG["connectivity"])
    cx,ar=blob(d0/f"raw/frames/{i:06d}.png")
    val.append((i,ref.status,ref.area_pixels,ar,None if ref.centroid_xy is None else round(ref.centroid_xy[0],3),
                None if cx is None else round(cx,3)))
print("VALIDATION frame | frozen_status frozen_area mine_area | frozen_cx mine_cx")
for r in val: print("  ",r)

SPEED={"P3DEV_C01":2.0,"P3DEV_C03":3.0}
print("\nrun                         dir  v(b/tick)  best_lag_ticks  rms_px@best  px_per_block")
for cand,rid in [("P3DEV_C01","p3dev_c01_t01_nowall"),("P3DEV_C01","p3dev_c01_t06_nowall"),
                 ("P3DEV_C03","p3dev_c03_t01_nowall"),("P3DEV_C03","p3dev_c03_t06_nowall")]:
    d=DATA/cand/"capture"/rid
    if not (d/"raw/frames").exists(): print(f"{rid}: frames absent"); continue
    st={int(r["server_tick"]):float(r["sheep_x"]) for r in jl(d/"raw/server_state.jsonl")}
    n=len(st); x=np.array([st[i] for i in range(n)])
    cx=np.full(n,np.nan)
    for i in range(n):
        c,_=blob(d/f"raw/frames/{i:06d}.png")
        if c is not None: cx[i]=c
    dirn="LTR" if x[1]>x[0] else "RTL"
    prof=[]
    for k in range(-6,7):
        j=np.arange(n)-k
        m=(j>=0)&(j<n)&~np.isnan(cx)
        m&= np.abs(x[np.clip(j,0,n-1)])<7.5
        if m.sum()<40: prof.append((k,None)); continue
        A=np.vstack([x[j[m]],np.ones(m.sum())]).T
        coef,_,_,_=np.linalg.lstsq(A,cx[m],rcond=None)
        prof.append((k,float(np.sqrt(np.mean((cx[m]-A@coef)**2))),float(coef[0]),int(m.sum())))
    good=[p for p in prof if p[1] is not None]
    best=min(good,key=lambda p:p[1])
    # sub-tick minimum by parabolic interpolation around best
    ks=[p[0] for p in good]; rs=[p[1] for p in good]
    bi=ks.index(best[0]); sub=best[0]
    if 0<bi<len(ks)-1:
        y0,y1,y2=rs[bi-1],rs[bi],rs[bi+1]
        den=(y0-2*y1+y2)
        if den!=0: sub=best[0]+0.5*(y0-y2)/den
    print(f"{rid:28s} {dirn}  {SPEED[cand]*0.05:.3f}      {best[0]:+d} (sub {sub:+.2f})   {best[1]:.3f}      {best[2]:.2f}  n={best[3]}")
    print("     rms_px by lag: "+"  ".join(f"{p[0]:+d}:{p[1]:.2f}" for p in good))
