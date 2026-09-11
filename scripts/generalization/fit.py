"""Identity-grouped nested fits and privileged-motion comparisons."""
import argparse
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','4')
os.environ.setdefault('OMP_NUM_THREADS','4')
import json
from pathlib import Path
import sys
import time
import numpy as np
from prepare import ROOT,SOURCE,read,save,sha
sys.path.insert(0,str(SOURCE/'scripts/rgb_replication'))
from fit_readouts import predict_alphas,ALPHAS
from mineocclude.experiment_iii.baselines_motion import last_seen,constant_velocity,fit_time_only,predict_time_only
from mineocclude.experiment_iii.readout import FoldData,cross_validated_predictions

OUT=ROOT/'analysis'


def fit_condition(model,cohort,condition,manifest):
    path=OUT/'predictions'/f'{model}__{cohort}__{condition}.json'
    if path.exists():
        print('PRESERVED',path.name,flush=True)
        return
    info={r['identity']:r for r in manifest['units'].values() if r['cohort']==cohort and r['condition_id']==condition}
    names=sorted(info)
    assert len(names)==25
    y={i:np.array(info[i]['targets']) for i in names}
    arrays={i:np.load(OUT/'features'/model/f'{i}__{condition}.npy',allow_pickle=False) for i in names}
    cells=[]
    selections=[]
    predictions_by_id={}
    started=time.monotonic()
    for fold in manifest['folds'][cohort]:
        train,held=fold['training_identities'],fold['held_out_identities']
        assert not set(train)&set(held)
        scores=[]
        for _,val in sorted(fold['inner_rotations'].items()):
            fit=[i for i in train if i not in val]
            pred=predict_alphas(np.concatenate([arrays[i] for i in fit]),np.concatenate([y[i] for i in fit]),np.concatenate([arrays[i] for i in val]))
            error=pred-np.concatenate([y[i] for i in val])[:,None]
            scores.append(np.sqrt((error**2).reshape(len(val),19,5).mean(axis=1)).mean(axis=0))
        scores=np.mean(scores,axis=0)
        alpha=float(ALPHAS[np.argmin(scores)])
        pred=predict_alphas(np.concatenate([arrays[i] for i in train]),np.concatenate([y[i] for i in train]),np.concatenate([arrays[i] for i in held]),[alpha])[:,0]
        selections.append(dict(fold=fold['outer_fold'],alpha=alpha,inner_scores=scores.tolist(),training_identities=train,held_out_identities=held))
        for n,i in enumerate(held):
            predictions_by_id[i]=pred[n*19:(n+1)*19]
            for j,value in enumerate(predictions_by_id[i]):
                cells.append(dict(identity=i,cohort=cohort,condition_id=condition,model=model,outer_fold=fold['outer_fold'],row_index=j,model_frame_idx=info[i]['target_model_frame_indices'][j],context_age=info[i]['context_ages'][j],target=float(y[i][j]),prediction=float(value)))
        print('FIT',model,cohort,condition,fold['outer_fold'],round(time.monotonic()-started,1),flush=True)
    # Check complete 25-identity fit against unmodified reference implementation.
    if cohort=='replication':
        data={i:FoldData(identity=i,features=arrays[i],targets=y[i]) for i in names}
        reference,_=cross_validated_predictions(data,manifest['folds'][cohort])
        maximum=max(float(np.max(abs(reference[i]-predictions_by_id[i]))) for i in names)
        assert maximum<1e-8,maximum
    else:
        maximum=None
    save(path,dict(cells=cells,selections=selections,seconds=time.monotonic()-started,reference_maximum_error=maximum,manifest_sha256=sha(ROOT/'manifest.json'),feature_hashes={i:sha(OUT/'features'/model/f'{i}__{condition}.npy') for i in names}))


def motion(cohort,manifest):
    path=OUT/'predictions'/f'MOTION__{cohort}.json'
    if path.exists():
        return
    info={r['identity']:r for r in manifest['units'].values() if r['cohort']==cohort and r['condition_id']=='L0'}
    cells=[]
    for fold in manifest['folds'][cohort]:
        train,held=fold['training_identities'],fold['held_out_identities']
        ages=[age for i in train for age in info[i]['context_ages']]
        directions=[info[i]['direction'] for i in train for _ in range(19)]
        targets=[v for i in train for v in info[i]['targets']]
        beta=fit_time_only(ages,directions,targets)
        for i in held:
            r=info[i]
            predictors={
                'DIRECTION_AGE':predict_time_only(beta,r['context_ages'],[r['direction']]*19),
                'TRAINING_MEAN':np.repeat(np.mean(targets),19),
                # Match the EXECUTED original implementation: raw server-state
                # position history, evaluated against FIR-aligned targets.
                'ORACLE_LAST_SEEN':[last_seen(r['state_positions'],r['fully_occluded'],t) for t in r['target_model_frame_indices']],
                'ORACLE_CONSTANT_VELOCITY':[constant_velocity(r['state_positions'],r['fully_occluded'],t) for t in r['target_model_frame_indices']],
            }
            for model,pred in predictors.items():
                for condition in ['L0','L4']:
                    for j,value in enumerate(pred):
                        cells.append(dict(identity=i,cohort=cohort,condition_id=condition,model=model,outer_fold=fold['outer_fold'],row_index=j,model_frame_idx=r['target_model_frame_indices'][j],context_age=r['context_ages'][j],target=r['targets'][j],prediction=float(value)))
    save(path,dict(cells=cells,oracle_information='Privileged raw server position before counterfactual full occlusion; matches original executed a12_predictions.load_identity_inputs, not its misleading FIR-history docstring.',manifest_sha256=sha(ROOT/'manifest.json')))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--models',nargs='+',default=['PIXEL_CURRENT','PIXEL_HISTORY16','MW_RGB_L19'])
    args=parser.parse_args()
    manifest=read(ROOT/'manifest.json')
    assert manifest['status']=='ALL_150_VERIFIED'
    for cohort in ['replication','geometry','speed']:
        motion(cohort,manifest)
        for model in args.models:
            for condition in ['L0','L4']:
                fit_condition(model,cohort,condition,manifest)
