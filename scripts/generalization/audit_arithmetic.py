"""Independent target-sum and historical executed-oracle checks."""
import math
import numpy as np
from prepare import ROOT,SOURCE,read,lines,save
from mineocclude.experiment_iii.cohort import generate_path
from mineocclude.experiment_iii.fir import frozen_kernel
from mineocclude.experiment_iii.a12_predictions import load_identity_inputs
from mineocclude.experiment_iii.baselines_motion import last_seen,constant_velocity


def main():
    errors=[]
    for row in read(ROOT/'cohort_geometry_draft.json')['identities']:
        positions,_=generate_path(row['seed'],row['motion_noise_q'],direction=row['direction'],start_world_x=row['start_world_x'],speed=row['speed_blocks_per_second'],frames=180)
        kernel=frozen_kernel(row['direction'])
        labels=[math.fsum(kernel[k]*float(positions[t-k]) for k in range(9)) for t in row['target_model_frame_indices']]
        errors.extend(abs(np.array(labels)-row['historical_FIR_reference_labels']))
    maximum=float(max(errors))
    assert maximum<1e-12,maximum
    historical=lines(SOURCE/'docs/experiment_iii/cohort/production_identity_manifest.jsonl')
    cells=read(SOURCE/'reproducibility/experiment_iii_a/prediction_lock/PREDICTION_LOCK.json')['cells']
    expected={(r['identity'],r['model'],r['row_index']):r['prediction'] for r in cells if r['condition_id']=='L0' and r['model'] in ['LAST_SEEN','CONSTANT_VELOCITY']}
    differences=[]
    for r in historical:
        info=load_identity_inputs(r['identity'],r,SOURCE/'recovery_inputs/corpus/captures'/f"{r['identity']}__L0")
        for model,fn in [('LAST_SEEN',last_seen),('CONSTANT_VELOCITY',constant_velocity)]:
            for j,t in enumerate(info.target_rows):
                pred=fn(info.positions,info.occluded,t)
                differences.append(abs(pred-expected[r['identity'],model,j]))
    assert max(differences)<1e-12,max(differences)
    save(ROOT/'arithmetic_audit.json',dict(status='PASS',new_target_fsum_max_absolute_difference=maximum,new_target_count=len(errors),historical_oracle_max_absolute_difference=max(differences),historical_oracle_cells_checked=len(differences),explanation='Existing FIR helper accumulates with Python sum; the historical exact reconstruction used math.fsum. The formula and taps are identical, with only binary64 summation rounding. Historical oracle inputs are raw server coordinates.'))
    print('ARITHMETIC_AUDIT_PASS',maximum,max(differences))


if __name__=='__main__':
    main()
