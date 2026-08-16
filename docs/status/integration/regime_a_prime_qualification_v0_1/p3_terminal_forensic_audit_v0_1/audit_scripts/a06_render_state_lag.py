#!/usr/bin/env python3
"""EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY
Direct measurement of render-vs-logged-state temporal alignment using NO_WALL runs
(no occluder => full silhouette always visible). Compares the magenta blob's image-space
centroid against the homography projection of the logged sheep_x for lag k in {-6..+6}.
"""
import json,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,"/home/sagemaker-user/MineOcclude")
sys.path.insert(0,"/home/sagemaker-user/MineOcclude/src")
from mineocclude.vision.magenta import HsvRange, detect_magenta
from scripts.run_regime_a import detector_rgb_rows

DATA=Path(sys.argv[1])
CFG=json.load(open("/home/sagemaker-user/MineOcclude/docs/status/person_e_phase3_step3_1_candidate_freeze_v0_1/detector_candidate_config.json"))["configuration"]["detector_settings"]
TH=tuple(HsvRange(*v) for v in CFG["hsv_ranges"])
def jl(p): return [json.loads(l) for l in p.read_text().splitlines() if l]

def blob_centroid_x(png):
    rgb=detector_rgb_rows(png,expected_size=(640,360))
    r=detect_magenta(rgb,hsv_ranges=TH,min_area_pixels=CFG["min_area_pixels"],
        max_area_pixels=CFG["max_area_pixels"],open_iterations=CFG["open_iterations"],
        close_iterations=CFG["close_iterations"],morphology_radius_pixels=CFG["morphology_radius_pixels"],
        connectivity=CFG["connectivity"])
    if r.status!="detected": return None,None
    for attr in ("centroid_x","centroid","cx"):
        v=getattr(r,attr,None)
        if v is not None: return (v[0] if isinstance(v,(tuple,list)) else v), r.area_pixels
    a=np.asarray(rgb,dtype=np.uint8)
    import colorsys
    # fallback: recompute mask centroid from HSV ranges directly
    import numpy as _np
    arr=a.astype(_np.float32)/255.0
    mx=arr.max(2); mn=arr.min(2); v=mx; d=mx-mn
    s=_np.where(mx>0,d/_np.maximum(mx,1e-9),0)
    h=_np.zeros_like(mx)
    rr,gg,bb=arr[...,0],arr[...,1],arr[...,2]
    m=(d>1e-9)
    idx=(mx==rr)&m; h[idx]=((gg-bb)[idx]/d[idx])%6
    idx=(mx==gg)&m; h[idx]=((bb-rr)[idx]/d[idx])+2
    idx=(mx==bb)&m; h[idx]=((rr-gg)[idx]/d[idx])+4
    h=h*60.0
    mask=_np.zeros(mx.shape,bool)
    for hr in TH:
        lo,hi=hr[0],hr[1]
        try: hlo,slo,vlo=hr.hue_min,hr.saturation_min,hr.value_min; hhi,shi,vhi=hr.hue_max,hr.saturation_max,hr.value_max
        except Exception:
            vals=list(hr); hlo,hhi,slo,shi,vlo,vhi=vals[0],vals[1],vals[2],vals[3],vals[4],vals[5]
        hlo2,hhi2=(hlo*2,hhi*2) if hhi<=180 else (hlo,hhi)
        slo2,shi2=(slo/255.0,shi/255.0) if shi>1 else (slo,shi)
        vlo2,vhi2=(vlo/255.0,vhi/255.0) if vhi>1 else (vlo,vhi)
        mask |= (h>=hlo2)&(h<=hhi2)&(s>=slo2)&(s<=shi2)&(v>=vlo2)&(v<=vhi2)
    if mask.sum()==0: return None,0
    xs=_np.nonzero(mask)[1]
    return float(xs.mean()), int(mask.sum())

SPEED={"P3DEV_C01":2.0,"P3DEV_C03":3.0}
runs=[("P3DEV_C01","p3dev_c01_t01_nowall"),("P3DEV_C01","p3dev_c01_t06_nowall"),
      ("P3DEV_C03","p3dev_c03_t01_nowall"),("P3DEV_C03","p3dev_c03_t06_nowall")]
print("run                         dir   best_lag_ticks  resid_px@best  slope_px_per_block")
summary=[]
for cand,rid in runs:
    d=DATA/cand/"capture"/rid
    if not (d/"raw/frames").exists(): print(f"{rid}: frames absent"); continue
    st={int(r["server_tick"]):float(r["sheep_x"]) for r in jl(d/"raw/server_state.jsonl")}
    n=len(st)
    cx=[];ok=[]
    for i in range(n):
        c,_=blob_centroid_x(d/f"raw/frames/{i:06d}.png")
        cx.append(c); ok.append(c is not None)
    cx=np.array([c if c is not None else np.nan for c in cx])
    x=np.array([st[i] for i in range(n)])
    best=None
    for k in range(-6,7):
        # compare frame i centroid against logged state at tick i-k  (k>0 => render lags state)
        idx=np.arange(n)
        j=idx-k
        m=(j>=0)&(j<n)&~np.isnan(cx)
        # exclude clamped ends where x is saturated
        m &= (np.abs(x[np.clip(j,0,n-1)])<7.6)
        if m.sum()<30: continue
        A=np.vstack([x[j[m]],np.ones(m.sum())]).T
        coef,res,_,_=np.linalg.lstsq(A,cx[m],rcond=None)
        pred=A@coef
        rms=float(np.sqrt(np.mean((cx[m]-pred)**2)))
        if best is None or rms<best[1]: best=(k,rms,float(coef[0]),int(m.sum()))
    dirn="LTR" if st[1]>st[0] else "RTL"
    print(f"{rid:28s} {dirn}   {best[0]:+d}              {best[1]:.3f}          {best[2]:.2f}   (n={best[3]})")
    summary.append((cand,rid,dirn,best))
    # print full lag profile
    prof=[]
    for k in range(-6,7):
        idx=np.arange(n); j=idx-k
        m=(j>=0)&(j<n)&~np.isnan(cx)&(np.abs(x[np.clip(j,0,n-1)])<7.6)
        if m.sum()<30: prof.append((k,None)); continue
        A=np.vstack([x[j[m]],np.ones(m.sum())]).T
        coef,_,_,_=np.linalg.lstsq(A,cx[m],rcond=None)
        prof.append((k,float(np.sqrt(np.mean((cx[m]-A@coef)**2)))))
    print("     lag profile (ticks: rms_px): "+"  ".join(f"{k}:{'-' if v is None else format(v,'.2f')}" for k,v in prof))
