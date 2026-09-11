"""Freeze fresh identities using only commanded trajectories and geometry."""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

SOURCE=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(SOURCE/'src'))
from mineocclude.experiment_iii.cohort import generate_path, path_sha256, noise_sha256
from mineocclude.experiment_iii.target_manifest import build_target_window
from mineocclude.experiment_iii.authority import LAYOUT_01

ROOT=Path('/home/bpcfno/mineocclude-generalization-20260911')
COHORTS=[('replication','layout_01',2.),('geometry','layout_04',2.),('speed','layout_01',3.)]


def sha(body):
    return hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def layout_config(name):
    layout=dict(LAYOUT_01)
    if name=='layout_04':
        layout.update(layout_id=name,wall_ortho_const=8.,wall_ortho_offset=-5.)
    return layout


def main():
    destination=ROOT/'cohort_geometry_draft.json'
    assert not destination.exists(),'Preserve existing roster'
    historical=[json.loads(s) for s in (SOURCE/'docs/experiment_iii/cohort/production_identity_manifest.jsonl').read_text().splitlines()]
    oldseeds={r['seed'] for r in historical}
    rows=[]
    rejected=[]
    for c,(name,layoutid,speed) in enumerate(COHORTS):
        layout=layout_config(layoutid)
        # Both selected layouts put the camera at the same world Z; physical
        # receipts must verify this prediction before the roster is admitted.
        camera=(.5,5.6200000048,-5.5)
        counts=[0,0]
        candidate=0
        while sum(counts)<25 and candidate<10000:
            d=candidate%2
            candidate+=1
            if counts[d]>=[13,12][d]:
                continue
            domain=f'mineocclude-fresh-generalization-20260911-{name}-{candidate}'
            seed=int.from_bytes(hashlib.sha256(domain.encode()).digest()[:7],'big')
            assert seed not in oldseeds
            rng=np.random.default_rng(seed^0x97AF)
            start=float(rng.uniform(7.3,7.9))*(-1 if d==0 else 1)
            direction=['LEFT_TO_RIGHT','RIGHT_TO_LEFT'][d]
            path,noise=generate_path(seed,.05,direction=direction,start_world_x=start,speed=speed)
            identity=f'g26_{name}_{sum(counts)+1:02d}'
            try:
                win=build_target_window(identity,direction,path,layout=layout,camera=camera)
                targets=np.asarray(win.target_model_frame_indices)
                assert targets[0]>=16
                assert not np.any(np.abs(path[targets])>=8)
                assert np.std(win.labels,ddof=1)>.10
            except Exception as e:
                rejected.append(dict(cohort=name,candidate=candidate,seed=seed,reason=str(e)))
                continue
            index=sum(counts)
            row=dict(identity=identity,cohort=name,layout_id=layoutid,layout=layout,camera=list(camera),speed_blocks_per_second=speed,direction=direction,seed=seed,start_world_x=start,frames=180,motion_noise_q=.05,dt_seconds=.05,outer_fold=index%5,path_sha256=path_sha256(path),noise_sha256=noise_sha256(noise),target_model_frame_indices=list(win.target_model_frame_indices),historical_FIR_reference_labels=list(win.labels),target_label_status='PROVISIONAL_PENDING_PILOT_ALIGNMENT',last_preocclusion_model_frame_idx=win.last_preocclusion_model_frame_idx,context_ages=list(win.context_ages),candidate=candidate)
            row['spec_hash']=sha(row)
            rows.append(row)
            counts[d]+=1
            print(name,len(rows),identity,seed,flush=True)
        assert sum(counts)==25
    assert len({r['seed'] for r in rows})==75
    body=dict(status='GEOMETRY_DRAFT_NOT_CAPTURE_AUTHORIZATION',cohorts=COHORTS,identities=rows,rejected_geometry_candidates=rejected,criteria='First 19 consecutive extent-occluded rows, >=16 frames context available, no target-boundary clamp, target SD >0.10. No decoder outputs inspected.',protocol_sha256=hashlib.sha256((Path(__file__).parent/'PROTOCOL.md').read_bytes()).hexdigest())
    body['manifest_sha256']=sha(body)
    destination.write_text(json.dumps(body,indent=2,allow_nan=False)+'\n')
    print('DRAFT_SAVED',body['manifest_sha256'],flush=True)


if __name__=='__main__':
    main()
