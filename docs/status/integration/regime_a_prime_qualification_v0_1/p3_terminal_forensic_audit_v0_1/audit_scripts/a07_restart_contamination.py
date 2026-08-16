#!/usr/bin/env python3
"""EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY - independent pre/post runtime-restart stratification."""
import json,sys,statistics as S
from pathlib import Path
import numpy as np
LED=Path("/home/sagemaker-user/MineOcclude/docs/status/integration/regime_a_prime_qualification_v0_1")
DATA=Path(sys.argv[1])
def jl(p): return [json.loads(l) for l in p.read_text().splitlines() if l]

ev=jl(LED/"p3_events.jsonl")
print("== controller restarts / hard failures in event ledger ==")
for e in ev:
    if e.get("event") in ("controller_started","controller_resumed","hard_failure","runtime_provenance_verified","controller_terminated") or e.get("status","").startswith("FAIL"):
        print(" ",e.get("timestamp"),e.get("candidate"),e.get("stage"),e.get("event"),e.get("status"),
              {k:v for k,v in e.items() if k not in ("timestamp","candidate","stage","event","status")} or "")
print()
cal=jl(LED/"p3_p3dev_c01_calibration_ledger.jsonl")
cap=jl(LED/"p3_p3dev_c01_capture_ledger.jsonl")
cap=[r for r in cap if r.get("status")=="COMPLETE_VALIDATED_DURABLE"]
cap.sort(key=lambda r:r["timestamp"])
print(f"C01 capture units in ledger order: {len(cap)}; first={cap[0]['timestamp']} last={cap[-1]['timestamp']}")
gaps=[]
for a,b in zip(cap,cap[1:]):
    import datetime as dt
    ta=dt.datetime.fromisoformat(a["timestamp"].replace("Z","+00:00"))
    tb=dt.datetime.fromisoformat(b["timestamp"].replace("Z","+00:00"))
    gaps.append(((tb-ta).total_seconds(),a["identity"],b["identity"]))
gaps.sort(reverse=True)
print("largest inter-unit gaps (s):")
for g in gaps[:4]: print("   ",round(g[0],1),g[1],"->",g[2])

# stratify: units completed before vs after the largest gap
cut=max(range(len(cap)-1),key=lambda i:gaps and 0)  # recompute properly
import datetime as dt
ts=[dt.datetime.fromisoformat(r["timestamp"].replace("Z","+00:00")) for r in cap]
deltas=[(ts[i+1]-ts[i]).total_seconds() for i in range(len(ts)-1)]
k=int(np.argmax(deltas))
pre=[r["identity"] for r in cap[:k+1]]; post=[r["identity"] for r in cap[k+1:]]
print(f"\nSTRATA: pre-restart n={len(pre)} (last={pre[-1]}), post-restart n={len(post)} (first={post[0]}), gap={deltas[k]:.0f}s")

def stats(ids):
    fc=[];px=[];fp=0;tot=0;areas=[];nfr=set()
    for rid in ids:
        d=DATA/"P3DEV_C01/capture"/rid
        st=jl(d/"raw/server_state.jsonl"); vis=jl(d/"raw/visibility.jsonl")
        nfr.add(len(st))
        for r in vis:
            tot+=1
            if r["magenta_area_pixels"] is not None: areas.append(r["magenta_area_pixels"])
    return dict(n=len(ids),frames=sorted(nfr),rows=tot,
                area_mean=round(S.mean(areas),2),area_med=S.median(areas),
                detected_rows=len(areas))
print(" pre :",stats(pre))
print(" post:",stats(post))

# renderer fingerprint from capture_package receipts
def pkg(ids):
    keys={}
    for rid in ids:
        for p in (DATA/"P3DEV_C01/capture"/rid).rglob("capture_package_v0_1.json"):
            d=json.load(open(p))
            for k in ("renderer","gl_renderer","gl_version","frame_width","frame_height",
                      "renderer_identity","mod_sha256","java_version","frames"):
                if k in d: keys.setdefault(k,set()).add(str(d[k]))
            for sub in ("runtime","provenance","renderer_provenance","environment"):
                if isinstance(d.get(sub),dict):
                    for k,v in d[sub].items():
                        if not isinstance(v,(dict,list)): keys.setdefault(f"{sub}.{k}",set()).add(str(v))
    return keys
kp,ko=pkg(pre),pkg(post)
print("\n renderer/provenance fields differing between strata:")
allk=set(kp)|set(ko); diff=0
for k in sorted(allk):
    a=kp.get(k,set()); b=ko.get(k,set())
    if a!=b:
        print(f"   {k}: pre={sorted(a)[:3]} post={sorted(b)[:3]}"); diff+=1
if not diff: print("   NONE — all recorded renderer/provenance fields identical across the restart")
print("\n sample provenance keys:",sorted(allk)[:25])
