from common import *
from motion import make

def revised(row):
    return make(row['family'],row['layout_id'],row['partition'],row['rank'],row['variant'],True,True,True,True)

def main():
    previous=ROOT/'motion_production_v3.json'
    old=read(previous)['rows'];rows=[revised(r) for r in old]
    changed=[a['identity'] for a,b in zip(old,rows) if a['spec_hash']!=b['spec_hash']]
    assert len(changed)==32
    assert not list((ROOT/'motion/predictions').glob('*.json'))
    assert all(r['partition']=='train' for r in old if (ROOT/'captures'/(r['identity']+'__L0')/'BANKED.json').exists())
    reason='Capture admission found zero visible approach pixels for low-speed training velocity rank 4. Extend the low-speed constant-velocity approach uniformly to first target >=36, preserving speeds, matched entry positions, target-relative trajectories, sample size, analysis, and all acceptance thresholds. No fitted outcomes or held-out captures inspected.'
    save(MOTION_ROSTER,dict(status='AMENDED_CAPTURE_PROTOCOL_REQUIRES_ADMISSION',rows=rows,previous_roster_sha256=sha(previous),reason=reason,analysis_sha256=sha(Path(__file__).with_name('MOTION_ANALYSIS.md'))))
    config=read(ROOT/'motion_pilots_v3.json');pilots=[revised(r) for r in config['rows']];sources=config['sources'].copy();retests=[]
    for a,b in zip(config['rows'],pilots):
        if a['spec_hash']!=b['spec_hash']:
            retests.append(b)
            for c in ['L0','L4']:sources[b['identity']+'__'+c]=4
    assert len(retests)==4
    save(ROOT/'motion_pilots_v4.json',dict(rows=pilots,sources=sources,status='ENGINEERING_ONLY'))
    save(ROOT/'motion_pilot_retests_v4.json',dict(rows=retests))
    save(ROOT/'CAPTURE_AMENDMENT_V4.json',dict(reason=reason,changed_identities=changed,previous_freeze_sha256=sha(ROOT/'PRODUCTION_FREEZE.json'),banked_before_amendment=len(list((ROOT/'captures').glob('*/BANKED.json'))),new_roster_sha256=sha(MOTION_ROSTER),all_old_artifacts_preserved=True))
    print('CAPTURE_AMENDMENT_V4_PREPARED',len(changed),flush=True)

if __name__=='__main__':main()
