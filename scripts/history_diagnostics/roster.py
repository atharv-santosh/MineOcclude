from diag_common import *
import numpy as np
from plan_cohort import layout_config
from mineocclude.experiment_iii.cohort import generate_path,path_sha256,noise_sha256
from mineocclude.experiment_iii.target_manifest import build_target_window


def build_row(layout_id,partition,d,j,speed=None):
    identity=f'h26_{layout_id}_{partition}_{d}_{j:02d}'
    for attempt in range(100):
        seed=int.from_bytes(hashlib.sha256(f'{identity}-v1-{attempt}'.encode()).digest()[:7],'big')
        rng=np.random.default_rng(seed^0xC78A)
        velocity=float(rng.uniform(.8,1.6) if j<6 else rng.uniform(2.4,3.2)) if speed is None else speed
        start=float(rng.uniform(7.3,7.9))*(-1 if d==0 else 1)
        direction=['LEFT_TO_RIGHT','RIGHT_TO_LEFT'][d]
        layout=layout_config(layout_id)
        camera=[.5,5.6200000048,-5.5]
        path,noise=generate_path(seed,.05,direction=direction,start_world_x=start,speed=velocity)
        try:
            win=build_target_window(identity,direction,path,layout=layout,camera=camera)
            assert win.target_model_frame_indices[0]>=16
            assert max(abs(path[list(win.target_model_frame_indices)]))<8
        except Exception as error:
            print('GEOMETRY_REJECT',identity,attempt,str(error),flush=True)
            continue
        row=dict(identity=identity,cohort=layout_id,layout_id=layout_id,layout=layout,camera=camera,partition=partition,direction=direction,direction_index=d,rank=j,seed=seed,start_world_x=start,speed_blocks_per_second=velocity,frames=180,motion_noise_q=.05,dt_seconds=.05,outer_fold=j%4,path_sha256=path_sha256(path),noise_sha256=noise_sha256(noise),target_model_frame_indices=list(win.target_model_frame_indices),historical_FIR_reference_labels=list(win.labels),context_ages=list(win.context_ages),last_preocclusion_model_frame_idx=win.last_preocclusion_model_frame_idx,donor=f'h26_{layout_id}_{partition}_{d}_{(j+6)%12:02d}' if partition!='pilot' else None,candidate_attempt=attempt)
        row['spec_hash']=seal(row)
        return row
    raise RuntimeError(identity)


def main():
    assert not (ROOT/'roster.json').exists()
    ROOT.mkdir(parents=True,exist_ok=True)
    rows=[build_row(layout,part,d,j) for part in ['train','test'] for layout in ['layout_01','layout_04'] for d in [0,1] for j in range(12)]
    pilots=[build_row(layout,'pilot',d,j,speed) for layout in ['layout_01','layout_04'] for d in [0,1] for j,speed in enumerate([.8,3.2])]
    old={r['seed'] for r in read(PREVIOUS/'cohort_geometry_draft.json')['identities']}
    old.update(r['seed'] for r in lines(SOURCE/'docs/experiment_iii/cohort/production_identity_manifest.jsonl'))
    assert not old & {r['seed'] for r in rows+pilots}
    assert len({r['seed'] for r in rows+pilots})==104
    save(ROOT/'roster.json',dict(status='PROSPECTIVE_NOT_YET_CAPTURE_ADMITTED',identities=rows,pilots=pilots,protocol_sha256=sha(Path(__file__).parent/'PROTOCOL.md')))
    config=read(PREVIOUS/'runtime.json')
    config['output_root']=str(ROOT/'logs')
    save(ROOT/'runtime.json',config)
    print('ROSTER',len(rows),'PILOTS',len(pilots),sha(ROOT/'roster.json'),flush=True)

if __name__=='__main__':
    main()
