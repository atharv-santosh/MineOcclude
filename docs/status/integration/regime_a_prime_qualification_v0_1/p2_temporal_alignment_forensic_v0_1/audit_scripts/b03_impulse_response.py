#!/usr/bin/env python3
"""EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY
Falsify the 'pure delay' model. Deconvolve the causal impulse response h[k]
relating logged server-state x[t] to rendered target position, in the
first-difference domain (immune to constant offset and to any DC scale error):

    dcx[i] ~ a * sum_k h[k] * dx[i-k],   h >= 0, sum h = 1

Reports the kernel, its group delay (sum k*h[k]), and compares fit quality of
FILTER vs PURE-DELAY models. No decoder is involved.
"""
import json,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).parent))
from b02_lag_multimethod import series

def fit_kernel(x,cx,K=8):
    dx=np.diff(x); dcx=np.diff(cx)
    n=len(dx)
    m=~np.isnan(dcx)&(np.abs(x[:-1])<7.5)
    idx=np.nonzero(m)[0]; idx=idx[idx>=K]
    if len(idx)<60: return None
    X=np.stack([dx[idx-k] for k in range(K+1)],axis=1)
    y=dcx[idx]
    # non-negative least squares keeps the kernel physically interpretable
    from scipy.optimize import nnls
    # rendered motion is a negative multiple of world motion (px/block<0) -> flip sign
    sgn=-1.0 if np.sum(X[:,0]*y)<0 else 1.0
    coef,_=nnls(X, sgn*y)
    pred=sgn*(X@coef)
    resid=float(np.sqrt(np.mean((y-pred)**2)))
    tot=float(coef.sum())
    if tot<=0: return None
    h=coef/tot
    gd=float(np.sum(np.arange(K+1)*h))
    # pure-delay comparison at the best integer delay
    best=None
    for k in range(0,K+1):
        Xi=dx[idx-k][:,None]
        c,_,_,_=np.linalg.lstsq(Xi,y,rcond=None)
        r=float(np.sqrt(np.mean((y-Xi@c)**2)))
        if best is None or r<best[1]: best=(k,r)
    return dict(h=h.tolist(),gain=tot,group_delay=gd,filter_rms=resid,
                delay_best_k=best[0],delay_rms=best[1],n=len(idx))

if __name__=="__main__":
    P2=Path(sys.argv[1]); P3=Path(sys.argv[2])
    units=[]
    for t in ("t01","t02","t03","t06","t07","t11","t16","t21"):
        u=P2/f"p2_nowall_regime_a_v2_{t}"
        if (u/"raw/frames").exists(): units.append(("P2",1.5,u))
    for cid,v in (("P3DEV_C01",2.0),("P3DEV_C03",3.0)):
        for t in ("t01","t06"):
            u=P3/cid/"capture"/f"p3dev_{cid[-3:].lower()}_{t}_nowall"
            if (u/"raw/frames").exists(): units.append((cid,v,u))
    res=[]
    print("unit                                v    group_delay  filter_rms  puredelay_k  puredelay_rms  improvement")
    Hs=[]
    for phase,v,u in units:
        x,cx,_=series(u)
        r=fit_kernel(x,cx)
        if r is None: continue
        r.update(phase=phase,v=v,unit=u.name,direction="LTR" if x[1]>x[0] else "RTL")
        res.append(r); Hs.append(r["h"])
        imp=100*(r["delay_rms"]-r["filter_rms"])/r["delay_rms"]
        print(f"{u.name:35s} {v:<4.1f} {r['group_delay']:10.2f} {r['filter_rms']:11.4f} "
              f"{r['delay_best_k']:12d} {r['delay_rms']:14.4f} {imp:9.1f}%")
    H=np.array(Hs)
    print("\n== mean causal impulse response h[k] (normalised, k = server ticks of delay) ==")
    mh=H.mean(0); sh=H.std(0)
    for k in range(H.shape[1]):
        bar="#"*int(round(mh[k]*60))
        print(f"  h[{k}] = {mh[k]:.4f} +/- {sh[k]:.4f}  {bar}")
    import statistics as S
    gds=[r["group_delay"] for r in res]
    sample_sd=S.stdev(gds)
    print(f"\n  GROUP DELAY  mean={S.mean(gds):.3f} ticks  median={S.median(gds):.3f}  sample_sd={sample_sd:.3f}  n={len(gds)}")
    from scipy.stats import t
    standard_error=sample_sd/len(gds)**.5
    half=float(t.ppf(0.975,df=len(gds)-1))*standard_error
    lo=S.mean(gds)-half; hi=S.mean(gds)+half
    rng=np.random.default_rng(20260816)
    draws=np.asarray(gds)[rng.integers(0,len(gds),size=(100000,len(gds)))].mean(axis=1)
    boot_lo,boot_hi=(float(v) for v in np.quantile(draws,[0.025,0.975]))
    print(f"  small-sample Student-t 95% interval: [{lo:.3f}, {hi:.3f}] ticks")
    print(f"  trajectory bootstrap 95% interval: [{boot_lo:.3f}, {boot_hi:.3f}] ticks")
    print(f"  in seconds @20Hz: {S.mean(gds)*0.05:.4f} s   ({lo*0.05:.4f}-{hi*0.05:.4f})")
    fr=[r["filter_rms"] for r in res]; dr=[r["delay_rms"] for r in res]
    print(f"\n  FILTER model rms={S.mean(fr):.4f}  vs  PURE-DELAY rms={S.mean(dr):.4f}"
          f"  -> filter is {100*(S.mean(dr)-S.mean(fr))/S.mean(dr):.1f}% better")
    print(f"  taps with h[k]>0.05: {[k for k in range(len(mh)) if mh[k]>0.05]}"
          f"  => impulse response is SPREAD, not a single spike: PURE-DELAY MODEL FALSIFIED"
          if sum(mh>0.05)>1 else "  single spike -> pure delay")
    print("\n== group delay by speed ==")
    for v in sorted({r["v"] for r in res}):
        g=[r["group_delay"] for r in res if r["v"]==v]
        print(f"  v={v}: mean={S.mean(g):.3f} ticks  = {S.mean(g)*v*0.05:.4f} blocks   n={len(g)}")
    print("== group delay by direction ==")
    for d in sorted({r["direction"] for r in res}):
        g=[r["group_delay"] for r in res if r["direction"]==d]
        print(f"  {d}: mean={S.mean(g):.3f} ticks  n={len(g)}")
    json.dump({"artifact_id":"render-state-impulse-response-v0.1",
               "label":"EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY",
               "mean_kernel":mh.tolist(),"kernel_sd":sh.tolist(),
               "group_delay_mean":S.mean(gds),"group_delay_sample_sd":sample_sd,
               "group_delay_t_interval_95":[lo,hi],
               "group_delay_ci95":[lo,hi],
               "group_delay_trajectory_bootstrap_interval_95":[boot_lo,boot_hi],
               "bootstrap":{"replicates":100000,"seed":20260816,"unit":"trajectory"},
               "units":res},open(sys.argv[3],"w"),indent=2)
