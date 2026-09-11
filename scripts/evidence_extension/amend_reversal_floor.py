from common import *
import argparse
import math
import numpy as np
from motion import entry_position
from mineocclude.experiment_iii.cohort import path_sha256
from mineocclude.experiment_iii.target_manifest import build_target_window

def revise(row,boundary=False):
    if row['family']!='reversal' or row['variant']!=0:return dict(row)
    old=row['speed_blocks_per_second'];speed=1.6 if boundary else 1.6+.3*(old-1.4)/.5
    sign=1 if row['direction']=='LEFT_TO_RIGHT' else -1
    v=np.array(row['signed_velocities']);v[20:110]+=sign*(speed-old)
    start=entry_position(row['layout_id'],sign)-float(np.sum(v[:49])*.05)
    assert abs(start)<=7.5
    x=start;path=[]
    for value in v:
        x=min(8.,max(-8.,(x+float(value)*.05)+0.));path.append(x)
    identity=row['identity'].replace('pilot_matched','pilot_boundary') if boundary else row['identity']
    family_id=row['family_id'].replace('pilot_matched','pilot_boundary') if boundary else row['family_id']
    win=build_target_window(identity,row['direction'],path,layout=row['layout'],camera=row['camera'])
    assert list(win.target_model_frame_indices)==list(range(48,67))
    new={k:v for k,v in row.items() if k!='spec_hash'}
    new.update(identity=identity,family_id=family_id,start_world_x=start,speed_blocks_per_second=speed,signed_velocities=v.tolist(),state_positions=path,path_sha256=path_sha256(path),target_model_frame_indices=list(win.target_model_frame_indices),historical_FIR_reference_labels=list(win.labels))
    if boundary:new['engineering_boundary_speed']=True
    new['spec_hash']=seal(new)
    return new

def propose():
    assert not list((ROOT/'motion/predictions').glob('*.json')) and not list((ROOT/'motion/fits').glob('*.npz'))
    old=read(ROOT/'motion_production_v4.json')['rows']
    assert not any((ROOT/'captures'/f'{r["identity"]}__{c}'/'BANKED.json').exists() for r in old if r['partition']=='test' for c in ['L0','L4'])
    reason='The complete-cycle v5 approach passed regular pilots but the minimum-speed training regression retained only two prior frames above 20 pixels. V5 was not admitted to production. Before held-out capture or fitting, bound low-speed reversal sampling uniformly to [1.6,1.9] rather than [1.4,1.9], retaining the same latent uniforms and all other speed distributions. Use first target 48, preserving reversal phase and matched entry but updating targets to the new physical speeds. Keep all acceptance thresholds and sample counts unchanged. Add explicit 1.6-block/s boundary checks in both directions/layouts.'
    rows=[revise(r) for r in old];changed=[a['identity'] for a,b in zip(old,rows) if a['spec_hash']!=b['spec_hash']]
    assert len(changed)==32
    save(ROOT/'REVERSAL_APPROACH_REGRESSION_V5.json',dict(status='FAIL_NOT_ADMITTED',identity='e26_layout_04_train_reversal_07_v0',entry_prior_visible_frames=2,required=3,raw_artifacts_preserved='engineering/reversal-v5',disposition='Retained; not used for production fitting'))
    save(MOTION_ROSTER,dict(rows=rows,status='AMENDED_CAPTURE_PROTOCOL_REQUIRES_ADMISSION',previous_roster_sha256=sha(ROOT/'motion_production_v4.json'),reason=reason,analysis_sha256=sha(Path(__file__).with_name('MOTION_ANALYSIS.md'))))
    oldpilots=read(ROOT/'motion_pilots_v4.json');pilots=[revise(r) for r in oldpilots['rows']];sources=oldpilots['sources'].copy();retests=[]
    for a,b in zip(oldpilots['rows'],pilots):
        if a['spec_hash']!=b['spec_hash']:
            retests.append(b)
            for c in ['L0','L4']:sources[b['identity']+'__'+c]=6
    boundaries=[revise(r,True) for r in oldpilots['rows'] if r['family']=='reversal' and r['variant']==0]
    regression=next(r for r in rows if r['identity']=='e26_layout_04_train_reversal_07_v0')
    assert len(boundaries)==len(retests)==4
    save(ROOT/'motion_pilots_v6.json',dict(rows=pilots,sources=sources,status='ENGINEERING_ONLY'))
    save(ROOT/'motion_pilot_retests_v6.json',dict(rows=retests+boundaries+[regression],status='ENGINEERING_ONLY'))
    save(ROOT/'motion_boundary_checks_v6.json',dict(rows=boundaries+[regression]))
    save(ROOT/'CAPTURE_AMENDMENT_V6.json',dict(reason=reason,changed_identities=changed,previous_freeze_sha256=sha(ROOT/'PRODUCTION_FREEZE_V4.json'),banked_before_amendment=len(list((ROOT/'captures').glob('*/BANKED.json'))),new_roster_sha256=sha(MOTION_ROSTER),all_old_artifacts_preserved=True))
    print('REVERSAL_FLOOR_AMENDMENT_PROPOSED',len(changed),'identities; 18 engineering captures',flush=True)

def regression():
    from motion_features import info
    from audit_pilots import measure
    reports=[]
    for row in read(ROOT/'motion_boundary_checks_v6.json')['rows']:
        histories={}
        for c in ['L0','L4']:
            base=ROOT/'pilots_a6'/f'{row["identity"]}__{c}'
            _,_,_,histories[c]=info(row,c,base)
            if c=='L0':
                measurements=[measure(base/'client/frames'/f'{t:06d}.png') for t in row['target_model_frame_indices']]
                focal=180/math.tan(math.radians(35))
                estimate=.5-(np.array([m['u'] for m in measurements])-320)*(row['layout']['wall_ortho_const']-row['camera'][2])/focal
                error=estimate-row['historical_FIR_reference_labels']
                assert np.std(error)<.15 and abs(np.median(error))<.30
        reports.append(dict(identity=row['identity'],speed=row['speed_blocks_per_second'],visible_prior_counts=histories,alignment_centered_rmse=float(np.std(error)),alignment_offset=float(np.median(error))))
    save(ROOT/'REVERSAL_BOUNDARY_REGRESSION_V6.json',dict(status='PASS',reports=reports,production_roster_sha256=sha(MOTION_ROSTER)))
    print('REVERSAL_BOUNDARY_REGRESSION_PASS',[(r['identity'],r['visible_prior_counts']['L4'][0]) for r in reports],flush=True)

def lock():
    assert read(MOTION_ADMISSION)['status']=='PASS' and read(MOTION_ADMISSION)['production_roster_sha256']==sha(MOTION_ROSTER)
    assert read(ROOT/'REVERSAL_BOUNDARY_REGRESSION_V6.json')['status']=='PASS'
    assert not list((ROOT/'motion/predictions').glob('*.json')) and not list((ROOT/'motion/fits').glob('*.npz'))
    amendment=read(ROOT/'CAPTURE_AMENDMENT_V6.json');archive=ROOT/'preserved_production_v4'
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
    record=dict(status='CAPTURE_AMENDMENT_LOCKED_BEFORE_HELDOUT_CAPTURE_AND_FITTING',previous_freeze_sha256=sha(ROOT/'PRODUCTION_FREEZE_V4.json'),amendment_sha256=sha(ROOT/'CAPTURE_AMENDMENT_V6.json'),roster_sha256=sha(MOTION_ROSTER),admission_sha256=sha(MOTION_ADMISSION),analysis_sha256=sha(Path(__file__).with_name('MOTION_ANALYSIS.md')),preserved_paths=moved,reused_unchanged_training_captures=len(list((ROOT/'captures').glob('*/BANKED.json'))),heldout_outcomes_inspected=False,acceptance_thresholds_unchanged=True,source={p.name:sha(p) for p in Path(__file__).parent.iterdir() if p.suffix in ('.py','.md')})
    save(MOTION_FREEZE,record);save(SOURCE/'evidence_extension_outputs'/MOTION_FREEZE.name,record)
    print('REVERSAL_FLOOR_AMENDMENT_LOCKED',len(moved),'preserved paths',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['propose','regression','lock']);a=p.parse_args()
    {'propose':propose,'regression':regression,'lock':lock}[a.action]()
