"""Verify fresh raw captures and export a complete target/fold manifest."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
from PIL import Image
from audit_pilots import ROOT,SOURCE,read,lines,measure
from pilot import save
from plan_cohort import layout_config
from mineocclude.experiment_iii.cohort import generate_path
from mineocclude.experiment_iii.fir import fir_labels
from mineocclude.experiment_iii.target_manifest import build_target_window
from mineocclude.experiment_iii.extent_geometry import counterfactual_extent_classes


def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def verify(directory,row):
    bank=read(directory/'BANKED.json')
    assert bank['spec_hash']==row['spec_hash']
    for filename,h in bank['files'].items():
        assert sha(directory/filename)==h,filename
    spec=read(directory/'spec.json')
    state=lines(directory/'server/server_state.jsonl')
    ticks=lines(directory/'client/client_tick.jsonl')
    actions=lines(directory/'client/raw_actions.jsonl')
    completion=read(directory/'client/capture_complete.json')
    authority=read(directory/'client/client_authority.json')
    physical=read(directory/'server/physical_receipt.json')
    frames=sorted((directory/'client/frames').glob('*.png'))
    assert len(frames)==len(state)==len(ticks)==len(actions)==180
    assert completion['drained'] and completion['writer_errors']==0
    assert authority['fov_degrees']==70 and authority['hud_hidden']
    assert physical['wall']['mismatch_count']==0
    assert physical['target']['valid'] and physical['target']['tagged_target_count']==1
    assert physical['condition_id']==spec['condition_id']
    assert physical['declared_block_id']==spec['wall_block_id']
    assert physical['layout_id']==row['layout_id']
    expected,_=generate_path(row['seed'],.05,direction=row['direction'],start_world_x=row['start_world_x'],speed=row['speed_blocks_per_second'])
    observed=np.array([r['sheep_x'] for r in state])
    assert np.max(abs(expected-observed))<1e-9
    camera=physical['camera']['observed']
    eye=[camera['feet_x'],camera['eye_y'],camera['feet_z']]
    assert np.max(abs(np.array(eye)-row['camera']))<1e-6
    assert all(r['player_yaw']==0 and r['player_pitch']==0 for r in state)
    assert len({r['target_entity_uuid'] for r in state})==1
    assert all(r['target_respawn_count']==0 for r in state)
    assert [r['server_tick'] for r in state]==list(range(180))
    assert [r['server_tick'] for r in ticks]==list(range(180))
    assert [r['render_frame_idx'] for r in ticks]==list(range(180))
    assert all(r['tick_queue_depth_at_capture']==0 for r in ticks)
    assert [r['render_frame_idx'] for r in actions]==list(range(180))
    assert [r['action_idx'] for r in actions]==list(range(180))
    payloads={json.dumps({k:v for k,v in a.items() if k not in ('episode_id','server_tick','render_frame_idx','action_idx')},sort_keys=True) for a in actions}
    assert len(payloads)==1, 'Nonconstant actions require explicit history-baseline handling'
    for frame in frames:
        with Image.open(frame) as im:
            assert im.size==(640,360)
    win=build_target_window(row['identity'],row['direction'],observed,layout=row['layout'],camera=eye)
    assert list(win.target_model_frame_indices)==row['target_model_frame_indices']
    assert np.array_equal(np.array(win.labels),row['historical_FIR_reference_labels'])
    # Pixel evidence validates geometry; it never selects alternative rows.
    areas=[measure(frames[t])['area'] for t in win.target_model_frame_indices]
    if spec['condition_id']=='L4':
        assert max(areas)==0,('Target evidence in opaque scoring window',directory.name,areas)
    else:
        assert min(areas)>20,('Visible target absent',directory.name,areas)
    classes=counterfactual_extent_classes(observed,layout=row['layout'],camera=eye)
    result={**row,'unit':directory.name,'condition_id':spec['condition_id'],'targets':list(win.labels),'state_positions':observed.tolist(),'fully_occluded':[c.name=='EXTENT_FULLY_OCCLUDED' for c in classes],'action_payload':json.loads(next(iter(payloads))),'target_magenta_areas':areas,'bank_sha256':sha(directory/'BANKED.json'),'status':'VERIFIED'}
    save(ROOT/'verified_units'/f'{directory.name}.json',result)
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--partial',action='store_true')
    args=parser.parse_args()
    draft=read(ROOT/'cohort_geometry_draft.json')
    admission=read(ROOT/'capture_admission.json')
    assert admission['admitted'] and admission['cohort_sha256']==sha(ROOT/'cohort_geometry_draft.json')
    assert admission['protocol_sha256']==sha(Path(__file__).parent/'PROTOCOL.md')
    assert read(ROOT/'seed_independence.json')['status']=='PASS'
    units={}
    for row in draft['identities']:
        for condition in ['L0','L4']:
            unit=f"{row['identity']}__{condition}"
            if not (ROOT/'captures'/unit/'BANKED.json').exists() and args.partial:
                continue
            output=ROOT/'verified_units'/f'{unit}.json'
            if output.exists():
                result=read(output)
                assert result['bank_sha256']==sha(ROOT/'captures'/unit/'BANKED.json')
            else:
                result=verify(ROOT/'captures'/unit,row)
            # A verification manifest is distinct from its preserved preflight
            # draft. Explicitly resolve the draft's provisional target status.
            units[unit]={**result,'target_label_status':'FROZEN_FIR_REFERENCE_ADMITTED_AFTER_PILOT_CHECKS','capture_admission_sha256':sha(ROOT/'capture_admission.json')}
            print('VERIFIED',len(units),150,unit,flush=True)
    if args.partial:
        print('PARTIAL_VERIFIED',len(units),flush=True)
        return
    assert len(units)==150
    assert len({json.dumps(r['action_payload'],sort_keys=True) for r in units.values()})==1
    for row in draft['identities']:
        a,b=(units[f"{row['identity']}__{c}"] for c in ['L0','L4'])
        for key in ['targets','state_positions','target_model_frame_indices','action_payload']:
            assert a[key]==b[key],(row['identity'],key)
    folds={}
    for cohort in ['replication','geometry','speed']:
        identities=[r for r in draft['identities'] if r['cohort']==cohort]
        folds[cohort]=[]
        for f in range(5):
            held=[r['identity'] for r in identities if r['outer_fold']==f]
            train=[r['identity'] for r in identities if r['outer_fold']!=f]
            inner={str(j):[r['identity'] for r in identities if r['outer_fold']==j] for j in range(5) if j!=f}
            assert len(held)==5 and len(train)==20 and not set(train)&set(held)
            folds[cohort].append(dict(outer_fold=f,held_out_identities=held,training_identities=train,inner_rotations=inner))
    save(ROOT/'manifest.json',dict(status='ALL_150_VERIFIED',units=units,folds=folds,protocol_sha256=sha(Path(__file__).parent/'PROTOCOL.md'),draft_sha256=sha(ROOT/'cohort_geometry_draft.json')))


if __name__=='__main__':
    main()
