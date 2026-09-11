"""Train-only grouped ridge, sharing preprocessing and Gram across alphas."""
import argparse
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault('OPENBLAS_NUM_THREADS', '8')
os.environ.setdefault('OMP_NUM_THREADS', '8')
import numpy as np
from scipy.linalg import eigh
from audit_recovery import ROOT, PKG, OUT, read, save, sha
sys.path.insert(0, str(ROOT / 'src'))
ALPHAS = np.array([.1, 1., 10., 100., 1000.])


def predict_alphas(x, y, test, alphas=ALPHAS):
    x = np.asarray(x,dtype=np.float64)
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale[scale == 0] = 1
    z = (x-mean)/scale
    q = (np.asarray(test,dtype=np.float64)-mean)/scale
    gram = z @ z.T
    centered = y-y.mean()
    columns=[]
    for alpha in alphas:
        dual=np.linalg.solve(gram+float(alpha)*np.eye(len(y)),centered)
        coefficients=z.T @ dual
        # Match reference evaluation in 19-row identity blocks. Near-constant
        # image columns can amplify otherwise harmless reordered arithmetic.
        columns.append(np.concatenate([q[k:k+19] @ coefficients+y.mean() for k in range(0,len(q),19)]))
    return np.stack(columns,axis=1)


def verify_solver():
    from mineocclude.probes.ridge import fit_ridge
    from mineocclude.experiment_iii.baselines_pixel import pixel_features
    rng = np.random.default_rng(20260911)
    x = rng.normal(size=(57,139))
    x[:,0] = 1
    x[:,1] = x[:,2]
    y, test = rng.normal(size=57), rng.normal(size=(19,139))
    test[:,0] = 1
    test[:,1] = test[:,2]
    efficient = predict_alphas(x,y,test)
    errors = []
    for j,alpha in enumerate(ALPHAS):
        reference = fit_ridge(x,y,alpha=float(alpha)).predict(test)
        errors.append(float(np.max(abs(efficient[:,j]-reference))))
    assert max(errors)<1e-9,errors
    save(OUT / 'solver_validation.json',{'status':'PASS','maximum_error':max(errors),'alpha_errors':errors,'training_constant_and_collinear_features_tested':True})
    print('SOLVER_EQUIVALENCE_PASS',max(errors),flush=True)


def fit_one(model, condition):
    targets = read(PKG/'cohort/EXECUTED_TARGETS.json')['rows']
    folds = read(PKG/'cohort/FOLD_ASSIGNMENTS.json')['folds']
    names = sorted({r['identity'] for r in targets})
    row_map = {(r['identity'],r['row_index']):r for r in targets if r['condition_id']==condition}
    ys = {i:np.array([row_map[i,j]['target'] for j in range(19)]) for i in names}
    arrays = {i:np.load(OUT/'features'/model/f'{i}__{condition}.npy',allow_pickle=False) for i in names}
    assert all(a.shape[0]==19 and np.isfinite(a).all() for a in arrays.values())
    cells, selections = [],[]
    started = time.perf_counter()
    for fold in folds:
        train,held = fold['training_identities'],fold['held_out_identities']
        assert not set(train)&set(held)
        rotation_scores = []
        for _,val in sorted(fold['inner_rotations'].items()):
            fit = [i for i in train if i not in val]
            predictions = predict_alphas(np.concatenate([arrays[i] for i in fit]),np.concatenate([ys[i] for i in fit]),np.concatenate([arrays[i] for i in val]))
            truth = np.concatenate([ys[i] for i in val])
            scores = np.sqrt(((predictions-truth[:,None])**2).reshape(len(val),19,5).mean(axis=1)).mean(axis=0)
            rotation_scores.append(scores)
        scores = np.mean(rotation_scores,axis=0)
        alpha = float(ALPHAS[np.argmin(scores)])
        predictions = predict_alphas(np.concatenate([arrays[i] for i in train]),np.concatenate([ys[i] for i in train]),np.concatenate([arrays[i] for i in held]),[alpha])[:,0]
        selections.append({'outer_fold':fold['outer_fold'],'alpha':alpha,'inner_scores':scores.tolist(),'held_out':held})
        for n,identity in enumerate(held):
            for j in range(19):
                cells.append({**row_map[identity,j],'model':model,'prediction':float(predictions[n*19+j])})
        print('FIT',model,condition,'fold',fold['outer_fold'],'alpha',alpha,'seconds',round(time.perf_counter()-started,1),flush=True)
    assert len(cells)==475
    path = OUT/'predictions'/f'{model}__{condition}.json'
    save(path,{'model':model,'condition':condition,'cells':cells,'selections':selections,'elapsed_seconds':time.perf_counter()-started,'folds_sha256':sha(PKG/'cohort/FOLD_ASSIGNMENTS.json'),'protocol_sha256':sha(Path(__file__).parent/'PROTOCOL.md'),'feature_sha256':{i:sha(OUT/'features'/model/f'{i}__{condition}.npy') for i in names}})


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--models',nargs='+',default=['PIXEL_CURRENT','PIXEL_HISTORY16'])
    parser.add_argument('--conditions',nargs='+',default=['L0','L1','L2','L3','L4'])
    parser.add_argument('--test-only',action='store_true')
    args=parser.parse_args()
    verify_solver()
    if not args.test_only:
        for model in args.models:
            for condition in args.conditions:
                path=OUT/'predictions'/f'{model}__{condition}.json'
                if path.exists():
                    print('EXISTING_PREDICTIONS_PRESERVED',path.name,flush=True)
                else:
                    fit_one(model,condition)
