from common import *
from motion import make

def main():
    old=read(ROOT/'motion_pilots_matched.json')['rows']
    pilots=[];changed=[];sources={}
    for row in old:
        r=make(row['family'],row['layout_id'],row['partition'],row['rank'],row['variant'],True,True)
        pilots.append(r)
        altered=r['spec_hash']!=row['spec_hash']
        if altered:changed.append(r)
        for c in ['L0','L4']:sources[r['identity']+'__'+c]=2 if altered else 1
    assert len(changed)==4
    save(ROOT/'motion_pilots_v2.json',dict(rows=pilots,sources=sources,status='ENGINEERING_ONLY'))
    save(ROOT/'motion_pilot_retests_v2.json',dict(rows=changed))
    oldprod=read(ROOT/'motion_production.json')['rows']
    production=[make(r['family'],r['layout_id'],r['partition'],r['rank'],r['variant'],True,True) for r in oldprod]
    save(ROOT/'motion_production_v2.json',dict(status='PROSPECTIVE_DRAFT_REQUIRES_ADMISSION',rows=production,previous_roster_sha256=sha(ROOT/'motion_production.json'),reason='Pilot-only revision: high-speed constant-velocity arm reduced to 2.65--2.8 blocks/s; all other schedules unchanged. No production data acquired.',analysis_sha256=sha(Path(__file__).with_name('MOTION_ANALYSIS.md'))))
    save(ROOT/'PILOT_REVISION_V2.json',dict(previous_audit_sha256=sha(ROOT/'pilot_audit_a1_64.json'),failures=['Three residual magenta pixels at first target for two high-speed RTL cases','Absolute alignment offsets 0.303 and 0.322 exceed 0.30'],changed_pilot_variants=4,new_capture_units=8,preserved_pilot_units=56,thresholds_unchanged=True,production_outcomes_inspected=False))
    print('PILOT_REVISION_V2_READY',flush=True)

if __name__=='__main__':main()
