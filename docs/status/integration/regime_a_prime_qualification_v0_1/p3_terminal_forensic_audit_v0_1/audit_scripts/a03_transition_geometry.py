#!/usr/bin/env python3
"""EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY
Extract geometric and rendered occlusion transition x-positions per calibration run.
Discriminates: (a) symmetric silhouette-extent mismatch vs (b) direction-dependent
render/state temporal lag.
Source: durable S3 raw/visibility.jsonl + raw/server_state.jsonl
"""
import json, sys
from pathlib import Path
ROOT = Path(sys.argv[1])
def jl(p): return [json.loads(l) for l in p.read_text().splitlines() if l]

SPEED = {"P3DEV_C01":2.0,"P3DEV_C02":2.5,"P3DEV_C03":3.0}
rows=[]
for cand in ("P3DEV_C01","P3DEV_C02","P3DEV_C03"):
    v_tick = SPEED[cand]*0.05
    for d in sorted((ROOT/cand/"calibration").iterdir()):
        vis = jl(d/"raw/visibility.jsonl")
        st  = {r["server_tick"]: float(r["sheep_x"]) for r in jl(d/"raw/server_state.jsonl")}
        direction = "LTR" if "ltr" in d.name else "RTL"
        geo=[(r["server_tick"], r["geometric_status"]=="visible") for r in vis]
        mag=[(r["server_tick"], r["magenta_status"]=="detected") for r in vis]
        def first_transition(seq, frm, to, after=0):
            for i in range(1,len(seq)):
                if seq[i][0] < after: continue
                if seq[i-1][1]==frm and seq[i][1]==to:
                    return seq[i][0]
            return None
        g_off = first_transition(geo, True, False)          # geometric enters occlusion
        g_on  = first_transition(geo, False, True, after=(g_off or 0)+5)
        m_off = first_transition(mag, True, False, after=(g_off or 0))   # magenta lost (entry)
        m_on  = first_transition(mag, False, True, after=(m_off or 0)+3) # magenta regained (exit)
        rows.append(dict(cand=cand, v=SPEED[cand], vt=v_tick, run=d.name, dir=direction,
                         g_off_t=g_off, g_off_x=st.get(g_off), g_on_t=g_on, g_on_x=st.get(g_on),
                         m_off_t=m_off, m_off_x=st.get(m_off), m_on_t=m_on, m_on_x=st.get(m_on)))

print(f"{'cand':10s} {'dir':4s} {'run':28s} {'geoOFF_x':>9s} {'magOFF_x':>9s} {'geoON_x':>9s} {'magON_x':>9s}")
for r in rows:
    fmt=lambda z: f"{z:9.4f}" if z is not None else "     None"
    print(f"{r['cand']:10s} {r['dir']:4s} {r['run']:28s} {fmt(r['g_off_x'])} {fmt(r['m_off_x'])} {fmt(r['g_on_x'])} {fmt(r['m_on_x'])}")

print("\n== Aggregated per candidate/direction (mean x) ==")
import statistics as S
agg={}
for r in rows:
    k=(r["cand"],r["dir"]); agg.setdefault(k,[]).append(r)
for k in sorted(agg):
    g=agg[k]
    m=lambda f:S.mean([x[f] for x in g if x[f] is not None])
    agg[k]=dict(g_off=m("g_off_x"), g_on=m("g_on_x"), m_off=m("m_off_x"), m_on=m("m_on_x"))
    print(f"{k}: geo_shadow=[{agg[k]['g_off']:.3f},{agg[k]['g_on']:.3f}]  render_shadow=[{agg[k]['m_off']:.3f},{agg[k]['m_on']:.3f}]")

print("\n== Model discrimination ==")
print("Symmetric-silhouette model predicts LTR and RTL give the SAME shadow interval.")
print("Render-lag model predicts the render interval shifts by +delta (LTR) / -delta (RTL).\n")
for cand in ("P3DEV_C01","P3DEV_C02","P3DEV_C03"):
    L=agg[(cand,"LTR")]; R=agg[(cand,"RTL")]
    vt=SPEED[cand]*0.05
    # geometric consistency check (should be direction-independent)
    gshift = ((L["g_off"]-R["g_on"]) + (L["g_on"]-R["g_off"]))/2
    # LTR render entry edge (Smin side) vs RTL render exit edge (Smin side)
    d_low  = (L["m_off"] - R["m_on"])/2
    d_high = (L["m_on"]  - R["m_off"])/2
    delta  = (d_low+d_high)/2
    L_halfwidth = (L["m_on"]-L["m_off"])/2
    R_halfwidth = (R["m_off"]-R["m_on"])/2
    geo_hw = ((L["g_on"]-L["g_off"])+(R["g_off"]-R["g_on"]))/4
    print(f"{cand} v={SPEED[cand]} b/s ({vt:.3f} b/tick):")
    print(f"   geometric direction-shift (should be ~0): {gshift:+.4f} blocks")
    print(f"   render direction-shift delta            : {delta:+.4f} blocks  (low {d_low:+.4f}, high {d_high:+.4f})")
    print(f"   => implied lag in server ticks           : {delta/vt:.2f}")
    print(f"   geometric shadow half-width={geo_hw:.3f}  render half-width LTR={L_halfwidth:.3f} RTL={R_halfwidth:.3f}")
    print(f"   => implied silhouette half-extent w      : {geo_hw-(L_halfwidth+R_halfwidth)/2:.3f} blocks")
