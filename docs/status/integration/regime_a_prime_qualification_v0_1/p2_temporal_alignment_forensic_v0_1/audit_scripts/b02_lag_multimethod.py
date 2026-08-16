#!/usr/bin/env python3
"""EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY
Independent reproduction of render-vs-server-state temporal lag using THREE
conceptually independent physical methods. No decoder, no neural performance,
is used anywhere in this estimation.

METHOD A  centroid-vs-state regression over integer lag (level-domain)
METHOD B  first-difference (velocity/innovation) cross-correlation  -- immune to
          any constant spatial offset and to the px/block scale
METHOD C  kinematic saturation-event timing: the lane clamp at |x|=8 stops the
          motion; compare the tick at which LOGGED x saturates with the frame at
          which the RENDERED centroid saturates. Uses no homography, no wall
          geometry, no scale calibration -- purely "when does motion stop".

Sources: durable S3 raw/{server_state.jsonl,frames/*.png} for P2 (v=1.5) and
P3 C01/C02/C03 (v=2.0/2.5/3.0).
"""
import json,sys,math
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage

CFG=json.load(open("/home/sagemaker-user/MineOcclude/docs/status/person_e_phase3_step3_1_candidate_freeze_v0_1/detector_candidate_config.json"))["configuration"]["detector_settings"]
HMIN,HMAX,SMIN,SMAX,VMIN,VMAX=CFG["hsv_ranges"][0]
MINA,MAXA=CFG["min_area_pixels"],CFG["max_area_pixels"]
def jl(p): return [json.loads(l) for l in p.read_text().splitlines() if l]

def blob_cx(png):
    a=np.asarray(Image.open(png).convert("RGB"),dtype=np.float32)/255.0
    mx=a.max(2); mn=a.min(2); d=mx-mn; v=mx
    s=np.where(mx>0,d/np.maximum(mx,1e-12),0.0)
    r,g,b=a[...,0],a[...,1],a[...,2]
    h=np.zeros_like(mx); m=d>0
    i=(mx==r)&m; h[i]=((g-b)[i]/d[i])%6
    i=(mx==g)&m; h[i]=((b-r)[i]/d[i])+2
    i=(mx==b)&m; h[i]=((r-g)[i]/d[i])+4
    h=(h*60.0)%360.0
    mask=(h>=HMIN)&(h<=HMAX)&(s>=SMIN)&(s<=SMAX)&(v>=VMIN)&(v<=VMAX)
    if not mask.any(): return None
    lab,n=ndimage.label(mask,structure=np.ones((3,3),bool))
    sizes=ndimage.sum(mask,lab,range(1,n+1))
    valid=[(sz,k+1) for k,sz in enumerate(sizes) if MINA<=sz<=MAXA]
    if not valid: return None
    _,k=max(valid)
    return float(np.nonzero(lab==k)[1].mean())

def series(unit):
    st=jl(unit/"raw/server_state.jsonl")
    x=np.array([float(r["sheep_x"]) for r in st])
    n=len(x)
    cx=np.full(n,np.nan)
    for i in range(n):
        p=unit/f"raw/frames/{i:06d}.png"
        if p.exists():
            c=blob_cx(p)
            if c is not None: cx[i]=c
    return x,cx,st

def method_A(x,cx,lags):
    out={}
    for k in lags:
        j=np.arange(len(x))-k
        m=(j>=0)&(j<len(x))&~np.isnan(cx)&(np.abs(x[np.clip(j,0,len(x)-1)])<7.5)
        if m.sum()<40: continue
        A=np.vstack([x[j[m]],np.ones(m.sum())]).T
        coef,_,_,_=np.linalg.lstsq(A,cx[m],rcond=None)
        out[k]=(float(np.sqrt(np.mean((cx[m]-A@coef)**2))),float(coef[0]),int(m.sum()))
    return out

def method_B(x,cx,lags):
    """First differences: dcx[i] ~ a * dx[i-k]. Constant offsets cancel."""
    dx=np.diff(x); dcx=np.diff(cx)
    out={}
    for k in lags:
        j=np.arange(len(dx))-k
        m=(j>=0)&(j<len(dx))&~np.isnan(dcx)
        m&= np.abs(x[np.clip(j,0,len(x)-2)])<7.5
        if m.sum()<40: continue
        A=dx[j[m]][:,None]
        coef,_,_,_=np.linalg.lstsq(A,dcx[m],rcond=None)   # no intercept
        out[k]=(float(np.sqrt(np.mean((dcx[m]-A@coef)**2))),float(coef[0]),int(m.sum()))
    return out

def saturation_index(sig, target, tol, from_end=True):
    """First index at which |sig-target| stays within tol for the rest of the run."""
    n=len(sig); ok=np.abs(sig-target)<=tol
    idx=None
    run=0
    for i in range(n-1,-1,-1):
        if np.isnan(sig[i]): break
        if ok[i]: run+=1; idx=i
        else: break
    return idx if (idx is not None and run>=8) else None

def method_C(x,cx):
    """Kinematic saturation: logged x clamps at +-8; rendered centroid clamps too."""
    lim=8.0 if x[-1]>0 else -8.0
    # logged: first tick from which x stays within 0.25 of clamp (noise jitters it)
    xs=saturation_index(x,lim,0.25)
    if xs is None: return None
    # rendered: centroid value at clamp = median of last 20 valid centroids
    valid=cx[~np.isnan(cx)]
    if len(valid)<30: return None
    csat=float(np.median(valid[-20:]))
    # scale px per block from a robust fit over the moving region
    m=~np.isnan(cx)&(np.abs(x)<7.0)
    if m.sum()<40: return None
    A=np.vstack([x[m],np.ones(m.sum())]).T
    coef,_,_,_=np.linalg.lstsq(A,cx[m],rcond=None)
    pxb=coef[0]
    tol=abs(pxb)*0.25
    cs=saturation_index(cx,csat,tol)
    if cs is None: return None
    return cs-xs, xs, cs, float(pxb)

def parabolic_min(prof):
    ks=sorted(prof); rs=[prof[k][0] for k in ks]
    bi=int(np.argmin(rs))
    if 0<bi<len(ks)-1:
        y0,y1,y2=rs[bi-1],rs[bi],rs[bi+1]; den=(y0-2*y1+y2)
        if den>0: return ks[bi]+0.5*(y0-y2)/den, ks[bi], rs[bi]
    return float(ks[bi]), ks[bi], rs[bi]

if __name__=="__main__":
    P2=Path(sys.argv[1]); P3=Path(sys.argv[2])
    LAGS=list(range(-6,9))
    rows=[]
    units=[]
    for t in ("t01","t02","t03","t06","t07","t11","t16","t21"):
        u=P2/f"p2_nowall_regime_a_v2_{t}"
        if (u/"raw/frames").exists(): units.append(("P2",1.5,"NO_WALL",u))
    for cid,v in (("P3DEV_C01",2.0),("P3DEV_C03",3.0)):
        for t in ("t01","t06"):
            u=P3/cid/"capture"/f"p3dev_{cid[-3:].lower()}_{t}_nowall"
            if (u/"raw/frames").exists(): units.append((cid,v,"NO_WALL",u))
    print(f"{'phase':10s} {'unit':34s} {'dir':4s} {'v':5s} {'A_lag':>7s} {'B_lag':>7s} {'C_lag':>6s} {'A_rms':>7s} {'B_rms':>8s} {'pxblk':>7s}")
    for phase,v,scene,u in units:
        x,cx,st=series(u)
        if np.isnan(cx).all(): print(f"{phase} {u.name}: no frames"); continue
        direction="LTR" if x[1]>x[0] else "RTL"
        A=method_A(x,cx,LAGS); B=method_B(x,cx,LAGS)
        a_sub,a_int,a_rms=parabolic_min(A); b_sub,b_int,b_rms=parabolic_min(B)
        C=method_C(x,cx)
        c_lag = C[0] if C else None
        pxb = A[a_int][1]
        rows.append(dict(phase=phase,unit=u.name,dir=direction,v=v,scene=scene,
                         A_sub=a_sub,A_int=a_int,A_rms=a_rms,
                         B_sub=b_sub,B_int=b_int,B_rms=b_rms,
                         C_lag=c_lag,px_per_block=pxb,n=len(x)))
        print(f"{phase:10s} {u.name:34s} {direction:4s} {v:<5.1f} {a_sub:+7.2f} {b_sub:+7.2f} "
              f"{'' if c_lag is None else format(c_lag,'+6d')} {a_rms:7.3f} {b_rms:8.4f} {pxb:7.2f}")
    json.dump({"artifact_id":"p2-p3-temporal-lag-multimethod-v0.1",
               "label":"EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY","rows":rows},
              open(sys.argv[3],"w"),indent=2)
    import statistics as S
    print("\n== aggregate ==")
    for meth,key in (("A (level regression)","A_sub"),("B (first-difference xcorr)","B_sub"),("C (saturation event)","C_lag")):
        vals=[r[key] for r in rows if r[key] is not None]
        if vals:
            print(f"  {meth:30s} n={len(vals):2d} mean={S.mean(vals):+.2f} median={S.median(vals):+.2f} "
                  f"sd={S.pstdev(vals):.2f} min={min(vals):+.2f} max={max(vals):+.2f}")
    print("\n== by speed (method A / B) ==")
    for v in sorted({r["v"] for r in rows}):
        g=[r for r in rows if r["v"]==v]
        print(f"  v={v}: A={S.mean([r['A_sub'] for r in g]):+.2f}  B={S.mean([r['B_sub'] for r in g]):+.2f}  "
              f"n={len(g)}  (lag in BLOCKS: A={S.mean([r['A_sub'] for r in g])*v*0.05:+.3f})")
    print("\n== by direction (method A / B) ==")
    for d in sorted({r["dir"] for r in rows}):
        g=[r for r in rows if r["dir"]==d]
        print(f"  {d}: A={S.mean([r['A_sub'] for r in g]):+.2f}  B={S.mean([r['B_sub'] for r in g]):+.2f}  n={len(g)}")
