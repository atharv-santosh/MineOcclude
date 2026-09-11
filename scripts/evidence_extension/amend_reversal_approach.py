from common import *
import argparse
import numpy as np
from motion import entry_position
from mineocclude.experiment_iii.cohort import path_sha256
from mineocclude.experiment_iii.target_manifest import build_target_window

def extend(row):
    if row['family']!='reversal' or row['variant']!=0:return dict(row)
    assert row['target_model_frame_indices'][0]==36
    first=48;sign=1 if row['direction']=='LEFT_TO_RIGHT' else -1
    v=row['signed_velocities'];start=entry_position(row['layout_id'],sign)-float(np.sum(v[:first+1])*.05)
    assert abs(start)<=7.5
    x=start;path=[]
    for value in v:
        x=min(8.,max(-8.,(x+float(value)*.05)+0.));path.append(x)
    win=build_target_window(row['identity'],row['direction'],path,layout=row['layout'],camera=row['camera'])
    indices=list(win.target_model_frame_indices)
    assert indices==[t+12 for t in row['target_model_frame_indices']]
    assert np.max(abs(np.array(win.labels)-row['historical_FIR_reference_labels']))<1e-10
    new={k:v for k,v in row.items() if k!='spec_hash'}
    new.update(start_world_x=start,state_positions=path,path_sha256=path_sha256(path),target_model_frame_indices=indices,historical_FIR_reference_labels=list(win.labels))
    new['spec_hash']=seal(new)
    return new

def propose():
    assert not list((ROOT/'motion/predictions').glob('*.json'))
    assert not list((ROOT/'motion/fits').glob('*.npz'))
    old=read(ROOT/'motion_production_v4.json')['rows']
    assert not any((ROOT/'captures'/f'{r["identity"]}__{c}'/'BANKED.json').exists() for r in old if r['partition']=='test' for c in ['L0','L4'])
    rows=[extend(r) for r in old]
    changed=[a['identity'] for a,b in zip(old,rows) if a['spec_hash']!=b['spec_hash']]
    assert len(changed)==32
    reason='A low-speed training reversal at 1.400625 blocks/s had only one prior image above the fixed sheep-pixel threshold. Uniformly add one complete 12-tick approach cycle to every low-speed reversal, moving first target from 36 to 48 while retaining speed, phase, entry position, target-relative paths, sample size, and all thresholds. No held-out captures or fitted outcomes existed.'
    save(MOTION_ROSTER,dict(rows=rows,status='AMENDED_CAPTURE_PROTOCOL_REQUIRES_ADMISSION',previous_roster_sha256=sha(ROOT/'motion_production_v4.json'),reason=reason,analysis_sha256=sha(Path(__file__).with_name('MOTION_ANALYSIS.md'))))
    pilots=read(ROOT/'motion_pilots_v4.json');newpilots=[extend(r) for r in pilots['rows']];sources=pilots['sources'].copy();retests=[]
    for a,b in zip(pilots['rows'],newpilots):
        if a['spec_hash']!=b['spec_hash']:
            retests.append(b)
            for c in ['L0','L4']:sources[b['identity']+'__'+c]=5
    assert len(retests)==4
    save(ROOT/'motion_pilots_v5.json',dict(rows=newpilots,sources=sources,status='ENGINEERING_ONLY'))
    save(ROOT/'motion_pilot_retests_v5.json',dict(rows=retests))
    save(ROOT/'CAPTURE_AMENDMENT_V5.json',dict(reason=reason,changed_identities=changed,previous_freeze_sha256=sha(ROOT/'PRODUCTION_FREEZE_V4.json'),banked_before_amendment=len(list((ROOT/'captures').glob('*/BANKED.json'))),new_roster_sha256=sha(MOTION_ROSTER),target_max_difference=max(float(np.max(abs(np.array(a['historical_FIR_reference_labels'])-b['historical_FIR_reference_labels']))) for a,b in zip(old,rows)),all_old_artifacts_preserved=True))
    print('REVERSAL_APPROACH_AMENDMENT_PROPOSED',len(changed),flush=True)

def regression():
    from motion_features import info
    row=next(r for r in read(MOTION_ROSTER)['rows'] if r['identity']=='e26_layout_04_train_reversal_07_v0')
    counts={}
    for c in ['L0','L4']:
        _,_,_,counts[c]=info(row,c,ROOT/'engineering/reversal-v5'/f'{row["identity"]}__{c}')
    save(ROOT/'REVERSAL_APPROACH_REGRESSION.json',dict(status='PASS',identity=row['identity'],visible_prior_counts=counts,production_roster_sha256=sha(MOTION_ROSTER)))
    print('REVERSAL_APPROACH_REGRESSION_PASS',counts,flush=True)

def lock():
    assert read(MOTION_ADMISSION)['status']=='PASS'
    assert read(MOTION_ADMISSION)['production_roster_sha256']==sha(MOTION_ROSTER)
    assert read(ROOT/'REVERSAL_APPROACH_REGRESSION.json')['status']=='PASS'
    assert not list((ROOT/'motion/predictions').glob('*.json'))
    assert not list((ROOT/'motion/fits').glob('*.npz'))
    amendment=read(ROOT/'CAPTURE_AMENDMENT_V5.json');archive=ROOT/'preserved_production_v4'
    assert not archive.exists();archive.mkdir();moved=[]
    def preserve(path):
        if not path.exists():return
        assert path.resolve().is_relative_to(ROOT.resolve())
        target=archive/path.relative_to(ROOT)
        assert target.resolve().is_relative_to(archive.resolve()) and not target.exists()
        target.parent.mkdir(parents=True,exist_ok=True);path.rename(target);moved.append(str(target.relative_to(ROOT)))
    for identity in amendment['changed_identities']:
        for c in ['L0','L4']:
            unit=identity+'__'+c;preserve(ROOT/'captures'/unit)
            for p in list((ROOT/'motion/features').glob('*/'+unit+'.npy')):preserve(p)
            for p in list((ROOT/'motion/receipts').glob('*__'+unit+'.json')):preserve(p)
    rows={r['identity']:r for r in read(MOTION_ROSTER)['rows']}
    for p in (ROOT/'captures').glob('*/BANKED.json'):assert read(p)['spec_hash']==rows[p.parent.name.rsplit('__',1)[0]]['spec_hash']
    record=dict(status='CAPTURE_AMENDMENT_LOCKED_BEFORE_HELDOUT_CAPTURE_AND_FITTING',previous_freeze_sha256=sha(ROOT/'PRODUCTION_FREEZE_V4.json'),amendment_sha256=sha(ROOT/'CAPTURE_AMENDMENT_V5.json'),roster_sha256=sha(MOTION_ROSTER),admission_sha256=sha(MOTION_ADMISSION),analysis_sha256=sha(Path(__file__).with_name('MOTION_ANALYSIS.md')),preserved_paths=moved,reused_unchanged_training_captures=len(list((ROOT/'captures').glob('*/BANKED.json'))),heldout_outcomes_inspected=False,acceptance_thresholds_unchanged=True,source={p.name:sha(p) for p in Path(__file__).parent.iterdir() if p.suffix in ('.py','.md')})
    save(MOTION_FREEZE,record);save(SOURCE/'evidence_extension_outputs'/MOTION_FREEZE.name,record)
    print('REVERSAL_APPROACH_AMENDMENT_LOCKED',len(moved),'preserved paths',flush=True)

p=argparse.ArgumentParser();p.add_argument('action',choices=['propose','regression','lock']);a=p.parse_args()
{'propose':propose,'regression':regression,'lock':lock}[a.action]()
