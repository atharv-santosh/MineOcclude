from common import *
import numpy as np
from fit_diag import predict_frozen
from mineocclude.experiment_iii.fir import fir_labels

def main():
    roster=read(MOTION_ROSTER)['rows']
    r=next(r for r in roster if r['partition']=='test' and r['layout_id']=='layout_01' and r['variant']==0)
    unit=r['identity']+'__L4'
    indices=r['target_model_frame_indices']
    base=ROOT/'captures'/unit/'client'
    observed={str(k):sha(base/'frames'/f'{k:06d}.png') for k in sorted({t-j for t in indices for j in range(16)})}
    observed['actions']=sha(base/'raw_actions.jsonl')
    input_a=dict(observed);input_b=dict(observed)
    assert seal(input_a)==seal(input_b)
    first=indices[0];prefix=r['state_positions'][:first]
    start=r['state_positions'][first];d=1. if r['direction']=='LEFT_TO_RIGHT' else -1.
    futures=[prefix+[start+d*rate*j for j in range(19)] for rate in [0.,.03]]
    targets=[fir_labels(f,indices,r['direction']) for f in futures]
    x=np.load(ROOT/'motion/features/MW_700M'/f'{unit}.npy',allow_pickle=False)
    fit=ROOT/'motion/fits/MW_700M__layout_01__L4.npz'
    pred_a=predict_frozen(fit,x.copy());pred_b=predict_frozen(fit,x.copy())
    assert np.array_equal(pred_a,pred_b)
    assert max(abs(np.array(targets[0])-targets[1]))>.1
    save(ROOT/'motion/identical_input_control.json',dict(status='PASS',kind='Constructed information-boundary control; not a second physical capture or empirical branch-identification experiment',identity=r['identity'],observed_input_sha256=seal(input_a),feature_sha256=sha(ROOT/'motion/features/MW_700M'/f'{unit}.npy'),fit_sha256=sha(fit),alternative_targets=targets,predictions=[pred_a.tolist(),pred_b.tolist()],prediction_max_difference=0.,target_max_difference=float(np.max(abs(np.array(targets[0])-targets[1]))),claim='Changing a scoring label cannot reveal an unobserved random future to a deterministic model receiving identical full inputs.'))
    print('IDENTICAL_INPUT_CONTROL_PASS',flush=True)

if __name__=='__main__':main()
