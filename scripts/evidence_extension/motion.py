from common import *
import numpy as np
from plan_cohort import layout_config
from mineocclude.experiment_iii.cohort import path_sha256, noise_sha256
from mineocclude.experiment_iii.target_manifest import build_target_window
from mineocclude.experiment_iii.extent_geometry import classify_counterfactual_extent
from functools import lru_cache
import argparse

FAMILIES=['velocity','acceleration','stop_resume','reversal']

@lru_cache(None)
def entry_position(layout_id,sign):
    outside=-8.*sign; inside=0.
    for _ in range(50):
        mid=(outside+inside)/2
        if classify_counterfactual_extent(mid,layout=layout_config(layout_id)).name=='EXTENT_FULLY_OCCLUDED': inside=mid
        else: outside=mid
    return inside+sign*.001

def make(family, layout_id, partition, rank, variant, matched=False, revised_velocity=False, extended_approach=False):
    family_id=f'e26_{layout_id}_{partition}_{family}_{rank:02d}'
    seed=int.from_bytes(hashlib.sha256(family_id.encode()).digest()[:7],'big')
    rng=np.random.default_rng(seed)
    sign=1 if rank%2==0 else -1
    direction='LEFT_TO_RIGHT' if sign==1 else 'RIGHT_TO_LEFT'
    speed=float(rng.uniform(1.4,1.9) if variant==0 else rng.uniform(2.65,2.8) if revised_velocity and family=='velocity' else rng.uniform(2.8,3.5))
    t=np.arange(180)
    if family=='velocity':
        v=np.full(180,speed)
    elif family=='acceleration':
        acceleration=float(rng.uniform(.8,1.5))*(1 if variant else -1)
        v=np.clip(speed+acceleration*(t-50)*.05,.25,4.5)
        v[:30]=v[30]
    elif family=='stop_resume':
        period=12
        phase=0 if variant==0 else 6
        v=np.where((t+phase)%period<8,speed*1.5,0.)
    else:
        phase=0 if variant==0 else 6
        v=speed+3.8*np.sin(2*np.pi*(t+phase)/12)
    v[:20]=0.
    v[110:]=0.
    velocities=v*sign
    layout=layout_config(layout_id)
    camera=[.5,5.6200000048,-5.5]
    identity=f'{family_id}_v{variant}'
    chosen=None
    for start_mag in np.linspace(7.2 if matched else 7.8,5.0,57):
        start=-sign*float(start_mag)
        path=[]
        x=start
        for value in velocities:
            x=min(8.,max(-8.,(x+float(value)*.05)+0.))
            path.append(x)
        try:
            win=build_target_window(identity,direction,path,layout=layout,camera=camera)
            indices=list(win.target_model_frame_indices)
            assert 30<=indices[0]<=85
            assert max(abs(np.array(path)[indices]))<7.9
            if family!='velocity':
                segment=velocities[indices[0]-15:indices[0]+10]
                assert np.ptp(segment)>.3
            chosen=(start,path,win)
            break
        except Exception:
            pass
    assert chosen is not None,(family,layout_id,rank,variant)
    start,path,win=chosen
    if matched:
        matched_choice=None
        for first in range(42 if extended_approach and family=='stop_resume' and variant==0 else 30,86):
            trial_start=entry_position(layout_id,sign)-float(np.sum(velocities[:first+1])*.05)
            if abs(trial_start)>7.5: continue
            shifted=[]; x=trial_start
            for value in velocities:
                x=min(8.,max(-8.,(x+float(value)*.05)+0.))
                shifted.append(x)
            try:
                trial=build_target_window(identity,direction,shifted,layout=layout,camera=camera)
                assert trial.target_model_frame_indices[0]==first
                assert abs(shifted[first]-entry_position(layout_id,sign))<1e-10
                if family!='velocity': assert np.ptp(velocities[first-15:first+10])>.3
                matched_choice=(trial_start,shifted,trial)
                break
            except Exception:pass
        assert matched_choice is not None,(family,layout_id,rank,variant,'matched entry infeasible')
        start,path,win=matched_choice
    row=dict(identity=identity,family_id=family_id,family=family,layout_id=layout_id,layout=layout,camera=camera,partition=partition,rank=rank,variant=variant,direction=direction,seed=seed,start_world_x=start,speed_blocks_per_second=speed,motion_noise_q=0.,frames=180,dt_seconds=.05,signed_velocities=velocities.tolist(),state_positions=path,path_sha256=path_sha256(path),noise_sha256=noise_sha256(np.zeros(180)),target_model_frame_indices=list(win.target_model_frame_indices),historical_FIR_reference_labels=list(win.labels),outer_fold=rank%4)
    row['spec_hash']=seal(row)
    return row

def main():
    p=argparse.ArgumentParser();p.add_argument('--matched',action='store_true');a=p.parse_args()
    rows=[make(f,l,'pilot_matched' if a.matched else 'pilot',rank,v,a.matched) for f in FAMILIES for l in ['layout_01','layout_04'] for rank in ([0,1] if a.matched else [0]) for v in [0,1]]
    save(ROOT/('motion_pilots_matched.json' if a.matched else 'motion_pilots.json'),dict(status='ENGINEERING_ONLY',rows=rows,protocol_sha256=sha(Path(__file__).with_name('PROTOCOL.md'))))
    config=read(OLD/'runtime.json')
    config['output_root']=str(ROOT/'capture_logs')
    if not (ROOT/'runtime.json').exists():save(ROOT/'runtime.json',config)
    print('PILOT_ROSTER',len(rows),flush=True)

if __name__=='__main__':
    main()
