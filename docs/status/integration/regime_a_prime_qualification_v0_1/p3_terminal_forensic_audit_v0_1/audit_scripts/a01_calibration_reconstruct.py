#!/usr/bin/env python3
"""EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY
Independently reconstruct the P3 visibility calibration gate from durable S3-restored raw data.
Source: <scratch>/p3data/<CAND>/calibration/<id>/{raw/visibility.jsonl,raw/server_state.jsonl}
"""
import json, sys
from pathlib import Path

ROOT = Path(sys.argv[1])
def jl(p): return [json.loads(l) for l in p.read_text().splitlines() if l]

for cand in ("P3DEV_C01","P3DEV_C02","P3DEV_C03"):
    tp=fp=tn=fn=amb=rows=0
    per=[]
    for d in sorted((ROOT/cand/"calibration").iterdir()):
        vis = jl(d/"raw/visibility.jsonl")
        st  = {r["server_tick"]: r for r in jl(d/"raw/server_state.jsonl")}
        ctp=cfp=ctn=cfn=0
        fps=[]
        fns=[]
        for r in vis:
            truth = r["geometric_status"]=="visible"
            pred  = r["magenta_status"]=="detected"
            s = st[r["server_tick"]]
            if truth and pred: tp+=1; ctp+=1
            elif (not truth) and pred:
                fp+=1; cfp+=1
                fps.append((r["server_tick"], round(float(s["sheep_x"]),4), r["magenta_area_pixels"]))
            elif (not truth) and (not pred): tn+=1; ctn+=1
            else:
                fn+=1; cfn+=1
                fns.append((r["server_tick"], round(float(s["sheep_x"]),4), r["magenta_area_pixels"]))
            amb += r["magenta_status"] not in ("detected","not_detected")
            rows+=1
        per.append((d.name, ctp,cfp,ctn,cfn, fps, fns))
    prec = tp/(tp+fp) if tp+fp else 0.0
    rec  = tp/(tp+fn) if tp+fn else 0.0
    spec_ = tn/(tn+fp) if tn+fp else 0.0
    print(f"\n===== {cand} =====")
    print(f"rows={rows} tp={tp} fp={fp} tn={tn} fn={fn} amb={amb}")
    print(f"precision={prec:.6f}  recall={rec:.6f}  specificity={spec_:.6f}  fp_rate={1-spec_:.6f}")
    print(f"visible_base_rate={(tp+fn)/rows:.4f}")
    for name,ctp,cfp,ctn,cfn,fps,fns in per:
        print(f"  {name}: tp={ctp} fp={cfp} tn={ctn} fn={cfn}")
        if fps:
            xs=[f[1] for f in fps]; ar=[f[2] for f in fps]
            print(f"     FP ticks={[f[0] for f in fps]}")
            print(f"     FP x-range=[{min(xs):.3f},{max(xs):.3f}] area px min={min(ar)} max={max(ar)} median={sorted(ar)[len(ar)//2]}")
        if fns:
            xs=[f[1] for f in fns]; ar=[f[2] for f in fns]
            print(f"     FN ticks={[f[0] for f in fns]} x-range=[{min(xs):.3f},{max(xs):.3f}] area px={ar}")
