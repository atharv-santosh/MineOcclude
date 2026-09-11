from common import *
from motion import make

def main():
    old=read(ROOT/'motion_pilots_v2.json');pilots=[];changed=[];sources=old['sources'].copy()
    for row in old['rows']:
        r=make(row['family'],row['layout_id'],row['partition'],row['rank'],row['variant'],True,True,True)
        pilots.append(r)
        if r['spec_hash']!=row['spec_hash']:
            changed.append(r)
            for c in ['L0','L4']:sources[r['identity']+'__'+c]=3
    assert len(changed)==4
    save(ROOT/'motion_pilots_v3.json',dict(rows=pilots,sources=sources,status='ENGINEERING_ONLY'))
    save(ROOT/'motion_pilot_retests_v3.json',dict(rows=changed))
    oldprod=read(ROOT/'motion_production_v2.json')['rows']
    rows=[make(r['family'],r['layout_id'],r['partition'],r['rank'],r['variant'],True,True,True) for r in oldprod]
    save(ROOT/'motion_production_v3.json',dict(status='PROSPECTIVE_DRAFT_REQUIRES_ADMISSION',rows=rows,previous_roster_sha256=sha(ROOT/'motion_production_v2.json'),reason='Pilot-only revision: low-speed stop/resume approach extended by at least one full 12-tick cycle, first target >=42; unchanged speed parameters and all admission thresholds. High-speed arm already has visible history and retains its feasible arena approach.',analysis_sha256=sha(Path(__file__).with_name('MOTION_ANALYSIS.md'))))
    save(ROOT/'PILOT_REVISION_V3.json',dict(previous_history_audit_sha256=sha(ROOT/'PILOT_HISTORY_AUDIT_V2.json'),failed_case='layout_01 low-speed left-to-right stop/resume had zero visible frames in the first input window',new_capture_units=8,thresholds_unchanged=True,production_outcomes_inspected=False))
    print('PILOT_REVISION_V3_READY',flush=True)

if __name__=='__main__':main()
