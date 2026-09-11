from common import *
import argparse
import numpy as np
from fit_diag import Ridge,predict_frozen

ALPHAS=np.array([.1,1.,10.,100.,1000.])

def main():
    p=argparse.ArgumentParser();p.add_argument('--model',required=True);p.add_argument('--opacity',action='store_true');a=p.parse_args()
    out=ROOT/'central'
    pkg=SOURCE/'reproducibility/experiment_iii_a/cohort'
    targets=read(pkg/'EXECUTED_TARGETS.json')['rows']
    folds=read(pkg/'FOLD_ASSIGNMENTS.json')['folds']
    names=sorted({r['identity'] for r in targets})
    conditions=['A000','A025','A050','A075','A100'] if a.opacity else ['L0','L1','L2','L3','L4']
    mapping={(r['identity'],r['row_index']):r['target'] for r in targets if r['condition_id']=='L0'}
    y={i:np.array([mapping[i,j] for j in range(19)]) for i in names}
    lock=out/f'{a.model}_analysis_lock.json'
    if not lock.exists():
        save(lock,dict(model=a.model,script_sha256=sha(Path(__file__)),alphas=ALPHAS.tolist(),folds_sha256=sha(pkg/'FOLD_ASSIGNMENTS.json'),grouping='identity',bootstrap=10000,seed=94112,primary_metric='mean identity RMSE, all 19 aligned rows',source_only_transfer=a.opacity))
    else: assert read(lock)['script_sha256']==sha(Path(__file__))
    for source in conditions:
        dest=out/'predictions'/f'{a.model}__{source}.json'
        if dest.exists():continue
        x={i:np.load(out/'features'/a.model/f'{i}__{source}.npy',allow_pickle=False) for i in names}
        cells=[]; selections=[]
        for f in folds:
            train,held=f['training_identities'],f['held_out_identities']
            scores=[]
            for _,val in sorted(f['inner_rotations'].items()):
                fit=[i for i in train if i not in val]
                model=Ridge(np.concatenate([x[i] for i in fit]),np.concatenate([y[i] for i in fit]))
                pred=model.predict(np.concatenate([x[i] for i in val]),ALPHAS)
                truth=np.concatenate([y[i] for i in val])
                scores.append(np.sqrt(((pred-truth[:,None])**2).reshape(len(val),19,5).mean(1)).mean(0))
            score=np.mean(scores,0); alpha=float(ALPHAS[np.argmin(score)])
            model=Ridge(np.concatenate([x[i] for i in train]),np.concatenate([y[i] for i in train]))
            fitpath=out/'fits'/f'{a.model}__{source}__{f["outer_fold"]}.npz'
            fitpath.parent.mkdir(parents=True,exist_ok=True)
            assert not fitpath.exists()
            model.freeze(fitpath,alpha)
            for condition in (conditions if a.opacity else [source]):
                q=np.concatenate([np.load(out/'features'/a.model/f'{i}__{condition}.npy',allow_pickle=False) for i in held])
                pred=model.predict(q,[alpha])[:,0]
                assert np.max(abs(pred-predict_frozen(fitpath,q)))<1e-8
                for n,i in enumerate(held):
                    for j in range(19):cells.append(dict(identity=i,row_index=j,condition=condition,source=source,outer_fold=f['outer_fold'],target=float(y[i][j]),prediction=float(pred[n*19+j]),model=a.model))
            selections.append(dict(fold=f['outer_fold'],alpha=alpha,training=train,held=held,scores=score.tolist(),fit_sha256=sha(fitpath)))
        save(dest,dict(cells=cells,selections=selections,analysis_lock_sha256=sha(lock)))
        print('FIT',a.model,source,flush=True)
    rng=np.random.default_rng(94112); draws=rng.integers(0,25,(10000,25)); results=[]
    for source in conditions:
        cells=read(out/'predictions'/f'{a.model}__{source}.json')['cells']
        for condition in (conditions if a.opacity else [source]):
            e=np.array([[r['prediction']-r['target'] for r in cells if r['identity']==i and r['condition']==condition] for i in names])
            rmse=np.sqrt(np.mean(e**2,axis=1))
            results.append(dict(source=source,condition=condition,rmse=float(rmse.mean()),rmse_ci=np.quantile(rmse[draws].mean(1),[.025,.975]).tolist(),mae=float(abs(e).mean())))
    save(out/f'{a.model}_statistics.json',dict(model=a.model,results=results,seed=94112))
    print('COMPLETE',a.model,json.dumps(results),flush=True)

if __name__=='__main__':main()
