#!/usr/bin/env python3
"""EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY - spatial profile of geometric vs rendered visibility."""
import json, sys
from pathlib import Path
ROOT = Path(sys.argv[1])
def jl(p): return [json.loads(l) for l in p.read_text().splitlines() if l]

def profile(cand, run):
    d = ROOT/cand/"calibration"/run
    vis = jl(d/"raw/visibility.jsonl")
    st  = {r["server_tick"]: r for r in jl(d/"raw/server_state.jsonl")}
    print(f"\n--- {cand}/{run} ---")
    print("tick    x        geo   mag   area")
    prev=None
    for r in vis:
        s=st[r["server_tick"]]
        g=r["geometric_status"]; m=r["magenta_status"]
        cur=(g,m)
        if cur!=prev:
            print(f"{r['server_tick']:4d} {float(s['sheep_x']):8.4f}  {g:8s} {m:13s} {r['magenta_area_pixels']}")
            prev=cur
    # transition edges in x
    print("  x at first/last frames:", round(float(st[0]['sheep_x']),3), round(float(st[len(vis)-1]['sheep_x']),3))

for cand in ("P3DEV_C01","P3DEV_C02","P3DEV_C03"):
    for run in sorted(p.name for p in (ROOT/cand/"calibration").iterdir()):
        profile(cand, run)
